// Escape hatches for the adaptive-resolution machinery (issue #744).
//
// The sampling constants (base grid size, refinement budgets, the stop
// tolerance) are deliberately NOT gear-menu settings: they'd need
// explanation, layout and persistence for something that should never be
// touched in normal use — the one common adjustment ("this design is too
// heavy") is the adaptive-resolution toggle. But the day a difficult
// design DOES show up, changing them must not require a rebuild — so each
// constant reads a localStorage override once at module load:
//
//   localStorage.setItem("antennaknobs.sweepBaseN", "31");  // then reload
//
// Read-once is the contract: these parameterise module-scope constants and
// mid-session changes would desynchronise planner and transport. If an
// override earns its keep on a real design, promote it to a proper setting.

/** Positive-integer override, clamped to [1, max]; the fallback on any
 *  absent/garbage value. `max` guards the server-side caps (MAX_SWEEP_POINTS,
 *  _CUT_MAX_ANGLES) from a fat-fingered exponent. */
export function tunedInt(key: string, fallback: number, max: number): number {
  const raw =
    typeof localStorage === "undefined" ? null : localStorage.getItem(key);
  if (raw === null) return fallback;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 1 ? Math.min(Math.floor(n), max) : fallback;
}

/** Positive-float override with the same contract. */
export function tunedFloat(key: string, fallback: number): number {
  const raw =
    typeof localStorage === "undefined" ? null : localStorage.getItem(key);
  if (raw === null) return fallback;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}
