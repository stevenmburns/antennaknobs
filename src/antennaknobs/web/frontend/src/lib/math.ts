import { reflectionCoefficient } from "./format";

// |Γ| from Z = re + j·im referenced to z0. A thin wrapper over
// reflectionCoefficient's gMag (lib/format.ts) rather than a second copy of
// the formula — the Smith chart and the gamma/VSWR sweep charts (issue #700
// unit 5) must never disagree about what |Γ| is for a given Z.
export function gammaMagFromZ(re: number, im: number, z0: number): number {
  return reflectionCoefficient(re, im, z0).gMag;
}

// VSWR = (1+|Γ|)/(1-|Γ|) blows up as |Γ| → 1 (a dead open/short feed). A
// finite ceiling keeps that one sample from stretching a chart's y-axis
// into a straight line at the horizon; 99 matches formatSwr's own
// three-nines display cutoff (lib/format.ts) so "off the chart" means the
// same thing in both places.
export const VSWR_CEILING = 99;
export function vswrFromGammaMag(gMag: number): number {
  if (gMag >= 1) return VSWR_CEILING;
  return Math.min((1 + gMag) / (1 - gMag), VSWR_CEILING);
}

// S11 log-magnitude, 20·log₁₀|Γ| — the negative-dB convention every VNA
// (including the NanoVNA this app's users own) plots: 0 dB = total
// reflection, a good match is a downward dip. NOT the IEEE positive
// "return loss"; pick one sign convention and keep it. |Γ| = 0 is −∞ dB, so
// a floor keeps a perfect match plottable and its data-* readout finite;
// −60 dB (|Γ| = 0.001) is far below anything an antenna sweep resolves.
export const S11_DB_FLOOR = -60;
export function gammaDbFromMag(gMag: number): number {
  if (gMag <= 0) return S11_DB_FLOOR;
  return Math.max(20 * Math.log10(gMag), S11_DB_FLOOR);
}

// Richardson-style extrapolation Z(1/N) → Z(N→∞). Fits Z = a₀ + a₁·h + a₂·h²
// (h = 1/N) on the last `nLast` points via least squares and returns a₀.
// Quadratic gives a sane answer for O(1/N) limit (BSpline without
// enrichment) AND O(1/N^p) for p slightly above 1 — basis-cap, enrichment,
// etc. With ≤2 points we can't fit; return null.
export function richardsonExtrap(
  invN: number[],
  vals: number[],
  nLast = 5,
): number | null {
  const m = Math.min(nLast, invN.length);
  if (m < 3) return null;
  const start = invN.length - m;
  // Solve Ax = b for x = [a₀, a₁, a₂] using normal equations on the last m
  // points. m × 3 → 3 × 3 — small, no need for an LAPACK call.
  let s0 = 0, s1 = 0, s2 = 0, s3 = 0, s4 = 0;
  let t0 = 0, t1 = 0, t2 = 0;
  for (let i = start; i < invN.length; i++) {
    const h = invN[i];
    const y = vals[i];
    s0 += 1;
    s1 += h;
    s2 += h * h;
    s3 += h * h * h;
    s4 += h * h * h * h;
    t0 += y;
    t1 += y * h;
    t2 += y * h * h;
  }
  // 3x3 linear system: [[s0,s1,s2],[s1,s2,s3],[s2,s3,s4]] · [a0,a1,a2] = [t0,t1,t2]
  const m00 = s0, m01 = s1, m02 = s2;
  const m10 = s1, m11 = s2, m12 = s3;
  const m20 = s2, m21 = s3, m22 = s4;
  const det =
    m00 * (m11 * m22 - m12 * m21) -
    m01 * (m10 * m22 - m12 * m20) +
    m02 * (m10 * m21 - m11 * m20);
  if (Math.abs(det) < 1e-30) return null;
  const a0 =
    (t0 * (m11 * m22 - m12 * m21) -
      m01 * (t1 * m22 - m12 * t2) +
      m02 * (t1 * m21 - m11 * t2)) /
    det;
  return a0;
}

// Per-feed Richardson Z*. Each feed's series is the column of feedsZRe /
// feedsZIm (one row per sampled N value) at that feed index across all
// sampled N values; richardsonExtrap returns null until ≥3 points are in,
// so the diamonds light up the same time the primary one does.
export function feedwiseRichardson(
  invN: number[],
  feedsZRe: number[][],
  feedsZIm: number[][],
): { feedsRe: (number | null)[]; feedsIm: (number | null)[] } {
  const nFeeds = feedsZRe[0].length;
  const feedsRe: (number | null)[] = [];
  const feedsIm: (number | null)[] = [];
  for (let fi = 0; fi < nFeeds; fi++) {
    const re = feedsZRe.map((row) => row[fi]);
    const im = feedsZIm.map((row) => row[fi]);
    feedsRe.push(richardsonExtrap(invN, re));
    feedsIm.push(richardsonExtrap(invN, im));
  }
  return { feedsRe, feedsIm };
}

// Blend two #rrggbb colors; t=0 -> a, t=1 -> b. Used to warm the knob's value
// arc from --accent toward --hot as it nears max (an "energizing" cue).
export function mixHex(a: string, b: string, t: number): string {
  const ch = (s: string, i: number) => parseInt(s.slice(i, i + 2), 16);
  const r = Math.round(ch(a, 1) + (ch(b, 1) - ch(a, 1)) * t);
  const g = Math.round(ch(a, 3) + (ch(b, 3) - ch(a, 3)) * t);
  const bl = Math.round(ch(a, 5) + (ch(b, 5) - ch(a, 5)) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}
