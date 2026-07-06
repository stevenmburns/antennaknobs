# Plan: cross-session pinned patterns, with per-pin enable/disable

Status: **implemented & verified 2026-07-05** (Phases 1+2 on
`cross-session-pinned-patterns`; Phase 3 loop run headless against the dev
server — all five checks passed). Motivated by the tabbed-sessions
work (PR #214): now that different antenna designs live in different session
tabs, the pin mechanism — built for comparing tunings *within* one session —
should span sessions so tab A's pattern can be overlaid on tab B's chart.

## Motivation

Pins exist to freeze a far-field snapshot and compare something else against
it. With tabbed sessions the natural "something else" is *another session's
design*, but today each session keeps its own private pin list, so the
comparison the tabs were built for can't use the pins. Three asks:

1. **Share pins across sessions** — one global pin list; a pin made in any tab
   shows (ghost overlay + compare-table row) in every tab.
2. **Individual delete** — already exists (✕ per row, `removePin`,
   `App.tsx:2983`); must survive the refactor unchanged.
3. **Individual enable/disable** — hide a pin's ghost overlay without losing
   the snapshot, so a crowded chart can be decluttered pin-by-pin (today the
   only options are delete-one or clear-all).

## How it works today (baseline)

All pin state is **per-session**, inside `DesignSession` (`App.tsx:1885`):

- `pinnedPatterns: PinnedPattern[]` + `pinSeq` ref (`App.tsx:2379–2381`).
  `PinnedPattern` (`App.tsx:5558`) = `{ id, label, result: SolveResponse,
  metrics: PatternMetrics | null }`. The snapshot is frozen at pin time; pins
  already survive design switches *within* a session.
- `pinCurrentPattern()` (`App.tsx:2970`) snapshots the session's current
  `result`, labels it `"{design label} @ {measFreq} MHz"`, and fetches
  `/pattern_metrics` for the table row. `fetchMetrics` (`App.tsx:2953`) is a
  plain async helper (no session state; can move to module level as-is).
- `liveMetrics` (`App.tsx:2380`) is the *live* antenna's table row, refreshed
  per solve while `comparing` (≥1 pin and a cut view) and gated on the
  session being `active` (`App.tsx:2993`). Genuinely per-session — stays put.
- Rendering: ghosts draw in the polar cut charts (`pinned={pinnedPatterns}` at
  `App.tsx:5501/5515`, drawn dashed at `App.tsx:6010`); the compare table
  (`PatternCompareTable`, `App.tsx:5565`) lists live + pins with per-row ✕ and
  a clear-all; the table minimizes to a "{n} pinned" chip
  (`compareCollapsed`, `App.tsx:2482`). Thumbnails intentionally pass
  `pinnedPatterns={[]}` (`App.tsx:4855`) — keep that.
- **Colors are positional**: both the table (`App.tsx:5589`) and the chart
  (`App.tsx:6015`) use `GHOST_COLORS[i % len]` where `i` is the array index.
  Consistent today only because both iterate the same array; deleting a pin
  already recolors every later pin.

Why sharing is safe: a `PinnedPattern` is a self-contained frozen snapshot —
it holds the full `SolveResponse` and never touches the owning session's
socket, knobs, or refs after creation. `computeCutDbi` (`App.tsx:5650`)
recomputes its trace from the snapshot alone. Nothing about a pin needs its
session to still exist.

## Design

### Phase 1 — lift pins to the shell (shared across sessions)

Move `pinnedPatterns` + `pinSeq` from `DesignSession` up to `AppShell`
(`App.tsx:4899`), exposed through a new dedicated context:

```ts
type PinsCtx = {
  pins: PinnedPattern[];
  addPin: (label: string, result: SolveResponse, req: SolveRequest) => void;
  removePin: (id: string) => void;
  togglePin: (id: string) => void;   // Phase 2
  clearPins: () => void;
};
```

- A **separate `PinsContext`**, not a field on `SessionsContext`: sessions
  context is identity-memoized for tab-strip renders; pin churn (metrics
  arriving async) shouldn't invalidate it.
- `addPin` lives in the shell and owns the `/pattern_metrics` fetch +
  patch-in (the `then` at `App.tsx:2976` moves with it). `fetchMetrics`
  moves to module level. `pinCurrentPattern` stays in `DesignSession` — it
  closes over `result` / `controlsRef` / `measFreq` / `currentExample` — and
  shrinks to computing the label and calling `addPin(...)`.
- **One shell-level `pinSeq`**, so ids stay unique across sessions (two
  per-session counters would both mint `pin-0`).
- Labels keep the current `"{design} @ {freq} MHz"` form — with cross-session
  pins that's still the distinguishing information. No session id in the
  label: sessions are anonymous tabs, and the pin outlives its tab anyway.
- Pins deliberately **survive closing the session that made them** (frozen
  snapshot, no live dependency). The tab-close confirm popover text
  (`App.tsx:1724`) doesn't mention pins and needn't change.
- `compareCollapsed` stays per-session UI state. `liveMetrics` and the
  `comparing` gate stay per-session (each tab compares *its* live antenna
  against the shared pins; the `active` gate already prevents hidden tabs
  from fetching metrics).

### Phase 2 — per-pin enable/disable + stable colors

Extend the type:

```ts
type PinnedPattern = {
  id: string;
  label: string;
  result: SolveResponse;
  metrics: PatternMetrics | null;
  enabled: boolean;    // ghost overlay drawn? default true
  colorIdx: number;    // fixed at pin time — see below
};
```

- **Color must become a stored property.** With enable/disable, the chart
  draws a *filtered* list while the table draws the full list — positional
  `GHOST_COLORS[i]` would desynchronize them (and index-based color already
  shifts on delete). Assign `colorIdx` at pin time as the smallest palette
  index unused by current pins (falling back to `seq % len` when all are
  taken), and index `GHOST_COLORS[p.colorIdx % len]` at both render sites
  (`App.tsx:5589`, `App.tsx:6015`).
- `togglePin(id)` flips `enabled`.
- **Charts** draw ghosts for `pins.filter(p => p.enabled)` only.
- **Table** lists *all* pins (metrics stay visible while disabled — that's
  the point of disable vs delete). Disabled rows render dimmed; the toggle is
  the row's color swatch (click to toggle, `title` explains, swatch hollow
  when disabled). ✕ delete and clear-all unchanged.
- The `comparing` gate and the "{n} pinned" chip keep counting **all** pins:
  the table (and its live-metrics fetch) is useful even with every ghost
  hidden, and a chip that says "0 pinned" while pins exist would be worse.

### Phase 3 — build, verify, ship

- `npm run build` in `src/antennaknobs/web/frontend` (runs `tsc --noEmit`
  first). The output under `web/static/` is gitignored — built at
  package/deploy time — so there is no bundle to commit.
- Manual verify (browser must be a **visible** window — hidden Chrome
  suspends rAF and solves never send):
  1. Tab 1: pin a dipole; open tab 2, pick a yagi → ghost + table row appear
     in tab 2.
  2. Pin in tab 2 → both pins visible in both tabs, colors distinct and
     matching between table and chart in each tab.
  3. Toggle a pin off → ghost gone, row dimmed, metrics still shown; toggle
     back on → same color returns.
  4. Delete the *middle* pin → remaining pins keep their colors (regression
     check on positional coloring).
  5. Close the tab that created a pin → pin persists.
- No backend changes; `tests/test_web_server.py` unaffected. There is no
  frontend test harness — verification is the manual loop above.

## Out of scope (noted for later)

- **Persistence across page reloads** (localStorage/IndexedDB): a
  `SolveResponse` snapshot carries every wire's sample positions + complex
  currents, so serialized pins can run large; worth its own sizing look if
  wanted. This plan keeps pins in-memory.
- **Renaming pins**: labels are auto-generated; editable labels would help
  once many similar pins accumulate, but it's cosmetic.
- **Pin from an inactive session automatically** (e.g. "pin all tabs"): easy
  to add on top of the shared list if it earns its keep.

## Order of work

Phases 1 and 2 touch the same few sites (type, `AppShell`, table, chart
renderers) and Phase 2's color fix is needed the moment filtering exists — do
them as one PR, commits split as `feat(web): lift pins to app shell` then
`feat(web): per-pin enable/disable + stable ghost colors`, then the bundle
rebuild.
