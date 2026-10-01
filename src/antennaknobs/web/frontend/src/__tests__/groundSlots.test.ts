// AK#1794 — the ground slots' pure state steps (lib/groundSlots.ts) and the
// served payload's parse (lib/settings.ts). The session-level behaviour is
// groundSlots.session.test.tsx.
import { describe, it, expect } from "vitest";
import {
  designGround,
  editActive,
  editSlot,
  GROUND_SLOT_IDS,
  groundSlotId,
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
    const ui = parseUiDefaults({
      ground: g,
      grounds: [
        { id: "X", ...g },
        { id: "Y", ...g, enabled: false },
        { id: "Z", ...g, method: "sommerfeld" },
        { id: "U", ...g, type: "pec", soil: { eps_r: 5, sigma: 0.001 } },
      ],
    });
    expect(ui.grounds.map((s) => s.id)).toEqual(["X", "Y", "Z", "U"]);
    expect(ui.grounds[3]).toMatchObject({ type: "pec", soil: { eps_r: 5, sigma: 0.001 } });
  });

  it("a server before AK#1794: its `ground` is slot X, the rest are stock", () => {
    const ui = parseUiDefaults({ ground: { ...g, method: "mininec" } });
    expect(ui.grounds[0]).toEqual({ id: "X", ...g, method: "mininec" });
    expect(ui.grounds.slice(1)).toEqual(BUILTIN_GROUND_SLOTS.slice(1));
  });

  it("no payload at all: the stock set", () => {
    expect(parseUiDefaults(undefined).grounds).toEqual(BUILTIN_GROUND_SLOTS);
  });

  it("a server before AK#1801 numbers its slots: they read as X, Y, Z, U (AK#1801)", () => {
    const ui = parseUiDefaults({
      ground: g,
      grounds: [
        { id: "1", ...g },
        { id: "2", ...g, enabled: false },
        { id: "3", ...g, method: "sommerfeld" },
        { id: "4", ...g, type: "pec" },
        { id: "nope", ...g },
      ],
    });
    expect(ui.grounds.map((s) => s.id)).toEqual(["X", "Y", "Z", "U"]);
    expect(ui.grounds[1].enabled).toBe(false);
  });
});

describe("ground slot names (AK#1801)", () => {
  it("chunks of three, each read forwards: X Y Z, U V W, R S T, ... down to F G H", () => {
    expect(GROUND_SLOT_IDS.join("")).toBe("XYZUVWRSTOPQLMNIJKFGH");
    // Never a solver slot's letter.
    for (const s of ["A", "B", "C", "D", "E"]) expect(GROUND_SLOT_IDS).not.toContain(s);
    expect(BUILTIN_GROUND_SLOTS.map((s) => s.id)).toEqual(["X", "Y", "Z"]);
  });

  it("a number is the letter at that place; anything else is no slot", () => {
    expect(["1", "2", "3", "4", "5", "6", "7", "21"].map(groundSlotId)).toEqual([
      "X", "Y", "Z", "U", "V", "W", "R", "H",
    ]);
    expect(groundSlotId("U")).toBe("U");
    for (const raw of ["0", "01", "22", "A", "x", ""]) expect(groundSlotId(raw)).toBeNull();
  });
});
