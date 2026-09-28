// The extrapolated impedance Z∞ of a refinement ladder (AK#1781).
//
// ONE estimator, implemented twice and kept identical: here (the workbench)
// and in src/antennaknobs/zinf.py (the CLI), whose docstring is the spec —
// read it before changing anything below. In short: < 3 rungs →
// "insufficient"; last step ≤ 1e-6·|Z| → "converged"; the last two local
// slopes of log|ΔZ| on log x agreeing within 10 % (and not oscillating, and
// p in [0.25, 4]) → "asymptotic", with the observed order p and a
// least-squares fit of Z = Z∞ + C·x^−p through the last 3 rungs; otherwise
// "rough", first order from the last two rungs.
//
// The shared vectors in __tests__/fixtures/zinfVectors.json come from the
// Python implementation and gate both languages to 1e-12; keep the
// operation order below the same as the Python's.

export type ZInfStatus = "insufficient" | "converged" | "asymptotic" | "rough";

export type ZInfEstimate = {
  /** null only when status is "insufficient". */
  re: number | null;
  im: number | null;
  /** The observed order; set only when status is "asymptotic". */
  p: number | null;
  status: ZInfStatus;
};

export const CONVERGED_REL = 1e-6;
export const STRAIGHT_REL = 0.1;
export const P_MIN = 0.25;
export const P_MAX = 4.0;
export const P_THEORY = 1.0;

const INSUFFICIENT: ZInfEstimate = { re: null, im: null, p: null, status: "insufficient" };

function localSlope(d0: number, d1: number, x0: number, x1: number): number | null {
  if (!(d0 > 0 && d1 > 0)) return null;
  return -(Math.log(d1) - Math.log(d0)) / (Math.log(x1) - Math.log(x0));
}

function fitOrder(xs: readonly number[], ds: readonly number[]): number {
  const n = xs.length;
  const lx = xs.map((x) => Math.log(x));
  const ld = ds.map((d) => Math.log(d));
  let sx = 0;
  let sd = 0;
  for (let i = 0; i < n; i++) sx += lx[i];
  for (let i = 0; i < n; i++) sd += ld[i];
  const mx = sx / n;
  const md = sd / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (lx[i] - mx) * (ld[i] - md);
    den += (lx[i] - mx) * (lx[i] - mx);
  }
  return -(num / den);
}

function fitZinf(
  xs: readonly number[],
  re: readonly number[],
  im: readonly number[],
  p: number,
): [number, number] {
  let s0 = 0;
  let s1 = 0;
  let s2 = 0;
  let t0r = 0;
  let t0i = 0;
  let t1r = 0;
  let t1i = 0;
  for (let i = 0; i < xs.length; i++) {
    const u = Math.pow(xs[i], -p);
    s0 += 1;
    s1 += u;
    s2 += u * u;
    t0r += re[i];
    t0i += im[i];
    t1r += u * re[i];
    t1i += u * im[i];
  }
  const det = s0 * s2 - s1 * s1;
  return [(s2 * t0r - s1 * t1r) / det, (s2 * t0i - s1 * t1i) / det];
}

/** Z∞ of the ladder (x_k, re_k + j·im_k): the rule in zinf.py. */
export function zinfEstimate(
  x: readonly number[],
  re: readonly number[],
  im: readonly number[],
): ZInfEstimate {
  const m = re.length;
  if (x.length !== m || im.length !== m) {
    throw new Error(`x, re and im differ in length (${x.length}, ${m}, ${im.length})`);
  }
  if (m < 3) return INSUFFICIENT;
  for (let k = 0; k < m; k++) if (!(x[k] > 0)) return INSUFFICIENT;
  for (let k = 0; k < m - 1; k++) if (!(x[k + 1] > x[k])) return INSUFFICIENT;

  const dr: number[] = [];
  const di: number[] = [];
  const ds: number[] = [];
  for (let k = 0; k < m - 1; k++) {
    dr.push(re[k + 1] - re[k]);
    di.push(im[k + 1] - im[k]);
    ds.push(Math.hypot(dr[k], di[k]));
  }
  const lastRe = re[m - 1];
  const lastIm = im[m - 1];
  if (ds[m - 2] <= CONVERGED_REL * Math.hypot(lastRe, lastIm)) {
    return { re: lastRe, im: lastIm, p: null, status: "converged" };
  }

  const oscillating = dr[m - 2] * dr[m - 3] + di[m - 2] * di[m - 3] < 0;
  if (!oscillating && m >= 4) {
    const sa = localSlope(ds[m - 4], ds[m - 3], x[m - 4], x[m - 3]);
    const sb = localSlope(ds[m - 3], ds[m - 2], x[m - 3], x[m - 2]);
    if (
      sa != null &&
      sb != null &&
      Number.isFinite(sa) &&
      Number.isFinite(sb) &&
      Math.abs(sa - sb) <= STRAIGHT_REL * Math.abs((sa + sb) / 2)
    ) {
      const n = Math.min(3, m - 1);
      const p = fitOrder(x.slice(m - 1 - n, m - 1), ds.slice(m - 1 - n, m - 1));
      if (P_MIN <= p && p <= P_MAX) {
        const [zr, zi] = fitZinf(x.slice(m - 3), re.slice(m - 3), im.slice(m - 3), p);
        return { re: zr, im: zi, p, status: "asymptotic" };
      }
    }
  }

  const ratio = Math.pow(x[m - 1] / x[m - 2], P_THEORY);
  return {
    re: lastRe + (lastRe - re[m - 2]) / (ratio - 1),
    im: lastIm + (lastIm - im[m - 2]) / (ratio - 1),
    p: null,
    status: "rough",
  };
}

/** Per-feed Z∞: the estimator on each feed's complex column (one row per
 *  rung), one p per feed. */
export function feedwiseZinf(
  x: readonly number[],
  feedsZRe: readonly (readonly number[])[],
  feedsZIm: readonly (readonly number[])[],
): ZInfEstimate[] {
  const nFeeds = feedsZRe[0]?.length ?? 0;
  const out: ZInfEstimate[] = [];
  for (let fi = 0; fi < nFeeds; fi++) {
    out.push(
      zinfEstimate(
        x,
        feedsZRe.map((row) => row[fi]),
        feedsZIm.map((row) => row[fi]),
      ),
    );
  }
  return out;
}

/** The short suffix beside a Z∞ readout: "· p 0.98" when asymptotic,
 *  "· rough" when rough, nothing when converged. */
export function zinfSuffix(status: ZInfStatus | null | undefined, p: number | null | undefined): string {
  if (status === "asymptotic" && p != null) return ` · p ${p.toFixed(2)}`;
  if (status === "rough") return " · rough";
  return "";
}

// The reason beside "rough": the step, in the last FEED_MESH_WINDOW rungs,
// where the fed segment least follows the ladder's 1/x scaling (a feed wire
// whose count moves in steps of two, AK#1767). zinf.py's feed_mesh_step is
// the spec; the shared vectors gate both. It never changes the estimate.
export const FEED_MESH_WINDOW = 4;
export const FEED_MESH_TOL = 1.25;

function sameLength(a: number, b: number): boolean {
  return Math.abs(a - b) <= 1e-9 * Math.max(a, b);
}

/** Index k of the step x[k] → x[k+1] to name, or null: a jump (the length
 *  changed) before a held step, the first largest departure within each. */
export function feedMeshStep(x: readonly number[], fedLen: readonly number[]): number | null {
  const m = x.length;
  if (m < 2 || fedLen.length !== m) return null;
  const tol = Math.log(FEED_MESH_TOL);
  let bestJump: number | null = null;
  let jumpDev = tol;
  let bestHeld: number | null = null;
  let heldDev = tol;
  for (let k = Math.max(0, m - FEED_MESH_WINDOW); k < m - 1; k++) {
    const x0 = x[k];
    const x1 = x[k + 1];
    const l0 = fedLen[k];
    const l1 = fedLen[k + 1];
    if (!(x0 > 0 && x1 > x0 && l0 > 0 && l1 > 0)) return null;
    const dev = Math.abs(Math.log(l0 / l1) - Math.log(x1 / x0));
    if (sameLength(l0, l1)) {
      if (dev > heldDev) {
        bestHeld = k;
        heldDev = dev;
      }
    } else if (dev > jumpDev) {
      bestJump = k;
      jumpDev = dev;
    }
  }
  return bestJump ?? bestHeld;
}

/** The chart's short clause for a feedMeshStep hit at step k, e.g.
 *  ": fed segment 100.0→33.3 mm at N 65→95". */
export function feedMeshClause(
  x: readonly number[],
  fedLen: readonly number[],
  k: number,
): string {
  const l0 = fedLen[k] * 1000;
  const l1 = fedLen[k + 1] * 1000;
  const len = sameLength(l0, l1)
    ? `fixed at ${l0.toFixed(1)} mm`
    : `${l0.toFixed(1)}→${l1.toFixed(1)} mm`;
  return `: fed segment ${len} at N ${x[k]}→${x[k + 1]}`;
}
