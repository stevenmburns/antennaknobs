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

// Blend two #rrggbb colors; t=0 -> a, t=1 -> b. Used to warm the knob's value
// arc from --accent toward --hot as it nears max (an "energizing" cue).
export function mixHex(a: string, b: string, t: number): string {
  const ch = (s: string, i: number) => parseInt(s.slice(i, i + 2), 16);
  const r = Math.round(ch(a, 1) + (ch(b, 1) - ch(a, 1)) * t);
  const g = Math.round(ch(a, 3) + (ch(b, 3) - ch(a, 3)) * t);
  const bl = Math.round(ch(a, 5) + (ch(b, 5) - ch(a, 5)) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}
