# Sweep framework, step 1: the analysis spec (proposal for A1 and A2)

Status: **decided, 2026-09-28** (the answers are recorded at the end). Nothing
here is built yet: step 2 implements it, CLI-first. This page
answers axis A1 (what `build_analyses()` returns) and the part of A2 that the
examples force (knob roles). It is tested on paper against all seven driving
examples in `sweep-framework-examples.md`: if an example needs a special
case, the types are wrong. The names are proposals too; renaming is cheap now
and expensive later.

## The shape in one paragraph

An **analysis** is a declarative, frozen value that a design's
`build_analyses()` returns, and nothing runs when it is built. It has:

- ONE **sweep**, the thing on the x axis: a knob, or a role such as
  frequency, density or height. It can have a range or explicit values, lin
  or log.
- Zero or more **crosses**, the things compared as separate curves: engines,
  grounds, measurement planes, designs, or a second knob's values (a family).
- The **views** it draws: R/X, SWR, S11, Smith, a map, a table.
- The **references** drawn on them: R = Z0, X = 0, an SWR threshold.

The CLI and the workbench both read the same value. An analysis prints back
as the Python that makes it, which is what the UI's "suggest the commands"
needs.

## The types

```python
from antennaknobs import analyses as an

# ── what varies: the x axis ─────────────────────────────────────────────
an.Sweep(
    knob,  # a knob name ("length_factor"), or a role:
    #   an.FREQUENCY, an.DENSITY, an.HEIGHT
    lo=None,
    hi=None,  # None: the design's own (see "Defaults")
    points=None,  # None: the role's / knob's default count
    values=None,  # explicit values instead of lo/hi/points
    spacing="lin",  # "lin" | "log"
)

# ── what is compared: one curve per combination ─────────────────────────
an.Cross(engines=("momwire:bspline", "nec5"))  # engine specs, as --engine takes
an.Cross(grounds=("free", "finite:13,0.005"))  # ground specs, as --ground takes
an.Cross(planes=("rig", "feed"))  # measurement planes (network ports)
an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex"))  # other designs/variants
an.Cross(step=an.Sweep("angle_deg", values=(0, 15, 30)))  # a family over a 2nd knob

# ── what is drawn on it ──────────────────────────────────────────────────
an.Ref(r=(50,), x=(0,), swr=2.0)  # reference lines; z0 comes from the session

# ── the analysis ─────────────────────────────────────────────────────────
an.Analysis(
    name,  # shown in the workbench's picker and the CLI's list
    sweep,  # a Sweep, or (Sweep, Sweep) for a map
    cross=(),  # Cross or a tuple of them: their product
    # view OBJECTS with their own options: an.Rx(), an.Swr(scale="rho"),
    # an.S11(), an.Smith(), an.Map(), an.Table()
    views=(an.Rx(),),
    references=an.Ref(),
    hold=None,  # an.Hold: optimise at every point (E8, E9)
    ground=None,
    engine=None,  # None: the session's own
)

# ── an optimisation held at every sweep point (E8, E9; added 2026-09-28) ─
an.Hold(
    objective,  # the optimizer's own names: "swr" | "resonance" | "match_z0"
    adjust,  # the knobs re-solved at each point, e.g. ("length_factor",)
    z0=None,  # None: the session's
    warm_start=True,  # seed each point from the previous one (continuation)
)
# a square system only: match_z0 takes exactly 2 knobs, resonance exactly 1
an.Knobs()  # a view: the held knobs against x

# ── the library (A2): generic analyses for any design ──────────────────────
# Analysis("convergence", Sweep(an.DENSITY), views=(Rx(), Table(), Smith()))
an.convergence(**kw)
# Analysis("band SWR", Sweep(an.FREQUENCY), views=(Swr(),), references=Ref(swr=2.0))
an.band_swr(**kw)
# Analysis(name, Sweep(name), views=(Rx(), Smith()))
an.knob(name, **kw)
```

### Roles (A2)

A role says what a knob MEANS, so a generic analysis can find it on any
design. It is declared where the per-knob UI metadata already lives:

```python
default_params = {
    "base": 7.0,
    "ui_params": {"base": {"min": 1.0, "max": 16.0, "role": "height"}},
}
```

- `an.FREQUENCY` is built in: the measurement frequency.
- `an.DENSITY` defaults to `nominal_nsegs` on a catalog design. A deck
  declares its own. A SimNEC `JamSegments($segs)` knob gets
  `role: "density"` from the importer.
- `an.HEIGHT` and any future role must be declared.
- A role the design lacks makes the analysis **unavailable on that design,
  by name** ("this design declares no height knob"). It is not an error.

### Defaults ("the design's own")

| sweep | `lo`/`hi`/`points` when None |
|---|---|
| `an.FREQUENCY` | the design's measurement range. For a deck, its own sweep (a SimNEC Generator sweep, an `FR` card). Otherwise the workbench's band policy. |
| `an.DENSITY` | the app's ladder, 8…68 (7 rungs) |
| a knob or another role | the knob's `ui_params` min/max, 11 points |

### Crossing, and refused cells

- Several `Cross` values multiply: engines × designs gives one curve per
  pair.
- A combination an engine cannot serve (NEC-2 on the apex knot, E7) is a
  **refused cell**. It is drawn as a named gap in the legend, and the rest
  of the analysis runs.
- **The curve cap is 6.** A product over the cap is refused when the
  analysis is **listed**, not when it runs.

### What the spec deliberately leaves out

- **Layout** (which pane, how many graphs): the view decides. §3.2
  principle 6 is still open.
- **Pins:** a pin is data captured from a run of an analysis, never part of
  the spec.
- **Imperative hooks:** there is no `custom=callable` (A1 (c)) until an
  example needs one. None of the seven does.

## The seven examples, written in it

**E1, convergence on three engines:**

```python
def build_analyses(self):
    return [
        an.convergence(
            cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec5")),
            ground="finite:13,0.005",
        ),
    ]
```

**E2, tuning two knobs to a Z0:**

```python
def build_analyses(self):
    lf = an.Sweep("length_factor", 0.90, 1.06, points=33)
    refs = an.Ref(r=(50, 75), x=(0,))
    return [
        an.Analysis(
            "tuning family",
            lf,
            cross=an.Cross(step=an.Sweep("angle_deg", values=(0, 15, 30, 45, 60))),
            references=refs,
        ),
        an.Analysis(
            "tuning map",
            (lf, an.Sweep("angle_deg", 0, 60, points=25)),
            views=(an.Map(),),
            references=refs,
        ),
    ]
```

**E3, R/X against height, three grounds** (the invvee's `base` declares
`role: "height"`):

```python
def build_analyses(self):
    return [
        an.Analysis(
            "height",
            an.Sweep(an.HEIGHT, 2, 20, points=37),
            cross=an.Cross(grounds=("free", "finite:13,0.005", "finite:5,0.001")),
            references=an.Ref(r=(50,), x=(0,)),
        ),
    ]
```

**E4, band SWR on the deck's own sweep** (this is also the deck stub A4
would generate, since `an.FREQUENCY` with no range means the file's
14.0–14.35 MHz):

```python
def build_analyses(self):
    return [an.band_swr(views=(an.Swr(scale="rho"),))]
```

**E5, one sweep at three network planes:**

```python
def build_analyses(self):
    return [
        an.band_swr(
            name="rig vs antenna",
            cross=an.Cross(planes=("rig", "T1", "feed")),
            views=(an.Swr(), an.Rx()),
        ),
    ]
```

**E6, convergence through the deck's own density knob** (the importer marks
`tmp_segs` with `role: "density"`):

```python
def build_analyses(self):
    return [
        an.convergence(
            sweep=an.Sweep(an.DENSITY, 10, 500, points=20, spacing="log"),
            cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec5")),
        ),
    ]
```

**E7, two feed spellings on one convergence chart** (2 × 3 = 6 curves, the
cap; razor-2p stands in for NEC-5; NEC-2 × apex is the refused cell):

```python
def build_analyses(self):
    return [
        an.convergence(
            cross=(
                an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex")),
                an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec2")),
            ),
        ),
    ]
```

**What writing them showed:**

- **No special case was needed.** Every example is a sweep, crosses, views
  and references.
- **Two small additions came from the examples**, not from design ahead of
  them:
  - E4's SWR scale is a view option. That's what settled Q2 in favour of
    view objects.
  - `name=` overriding a library default (E5).
- **The library carries most of the weight.** Four of the seven are one
  library call with keywords. That's A2's case for option (a), a shared
  library, over inheritance alone.

## Addendum: `hold` (Steve, 2026-09-28)

Steve asked to future-proof the spec for optimising at each sweep point:
match 50 with length and angle while the height sweeps (E8), and hold the
match with length while the angle sweeps (E9). Both are now driving examples,
measured with the workbench's own optimizer.

The spec gains:

- one optional `Analysis.hold`: an `an.Hold`, written in the optimizer's own
  objective names, with its free knobs, Z0 and warm start;
- one view, `an.Knobs()`.

Step 2 adds both as DATA only: they print back as code, and a held analysis
is refused at run time by name. Running holds is a later step.

```python
# E8
an.Analysis(
    "match vs height",
    an.Sweep(an.HEIGHT, 2, 20, points=37),
    hold=an.Hold("match_z0", adjust=("length_factor", "angle_deg"), z0=50),
    views=(an.Rx(), an.Knobs()),
)
# E9: with one free knob the square system is resonance, not a match
an.Analysis(
    "resonance vs angle",
    an.Sweep("angle_deg", 0, 60, points=25),
    hold=an.Hold("resonance", adjust=("length_factor",)),
    views=(an.Rx(), an.Knobs()),
    references=an.Ref(r=(50,)),
)
```

## Decisions (Steve, 2026-09-28)

1. **Declarative specs (A1 (a)): yes.**
2. **Views take options: yes.** Views are objects (`an.Rx()`,
   `an.Swr(scale="rho")`, `an.Map()`, …), not strings.
3. **Roles live in `ui_params`: yes.** It carries more per-knob information,
   beside `min`/`max`/`hidden`.
4. **Crosses multiply**, with a **curve cap of 6**.
5. **Library names:** `convergence`, `band_swr`, `knob`, in the module
   `antennaknobs.analyses`, imported as `an`: yes.

Step 2 (the CLI-first implementation of E1, E3 and E6) starts from this page.

## Rulings after step 2 (Steve, 2026-09-28)

The step-2 build (#1786) surfaced five questions:

1. **E7 and the cap.** E7 is 2 feed spellings × 3 engines (B-spline,
   razor-2p, NEC-2) = 6 curves, the cap. NEC-5 isn't needed where razor-2p,
   its formulation, is present. NEC-2 × the apex knot stays as E7's refused
   cell (#1787).
2. **Names.** An analysis's name defaults to its library name
   ("convergence", "band SWR"). Name one explicitly (`name=`) only when a
   design has two of the same kind. Two alike are refused when listed, with
   that fix in the message. A design's own analysis replacing the library
   one of its name is the intended override, not a clash.
3. **Spacing.** `Sweep(spacing=None)`, the default, is the sweep's own:
   geometric for density, linear otherwise. `"lin"` or `"log"` written
   explicitly wins, except that a linear density ladder is refused, since
   Z∞ reads a power law.
4. **The deck stub stays late** (the last step). Steps 3–6 are testable on
   catalog designs, which already have `build_analyses()`.
5. **The step plan, with the workbench early:**

   | step | what | driving examples |
   |---|---|---|
   | 2 ✅ | analyses in Python, roles, `analyze` (knob / density / height; crosses over engines and grounds) | E1, E3, E6 |
   | 3 | the workbench lists a design's analyses and runs those today's views draw | E1, E3 |
   | 4 | the frequency sweep as an analysis; SWR / S11 / Smith views (ρ scale, threshold, 2:1 BW); frequency's default range is the design's or deck's own | E4 |
   | 5 | crosses over planes, designs and a second knob (families); the map view | E2, E5, E7 |
   | 6 | hold: an optimisation at each point, warm-started, skipping the optimizer's seed after the first point | E8, E9 |
   | 7 | the UI writes the Python ("copy as analysis"); the deck stub | E4, E5 on Dan's files |

   The CLI leads each capability, and the workbench follows it from step 3
   on.

## Steps 3 and 4 done; questions before step 5 (2026-09-28)

Step 3 merged as #1788 (the workbench's analysis picker) and step 4 as #1790
(frequency analyses, the SWR / S11 / Smith views, one default-range rule).
Both shipped in v0.91.0.

**Rulings on #1790 (Steve):**

1. **The band policy applies to `sweep --swr` too.** With no `--range`, a
   band-locked design sweeps its band, the same rule `analyze` and the
   workbench read.
2. **The views no step planned get one, step 5:** the workbench's table,
   R/X against frequency, and a frequency analysis given explicit values
   rather than a range.

**Open questions for step 5.** Each needs a ruling before code.

1. **More than one sweep graph** (§3.2 principle 6). Today the workbench
   draws one chart per view. Step 5's crosses and families need several
   curves on one chart. Do we also want several charts at once, or does one
   chart with a picker stay the rule?
2. **A cross the workbench cannot draw whole.** Today it runs the session's
   own cell, with a note. Step 5's crosses over planes, designs and families
   draw every cell. Does the engines × grounds cross follow suit, or does
   "the session's cell" remain the workbench's answer for those?
3. **Views and quantities a design defines itself (A1 (c)).** Today the
   declarative half of `an` is open and the computing half is closed:
   - **Open:** a design can write its own library-style functions (anything
     returning an `an.Analysis`) and its own roles (`an.Role("tilt")` with
     `"role": "tilt"` on the knob).
   - **Closed:** the views (Rx, Swr, S11, Smith, Table, Map, Knobs), the
     kinds of cross, and the quantities, all derived from the driving-point
     Z. There is no gain, F/B or pattern quantity, and no `custom=callable`.
     A design's own `View` subclass is refused by name, "not a view
     antennaknobs draws" (#1793; it was a bare `KeyError`).

   Options:
   - (a) **Stay closed.** Add built-in views as examples need them. Gain
     against frequency or height is the obvious next one.
   - (b) **A quantity view.** A design supplies a function from a solved
     antenna to one number, with its label and unit, and the generic line
     chart draws it against the sweep. This needs two rulings: what the
     function is given (Z only is cheap; the far field costs a pattern per
     point), and running design code in the workbench (the trust gate
     already covers it, since a design is code).
   - (c) **`custom=callable` per analysis.** The most general, and the
     hardest to draw generically or print back as Python.

   **Recommendation:** (b), after (a)'s built-in gain view. (b) keeps
   analyses declarative, and gain gives it a first real example.

   It is related to A3, where user analyses live: a quantity a user defines
   is only useful across antennas if something other than one design can
   hold it.

**Ruling on question 1 (Steve, 2026-09-28).** Step 4's workbench shape is
inconsistent. Picking "band SWR" in the Z vs parameter header jumps to a
different chart, and that chart draws nothing when the freq-sweep switch is
off in the Smith or VSWR view. The direction:

- **A chart with its own analysis picker.** Picking an analysis draws it in
  that chart, whatever it sweeps (a knob or the frequency). It does not hand
  off to another view, and it does not depend on a switch elsewhere.
- **Duplicate the chart window**, so a second, third or fourth chart can
  each pick an analysis.

This answers "more than one sweep graph": several charts, each with a
picker. Questions it leaves for the design:

- does a chart re-run live while a knob drags, or on Run as the Z vs
  parameter view does today? Several charts under the one-solve-at-a-time
  scheduler multiply the cost of live;
- how does the picker chart relate to the existing VSWR / S11 / Smith views
  and the freq-sweep switch: does it replace them, or do they stay as the
  live views?
- do duplicated charts persist in `settings.toml` or a layout?

**Ruling on "live or on Run" (Steve, 2026-09-28).** A chart runs its
analysis on **Run**, because these can take a long time. A switch lets it
re-run on its own **after a dwell** (the knobs have stopped moving), and an
explicit click always works. Picking an analysis is itself an explicit act,
so a pick runs it. Still open: whether the dwell switch is per chart or one
for the session (the track-while-drag switch is one global switch,
precedent), and the dwell's length.

**Ruling on the dwell switch (Steve, 2026-09-28): per chart**, not one for
the session. That fits the layout's split, which is already strained:

- **The left side is inputs:** the design and its knobs.
- **The right side is outputs:** the charts.
- The view selector and the carousel already sit on the right, because they
  configure what an output shows.

So a chart's own controls live on the chart: its analysis picker, Run, the
re-run-after-dwell switch, and its SWR scale and threshold. They say what
that chart computes and draws. They are not design inputs and do not belong
on the left.

The line to watch: an analysis's sweep range is an input to the analysis
but not to the design, so it belongs on the chart too. The measurement
frequency dial, the design's own, stays left. Step 5's design should state
which side every control lands on.

**Ruling on persistence (Steve, 2026-09-28): only the `.py` file is
remembered between sessions.** The analyses are specified there. Duplicated
charts, a chart's pick, its dwell switch and its range edits last for the
session only. They are not written to `settings.toml` or to a layout.
Keeping a chart setup means putting it in the design's `build_analyses()`,
which step 7's "copy as analysis" makes one click.
