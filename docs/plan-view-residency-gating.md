# Plan: gate background analyses on view residency (issue #715)

**Date:** 2026-08-05 · **Status:** design pass complete, implementing.
Deferred from #700 with the warning that it "couples data flow to layout —
needs its own design pass." This is that pass.

## The consumer census (the load-bearing table)

Every product of `useAnalysisRunners` + `useSchematic`, and every place it
renders (post-#700 view registry):

| Analysis        | View consumers            | Non-view consumers            |
|-----------------|---------------------------|-------------------------------|
| freq sweep      | `smith`, `gamma`, `vswr`  | — (StageOverlays only toggles)|
| converge sweep  | `smith`                   | —                             |
| NEC rp pattern  | `azimuth`, `elevation`    | —                             |
| norm check      | —                         | **SolveReadout (the HUD)**    |
| schematic SVG   | `schematic`               | —                             |

The one the issue warned about is the norm check: the HUD renders in every
layout (mobile Info page, desktop rail slide, grid stage HUD), so its
radiated-fraction row is resident whenever the session is. **The norm check
is therefore NOT gated on view residency at all** — gating it would blank a
number that is always on screen. It keeps its existing gates (checkbox,
autoSim, tab-active) untouched. Everything else has only view consumers and
gates cleanly.

## Residency definition

    resident(view) = pinned.includes(view) || view === activeView

`pinned ∪ {active}` is exactly what can be on screen in every layout:

- **rail**: pinned render as live thumbs, the active view renders large —
  and a *peeked* view (active but unpinned) renders large too;
- **grid**: pinned are the cells; active ⊆ pinned in practice, and the
  union is a safe superset regardless;
- **mobile**: the carousel maps over ALL pinned screens (they are mounted,
  scroll-snapped), so pinned is the right set there as well.

Fetching for a view that is only a thumbnail is deliberate: thumbs render
the real charts, and a thumb with missing data would look broken.

## Where the coupling lives (and where it must not)

`DesignSession` — which already owns both the layout state and the analysis
cluster — derives three booleans:

    sweepResident    = smith | gamma | vswr resident
    convergeResident = smith resident
    patternResident  = azimuth | elevation resident

and passes them to `useAnalysisRunners` as plain gating props, exactly like
`sweepEnabled`/`autoSim`. The hook stays layout-agnostic: it never imports
view types, never sees `pinned`. `useSchematic` composes at its call site
(`active && resident(schematic)`) since it already has a single `active`
gate. That containment is the answer to #700's coupling worry: layout
knowledge stays in the one component that always had it.

The effective gate per analysis is `userCheckbox && resident && autoSim &&
active` — residency is a second gate, not a replacement for the
StageOverlays checkboxes (a user who turned the converge sweep off keeps it
off even with the smith view pinned).

## Semantics on residency changes

- **Losing residency** (unpin the last consumer / navigate away from a
  peek): the effect re-fires, aborts any in-flight fetch, clears the data,
  and returns before scheduling — the same clear-on-disable semantics the
  effects already have for their checkboxes. This is the perf win: no
  sweep/converge/pattern churn for views nobody can see, and the server
  lane is freed mid-flight.
- **Gaining residency** (pin, or peek from the picker): the effect re-fires
  and fetches after the standard 500 ms debounce. Scrubbing through peeks
  in the picker costs at most one aborted debounce per hop. Refetch-on-
  re-pin is cheap because the server's `_SOLVE_CACHE` still holds the
  points; deliberately NOT client-cached across residency loss — stale
  invalidation questions (the #691 class) are not worth the saved
  round-trip to a warm server cache.
- The #692 request-signature invalidation is untouched: residency booleans
  join the *gating* half of each dep array, never the physics half.

## Out of scope

- The optimizer, live solve, geometry preview, measured overlay: not
  background analyses, no view gating.
- Client-side caching across residency loss (above).
- Gating the norm check (above — HUD consumer).

## Test plan

1. Unpinning all sweep consumers aborts + clears the sweep and stops
   refetching on knob changes; re-pinning any one consumer refetches.
2. A peek (active, unpinned) counts as resident — fetch fires.
3. `convergeResident` follows `smith` alone; `patternResident` follows
   either cut view.
4. Norm check is unaffected by any residency change (pinned set empty →
   still fetches when its checkbox is on).
5. Checkbox-off still wins over resident-on (no fetch).
6. The #691 plane-flip and #692 signature/exemption tests pass unchanged.
