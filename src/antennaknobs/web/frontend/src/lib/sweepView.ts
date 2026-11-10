// The SWR / S11 charts' frequency zoom (see SweepChart.tsx). Pure math, kept
// out of the component as lib/smithView.ts is, so the invariants — the
// frequency under the cursor stays put, the view never leaves the sweep, it
// cannot narrow past the minimum span — are testable without a canvas.
//
// A view is the visible frequency window in MHz, or null for the whole
// sweep. It is stored in absolute MHz rather than as a fraction of the span,
// so a re-solve that keeps the span keeps the window exactly, and one that
// moves the span clamps it (clampView) instead of sliding it along.

export type FreqSpan = { lo: number; hi: number };

/** The visible window, or null: the whole sweep. */
export type SweepView = FreqSpan | null;

export const FULL_VIEW: SweepView = null;

/** The narrowest view is the sweep's span / 1000. The hosted instance solves
 *  at most 500 points across a sweep (MAX_SWEEP_POINTS), so at 1000× even the
 *  densest base grid puts about one interval across the view; past that the
 *  zoom only magnifies the straight line between two samples. "Sweep this
 *  span" is how to look closer: it re-solves over the window. Relative, not a
 *  fixed kHz: the 2200 m band is 2.1 kHz wide, a 70 cm sweep tens of MHz. */
export const SWEEP_ZOOM_MAX = 1000;

/** A band click leaves this fraction of the band's width either side, so its
 *  edges (and the curve crossing them) are not drawn on the frame. */
export const BAND_MARGIN = 0.1;

// A view within this fraction of the whole span IS the whole span: a pinch
// that ends a hair short of full must not leave a "Reset zoom" chip behind.
const FULL_TOL = 1e-3;

const width = (s: FreqSpan) => s.hi - s.lo;

/** The view kept inside the sweep: no narrower than span / SWEEP_ZOOM_MAX,
 *  shifted (not cut) back inside where it overhangs an end, and null when it
 *  is the whole span. A span with no width has no zoom. */
export function clampView(v: FreqSpan, span: FreqSpan): SweepView {
  const full = width(span);
  if (!(full > 0) || !Number.isFinite(v.lo) || !Number.isFinite(v.hi)) return null;
  const w = Math.max(Math.abs(width(v)), full / SWEEP_ZOOM_MAX);
  if (w >= full * (1 - FULL_TOL)) return null;
  const c = (v.lo + v.hi) / 2;
  let lo = c - w / 2;
  let hi = c + w / 2;
  if (lo < span.lo) {
    lo = span.lo;
    hi = lo + w;
  } else if (hi > span.hi) {
    hi = span.hi;
    lo = hi - w;
  }
  return { lo, hi };
}

/** The window drawn: the view clamped to the sweep, else the sweep. */
export function visibleSpan(view: SweepView, span: FreqSpan): FreqSpan {
  return (view && clampView(view, span)) ?? span;
}

export function isZoomed(view: SweepView, span: FreqSpan): boolean {
  return view !== null && clampView(view, span) !== null;
}

/** Zoom by `factor` (> 1 in) about the frequency `at`, which stays where it
 *  is on the axis — unless the result would overhang an end of the sweep,
 *  where the window is shifted back inside and the end wins. */
export function zoomAbout(view: SweepView, factor: number, at: number, span: FreqSpan): SweepView {
  const v = visibleSpan(view, span);
  const full = width(span);
  if (!(full > 0) || !(factor > 0)) return view;
  const a = Math.min(v.hi, Math.max(v.lo, at));
  const w = Math.min(full, Math.max(full / SWEEP_ZOOM_MAX, width(v) / factor));
  const t = (a - v.lo) / width(v);
  const lo = a - t * w;
  return clampView({ lo, hi: lo + w }, span);
}

/** Move the window by `df` MHz (a one-finger drag once zoomed). */
export function panBy(view: SweepView, df: number, span: FreqSpan): SweepView {
  if (view === null) return null;
  const v = visibleSpan(view, span);
  return clampView({ lo: v.lo + df, hi: v.hi + df }, span);
}

/** A ham band's window: the band plus BAND_MARGIN of its width each side,
 *  cut to the sweep (a band the sweep only half covers shows that half). */
export function bandView(band: FreqSpan, span: FreqSpan, margin = BAND_MARGIN): SweepView {
  const m = margin * width(band);
  return clampView(
    { lo: Math.max(span.lo, band.lo - m), hi: Math.min(span.hi, band.hi + m) },
    span,
  );
}

/** The window a drag from f0 to f1 selects, either direction. */
export function dragView(f0: number, f1: number, span: FreqSpan): SweepView {
  return clampView(
    { lo: Math.max(span.lo, Math.min(f0, f1)), hi: Math.min(span.hi, Math.max(f0, f1)) },
    span,
  );
}

/** The values of a sampled curve that are drawn inside [lo, hi]: the samples
 *  there, plus the curve's height where it crosses each edge (interpolated
 *  between the straddling samples). The edges matter: a narrow view between
 *  two samples has no sample in it, and its line still has a height. */
export function visibleValues(xs: readonly number[], ys: readonly number[], lo: number, hi: number): number[] {
  const out: number[] = [];
  const n = Math.min(xs.length, ys.length);
  const at = (f: number) => {
    for (let i = 1; i < n; i++) {
      const x0 = xs[i - 1];
      const x1 = xs[i];
      if ((x0 <= f && f <= x1) || (x1 <= f && f <= x0)) {
        if (x1 === x0) return ys[i];
        return ys[i - 1] + ((f - x0) / (x1 - x0)) * (ys[i] - ys[i - 1]);
      }
    }
    return null;
  };
  for (const edge of [lo, hi]) {
    const v = at(edge);
    if (v !== null && Number.isFinite(v)) out.push(v);
  }
  for (let i = 0; i < n; i++) if (xs[i] >= lo && xs[i] <= hi) out.push(ys[i]);
  return out;
}

// Decimal places of MHz that tell a window's ends apart: kHz (3) down to a
// 10 kHz window, one more per decade narrower (the 2200 m band's 2.1 kHz
// at its minimum span is a few Hz wide).
function viewDigits(v: FreqSpan): number {
  const w = width(v);
  return w > 0 ? Math.max(3, Math.ceil(-Math.log10(w)) + 1) : 3;
}

/** The window as the zoom chip reads it. */
export function formatView(v: FreqSpan): string {
  const d = viewDigits(v);
  return `${v.lo.toFixed(d)}–${v.hi.toFixed(d)} MHz`;
}

/** The window as the chip reads it, as numbers: what "Sweep this span"
 *  sweeps, so the range boxes then show the figures the chip showed. */
export function roundView(v: FreqSpan): FreqSpan {
  const d = viewDigits(v);
  return { lo: Number(v.lo.toFixed(d)), hi: Number(v.hi.toFixed(d)) };
}
