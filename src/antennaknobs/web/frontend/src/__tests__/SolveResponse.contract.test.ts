// The tsc-level half of the /solve response contract (issue #737): each
// fixture below is a real server response (see
// scripts/regenerate_solve_fixtures.py, which generates this test's
// ./fixtures/solveShapes.ts sibling from a live solve). `satisfies
// SolveResponse` fails `tsc --noEmit` the moment the server ships a field
// SolveResponse doesn't declare, or a field whose type disagrees — no regex
// tripwire over generated TS, just the compiler checking real shapes.
//
// The runtime assertions are deliberately trivial: the interesting check
// already happened at compile time. This test's job is to make sure that
// checked expression is actually reachable so `tsc --noEmit` cannot skip it
// as dead code, and to give the vitest run a concrete pass/fail per design.
import { describe, expect, it } from "vitest";
import type { SolveResponse } from "../lib/api";
import {
  doubletLadderTunerShape,
  invveeCatenaryShape,
  invveeShape,
} from "./fixtures/solveShapes";

describe("solve responses satisfy SolveResponse", () => {
  it("dipoles.invvee (plain build_wires antenna)", () => {
    expect(invveeShape satisfies SolveResponse).toBe(invveeShape);
  });

  it("wire.doublet_ladder_tuner (networked station: power_budget/plane)", () => {
    expect(doubletLadderTunerShape satisfies SolveResponse).toBe(
      doubletLadderTunerShape,
    );
  });

  it("dipoles.invvee_catenary (rig_report + readout_rows)", () => {
    expect(invveeCatenaryShape satisfies SolveResponse).toBe(
      invveeCatenaryShape,
    );
  });
});
