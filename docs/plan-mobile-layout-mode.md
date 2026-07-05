# Plan: mobile layout mode for the web workbench

Status: **planned, not started.** This document is the implementation brief; a
future session executes it. All work is in
`src/antennaknobs/web/frontend/src/App.tsx` and `.../styles.css`.

## Context

On a phone today the workbench builds one desktop-sized canvas and lets you
**pan around** it. The CSS block `@media (max-width:700px), (max-height:500px)
and (pointer:coarse)` (styles.css ~2144–2178) turns `.app` into a fixed
1920×1080 two-axis scroll surface. It works but is inconvenient: the knobs and
the output charts are never on screen together, so you can't see the effect of a
knob turn while you turn it.

Goal: a purpose-built mobile layout that keeps knobs and one output view visible
at once.

- **Portrait**: top half = input knobs, bottom half = one output screen.
- **Landscape**: knobs on the left, one output screen on the right.
- Output = **5 swipeable screens** — Antenna (3D), Azimuth, Elevation, Smith,
  and a new **Info** screen holding the R/X/SWR/rtt readout. Swipe left/right
  with a **row of dots** showing position.
- Each pane is independently scrollable.

## Hard constraints

1. **Desktop must not change at all** — the `>700px` fine-pointer render path
   stays byte-for-byte today's DOM/CSS/behavior.
2. **Refactor first, feature second** — the desktop-identical refactor (Phase A)
   lands as its own commit before the mobile feature (Phase B), so the no-op
   refactor is reviewable in isolation.

## The invariant that guarantees desktop safety

The new `useIsMobile()` hook's matchMedia string is **identical** to the existing
CSS breakpoint: `(max-width:700px), (max-height:500px) and (pointer:coarse)`. So
the set of viewports where `isMobile===true` equals the set that today already
get the pan-around. No normal desktop viewport ever takes the mobile branch. All
new hooks/effects are added **unconditionally** at stable positions (never behind
an `if`), and the desktop JSX branch is left untouched.

## UX decisions (already settled)

- View switcher: **swipe + dot indicators** (a CSS scroll-snap carousel; no new
  drag JS).
- The info readout becomes a **dedicated 5th screen**; the floating HUD is
  **suppressed on mobile only** (desktop HUD unchanged).
- Split: portrait 50/50 stacked; landscape knobs-left / output-right.

---

## Phase A — desktop-identical refactor

**A1. Extract `SolveReadout` (module scope).** Move the inline HUD JSX
(App.tsx ~4534–4589) into a module-scope component placed near `formatSwr`
(~5049), before `ViewPanel`. It reuses already-module-scope helpers `feedMag`
(~5033), `formatSwr` (~5049), `ResultPanel` (~1073). Props:
`{ result, rttMs, currentExample, effectiveMultiFeed, className = "" }`, rendering
`` `readout${className ? " " + className : ""}` ``. Desktop call site:
```
<SolveReadout className={`stage-readout${stale ? " stale" : ""}`}
  result={result} rttMs={rttMs} currentExample={currentExample}
  effectiveMultiFeed={effectiveMultiFeed} />
```
This reproduces `readout stage-readout` / `readout stage-readout stale` exactly.
*Riskiest line in Phase A — verify the className concatenation is byte-identical.*

**A2. Add `useIsMobile()` (module scope, near `useSlideSize` ~1588).** Use
`useSyncExternalStore` (StrictMode/SSR-safe) with the breakpoint string above,
plus an `(orientation:portrait)` query; return `{ isMobile, orientation }`. Add
`useSyncExternalStore` to the React import. Desktop never reads the result.
**Snapshot gotcha:** `getSnapshot` must NOT return a fresh object each call
(React warns "The result of getSnapshot should be cached" and re-renders
forever). Implement as two internal `useSyncExternalStore` calls that each
return a boolean primitive, then compose the result object.

**A3. Extract a local `renderOutput` closure (NOT a component).** Inside
`DesignSession`, before `return`, define
`const renderOutput = (v: View, size: number, fill: boolean) => (<>…</>)` that
moves the per-view overlays (~4320–4507, `view`→`v`) and the main
`<ViewPanel view={v} size={size} fill={fill} …/>` (~4508–4530). A **closure**
captures the ~30 locals for free — no prop surface, no drift; a Fragment adds no
DOM node. Desktop `.carousel-slide` children become
`{renderOutput(view, chartSize, view === "antenna")}` followed by the
`<SolveReadout>` HUD. **Keep the HUD outside `renderOutput`** so mobile chart
screens don't inherit it.

**A4. Hoist the sidebar children to a `controls` const.** The `<aside>` closes
over dozens of locals, so it can't be a prop-driven component; instead
`const controls = (<>…children of the aside, ~3670–4216…</>)` and render
`<aside className="sidebar">{controls}</aside>` on desktop (identical DOM). Lets
Phase B reuse the exact knob JSX.

**A5. Hoist the solve overlays to a `solveOverlays` const.** The stage children
`.solve-bar` / `.solve-cancel` / `.solver-suggest` / `.solve-error`
(~4220–4278) are NOT cosmetic and must exist on mobile too:
`.solver-suggest` actively **withholds solves** (App.tsx ~2954–2956) until the
user clicks "Solve anyway" / "Pause simulation" — without it a mismatched
design never solves and gives no explanation; `.solve-error` is the only
failure surface; `.solve-bar`/`.solve-cancel` are the only in-flight/stop
affordances. Like `controls`: `const solveOverlays = (<>…~4220–4278…</>)`,
rendered first inside `<main className="stage">` on desktop (identical DOM)
and inside `.mobile-output` in Phase B (they're absolutely positioned relative
to their container, so `.mobile-output { position:relative }` hosts them).

**A6. Add an optional reattach key to `useSlideSize`.** Its effect runs once
(deps `[maxSize]`) and early-returns when the ref is detached — so if the
breakpoint flips at runtime (window resized across 700px, dev-tools device
toolbar), the newly mounted branch's element attaches *after* the effect ran:
no ResizeObserver, size stuck at the default. Add an optional
`reattachKey?: unknown` param included in the effect deps. Desktop call sites
pass nothing in Phase A (deps value `undefined` — behavior identical); Phase B
passes `isMobile` at every call site (`slideRef`, `mobRef`) so both branches
re-measure on a flip. Give `useThumbColumnSize` the same treatment.

*No `<OutputCarousel>` component and no change to the `View` union — the closure +
`SolveReadout` are the minimum reuse surface with the least desktop risk.*

**Verify Phase A**: `npm run build`; run dev at desktop width and confirm the HUD,
thumbstrip, and arrow-key view cycling are unchanged (optionally DOM-diff against
`git stash`).

---

## Phase B — mobile feature (gated on `isMobile`)

**B1. Branch the return.** At the top of `DesignSession`'s `return`:
```
if (isMobile) return (
  <div className="app app-mobile">
    <aside className="sidebar mobile-knobs">{controls}</aside>
    <section className="mobile-output" ref={mobRef}>
      {solveOverlays} …carousel + dots…
    </section>
  </div>
);
return ( /* existing desktop tree, unchanged */ );
```
Rendering a distinct mobile output tree (rather than CSS-hiding the desktop
thumbstrip/status/HUD) is cleaner and lower-risk — but the solve overlays
(A5) MUST be included; they carry solver-mismatch approval, solve errors, and
cancel (see A5). The `.status` ws indicator may be dropped or folded into the
Info screen.

**B2. The 5-screen scroll-snap carousel (no new drag JS).** Add module-scope
`const MOBILE_SCREENS = [...VIEWS, { id: "info", label: "Info" }]` (leave the
`View` union at 4 so `"info"` never ripples into `ViewPanel`/effects). New state:
`mobileIndex`, `carouselRef`, and a **second unconditional** `useSlideSize(720)`
whose ref (`mobRef`) attaches to `.mobile-output` (unused/default on desktop).
Each screen is `flex:0 0 100%` with `scroll-snap-align:start`; chart screens call
`renderOutput(s.id as View, mobChartSize, s.id==="antenna")`, the info screen
renders `<SolveReadout className="mobile-readout" …/>` (a normal block, not the
positioned HUD). Dots = a button per screen; `.active` at `mobileIndex`.
**Staleness**: desktop dims via `carousel-slide stale` (~4317) — carry the same
cue over by rendering the carousel as
`` className={`mobile-carousel${stale ? " stale" : ""}`} `` and reusing the
existing dim rule for it. Do NOT also put `stale` on the mobile readout: on
desktop the HUD sits inside the dimmed slide and its own `.readout.stale` rule
compounds to ~0.25 opacity (double dim — possibly unintentional; candidate for
a separate desktop PR). The mobile carousel dim already covers the Info screen,
so mobile takes the single dim and doesn't inherit the quirk.
All 5 mount at once (acceptable: canvases are pure, non-interactive render
targets; data comes from existing effects). *Perf note: if the 3D canvas makes
5-up sluggish on a real phone, a follow-up can render only active±1 screens.*

**B3. Keep `view` as the source of truth for the 4 chart screens.**
- `onCarouselScroll` (rAF-throttled): `i = round(scrollLeft/clientWidth)`; if
  changed → `setMobileIndex(i)`, and if `i < VIEWS.length` → `setView(VIEWS[i].id)`.
- `goToScreen(i)`: set state + `carouselRef.scrollTo({left:i*clientWidth,
  behavior:"smooth"})`.
- Reverse-sync effect keyed `[view]` (early-return `!isMobile`): if
  `mobileIndex < VIEWS.length` and out of sync, scroll to the view's index.
- Loop guard: only `scrollTo` when the rounded index differs (never fight a drag).
- Leave the arrow-key cycler (~2416–2439) **unchanged** — it cycles the 4 chart
  views; reverse-sync pages the carousel among them. Info is swipe/dot-only.

**B4. Orientation flip.** Screen width changes on flip, so `scrollLeft` no longer
lands on a snap point. Add an effect keyed `[orientation, mobChartSize]`
(early-return `!isMobile`) that `requestAnimationFrame`s a
`scrollTo({left: mobileIndex*clientWidth})` to re-center. `useSlideSize`'s
ResizeObserver re-sizes the charts automatically.

**B5. CSS (styles.css).** **Replace** the pan-around block (~2144–2178). Gate all
mobile layout on the `.app-mobile` class (present only when `isMobile`, so JS and
CSS can't disagree and plain `.app` is untouched):
```css
.app-mobile { grid-template-columns:1fr; grid-template-rows:1fr 1fr; overflow:hidden; }
.app-mobile .mobile-knobs { grid-row:1; overflow-y:auto; overflow-x:hidden; min-height:0; }
.app-mobile .mobile-output { grid-row:2; position:relative; overflow:hidden; min-height:0; min-width:0; }
@media (orientation:landscape) {
  .app-mobile { grid-template-columns:minmax(0,44%) 1fr; grid-template-rows:100%; }
  .app-mobile .mobile-knobs  { grid-row:auto; grid-column:1; }
  .app-mobile .mobile-output { grid-row:auto; grid-column:2; }
}
.mobile-carousel { display:flex; height:100%; overflow-x:auto; overflow-y:hidden;
  scroll-snap-type:x mandatory; -webkit-overflow-scrolling:touch; }
.mobile-screen { flex:0 0 100%; scroll-snap-align:start; scroll-snap-stop:always;
  position:relative; display:flex; align-items:center; justify-content:center; overflow:hidden; }
.mobile-screen.mobile-screen-info { overflow-y:auto; align-items:flex-start; }
  /* Info can exceed a ~400px landscape pane (per-feed Z table) — it scrolls
     vertically; y-scroll inside an x-snap carousel coexists fine. */
.mobile-dots { position:absolute; bottom:var(--space-4); left:50%; transform:translateX(-50%);
  display:flex; z-index:3; }
.mobile-dots button { padding:16px 10px; border:none; background:none; }
  /* ≥40px touch targets (cf. the coarse-pointer block ~2184); the visual dot
     is the ::before pseudo-element. */
.mobile-dots button::before { content:""; display:block; width:8px; height:8px;
  border-radius:50%; background:var(--muted); opacity:.5; }
.mobile-dots button.active::before { background:var(--accent); opacity:1; }
.mobile-readout { max-width:min(90%,320px); }
.app-mobile .stage-readout { display:none; } /* defensive; HUD isn't rendered on mobile anyway */
```
Because `.app-mobile` exists only on mobile, the `orientation:landscape` rule
never touches a landscape desktop window (which has plain `.app`). Keep the touch
hit-target block (~2184–2197) as-is.

---

## Edge cases

- **Desktop byte-identity**: `SolveReadout` className concat + `renderOutput`
  Fragment must reproduce ~4320–4589 exactly; all new hooks added unconditionally.
- **Cut-angle `Knob`** on the az/elev screens keeps `touch-action:none`: a swipe
  starting on the knob turns it (as on desktop); page-swipes use empty chart area.
  No other canvas has pointer handlers, so no swipe conflict.
- **View-gated data effects** (freq sweep / converge / norm-check / pin) key off
  `view`; B3 keeps `view` synced to the snapped chart screen, so they behave as on
  desktop. Info screen leaves `view` on the last chart.
- **scroll ⇄ dots feedback loop**: guarded by the rounded-index tolerance + rAF.
- **StrictMode double-mount**: `useSyncExternalStore` + idempotent ResizeObserver.
- **Runtime breakpoint flip** (window resized across 700px / device toolbar):
  handled by A6's reattach key — both branches re-measure when `isMobile`
  changes. The solve overlays and solver-approval state live in `DesignSession`
  state, so they survive the flip.

## Verification

1. `npm run build` (`tsc --noEmit && vite build`) in the frontend dir.
2. Dev server at desktop width: confirm desktop unchanged (HUD, thumbstrip,
   arrow cycling); optionally DOM-diff against `git stash`.
3. Chrome device-toolbar / resize to a **portrait** phone viewport (≤700px):
   50/50 stack, both panes scroll, swipe pages all 5 screens, dots track, Info
   shows the full readout, no HUD over charts. Turning a knob dims the carousel
   (stale) while the solve is in flight; a solver-mismatch design shows the
   suggest dialog and a broken design shows the solve error.
   Flip the device toolbar between mobile and desktop widths: charts re-measure
   in both directions (A6).
4. Rotate to **landscape**: knobs-left / output-right; active screen stays
   centered across the flip.
5. Tap dots to jump; arrow-cycle with a keyboard and confirm the carousel follows
   for the 4 chart screens.

## Reference: current architecture (verified)

- `DesignSession({ id, active })` (App.tsx ~1835); its `return` (~3667–4596) is
  `<div className="app">` = `<aside className="sidebar">` (knobs, ~3669–4217) +
  `<main className="stage">` (~4219–4595). `App()` (~4606) mounts sessions.
- `.app` grid `320px 1fr` (styles.css 234–240); `.sidebar` `overflow-y:auto`
  single scroll container (242–253); `.stage` flex row (1819–1831).
- Stage children: `.solve-bar`, `.solve-cancel?`, `.solver-suggest`,
  `.solve-error`, `.thumbstrip` (~4279, sized by `useThumbColumnSize` from
  column height), `.carousel-slide` (~4316, ref=`slideRef`, sized by
  `useSlideSize`), `.status` (~4591).
- `.carousel-slide` = per-view overlays (~4320–4507) + `<ViewPanel>` (~4508–4530)
  + floating `.readout.stage-readout` HUD (~4534–4589).
- `View`/`VIEWS` module scope (1571–1577): antenna, azimuth, elevation, smith.
- `useSlideSize` (1588): measures ref via getBoundingClientRect + ResizeObserver,
  clamps `min(w,h,max)` then `max(160, floor-16)`; returns default when detached.
- Arrow-key view cycler (2416–2439): window keydown, `if(!active)return`, skips
  INPUT/TEXTAREA/SELECT/contentEditable/`.knob`, cycles `VIEWS` mod-4.
- Canvases (`CurrentCanvas` ~6221, `SmithChart` ~5777, `FarFieldChart` ~5444)
  have **no** pointer/touch handlers; only `Knob` (~426, `touch-action:none`)
  owns pointer drags (sidebar + az/elev cut-angle overlay).
- No `matchMedia`/`innerWidth` anywhere today; React 18.3.1 (Vite + `tsc`).
