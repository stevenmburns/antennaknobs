// Per-feed colors for multi-line Smith chart overlays. Feed 0 keeps the
// existing single-feed blue so single-feed geometries are visually
// unchanged; subsequent feeds use distinct hues that read well on the
// dark background. Indices beyond this list wrap, but that's only
// reachable on >4-feed geometries (none exist yet).
const FEED_COLORS: [number, number, number][] = [
  [118, 208, 255],  // blue (primary)
  [255, 196, 102],  // amber
  [140, 230, 140],  // green
  [255, 130, 200],  // pink
];

// Swatch colors for pinned far-field ghost overlays, themed via CSS vars —
// the dark theme's pastels are darker inks in light mode, where a 1px dashed
// pastel stroke vanishes on the white canvas. Distinct from the live lobe
// (orange) and the NEC overlay (cyan); they wrap past the 4th pin.
export const GHOST_COLOR_COUNT = 4;
// Fallbacks match the dark-theme values in styles.css.
export const GHOST_FALLBACK_RGB = [
  "140, 230, 140", // green
  "255, 130, 200", // pink
  "180, 160, 255", // violet
  "120, 220, 220", // teal
];
// "r, g, b" for a pin's color slot in the current theme, for canvas strokes.
// (The compare table instead inlines the CSS var so it rethemes live.)
export function ghostRgb(colorIdx: number): string {
  const i = colorIdx % GHOST_COLOR_COUNT;
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(`--plot-ghost-${i}-rgb`)
    .trim();
  return v || GHOST_FALLBACK_RGB[i];
}

export function feedColor(i: number, alpha = 0.85): string {
  const [r, g, b] = FEED_COLORS[i % FEED_COLORS.length];
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Sweep trail uses a darkened variant of each feed's primary color so the
// current-Z marker reads as "you are here" against a dimmer "trail". With
// two feeds at identical Z (e.g. the in-phase symmetric case) the two
// primary markers stack on top of each other but stay distinguishable from
// the sweep cloud underneath — without this they were indistinguishable.
export function feedSweepColor(i: number, alpha = 0.85): string {
  const [r, g, b] = FEED_COLORS[i % FEED_COLORS.length];
  const f = 0.55; // darken factor — empirically readable on the #0d1015 bg
  return `rgba(${Math.round(r * f)}, ${Math.round(g * f)}, ${Math.round(b * f)}, ${alpha})`;
}

// Plot colors are pulled from CSS custom properties so the <canvas>
// views theme from the same tokens as the DOM chrome. Fallbacks
// reproduce the original dark palette, so missing vars are harmless.
export function plotColors() {
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string, fb: string): string => {
    const val = cs.getPropertyValue(name).trim();
    return val || fb;
  };
  return {
    bg: v("--plot-bg", "#0d1015"),
    bgRgb: v("--plot-bg-rgb", "13, 16, 21"),
    grid: v("--plot-grid", "#2a313d"),
    axis: v("--plot-axis", "#3a4150"),
    axisFaint: v("--plot-axis-faint", "#23272f"),
    labelDim: v("--plot-label-dim", "#4a5160"),
    label: v("--plot-label", "#7b8493"),
    labelBright: v("--plot-label-bright", "#9aa3b2"),
    labelStrong: v("--plot-label-strong", "#cdd5e0"),
    centerMark: v("--plot-center-mark", "#5a6170"),
    spoke: v("--plot-spoke", "rgba(180, 140, 250, 0.7)"),
    lobeRgb: v("--plot-lobe-rgb", "255, 209, 102"),
    necRgb: v("--plot-nec-rgb", "110, 220, 255"),
    groundRgb: v("--plot-ground-rgb", "140, 110, 70"),
    envelopeRgb: v("--plot-envelope-rgb", "118, 208, 255"),
    feed: v("--plot-feed", "#ffd166"),
    // Measured-overlay locus (issue #595). Violet: unused elsewhere on the
    // Smith chart, so it never reads as another feed.
    measured: v("--plot-measured", "#b48cfa"),
  };
}

// Current-magnitude heatmap ramp, also CSS-driven. Read once and cached
// (currentColor runs per wire segment, so getComputedStyle must not be
// called in the loop). Fallbacks are the original cool->warm stops.
let _currentRampCache: [number, [number, number, number]][] | null = null;
export function currentRamp(): [number, [number, number, number]][] {
  if (_currentRampCache) return _currentRampCache;
  const cs = getComputedStyle(document.documentElement);
  const tri = (name: string, fb: [number, number, number]): [number, number, number] => {
    const s = cs.getPropertyValue(name).trim();
    if (!s) return fb;
    const p = s.split(",").map((n) => parseInt(n.trim(), 10));
    return p.length === 3 && p.every((n) => !Number.isNaN(n)) ? [p[0], p[1], p[2]] : fb;
  };
  _currentRampCache = [
    [0.0, tri("--plot-current-0", [40, 64, 96])],
    [0.25, tri("--plot-current-1", [60, 140, 200])],
    [0.5, tri("--plot-current-2", [118, 208, 255])],
    [0.75, tri("--plot-current-3", [255, 209, 102])],
    [1.0, tri("--plot-current-4", [255, 130, 80])],
  ];
  return _currentRampCache;
}

export function currentColor(t: number): string {
  // Cool → warm ramp: dim blue → cyan → yellow → orange.
  const stops = currentRamp();
  for (let i = 1; i < stops.length; i++) {
    const [t0, c0] = stops[i - 1];
    const [t1, c1] = stops[i];
    if (t <= t1) {
      const f = (t - t0) / (t1 - t0 || 1);
      const r = Math.round(c0[0] + (c1[0] - c0[0]) * f);
      const g = Math.round(c0[1] + (c1[1] - c0[1]) * f);
      const b = Math.round(c0[2] + (c1[2] - c0[2]) * f);
      return `rgb(${r},${g},${b})`;
    }
  }
  return "rgb(255,130,80)";
}
