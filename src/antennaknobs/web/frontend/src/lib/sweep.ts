import type { SweepData } from "./api";
import { backendSupportsGround, type BackendEntry } from "./backends";
import type { GroundModel } from "./ground";
import type { BandSpec, ExampleDescriptor } from "./params";

// Sweep frequency plan: the log-spaced freq list `runSweep` requests.
// Sommerfeld ground stays at half resolution: momwire 0.7.0's C++ fill +
// grid cache made warm sweeps fast (~30 ms per point once the
// per-frequency grids are cached; measured 0.6 s for 21 points at 2
// threads), but the FIRST sweep after enabling it still fills one grid per
// point (measured 4.3 s for 21 points at 2 threads; 41 would be ~9 s) —
// half resolution halves that cold hit. Fast (reflection-coefficient)
// ground and momwire PEC ground are cheap enough for full resolution.
//
// Anchor + span come from the active example's sweep_policy (a variant can
// override it — see SweepPolicy in web/examples/_base.py). Anchor on the
// measurement frequency whenever the sweep should follow what the user is
// *viewing*: multiband designs declare anchor="meas_freq", and any design
// that's been unlocked from its design freq (to check the pattern on
// another band) should sweep that band too — not stay pinned to the
// design band. Locked single-resonance designs keep sweeping design_freq
// (where measFreq == designFreq anyway).
//
// Band-locked sweep: when the active band contains the anchor, snap the
// sweep range to that band's [min_mhz, max_mhz] so the trace stays inside
// the band the user is tuning instead of bleeding into adjacent ones.
// Falls through to the multiplicative window if the anchor sits outside
// every band.
export function planSweepFreqs(params: {
  backend: BackendEntry;
  groundEnabled: boolean;
  groundModel: GroundModel;
  currentExample: ExampleDescriptor | undefined;
  currentVariant: string;
  measLocked: boolean;
  measFreq: number;
  designFreq: number;
  currentBands: BandSpec[];
  freqWindowCeiling: number;
  /** Adaptive resolution is on for this session (the default): the base
   *  grid's job is then DETECTION, not resolution — it only has to land
   *  samples in a feature's tails for the refinement planner to dig in —
   *  so it starts lean and lets refinement spend points where the curve
   *  actually bends. 17 log-spaced (~6% spacing) keeps every plausible
   *  resonance signature within reach of at least one sample; much below
   *  15 the straddled-feature blindspot (a notch no sample touches at
   *  all) becomes a real risk. With refinement OFF the base grid IS the
   *  final rendering, so the historical 41 (21 on Sommerfeld ground)
   *  stays — the toggle must mean "today's behavior", not "coarser". */
  refineEnabled?: boolean;
}): number[] {
  const {
    backend,
    groundEnabled,
    groundModel,
    currentExample,
    currentVariant,
    measLocked,
    measFreq,
    designFreq,
    currentBands,
    freqWindowCeiling,
    refineEnabled = true,
  } = params;
  const slowGround =
    backendSupportsGround(backend) &&
    groundEnabled &&
    groundModel === "sommerfeld";
  const N = refineEnabled ? 17 : slowGround ? 21 : 41;
  const policy =
    currentExample?.variant_ui?.[currentVariant]?.sweep_policy ??
    currentExample?.sweep_policy;
  const sweepAnchor =
    !measLocked || policy?.anchor === "meas_freq" ? measFreq : designFreq;
  let fLo: number;
  let fHi: number;
  const bandLocked = policy?.band_locked
    ? currentBands.find(
        (b) => sweepAnchor >= b.min_mhz && sweepAnchor <= b.max_mhz,
      )
    : undefined;
  if (bandLocked) {
    fLo = bandLocked.min_mhz;
    fHi = bandLocked.max_mhz;
  } else {
    fLo = Math.max(0.5, sweepAnchor * (policy?.lo_factor ?? 0.8));
    fHi = Math.min(freqWindowCeiling, sweepAnchor * (policy?.hi_factor ?? 1.25));
  }
  return Array.from({ length: N }, (_, i) =>
    Math.exp(Math.log(fLo) + (i / (N - 1)) * (Math.log(fHi) - Math.log(fLo))),
  );
}

// Point budget for adaptive sweep refinement (issue #744), summed across
// rounds. 41 planned + 48 refined = 89 points, an order of magnitude under
// the hosted MAX_SWEEP_POINTS=500 cap (web/cost.py) and — thanks to the
// server's per-freq Z cache — nearly free to re-request on a later dwell.
export const SWEEP_REFINE_BUDGET = 48;
// Per round, so one round's plan (which cannot re-evaluate its own inserted
// points) never commits the whole budget on an estimate.
export const SWEEP_REFINE_ROUND_BUDGET = 12;

/** Merge refinement points into an accumulated sweep, re-sorted by
 *  frequency for display.
 *
 * Every row array is permuted by the SAME ordering — the per-feed Z rows
 * (bowtie arrays) are index-aligned with `freqs_mhz` by SweepData's
 * contract, and a chart that reads `feeds_z_re[i]` next to `freqs_mhz[i]`
 * would otherwise plot one feed's impedance at another frequency's x. A
 * frequency already present wins over the incoming duplicate: the existing
 * value came from the same cached solve, so preferring it keeps the merge
 * idempotent.
 */
export function mergeSweepPoints(base: SweepData, extra: SweepData): SweepData {
  const eps =
    Math.abs(
      (base.freqs_mhz[base.freqs_mhz.length - 1] ?? 0) -
        (base.freqs_mhz[0] ?? 0),
    ) * 1e-9;
  type Row = { from: "base" | "extra"; i: number };
  const rows: Row[] = base.freqs_mhz.map((_, i) => ({ from: "base", i }));
  for (let i = 0; i < extra.freqs_mhz.length; i++) {
    const f = extra.freqs_mhz[i];
    if (base.freqs_mhz.some((have) => Math.abs(have - f) <= eps)) continue;
    rows.push({ from: "extra", i });
  }
  const freqAt = (r: Row) =>
    (r.from === "base" ? base : extra).freqs_mhz[r.i];
  rows.sort((a, b) => freqAt(a) - freqAt(b));
  // Per-feed rows survive the merge only when every contributing row has
  // one. A half-populated feeds array would be worse than none: the chart
  // indexes it positionally, so a hole reads as another feed's impedance.
  const pick = (
    get: (s: SweepData) => number[][] | undefined,
  ): number[][] | undefined => {
    const got = rows.map((r) => get(r.from === "base" ? base : extra)?.[r.i]);
    return got.length > 0 && got.every((row) => Array.isArray(row))
      ? (got as number[][])
      : undefined;
  };
  const feedsRe = pick((s) => s.feeds_z_re);
  const feedsIm = pick((s) => s.feeds_z_im);
  return {
    freqs_mhz: rows.map(freqAt),
    z_re: rows.map((r) => (r.from === "base" ? base : extra).z_re[r.i]),
    z_im: rows.map((r) => (r.from === "base" ? base : extra).z_im[r.i]),
    ...(feedsRe ? { feeds_z_re: feedsRe } : {}),
    ...(feedsIm ? { feeds_z_im: feedsIm } : {}),
  };
}
