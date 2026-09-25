import { useCallback, useSyncExternalStore } from "react";

// The optimizer's reference impedance, per design (AK#1735).
//
// A design names its own Zo — `ui_params["target_z0"]`, a `.ssn` Generator's
// Zo, 2 × 50 Ω for a two-element array — and the server reports it on every
// response as `design_z0_ohms`. The gear menu's Zo field sets an OVERRIDE of
// it, sent as the request's `z0_ohms`; everything that measures a match
// (the SWR readout, the Smith chart's centre, the VSWR / |Γ| sweeps, an swr or
// match_z0 optimize run, the drag tracker) then measures against it.
//
// Where it lives, and why: per design, in this browser's localStorage. Not in
// settings.toml — that file holds where the workbench STARTS (switches,
// ground, solver slots), is never written on the hosted app, and has no
// per-design table; a design's reference is not a startup default. Per design
// because the reference belongs to the antenna: a 75 Ω design stays 75 Ω when
// you come back to it, and switching to another design does not carry it
// over. Sparse, like the settings file's save: only an override that differs
// from the design's own value is stored, so a design whose file later names a
// new Zo is not pinned to a stale copy of its old one.
//
// A module store (the useViewPrefs idiom), so two sessions open on the same
// design agree on its Zo instead of racing on the key.

export const ZO_STORAGE_KEY = "akb.optimizerZo.v1";

/** A usable reference impedance: a finite number of ohms, greater than 0. */
export function isValidZo(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v) && v > 0;
}

/** The field's text as a Zo, or null when it is not one. Strict: "75 ohm" or
 *  "1e400" is refused, never read as a prefix or clamped. */
export function parseZo(text: string): number | null {
  const t = text.trim();
  if (t === "") return null;
  const v = Number(t);
  return isValidZo(v) ? v : null;
}

type ZoMap = Readonly<Record<string, number>>;

// localStorage is user-editable, so nothing read back is trusted: an entry
// that is not a valid Zo is dropped on its own, and a record that is not an
// object reads as "no overrides".
function load(): ZoMap {
  try {
    const raw = localStorage.getItem(ZO_STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: Record<string, number> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (isValidZo(v)) out[k] = v;
    }
    return out;
  } catch {
    return {};
  }
}

let cached: ZoMap | null = null;
const listeners = new Set<() => void>();

function getSnapshot(): ZoMap {
  if (!cached) cached = load();
  return cached;
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
    // Nothing mounted: the next mount re-reads storage (which is also what
    // gives each test a fresh read of whatever it put there).
    if (listeners.size === 0) cached = null;
  };
}

/** Set (a valid Zo) or clear (null) the override for one design. */
export function setZoOverride(geometry: string, zo: number | null): void {
  const next: Record<string, number> = { ...getSnapshot() };
  if (zo === null) delete next[geometry];
  else if (isValidZo(zo)) next[geometry] = zo;
  else return;
  cached = next;
  try {
    if (Object.keys(next).length === 0) localStorage.removeItem(ZO_STORAGE_KEY);
    else localStorage.setItem(ZO_STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* storage disabled — the override still holds for this page's life */
  }
  for (const l of listeners) l();
}

/** This design's Zo override (null = the design's own), and its setter. */
export function useZoOverride(
  geometry: string,
): [number | null, (zo: number | null) => void] {
  const map = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const set = useCallback(
    (zo: number | null) => setZoOverride(geometry, zo),
    [geometry],
  );
  return [map[geometry] ?? null, set];
}
