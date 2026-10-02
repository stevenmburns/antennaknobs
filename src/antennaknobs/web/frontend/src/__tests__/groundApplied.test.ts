// AK#1854 (Dan AC6LA, QRZ 1003328 #183): a ground slot says what the ACTIVE
// solver runs for it, the pair being solved is named in one line, and a chart
// whose engines solve one ground slot as different ground models says so.
import { describe, it, expect } from "vitest";
import {
  appliedGroundChange,
  groundSlotLabel,
  mixedGroundNote,
  solvePairLabel,
  type GroundSlot,
} from "../lib/groundSlots";
import { defaultOptsFor } from "../lib/backends";
import { backendEntry, ROSTER_WITH_NEC5 } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const nec5 = ROSTER_WITH_NEC5.find((b) => b.name === "nec5")!;
const bspline = backendEntry({
  ground_applied: { fast: "refl-coef", sommerfeld: "sommerfeld", mininec: "mininec" },
});
// A server predating AK#1854 serves no map.
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

describe("what the active solver runs for a ground slot", () => {
  it("NEC-5 runs refl-coef as Sommerfeld; momwire runs it as asked", () => {
    expect(appliedGroundChange(slot(), nec5)).toBe("Sommerfeld");
    expect(appliedGroundChange(slot(), bspline)).toBeNull();
    expect(appliedGroundChange(slot({ method: "sommerfeld" }), nec5)).toBeNull();
  });

  it("free space, PEC and a server without the map change nothing", () => {
    expect(appliedGroundChange(slot({ enabled: false }), nec5)).toBeNull();
    expect(appliedGroundChange(slot({ type: "pec" }), nec5)).toBeNull();
    expect(appliedGroundChange(slot(), old)).toBeNull();
  });

  it("a momwire solver without the model would read as the PEC image", () => {
    const noRefl = backendEntry({
      ground_applied: { fast: "pec-image", sommerfeld: "sommerfeld", mininec: "mininec" },
    });
    expect(appliedGroundChange(slot(), noRefl)).toBe("PEC image");
  });

  it("the tab label carries the change only when there is one", () => {
    expect(groundSlotLabel(slot(), [], nec5)).toBe("refl-coef → Sommerfeld");
    expect(groundSlotLabel(slot(), [], bspline)).toBe("refl-coef");
    expect(groundSlotLabel(slot(), [])).toBe("refl-coef");
  });
});

describe("the pair line", () => {
  it("names the solver slot and the ground slot, independently", () => {
    const opts = defaultOptsFor(nec5, SERVED_OPTION_SPECS);
    expect(solvePairLabel("A", nec5, opts, slot({ id: "Z" }), [])).toBe(
      "solving on A (NEC-5) × Z (refl-coef → Sommerfeld)",
    );
  });
});

describe("a chart whose engines solve one ground differently", () => {
  const backends: Record<string, (typeof ROSTER_WITH_NEC5)[number]> = { A: bspline, B: nec5 };
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

  it("an engine cross on a refl-coef slot with NEC-5 in it is named", () => {
    expect(
      note([
        { slot: "A", ground: "X" },
        { slot: "B", ground: "X" },
      ]),
    ).toBe(
      "Ground X is solved as refl-coef on B-spline but as Sommerfeld on NEC-5: " +
        "those curves differ in ground model, not only in engine.",
    );
  });

  it("the same cross on a Sommerfeld slot, or one engine, needs no note", () => {
    expect(
      note([
        { slot: "A", ground: "Z" },
        { slot: "B", ground: "Z" },
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
