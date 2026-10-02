// AK#1854 (Dan AC6LA, QRZ 1003328 #183): a ground slot says what the ACTIVE
// solver makes of it, the pair being solved is named in one line, and a chart
// whose engines solve one ground slot as different ground models says so.
// AK#1856: a ground the solver refuses (NEC-5 on refl-coef) is marked refused
// in the served words, never relabelled as the model it used to be upgraded to.
import { describe, it, expect } from "vitest";
import {
  appliedGroundChange,
  groundRefusal,
  groundSlotLabel,
  mixedGroundNote,
  solvePairLabel,
  sommerfeldSlotFor,
  type GroundSlot,
} from "../lib/groundSlots";
import { defaultOptsFor } from "../lib/backends";
import { backendEntry, NEC5_REFL_COEF_REFUSAL, ROSTER_WITH_NEC5 } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const nec5 = ROSTER_WITH_NEC5.find((b) => b.name === "nec5")!;
const bspline = backendEntry({
  ground_applied: { fast: "refl-coef", sommerfeld: "sommerfeld", mininec: "mininec" },
  ground_refusals: {},
});
// A momwire solver without the refl-coef model runs it as the PEC image.
const noRefl = backendEntry({
  name: "pulse",
  label: "Harrington (pulse)",
  ground_applied: { fast: "pec-image", sommerfeld: "sommerfeld", mininec: "mininec" },
  ground_refusals: {},
});
// A server predating AK#1854 serves neither map.
const old = backendEntry();

const slot = (over: Partial<GroundSlot> = {}): GroundSlot => ({
  id: "X",
  enabled: true,
  type: "finite",
  method: "fast",
  soil: null,
  terrainPreset: "levee",
  terrainParams: {},
  fromDesign: false,
  ...over,
});

describe("a ground the active solver refuses (AK#1856)", () => {
  it("NEC-5 refuses refl-coef in the served sentence; momwire runs it", () => {
    expect(groundRefusal(slot(), nec5)).toBe(NEC5_REFL_COEF_REFUSAL);
    expect(groundRefusal(slot(), bspline)).toBeNull();
    expect(groundRefusal(slot({ method: "sommerfeld" }), nec5)).toBeNull();
    expect(groundRefusal(slot({ method: "mininec" }), nec5)).toBeNull();
  });

  it("free space, PEC and a server without the map refuse nothing", () => {
    expect(groundRefusal(slot({ enabled: false }), nec5)).toBeNull();
    expect(groundRefusal(slot({ type: "pec" }), nec5)).toBeNull();
    expect(groundRefusal(slot(), old)).toBeNull();
  });

  it("the tab carries the refusal mark, not an arrow", () => {
    expect(groundSlotLabel(slot(), [], nec5)).toBe("refl-coef ⊘");
    expect(groundSlotLabel(slot({ method: "sommerfeld" }), [], nec5)).toBe("Sommerfeld");
    expect(appliedGroundChange(slot(), nec5)).toBeNull();
  });

  it("the way out is the first Sommerfeld slot the solver serves", () => {
    const slots = [
      slot({ id: "X", enabled: false }),
      slot({ id: "Y", method: "sommerfeld", type: "pec" }),
      slot({ id: "Z" }),
      slot({ id: "U", method: "sommerfeld" }),
      slot({ id: "V", method: "sommerfeld" }),
    ];
    expect(sommerfeldSlotFor(slots, nec5)).toBe("U");
    expect(sommerfeldSlotFor(slots.slice(0, 3), nec5)).toBeNull();
  });
});

describe("what the active solver runs for a ground slot", () => {
  it("a momwire solver without the model runs refl-coef as the PEC image", () => {
    expect(appliedGroundChange(slot(), noRefl)).toBe("PEC image");
    expect(appliedGroundChange(slot(), bspline)).toBeNull();
    expect(appliedGroundChange(slot({ method: "sommerfeld" }), noRefl)).toBeNull();
  });

  it("free space, PEC and a server without the map change nothing", () => {
    expect(appliedGroundChange(slot({ enabled: false }), noRefl)).toBeNull();
    expect(appliedGroundChange(slot({ type: "pec" }), noRefl)).toBeNull();
    expect(appliedGroundChange(slot(), old)).toBeNull();
  });

  it("the tab label carries the change only when there is one", () => {
    expect(groundSlotLabel(slot(), [], noRefl)).toBe("refl-coef → PEC image");
    expect(groundSlotLabel(slot(), [], bspline)).toBe("refl-coef");
    expect(groundSlotLabel(slot(), [])).toBe("refl-coef");
  });
});

describe("the pair line", () => {
  it("names the solver slot and the ground slot, independently", () => {
    const opts = defaultOptsFor(nec5, SERVED_OPTION_SPECS);
    expect(solvePairLabel("A", nec5, opts, slot({ id: "Z", method: "sommerfeld" }), [])).toBe(
      "solving on A (NEC-5) × Z (Sommerfeld)",
    );
  });

  it("says a refused pair is refused, not solving", () => {
    const opts = defaultOptsFor(nec5, SERVED_OPTION_SPECS);
    expect(solvePairLabel("A", nec5, opts, slot({ id: "Z" }), [])).toBe(
      "refused: A (NEC-5) × Z (refl-coef ⊘)",
    );
  });
});

describe("a chart whose engines solve one ground differently", () => {
  const backends: Record<string, (typeof ROSTER_WITH_NEC5)[number]> = {
    A: bspline,
    B: noRefl,
    C: nec5,
  };
  const grounds: Record<string, GroundSlot> = {
    X: slot(),
    Z: slot({ id: "Z", method: "sommerfeld" }),
  };
  const note = (cells: { slot: string; ground: string }[]) =>
    mixedGroundNote(
      cells,
      (id) => backends[id],
      (id) => grounds[id],
    );

  it("an engine cross on a refl-coef slot with a PEC-image solver in it is named", () => {
    expect(
      note([
        { slot: "A", ground: "X" },
        { slot: "B", ground: "X" },
      ]),
    ).toBe(
      "Ground X is solved as refl-coef on B-spline but as PEC image on Harrington (pulse): " +
        "those curves differ in ground model, not only in engine.",
    );
  });

  it("a NEC-5 cell on refl-coef is refused, not a second ground model", () => {
    expect(
      note([
        { slot: "A", ground: "X" },
        { slot: "C", ground: "X" },
      ]),
    ).toBeNull();
  });

  it("the same cross on a Sommerfeld slot, or one engine, needs no note", () => {
    expect(
      note([
        { slot: "A", ground: "Z" },
        { slot: "B", ground: "Z" },
        { slot: "C", ground: "Z" },
      ]),
    ).toBeNull();
    expect(
      note([
        { slot: "B", ground: "X" },
        { slot: "B", ground: "Z" },
      ]),
    ).toBeNull();
  });
});
