# Sweep framework, step 5: charts that pick their own analysis (design note)

Status: **draft for Steve's review, 2026-09-28.** It collects the rulings made
on 2026-09-28 (recorded at the end of `sweep-framework-spec.md`) into one
buildable plan. No code yet.

## What step 5 delivers

1. **Crosses over measurement planes, designs and a second knob**
   (families), and the **map** view, in the CLI first (E2, E5, E7).
2. **The analysis chart** in the workbench. A chart owns an analysis
   picker, Run and a dwell switch, and draws whatever it picked, whether a
   knob sweep or a frequency sweep, in place.
3. **The VSWR, S11 and Smith views fold into it.** They stop being
   standalone views. The default chart is a frequency sweep on the Smith
   chart, so the workbench opens looking about as it does today.
4. **Duplicate a chart**, for a second, third or fourth chart.
5. **Multi-curve drawing** for crosses, and the views no step planned
   before: the workbench's table, R/X against frequency, and a frequency
   analysis given explicit values.

Out of step 5:
- pins (they come after);
- holds (step 6);
- the generated Python and the deck stub (step 7);
- a gain view (Q3 (a): built-in views are added as examples need them);
- user-defined views and quantities (wanted later, not now).

## The chart

- **Picker.** It lists the design's analyses (`POST /analyses`). Picking
  one runs it, since a pick is an explicit act.
- **Run.** It re-runs the chart's analysis.
- **The dwell switch, one per chart.** On, the chart re-sweeps once the
  knobs settle (500 ms), exactly as today's freq-sweep checkbox does.
  - It applies to knob sweeps too, which rebuild per point and so cost
    more. That is why the switch is per chart.
  - The freq-sweep checkbox goes away. Its meaning moves into this switch.
- **The live point.** The measurement frequency's Z marker and SWR readout
  follow a drag in every chart. Only the swept curve waits.
- **View options on the chart:**
  - Swr: scale (1–∞ / ρ), range popover, threshold and 2:1 readout;
  - Smith: zoom, and the param-sweep trail.
- **Engine and ground crosses** (question-2 ruling):
  - engines are a non-empty subset of the solver slots A, B and C, as
    checkboxes on the chart; the `.py`'s list preselects;
  - a listed engine no slot holds is a named refused cell, and a slot is
    never rewritten;
  - grounds run as written, as checkboxes.
- **Refused cells** appear in the legend by name, and the rest draws.

## Which side every control lands on

| control | side | why |
|---|---|---|
| the design, its knobs, the measurement-frequency dial | left (inputs) | the design's own |
| the solver slots and their gear menus, the session ground | left | the session's engine and ground, which every chart reads |
| a chart's picker, Run, dwell switch | right, on the chart | what that chart computes |
| a chart's sweep range edit, points, spacing | right, on the chart | an input to the analysis, not to the design |
| a chart's SWR scale, threshold, Smith zoom and trail | right, on the chart | how that chart draws |
| a chart's slot and ground checkboxes | right, on the chart | what that chart compares |

## Where charts live

The view rail (#684 / #700) already has pinned views (cap 6), a grid of up
to four cells, and per-viewer view preferences saved in the browser
(`akb.viewPrefs.v1`).

- An analysis chart is a view. "Duplicate" adds another instance, so the
  grid's four cells are the second, third and fourth charts.
- **Persistence (ruling):** only the `.py` is remembered.
  - A chart's pick, switch, range edits and duplicates are session-only.
  - Open for review: the rail's existing pinned-view preferences still
    persist in the browser. They say which views are shown, not what any
    chart computes. Keep them, or make the whole rail session-only?

## Units (CLI leads, then the workbench)

1. **CLI crosses and the map.** Planes (E5), designs (E7, with its refused
   NEC-2 × apex cell), families (E2's family), and E2's map as a heatmap.
   The oracle for each is the `sweep` command, or the per-cell solves
   themselves.
2. **The analysis chart.** A new view with the picker, Run, the dwell
   switch and the live point, drawing one curve. It replaces the picker in
   the Z vs parameter header, and the zparam view becomes this chart
   showing a knob analysis.
3. **Fold VSWR / S11 / Smith in.** The default chart is a frequency-sweep
   Smith chart. The old views' options move onto the chart, and the
   freq-sweep checkbox goes. The gate is a real-app drive: the default
   workbench looks about like today, and a knob drag moves the point live
   and re-sweeps after the dwell.
4. **Duplicate, and multi-curve.** Up to four charts in the grid; slot and
   ground checkboxes; planes, designs and families drawn as curves; refused
   cells in the legend.
5. **The views no step planned:** the table, R/X against frequency, and
   explicit frequency values.

Unit 1 stands alone. Units 2–5 are workbench work, suited to one stacked
arc. Unit 3 is the one that changes what every user sees on first open, so
it needs a live visual pass, not only tests.

## Questions for review

1. The rail's pinned-view preferences: keep them in the browser, or make
   them session-only too? (above)
2. When a picked analysis cannot run in the chart (a hold, before step 6),
   is it greyed in the picker with its reason, as today?
3. Unit 3 removes three views that `settings.toml` and saved pins may
   name. Do those names map to the default chart with the right view
   (vswr → a band-SWR chart on the Swr view), or reset to the default?
