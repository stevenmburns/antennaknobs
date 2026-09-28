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

// Z∞ (the extrapolated N→∞ impedance) lives in lib/zinf.ts: one estimator,
// shared with the CLI (AK#1781).

// Blend two #rrggbb colors; t=0 -> a, t=1 -> b. Used to warm the knob's value
// arc from --accent toward --hot as it nears max (an "energizing" cue).
export function mixHex(a: string, b: string, t: number): string {
  const ch = (s: string, i: number) => parseInt(s.slice(i, i + 2), 16);
  const r = Math.round(ch(a, 1) + (ch(b, 1) - ch(a, 1)) * t);
  const g = Math.round(ch(a, 3) + (ch(b, 3) - ch(a, 3)) * t);
  const bl = Math.round(ch(a, 5) + (ch(b, 5) - ch(a, 5)) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}
