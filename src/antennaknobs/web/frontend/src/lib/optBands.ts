// AK#1901: the band list's pure helpers (the editor is OptBands.tsx).

/** The server's cap on a band list (AK#1901). */
export const MAX_OPT_BANDS = 8;

/** The text for a band reading that is not there: the server's null, which
 *  stands for a non-finite value (an infinite SWR, a NaN Z). */
export const NO_READING = "no reading";

export const fmtFreq = (f: number) => String(Number(f.toPrecision(7)));

/** A frequency the user typed, or the reason it is refused. */
export function parseBandFreq(
  text: string,
  existing: number[],
): { freq: number } | { error: string } {
  const t = text.trim();
  const v = t === "" ? NaN : Number(t);
  if (!Number.isFinite(v) || v <= 0) {
    return { error: "a band is a frequency in MHz greater than 0" };
  }
  if (existing.includes(v)) return { error: `${fmtFreq(v)} MHz is already a band` };
  if (existing.length >= MAX_OPT_BANDS) {
    return { error: `at most ${MAX_OPT_BANDS} bands` };
  }
  return { freq: v };
}
