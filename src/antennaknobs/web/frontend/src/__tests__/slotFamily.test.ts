// AK#1801: the variable-count rules both slot families share, and the ground
// slots' pure add/remove steps. The session-level behaviour (the + on each
// strip, remove in a slot's settings, the save) is
// slotAddRemove.session.test.tsx.
import { describe, it, expect } from "vitest";
import { nextSlotId, slotBefore, slotRemovalRefusal } from "../lib/slotFamily";
import { defaultSlots, slotOrder, SOLVER_SLOTS } from "../lib/backends";
import {
  addGroundSlot,
  GROUND_SLOTS,
  removeGroundSlot,
  type GroundSlot,
  type GroundSlotsState,
} from "../lib/groundSlots";
import { SERVED_ROSTER, SERVED_SLOT_SEEDS } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

describe("slot families", () => {
  it("the solver family is A–E with A, B, C stock; the ground family is X, Y, Z, U, ...", () => {
    expect(SOLVER_SLOTS.ids).toEqual(["A", "B", "C", "D", "E"]);
    expect(SOLVER_SLOTS.ids.slice(0, SOLVER_SLOTS.stock)).toEqual(["A", "B", "C"]);
    expect(GROUND_SLOTS.ids.slice(0, 6)).toEqual(["X", "Y", "Z", "U", "V", "W"]);
    expect(GROUND_SLOTS.stock).toBe(3);
    // The two never share a letter.
    expect(SOLVER_SLOTS.ids.filter((id) => GROUND_SLOTS.ids.includes(id))).toEqual([]);
  });

  it("nextSlotId: the first id the session lacks, or null when full", () => {
    expect(nextSlotId(SOLVER_SLOTS, ["A", "B", "C"])).toBe("D");
    expect(nextSlotId(SOLVER_SLOTS, ["A", "B", "C", "D"])).toBe("E");
    expect(nextSlotId(SOLVER_SLOTS, SOLVER_SLOTS.ids)).toBeNull();
    expect(nextSlotId(GROUND_SLOTS, ["X", "Y", "Z"])).toBe("U");
  });

  it("slotRemovalRefusal: stock slots stay, and only the last slot goes", () => {
    const have = ["A", "B", "C", "D", "E"];
    expect(slotRemovalRefusal(SOLVER_SLOTS, have, "B")).toBe(
      "A, B, C are the stock solver slots, which stay",
    );
    expect(slotRemovalRefusal(SOLVER_SLOTS, have, "D")).toBe(
      "remove slot E first: solver slots run without gaps",
    );
    expect(slotRemovalRefusal(SOLVER_SLOTS, have, "E")).toBeNull();
    expect(slotRemovalRefusal(SOLVER_SLOTS, ["A", "B", "C"], "D")).toBe(
      "there is no solver slot D",
    );
  });

  it("slotBefore: the slot that becomes active when one goes", () => {
    expect(slotBefore(SOLVER_SLOTS, "D")).toBe("C");
    expect(slotBefore(GROUND_SLOTS, "U")).toBe("Z");
  });
});

describe("solver slot seeds (AK#1801)", () => {
  it("A, B, C always; a served seed past C adds its slot", () => {
    expect(slotOrder(defaultSlots(SERVED_ROSTER, SERVED_OPTION_SPECS, SERVED_SLOT_SEEDS))).toEqual([
      "A",
      "B",
      "C",
    ]);
    const slots = defaultSlots(SERVED_ROSTER, SERVED_OPTION_SPECS, [
      ...SERVED_SLOT_SEEDS,
      { slot: "D", backend: "bspline", n_per_wire: 31, model: {} },
    ]);
    expect(slotOrder(slots)).toEqual(["A", "B", "C", "D"]);
    expect(slots.D!.opts.nPerWire).toBe(31);
  });
});

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
  slots: [
    slot("X", { fromDesign: true }),
    slot("Y", { enabled: false }),
    slot("Z", { method: "sommerfeld" }),
  ],
  active,
});

describe("addGroundSlot / removeGroundSlot (AK#1801)", () => {
  it("+ copies the ACTIVE slot under the next letter and makes it active", () => {
    const next = addGroundSlot(state("Z"));
    expect(next.slots.map((s) => s.id)).toEqual(["X", "Y", "Z", "U"]);
    expect(next.active).toBe("U");
    expect(next.slots[3]).toEqual({ ...state().slots[2], id: "U" });
  });

  it("a copy of a design's ground is the user's own, and shares no objects", () => {
    const st = state("X");
    st.slots[0].terrainParams = { h: 1 };
    const next = addGroundSlot(st);
    expect(next.slots[3].fromDesign).toBe(false);
    expect(next.slots[3].soil).toEqual(st.slots[0].soil);
    expect(next.slots[3].soil).not.toBe(st.slots[0].soil);
    expect(next.slots[3].terrainParams).not.toBe(st.slots[0].terrainParams);
  });

  it("a full family adds nothing", () => {
    const full: GroundSlotsState = {
      slots: GROUND_SLOTS.ids.map((id) => slot(id)),
      active: "X",
    };
    expect(addGroundSlot(full)).toBe(full);
  });

  it("removes only the last added slot; the slot before becomes active if it was", () => {
    const two = addGroundSlot(addGroundSlot(state("X")));
    expect(two.active).toBe("V");
    expect(removeGroundSlot(two, "U")).toBe(two);
    expect(removeGroundSlot(two, "Z")).toBe(two);
    const one = removeGroundSlot(two, "V");
    expect(one.slots.map((s) => s.id)).toEqual(["X", "Y", "Z", "U"]);
    expect(one.active).toBe("U");
    const kept = removeGroundSlot({ ...one, active: "Y" }, "U");
    expect(kept.active).toBe("Y");
  });
});

describe("a stock slot without a served seed (AK#1858)", () => {
  it("is refused by name, never seeded from the roster's head", () => {
    const seeds = SERVED_SLOT_SEEDS.filter((s) => s.slot !== "B");
    expect(() => defaultSlots(SERVED_ROSTER, SERVED_OPTION_SPECS, seeds)).toThrow(
      /solver slot B has no served seed/,
    );
  });
});
