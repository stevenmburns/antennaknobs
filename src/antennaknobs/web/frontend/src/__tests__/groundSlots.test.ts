// AK#1794 — the ground slots' pure state steps (lib/groundSlots.ts) and the
// served payload's parse (lib/settings.ts). The session-level behaviour is
// groundSlots.session.test.tsx.
import { describe, it, expect } from "vitest";
import {
  designGround,
  editActive,
  groundSlotLabel,
  withDesignGround,
  type GroundSlot,
  type GroundSlotsState,
} from "../lib/groundSlots";
import { BUILTIN_GROUND_SLOTS, parseUiDefaults } from "../lib/settings";

const slot = (id: string, over: Partial<GroundSlot> = {}): GroundSlot => ({
  id,
  enabled: true,
  type: "finite",
  method: "fast",
  soil: { eps_r: 13, sigma: 0.005 },
  terrainPreset: "levee",
  terrainParams: {},
  fromDesign: false,
  ...over,
});

const state = (active = "1"): GroundSlotsState => ({
  slots: [slot("1"), slot("2", { enabled: false }), slot("3", { method: "sommerfeld" })],
  active,
});

describe("designGround: what a design brings, in the order the session applied it", () => {
  it("nothing for a design with neither a seed nor a requirement", () => {
    expect(designGround({})).toBeNull();
  });
  it("the buried requirement: finite Sommerfeld", () => {
    expect(designGround({ ground_requirement: "sommerfeld" })).toEqual({
      enabled: true,
      type: "finite",
      method: "sommerfeld",
    });
  });
  it("GE 0 turns the ground off and touches nothing else", () => {
    expect(designGround({ ground_seed: "free" })).toEqual({ enabled: false });
  });
  it("GE 1 / GN 1: PEC", () => {
    expect(designGround({ ground_seed: "pec" })).toEqual({ enabled: true, type: "pec" });
  });
  it("GN 0 with its medium", () => {
    expect(
      designGround({ ground_seed: "fast", ground_medium: { eps_r: 5, sigma: 0.001 } }),
    ).toEqual({
      enabled: true,
      type: "finite",
      method: "fast",
      soil: { eps_r: 5, sigma: 0.001 },
    });
  });
  it("a bare GD: MININEC", () => {
    expect(designGround({ ground_seed: "mininec" })?.method).toBe("mininec");
  });
  it("a seed on a buried design wins where they disagree", () => {
    expect(designGround({ ground_requirement: "sommerfeld", ground_seed: "free" })).toEqual({
      enabled: false,
      type: "finite",
      method: "sommerfeld",
    });
  });
});

describe("withDesignGround", () => {
  const sessionDefault = slot("1");

  it("puts a design's own ground in slot 1 over what it held, and activates it", () => {
    const next = withDesignGround(state("3"), { enabled: false }, sessionDefault);
    expect(next.active).toBe("1");
    expect(next.slots[0]).toEqual(slot("1", { enabled: false, fromDesign: true }));
    expect(next.slots.slice(1)).toEqual(state().slots.slice(1));
  });

  it("a design without one leaves everything alone, active slot included", () => {
    const s = editActive(state("1"), { method: "sommerfeld" });
    const next = withDesignGround({ ...s, active: "2" }, null, sessionDefault);
    expect(next).toEqual({ ...s, active: "2" });
  });

  it("…but puts the session default back over a previous design's untouched ground", () => {
    const seeded = withDesignGround(state("1"), { type: "pec" }, sessionDefault);
    const next = withDesignGround({ ...seeded, active: "3" }, null, sessionDefault);
    expect(next.slots[0]).toEqual(sessionDefault);
    expect(next.active).toBe("3");
  });

  it("a hand edit after the seed makes the ground the user's", () => {
    const seeded = withDesignGround(state("1"), { type: "pec" }, sessionDefault);
    const edited = editActive(seeded, { method: "sommerfeld" });
    expect(edited.slots[0].fromDesign).toBe(false);
    expect(withDesignGround(edited, null, sessionDefault)).toBe(edited);
  });
});

describe("editActive", () => {
  it("edits the active slot only", () => {
    const next = editActive(state("2"), { enabled: true });
    expect(next.slots.map((s) => s.enabled)).toEqual([true, true, true]);
    expect(next.slots[2]).toEqual(state().slots[2]);
  });
  it("takes an updater for the terrain knobs", () => {
    const next = editActive(state("3"), (s) => ({
      terrainParams: { ...s.terrainParams, height_m: 4 },
    }));
    expect(next.slots[2].terrainParams).toEqual({ height_m: 4 });
  });
});

describe("groundSlotLabel", () => {
  const presets = [
    { name: "average", label: "average", eps_r: 13, sigma: 0.005, tooltip: "" },
  ];
  it.each([
    [slot("1", { enabled: false }), "free space"],
    [slot("1", { type: "pec" }), "PEC"],
    [slot("1", { type: "terrain", terrainPreset: "cliff" }), "terrain · cliff"],
    [slot("1"), "refl-coef · average"],
    [slot("1", { method: "sommerfeld", soil: { eps_r: 20, sigma: 0.03 } }), "Sommerfeld · εr 20, σ 0.03 S/m"],
    [slot("1", { method: "mininec", soil: null }), "MININEC"],
  ])("%j → %s", (s, label) => {
    expect(groundSlotLabel(s, presets)).toBe(label);
  });
});

describe("parseUiDefaults: ground slots", () => {
  const g = { enabled: true, type: "finite", method: "fast", soil: null, terrain_preset: null };

  it("takes the served slots, as many as there are", () => {
    const ui = parseUiDefaults({
      ground: g,
      grounds: [
        { id: "1", ...g },
        { id: "2", ...g, enabled: false },
        { id: "3", ...g, method: "sommerfeld" },
        { id: "4", ...g, type: "pec", soil: { eps_r: 5, sigma: 0.001 } },
      ],
    });
    expect(ui.grounds.map((s) => s.id)).toEqual(["1", "2", "3", "4"]);
    expect(ui.grounds[3]).toMatchObject({ type: "pec", soil: { eps_r: 5, sigma: 0.001 } });
  });

  it("a server before AK#1794: its `ground` is slot 1, the rest are stock", () => {
    const ui = parseUiDefaults({ ground: { ...g, method: "mininec" } });
    expect(ui.grounds[0]).toEqual({ id: "1", ...g, method: "mininec" });
    expect(ui.grounds.slice(1)).toEqual(BUILTIN_GROUND_SLOTS.slice(1));
  });

  it("no payload at all: the stock set", () => {
    expect(parseUiDefaults(undefined).grounds).toEqual(BUILTIN_GROUND_SLOTS);
  });
});
