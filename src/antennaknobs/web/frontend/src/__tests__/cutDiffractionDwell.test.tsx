// The diffracted field on settle (issue #1373), client side.
//
// A faceted terrain has two far fields — #534's specular composer and #1373's
// with shadowing, tilted mirrors and UTD wedge diffraction — and the second
// costs about a second per pattern against 17 ms, per direction. So the app
// draws specular while a knob moves and composes the diffracted field once the
// knob settles.
//
// What is pinned here is everything that could make that swap silently not
// happen, or happen when it should not:
//
//  - no diffracted request mid-drag, ever;
//  - exactly one after the dwell, deduped across the two polar charts;
//  - none at all over a ground with only one field;
//  - the trace the chart reads flips field, at unchanged angles and unchanged
//    sample count — which is why the redraw key has to carry the field;
//  - the refinement rounds follow the field onto its own corners;
//  - a server that ignores the flag does not get its specular trace filed as
//    the settled one, because that is the one way the label could lie.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import {
  cutsRedrawKey,
  setCutRefineEnabled,
  useCutTraces,
} from "../components/charts/cuts";
import type { PatternCuts, SolveResponse } from "../lib/api";

const N = 24;
const dbiAt = (deg: number) => 10 + 5 * Math.cos((2 * deg * Math.PI) / 180);

function cuts(opts: {
  diffraction: boolean;
  angles?: number[];
  az?: number;
  el?: number;
}): PatternCuts {
  const angles =
    opts.angles ?? Array.from({ length: N }, (_, i) => (360 * i) / N);
  // The diffracted field is a DIFFERENT curve, so the fixture makes it one —
  // otherwise "did the swap happen" would be unanswerable from the samples.
  const lift = opts.diffraction ? 3 : 0;
  const dbi = angles.map((a) => dbiAt(a) + lift);
  return {
    az_elev_deg: opts.az ?? 15,
    elev_az_deg: opts.el ?? 0,
    n_dir: N,
    floor_dbi: -999,
    azimuth: dbi,
    elevation: dbi,
    ...(opts.angles ? { az_angles_deg: angles, elev_angles_deg: angles } : {}),
    diffraction: opts.diffraction,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;
let bodies: Record<string, unknown>[];
let solveSeq = 0;
/** Set for the "old server" case: reply to a diffracted request with the
 *  specular field, the way a build predating the flag would. */
let ignoreTheFlag = false;

const TERRAIN = {
  sectors: [{ az0: 0, az1: 360, facets: [[null, 0, 13, 0.005]] }],
} as unknown as SolveResponse["ground_terrain"];

function makeSolve(withTerrain = true): SolveResponse {
  // A fresh object per call: the cuts cache keys on solve identity, so this is
  // what "a new solve" means to this module.
  return {
    solve_id: `solve-${++solveSeq}`,
    cuts: cuts({ diffraction: false }),
    ...(withTerrain ? { ground_terrain: TERRAIN } : {}),
  } as unknown as SolveResponse;
}

beforeEach(() => {
  vi.useFakeTimers();
  bodies = [];
  ignoreTheFlag = false;
  setCutRefineEnabled(true);
  fetchMock = vi.fn((url: string, init?: { body?: string }) => {
    const body = JSON.parse(init?.body ?? "{}");
    if (url === "/cuts") bodies.push(body);
    const angles = body.az_angles_deg as number[] | undefined;
    const diffraction = !!body.diffraction && !ignoreTheFlag;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve(
          cuts({
            diffraction,
            ...(angles ? { angles: [...angles].sort((a, b) => a - b) } : {}),
          }),
        ),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  setCutRefineEnabled(true);
});

async function settle(ms: number, flushes = 60) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
    for (let i = 0; i < flushes; i++) await Promise.resolve();
  });
}

/** Any request in the settled field — the compose AND its refinement rounds. */
const diffractedBodies = () => bodies.filter((b) => b.diffraction === true);
/** The COMPOSE alone: the settled field at the uniform circle. Refinement
 *  rounds also carry the flag (that is their own test below), so counting "how
 *  many times did we ask for the other field" has to exclude them or the answer
 *  is the round count. */
const composeBodies = () =>
  bodies.filter((b) => b.diffraction === true && !b.az_angles_deg);

describe("diffracted field on settle (issue #1373)", () => {
  it("asks for nothing mid-drag and once after the dwell", async () => {
    const solve = makeSolve();
    const { result } = renderHook(() => useCutTraces("xy", [solve], 15, 0));
    // The solve already carries cuts at these angles, so nothing is fetched.
    await settle(300);
    expect(diffractedBodies()).toHaveLength(0);
    expect(result.current[0]!.diffraction).toBe(false);

    await settle(500);
    expect(composeBodies()).toHaveLength(1);
    expect(result.current[0]!.diffraction).toBe(true);
  });

  it("a cut-dial drag inside the dwell asks for nothing", async () => {
    const solve = makeSolve();
    const { rerender } = renderHook(
      (p: { az: number }) => useCutTraces("xy", [solve], p.az, 0),
      { initialProps: { az: 15 } },
    );
    for (const az of [16, 17, 18, 19, 20]) {
      await settle(100);
      rerender({ az });
    }
    expect(diffractedBodies()).toHaveLength(0);
  });

  it("the swap keeps the angles and the sample count, and moves the trace", async () => {
    const solve = makeSolve();
    setCutRefineEnabled(false); // isolate the swap from refinement
    const { result } = renderHook(() => useCutTraces("xy", [solve], 15, 0));
    await settle(300);
    const before = result.current[0]!;
    await settle(500);
    const after = result.current[0]!;

    expect(after.diffraction).toBe(true);
    expect(after.azimuth).toHaveLength(before.azimuth.length);
    expect(after.az_angles_deg).toBeUndefined();
    expect(after.az_elev_deg).toBe(before.az_elev_deg);
    expect(after.azimuth).not.toEqual(before.azimuth);

    // Everything a chart could key a redraw on EXCEPT the field is unchanged,
    // which is why the field is in the key.
    const without = (t: PatternCuts) =>
      `${t.az_elev_deg},${t.elev_az_deg},${t.azimuth.length},${t.elevation.length}`;
    expect(without(after)).toBe(without(before));
    expect(cutsRedrawKey([after])).not.toBe(cutsRedrawKey([before]));
  });

  it("asks for nothing over a ground with only one field", async () => {
    const solve = makeSolve(false); // no faceted terrain
    const { result } = renderHook(() => useCutTraces("xy", [solve], 15, 0));
    await settle(1200);
    expect(diffractedBodies()).toHaveLength(0);
    expect(result.current[0]!.diffraction).toBe(false);
  });

  it("both polar charts settling together make one request", async () => {
    const solve = makeSolve();
    setCutRefineEnabled(false);
    renderHook(() => useCutTraces("xy", [solve], 15, 0));
    renderHook(() => useCutTraces("yz", [solve], 15, 0));
    await settle(1200);
    expect(composeBodies()).toHaveLength(1);
  });

  it("refinement follows the field onto its own corners", async () => {
    const solve = makeSolve();
    const { result } = renderHook(() => useCutTraces("xy", [solve], 15, 0));
    await settle(1200);
    const rounds = bodies.filter((b) => Array.isArray(b.az_angles_deg));
    expect(rounds.length).toBeGreaterThan(0);
    // Every round asks for the settled field. A round that dropped the flag
    // would densify the specular curve and cache it as the settled one.
    expect(rounds.every((b) => b.diffraction === true)).toBe(true);
    expect(result.current[0]!.diffraction).toBe(true);
    expect(result.current[0]!.azimuth.length).toBeGreaterThan(N);
  });

  it("a server that ignores the flag leaves the specular trace as specular", async () => {
    // The one way the label could lie: a reply composed the OTHER way filed
    // under the settled field. Better to keep drawing the specular trace and
    // say so — a true picture of a different field, rather than a false
    // caption on this one.
    ignoreTheFlag = true;
    const solve = makeSolve();
    setCutRefineEnabled(false);
    const { result } = renderHook(() => useCutTraces("xy", [solve], 15, 0));
    await settle(1200);
    expect(composeBodies()).toHaveLength(1); // it did ask
    expect(result.current[0]!.diffraction).toBe(false); // and did not believe it
  });

  it("a new solve settles on its own", async () => {
    const first = makeSolve();
    const { result, rerender } = renderHook(
      (p: { s: SolveResponse }) => useCutTraces("xy", [p.s], 15, 0),
      { initialProps: { s: first } },
    );
    await settle(1200);
    expect(result.current[0]!.diffraction).toBe(true);
    const second = makeSolve();
    rerender({ s: second });
    await settle(300);
    expect(result.current[0]!.diffraction).toBe(false); // dragging again
    await settle(500);
    expect(result.current[0]!.diffraction).toBe(true);
    expect(composeBodies()).toHaveLength(2);
  });
});
