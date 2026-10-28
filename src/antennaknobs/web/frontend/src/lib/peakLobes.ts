// Where a pattern's maximum is, when it is in more than one place (AK#2094).
//
// An antenna that is the same after a turn of 360°/k has k equal lobes: a
// dipole or SP3L's turnstile 2 (180° apart), a vertical on three radials 3,
// and a vertical on a full screen of radials is the same all the way round.
// A first-found rule names one of them by chance, so two readouts sampling
// the same pattern differently named different bearings (AC6LA, QRZ 1003328
// #214: "@ az 8°" against "@ az 6°" on the turnstile). Both readouts now list
// every lobe within PEAK_LOBE_TOL_DB of the maximum, each at the centre of its
// run, the rule the server's `far_field.azimuth_lobes` applies to the 3-D max.
// React-free, so the rule is tested alone.

import type { PatternMetrics } from "../components/charts/types";

/** NEC's printed resolution, so the readouts list the same lobes whichever
 *  engine drew the pattern (`far_field.PEAK_LOBE_TOL_DB`). */
export const PEAK_LOBE_TOL_DB = 0.01;

/** More lobes than this are listed as the first few and a count. */
export const MAX_LISTED_LOBES = 4;

/**
 * The centre of each run of samples within `tolDb` of the trace's maximum,
 * ascending. `wrap`: the angles go once round a circle (an azimuth ring), so a
 * run may cross 0°, and a trace within `tolDb` everywhere is omnidirectional:
 * the answer is empty. Unwrapped, a flat trace is one run, its centre.
 */
export function lobeCentresDeg(
  anglesDeg: readonly number[],
  dbi: readonly number[],
  wrap: boolean,
  tolDb: number = PEAK_LOBE_TOL_DB,
): number[] {
  let n = Math.min(anglesDeg.length, dbi.length);
  if (n === 0) return [];
  // A closed ring repeats its first direction at the end: count it once.
  if (wrap && n > 1 && Math.abs((anglesDeg[n - 1] - anglesDeg[0]) % 360) < 1e-9)
    n -= 1;
  let top = -Infinity;
  for (let i = 0; i < n; i++) top = Math.max(top, dbi[i]);
  const on = Array.from({ length: n }, (_, i) => dbi[i] >= top - tolDb);
  const firstOff = on.indexOf(false);
  if (firstOff < 0) return wrap ? [] : [(anglesDeg[0] + anglesDeg[n - 1]) / 2];

  const centres: number[] = [];
  const close = (first: number, last: number) => {
    const a0 = anglesDeg[first];
    let a1 = anglesDeg[last];
    if (wrap && a1 < a0) a1 += 360;
    const c = (a0 + a1) / 2;
    centres.push(wrap ? ((c % 360) + 360) % 360 : c);
  };
  // Start just after an off sample, so a wrapped run is never split in two.
  const start = wrap ? firstOff + 1 : 0;
  let runStart = -1;
  let prev = -1;
  for (let k = 0; k < n; k++) {
    const i = wrap ? (start + k) % n : k;
    if (on[i]) {
      if (runStart < 0) runStart = i;
      prev = i;
    } else if (runStart >= 0) {
      close(runStart, prev);
      runStart = -1;
    }
  }
  if (runStart >= 0) close(runStart, prev);
  return centres.sort((a, b) => a - b);
}

/** "az 7° · 187°"; "all az" for none (omnidirectional); past
 *  MAX_LISTED_LOBES, the first few and how many more. */
export function formatPeakAngles(anglesDeg: readonly number[], axis: "az" | "el"): string {
  if (anglesDeg.length === 0) return `all ${axis}`;
  const deg = (a: number) => `${axis === "az" ? Math.round(a) % 360 : Math.round(a)}°`;
  const shown = anglesDeg.slice(0, MAX_LISTED_LOBES).map(deg).join(" · ");
  const more = anglesDeg.length - MAX_LISTED_LOBES;
  return `${axis} ${shown}${more > 0 ? ` · +${more}` : ""}`;
}

/** The 3-D max's azimuths: the server's lobes (AK#2094), or the one bearing a
 *  server predating them sends. Empty: omnidirectional. */
export function maxAzimuthsDeg(m: PatternMetrics): number[] {
  return m.azimuth_lobes_deg ?? [m.azimuth_deg];
}

/** The bearing to aim an elevation cut at for the 3-D max: its first lobe, or
 *  null when every azimuth is the peak's (leave the cut where it is). */
export function maxBearingDeg(m: PatternMetrics): number | null {
  const lobes = maxAzimuthsDeg(m);
  return lobes.length ? Math.round(lobes[0]) % 360 : null;
}
