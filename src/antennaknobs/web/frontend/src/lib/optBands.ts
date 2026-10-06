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

/** How many positions a band's marker trail keeps on the Smith chart: the
 *  head and the few before it, enough to see the motion and the settling. */
export const BAND_TRAIL_LEN = 6;

/** One band's live marker on the Smith chart during a band run (AK 0.97.1):
 *  its last few impedances, oldest first, each normalised to the band's own
 *  reference when drawn. `live` is false while the band's latest reading is
 *  null (an infinite SWR, a NaN Z): the marker is then not drawn. */
export type BandMark = {
  index: number;
  freq_mhz: number;
  z0_ohms: number;
  trail: { re: number; im: number }[];
  live: boolean;
};

/** Every band's marker, and the band the minimax is chasing (bright ring). */
export type BandMarks = { bands: BandMark[]; worst: number | null };

/** The minimal shape of a progress frame's band records. */
type BandReading = {
  index: number;
  freq_mhz: number;
  z0_ohms: number;
  z_re: number | null;
  z_im: number | null;
};

/** The markers after one progress frame. A band in the frame moves (its new
 *  Z appended to its trail, the oldest dropped past BAND_TRAIL_LEN); a band
 *  with a null Z stops drawing until a reading returns; a band absent from
 *  the frame (a sequential sub-step) keeps its last position. A frame with
 *  no `bands` (a single-frequency run) leaves the markers as they were. */
export function nextBandMarks(
  prev: BandMarks | null,
  frame: { bands?: BandReading[] | undefined; worst_band?: number | null | undefined },
): BandMarks | null {
  if (!frame.bands || frame.bands.length === 0) return prev;
  const byIndex = new Map((prev?.bands ?? []).map((b) => [b.index, b]));
  for (const r of frame.bands) {
    const old = byIndex.get(r.index);
    const ok =
      r.z_re != null && r.z_im != null && Number.isFinite(r.z_re) && Number.isFinite(r.z_im);
    let trail = old?.trail ?? [];
    if (ok) {
      const last = trail[trail.length - 1];
      if (!last || last.re !== r.z_re || last.im !== r.z_im) {
        trail = [...trail, { re: r.z_re as number, im: r.z_im as number }].slice(-BAND_TRAIL_LEN);
      }
    }
    byIndex.set(r.index, {
      index: r.index,
      freq_mhz: r.freq_mhz,
      z0_ohms: r.z0_ohms,
      trail,
      live: ok,
    });
  }
  const bands = [...byIndex.values()].sort((a, b) => a.index - b.index);
  const worst =
    frame.worst_band !== undefined ? (frame.worst_band ?? null) : (prev?.worst ?? null);
  return { bands, worst };
}
