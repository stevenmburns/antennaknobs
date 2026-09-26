// AK#1762: a design's load resets (the band snap, the ground seed, the
// camera snap) used to run in passive effects, a Scheduler task after the
// commit that shows the new design. Two consequences, both reproduced:
//
//  - the FIRST interaction landing in that gap was overwritten by the late
//    reset (a ground-switch click, a camera pick: lost every time);
//  - the measurement dial and its range menu were live before the catalog
//    had loaded any design, and the load's band snap replaced an edit made
//    there (a range edited to 20 MHz came back as the deck's 14–14.35).
//
// The resets now run during render, in the same render as the design they
// belong to, and the dial is inert until a design is loaded. Each test acts
// exactly where the old code lost the action: a MutationObserver callback
// (untilDom) runs after the commit and before React's passive effects.
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import type { ExampleDescriptor } from "../lib/params";
import { HARNESS_EXAMPLE, mountDesignSession, sessionReady, untilDom } from "./designSessionHarness";

const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  param_schema: [
    {
      name: "gap", label: "Gap", default: 0.25, kind: "float", min: 0, max: 1,
      step: 0.05, precision: 2, unit: null, visible_when: null,
    },
  ],
  bands: [
    { key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 },
  ],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
  ground_seed: "pec",
  default_view: "xz",
};

function json(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) } as unknown as Response;
}

// The first moment the design is on screen: its knob, rendered in the commit
// that selects it.
const designShown = () =>
  untilDom(() => document.querySelector('[role="slider"][aria-label="Gap"]'));

const groundBox = () =>
  screen.getAllByRole("checkbox", { name: /ground plane/ })[0] as HTMLInputElement;

const activeProjection = () =>
  ["Top (xy)", "Front (xz)", "Side (yz)", "Iso"].filter((l) =>
    screen.queryAllByRole("button", { name: l }).some((b) => b.classList.contains("active")),
  );

afterEach(() => vi.unstubAllGlobals());

describe("the design's load resets do not overwrite the first interaction", () => {
  it("a ground-switch click the moment the design appears is kept", async () => {
    mountDesignSession({ examples: [DECK] });
    await designShown();
    // The deck seeds perfect ground: the switch is on.
    expect(groundBox().checked).toBe(true);
    fireEvent.click(groundBox());
    await sessionReady(document.body);
    expect(groundBox().checked).toBe(false);
  });

  it("a camera pick the moment the design appears is kept", async () => {
    mountDesignSession({ examples: [DECK] });
    await designShown();
    // The design's own view is already applied when it appears.
    expect(activeProjection()).toEqual(["Front (xz)"]);
    fireEvent.click(screen.getByRole("button", { name: "Iso" }));
    await sessionReady(document.body);
    expect(activeProjection()).toEqual(["Iso"]);
  });
});

describe("the dial before a design is loaded", () => {
  it("is inert, so no edit is made that the band snap would replace", async () => {
    let release: () => void = () => {};
    const held = new Promise<void>((r) => (release = r));
    mountDesignSession({
      examples: [DECK],
      routes: {
        "/examples": async () => {
          await held;
          return json({ examples: [DECK], errors: [] });
        },
      },
    });
    const dialBox = await untilDom(() => document.querySelector<HTMLElement>(".vfo-dial"));
    // The catalog is still loading: no design, so no range to edit.
    fireEvent.contextMenu(dialBox, { clientX: 40, clientY: 50 });
    expect(screen.queryByRole("dialog", { name: "sweep range" })).toBeNull();
    expect(
      screen.getByRole("slider", { name: "measurement frequency" }).getAttribute("aria-disabled"),
    ).toBe("true");
    release();
    await sessionReady(document.body);
    // Once the design is loaded the menu opens, and an edit there stays.
    fireEvent.contextMenu(dialBox, { clientX: 40, clientY: 50 });
    expect(screen.getByRole("dialog", { name: "sweep range" })).toBeTruthy();
  });
});
