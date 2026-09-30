# Sweep framework, step 7: studies, states, and keeping what you built (design note)

Status: **draft for Steve's review, 2026-09-30.** No code yet. This takes Steve's
framing from 2026-09-30:

> "We need a way to store cases like E7 that don't really belong in with a
> particular Builder but are more cross builder. It is the difference between a
> method of a class and a function in a module that works off of multiple
> objects. I think we also need a way to save pinned far-field patterns as well
> in a similar way."

## What exists (inventory)

- **`Builder.build_analyses()`** (builder.py:244): a *method*. Its analyses
  implicitly target `self`, "this design". Only `dipoles.invvee` defines one in
  the catalog.
- **The spec** (`antennaknobs.analyses`, imported as `an`): `Analysis`, `Sweep`,
  `Cross` (engines, grounds, planes, **designs**, step), the views (`Rx`, `Swr`,
  `S11`, `Smith`, `Map`, `Table`, `Knobs`), `Ref`, `Hold`, and the library
  (`convergence`, `band_swr`, `knob`).
- **`to_code()`** already renders any spec back to Python. That is how the chart's
  "analyses as Python" panel works, so the "translate to Python" half of step 7
  exists for anything the spec can say.
- **Pins** (v0.93.0): sweep pins and pattern pins, both shell-level and
  session-only, as ruled.
- **Where E7 lives today:** inside `invvee.build_analyses()`, crossed
  `designs=("dipoles.invvee", "dipoles.invvee_apex")`. That is the misfit Steve
  names. E7 is a study *of two designs*, not a property of invvee, and it
  shows up in invvee's picker but not in invvee_apex's.

## The gap, in three parts

1. **Studies.** An analysis that names its designs explicitly has no home except
   one of those designs' classes. It is a method where it should be a function.
2. **States.** A pin that differs from the live chart by a *knob value* ("height
   9.5 vs 12") has no spelling in the spec. The pins note said as much: "a pin
   that differs by a knob drag has no such spelling; it stays a pin". So a
   comparison you built with pins cannot be kept.
3. **Patterns.** The spec draws impedance against a swept x. A far-field
   comparison (the pattern pins' job) is not an analysis at all today.

## Proposal

### 1. Studies: module-level functions over several designs

A **study** is an `an.Analysis` that names its designs, returned by a module-level
function, not by a method:

```python
# dipoles/invvee.py, beside the classes (or any .py in the studies folder)
import antennaknobs.analyses as an

def build_studies():
    return [
        an.convergence(
            name="feed spelling (E7)",
            cross=(
                an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex")),
                an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec2")),
            ),
        ),
    ]
```

- **The rule that separates the two:** an analysis in `build_analyses()` may omit
  `designs=` ("this design"). A study must name them, since it has no `self`.
  Otherwise it is the same spec, the same runner, the same views and the same
  `to_code()`.
- **Where studies are found:**
  - (a) a `build_studies()` function in any catalog design module;
  - (b) `.py` files in a user **studies folder**, `~/.antennaknobs/studies/`, a
    sibling of `designs/`, under the **same trust gate** (`allow`) as user
    designs, since a study file is Python.
- **Where they show up:**
  - the CLI: `antennaknobs analyze --study "feed spelling (E7)"` and `analyze
    --list-studies`;
  - the workbench: every chart's picker gets a **Studies** group below the
    design's own analyses, listing every study that **includes the tab's design**.
    So E7 appears on both the invvee and the invvee_apex tabs, and on no others.
- **E7 moves** from `invvee.build_analyses()` to `build_studies()` in that module.

### 2. States: a knob setting as a crossable axis

A new cross kind: **named knob overrides** on a design.

```python
an.Cross(states=(
    an.State("as built"),                        # the design's defaults
    an.State("tall", base=12.0),
    an.State("tall, narrow", base=12.0, angle_deg=20),
))
```

- A state is to knobs what `designs=` is to builders: each state is one cell,
  solved with those knob values over the design's defaults.
- It crosses and multiplies like the others, under the same cap of 6.
- **In a study, a state can name its design:** `an.State("apex, tall",
  design="dipoles.invvee_apex", base=12.0)`. That lets a study compare specific
  settings of different designs, not only their defaults.
- **Why it matters:** it gives every pin a spelling. A pin's context is exactly
  (design, changed knobs, engine, ground, plane), which is a cell of
  `designs × states × engines × grounds × planes`. So "keep this" can turn a set
  of pins into a study that re-solves them next session, which the pins note said
  was impossible.

### 3. Patterns: a no-sweep analysis with a pattern view

- **An analysis without a swept x** (`sweep=None`) is one solve per cell at the
  measurement frequency.
- **New views** draw what the pattern pins draw today:
  - `an.Elevation(az=0)`: an elevation cut;
  - `an.Azimuth(el=10)`: an azimuth cut;
  - `an.PatternTable()`: the pattern metrics table the pin compare table
    shows (gain, F/B, take-off angle).
- **Crossed** over designs, states, engines and grounds like everything else:

```python
an.Analysis(
    "tall vs as-built pattern",
    sweep=None,
    cross=an.Cross(states=(an.State("as built"), an.State("tall", base=12.0))),
    views=(an.Elevation(az=0), an.Azimuth(el=10), an.PatternTable()),
)
```

- **Saving pinned patterns:** the pattern compare table gets **keep as study**,
  which turns its pins into exactly this, with each pin a state or design cell.

### 4. Keeping what you built: "keep as study" / "copy as analysis"

The UI never needs its own saved format. It writes Python, per the step-5 ruling
that only the `.py` persists:

- **copy as analysis** (a chart about the tab's design only): the `to_code()` text
  on the clipboard, to paste into the design's `build_analyses()`;
- **keep as study** (anything spanning designs, or built from pins): a study
  function. It is either copied, or saved as a new file in the studies folder
  (local workbench only, never hosted).

Saving puts a Python file on disk, so it needs the trust question answered
(question 4).

## Questions for review

1. **Where studies live.** (a) `build_studies()` in design modules plus a user
   studies folder; (b) the studies folder only; (c) a studies package in the
   catalog (`designs/studies/*.py`) plus the user folder. Recommendation: **(a)**.
   E7 sits beside the two designs it compares, and user studies sit beside user
   designs.
2. **States.** Is a knob-override cross the right way to make pins keepable?
   Recommendation: **yes**, named states with optional `design=`.
3. **Patterns.** Is the first set of views right (elevation cut, azimuth cut,
   pattern metrics table), with 3D later? Recommendation: **yes**.
4. **Saving from the UI.** (a) copy to the clipboard only; (b) also "save as a
   study file" on a local workbench. If (b), is a file the app itself wrote
   trusted as written, or does it go through `allow` like any other file?
   Recommendation: **(b), trusted as written**, because the app wrote it from a
   spec and never from free text, and the file says so in a header comment. An
   edit changes its hash, so a hand-edited study asks again, like any design.
5. **Studies in the picker.** Are studies that include the tab's design listed
   under a Studies group? Recommendation: **yes**, so a study is reachable from
   every design it names.

## Units (after review)

1. **Studies:** the CLI first (`build_studies()`, discovery, `analyze --study`,
   the studies folder with its trust gate). E7 moves.
2. **States:** the cross kind, in the CLI and the workbench. Pins' "keep as study"
   for sweep pins.
3. **Patterns:** the no-sweep analysis, the pattern views, "keep as study" on the
   pattern compare table.
4. **The Studies group** in the workbench picker, and "copy as analysis" / "keep
   as study" on charts.
5. **The deck stub** (unchanged from the plan: it comes last).
