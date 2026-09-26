# Z vs parameter view

AC6LA's SimNEC convergence charts (QRZ 1003328 #163) plot R (left axis) and
X (right axis) against the segment count on a log axis, with value boxes at
the ends. The workbench drew convergence only as a Smith trail. This view is
that chart for **any** parameter: the density or a numeric knob. It follows
the CLI's version (`sweep --log --panels --callouts`).

## The parameter

- **Choices:** "density" (the request's `n_per_wire`, segments per λ/4 at
  the design frequency) or any visible top-level `float`/`int` knob. The x
  axis is the **nominal** value the user set, not the engine's achieved
  segment count: that is the number the user acts on, the same on every
  engine.
- **Not sweepable in phase 1:** enum/bool knobs, group (per-band) knobs, and
  knobs that drive a frequency (`linked_to_design_freq`,
  `link_meas_freq_to_param`, `freq`, `design_freq`). The measurement
  frequency stays fixed during a knob sweep; a knob that moved it would make
  the sweep a frequency sweep in disguise. Density stays offered on a deck
  with fixed segment counts, as the old switch was; its curve is then flat.
- **Default range.** Density: the old switch's ladder, kept literal
  (`8 12 17 24 34 48 68`, the CLI's `NOMINAL_NSEGS_LADDER`) so the migrated
  trail and `Z*` do not move. A knob: its own `min`…`max`, or ±20 % of its
  value when it declares none, 11 linear points.
- **Spacing and rounding.** Linear or geometric, the CLI's `gen_xs` rule: an
  integer parameter (density, an `int` knob such as an SY segment knob) is
  rounded and deduplicated, so 10 … 500 × 20 solves whole counts. Points
  clamp to 2 … 41.
- **Where:** the view's header (parameter, from, to, points, log spacing),
  plus **Sweep this knob…** in the knob's right-click menu, which picks the
  knob at its default range and opens the view. Session state, per tab; a
  design switch that drops the knob falls back to density.

## The backend

One streaming endpoint, `POST /param_sweep`: a solve request plus `param`
and `values[]`. Each point is the request with that field overridden, solved
on **the request's own engine** through `_solve_z_only`, as the optimizer
does since #1743. Admission (`_admit`, kind `converge`), the per-point size
check, the lane turn and cancel-on-disconnect are `/converge`'s, unchanged:
the endpoint is `/converge`'s body with the override generalised. Records are
`{param, value, z_re, z_im, solver}` (+ per-feed Z); the closing record
carries `advisories`. An unknown or non-numeric parameter is a 422 before any
solve.

`/converge` stays as a **thin alias** (`param = n_per_wire`, old record key).
The frontend moves to `/param_sweep`; the alias is a few lines and keeps a tab
on the old bundle, and any script, working across a server upgrade.

## The chart

- R in red on a **left** axis, X in blue on a **right** axis, each with its
  own range popover (**Auto**, fitting that trace, or a custom min/max).
- A **lin x / log x** toggle on the chart, following the spacing until set.
- Circles at every point, value boxes at the first and last points, and a
  **hover** (or tap) readout at the nearest point.
- The **current value** as a dashed guide carrying the live solve's R and X.
  It moves as the knob is dragged **without re-sweeping** (the #1755 lesson):
  the swept field is exempt from the sweep's request signature, since every
  point overrides it. Any other knob, the engine or the ground re-sweeps.
- For density, **Richardson `Z*`** (in 1/N, as before) dotted on each axis
  and read out at the top.

## The Smith trajectory

The convergence trail becomes the parameter's trail: the same polyline, ring
at the first value, disc at the last, both labelled with their values (one
label when the trail is too short for two); `Z*` only for density. The
caption reads `length_factor: 0.8 → 1.25`.

## Multiple slots

Phase 1 sweeps the **active slot only**; switching the slot re-sweeps. One
panel per engine, with ranges lockable across them, is phase 2: it needs a
stream per slot and a per-slot lane story.

## Refinement

Phase 2. The #744 planner's curvature test would transfer, but a density
ladder is chosen for Richardson, not flatness, and a knob sweep is cheap to
re-run denser by hand.

## The gap-fed warning

Server-side, density sweeps only, when the engine models the source as a
**delta gap** (NEC-2, PyNEC, momwire `sinusoidal`, or any momwire model with
`feed_model = segment`) **and** the design is **gap-fed**: an excited wire
shorter than one segment (λ/4 ÷ N) at the coarsest density swept. That is a
dedicated feed wire: as N climbs its segment goes from much shorter than its
neighbours to their size, and a delta gap reads that ratio. A dipole fed
mid-wire, or a quad fed on a whole side, never qualifies. Wording:

> Density here mostly measures the delta-gap feed, not the antenna: the
> source sits on a 0.10 m feed wire, shorter than one segment at N = 10
> (0.26 m), so the gap segment's size against its neighbours changes along
> the sweep, and PyNEC's delta-gap impedance moves with it. Read convergence
> from a point-gap engine (B-spline).

Measured on the catalog dipole, 8 … 68: NEC-2 and sinusoidal R 59.9 → 71.7 Ω,
B-spline 70.72 → 70.8 Ω. It shows bottom-left with the other sweep
advisories, on this view and beside the Smith trail.

## The old "convergence sweep" switch

It becomes this view's analysis with parameter = density. One runner, one
result: it runs when the view is on screen, or when the switch is on and the
Smith chart is (the old condition). The `convergence_sweep` settings key and
the label stay, so no `settings.toml` breaks; with a knob chosen in the view,
the switch's trail follows it and its tooltip says so.

## Mobile

The view joins the carousel when pinned. The header sits in the page flow
above the chart and wraps; the chart takes the carousel width; a tap reads
the nearest point.

## Phases

**Phase 1:** `/param_sweep` + alias; the view (off by default in the
picker); the twin-axis chart with log x, per-axis ranges, readouts, end
values, the current-value guide and `Z*`; the Smith trail generalised; the
switch migrated; the gap-fed advisory; "Sweep this knob".

**Phase 2:** one panel per slot with lockable ranges; persisting the
parameter and ranges; refinement along x; a density preset from the slot's
converged N (×¼ … ×4); group and frequency-linked knobs; CSV export.
