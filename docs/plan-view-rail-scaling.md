# Plan: scale the output-view rail beyond 4 views (pinned set + overflow)

Status: **design for review** (issue #684). This is the design-exploration
deliverable — the pattern survey, the chosen direction, and the follow-up
implementation issues to file once the direction is accepted. No code changes
land with this doc. Mock: `docs/mock-view-rail.html` (open in a browser; shows
both layout modes and the picker at a 9-view roster).

## Context

The output-view roster is growing. #686 shipped the schematic as view five,
putting four thumbnails in the desktop rail, and the next views are imminent
rather than hypothetical (sweep data already reaches the Smith chart, so an
RC-vs-frequency chart is mostly presentation). The current layout divides the
thumbstrip column equally among all non-active views
(`useThumbColumnSize`, `components/hooks.ts`), so every added view shrinks
every thumbnail.

The numbers, using the hook's own overhead model on a ~720 px stage column
(a 13" laptop):

| rail thumbs | thumb height | verdict |
|---|---|---|
| 3 (pre-#686) | ~160 px | comfortable |
| 4 (today) | ~131 px | noticeably smaller, still fine |
| 6 | ~72 px | labels legible, charts marginal |
| 8 (roster below, unbounded) | ~44 px | at the 40 px clamp floor — unusable |

So the rail cannot stay "everything, always resident." The user needs to pick
a small always-visible set; the rest must be reachable without being resident.

### Constraints (scored against every surveyed pattern)

- **C1 Live charts.** Every resident view re-renders on each solve (the rail
  thumbs are real `ViewPanel`s, not snapshots). A pattern that keeps many
  views resident multiplies render cost; a pattern that hides views must
  bring them back current, not stale.
- **C2 Thumbnail legibility floor.** Charts draw fixed-px text at the
  3-thumb-era width and scale down uniformly (`thumb-scale`); below ~70 px of
  height a polar chart is a smudge. The clamp floor is 40 px.
- **C3 Keyboard cycling.** ArrowUp/Down cycles views (`useViewState`). Cycling
  must stay fast — 9 stops to get back to the antenna view is a regression.
- **C4 Mobile carousel.** Scroll-snap pages + dots (`useMobileCarousel`), with
  the invariant that carousel index ↔ `VIEWS` order plus a trailing Info page.
  Whatever the desktop does must project onto this cleanly.
- **C5 Small-laptop column height.** The rail never scrolls
  (`overflow: hidden` by design); everything resident must fit ~700–800 px.

### The view roster this must be sized for

| # | view | status |
|---|---|---|
| 1 | Antenna (3D geometry + currents) | shipped |
| 2 | Azimuth cut | shipped |
| 3 | Elevation cut | shipped |
| 4 | Smith chart | shipped |
| 5 | Schematic | shipped (#686) |
| 6 | \|Γ\| / return loss vs. frequency | imminent (sweep data already flows) |
| 7 | VSWR vs. frequency | imminent (same data, different axis) |
| 8 | Optimization traces (objective vs. iteration, parameter trajectories) | planned |
| 9 | Convergence view (metric vs. mesh density; today an overlay on Smith) | planned |

Design target: **9 views**, of which a user actively watches 3–5 at a time.

## Survey: how other UIs solve "many views, few slots"

### P1. Pinned rail + overflow picker

*Browser bookmarks bar + "other bookmarks" chevron; Chrome/Firefox pinned
tabs; IDE pinned editor tabs; Grafana dashboard panels drawn from a panel
library; Slack starred channels.*

```
┌──────┐ ┌──────────────────┐
│ [az] │ │                  │
│ [el] │ │   ACTIVE VIEW    │
│ [sm] │ │                  │
│ ⋯ +5 │ │                  │
└──────┘ └──────────────────┘
```

The user curates a small "always visible" set; everything else lives behind
one compact affordance. Pinning is an explicit, low-frequency act; switching
among pinned items is the high-frequency act and stays one click.

- **C1** ✅ resident set is bounded, so live re-render cost is bounded.
- **C2** ✅ thumb size is a function of pin count, which is capped.
- **C3** ✅ cycling over the pinned set is short by construction.
- **C4** ✅ "carousel pages = pinned set" is a clean projection.
- **C5** ✅ the cap is chosen *from* the column-height math.
- **Cons:** unpinned views are out of sight (no ambient monitoring of view
  #7); needs a picker affordance and sane defaults; new views ship invisible
  unless the picker advertises them.

### P2. Multi-chart grid presets

*TradingView layouts: 1/2/4/6/8-up grid presets over the same loaded charts,
saved as named workspaces; thinkorswim flexible grid.*

```
┌─────────┬─────────┐
│  az     │  el     │
├─────────┼─────────┤
│  smith  │  vswr   │
└─────────┴─────────┘
```

The key insight from TradingView: "1 big" and "N equal" are **presets of one
system**, not separate features — the same chart set flows into whichever
arrangement is selected. Users flip presets constantly; they curate the chart
set rarely.

- **C1** ✅ 4 live full-size charts is comparable to today's 1 full + 4 thumbs.
- **C2** ✅✅ no thumbnails at all — every cell is above legibility.
- **C3** ⚠️ "active view" needs a definition (a focus ring) for arrows to act on.
- **C4** ➖ grids don't project to a phone; mobile keeps its carousel.
- **C5** ✅ 2×2 uses the stage, not the column.
- **Cons:** no primacy — the antenna canvas (the view you steer by) drops to
  quarter size; slot-assignment UI (drag into cells) can balloon; at 9 views
  a 3×3 makes everything small again, so a grid still needs a curated subset —
  i.e. it needs P1 underneath it.

### P3. Docking / tiling workspaces

*JupyterLab drag-dock panels; VS Code editor groups; Golden Layout; CAD quad
viewport (Blender `Ctrl-Alt-Q`, Fusion 360).*

Fully free-form: any view any size anywhere, persisted workspaces. The CAD
quad viewport is the disciplined version: a fixed 2×2 of standard projections
with a **maximize toggle** flipping one cell ↔ full stage.

- **C1** ⚠️ unbounded resident set — a user can dock all 9 live views.
- **C2** ✅ user controls every size (and can make them illegible).
- **C3** ❌ cycling over a free-form layout is ill-defined.
- **C4** ❌ nothing about a dock layout projects to a phone.
- **C5** ⚠️ user-managed; layouts rot as the roster changes.
- **Cons:** by far the most implementation surface (drag targets, splitters,
  serialization, migration of stale layouts) for a roster of only 9
  fixed-aspect views. **Take from it:** the maximize toggle — grid cell ↔
  primary is one gesture, both directions.

### P4. Filmstrip / carousel with paging

*Lightroom filmstrip; macOS Mission Control; our own mobile carousel.*

A single strip of all views, scrolled/paged; the strip shows a window of N.

- **C1** ✅ only the visible window renders (virtualization is natural).
- **C2** ✅ fixed thumb size, count handled by scrolling.
- **C3** ⚠️ cycling walks the *full* roster — 9 stops (the regression C3 fears).
- **C4** ✅ it *is* the mobile pattern; already shipped.
- **C5** ❌ contradicts the rail's deliberate never-scrolls invariant: a
  scrolling rail means the view you glance at may be off-screen, killing
  ambient monitoring (the rail's whole point).
- **Verdict:** stays exactly where it already is — the mobile mode.

### P5. Instrument idioms

*Spectrum-analyzer multi-trace with soft-key trace enable; oscilloscope
channel enable buttons (CH1–CH4 toggle lit/unlit); SDR panadapter split
views.*

The front panel has N channel buttons, each toggling that channel's
visibility; enabled channels share the screen. State is visible at a glance
— a lit button *is* the indicator.

- **C1** ✅ enabled set bounded by channel count.
- **C2/C5** ✅ bounded by construction.
- **C3** ✅ scopes cycle among *enabled* channels only.
- **C4** ➖ n/a.
- **Cons:** scope channels are homogeneous overlaid traces; our views are
  heterogeneous (3D canvas / polar / Smith / SVG) so they can't overlay —
  they need slots. Soft-key menu trees are modal and dated. **Take from
  it:** the picker should read as a channel-enable row — every view listed,
  each with a visible on/off pin state, one tap to toggle.

### P6. Ham/RF simulator prior art

*xnec2c: an independent GTK top-level window per chart (geometry, pattern,
charts each float free). EZNEC: modal window per output — open the pattern
window, close it, open the SWR window. 4nec2: same, separate windows. SimNEC:
everything on one fixed canvas, always. AntennaSim: single view + tabs.*

- xnec2c's window-per-chart is the P3 endpoint: great on a 30" desk with a
  window manager, untenable inside one browser tab and hostile to laptops.
- EZNEC's modal windows break the live loop — you cannot watch SWR while
  turning a knob, which is this workbench's entire reason to exist.
- SimNEC's single canvas is the zero-navigation extreme and simply does not
  scale in roster.
- **Verdict:** none of the incumbents solve "live-updating + bounded space";
  whatever we pick here is a differentiator, not table stakes.

### Survey conclusion

P4 is already correctly deployed (mobile). P3 and P6-windows are
over-engineered for 9 fixed views. P2 alone still needs curation underneath.
The composition that scores green across the constraint row is:

> **P1 (pinned set + overflow picker) as the model, P5 (channel-enable row)
> as the picker idiom, P2 (presets of one system) for layout modes, P3's
> maximize toggle as the mode-switch gesture.**

Precedent note the issue asked for: TradingView and the CAD quad viewport
both treat "1 big + N small" and "N equal" as **presets over one selection**;
Lightroom's Loupe/Grid similarly share one filmstrip selection. Nobody
successful makes them separate features with separate state. We follow that:
both layout modes render *the pinned set*; only the arrangement changes.

## Chosen direction

### The pin model

- `pinned: View[]` — an **ordered** list, default
  `["antenna", "azimuth", "elevation", "smith"]` (the founding four;
  schematic and all future views default unpinned).
- **Cap: 6 pinned.** From the column math: 6 pinned ⇒ 5 rail thumbs (active
  excluded) ⇒ ~96 px thumbs on a 720 px column — above the legibility floor
  with margin. The picker disables further pinning at the cap (tooltip: "Unpin
  a view first").
- Rail renders `pinned \ {active}` exactly as today. **Peek:** activating an
  unpinned view (from the picker) makes it primary without pinning it; the
  rail then shows all pinned views. Peek is transient — it costs no pin slot.

### The overflow affordance: the view picker

A fixed-height slot at the bottom of the thumbstrip — a compact button
labeled **"All views ⌄"** with a count of unpinned views ("+5"). Clicking
opens a popover listing the **entire roster in registry order**, channel-row
style (P5):

```
┌──────────────────────────┐
│ 📌 Antenna            ●  │   ● = pinned (click pin dot to toggle)
│ 📌 Azimuth (xy)       ●  │   row click = show (peek or switch)
│ 📌 Elevation (yz)     ●  │
│ 📌 Smith              ●  │
│    Schematic          ○  │
│    |Γ| vs freq   NEW  ○  │
│    VSWR vs freq  NEW  ○  │
│    Optimization       ○  │
│    Convergence        ○  │
└──────────────────────────┘
```

- Row click → that view becomes active (peek if unpinned). Pin-dot click →
  toggles pinned, capped at 6.
- A **"NEW" badge** marks views added since the user last opened the picker
  (roster version stamped into the persisted state) — this answers P1's
  discoverability con: new views ship unpinned but announced.
- The button occupies fixed height, so `useThumbColumnSize`'s overhead model
  gains one constant term and nothing else changes shape.

### Layout modes (presets of one system)

Two modes, selectable via a two-icon segmented control in the stage's top-right
corner (▤ rail / ⊞ grid):

1. **Rail** (today): primary + pinned thumbs. Unchanged behavior, now over
   the pinned set.
2. **Grid**: equal cells over the **first 4 pinned views** in pin order, no
   primary. 2 pinned → 1×2, 3–4 pinned → 2×2 (a 3-pin grid leaves cell 4
   empty with a "pin a 4th view" hint). Pins beyond 4 stay rail-only —
   the grid does not go 3×2; below ~⅓-stage cells the antenna canvas stops
   being steerable, which defeats the mode. Each cell is a **full live
   `ViewPanel`** (`fill` semantics, not a scaled thumb — no `thumb-scale`
   trick), so C2 vanishes in this mode.
3. **Active still exists in grid** — a focus ring on one cell. ArrowUp/Down
   moves the ring (C3 keeps working, same key mnemonic); the HUD readout
   anchors to the stage lower-left as today. Clicking a cell's body focuses
   it; the maximize glyph in a cell's corner (or double-click, Blender-style)
   jumps to rail mode with that view primary. The segmented control returns
   to grid.

### Keyboard

ArrowUp/Down cycles **`pinned ∪ {active}`** — the active view joins the cycle
transiently while peeked, so arrows never strand you. Full roster is
reachable through the picker only. With the default 4 pins the cycle is
exactly today's pre-#686 feel: short.

### Mobile

- Carousel pages = **pinned views + Info**, same scroll-snap and dots. Pin
  order is the page order; the `mobileIndex ↔ VIEWS` mapping becomes
  `mobileIndex ↔ pinned` (plus trailing Info).
- The dots row gains a trailing **"⋯" dot** opening the same picker as a
  bottom sheet. On mobile the picker's row-click **pins** (no transient peek
  — a peeked page would break the "carousel = pinned + Info" invariant and
  scroll-position bookkeeping for one gesture's worth of convenience).
- Grid mode is desktop-only; the segmented control hides on mobile.

### Persistence: global, not per-design

Pinned set, pin order, layout mode, and picker roster-version persist in
`localStorage` under one key (e.g. `akb.viewPrefs.v1`).

Rationale: the roster is a property of the **workbench**, not of a design —
every design has every view, and the user's watching habits ("I care about
VSWR and the pattern") span designs. Per-design pin sets would reshuffle the
workspace on every catalog switch and strand stale state across 100+
designs. The counter-case (a multi-feed design where you'd pin the schematic)
is served by peek — one picker click, no state to clean up later.
Per-design overrides can be layered on later without migration (a per-design
key shadowing the global one); starting global keeps door open, starting
per-design doesn't.

### What this deliberately does not do

- **No drag-to-reorder** in v1 — pin order = order pinned. Reorder is cheap
  to add later and drag machinery is the biggest cost in P2/P3 systems.
- **No analysis gating** — unpinned views stop *rendering* but background
  analyses (sweep, converge, schematic fetch) keep their current triggers;
  gating analyses on residency is a real perf opportunity but couples data
  flow to layout and deserves its own issue after this ships.
- **No saved named workspaces** (TradingView's full feature) — one persisted
  state is enough at 9 views.

## Mock

`docs/mock-view-rail.html` — static, self-contained. Shows, at the 9-view
roster: (a) rail mode with 4 pins + the "All views" button, (b) the picker
open with pin dots and NEW badges, (c) grid mode 2×2 with focus ring and
maximize glyphs, (d) the mobile carousel dots with the "⋯" dot. Numbers in
the mock use the real overhead model from `useThumbColumnSize`.

## Follow-up implementation issues (file on acceptance)

1. **View registry.** Replace `ViewPanel`'s flat conditional and the bare
   `VIEWS` array with a registry: `{ id, label, defaultPinned, render(props) }`.
   Pure refactor, no behavior change; netted by the #673 component tests.
   Everything below depends on it.
2. **Pin model + picker (desktop).** `pinned` state + localStorage
   persistence + the "All views" button/popover + peek + cycling over
   `pinned ∪ {active}` + NEW badges. Rail rendering itself barely changes
   (`pinned` replaces `VIEWS` in the filter; `useThumbColumnSize` gains the
   picker-button constant).
3. **Grid layout mode.** The segmented control, 2×2 stage layout, focus
   ring, maximize toggle, HUD anchoring.
4. **Mobile: pinned carousel + picker sheet.** `useMobileCarousel` maps
   pages onto `pinned`; "⋯" dot; sheet variant of the picker.
5. **New views: |Γ| and VSWR vs. frequency.** First registry customers;
   presentation over existing `SweepData`.

(1) and (2) are the core; (3), (4), (5) are independent of each other once
(1)+(2) land.
