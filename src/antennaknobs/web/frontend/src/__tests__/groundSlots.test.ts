// AK#1794 — the ground slots' pure state steps (lib/groundSlots.ts) and the
// served payload's parse (lib/settings.ts). The session-level behaviour is
// groundSlots.session.test.tsx.
import { describe, it, expect } from "vitest";
import {
  designGround,
  editActive,
  editSlot,
  GROUND_SLOT_IDS,
  groundSlotLabel,
  withDesignGround,
  type GroundSlot,
  type GroundSlotsState,
} from "../lib/groundSlots";
import { parseUiDefaults } from "../lib/settings";
import { overServed } from "./designSessionHarness";

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

const state = (active = "X"): GroundSlotsState => ({
  slots: [slot("X"), slot("Y", { enabled: false }), slot("Z", { method: "sommerfeld" })],
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
  const sessionDefault = slot("X");

  it("puts a design's own ground in slot X over what it held, and activates it", () => {
    const next = withDesignGround(state("Z"), { enabled: false }, sessionDefault);
    expect(next.active).toBe("X");
    expect(next.slots[0]).toEqual(slot("X", { enabled: false, fromDesign: true }));
    expect(next.slots.slice(1)).toEqual(state().slots.slice(1));
  });

  it("a design without one leaves everything alone, active slot included", () => {
    const s = editActive(state("X"), { method: "sommerfeld" });
    const next = withDesignGround({ ...s, active: "Y" }, null, sessionDefault);
    expect(next).toEqual({ ...s, active: "Y" });
  });

  it("…but puts the session default back over a previous design's untouched ground", () => {
    const seeded = withDesignGround(state("X"), { type: "pec" }, sessionDefault);
    const next = withDesignGround({ ...seeded, active: "Z" }, null, sessionDefault);
    expect(next.slots[0]).toEqual(sessionDefault);
    expect(next.active).toBe("Z");
  });

  it("a hand edit after the seed makes the ground the user's", () => {
    const seeded = withDesignGround(state("X"), { type: "pec" }, sessionDefault);
    const edited = editActive(seeded, { method: "sommerfeld" });
    expect(edited.slots[0].fromDesign).toBe(false);
    expect(withDesignGround(edited, null, sessionDefault)).toBe(edited);
  });
});

describe("editActive", () => {
  it("edits the active slot only", () => {
    const next = editActive(state("Y"), { enabled: true });
    expect(next.slots.map((s) => s.enabled)).toEqual([true, true, true]);
    expect(next.slots[2]).toEqual(state().slots[2]);
  });
  it("takes an updater for the terrain knobs", () => {
    const next = editActive(state("Z"), (s) => ({
      terrainParams: { ...s.terrainParams, height_m: 4 },
    }));
    expect(next.slots[2].terrainParams).toEqual({ height_m: 4 });
  });
});

describe("editSlot (AK#1801)", () => {
  it("edits the named slot, not the active one, and keeps the active id", () => {
    const next = editSlot(state("X"), "Y", { enabled: true, type: "pec" });
    expect(next.active).toBe("X");
    expect(next.slots[1]).toMatchObject({ enabled: true, type: "pec", fromDesign: false });
    expect(next.slots[0]).toEqual(state("X").slots[0]);
    expect(next.slots[2]).toEqual(state("X").slots[2]);
  });
});

describe("groundSlotLabel", () => {
  const presets = [
    { name: "average", label: "average", eps_r: 13, sigma: 0.005, tooltip: "" },
  ];
  it.each([
    [slot("X", { enabled: false }), "free space"],
    [slot("X", { type: "pec" }), "PEC"],
    [slot("X", { type: "terrain", terrainPreset: "cliff" }), "terrain · cliff"],
    [slot("X"), "refl-coef · average"],
    [slot("X", { method: "sommerfeld", soil: { eps_r: 20, sigma: 0.03 } }), "Sommerfeld · εr 20, σ 0.03 S/m"],
    [slot("X", { method: "mininec", soil: null }), "MININEC"],
  ])("%j → %s", (s, label) => {
    expect(groundSlotLabel(s, presets)).toBe(label);
  });
});

describe("parseUiDefaults: ground slots", () => {
  const g = { enabled: true, type: "finite", method: "fast", soil: null, terrain_preset: null };

  it("takes the served slots, as many as there are", () => {
    const ui = parseUiDefaults(
      overServed({
        grounds: [
          { id: "X", ...g },
          { id: "Y", ...g, enabled: false },
          { id: "Z", ...g, method: "sommerfeld" },
          { id: "U", ...g, type: "pec", soil: { eps_r: 5, sigma: 0.001 } },
        ],
      }),
    );
    expect(ui?.grounds.map((s) => s.id)).toEqual(["X", "Y", "Z", "U"]);
    expect(ui?.grounds[3]).toMatchObject({ type: "pec", soil: { eps_r: 5, sigma: 0.001 } });
  });

  it("the served stock set is X, Y, Z", () => {
    expect(parseUiDefaults(overServed())?.grounds.map((s) => s.id)).toEqual(["X", "Y", "Z"]);
  });

  // Strict (AK#1858): the page has no stock set of its own to fall back to,
  // and the shipped server serves letters only (it reads a numbered table
  // as its letter itself, tests/test_ground_slots_xyz_1801.py).
  it.each([
    ["no grounds", { grounds: undefined }],
    ["an empty list", { grounds: [] }],
    ["a numbered slot", { grounds: [{ id: "1", ...g }] }],
    ["a slot that is not a ground slot", { grounds: [{ id: "A", ...g }] }],
    ["an unknown method", { grounds: [{ id: "X", ...g, method: "exact" }] }],
    ["a slot missing its enabled flag", { grounds: [{ id: "X", type: "finite", method: "fast", soil: null, terrain_preset: null }] }],
    ["a half soil", { grounds: [{ id: "X", ...g, soil: { eps_r: 13 } }] }],
    ["one slot twice", { grounds: [{ id: "X", ...g }, { id: "X", ...g }] }],
  ])("refuses %s", (_what, over) => {
    expect(parseUiDefaults(overServed(over))).toBeNull();
  });
});

describe("ground slot names (AK#1801)", () => {
  it("chunks of three, each read forwards: X Y Z, U V W, R S T, ... down to F G H", () => {
    expect(GROUND_SLOT_IDS.join("")).toBe("XYZUVWRSTOPQLMNIJKFGH");
    // Never a solver slot's letter.
    for (const s of ["A", "B", "C", "D", "E"]) expect(GROUND_SLOT_IDS).not.toContain(s);
  });
});
