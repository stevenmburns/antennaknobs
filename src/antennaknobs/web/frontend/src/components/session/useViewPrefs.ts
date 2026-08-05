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

// Unit 3 of docs/plan-view-rail-scaling.md: the desktop stage's two layout
// presets over the same pinned set. "rail" is today's primary+thumbstrip;
// "grid" is equal cells over the first GRID_CELL_CAP pins. Exported so
// components (the segmented control, useViewState) share one type instead of
// re-deriving the string union.
export type Layout = "rail" | "grid";

// The persisted record. Fields are independent and each is optional on read,
// so a field can be added by extending this type and the writer — no v2 key,
// and a build that predates a field simply ignores it. `layout` (unit 3)
// is also optional on WRITE: update() below omits it entirely while it's
// "rail" (the default), so a session that never touches layout persists the
// exact `{pinned, seen}` shape unit 2 shipped — see the exact-keys assertion
// in useViewPrefs.test.tsx, which this deliberately keeps passing unedited.
type ViewPrefs = {
  pinned: View[];
  seen: View[];
  layout: Layout;
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

// Anything other than the literal "grid" reads as "rail" — an absent field
// (pre-unit-3 storage or a rail session that never wrote it, see the type's
// comment), a wrong type, or hand-edited garbage. A bad layout does not
// condemn the whole record the way an empty `pinned` does: the other two
// fields are still perfectly good, so only this one falls back.
function sanitizeLayout(raw: unknown): Layout {
  return raw === "grid" ? "grid" : "rail";
}

// What loadPrefs falls back to on any of: missing key, corrupt JSON, wrong
// shape, or an empty pin set post-sanitisation.
function defaultPrefs(): ViewPrefs {
  return { pinned: defaultPins(), seen: SEEN_SEED, layout: "rail" };
}

// Parses and validates a raw stored string exactly as loadPrefs does, but
// without touching localStorage — shared by the initial load (below) and by
// the `storage` listener (further down), so a value ARRIVING from another
// window is held to the same distrust as a value read from this window's own
// storage: nothing surviving sanitisation ⇒ null, meaning "not usable",
// never a thrown error and never a partially-applied record.
function parseStoredPrefs(raw: string): ViewPrefs | null {
  try {
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
        return {
          pinned,
          seen: seen.length > 0 ? seen : SEEN_SEED,
          layout: sanitizeLayout(rec.layout),
        };
      }
    }
  } catch {
    /* corrupt JSON */
  }
  return null;
}

function loadPrefs(): ViewPrefs {
  try {
    const raw = localStorage.getItem(VIEW_PREFS_KEY);
    if (raw) {
      const parsed = parseStoredPrefs(raw);
      if (parsed) return parsed;
    }
  } catch {
    /* storage disabled — the defaults below are the answer */
  }
  return defaultPrefs();
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
    // Sparse write: `layout` joins the JSON only when it is not the default
    // — JSON.stringify drops a key whose value is `undefined`. A pin/unpin
    // that never touches layout (the common case, and every case before
    // unit 3) writes exactly `{pinned, seen}`, so existing stored records
    // and the pre-unit-3 test fixture stay byte-shaped as before.
    localStorage.setItem(
      VIEW_PREFS_KEY,
      JSON.stringify({
        pinned: next.pinned,
        seen: next.seen,
        layout: next.layout === "rail" ? undefined : next.layout,
      }),
    );
  } catch {
    /* storage disabled — the in-memory prefs still work for this session,
       exactly as App.tsx's theme toggle degrades */
  }
  for (const l of listeners) l();
}

// A `storage` event fires in every OTHER window/tab sharing this origin the
// moment localStorage actually changes there — never in the window that
// wrote it, and never for a write that doesn't change the value (MDN
// StorageEvent). Sessions in the SAME window already share `cached` and
// `listeners` directly (that's the whole module-store idiom above); this is
// the one signal a second browser WINDOW gets, which is what #716 asks for —
// #700 shipped the same-window half and left this as "converges on reload".
//
// Registered once, at module scope, rather than per hook mount: every mount
// already shares the one `listeners` Set, so a listener per mount would just
// be N redundant copies of the same dispatch. And unlike `listeners`, there
// is no "last one out" moment to remove it at — a store with zero mounted
// hooks is a normal, valid state (see `subscribe`'s comment: `cached` just
// gets dropped and re-read on the next mount), not a teardown signal.
function handleStorage(event: StorageEvent): void {
  // Ignore writes to any other key. `event.key === null` is the browser's
  // signal for `localStorage.clear()`, which did clear this key too, so it
  // falls through to the same handling as an explicit removal below.
  if (event.key !== null && event.key !== VIEW_PREFS_KEY) return;

  // A null newValue means the key was removed (or storage.clear() ran) in
  // the other window — the same situation loadPrefs sees as "nothing on
  // disk", so it gets the same answer: the defaults.
  const next = event.newValue === null ? defaultPrefs() : parseStoredPrefs(event.newValue);

  // A corrupt or malformed value from another window is trusted no more than
  // one read from OUR OWN storage on load: ignore it and keep whatever this
  // window already has, rather than crashing or clobbering good state with
  // garbage.
  if (!next) return;

  // Deliberately does NOT call update(): this window did not originate the
  // change, so writing it back to localStorage here would only ever echo the
  // value already sitting there. An identical write fires no further
  // `storage` event (browsers dedupe on value), so it would be harmless, but
  // it is also pure overhead and one more writer that could race a genuine
  // write arriving from a THIRD window — simplest is to just not.
  cached = next;
  for (const l of listeners) l();
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", handleStorage);
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

// --- grid layout mode (unit 3) ------------------------------------------

// Grid mode never goes past 4 cells: below ~⅓-stage cells the antenna canvas
// stops being steerable, which defeats the mode's whole point (plan doc
// "Layout modes"), so pins #5/#6 stay rail-only rather than making a 3×2.
export const GRID_CELL_CAP = 4;

// Grid mode's displayed cells: the first ≤4 pins, in pin order. Pure slice —
// used both for what renders (ViewGrid) and what the arrow keys cycle
// (useViewState), so the two can never disagree about "what's on screen".
export function gridCells(pinned: View[]): View[] {
  return pinned.slice(0, GRID_CELL_CAP);
}

// The grid's row/column count for a given number of displayed cells:
// 1 → one full cell, 2 → 1×2, 3–4 → 2×2 (3 leaves the 4th cell the "pin a
// 4th view" hint — ViewGrid draws that, this only says the shape is square).
export function gridShape(nCells: number): { rows: number; cols: number } {
  if (nCells <= 1) return { rows: 1, cols: 1 };
  if (nCells === 2) return { rows: 1, cols: 2 };
  return { rows: 2, cols: 2 };
}

// What to do when the grid-mode focus ring (`view`) is not one of the
// displayed cells — see docs/plan-view-rail-scaling.md "Layout modes" and
// "Keyboard". There are two distinct causes, told apart by `wasGrid` (was
// the layout already "grid" the last time this ran):
//
//   - `wasGrid` false: we just switched INTO grid (rail → grid). The view
//     that was active carries over regardless of WHY it's off-grid — a peek
//     or a pinned view beyond cell 4 (pin #5/#6) — either way there is
//     nowhere to put the ring but cell 1, so grid mode itself is not
//     disturbed.
//   - `wasGrid` true and the view IS pinned: already in grid, and a picker
//     row-click landed on a pinned-but-off-grid view (pin #5/#6) — same
//     fix, snap the ring to cell 1.
//   - `wasGrid` true and the view is NOT pinned: the row-click activated a
//     peek. A peek has no cell by definition — it costs no pin slot (see
//     the plan doc's "Peek" note), so it never gets one — there is nothing
//     to snap the ring to. Leave grid for rail, where the peek becomes
//     rail's primary instead of being stranded off-screen.
//
// Returns null when the ring is already on a displayed cell (the common
// case on every render that isn't one of the above transitions).
export type GridFix = { view: View } | { layout: "rail" } | null;
export function gridFix(
  layout: Layout,
  wasGrid: boolean,
  view: View,
  pinned: View[],
): GridFix {
  if (layout !== "grid") return null;
  const cells = gridCells(pinned);
  if (cells.includes(view)) return null;
  if (!wasGrid || pinned.includes(view)) return { view: cells[0] };
  return { layout: "rail" };
}

export function useViewPrefs() {
  const prefs = useSyncExternalStore(subscribe, getSnapshot);
  const { pinned, seen, layout } = prefs;

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

  // Unit 3: the desktop layout preset. No validation needed beyond the type
  // itself — unlike pins, there is no cap or floor to enforce here.
  const setLayout = useCallback((next: Layout) => {
    const cur = getSnapshot();
    if (cur.layout === next) return; // keeps snapshot identity, as markRosterSeen does
    update({ ...cur, layout: next });
  }, []);

  return { pinned, seen, newIds, railViews, togglePin, markRosterSeen, layout, setLayout };
}
