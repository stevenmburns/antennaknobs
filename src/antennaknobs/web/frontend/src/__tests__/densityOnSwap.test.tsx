// A solver swap adopts the engine's default segments-per-wire (#1543).
//
// The defect this closes: `setSlotBackend` PRESERVED the slot's N across an
// engine swap, so the roster's per-engine default was reachable only by a seed
// that named no density (slot C) and by Reset. Razor-2p in slot A therefore ran
// at 15 — below the lowest rung of #1525's ladder — while the razor tab was
// documented at 40.
//
// The rule is "it does what the roster says, every time": always adopt, with no
// memory of a hand-set value, and say so beside the knob. What must NOT move is
// startup — the stock seeds and a saved settings file are decisions, and this
// issue is about the swap.
//
// Driven through the hook rather than the whole session because these are
// claims about the slot MODEL; the note's rendering is asserted end-to-end in
// newBackend.test.tsx.
import { describe, it, expect } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useSolverSlots } from "../components/session/useSolverSlots";
import {
  ROSTER_WITH_NEC5,
  SERVED_SLOT_SEEDS,
  entry,
} from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const ROSTER = ROSTER_WITH_NEC5;
const back = (name: string) => entry(name, ROSTER);

function slots() {
  return renderHook(() =>
    useSolverSlots({
      roster: ROSTER,
      specs: SERVED_OPTION_SPECS,
      seeds: SERVED_SLOT_SEEDS,
    }),
  );
}

describe("startup is unchanged (#1543 changes the swap, not the seeds)", () => {
  it("seeds A/B/C at the served values", () => {
    const { result } = slots();
    expect(result.current.slots.A.opts.nPerWire).toBe(15);
    expect(result.current.slots.B.opts.nPerWire).toBe(20);
    // Slot C names no density, so it takes its backend's own — the one path
    // by which the roster default was already reachable.
    expect(result.current.slots.C.opts.nPerWire).toBe(21);
    expect(result.current.densityNotes).toEqual({ A: null, B: null, C: null });
  });

  it("a saved seed's n_per_wire wins over the engine default", () => {
    // What a settings file produces (#1492): the same seed shape, carrying a
    // density the user saved. A saved value is a decision and adoption is for
    // the swap, so it must survive seeding even though the engine has an
    // opinion — and even though the seed's degree has one too.
    const { result } = renderHook(() =>
      useSolverSlots({
        roster: ROSTER,
        specs: SERVED_OPTION_SPECS,
        seeds: [
          { slot: "A", backend: "bspline", n_per_wire: 33, model: { degree: 1 } },
          { slot: "B", backend: "razor-2p", n_per_wire: 7, model: {} },
          { slot: "C", backend: "pynec", n_per_wire: null, model: {} },
        ],
      }),
    );
    expect(result.current.slots.A.opts.nPerWire).toBe(33);
    expect(result.current.slots.B.opts.nPerWire).toBe(7);
    expect(result.current.slots.C.opts.nPerWire).toBe(21);
  });

  it("a seed that names a degree and no density takes THAT degree's default", () => {
    // Degree 1 is 20, not degree 2's 15: the degree is the basis, so a seed
    // that fixes the basis has fixed the density with it.
    const { result } = renderHook(() =>
      useSolverSlots({
        roster: ROSTER,
        specs: SERVED_OPTION_SPECS,
        seeds: [{ slot: "A", backend: "bspline", n_per_wire: null, model: { degree: 1 } }],
      }),
    );
    expect(result.current.slots.A.opts.nPerWire).toBe(20);
  });
});

describe("an engine swap adopts that engine's density", () => {
  it.each([
    ["razor-2p", 40, "segments set to Razor (2-point)'s default, 40"],
    ["nec5", 40, "segments set to NEC-5's default, 40"],
    // The stock bspline tab is degree 2, so a swap to it lands on 15.
    ["bspline", 15, "segments set to B-spline d=2's default, 15"],
    ["pynec", 21, "segments set to PyNEC's default, 21"],
  ])("to %s: N=%i, with the note", (name, n, note) => {
    const { result } = slots();
    act(() => result.current.setSlotBackend("A", back(name)));
    expect(result.current.slots.A.opts.nPerWire).toBe(n);
    expect(result.current.densityNotes.A).toBe(note);
  });

  it("adopts even over a hand-set value — no memory (#1543)", () => {
    const { result } = slots();
    act(() => result.current.updateSlotOpts("A", { nPerWire: 77 }));
    expect(result.current.slots.A.opts.nPerWire).toBe(77);
    act(() => result.current.setSlotBackend("A", back("razor-2p")));
    expect(result.current.slots.A.opts.nPerWire).toBe(40);
  });

  it("keeps wire radius, which is geometry and means the same on every solver", () => {
    const { result } = slots();
    act(() => result.current.updateSlotOpts("A", { wireRadius: 0.003 }));
    act(() => result.current.setSlotBackend("A", back("razor-2p")));
    expect(result.current.slots.A.opts.wireRadius).toBe(0.003);
  });

  it("touches only the slot that swapped", () => {
    const { result } = slots();
    act(() => result.current.setSlotBackend("A", back("razor-2p")));
    expect(result.current.slots.B.opts.nPerWire).toBe(20);
    expect(result.current.densityNotes.B).toBeNull();
  });
});

describe("the note says where the number came from, and only until it doesn't", () => {
  it("clears when the knob is touched", () => {
    const { result } = slots();
    act(() => result.current.setSlotBackend("A", back("razor-2p")));
    expect(result.current.densityNotes.A).toBeTruthy();
    act(() => result.current.updateSlotOpts("A", { nPerWire: 31 }));
    expect(result.current.densityNotes.A).toBeNull();
  });

  it("survives an unrelated knob edit — that knob did not set the density", () => {
    const { result } = slots();
    act(() => result.current.setSlotBackend("A", back("razor-2p")));
    act(() => result.current.updateSlotOpts("A", { wireRadius: 0.002 }));
    expect(result.current.densityNotes.A).toBeTruthy();
  });

  it("clears on Reset, which returns the SEED and not an engine default", () => {
    const { result } = slots();
    act(() => result.current.setSlotBackend("A", back("razor-2p")));
    act(() => result.current.resetSlot("A"));
    expect(result.current.slots.A.backend.name).toBe("bspline");
    expect(result.current.slots.A.opts.nPerWire).toBe(15);
    expect(result.current.densityNotes.A).toBeNull();
  });
});

describe("a degree tab change adopts that degree's density", () => {
  // Slot A seeds at degree 2, so the walk starts there and 2 is reached by
  // coming BACK to it — setting a degree to what it already is is not a
  // change and must adopt nothing.
  it.each([
    [[1], 20],
    [[3], 16],
    [[1, 2], 15],
  ])("degrees %j -> N=%i", (walk, n) => {
    const { result } = slots();
    for (const degree of walk) {
      act(() =>
        result.current.updateSlotOpts("A", {
          model: { ...result.current.slots.A.opts.model, degree },
        }),
      );
    }
    const last = walk[walk.length - 1];
    expect(result.current.slots.A.opts.nPerWire).toBe(n);
    expect(result.current.densityNotes.A).toBe(
      `segments set to B-spline d=${last}'s default, ${n}`,
    );
  });

  it("a degree re-selected at its current value adopts nothing", () => {
    const { result } = slots();
    act(() => result.current.updateSlotOpts("A", { nPerWire: 44 }));
    act(() =>
      result.current.updateSlotOpts("A", {
        model: { ...result.current.slots.A.opts.model, degree: 2 },
      }),
    );
    expect(result.current.slots.A.opts.nPerWire).toBe(44);
    expect(result.current.densityNotes.A).toBeNull();
  });

  it("leaves a hand-set N alone on a backend that serves no per-degree map", () => {
    // hmatrix and arrayblock accept `degree` and keep one density across it.
    // Falling back to the flat default there would discard a value the user
    // chose, which this issue never said to do.
    const { result } = slots();
    act(() => result.current.setSlotBackend("A", back("hmatrix")));
    act(() => result.current.updateSlotOpts("A", { nPerWire: 55 }));
    act(() =>
      result.current.updateSlotOpts("A", {
        model: { ...result.current.slots.A.opts.model, degree: 1 },
      }),
    );
    expect(result.current.slots.A.opts.nPerWire).toBe(55);
    expect(result.current.densityNotes.A).toBeNull();
  });

  it("does not fire on a model edit that is not a degree change", () => {
    const { result } = slots();
    act(() => result.current.updateSlotOpts("A", { nPerWire: 44 }));
    act(() =>
      result.current.updateSlotOpts("A", {
        model: { ...result.current.slots.A.opts.model, extended_kernel: true },
      }),
    );
    expect(result.current.slots.A.opts.nPerWire).toBe(44);
    expect(result.current.densityNotes.A).toBeNull();
  });
});
