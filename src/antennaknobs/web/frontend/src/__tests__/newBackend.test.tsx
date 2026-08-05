// The end-state probe for issue #628: a solver that exists ONLY in the served
// roster — no entry in any frontend list, no TypeScript written for it — must
// reach the user as a working tab.
//
// This mounts the real <DesignSession> against a stubbed /capabilities whose
// roster carries an invented "fake-solver", then checks the three things that
// make it usable end to end: its tab appears with the SERVED label, selecting
// it renders the knob from its served options_schema, and the request the
// session actually POSTs carries `momwire_model: "fake-solver"` with that
// knob's wire key in `model_options`. Nothing in src/ names it — that is the
// assertion. (The wire body is read off the /geometry preview POST, which is
// buildRequest() verbatim.)
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DesignSession } from "../components/session/DesignSession";
import type { BackendEntry } from "../lib/backends";
import type { ExampleDescriptor } from "../lib/params";
import { SERVED_ROSTER } from "./backendFixtures";

const FAKE: BackendEntry = {
  name: "fake-solver",
  label: "Fake Solver",
  kind: "momwire",
  supports_ground: false,
  options_schema: [
    {
      key: "n_qp_const",
      label: "n_qp_const (GL pts)",
      min: 2,
      max: 32,
      step: 1,
      default: 8,
    },
  ],
  panel: null,
  default_n_per_wire: 12,
  accelerator: false,
  dense_family: false,
};

const EXAMPLE: ExampleDescriptor = {
  name: "dipoles.probe",
  label: "Probe dipole",
  multi_feed: false,
  param_schema: [],
  result_schema: [],
  bands: [],
  meas_freq_range_mhz: null,
  default_view: "xz",
  default_freq: null,
  default_design_freq: null,
  default_backend: null,
  requires_backends: null,
  has_design_freq: true,
  variants: ["default"],
  variant_values: {},
  sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25 },
};

// Every POST body the session sent to /geometry — buildRequest() as JSON.
let geometryPosts: Record<string, unknown>[] = [];
// What /capabilities serves for the test at hand.
let servedRoster: BackendEntry[] = [];

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

beforeEach(() => {
  geometryPosts = [];
  servedRoster = [...SERVED_ROSTER, FAKE];
  // getContext/ResizeObserver/matchMedia/WebSocket provide-only defaults now
  // live in setup.ts (#728) — every component test gets them unconditionally,
  // including the never-matching matchMedia this file used to stub itself
  // (this session doesn't care about layout, so the desktop tree is fine).
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    const path = String(url);
    if (path.startsWith("/capabilities"))
      return jsonResponse({
        have_pynec: true,
        backends: servedRoster,
        terrain_presets: [],
      });
    if (path.startsWith("/examples"))
      return jsonResponse({ examples: [EXAMPLE], errors: [] });
    if (path.startsWith("/geometry")) {
      geometryPosts.push(JSON.parse(String(init?.body ?? "{}")));
      return jsonResponse({ wires: [] });
    }
    return jsonResponse({});
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a solver that exists only in the served roster (#628)", () => {
  it("gets a tab, its knob, and a correct request — with no frontend roster to edit", async () => {
    const user = userEvent.setup();
    render(<DesignSession id={1} active />);

    // The session waits for /capabilities: no hardcoded fallback roster.
    expect(screen.queryByRole("tablist")).toBeNull();
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Solver slot A/ })).toBeTruthy(),
    );

    // Pause the live solve so the session's own request refresh goes out over
    // POST /geometry (buildRequest verbatim) instead of the solve socket.
    await user.click(screen.getByRole("button", { name: "Live" }));

    // (a) the tab, labelled as SERVED — nothing in src/ knows this name.
    await user.click(screen.getByRole("button", { name: "Slot A options" }));
    const tab = screen.getByRole("tab", { name: "Fake Solver" });
    expect(tab.getAttribute("aria-selected")).toBe("false");

    // (b) selecting it renders the generic knob from its options_schema, at
    //     the served default.
    await user.click(tab);
    const knob = screen
      .getByText("n_qp_const (GL pts)")
      .closest(".field")
      ?.querySelector("input") as HTMLInputElement;
    expect(knob.value).toBe("8");
    expect(knob.min).toBe("2");
    expect(knob.max).toBe("32");
    // Segments/wire carries over from the slot's previous backend, as on
    // any manual swap — it is geometry sizing, not a solver kwarg.
    const nPerWire = screen
      .getByText("segments / wire (N)")
      .closest(".field")
      ?.querySelector("input") as HTMLInputElement;
    expect(nPerWire.value).toBe("15");
    // Its bespoke-panel-less roster entry shows no other solver's controls.
    expect(screen.queryByRole("tab", { name: "d=2" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Converged" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Close" }));

    // (c) the request the session builds names it as a momwire model and
    //     forwards the knob under its served (wire) key.
    await waitFor(() => {
      const req = geometryPosts.at(-1);
      expect(req?.momwire_model).toBe("fake-solver");
      expect(req?.solver).toBe("momwire");
      expect(req?.model_options).toEqual({ n_qp_const: 8 });
      expect(req?.n_per_wire).toBe(15);
      // supports_ground: false is honoured all the way to the wire.
      expect(req?.ground).toBe(false);
    });
  });

  // Negative control: the tab above is roster-driven, not a hardcoded entry
  // that happens to share the fixture's name.
  it("has no tab at all when the server doesn't serve it", async () => {
    servedRoster = [...SERVED_ROSTER];
    const user = userEvent.setup();
    render(<DesignSession id={1} active />);
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Solver slot A/ })).toBeTruthy(),
    );
    await user.click(screen.getByRole("button", { name: "Slot A options" }));
    expect(screen.queryByRole("tab", { name: "Fake Solver" })).toBeNull();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(
      expect.arrayContaining(SERVED_ROSTER.map((b) => b.label)),
    );
  });
});
