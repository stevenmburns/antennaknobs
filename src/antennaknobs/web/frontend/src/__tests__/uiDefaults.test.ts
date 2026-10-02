// AK#1858: the startup settings are the server's alone. parseUiDefaults takes
// the served `ui_defaults` as it is and refuses one it cannot start from,
// with no default of its own to fill a gap with; readUiDefaults says which
// field was missing, the sentence the session's error state shows. The
// served payload is uiDefaultsFixtures.ts, generated off the server.
import { describe, it, expect } from "vitest";
import { parseUiDefaults, readUiDefaults, SWITCH_KEYS } from "../lib/settings";
import { overServed } from "./designSessionHarness";
import { SERVED_UI_DEFAULTS } from "./uiDefaultsFixtures";

describe("parseUiDefaults takes the served payload", () => {
  it("reads every field of what a server with no settings file serves", () => {
    const ui = parseUiDefaults(SERVED_UI_DEFAULTS);
    expect(ui).not.toBeNull();
    expect(ui!.switches).toEqual(SERVED_UI_DEFAULTS.switches);
    expect(ui!.orientation).toBe(SERVED_UI_DEFAULTS.antenna_view.orientation);
    expect(ui!.runOnPick).toEqual(SERVED_UI_DEFAULTS.workbench.run_on_pick);
    expect(ui!.grounds).toEqual(SERVED_UI_DEFAULTS.grounds);
    expect(ui!.path).toBe(SERVED_UI_DEFAULTS.path);
    expect(ui!.writable).toBe(SERVED_UI_DEFAULTS.writable);
    expect(ui!.problems).toEqual([]);
  });

  it("names every switch the server serves", () => {
    expect([...SWITCH_KEYS]).toEqual(SERVED_UI_DEFAULTS.switch_labels.map((s) => s.key));
  });
});

describe("parseUiDefaults refuses what it cannot start from", () => {
  it("no payload at all", () => {
    expect(parseUiDefaults(undefined)).toBeNull();
    expect(parseUiDefaults(null)).toBeNull();
    expect(readUiDefaults(undefined).refusal).toBe(
      "the server sent no startup settings (ui_defaults)",
    );
  });

  it("a payload missing a switch, naming it", () => {
    const served = overServed();
    const switches = Object.fromEntries(
      Object.entries(served.switches as Record<string, boolean>).filter(([k]) => k !== "refine"),
    );
    const read = readUiDefaults({ ...served, switches });
    expect(read.defaults).toBeNull();
    expect(read.refusal).toBe('the server\'s startup settings give no value for the switch "refine"');
  });

  it("a switch that is not a boolean", () => {
    expect(parseUiDefaults(overServed({ switches: { live: "yes" } }))).toBeNull();
  });

  it("an empty ground-slot list", () => {
    const read = readUiDefaults(overServed({ grounds: [] }));
    expect(read.defaults).toBeNull();
    expect(read.refusal).toBe("the server's startup settings carry no ground slots");
  });

  it("an orientation the page does not know", () => {
    expect(parseUiDefaults(overServed({ antenna_view: { orientation: "isometric" } }))).toBeNull();
  });

  it.each(["path", "exists", "writable", "problems", "switches_set"])("a payload without %s", (key) => {
    const payload = { ...overServed() };
    delete payload[key];
    expect(parseUiDefaults(payload)).toBeNull();
  });
});
