# Sweep framework: pinned sweeps (design note)

Status: **draft for Steve's review, 2026-09-29.** No code yet. Pins were
item 1 of AK#1757 ("the ability to pin a sweep from a previous run: a
different engine, ground model, or design") and were set aside in step 5
("pins come after"). This note brings them back on top of step 5's charts.

## What a pin is, and how it differs from a cross

- A **cross** recomputes. A chart that crosses engines, grounds, planes,
  designs or a second knob re-solves every curve whenever it runs. It
  answers "how do these alternatives compare *now*".
- A **pin** is a frozen snapshot of one curve. It never re-solves. It
  answers "how does what I have now compare with what I had *before* I
  changed something": a knob, the design, a slot's engine, a ground's
  constants, even another design tab.

Both draw on the same chart. A pin is dashed, in its own colour, and has no
live marker.

## What a pin holds

It holds the solved **Z at each x**, not the pixels of a view. Every view in
the workbench today (Smith, SWR, S11, R/X) is Z-derived, so one pin draws in
any of them, and switching the chart's view keeps the pin.

- **x:** its kind (frequency / knob / density), the knob's name, and the
  values.
- **Z(x):** complex, per point, for one port.
- **Z0:** the reference the pin was taken at.
- **Context:** the design and variant, the knob values that differ from the
  design's defaults, the slot's engine and basis, the ground slot and its
  constants, and the measurement plane. It is shown as a label, e.g.
  "invvee:dipole · NEC-5 · Sommerfeld 13/0.005 · height 9.5".

## Where pins live and where they draw

- **Shell-level, like pattern pins** (`App.tsx`'s `PinnedPattern` list). A
  pin outlives the design tab that made it. That is what makes "a different
  design" work: pin in one tab, compare in another.
- **Session-only.** Pins are kept in memory, never in `settings.toml` and
  never in a layout. That is the step-5 ruling: only the `.py` persists
  between sessions.
- **A chart draws the enabled pins whose x matches its own:**
  - a frequency pin on any frequency chart, over the part of its range that
    overlaps;
  - a knob pin on a chart sweeping a knob of the same name;
  - a density pin on a density chart.
- **A pin that cannot draw** stays in the list, greyed, with its reason
  (#1757's rule), e.g. "sweeps height; this chart sweeps frequency".
- **Pins sit outside the curve cap.** The cap of 6 bounds a cross's curves.
  Pins are drawn on top and share the ghost palette (4 colours today, the
  same as pattern pins).

## The controls, and which side they land on

All of them are on the chart (right side, the step-5 rule):
- **Pin** on the chart's header. It snapshots the chart's curves as they
  stand. It is disabled while a run is in flight or a curve is refused.
- **The legend's pins section:** each pin's label and colour, show/hide,
  delete, and CSV export (x, R, X, and the SWR at the pin's Z0).
- **Hover** reads each pin's value at the hovered x, beside the live curves'.

## Questions for review

1. **Pinning a multi-curve chart.** A cross can draw up to 6 curves.
   (a) Pin makes one pin per curve, each labelled by its cell. (b) Pin makes
   one pin *group*, a single list row that shows and hides together.
   (c) Each curve's legend entry gets its own pin, plus a "pin all".
   Recommendation: **(a) for now**; (c) later if the list gets crowded.
2. **Show/hide per chart or global?** Pattern pins are global: one enabled
   flag, drawn on every pattern view. Recommendation: **global**, the same
   precedent. The per-chart x match already keeps a pin off charts where it
   means nothing.
3. **Matching knob pins by name across designs.** A pin of `height` from
   design A would draw on design B's `height` chart. Recommendation:
   **yes**, with the design in the label. Comparing designs is the point.
4. **Z0.** SWR and S11 depend on the reference. Recommendation: **draw a
   pin at its own Z0**, which is faithful to the snapshot, and say "Z0 75 Ω"
   in its label when that differs from the chart's.
5. **Ghost palette size.** Pattern pins cycle through 4 colours. Keep 4,
   or grow the palette for sweeps?

## Relation to step 7 (the UI writes the Python)

A pin is ad hoc and never persists, as ruled. Step 7's "copy as analysis"
can still carry a pin's *intent* where it has one. A pin that differs from
the live chart only along a crossable axis (another engine slot, another
ground slot, another design) can be written into the `.py` as that cross,
so that it re-solves next session. A pin that differs by a knob drag has no
such spelling; it stays a pin. That decision belongs to step 7 and is only
noted here.

## Units

1. **The pin model:** snapshot, x matching, drawing on R/X and on the Smith
   trail, the Pin button, the legend's pins section (show/hide/delete).
2. **The Z-derived views:** SWR and S11 drawing (with the pin's own Z0),
   hover values, CSV export.

Both units are frontend-only. The server already returns Z per point.
