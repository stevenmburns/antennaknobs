/**
 * Startup settings through a real <DesignSession> (AK#1492).
 *
 * AC6LA asked to start the workbench with the frequency sweep off. The
 * switches, the ground and the solver slots now start where the server's
 * settings.toml says, and the Settings menu can save the session's own
 * choices back to it.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { groundSettings, mountDesignSession, mountReady, untilDom } from "./designSessionHarness";
import { SERVED_SLOT_SEEDS } from "./backendFixtures";
import { SERVED_UI_DEFAULTS } from "./uiDefaultsFixtures";

const DEFAULTS = {
  path: "/home/ham/.antennaknobs/settings.toml",
  exists: true,
  writable: true,
  switches: {
    live: true,
    freq_sweep: false,
    convergence_sweep: false,
    pattern_renorm: true,
    refine: false,
    heatmap_currents: false,
    current_waveforms: true,
    wire_labels: true,
    feed_labels: false,
  },
  switches_set: ["freq_sweep", "refine", "heatmap_currents", "current_waveforms", "wire_labels", "feed_labels"],
  antenna_view: { orientation: "iso" },
  // Slot X as the file sets it; Y and Z as served.
  grounds: [
    {
      id: "X",
      enabled: false,
      type: "finite",
      method: "sommerfeld",
      soil: { eps_r: 20, sigma: 0.03 },
      terrain_preset: null,
    },
    ...SERVED_UI_DEFAULTS.grounds.slice(1),
  ],
  problems: ["[switches] freq_swep: not a switch (known: live, freq_sweep)"],
};

function checkedStates(name: string) {
  return screen
    .getAllByRole("checkbox", { name })
    .map((c) => (c as HTMLInputElement).checked);
}

// The Antenna view's projection switch: the label(s) drawn active.
function activeProjections() {
  return ["Top (xy)", "Front (xz)", "Side (yz)", "Iso"].filter((label) =>
    screen
      .queryAllByRole("button", { name: label })
      .some((b) => b.classList.contains("active")),
  );
}

async function openTools(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Tools menu" }));
}

describe("startup settings (AK#1492)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("starts every switch and the ground where settings.toml says", async () => {
    const user = userEvent.setup();
    await mountReady({ uiDefaults: DEFAULTS });
    await openTools(user);
    expect(checkedStates("wire labels").every((c) => c)).toBe(true);
    expect(checkedStates("heatmapped currents").every((c) => !c)).toBe(true);
    expect(checkedStates("current waveforms").every((c) => c)).toBe(true);
    expect(checkedStates("feed labels").every((c) => !c)).toBe(true);
    // A file that names `refine` wins over the browser's memory.
    expect(checkedStates("adaptive resolution")).toEqual([false]);
    // The ground plane lives behind the active ground slot's ⚙ (AK#1801).
    groundSettings();
    expect(checkedStates("ground plane").every((c) => !c)).toBe(true);
    // The freq-sweep and param-sweep switches are gone from the menu (AK#1757
    // step 5 unit 3): their keys seed each analysis chart's dwell switch
    // instead (settingsSweepKeys.session.test.tsx).
    expect(screen.queryAllByRole("checkbox", { name: "freq sweep" })).toEqual([]);
    expect(screen.queryAllByRole("checkbox", { name: "param sweep" })).toEqual([]);
    expect(screen.queryAllByRole("checkbox", { name: /converge/i })).toEqual([]);
  });

  it("shows the file's problems once, and they dismiss", async () => {
    const user = userEvent.setup();
    await mountReady({ uiDefaults: DEFAULTS });
    const notice = screen.getByRole("alert");
    expect(notice.textContent).toContain("freq_swep: not a switch");
    await user.click(screen.getByRole("button", { name: "Dismiss the settings notice" }));
    expect(screen.queryByText(/freq_swep/)).toBeNull();
  });

  it("saves the session's switches, ground and slots as the defaults", async () => {
    const user = userEvent.setup();
    let posted: Record<string, unknown> | null = null;
    await mountReady({
      uiDefaults: DEFAULTS,
      routes: {
        "/settings": (_url, init) => {
          posted = JSON.parse(String(init?.body));
          return {
            ok: true,
            status: 200,
            json: async () => ({ ...DEFAULTS, problems: [] }),
          } as unknown as Response;
        },
      },
    });
    await openTools(user);
    await user.click(screen.getByRole("button", { name: "save as my defaults" }));
    // The save's own answer: the status line renders once the POST has
    // come back, so the body it sent is in hand.
    const status = await untilDom(() => screen.queryByRole("status"));
    expect(posted).not.toBeNull();
    const body = posted as unknown as {
      switches: Record<string, boolean>;
      antenna_view: { orientation: string };
      ground?: Record<string, unknown>;
      grounds: Record<string, Record<string, unknown>>;
      slots: Record<string, { backend: string; n_per_wire: number }>;
    };
    expect(body.switches).toEqual(DEFAULTS.switches);
    expect(body.antenna_view).toEqual({ orientation: "iso" });
    // The file's [ground] is ground slot X (AK#1794), and the page posts
    // every slot under `grounds`, never the older `ground` beside it.
    expect(body.ground).toBeUndefined();
    expect(Object.keys(body.grounds)).toEqual(["X", "Y", "Z"]);
    expect(body.grounds["X"]).toMatchObject({
      enabled: false,
      type: "finite",
      method: "sommerfeld",
      eps_r: 20,
      sigma: 0.03,
    });
    expect(Object.keys(body.slots).sort()).toEqual(["A", "B", "C"]);
    expect(body.slots.A!.backend).toBe(SERVED_SLOT_SEEDS.find((s) => s.slot === "A")!.backend);
    expect(status.textContent).toContain(
      "Saved as your defaults: /home/ham/.antennaknobs/settings.toml",
    );
  });

  it("starts the Antenna view at the file's orientation, over the design's guess (AK#1737)", async () => {
    const user = userEvent.setup();
    // HARNESS_EXAMPLE guesses "xz" (Front); the file says Iso.
    await mountReady({ uiDefaults: DEFAULTS });
    expect(activeProjections()).toEqual(["Iso"]);
    await openTools(user);
    const select = screen.getByRole("combobox", {
      name: "antenna view on load",
    }) as HTMLSelectElement;
    expect(select.value).toBe("iso");
    // A change in the menu applies at once, and is what a save would write.
    await user.selectOptions(select, "side");
    expect(activeProjections()).toEqual(["Side (yz)"]);
  });

  it("keeps the design's own guess when the file says nothing (auto)", async () => {
    await mountReady();
    expect(activeProjections()).toEqual(["Front (xz)"]);
  });

  it("saves auto as auto, which the server then leaves out of the file", async () => {
    const user = userEvent.setup();
    let posted: { antenna_view?: unknown } | null = null;
    // A file with no [antenna_view] table: the served payload's default.
    const withoutView = { ...DEFAULTS, antenna_view: { orientation: "auto" } };
    await mountReady({
      uiDefaults: withoutView,
      routes: {
        "/settings": (_url, init) => {
          posted = JSON.parse(String(init?.body));
          return {
            ok: true,
            status: 200,
            json: async () => ({ ...withoutView, problems: [] }),
          } as unknown as Response;
        },
      },
    });
    await openTools(user);
    await user.click(screen.getByRole("button", { name: "save as my defaults" }));
    await untilDom(() => screen.queryByRole("status"));
    expect(posted).not.toBeNull();
    expect(posted!.antenna_view).toEqual({ orientation: "auto" });
  });

  it("offers no save on an instance that cannot write the file", async () => {
    const user = userEvent.setup();
    await mountReady({ uiDefaults: { ...DEFAULTS, writable: false, problems: [] } });
    await openTools(user);
    expect(screen.queryByRole("button", { name: "save as my defaults" })).toBeNull();
  });

  it("refuses a server without ui_defaults, with a sentence and no workbench (AK#1858)", async () => {
    mountDesignSession({ uiDefaults: null });
    const alert = await untilDom(() => screen.queryByRole("alert"));
    expect(alert.textContent).toContain("the server sent no startup settings (ui_defaults)");
    expect(screen.queryByRole("button", { name: "Tools menu" })).toBeNull();
    expect(screen.queryByRole("tab", { name: /Solver slot A/ })).toBeNull();
  });

  it("refuses a payload without a stock slot's starting solver (AK#1858)", async () => {
    mountDesignSession({ slotSeeds: SERVED_SLOT_SEEDS.filter((s) => s.slot !== "C") });
    const alert = await untilDom(() => screen.queryByRole("alert"));
    expect(alert.textContent).toContain("the server sent no starting solver for slot C");
    expect(screen.queryByRole("button", { name: "Tools menu" })).toBeNull();
  });

  it("starts at the served defaults on a server with no settings file", async () => {
    const user = userEvent.setup();
    await mountReady();
    await openTools(user);
    expect(checkedStates("wire labels").every((c) => c === SERVED_UI_DEFAULTS.switches.wire_labels)).toBe(true);
    expect(screen.queryByRole("button", { name: "save as my defaults" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
