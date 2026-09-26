# Z vs parameter view

AC6LA's SimNEC convergence charts (QRZ 1003328 #163) plot the feed R and X
against the segment count on a log axis, R on the left and X on the right,
each on its own range, with value boxes at the ends. The workbench's
convergence sweep drew only a trail on the Smith chart. This view is that
chart for **any** parameter: the mesh density, or any numeric design knob.
The CLI got the same chart first (`sweep --log --panels --callouts`); this
note follows its findings.

## The parameter

- **Choices:** "density" (the request's `n_per_wire`, the nominal density in
  segments per λ/4 at the design frequency) or any visible `float`/`int` knob
  of the design's top level. The x axis is the **nominal** value the user
  set, never the engine's achieved segment count: that is the number the
  user can act on, and it is the same on every engine.
- **Not sweepable, phase 1:** enum/bool knobs, group (per-band) knobs, and
  knobs that drive a frequency (`linked_to_design_freq`,
  `link_meas_freq_to_param`). The measurement frequency stays fixed during a
  knob sweep; a knob that moves it would make the sweep a frequency sweep in
  disguise. A deck with fixed segment counts has no density to sweep, so
  "density" is not offered there.
- **Default range.** Density: the old switch's ladder, 8 … 68 in 7 log steps,
  kept as the literal `8 12 17 24 34 48 68` (the CLI's `NOMINAL_NSEGS_LADDER`)
  so the migrated trail and its `Z*` are unchanged. A knob: its own
  `min`…`max` from `ui_params`, or ±20 % of its value when it declares none,
  11 linear points.
- **Spacing and rounding.** Linear or geometric (`log`), the same rule as the
  CLI's `gen_xs`: a geometric ladder rounds an integer parameter (density, an
  `int` knob such as an SY segment knob) to integers and drops duplicates, so
  10 … 500 × 20 solves only whole counts. Points are clamped to 2 … 41.
- **Where it is picked:** the view's own header (parameter, from, to, points,
  lin/log), plus **Sweep this knob** in the knob's right-click menu, which
  selects the knob, resets the range to its default, and opens the view.
  The choice is session state (per tab), reset to density when a design
  switch drops the knob.

## The backend

One streaming endpoint, `POST /param_sweep`: a solve request plus
`param` and `values[]`. Each point is the request with `param` overridden
(`n_per_wire` for density, the knob's top-level field otherwise) and solved
on **the request's own engine**, as the optimizer does since #1743, through
the same `_solve_z_only`. Admission (`_admit`, kind `converge`), the per-point
size check, the lane turn and cancel-on-disconnect are `/converge`'s,
unchanged: the new endpoint is `/converge`'s body with the override
generalised. Records are `{param, value, z_re, z_im, solver}` (+ per-feed Z),
and the closing record carries `advisories`.

`/converge` stays as a **thin alias** (`param = n_per_wire`,
`values = n_values`, old record key `n_per_wire`). The frontend migrates to
`/param_sweep`; the alias costs a few lines and keeps a tab running the old
bundle working across a server restart and keeps scripts working.

An unknown or non-numeric `param` is a 422 before any solve.

## The chart

- R in red on a **left** axis, X in blue on a **right** axis, each with its
  own range popover (**Auto**, which fits that trace, plus a custom min/max).
- **log/lin x** toggle in the header; density defaults to log, knobs to lin.
- Circles at every point, a value box at the first and last points
  (`N=8 · R 70.72 · X −10.32`), and a **hover readout** at the nearest point.
- The **current value** as a dashed vertical guide, with the live solve's R
  and X as bright dots on it. It moves as the knob is dragged **without
  re-sweeping** (the #1755 lesson): the swept knob, and `n_per_wire` for a
  density sweep, are exempt from the sweep's request signature, since every
  point overrides them.
- For density, the **Richardson estimate** `Z*` (in 1/N, as before) as a
  dotted line on each axis, labelled.

## The Smith trajectory

The convergence trail generalises to the parameter's trail: the same polyline
with the hollow ring at the first value and the filled disc at the last, now
labelled with the parameter's values at both ends; the diamond `Z*` only for
density. The bottom-left caption reads `length_factor: 0.8 → 1.25`.

## Multiple slots

Phase 1 sweeps the **active slot only**, on that slot's engine; switching the
slot re-sweeps. One panel per engine (A/B/C side by side, ranges lockable
across them) is phase 2: it needs one stream per slot and a per-slot lane
story, and the single-slot view is already the SimNEC chart.

## Refinement

Not in phase 1. The #744 planner's curvature test would transfer (samples are
a curve in x), but a density ladder is chosen for Richardson, not for
flatness, and a knob sweep of 11 points is cheap to re-run denser by hand.

## The gap-fed warning

Condition (server-side, density sweeps only): the engine models the source
as a **delta gap** (NEC-2, PyNEC, momwire `sinusoidal`, or any momwire model
with `feed_model = segment`) **and** the design is **gap-fed**: an excited
wire shorter than 10 % of the design's longest wire (the invvee's 0.1 m feed
wire is 4 %). Wording:

> Density here mostly measures the delta-gap feed, not the antenna: the
> source sits on a 0.10 m feed wire (4 % of the longest wire), and a
> delta-gap engine's impedance there moves with the gap segment's size. Read
> convergence from a point-gap engine (B-spline).

(Measured on the catalog dipole, 8 … 68: NEC-2 and sinusoidal R 59.9 → 71.7
Ω, B-spline 70.72 → 70.8 Ω.)

## The old "convergence sweep" switch

It becomes this view's analysis with parameter = density. One runner, one
result: it runs when the view is on screen, or when the switch is on and the
Smith chart is on screen (the old condition). The settings key
`convergence_sweep` stays, so nobody's `settings.toml` breaks, and the label
stays "convergence sweep"; with a knob chosen in the view, the Smith trail
follows the view's parameter and its caption names it.

## Mobile

The view joins the carousel when pinned. The header wraps to two rows
(parameter + points; from/to + log), the chart takes the carousel width, and
the hover readout follows a tap.

## Phases

**Phase 1 (this PR):** `/param_sweep` + alias; the view (off by default in
the picker); the twin-axis chart with log x, per-axis ranges, readouts, end
values, the current-value guide, `Z*`; the Smith trail generalised; the
switch migrated; the gap-fed advisory; "Sweep this knob".

**Phase 2:** one panel per slot, with lockable ranges; persisting the chosen
parameter and ranges; adaptive refinement along x; a density preset from
the slot's converged N (×¼ … ×4); group and frequency-linked knobs; CSV
export of the points.
