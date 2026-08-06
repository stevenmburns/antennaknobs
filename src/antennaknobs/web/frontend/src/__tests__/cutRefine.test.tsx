// Adaptive cut refinement (issue #744), client side.
//
// Two things are pinned here. First the GEOMETRY: a refined cut is no
// longer uniform, so the chart can no longer derive a sample's angle from
// its index — it has to read the angles the server sent, and the drawn
// polyline must land where those angles say. Second the TRANSPORT: the
// refinement request only goes out after a dwell (never mid-drag), carries
// explicit angles, respects its budget, and leaves nothing behind when the
// solve changes.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import {
  CUT_REFINE_BUDGET,
  setCutRefineEnabled,
  traceFor,
  useCutTraces,
} from "../components/charts/cuts";
import { cutDbiToFrac, cutProjection, maxChordDeviation } from "../lib/refine";
import type { PatternCuts, SolveResponse } from "../lib/api";

// Six lobes over the circle: the null-to-lobe transitions are what a fixed
// polar grid renders as corners.
const dbiAt = (deg: number) =>
  10 + 20 * Math.log10(Math.abs(Math.cos((6 * deg * Math.PI) / 180)) + 3e-3);

function uniformCuts(n: number, az = 15, el = 0): PatternCuts {
  const dbi = Array.from({ length: n }, (_, i) => dbiAt((360 * i) / n));
  return {
    az_elev_deg: az,
    elev_az_deg: el,
    n_dir: n,
    floor_dbi: -999,
    azimuth: dbi,
    elevation: dbi,
  };
}

function cutsAtAngles(anglesDeg: number[], az = 15, el = 0): PatternCuts {
  const dbi = anglesDeg.map(dbiAt);
  return {
    az_elev_deg: az,
    elev_az_deg: el,
    n_dir: 180,
    floor_dbi: -999,
    azimuth: dbi,
    elevation: dbi,
    az_angles_deg: anglesDeg,
    elev_angles_deg: anglesDeg,
  };
}

// ---- geometry --------------------------------------------------------------

/** FarFieldChart's screen-coordinate loop, extracted verbatim in shape:
 *  sample i sits at 2π·i/n unless the trace carries explicit angles. */
function chartPoints(
  dbi: number[],
  anglesDeg: number[] | undefined,
  dbiTop: number,
  cx: number,
  cy: number,
  R: number,
) {
  const toFrac = cutDbiToFrac(dbiTop);
  const n = dbi.length;
  const out: { x: number; y: number }[] = [];
  for (let pi = 0; pi <= n; pi++) {
    const i = pi % n;
    const t = anglesDeg ? (anglesDeg[i] * Math.PI) / 180 : (2 * Math.PI * pi) / n;
    const frac = toFrac(dbi[i]);
    out.push({ x: cx + Math.cos(t) * frac * R, y: cy - Math.sin(t) * frac * R });
  }
  return out;
}

describe("non-uniform cut geometry", () => {
  it("traceFor hands the chart the explicit angles when the cut is refined", () => {
    const uniform = traceFor(uniformCuts(8), "xy");
    expect(uniform!.anglesDeg).toBeUndefined();
    const refined = traceFor(cutsAtAngles([0, 30, 45, 200, 359]), "yz");
    expect(refined!.anglesDeg).toEqual([0, 30, 45, 200, 359]);
  });

  it("drops an angle list that does not match its samples", () => {
    // A server/client disagreement must fall back to the uniform
    // parameterisation, not index past the end of the list.
    const bad = { ...cutsAtAngles([0, 90, 180, 270]), az_angles_deg: [0, 90] };
    expect(traceFor(bad, "xy")!.anglesDeg).toBeUndefined();
  });

  it("places a refined sample at its own angle, not at its index", () => {
    // Four samples at 0/90/180/270 plus one inserted at 315: read by index
    // the inserted point would land at 288°, a visibly wrong place.
    const angles = [0, 90, 180, 270, 315];
    const dbi = angles.map(() => 10); // constant radius: the rim
    const pts = chartPoints(dbi, angles, 10, 100, 100, 50);
    expect(pts[4].x).toBeCloseTo(100 + 50 * Math.cos((315 * Math.PI) / 180), 9);
    expect(pts[4].y).toBeCloseTo(100 - 50 * Math.sin((315 * Math.PI) / 180), 9);
    // Uniform reading of the same five samples puts it at 288° — the bug
    // this field exists to prevent.
    const wrong = chartPoints(dbi, undefined, 10, 100, 100, 50);
    expect(wrong[4].x).not.toBeCloseTo(pts[4].x, 3);
  });

  it("closes the polygon back to the first sample", () => {
    const angles = [0, 90, 180, 270, 315];
    const pts = chartPoints(angles.map(dbiAt), angles, 11, 100, 100, 50);
    expect(pts).toHaveLength(angles.length + 1);
    expect(pts[pts.length - 1]).toEqual(pts[0]);
  });

  it("a refined trace draws closer to the true pattern than the uniform one", () => {
    // The acceptance shape, in display units: same chart, same radial
    // scale, denser sampling ⇒ strictly less drawn error.
    const n = 24;
    const base = Array.from({ length: n }, (_, i) => dbiAt((360 * i) / n));
    const top = 11;
    const coarse = maxChordDeviation(cutProjection(base, undefined, top), true);
    const dense = Array.from({ length: 4 * n }, (_, i) => (360 * i) / (4 * n));
    const fine = maxChordDeviation(
      cutProjection(dense.map(dbiAt), dense, top),
      true,
    );
    expect(fine).toBeLessThan(coarse);
  });
});

// ---- transport -------------------------------------------------------------

let fetchMock: ReturnType<typeof vi.fn>;
let cutsBodies: Record<string, unknown>[];
let solveSeq = 0;

function makeSolve(): SolveResponse {
  // A fresh object per call: the cuts cache keys on solve identity, so this
  // is what "a new solve" means to this module.
  return {
    solve_id: `solve-${++solveSeq}`,
    cuts: uniformCuts(24),
  } as unknown as SolveResponse;
}

beforeEach(() => {
  vi.useFakeTimers();
  cutsBodies = [];
  fetchMock = vi.fn((url: string, init?: { body?: string }) => {
    const body = JSON.parse(init?.body ?? "{}");
    if (url === "/cuts") cutsBodies.push(body);
    const angles: number[] | undefined = body.az_angles_deg;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve(
          angles ? cutsAtAngles([...angles].sort((a, b) => a - b)) : uniformCuts(24),
        ),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function settle(ms: number, flushes = 60) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
    for (let i = 0; i < flushes; i++) await Promise.resolve();
  });
}

const refineBodies = () =>
  cutsBodies.filter((b) => Array.isArray(b.az_angles_deg));

describe("cut refinement transport (issue #744)", () => {
  it("refines only after the dwell, at explicit angles, within budget", async () => {
    const solve = makeSolve();
    const { result } = renderHook(() => useCutTraces("xy", [solve], 15, 0));
    // The solve already carries cuts at these angles, so nothing is fetched
    // and nothing is refined until the dwell elapses.
    await settle(300);
    expect(refineBodies()).toHaveLength(0);

    await settle(500);
    const rounds = refineBodies();
    expect(rounds.length).toBeGreaterThan(0);
    for (const b of rounds) {
      expect(b.az_elev_deg).toBe(15);
      expect(b.elev_az_deg).toBe(0);
      // Every request carries the WHOLE parameterisation (base + added), so
      // the server has no state to reconcile.
      const angles = b.az_angles_deg as number[];
      expect(angles.length).toBeGreaterThan(24);
      expect(angles.length).toBeLessThanOrEqual(24 + CUT_REFINE_BUDGET);
    }
    // The chart now sees a denser trace than the solve shipped with.
    const trace = traceFor(result.current[0], "xy")!;
    expect(trace.dbi.length).toBeGreaterThan(24);
    expect(trace.anglesDeg).toBeDefined();
    expect(trace.anglesDeg).toEqual(
      [...trace.anglesDeg!].sort((a, b) => a - b),
    );
  });

  it("a cut-dial drag inside the dwell issues no refinement", async () => {
    const solve = makeSolve();
    const { rerender } = renderHook(
      (p: { az: number }) => useCutTraces("xy", [solve], p.az, 0),
      { initialProps: { az: 15 } },
    );
    // Drag through a run of angles, each well inside the refinement dwell.
    for (const az of [16, 17, 18, 19, 20]) {
      rerender({ az });
      await settle(100);
    }
    expect(refineBodies()).toHaveLength(0);
    // Letting go fetches the cuts for where the dial landed (120 ms), and a
    // dwell after THAT lands, refinement runs — for 20, never for 16..19.
    await settle(500);
    expect(refineBodies()).toHaveLength(0);
    await settle(500);
    expect(refineBodies().length).toBeGreaterThan(0);
    for (const b of refineBodies()) expect(b.az_elev_deg).toBe(20);
  });

  it("a new solve leaves no refined sample behind", async () => {
    const first = makeSolve();
    const { result, rerender } = renderHook(
      (p: { solve: SolveResponse }) => useCutTraces("xy", [p.solve], 15, 0),
      { initialProps: { solve: first } },
    );
    await settle(1000);
    expect(traceFor(result.current[0], "xy")!.dbi.length).toBeGreaterThan(24);

    const second = makeSolve();
    rerender({ solve: second });
    // Keyed on solve identity: the new solve draws its own uniform cuts,
    // never the previous solve's refined ones.
    const fresh = traceFor(result.current[0], "xy")!;
    expect(fresh.dbi).toHaveLength(24);
    expect(fresh.anglesDeg).toBeUndefined();
  });

  it("stops when the trace is already accurate enough", async () => {
    // A round pattern on the real 180-point grid: the drawn 180-gon misses
    // the true circle by far less than a pixel, so no round is spent.
    const round = {
      ...uniformCuts(180),
      azimuth: Array.from({ length: 180 }, () => 5),
      elevation: Array.from({ length: 180 }, () => 5),
    };
    const solve = {
      solve_id: "solve-round",
      cuts: round,
    } as unknown as SolveResponse;
    renderHook(() => useCutTraces("xy", [solve], 15, 0));
    await settle(1000);
    expect(refineBodies()).toHaveLength(0);
  });

  it("buys angles only for the cut whose chart is mounted", async () => {
    // Faithful mock: echo an explicit list only for the cut that asked for
    // one, exactly like the real server ("absent means uniform").
    fetchMock.mockImplementation((url: string, init?: { body?: string }) => {
      const body = JSON.parse(init?.body ?? "{}");
      if (url === "/cuts") cutsBodies.push(body);
      const az: number[] | undefined = body.az_angles_deg;
      const el: number[] | undefined = body.elev_angles_deg;
      const at = (a: number[] | undefined) =>
        a ? [...a].sort((x, y) => x - y).map(dbiAt) : uniformCuts(24).azimuth;
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            ...uniformCuts(24),
            azimuth: at(az),
            elevation: at(el),
            ...(az ? { az_angles_deg: [...az].sort((x, y) => x - y) } : {}),
            ...(el ? { elev_angles_deg: [...el].sort((x, y) => x - y) } : {}),
          }),
      });
    });
    // Only the azimuth chart is mounted (the hook registers its cut).
    renderHook(() => useCutTraces("xy", [makeSolve()], 15, 0));
    await settle(1000);
    const rounds = refineBodies();
    expect(rounds.length).toBeGreaterThan(0);
    // Not one request spent an angle on the elevation cut: its chart is not
    // on screen, so its uniform parameterisation travels as ABSENT.
    for (const b of cutsBodies) expect(b.elev_angles_deg).toBeUndefined();
  });

  it("the adaptive-resolution toggle gates cut refinement entirely", async () => {
    setCutRefineEnabled(false);
    try {
      renderHook(() => useCutTraces("xy", [makeSolve()], 15, 0));
      await settle(1500);
      expect(refineBodies()).toHaveLength(0);
    } finally {
      setCutRefineEnabled(true);
    }
  });
});
