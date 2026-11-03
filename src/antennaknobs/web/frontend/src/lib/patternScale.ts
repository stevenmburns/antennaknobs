import { useCallback, useSyncExternalStore } from "react";

// The polar pattern charts' radial scale (AC6LA, 2026-11-02/03).
//
// "arrl" and "eznec" are the same modified-logarithmic radius,
// r = R_max * 0.89^(-dB/3), dB down from the top of the scale: the first 3 dB
// step takes about a tenth of the radius and each later 3 dB step is 89 % of
// the one before, so the main lobe keeps its shape while sidelobes 20-30 dB
// down stay readable. They differ only in their rings (lib/refine.ts
// cutRings): the ARRL Antenna Book's, with a -3 dB half-power ring, or
// EZNEC's. "linear" is the scale the charts drew before: dBi linear in radius
// from a -20 dBi floor, which reads a null's depth directly but squashes
// everything below the floor onto the centre.
//
// The default comes from settings.toml's [pattern_chart] scale (the server
// validates it; "arrl" when the file says nothing), and a choice made in the
// gear menu is remembered in this browser over it: how you like to read a
// plot, not a property of the antenna. A module store (the zoOverride
// idiom), so every chart on the page agrees at once.

export type PatternScale = "arrl" | "eznec" | "linear";

export const PATTERN_SCALES: readonly PatternScale[] = ["arrl", "eznec", "linear"];

export const PATTERN_SCALE_LABELS: Record<PatternScale, string> = {
  arrl: "ARRL",
  eznec: "EZNEC",
  linear: "linear dB",
};

/** The built-in default, before settings.toml says otherwise. */
export const DEFAULT_PATTERN_SCALE: PatternScale = "arrl";

export const PATTERN_SCALE_KEY = "akb.patternScale.v1";

export function isPatternScale(v: unknown): v is PatternScale {
  return v === "arrl" || v === "eznec" || v === "linear";
}

/** The two scales drawn on the modified-log radius (their rings differ). */
export function isLogScale(scale: PatternScale): boolean {
  return scale !== "linear";
}

// The startup default: settings.toml's, once the page has read it.
let startDefault: PatternScale = DEFAULT_PATTERN_SCALE;

// localStorage is user-editable: anything that is not a scale reads as no
// browser choice, so the startup default applies.
function load(): PatternScale {
  try {
    const raw = localStorage.getItem(PATTERN_SCALE_KEY);
    return isPatternScale(raw) ? raw : startDefault;
  } catch {
    return startDefault;
  }
}

let cached: PatternScale | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  for (const l of listeners) l();
}

/** The scale the charts draw with now. Also read outside React (the cut
 *  refinement planner, the settings save), so it is a plain function as well
 *  as a hook. */
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

/** The settings file's default, from the served startup settings. A browser
 *  that has made its own choice keeps it. */
export function setPatternScaleDefault(scale: PatternScale): void {
  if (!isPatternScale(scale) || scale === startDefault) return;
  startDefault = scale;
  cached = load();
  notify();
}

/** The gear menu's choice. Stored in this browser only when it differs from
 *  the startup default, so a browser that never chose follows the file. */
export function setPatternScale(scale: PatternScale): void {
  if (!isPatternScale(scale)) return;
  cached = scale;
  try {
    if (scale === startDefault) localStorage.removeItem(PATTERN_SCALE_KEY);
    else localStorage.setItem(PATTERN_SCALE_KEY, scale);
  } catch {
    /* storage disabled: the choice still holds for this page's life */
  }
  notify();
}

/** The polar charts' radial scale, and its setter. */
export function usePatternScale(): [PatternScale, (s: PatternScale) => void] {
  const scale = useSyncExternalStore(subscribe, getPatternScale, getPatternScale);
  const set = useCallback((s: PatternScale) => setPatternScale(s), []);
  return [scale, set];
}
