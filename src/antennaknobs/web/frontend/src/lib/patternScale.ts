import { useCallback, useSyncExternalStore } from "react";

// The polar pattern charts' radial scale (AC6LA, 2026-11-02).
//
// "arrl" is the ARRL modified-logarithmic grid: r = R_max * 0.89^(-dB/3), dB
// measured down from the top of the scale. The first 3 dB step takes about a
// tenth of the radius and each later 3 dB step is 89 % of the one before, so
// the main lobe keeps its shape while sidelobes 20-30 dB down stay readable
// and -100 dB sits near the centre. "linear" is the scale the charts drew
// before: dBi linear in radius from a -20 dBi floor, which reads a null's
// depth directly but squashes everything below the floor onto the centre.
//
// Per browser, in localStorage, like the gear menu's other display choices:
// it is how you like to read a plot, not a property of the antenna. A module
// store (the zoOverride idiom), so every chart on the page agrees at once.

export type PatternScale = "arrl" | "linear";

export const PATTERN_SCALES: readonly PatternScale[] = ["arrl", "linear"];

export const PATTERN_SCALE_LABELS: Record<PatternScale, string> = {
  arrl: "ARRL",
  linear: "linear dB",
};

export const DEFAULT_PATTERN_SCALE: PatternScale = "arrl";

export const PATTERN_SCALE_KEY = "akb.patternScale.v1";

function isScale(v: unknown): v is PatternScale {
  return v === "arrl" || v === "linear";
}

// localStorage is user-editable: anything that is not a scale reads as the
// default.
function load(): PatternScale {
  try {
    const raw = localStorage.getItem(PATTERN_SCALE_KEY);
    return isScale(raw) ? raw : DEFAULT_PATTERN_SCALE;
  } catch {
    return DEFAULT_PATTERN_SCALE;
  }
}

let cached: PatternScale | null = null;
const listeners = new Set<() => void>();

/** The scale the charts draw with now. Also read outside React (the cut
 *  refinement planner), so it is a plain function as well as a hook. */
export function getPatternScale(): PatternScale {
  if (cached === null) cached = load();
  return cached;
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
    // Nothing mounted: the next mount re-reads storage (which also gives
    // each test a fresh read of whatever it put there).
    if (listeners.size === 0) cached = null;
  };
}

export function setPatternScale(scale: PatternScale): void {
  if (!isScale(scale)) return;
  cached = scale;
  try {
    // Sparse: the default is not written, so a browser that never touches
    // the setting follows a future change of default.
    if (scale === DEFAULT_PATTERN_SCALE) localStorage.removeItem(PATTERN_SCALE_KEY);
    else localStorage.setItem(PATTERN_SCALE_KEY, scale);
  } catch {
    /* storage disabled: the choice still holds for this page's life */
  }
  for (const l of listeners) l();
}

/** The polar charts' radial scale, and its setter. */
export function usePatternScale(): [PatternScale, (s: PatternScale) => void] {
  const scale = useSyncExternalStore(subscribe, getPatternScale, getPatternScale);
  const set = useCallback((s: PatternScale) => setPatternScale(s), []);
  return [scale, set];
}
