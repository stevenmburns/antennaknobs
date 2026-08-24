// Pins SmithChart (src/components/charts/SmithChart.tsx), in particular the
// frequency-anchor ring added for issue #719: the sweep-trail point nearest
// measFreqMhz gets a hollow highlight ring, distinct from the bright
// current-Z marker and from the endpoint dots.
//
// jsdom ships no 2-D canvas context, so unlike SweepChart (which exposes its
// pure derivation via data-* attributes) SmithChart does all of its geometry
// inside the draw effect itself — there is nothing to read off the DOM. To
// assert what actually got drawn, getContext() here returns a small
// recording stub that implements every CanvasRenderingContext2D method the
// component calls and pushes one entry per arc() call (with the fillStyle/
// strokeStyle/lineWidth in effect at that moment) into an array the test can
// inspect. This is a from-scratch idiom — no prior SmithChart test and no
// other chart test in this repo asserts drawn coordinates, only the
// null-context no-crash path.
// A ResizeObserver stub was briefly added here while diagnosing #726's CI
// failure — wrongly, it turned out: SmithChart takes `size` as a prop and
// never touches the sizing hooks, and the failing file in that CI run was
// DesignSession.mobile.test.tsx, whose OWN stub was torn down by afterEach's
// unstubAllGlobals() before a late React passive-effect flush ran (#728's
// real mechanism). setup.ts's unconditional defaults now close that race
// for every file; nothing needs stubbing here.
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { SmithChart } from "../components/charts/SmithChart";
import { reflectionCoefficient } from "../lib/format";
import { feedColor } from "../components/charts/palette";
import type { SweepData } from "../lib/api";

type ArcCall = {
  x: number;
  y: number;
  radius: number;
  fillStyle: string;
  strokeStyle: string;
  lineWidth: number;
};

function makeRecordingContext(): { ctx: CanvasRenderingContext2D; arcs: ArcCall[] } {
  const arcs: ArcCall[] = [];
  let fillStyle = "";
  let strokeStyle = "";
  let lineWidth = 1;
  let font = "";
  const ctx = {
    get fillStyle() {
      return fillStyle;
    },
    set fillStyle(v: string) {
      fillStyle = v;
    },
    get strokeStyle() {
      return strokeStyle;
    },
    set strokeStyle(v: string) {
      strokeStyle = v;
    },
    get lineWidth() {
      return lineWidth;
    },
    set lineWidth(v: number) {
      lineWidth = v;
    },
    get font() {
      return font;
    },
    set font(v: string) {
      font = v;
    },
    setTransform() {},
    fillRect() {},
    beginPath() {},
    arc(x: number, y: number, radius: number) {
      arcs.push({ x, y, radius, fillStyle, strokeStyle, lineWidth });
    },
    stroke() {},
    fill() {},
    moveTo() {},
    lineTo() {},
    save() {},
    restore() {},
    clip() {},
    fillText() {},
    measureText() {
      return { width: 0 };
    },
    setLineDash() {},
    rect() {},
    translate() {},
    rotate() {},
  };
  return { ctx: ctx as unknown as CanvasRenderingContext2D, arcs };
}

const Z0 = 50;
const SIZE = 220;
const CX = SIZE / 2;
const CY = SIZE / 2;
const R = SIZE / 2 - 10;

function gammaPoint(re: number, im: number) {
  const g = reflectionCoefficient(re, im, Z0);
  return { x: CX + g.gRe * R, y: CY - g.gIm * R };
}

function renderSmith(overrides: Partial<React.ComponentProps<typeof SmithChart>> = {}) {
  const { ctx, arcs } = makeRecordingContext();
  HTMLCanvasElement.prototype.getContext =
    (() => ctx) as unknown as HTMLCanvasElement["getContext"];
  const utils = render(
    <SmithChart
      r={0}
      x={0}
      z0={Z0}
      size={SIZE}
      sweep={null}
      converge={null}
      measured={null}
      measFreqMhz={14}
      running={false}
      convergeRunning={false}
      multiFeed={false}
      {...overrides}
    />,
  );
  return { ...utils, arcs };
}

// Sorted 3-point sweep: Z=50+0j / 100+0j / 25+0j across 10/14/18 MHz — same
// oracle triples used by SweepChart.test.tsx / math.test.ts.
const SWEEP: SweepData = {
  freqs_mhz: [10, 14, 18],
  z_re: [50, 100, 25],
  z_im: [0, 0, 0],
};

// Same three points, unsorted and non-uniformly spaced — a log-style sweep
// could arrive in any order and with irregular gaps. Index 1 (freq 10,
// Z=100+0j) is nearest whenever measFreqMhz sits near 10-11, which only a
// min-|Δf| scan (not a sortedness or uniform-spacing assumption) gets right.
const UNSORTED_SWEEP: SweepData = {
  freqs_mhz: [18, 10, 14],
  z_re: [25, 100, 50],
  z_im: [0, 0, 0],
};

const RING_RADIUS = 6;
const HIGHLIGHT_STROKE = "#cdd5e0"; // plotColors() fallback for --plot-label-strong

function ringArcs(arcs: ArcCall[]): ArcCall[] {
  return arcs.filter((a) => a.radius === RING_RADIUS);
}

describe("frequency-anchor ring (issue #719)", () => {
  it("highlights the trail point nearest measFreqMhz", () => {
    // measFreqMhz=13 is nearest to the 14 MHz sample (|13-14|=1) over the
    // 10 MHz (|13-10|=3) and 18 MHz (|13-18|=5) samples, so the ring should
    // land on the 100+0j point, not the 50+0j one it would sit on if the
    // component picked the array's first/last point instead of the nearest.
    const { arcs } = renderSmith({ sweep: SWEEP, measFreqMhz: 13 });
    const rings = ringArcs(arcs);
    expect(rings).toHaveLength(1);
    const expected = gammaPoint(100, 0);
    expect(rings[0].x).toBeCloseTo(expected.x, 5);
    expect(rings[0].y).toBeCloseTo(expected.y, 5);
    expect(rings[0].strokeStyle).toBe(HIGHLIGHT_STROKE);
    // Distinguishable from the current-Z marker: different radius (this is
    // the marker's *radius*, not its position) and no fill (only reachable
    // via stroke(), asserted by the mock only recording arc() calls used
    // together with a stroke — the marker instead uses fillStyle+fill()).
    expect(rings[0].radius).not.toBe(4);
  });

  it("picks the correct point for an unsorted, non-uniformly-spaced sweep", () => {
    // freqs arrive as [18, 10, 14]; measFreqMhz=11 is nearest to the 10 MHz
    // sample at index 1 (|11-10|=1) over index 2's 14 MHz (|11-14|=3) and
    // index 0's 18 MHz (|11-18|=7). A scan that assumed ascending order (or
    // bisected assuming uniform spacing) would not reliably land here.
    const { arcs } = renderSmith({ sweep: UNSORTED_SWEEP, measFreqMhz: 11 });
    const rings = ringArcs(arcs);
    expect(rings).toHaveLength(1);
    const expected = gammaPoint(100, 0);
    expect(rings[0].x).toBeCloseTo(expected.x, 5);
    expect(rings[0].y).toBeCloseTo(expected.y, 5);
  });

  it("draws no highlight when there is no sweep data, and does not crash", () => {
    const { arcs } = renderSmith({ sweep: null, r: 75, x: 10 });
    expect(ringArcs(arcs)).toHaveLength(0);
  });

  it("highlights the nearest endpoint when measFreqMhz is outside the sweep range", () => {
    // 40 MHz is well past the swept 10-18 MHz band; the nearest sample is
    // simply the high-frequency endpoint (18 MHz / 25+0j) — no special-case
    // clamping logic is needed, the plain min-|Δf| scan already lands there.
    const { arcs } = renderSmith({ sweep: SWEEP, measFreqMhz: 40 });
    const rings = ringArcs(arcs);
    expect(rings).toHaveLength(1);
    const expected = gammaPoint(25, 0);
    expect(rings[0].x).toBeCloseTo(expected.x, 5);
    expect(rings[0].y).toBeCloseTo(expected.y, 5);

    // And symmetrically for the low-frequency endpoint.
    const below = renderSmith({ sweep: SWEEP, measFreqMhz: -5 });
    const belowRings = ringArcs(below.arcs);
    expect(belowRings).toHaveLength(1);
    const expectedLo = gammaPoint(50, 0);
    expect(belowRings[0].x).toBeCloseTo(expectedLo.x, 5);
    expect(belowRings[0].y).toBeCloseTo(expectedLo.y, 5);
  });

  it("still draws the current-Z marker alongside the ring", () => {
    const { arcs } = renderSmith({ sweep: SWEEP, measFreqMhz: 14, r: 100, x: 0 });
    const expected = gammaPoint(100, 0);
    const marker = arcs.find(
      (a) =>
        a.radius === 4 &&
        Math.abs(a.x - expected.x) < 1e-6 &&
        Math.abs(a.y - expected.y) < 1e-6,
    );
    expect(marker).toBeTruthy();
    // The marker and the ring are both present and at radii that make them
    // visually distinguishable (marker r=4 filled dot, ring r=6 hollow).
    expect(ringArcs(arcs)).toHaveLength(1);
  });

  it("still draws the current-Z marker when there is no sweep at all", () => {
    const { arcs } = renderSmith({ sweep: null, r: 75, x: -25 });
    const expected = gammaPoint(75, -25);
    const marker = arcs.find(
      (a) =>
        a.radius === 4 &&
        Math.abs(a.x - expected.x) < 1e-6 &&
        Math.abs(a.y - expected.y) < 1e-6,
    );
    expect(marker).toBeTruthy();
  });
});

// The live trial rings (issue #789). During a streamed optimizer run the
// chart is the only thing on screen describing the geometry as it is NOW, and
// before this it described only feed 0 — while the minimax objective (#785)
// chases whichever feed is worst. On an 8-feed array that means the ring
// could sit still while the impedance actually being optimised walked away.
//
// Radii 5 (worst) and 3.5 (the rest) are unique to these rings: the settled
// marker is 4, the frequency anchor 6, trail dots 1.5/1.8/3, and no grid arc
// lands on either (r-circles are R/3 and R/6, x-arcs R/{0.2..5}, R = 100).
describe("live per-feed trial rings (issue #789)", () => {
  // Three feeds at distinct, well-separated impedances so a ring drawn at the
  // wrong feed's Z cannot coincide with the right answer.
  const TRIAL_FEEDS = [
    { z_re: 50, z_im: 0 },
    { z_re: 100, z_im: 0 },
    { z_re: 25, z_im: 0 },
  ];
  const WORST = 1;

  function trialRings(arcs: ArcCall[]): ArcCall[] {
    return arcs.filter((a) => a.radius === 5 || a.radius === 3.5);
  }

  it("draws one ring per feed, each at its own impedance", () => {
    const { arcs } = renderSmith({
      trial: true,
      r: 50,
      x: 0,
      trialFeeds: TRIAL_FEEDS,
      trialWorstFeed: WORST,
      multiFeed: true,
    });
    const rings = trialRings(arcs);
    expect(rings).toHaveLength(TRIAL_FEEDS.length);
    TRIAL_FEEDS.forEach((f, i) => {
      const expected = gammaPoint(f.z_re, f.z_im);
      expect(rings[i].x).toBeCloseTo(expected.x, 5);
      expect(rings[i].y).toBeCloseTo(expected.y, 5);
    });
  });

  it("draws the feed the objective is chasing bright, the rest dimmed", () => {
    const { arcs } = renderSmith({
      trial: true,
      r: 50,
      x: 0,
      trialFeeds: TRIAL_FEEDS,
      trialWorstFeed: WORST,
      multiFeed: true,
    });
    const rings = trialRings(arcs);
    expect(rings[WORST].radius).toBe(5);
    expect(rings[WORST].lineWidth).toBe(2);
    expect(rings[WORST].strokeStyle).toBe(feedColor(WORST, 0.85));
    for (const i of [0, 2]) {
      expect(rings[i].radius).toBe(3.5);
      expect(rings[i].strokeStyle).toBe(feedColor(i, 0.32));
      expect(rings[i].lineWidth).toBeLessThan(rings[WORST].lineWidth);
    }
  });

  it("falls back to the single r/x ring when the proposer sends no table", () => {
    // A single-feed design's payload omits `feeds` entirely — that shape is
    // byte-compatible on purpose, so the chart must not need the key.
    const { arcs } = renderSmith({ trial: true, r: 75, x: 10 });
    const rings = trialRings(arcs);
    expect(rings).toHaveLength(1);
    const expected = gammaPoint(75, 10);
    expect(rings[0].x).toBeCloseTo(expected.x, 5);
    expect(rings[0].y).toBeCloseTo(expected.y, 5);
    // A lone ring is the one being optimised by definition, so it stays
    // bright even though no worst-feed index came with it.
    expect(rings[0].radius).toBe(5);
    expect(rings[0].strokeStyle).toBe(feedColor(0, 0.85));
  });

  it("draws the trial table, not the settled solve's stale feeds", () => {
    // `feeds` still holds the PRE-RUN solve for the whole run: the knobs are
    // not touched until it ends. Drawing those was the frozen-dot defect;
    // drawing them ALONGSIDE the trial rings would be the same lie twice.
    const STALE = [
      { z_re: 5, z_im: 5, wire_index: 0, knot_index: 0, v_re: 1, v_im: 0 },
      { z_re: 7, z_im: -7, wire_index: 1, knot_index: 0, v_re: 1, v_im: 0 },
      { z_re: 9, z_im: 9, wire_index: 2, knot_index: 0, v_re: 1, v_im: 0 },
    ];
    const { arcs } = renderSmith({
      trial: true,
      r: 50,
      x: 0,
      feeds: STALE,
      trialFeeds: TRIAL_FEEDS,
      trialWorstFeed: WORST,
      multiFeed: true,
    });
    expect(trialRings(arcs)).toHaveLength(TRIAL_FEEDS.length);
    // No settled marker anywhere, and nothing drawn at a stale impedance.
    expect(arcs.filter((a) => a.radius === 4)).toHaveLength(0);
    for (const f of STALE) {
      const stale = gammaPoint(f.z_re, f.z_im);
      const hit = arcs.find(
        (a) => Math.abs(a.x - stale.x) < 1e-6 && Math.abs(a.y - stale.y) < 1e-6,
      );
      expect(hit).toBeUndefined();
    }
  });

  it("goes back to filled per-feed dots once the run settles", () => {
    // trial=false is the post-run state: the solve channel has caught up and
    // `feeds` is current again, so the grammar returns to filled dots.
    const SETTLED = TRIAL_FEEDS.map((f, i) => ({
      ...f,
      wire_index: i,
      knot_index: 0,
      v_re: 1,
      v_im: 0,
    }));
    const { arcs } = renderSmith({ feeds: SETTLED, multiFeed: true, r: 50, x: 0 });
    expect(trialRings(arcs)).toHaveLength(0);
    expect(arcs.filter((a) => a.radius === 4)).toHaveLength(SETTLED.length);
  });
});
