// The sweep charts' vertical axis (AK#1738): the range a viewer picks for the
// VSWR and S11-vs-frequency charts, the Auto fit that replaces the old fixed
// 1–10 / −30..0 scales, and the SWR-threshold line with its bandwidth
// readout. Pure and React-free: SweepChart draws from it and the refinement
// planner (lib/refine.ts) judges curvature against it, so the two cannot
// disagree about where a sample lands.

export type SweepMode = "gamma" | "vswr";

/** A chart's vertical range. "auto" fits the sweep's dip; "fixed" is a
 *  preset or a custom min/max, in the chart's own units (VSWR, or S11 dB).
 *  "reciprocal" is VSWR only: the whole 1…∞ range on the compressed scale
 *  y = 1 − 1/SWR (see swrReciprocalY). It is a range choice like the others,
 *  not a scale toggle on top of one — the scale IS its range (1 to ∞, all of
 *  it), so there is nothing left for a range to choose, and one choice per
 *  chart keeps the popover, the stored prefs and the planner single-valued. */
export type SweepAxisChoice =
  | { kind: "auto" }
  | { kind: "fixed"; lo: number; hi: number }
  | { kind: "reciprocal" };

export type SweepAxes = Record<SweepMode, SweepAxisChoice>;

export type AxisDomain = { lo: number; hi: number };

export const AUTO: SweepAxisChoice = { kind: "auto" };
export const AUTO_AXES: SweepAxes = { vswr: AUTO, gamma: AUTO };

/** The popover's presets. VSWR is a top over the fixed floor of 1; S11 is a
 *  floor under a 0 dB top (which still grows for an over-unity port, see
 *  s11DbTop in lib/refine.ts). */
export const VSWR_PRESET_TOPS = [1.5, 2, 3, 5, 10] as const;
export const S11_PRESET_FLOORS = [-10, -20, -30, -40] as const;

/** The "nice" edges Auto chooses among, smallest range first. Past the last
 *  one the axis stops growing and the rest pegs (VSWR) or clamps (S11), as
 *  the fixed scales always did. VSWR tops end at 100 because vswrFromGammaMag
 *  caps at 99. */
export const VSWR_AUTO_TOPS = [1.5, 2, 3, 5, 10, 20, 50, 100] as const;
export const S11_AUTO_FLOORS = [-10, -20, -30, -40, -50, -60] as const;

/** Auto's headroom. Both charts put the good match at the bottom; what Auto
 *  moves differs. VSWR's floor is fixed at 1 and Auto moves the TOP: the dip
 *  stays in the lower two thirds, leaving room to see the curve climb out of
 *  it. S11's top is fixed at 0 dB and Auto moves the FLOOR: the dip clears it
 *  by at least 5 dB, so a dip reads as a dip and not as a clamp. */
export const VSWR_AUTO_HEADROOM = 1 / 3;
export const S11_AUTO_CLEARANCE_DB = 5;

/** Where the old fixed scales sat, and where Auto starts with nothing to fit
 *  (no sweep and no marker yet). */
export const VSWR_EMPTY: AxisDomain = { lo: 1, hi: 10 };
export const S11_EMPTY_FLOOR = -30;

/** The SWR threshold line's default: the 2:1 bandwidth hams quote. */
export const DEFAULT_SWR_THRESHOLD = 2;
export const SWR_THRESHOLD_MIN = 1.05;
export const SWR_THRESHOLD_MAX = 20;

const finite = (vs: readonly number[]) => vs.filter((v) => Number.isFinite(v));

/** The dip of a set of chart values: the lowest VSWR, or the most negative
 *  S11 dB. Null when there is nothing finite to fit. */
export function sweepDip(values: readonly number[]): number | null {
  const f = finite(values);
  return f.length ? Math.min(...f) : null;
}

/** Auto's VSWR top: the smallest nice top that holds the dip with headroom
 *  AND is at least the SWR threshold, so the threshold line is always on
 *  screen under Auto (Steve, 2026-09-25: a sharp dip alone picks 1.5, which
 *  hid the 2:1 line). Threshold 2 ⇒ at least 2; 2.5 ⇒ at least 3. */
export function autoVswrTop(
  values: readonly number[],
  threshold = DEFAULT_SWR_THRESHOLD,
): number {
  const dip = sweepDip(values);
  const fits = (top: number) =>
    top >= threshold &&
    (dip === null
      ? top >= VSWR_EMPTY.hi
      : dip - 1 <= (1 - VSWR_AUTO_HEADROOM) * (top - 1));
  return VSWR_AUTO_TOPS.find(fits) ?? VSWR_AUTO_TOPS[VSWR_AUTO_TOPS.length - 1];
}

/** Auto's S11 floor: the shallowest nice floor the dip clears by
 *  S11_AUTO_CLEARANCE_DB — the VSWR rule mirrored onto the moving floor —
 *  and at or below the threshold's return loss, so the line stays on screen.
 *  Every floor is ≤ −10 dB and a threshold's line is above that from 2:1 up
 *  (−9.54 dB; 5:1 is −3.5), so this only bites for a tight threshold: 1.1:1
 *  is −26.4 dB, which needs a −30 floor. */
export function autoS11Floor(
  values: readonly number[],
  threshold = DEFAULT_SWR_THRESHOLD,
): number {
  const dip = sweepDip(values);
  const line = s11DbForSwr(threshold);
  const fits = (floor: number) =>
    floor <= line &&
    (dip === null ? floor <= S11_EMPTY_FLOOR : dip - floor >= S11_AUTO_CLEARANCE_DB);
  return S11_AUTO_FLOORS.find(fits) ?? S11_AUTO_FLOORS[S11_AUTO_FLOORS.length - 1];
}

// --- the compressed VSWR scale (y = 1 − 1/SWR) ------------------------------

export const RECIPROCAL: SweepAxisChoice = { kind: "reciprocal" };

/** SWR → the compressed scale's y: 1 − 1/SWR = 2|Γ|/(1 + |Γ|), mapping SWR
 *  1…∞ onto 0…1 (1.5 → ⅓, 2 → ½, 3 → ⅔, 5 → 0.8, 10 → 0.9). Every SWR
 *  fits below the top, so nothing ever pegs. A non-number or anything
 *  below 1 reads as 1 (y = 0). */
export function swrReciprocalY(swr: number): number {
  if (!(swr > 1)) return 0;
  return 1 - 1 / swr;
}

/** The compressed scale's tick marks, labelled in SWR, ∞ at the top. */
export const RECIPROCAL_TICK_SWRS = [1, 1.5, 2, 3, 5, 10] as const;

/** A tick: where it sits in the axis's own coordinates, and its label. */
export type AxisTick = { at: number; label: string };

/** Chart value → the axis coordinate the domain is measured in. The
 *  identity for every choice but the compressed VSWR scale. The chart and
 *  the refinement planner both place samples through this, so the planner
 *  judges curvature on the geometry actually drawn. */
export function axisProjector(
  mode: SweepMode,
  choice: SweepAxisChoice,
): (v: number) => number {
  return mode === "vswr" && choice.kind === "reciprocal"
    ? swrReciprocalY
    : (v) => v;
}

/** The drawn domain for a mode, a choice and the values Auto fits.
 *
 *  `s11Top` is the S11 top the over-unity rule gives (s11DbTop: 0 for any
 *  passive port); it applies to Auto and to a preset floor. A custom range's
 *  own top wins, and a value above it pegs like VSWR's. `threshold` is the
 *  SWR threshold, which Auto keeps on screen; fixed ranges ignore it. */
export function sweepAxisDomain(
  mode: SweepMode,
  choice: SweepAxisChoice,
  values: readonly number[],
  s11Top = 0,
  threshold = DEFAULT_SWR_THRESHOLD,
): AxisDomain {
  if (mode === "vswr") {
    if (choice.kind === "fixed") return { lo: choice.lo, hi: choice.hi };
    // In axisProjector's coordinates: all of 1…∞.
    if (choice.kind === "reciprocal") return { lo: 0, hi: 1 };
    return { lo: 1, hi: autoVswrTop(values, threshold) };
  }
  // (A reciprocal choice is VSWR only; validChoice refuses it for S11, and
  // it falls through to Auto here should one ever arrive.)
  if (choice.kind === "fixed") {
    // A preset is a floor under 0 dB; a custom range carries its own top.
    return choice.hi === 0
      ? { lo: choice.lo, hi: s11Top }
      : { lo: choice.lo, hi: choice.hi };
  }
  return { lo: autoS11Floor(values, threshold), hi: s11Top };
}

/** The grow-only rule while a knob is live: the union of the range already
 *  on screen and the one the new values ask for, so the axis never shrinks
 *  under the viewer's hand. */
export function widenDomain(held: AxisDomain | null, next: AxisDomain): AxisDomain {
  if (!held) return next;
  return { lo: Math.min(held.lo, next.lo), hi: Math.max(held.hi, next.hi) };
}

/** Tick values for a domain: a 1-2-2.5-5 step giving about five intervals,
 *  plus the domain's own floor (VSWR 1 is always labelled). */
export function axisTicks(d: AxisDomain, target = 5): number[] {
  const span = d.hi - d.lo;
  if (!(span > 0)) return [d.lo];
  const raw = span / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step =
    [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw * (1 - 1e-9)) ??
    10 * mag;
  const out: number[] = [];
  const eps = step * 1e-6;
  for (let t = Math.ceil((d.lo - eps) / step) * step; t <= d.hi + eps; t += step) {
    // Snapped to the step and rounded to 12 significant digits, so 1.2 is
    // 1.2 and not 1.2000000000000002.
    out.push(Number((Math.round(t / step) * step).toPrecision(12)));
  }
  if (out.length === 0 || Math.abs(out[0] - d.lo) > eps) out.unshift(d.lo);
  return out;
}

/** The tick marks a chart draws, in its axis coordinates. The compressed
 *  VSWR scale gets SWR-labelled marks at RECIPROCAL_TICK_SWRS plus ∞ at the
 *  top; everything else is axisTicks' numbers labelled as themselves. */
export function axisTickMarks(
  mode: SweepMode,
  choice: SweepAxisChoice,
  d: AxisDomain,
): AxisTick[] {
  if (mode === "vswr" && choice.kind === "reciprocal") {
    return [
      ...RECIPROCAL_TICK_SWRS.map((s) => ({ at: swrReciprocalY(s), label: formatTick(s) })),
      { at: 1, label: "∞" },
    ];
  }
  return axisTicks(d).map((t) => ({ at: t, label: formatTick(t) }));
}

/** A tick label: integers bare, the rest to at most two decimals. */
export function formatTick(t: number): string {
  if (Number.isInteger(t)) return t.toFixed(0);
  return String(Number(t.toFixed(2)));
}

/** The S11 dB that matches an SWR threshold: 20·log₁₀((s−1)/(s+1)). 2:1 is
 *  −9.54 dB. */
export function s11DbForSwr(swr: number): number {
  return 20 * Math.log10((swr - 1) / (swr + 1));
}

/** One run of the sweep with SWR below the threshold. `lo`/`hi` are the
 *  interpolated threshold crossings; an `open` edge is where the run meets
 *  the sweep's own edge instead, so the true band may extend past it. */
export type SwrBand = {
  lo: number;
  hi: number;
  openLo: boolean;
  openHi: boolean;
};

// Where the straight line from (f0, v0) to (f1, v1) crosses `t`.
function crossing(f0: number, v0: number, f1: number, v1: number, t: number): number {
  return v1 === v0 ? f0 : f0 + ((t - v0) / (v1 - v0)) * (f1 - f0);
}

/** Every run of `vswr` below `threshold`, in frequency order, each edge
 *  found by linear interpolation between the two samples that straddle the
 *  threshold (the same straight segment the VSWR chart draws), never
 *  snapped to a sample. A sample exactly at the threshold is not below it.
 *  Non-finite samples count as above. */
export function swrBands(
  freqs: readonly number[],
  vswr: readonly number[],
  threshold: number,
): SwrBand[] {
  const n = Math.min(freqs.length, vswr.length);
  const below = (i: number) => Number.isFinite(vswr[i]) && vswr[i] < threshold;
  const out: SwrBand[] = [];
  let start: { f: number; open: boolean } | null = null;
  for (let i = 0; i < n; i++) {
    if (below(i) && start === null) {
      start =
        i === 0
          ? { f: freqs[0], open: true }
          : {
              f: Number.isFinite(vswr[i - 1])
                ? crossing(freqs[i - 1], vswr[i - 1], freqs[i], vswr[i], threshold)
                : freqs[i - 1],
              open: false,
            };
    } else if (!below(i) && start !== null) {
      const hi = Number.isFinite(vswr[i])
        ? crossing(freqs[i - 1], vswr[i - 1], freqs[i], vswr[i], threshold)
        : freqs[i];
      out.push({ lo: start.f, hi, openLo: start.open, openHi: false });
      start = null;
    }
  }
  if (start !== null && n > 0) {
    out.push({ lo: start.f, hi: freqs[n - 1], openLo: start.open, openHi: true });
  }
  return out;
}

/** The band the readout reports: the one holding the operating frequency
 *  (the chart's dashed guide) when there is one, else the widest. Null when
 *  no sample is below the threshold. */
export function primaryBand(bands: readonly SwrBand[], measFreqMhz: number): SwrBand | null {
  if (bands.length === 0) return null;
  const holding = bands.find((b) => measFreqMhz >= b.lo && measFreqMhz <= b.hi);
  if (holding) return holding;
  return bands.reduce((w, b) => (b.hi - b.lo > w.hi - w.lo ? b : w));
}

/** A frequency span for the readout: kHz below 1 MHz, else MHz. */
export function formatSpan(mhz: number): string {
  return mhz < 1 ? `${(mhz * 1000).toFixed(0)} kHz` : `${mhz.toFixed(3)} MHz`;
}

/** The readout's text. One band: its width. An open edge (the run meets the
 *  sweep's end) reads "≥", since the band may continue past the sweep. More
 *  than one band: the primary band's width and the count, so a second dip is
 *  never silently summed into or dropped from the number. */
export function bandwidthReadout(
  bands: readonly SwrBand[],
  measFreqMhz: number,
  threshold: number,
): string {
  const label = `${formatTick(Number(threshold.toFixed(2)))}:1 BW`;
  const b = primaryBand(bands, measFreqMhz);
  if (!b) return `${label} none`;
  const open = b.openLo || b.openHi ? "≥" : "";
  const more = bands.length > 1 ? ` (1 of ${bands.length})` : "";
  return `${label} ${open}${formatSpan(b.hi - b.lo)}${more}`;
}

// --- persistence (the view prefs' sweepAxes / swrThreshold fields) ---------

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Whether a choice is drawable for its mode: VSWR at or above 1, S11 at or
 *  below its top, and a nonzero span. */
export function validChoice(mode: SweepMode, c: SweepAxisChoice): boolean {
  if (c.kind === "auto") return true;
  if (c.kind === "reciprocal") return mode === "vswr";
  if (!Number.isFinite(c.lo) || !Number.isFinite(c.hi) || !(c.hi > c.lo)) return false;
  return mode === "vswr" ? c.lo >= 1 : true;
}

/** A stored choice, distrusted like everything in localStorage: anything
 *  that is not a drawable choice reads as Auto. */
export function sanitizeChoice(mode: SweepMode, raw: unknown): SweepAxisChoice {
  if (isRecord(raw) && raw.kind === "reciprocal") {
    return validChoice(mode, RECIPROCAL) ? RECIPROCAL : AUTO;
  }
  if (!isRecord(raw) || raw.kind !== "fixed") return AUTO;
  const c: SweepAxisChoice = {
    kind: "fixed",
    lo: Number(raw.lo),
    hi: Number(raw.hi),
  };
  return validChoice(mode, c) ? c : AUTO;
}

export function sanitizeThreshold(raw: unknown): number {
  const t = Number(raw);
  return Number.isFinite(t) && t >= SWR_THRESHOLD_MIN && t <= SWR_THRESHOLD_MAX
    ? t
    : DEFAULT_SWR_THRESHOLD;
}

export function sameChoice(a: SweepAxisChoice, b: SweepAxisChoice): boolean {
  if (a.kind === "fixed" && b.kind === "fixed") return a.lo === b.lo && a.hi === b.hi;
  return a.kind === b.kind;
}
