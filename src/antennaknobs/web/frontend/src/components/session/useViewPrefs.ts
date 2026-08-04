import { useCallback, useMemo, useSyncExternalStore } from "react";
import { VIEW_META, VIEWS, type View, type ViewMeta } from "../../lib/view";

// The desktop view preferences: which views are PINNED (resident in the
// thumbstrip) and which the user has already been shown in the picker.
// Unit 2 of docs/plan-view-rail-scaling.md.
//
// Global, not per-design: every design has every view, and the user's
// watching habits ("I care about VSWR and the pattern") span designs, so a
// per-design pin set would reshuffle the workspace on every catalog switch.
// Global also means every open session tab must agree, which is why the state
// lives in a module store read through useSyncExternalStore (the same idiom
// hooks.ts uses for media queries) rather than in per-component useState —
// two mounted sessions holding private copies would drift and race on the key.

// Six pins ⇒ five rail thumbs ⇒ ~96 px thumbs on a 720 px column, which is
// above the legibility floor with margin (the column math is in the plan's
// context table). Above six the rail is smudges again, so this is a hard cap,
// not a nudge.
export const PIN_CAP = 6;

export const VIEW_PREFS_KEY = "akb.viewPrefs.v1";

// What `seen` is seeded with on a first run: the roster as it stood when the
// picker shipped, written out rather than derived from VIEWS. Seeding from the
// live roster would mark every FUTURE view as already-seen for anyone whose
// first visit happens after that view ships — the NEW badge would never fire
// for the users it exists for. A literal makes the badge mean "added after the
// picker shipped", which is what the user reads it as.
const SEEN_SEED: View[] = ["antenna", "azimuth", "elevation", "smith", "schematic"];

// The persisted record. Fields are independent and each is optional on read,
// so unit 3 can add `layout: "rail" | "grid"` by extending this type and the
// writer — no v2 key, and a build that predates a field simply ignores it.
type ViewPrefs = {
  pinned: View[];
  seen: View[];
};

const KNOWN = new Set<string>(VIEWS.map((v) => v.id));

const defaultPins = (): View[] =>
  VIEWS.filter((v) => v.defaultPinned)
    .map((v) => v.id)
    .slice(0, PIN_CAP);

// localStorage is user-editable and outlives roster changes, so nothing read
// back is trusted: non-arrays become empty, ids we no longer ship are dropped,
// duplicates collapse (a duplicate would render two rail thumbs of one view).
function sanitizeIds(raw: unknown): View[] {
  if (!Array.isArray(raw)) return [];
  const out: View[] = [];
  for (const v of raw) {
    if (typeof v === "string" && KNOWN.has(v) && !out.includes(v as View)) {
      out.push(v as View);
    }
  }
  return out;
}

function loadPrefs(): ViewPrefs {
  try {
    const raw = localStorage.getItem(VIEW_PREFS_KEY);
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        const rec = parsed as Record<string, unknown>;
        // Clamp to the cap on the way in too: the cap can shrink between
        // releases, and the picker's disabled dots can only refuse NEW pins.
        const pinned = sanitizeIds(rec.pinned).slice(0, PIN_CAP);
        const seen = sanitizeIds(rec.seen);
        // Everything surviving sanitisation was garbage ⇒ treat the record as
        // corrupt rather than honour an empty rail, which is never what a user
        // meant and leaves no visible way back.
        if (pinned.length > 0) {
          return { pinned, seen: seen.length > 0 ? seen : SEEN_SEED };
        }
      }
    }
  } catch {
    /* corrupt JSON or storage disabled — the defaults below are the answer */
  }
  return { pinned: defaultPins(), seen: SEEN_SEED };
}

// --- module store ------------------------------------------------------------

let cached: ViewPrefs | null = null;
const listeners = new Set<() => void>();

// useSyncExternalStore compares snapshots by identity, so this must hand back
// the SAME object until something actually changes — hence the cache.
function getSnapshot(): ViewPrefs {
  if (!cached) cached = loadPrefs();
  return cached;
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
    // Nothing is mounted any more, so drop the cache and let the next mount
    // re-read storage. In the app that only happens before the first session
    // mounts (sessions never all unmount); in tests it makes every mount a
    // fresh read of whatever the test put in localStorage.
    if (listeners.size === 0) cached = null;
  };
}

function update(next: ViewPrefs): void {
  cached = next;
  try {
    localStorage.setItem(VIEW_PREFS_KEY, JSON.stringify(next));
  } catch {
    /* storage disabled — the in-memory prefs still work for this session,
       exactly as App.tsx's theme toggle degrades */
  }
  for (const l of listeners) l();
}

// --- pure helpers the UI and the key cycler share ----------------------------

// ArrowUp/Down walks `pinned ∪ {active}`: a peeked view (active but unpinned)
// joins the cycle transiently at the end so the arrows can never strand you on
// a view they cannot leave. The full roster stays picker-only, which is the
// point — cycling is short by construction.
export function cycleOrder(pinned: View[], active: View): View[] {
  return pinned.includes(active) ? pinned : [...pinned, active];
}

// Why a pin dot is inert, or null when it is live — the picker shows this as
// the dot's tooltip. togglePin enforces the same two rules itself: the dots
// are the affordance, these are the invariant.
export function pinBlockedReason(pinned: View[], id: View): string | null {
  if (pinned.includes(id)) {
    // A floor of one keeps the stored set a fixed point of loadPrefs, which
    // reads an empty pinned list as corruption and hands back the defaults.
    return pinned.length <= 1 ? "Keep at least one view pinned" : null;
  }
  return pinned.length >= PIN_CAP ? "Unpin a view first" : null;
}

export function useViewPrefs() {
  const prefs = useSyncExternalStore(subscribe, getSnapshot);
  const { pinned, seen } = prefs;

  // Views the user has never been offered. Seeded (not empty) on a first run,
  // so the badge only ever fires for views added after the picker shipped.
  const newIds = useMemo(
    () => new Set(VIEWS.filter((v) => !seen.includes(v.id)).map((v) => v.id)),
    [seen],
  );

  // The rail: pinned minus the active view. When the active view is unpinned
  // (a peek) nothing is subtracted, so the rail shows every pin — peek costs
  // no pin slot and displaces no thumb.
  const railViews = useCallback(
    (active: View): ViewMeta[] =>
      pinned.filter((id) => id !== active).map((id) => VIEW_META[id]),
    [pinned],
  );

  // Callbacks read the store rather than close over `pinned`, so a stale
  // handler (a popover rendered before someone else's pin landed) still
  // toggles against current truth.
  const togglePin = useCallback((id: View) => {
    const cur = getSnapshot();
    if (pinBlockedReason(cur.pinned, id)) return;
    const pins = cur.pinned.includes(id)
      ? cur.pinned.filter((v) => v !== id)
      : // Pin order is order-pinned; no drag-to-reorder in v1.
        [...cur.pinned, id];
    update({ ...cur, pinned: pins });
  }, []);

  // Opening the picker is what "you have now been shown the roster" means.
  // No-ops when nothing is new, so the snapshot identity (and every memo
  // hanging off it) survives an open.
  const markRosterSeen = useCallback(() => {
    const cur = getSnapshot();
    const missing = VIEWS.map((v) => v.id).filter((id) => !cur.seen.includes(id));
    if (missing.length === 0) return;
    update({ ...cur, seen: [...cur.seen, ...missing] });
  }, []);

  return { pinned, seen, newIds, railViews, togglePin, markRosterSeen };
}
