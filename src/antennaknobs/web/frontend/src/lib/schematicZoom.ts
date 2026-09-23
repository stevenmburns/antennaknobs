// Sizing helpers for the schematic panel (AK#1682) — see SchematicPanel.tsx.

/** Upward limit on the fit scale: enough to fill a stage with a small
 *  chain, not enough to turn 10 pt labels into a poster. */
export const FIT_CAP = 1.25;
/** The explicit zoom ladder, in multiples of natural size. */
export const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4] as const;

/** The drawing's natural CSS size in px, from schemdraw's pt width/height
 *  attributes (1 pt = 4/3 px). Null when the markup carries none — the
 *  panel then fits without a cap rather than guessing. */
export function naturalSize(svg: string): { w: number; h: number } | null {
  const tag = /<svg\b[^>]*>/.exec(svg)?.[0];
  if (!tag) return null;
  const read = (attr: string): number | null => {
    const m = new RegExp(`\\b${attr}="([\\d.]+)(pt|px)?"`).exec(tag);
    if (!m) return null;
    const v = parseFloat(m[1]);
    return m[2] === "px" ? v : (v * 4) / 3;
  };
  const w = read("width");
  const h = read("height");
  return w && h ? { w, h } : null;
}

/** The next zoom step above (dir = 1) or below (dir = −1) `current`. From
 *  fit, `current` is the scale fit is drawing at, so the first press moves
 *  one step from what is on screen rather than jumping to a fixed level. */
export function stepZoom(current: number, dir: 1 | -1): number {
  if (dir > 0) {
    return ZOOM_STEPS.find((z) => z > current + 1e-6) ?? ZOOM_STEPS[ZOOM_STEPS.length - 1];
  }
  const below = ZOOM_STEPS.filter((z) => z < current - 1e-6);
  return below.length ? below[below.length - 1] : ZOOM_STEPS[0];
}
