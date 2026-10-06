---
title: Command line
description: Driving antennaknobs from the terminal — list, draw, sweep, analyze, pattern, optimize, compare, params, .nec export, and allowing user designs.
---

antennaknobs has a command-line interface for batch work. The subcommands:

```text
python -m antennaknobs {draw,sweep,analyze,optimize,pattern,compare_patterns,params,export,list,screen,allow,disallow}
```

| Command | What it does |
| --- | --- |
| `list` | List available designs (built-in and user) |
| `draw` | Draw the antenna geometry |
| `sweep` | Sweep a parameter or frequency |
| `analyze` | List or run a design's named analyses, and studies across designs |
| `pattern` | Plot the far-field pattern |
| `compare_patterns` | Overlay the patterns of several antennas / engines |
| `optimize` | Optimize an antenna's parameters |
| `params` | Print a design's knob values as paste-ready Python |
| `export` | Export the design as a NEC-2, NEC-4 or NEC-5 `.nec` card deck |
| `screen` | Show what a design file does that's unusual, without running it |
| `allow` | Allow a user design to run (it runs code on your machine) |
| `disallow` | Stop allowing a user design to run |

Since v0.81.0 a pip install also puts an `antennaknobs` command on PATH, so
`antennaknobs sweep ...` and `python -m antennaknobs sweep ...` are the same
thing; the Windows workbench zip carries the same command line as
`antennaknobs-cli.exe` (see [the workbench page](/start/workbench/#the-command-line)),
with no Python to set up. `--version` prints the antennaknobs and momwire
versions; `-v` / `-vv` are log verbosity, given before the command.

## Naming a design

Designs are addressed as `family.name` (the same names `list` prints):

```bash
python -m antennaknobs list            # arrays.bowtiearray, beams.yagi, loops.delta_loop, ...
```

Three spec forms work anywhere a `--builder` / `--builders` argument does:

- **`family.name`** — a catalog or user design.
- **`family.name:variant`** — a stored knob-set overlay
  (see [Variants are overlays](#variants-are-overlays)).
- **`@path/to/file.nec`**, **`@path/to/file.ssn`** or **`@path/to/file.maa`**
  — a NEC card deck (via [`read_nec`](/reference/nec-import/)), a SimNEC
  circuit (via the [SimNEC importer](/reference/simnec/#importing-ssn--design))
  or an MMANA-GAL model (via [the `.maa` reader](/reference/nec-import/#mmana-gal-maa-models)), loaded on
  the fly as a frozen-geometry design. No user-design stub to write:
  `draw`, `sweep`, `pattern`, `schematic`, and `export` all take it
  directly, and files mix freely with named designs in `--builders` lists —

  ```bash
  python -m antennaknobs compare_patterns --builders dipoles.invvee @measured/invvee.nec
  ```

  A station `.ssn`'s tuner chain rides along as the design's feed network,
  and its Generator sets the frequency. The `@` sigil keeps the grammar
  unambiguous (a bare `foo.nec` would parse as family `foo`, design `nec`),
  and an `@` spec never splits off a `:variant` suffix, so colons in paths
  (Windows drive letters) pass through. One shell trap: in **PowerShell**
  quote the whole spec, `--builder "@C:\decks\yagi.nec"` — an unquoted `@"`
  opens a here-string there and the path never reaches the program. The same
  files dropped in `~/.antennaknobs/designs/` become `user.<name>` designs
  with no stub (see [Importing a NEC deck](/reference/nec-import/#quick-start)).

## Patterns

```bash
# Far-field pattern of a Yagi, solved with momwire's default (B-spline) basis
python -m antennaknobs pattern --builder beams.yagi --engine momwire
```

Useful `pattern` flags: `--fn out.png` (write to a file instead of the screen),
`--ground free|pec|finite|finite:<eps_r>,<sigma>|mininec:<eps_r>,<sigma>`
(`finite-fast` for the reflection-coefficient model, and `mininec` for
EZNEC's [MININEC-type ground](/reference/web/#the-mininec-type-ground):
perfect-ground currents and impedance, a real-ground pattern), `--wireframe`, and
`--elevation_angle`. With no `--ground`, a catalog design is solved over
Sommerfeld average soil (`finite:13,0.005`), the same default the workbench
starts on.

## Sweeps

`sweep` plots impedance against measurement frequency by default; `--param
<knob>` sweeps any named knob instead. Add `--swr` to plot the curve as SWR
(against a 50 Ω reference by default, `--z0` to change it):

```bash
# SWR across the band
python -m antennaknobs sweep --builder dipoles.invvee --swr
# how SWR responds to the droop angle, at a fixed frequency
python -m antennaknobs sweep --builder dipoles.invvee --swr --param angle_deg
```

`--swr` frequency sweeps use the vectorized impedance sweep (one geometry,
many frequencies), so they are much faster than scripting one solve per
point; the R/X and Smith charts still solve one point at a time.

With no `--range`, an `--swr` frequency sweep covers the design's own range,
the same one `analyze` and the workbench use. That is, first match wins:

1. a file's own sweep (a `.nec` deck's `FR` card, a SimNEC Generator sweep),
   with its grid;
2. a design's `ui_params["sweep_range"]`, else its `meas_freq_range`;
3. its band policy: the amateur band holding its frequency when it is
   band-locked, else its `sweep_policy` factors;
4. ×0.8–×1.25 of `freq`, in 21 points.

Dan's `snDipoleVarLenSegs.ssn` sweeps its Generator's 14.0–14.35 MHz in 15
points. `--npoints` alone keeps that span and sets the count. `--center` or
`--fraction` asks for the relative window around a centre, as before. The
R/X, gain and pattern sweeps keep the ×0.8–×1.25 window.
Every R/X sweep, of frequency or of a knob, also prints its numbers on
stdout: one block per `--engine`, the swept value then R and X (per port on a
multi-port design), under the ground the run used. `--markers` points are rows
in place, starred.

Note that knob sweeps in **free space** can be perfectly flat by design —
translation-invariant knobs like a height `base` only matter over a ground
(`--ground finite`).

`--param nominal_nsegs` is a different kind of sweep — a mesh-density
convergence study rather than a geometry or frequency one; see [Convergence
studies](#convergence-studies) below. So is a knob a design marks as its
density knob: a SimNEC `.ssn`'s `JamSegments($segs)` count, which imports as
`tmp_segs`, gets the same table and `Z∞` (see [Analyses](#analyses)). `--engine` also takes a
comma-separated list (or repeat the flag): one trajectory or line per engine
on the same chart, most useful for that same convergence study.

`--set NAME=VALUE ...` sets a design's knobs before the sweep, so a catalog
design can be studied away from its defaults without copying it:
`--set freq=14 design_freq=14`. Only the design's own knobs are accepted (an
unknown name refuses and lists them), and each value keeps its knob's type,
so an integer knob stays an integer.

### R and X charts

The impedance chart (without `--use_smithchart`) draws R in red on the left
axis and X in blue on a twin right axis, each auto-ranged on its own. These
options shape it the way SimNEC's charts are drawn:

- `--log` spaces the `--param` points geometrically (a fixed step in log x,
  SimNEC's `logStep`) and draws a log x axis. An integer knob's points are
  rounded to integers, and duplicates dropped, so `--range 10 500 --npoints
  20` over a segment-count knob solves only whole counts.
- `--r-range LO HI` and `--x-range LO HI` pin the R and X axes, for example
  to put two charts on the same scale.
- `--callouts` labels R and X with their values: `--callouts` alone (or
  `--callouts ends`) at the first and last points, `--callouts markers` also
  at every `--markers` point, `--callouts all` at every point.
- `--panels`, with several `--engine` specs, draws one twin-axis panel per
  engine side by side, instead of one chart coloured by engine.
- `--overlay`, with several `--engine` specs, draws every engine on ONE
  twin-axis chart: R solid on the left axis, X dashed on the right, each
  axis shared by all engines (its range is their union, unless `--r-range`
  / `--x-range` pin it), with one colour and marker per engine. `--callouts`
  gives each engine one box per end, holding both values, stacked in
  columns in a margin beside the data so they never overlap. It works for a
  general `--param` sweep and for a `nominal_nsegs` study, where each
  engine's `Z∞` is a dotted line in its colour. `--overlay` refuses beside
  `--panels`, and with a single engine.
- `--only x` draws just the reactance, `--only r` just the resistance, on a
  single y axis with no twin (X keeps its blue, R its red; on `--overlay` X
  keeps its dashed line and R its solid one). It works on the single-engine
  chart, with `--panels`, with `--overlay`, on a `nominal_nsegs` study and
  on the default multi-engine chart. `--callouts` then label only that
  quantity, and a range pin on the quantity it hides (`--only x --r-range`,
  `--only r --x-range`) refuses rather than being silently ignored.
- Without `--panels` or `--overlay`, the multi-engine chart is unchanged
  (a `nominal_nsegs` study draws panels), and the range and callout options
  refuse by name on a general sweep (that chart has no separate R and X
  axes).

```bash
# A deck's own segment knob (a SY symbol), as a SimNEC-style convergence chart
python -m antennaknobs sweep --builder @dipole.nec --param sy_segs \
    --log --range 10 500 --npoints 20 --engine nec2,nec5 --panels --callouts
```

The options apply to the impedance chart only: they refuse with `--swr`,
`--gain`, and `--patterns`, and the axis options refuse with
`--use_smithchart` (where `--log` still spaces the points).

### Saving the numbers: `--csv`

`sweep --csv PATH` and `analyze --analysis NAME --csv PATH` write the run's
numbers as a CSV file, with or without `--fn`: one row per swept point, the
swept parameter first, then `R_ohm` and `X_ohm` for each curve (a column group
per engine, prefixed with its name, when there are several; per port on a
multi-port design). `--swr` and an `analyze` frequency sweep add `SWR` at
`--z0`; a `nominal_nsegs` study writes its table's `N_ach` and `dGamma`. Values
are at full precision, not the printed `%.3f`. Curves on different grids (an
`analyze` cell on its own band) share the rows they have in common and leave the
rest empty. `--markers` points are not written, and `--gain`, `--patterns` and a
two-sweep map have no such form and refuse. `--csv -` writes to stdout, and the
printed tables go to stderr for that run:

```bash
python -m antennaknobs sweep --builder dipoles.invvee:dipole --param freq \
    --engine momwire:bspline --csv - --fn /dev/null > dipole.csv
```

## Analyses

`analyze` is the first step of the sweep framework: a design names the sweeps
worth running on it, and the command line lists and runs them by name. An
analysis is a Python value, returned by the design's `build_analyses()`, so
nothing solves until you ask for one:

```bash
python -m antennaknobs analyze --builder dipoles.invvee --list
python -m antennaknobs analyze --builder dipoles.invvee --analysis height --fn height.png
python -m antennaknobs analyze --builder dipoles.invvee --analysis height --code
```

`--list` prints one line per analysis: what it sweeps, how many curves it
draws, and its views. Under it go the reasons it cannot run here, if any:

- `UNAVAILABLE`: the design lacks what the analysis needs, e.g. `this design
  declares no height knob`;
- `REFUSED`: the curves multiply past the cap of 6, e.g. `2 designs x 4
  engines = 8 curves`;
- `REFUSED` also names a value a cross lists twice, a knob that is both
  swept and stepped, and a [state](#states) that sets a knob it may not;
- a [hold](#holds) the command line cannot run, named with why (`hold swr`,
  or a hold on a frequency or density sweep).

A long list is grouped. An analysis may name a `group=`, the heading it is
listed under; the design's list order sets the groups' order (the first is
the most important) and the order inside each, and the generic analyses
every design gets (`convergence`, `band SWR`, `height`) go last under
`General`, unless the design lists one under a group of its own. Where a
design offers more than three analyses in more than one group, `--list`
prints each group as a `[Tuning]` line above its analyses; a shorter list
prints none. Names, `--analysis` and deep links are unchanged.

`--code` prints the analysis as the Python that makes it, ready to paste into
a design's `build_analyses()`:

```python
an.Analysis(
    "height",
    an.Sweep("base", 2, 20, points=37),
    cross=an.Cross(grounds=("free", "finite:13,0.005", "finite:5,0.001")),
    references=an.Ref(r=(50,), x=(0,)),
    group="Height & ground",
)
```

`an` is `antennaknobs.analyses`. An analysis sweeps one knob, by name
(`"base"` is the inverted vee's apex height), or one of two *roles* that
mean the same thing on every design: `an.FREQUENCY` (the measurement
frequency) and `an.DENSITY` (the mesh density: `nominal_nsegs` on a catalog
design; an imported `.ssn` marks the knob its `JamSegments` count reads with
`"role": "density"` in `ui_params`). There is no height role: a height is
whichever knob the design calls it, named (an analysis that still says
`an.HEIGHT` is refused with the knob to write instead). Its crosses are
compared as separate curves, one per combination: engines, grounds,
measurement planes, designs, named knob settings, and a second knob's values
(see [Planes, designs and families](#planes-designs-and-families) and
[States](#states)).

Every design also offers the library's generic analyses: `convergence` (a
density ladder) and `band SWR`, on every design, with nothing offered only
where a design happens to declare something. A design's own analysis of the
same name replaces the generic one. The inverted
vee's `convergence` is the density ladder on three engines over average
ground, and its `height` is R and X from 2 to 20 m over three grounds.

`--engine` and `--ground` set what an analysis leaves open: an analysis that
names no engine runs on `--engine`, and one that names no ground runs on
`--ground` (a file design's own ground by default, as for `sweep`).

The runs go through the same code as `sweep`, so the numbers are the same: the
invvee's `convergence` gives exactly the table and `Z∞` of

```bash
python -m antennaknobs sweep --builder dipoles.invvee --param nominal_nsegs \
    --engine momwire:bspline,momwire:razor-2p,nec5 --ground finite:13,0.005
```

and each curve of its `height` is `sweep --param base --range 2 20 --npoints
37 --ground <g>`. All the curves are drawn on one [overlay](#r-and-x-charts)
chart, with the analysis's reference lines (R = 50 Ω, X = 0) dash-dotted.

A curve an engine cannot serve is *refused* and named, and the rest runs. That
happens with `nec5` when no NEC-5 binary is configured, or with an engine that
refuses the design (NEC-2 on a vertex feed). The reason is printed, and the
legend keeps the gap:

```text
nec5: refused: engine 'nec5' needs a licensed NEC-5 console binary ...
```

### Frequency analyses

`band SWR` sweeps `an.FREQUENCY`, and every design offers it. With no range of
its own it sweeps the design's, by the rule in [Sweeps](#sweeps): a deck's own
sweep, the design's declared range, else its band policy. Its SWR values are
exactly those of `sweep --swr` over the same frequencies, because both use the
same solve:

```bash
# Dan's deck: its Generator's 14.0-14.35 MHz, 15 points
python -m antennaknobs analyze --builder @snDipoleVarLenSegs.ssn --analysis "band SWR" --fn swr.png
# the same numbers
python -m antennaknobs sweep --builder @snDipoleVarLenSegs.ssn --swr --range 14 14.35 --npoints 15
```

It prints the frequencies it swept and where they came from. For each curve,
it also prints the band where SWR stays below the analysis's threshold (2:1
unless `an.Ref(swr=...)` says otherwise):

```text
  frequency 14..14.35 MHz, 15 points (the file's own range)
momwire: 2:1 BW ≥ 303 kHz, 14.0474..14.35 MHz (runs off the high end of the sweep); minimum SWR 1.61 at 14.35 MHz (an end of the sweep: the true minimum may lie past it)
```

`≥` and "runs off the ... end" mean the band meets the edge of the sweep and
may continue past it. `none` means SWR never drops below the threshold. When
two dips each make a band, the readout reports the one holding the design's
frequency and says how many there are.

The views are panels of one chart:

- `an.Swr(scale=...)` draws SWR on the workbench's 1-to-∞ scales:
  `"reciprocal"` (1 − 1/SWR; `"auto"` is the same) or `"rho"` (EZNEC's, linear
  in |Γ|). The threshold is a dash-dotted line.
- `an.S11()` draws 20·log₁₀|Γ| in dB, with the threshold's return loss.
- `an.Smith()` draws the trajectory on a Smith chart.

`an.Rx()` draws R and X against frequency as its own chart. When an analysis
has both, R/X goes to `--fn` and the panels go beside it as
`<name>-views.png`. `an.Table()` prints frequency, R, X and SWR. The same
panels draw a knob or density sweep's SWR, S11 and Smith views, which is how
the `convergence` analysis gets its Smith chart.

E4 in the sweep-framework examples is this analysis on Dan's deck, on EZNEC's
scale:

```python
def build_analyses(self):
    return [an.band_swr(views=(an.Swr(scale="rho"),))]
```

### Planes, designs and families

Three more crosses, each one curve per value, multiply with each other and
with engines and grounds under the same cap of 6:

- `an.Cross(planes=("rig", "T1", "feed"))` reads Z at each named port of the
  design's feed network, as a VNA clipped on there would: the chain upstream
  of the port is cut away and the source moves to it, exactly as the
  workbench's plane selector does. Each curve is labelled by the port's own
  name in the design, and a name means only what the design wired to it: in
  Dan's TL-Xfmr-CLC rig below, `feed` is the antenna end of the coax, while
  in one of his tuner decks (QRZ #143) `feed` was the node after a shunt C,
  not the bare antenna. A port the design does not have is a refused curve
  that names the ports it does have.
- `an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex"))` runs the same
  sweep on other designs from the catalog, each on its own knobs and its own
  file ground. Each curve is what `analyze` gives on that design alone.
- `an.Cross(step=an.Sweep("angle_deg", values=(0, 15, 30, 45, 60)))` is a
  *family*: the sweep runs once per value of the second knob, and each curve
  is labelled `angle_deg = 15`. Each curve is `sweep --param ... --set
  angle_deg=15`.

A curve's label joins what makes it, in the order the crosses are written:
`dipoles.invvee_apex, momwire:razor-2p`, or `rig, angle_deg = 30`. Tables print
one block per curve, and a refused curve keeps its place in the legend.

The study `feed spelling (E7)` (see [Studies](#studies)) compares the stock
bridge-fed vee with the apex-knot spelling on three engines, over the density
ladder. NEC-2 cannot feed a knot, so that one curve is refused and the other
five run:

```bash
NEC2_EXE=$(command -v nec2c) python -m antennaknobs analyze --study "feed spelling (E7)"
```

```text
dipoles.invvee, momwire:bspline  Z∞ = 55.144-9.674j  (rough: not yet asymptotic, first order assumed)
...
dipoles.invvee_apex, momwire:razor-2p  Z∞ = 54.464-12.271j  (p = 1.08, asymptotic)
dipoles.invvee_apex, nec2: refused: this design uses PortAtVertex (a series apex feed at a junction knot), which NEC-2 cannot represent ...
```

Its `tuning family` (E2) is R and X against `length_factor`, one pair per
apex angle.

A plane cross on Dan's rig, over 13.9–14.45 MHz in free space, reads:

| plane | minimum SWR | at | Z there |
|---|---|---|---|
| `rig` | 1.19 | 14.450 MHz (the sweep's edge) | 43.13 − j4.32 |
| `T1` | 1.39 | 14.250 MHz | 37.59 − j7.39 |
| `feed` | 1.45 | 14.250 MHz | 72.51 − j1.90 |

```python
def build_analyses(self):
    return [
        an.band_swr(
            name="rig vs antenna",
            sweep=an.Sweep(an.FREQUENCY, 13.9, 14.45, points=23),
            cross=an.Cross(planes=("rig", "T1", "feed")),
            views=(an.Swr(), an.Rx()),
        )
    ]
```

Two knobs cannot be the same knob: a family that steps the swept knob, a map
with one knob on both axes, and a cross that names a value twice are refused
when listed. The density knob is not stepped or mapped (its ladder is
`an.convergence`); cross the other knob as a family instead.

### States

A *state* is a named setting of a design: a few knobs, set over the design's
**defaults**. `an.Cross(states=(...))` crosses them like any other kind, one
curve per state, multiplied with the other crosses under the same cap of 6.
The inverted vee's `height states` is the band's SWR at three mast heights:

```python
an.band_swr(
    name="height states",
    sweep=an.Sweep(an.FREQUENCY, 27.5, 30.0, points=26),
    cross=an.Cross(
        states=(
            an.State("as built"),
            an.State("low mast", base=5.0),
            an.State("tall mast", base=12.0),
        ),
    ),
    ground="finite-fast",
    group="Height & ground",
)
```

```bash
python -m antennaknobs analyze --builder dipoles.invvee --analysis "height states" --fn h.png
```

```text
as built: 2:1 BW 1.316 MHz, 27.9976..29.3134 MHz; minimum SWR 1.03 at 28.6 MHz
low mast: 2:1 BW 1.486 MHz, 28.0969..29.5826 MHz; minimum SWR 1.23 at 28.8 MHz
tall mast: 2:1 BW 1.353 MHz, 28.011..29.3639 MHz; minimum SWR 1.07 at 28.7 MHz
```

`an.State("as built")`, with no knobs, is the design as it ships. A state is
set over the defaults and not over whatever the knobs happen to be, so it
names the same antenna in every session, on the command line and in the
workbench alike. Each curve is the design with those knobs set, as `sweep
--set base=5.0` sets them: the same numbers, to the last bit.
The curves are labelled by the state's name, and `--csv` writes a column group
per state (`low mast R_ohm`, `low mast X_ohm`, `low mast SWR`).

A state can name its design, which makes it that design's curve. A study
can then compare specific settings of different designs, not only their
defaults, without a `designs=` cross:

```python
def build_studies():
    return [
        an.band_swr(
            name="feeds at 12 m",
            cross=an.Cross(
                states=(
                    an.State("bridge", design="dipoles.invvee", base=12.0),
                    an.State("apex", design="dipoles.invvee_apex", base=12.0),
                )
            ),
        ),
    ]
```

Such a curve is labelled with its design first, `dipoles.invvee_apex, apex`.
A state without `design=` is set on the design the analysis runs on. Beside a
`designs=` cross it is set on every design of the cross, so two designs and
three states make six curves. A state that names its design *and* a `designs=`
cross in the same analysis is refused, since the cross would multiply it
again. In a module-level study, which has no design of its own, every state
needs a `design=` unless a `designs=` cross carries them.

Refused by name, when listed or, for another design's knob, when that curve
is built:

- a knob the design does not have;
- the knob the analysis sweeps (a height sweep and a state setting `base`),
  the knob its family steps, or one its hold adjusts;
- the density knob (`nominal_nsegs`): a ladder sweeps it, and any other sweep
  runs at the engine's own density, so the setting would be undone;
- two states with the same name (on the same design).

One state may set the swept, stepped and held knobs: a `MetricPlot`'s
fixed reference (its `relative_to` cell, when that state sets the swept knob
or its design has no such knob; see [Metrics you define](#metrics-you-define)).
It is solved once at its own setting, outside the sweep, the family and the
hold, so a knob any of them moves is its own to set. M0AGP's `vertical` sets
both the swept `vert_ft` and the held `horiz_ft`.

### Holds

An analysis can hold an objective at every point while its knob sweeps: keep
the antenna resonant (or matched to Z0) and see what that takes. At each
swept value the hold's knobs are re-solved by the workbench's own optimizer,
and the views are drawn at the optimised point. The inverted vee has two:

```python
# E9: the resonant length as the droop angle sweeps
an.Analysis(
    "resonance vs angle",
    an.Sweep("angle_deg", 0, 60, points=25),
    hold=an.Hold("resonance", adjust=("length_factor",)),
    views=(an.Rx(), an.Knobs()),
    references=an.Ref(r=(50,)),
)
# E8: a 50-ohm match held with length and angle as the height sweeps
an.Analysis(
    "match vs height",
    an.Sweep("base", 2, 20, points=37),
    hold=an.Hold("match_z0", adjust=("length_factor", "angle_deg"), z0=50),
    views=(an.Rx(), an.Knobs()),
)
```

```bash
python -m antennaknobs analyze --builder dipoles.invvee --analysis "resonance vs angle" --fn e9.png
python -m antennaknobs analyze --builder dipoles.invvee --analysis "match vs height" --ground finite-fast --fn e8.png
```

- **Objectives** are the optimizer's: `resonance` (X = 0) takes exactly one
  knob, `match_z0` (R = Z0, X = 0) exactly two. `z0=None` is the session's
  (`--z0`).
- **Bounds** are each held knob's own `ui_params` `min` and `max`, as in the
  workbench's optimizer. A held knob without both is refused by name.
- **Start.** The first point starts from the design's defaults. With
  `warm_start=True` (the default) each later point starts from the previous
  point's solution; with `False` every point starts from the defaults.
- **`an.Knobs()`** draws the held knobs against the swept one, written beside
  the chart as `<fn stem>-knobs<suffix>`. `an.Table()` prints them as columns,
  and `--csv` writes them, with each point's R and X, whatever the views: a
  held cell's `<cell> R_ohm`, `<cell> X_ohm` and `<cell> <knob>` columns are
  there beside a `MetricPlot`'s too.
- **A point that does not converge is a gap**, never a value: the optimizer's
  root search did not find its root within the bounds, or its solved
  residual is over 1 ohm. The line breaks there, the CSV leaves its cells
  empty, and the output names the reason, e.g.
  `gap at angle_deg = 52.5: no resonance held (...); length_factor at its
  ui_params max 0.99`. The next point warm-starts from the last point that
  did converge. After three gaps in a row, each remaining point starts once
  from the defaults; one that converges resumes the warm start, and one that
  does not stays a gap.
- **Not in this version:** a hold on a frequency sweep, a density ladder or a
  map, and `swr` (a minimisation, with no root to call converged). Each is
  refused by name.

Each crossed cell is held on its own: its design, state, family step, engine
and ground, starting from that cell's defaults.

**Across several bands.** `an.Hold(..., bands=(an.Band(MHz), ...))` holds a
multi-band objective at every point instead, each point one
[`optimize --bands`](#optimizing-across-bands) run: `swr` is the SWR
minimax across the bands (with `mean_weight=`, default 0.5), and
`resonance` / `match_z0` the root form, every band a root and as many
equations as knobs. A band hold may move a group's leaf (`bands.0.length`),
and a knob with no `ui_params` range searches ±20 % of its value, as
`optimize --bands` does. A root the form cannot reach at a point is a gap,
never its near miss, and so is a minimax answer with no band near a match.
Its views draw a curve per band: `an.Swr()` each band's SWR along the sweep,
`an.Table()` an SWR column per band, and `an.Knobs()` the knobs that hold it.

```python
an.Analysis(
    "the fan held across its bands",
    an.Sweep("base", 6, 8, points=5),
    hold=an.Hold(
        "swr",
        adjust=("bands.0.length", "bands.1.length"),
        bands=(an.Band(26.6), an.Band(29.3)),
    ),
    views=(an.Swr(), an.Table(), an.Knobs()),
)
```

The workbench lists a band hold, and says it is the command line's for now.

### Maps

An analysis with a pair of sweeps, `(x, y)`, is a map: every point of the
grid is solved, and `an.Map()` draws |Γ| on `--z0` as a heat map, one panel
per curve the crosses make. The analysis's reference lines become contours:
R = each `r` and X = each `x` of its `an.Ref`, drawn from the same grid (with
no `r` or `x`, X = 0 and R = `--z0`, resonance and the match). Its `swr`
threshold is a dotted contour where |Γ| = (SWR − 1)/(SWR + 1), so
`an.Ref(swr=2)` outlines the region inside SWR 2. A level the grid never
reaches is named in the legend as `(not reached)`. The run prints the
grid's best cell, and `an.Table()` prints every cell.

The inverted vee's `tuning map` (E2) is `length_factor` against the apex angle,
825 solves:

```bash
python -m antennaknobs analyze --builder dipoles.invvee --analysis "tuning map" \
    --ground finite:13,0.005 --fn map.png
```

```text
momwire: least |Γ| 0.0235 (SWR 1.05) at length_factor 0.975, angle_deg 30: Z 50.96 -2.17j
```

X = 0 crosses R = 50 near 32.5° and 0.978. R = 75 never meets X = 0 at this
height. A map draws `Map` and `Table`; for curves against one knob, cross the
other as a family.

A *hold* (re-optimising knobs at every point) is declared in the same Python
but refused by name for now, naming its step.

### Patterns

An analysis with no sweep, `sweep=None`, is a *pattern*: each cell is solved
once, at its measurement frequency, and drawn as far-field cuts instead of
curves against x. Three views draw it, and only them:

- `an.Elevation(az=0)`: the elevation cut through azimuth `az`, from that
  horizon over the zenith to the opposite one;
- `an.Azimuth(el=10)`: the azimuth cut at `el` degrees above the horizon;
- `an.PatternTable()`: the metrics the workbench's pattern compare table
  shows, per cell: peak gain, take-off angle, F/B, both beamwidths and RDF.

A pattern crosses designs, states, engines, grounds, planes and a family like
any analysis, one pattern per cell under the same cap of 6. A family over a
knob is that knob's patterns (`an.Cross(step=an.Sweep("base", 4, 14,
points=6))`, what the workbench's [Sweep a knob chart
keeps](/reference/web/#patterns-across-any-knob)); a family over
`an.FREQUENCY` is patterns across the band, each cell solved at its own
measurement frequency (`an.Sweep(an.FREQUENCY, 28, 29.7, points=3)`).
`an.patterns(...)` is the library's form, with all three views (the
elevation cut along +x, the azimuth cut at 10°). The inverted vee's `height
patterns` is its three mast heights over average ground:

```python
an.patterns(
    name="height patterns",
    cross=an.Cross(
        states=(
            an.State("as built"),
            an.State("low mast", base=5.0),
            an.State("tall mast", base=12.0),
        ),
    ),
    views=(an.Elevation(az=0), an.PatternTable()),
    ground="finite-fast",
    group="Height & ground",
)
```

```bash
python -m antennaknobs analyze --builder dipoles.invvee --analysis "height patterns" \
    --fn heights.png --csv heights.csv
```

```text
analysis 'height patterns': pattern at 28.47 MHz (freq); 3 patterns (3 states); views Elevation, PatternTable
  as built: 28.47 MHz, ground: finite-fast 13/0.005 (reflection-coefficient)
  low mast: 28.47 MHz, ground: finite-fast 13/0.005 (reflection-coefficient)
  tall mast: 28.47 MHz, ground: finite-fast 13/0.005 (reflection-coefficient)
design     peak dBi  takeoff°    F/B dB    az bw°    el bw°    RDF dB
---------------------------------------------------------------------
as built       7.55        22       0.0        86        25       9.1
low mast       6.28        33       0.0        94        42       7.7
tall mast      7.69        13       0.0        83        13       9.1
```

The chart is one polar panel per cut view, on `compare_patterns`' dBi axes,
with a trace per cell and one legend below. Each cut is read straight off the
engine's far-field grid, the one `compare_patterns` draws (1° steps, θ 0–89°
from the zenith), so a cell's cut is that design's pattern sample for sample.
That grid sets the angles a cut may take: whole degrees, an azimuth of 0–359
and an elevation of 1–89 (the grid has no horizon row). The table is the
compare table's own measure, which finds the peak off the 1° grid on momwire.
On PyNEC, NEC-2 and NEC-5, which have no gain evaluator, it is
`compare_patterns`' grid measure.

The measurement frequency is the design's `freq`, the knob `an.FREQUENCY`
names. A state can set it, `an.State("20 m", freq=14.2)`, and a family can step
it, `an.Cross(step=an.Sweep(an.FREQUENCY, values=(28.0, 29.0)))`, for one
pattern per frequency.

`--csv` writes the cuts: one block of rows per cut view, in the analysis's
order. Each row is `cut, angle_deg`, then a `<cell> gain_dBi` column per cell:

```text
cut,angle_deg,as built gain_dBi,low mast gain_dBi,tall mast gain_dBi
elevation az=0,1,-14.82…,-18.83…,-10.20…
...
azimuth el=10,0,...
```

An elevation cut's angle runs 1–179 over the zenith (90), and an azimuth
cut's 0–359. A pattern with no cut view (only the table) writes the table
instead: a row per cell, `cell`, the table's columns
(`peak_gain_dBi, takeoff_deg, azimuth_deg, front_to_back_dB,
az_beamwidth_deg, el_beamwidth_deg, rdf_dB`), then a column per metric the
table names (below).

Refused by name when the analysis is built: a pattern view on a swept
analysis, a sweep's view (`Rx`, `Swr`, `Table`, …) on a pattern, a hold on a
pattern, and a cut angle off the grid.

A study can be a pattern too. This one, saved as a `.py` in the studies
folder, compares the vee with the Yagi on its tab and on the Yagi's:

```python
import antennaknobs.analyses as an


def build_studies():
    return [
        an.patterns(
            name="vee vs yagi",
            cross=an.Cross(designs=("dipoles.invvee", "beams.yagi")),
            views=(an.Elevation(az=0), an.Azimuth(el=15), an.PatternTable()),
            ground="finite-fast",
        ),
    ]
```

```text
design          peak dBi  takeoff°    F/B dB    az bw°    el bw°    RDF dB
--------------------------------------------------------------------------
dipoles.invvee      7.55        22       0.0        86        25       9.1
beams.yagi         13.45        20       8.9        61        22      14.4
```

### Metrics you define

A *metric* is a number read off a far-field pattern. The pattern table's
columns are metrics, and you can define your own. M0AGP's "DX gain", the
power average of the gain over 2–10° of elevation in 0.1° steps, is one line:

```python
DX = an.ElevationWindow("DX gain", 2, 10, step=0.1)
```

The declarative metrics are:

- `an.ElevationWindow(name, lo, hi, step=1, mean="power", az=an.PEAK_AZ)`:
  the gain over elevations `lo`..`hi` (`step` apart, both ends included),
  reduced by `mean`. `"power"` averages the power ratios and converts back to
  dB, `"db"` averages the dB values, and `"max"` takes the largest.
- `an.GainAt(name, el, az=an.PEAK_AZ)`: the gain at one elevation.
- `an.PeakGain()` and `an.TakeOff()`: the peak and its elevation. At
  `an.PEAK_AZ` these are the table's own; on any other cut they are the cut's,
  0–90° `step` apart.
- The table's other columns: `an.PeakAzimuth()`, `an.FrontToBack()`,
  `an.AzBeamwidth()`, `an.ElBeamwidth()` and `an.Rdf()`. `an.TABLE_METRICS`
  lists all seven, and the table reads its columns through them, so a column
  and the same metric asked for by name are one number.

`az=` picks the elevation cut a metric reads:

- a number (degrees from +x) fixes it;
- `an.PEAK_AZ` (the default) is the azimuth of the pattern's peak gain, the
  table's azimuth column, which is the cut through the main lobe;
- `an.MEAN_AZ` power-averages each elevation over the whole azimuth ring,
  1° apart.

An asymmetric antenna reads differently on each, so say which you mean.

**In a pattern's table.** `an.PatternTable(metrics=(DX,))` adds a column per
metric after the fixed ones, in the printed table and in a table-only
`--csv`.

**Against a swept knob.** `an.MetricPlot(metric, relative_to=None)` is a
swept view. It solves the far field at every sweep point of every cell, and
plots the metric against x:

```python
an.Analysis(
    "DX gain vs mast",
    an.Sweep("base", values=(5.0, 7.0, 9.0, 12.0)),
    cross=an.Cross(states=(an.State("as built"), an.State("reference", base=7.0))),
    views=(an.MetricPlot(DX, relative_to="reference"),),
    ground="finite",
)
```

- `relative_to=` names a cell by its state's name, its design or its label,
  and the plot is each curve less that cell, in dB for a gain. When the cross
  names several (one per engine, say), a curve's reference is the one that
  matches it on engine, ground, plane and family step.
- A reference whose state sets the swept knob (as here), or whose design has
  no such knob, is *fixed*. It is solved once at its own setting, drawn flat,
  and subtracted at every x. That is how a new antenna is compared with a
  standard one while one of its own knobs moves. Being outside the sweep, the
  family and the hold, a fixed reference's state may set the swept knob, the
  stepped knob and a held knob, which any other state is refused (see
  [States](#states)): M0AGP's `vertical` sets `vert_ft` and the held
  `horiz_ft`.

`analyze` prints a table per cell and writes the plot. With no impedance view
in the analysis (`Rx`, `Swr`, `S11`, `Smith` or `Table`) the metric plot is
`--fn` itself; beside one it is written as `<fn stem>-metrics<suffix>`.
`--csv` adds `<cell> <metric> (unit)` and
`<cell> <metric> vs <reference> (dB)` columns. On the workbench the chart has
a **Metric** view, read off each point's own momwire solve. A frequency sweep's
metric plot, and any engine but momwire, are `analyze`'s for now.

**Your own function.** When no declarative metric says it, write the
function:

```python
import numpy as np
import antennaknobs.analyses as an


def dx_gain(cut):
    lin = 10 ** (cut.gain_dbi[(cut.el >= 2) & (cut.el <= 10)] / 10)
    return 10 * np.log10(lin.mean())


DX = an.Metric("DX gain", dx_gain, step=0.1)
```

`an.Metric(name, fn, over="elevation", step=1, az=None, lo=None, hi=None,
el=None, unit="dBi")` calls `fn` with an `an.Cut`:

- `cut.el` (or `cut.az` for `over="azimuth"`, which needs `el=`) holds the
  angles in degrees;
- `cut.gain_dbi` holds the total gain, and `cut.gain_v_dbi` and
  `cut.gain_h_dbi` its vertical and horizontal parts;
- `cut.freq_mhz` is the frequency, and `cut.fixed_deg` the cut's fixed angle
  (None for `MEAN_AZ`).

`fn` must be a named, module-level function. A lambda or a nested function is
refused by name, because `--code` and "keep as study" write the function by
reference (`module.dx_gain`, with its `import`). A function from your own
design or study file can't be imported by name, so a kept study writes a
comment saying to copy it in. The hosted workbench offers no function but the
catalog's. A callable written to equal `ElevationWindow(2, 10, step=0.1)` gives
the same number, to the bit, on the same pattern.

### Studies

An analysis in `build_analyses()` belongs to its design: it can leave out
`designs=` and mean "this design". A comparison of several designs belongs to
none of them, so it is a **study**: the same `an.Analysis`, returned by a
`build_studies()`, run by the same code and drawn with the same views. There
are three places to put an analysis, side by side:

| where | what it is | `designs=` | listed on |
|---|---|---|---|
| `Builder.build_analyses(self)` | an analysis of this design | optional; leave it out for "this design" | this design |
| `Builder.build_studies(self)` | this design against a few references | the references only; this design is always the first cell | this design only |
| a module-level `build_studies()` | a study of peers | every design, since a function has no "this design" | every design it names |

The method form is for "how does my new antenna compare with the standard
ones", and it stays on its own design: a Yagi that everyone compares against
does not fill up with everyone's comparisons. Naming your own design among
the references is harmless; it is still one curve, and still first.

```python
import antennaknobs.analyses as an


class Builder(AntennaBuilder):
    def build_studies(self):
        # three curves: this design, then the two references
        return [
            an.band_swr(
                name="vs the references",
                cross=an.Cross(designs=("beams.yagi", "dipoles.invvee")),
            )
        ]
```

The function form is for peers, and it lives in a studies directory, never
in a design module. The catalog's is `studies/`, beside `designs/`: E7, which
compares the inverted vee's two feed spellings, is
`studies/dipoles/apex_feed_on_invvee.py`, and it is offered on both of their
tabs:

```python
# src/antennaknobs/studies/dipoles/apex_feed_on_invvee.py
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

A study with no `designs=` is refused by name: in a function it has no design
to fall back on, and in a method it is just an analysis of this design, which
belongs in `build_analyses()`.

Designs and studies each have one home, and the catalog and your own
folders follow the same rule:

| | designs | module-level studies |
|---|---|---|
| the catalog | `designs/<family>/<design>.py`, named `family.design` | `studies/<family>/<name>.py`, named `family.name` |
| your folders | `~/.antennaknobs/designs/<name>.py`, named `user.name` | `~/.antennaknobs/studies/<path>.py`, named by its path |

- The catalog's studies are the `.py` files under `studies/`, at any depth,
  each inside a family folder. They ship with antennaknobs, so they run
  without being allowed.
- Your studies are the `.py` files in your studies folder,
  `~/.antennaknobs/studies/` (or `$ANTENNAKNOBS_STUDIES_DIR`), beside the
  designs folder. Subfolders become part of the name: `feeds/e7.py` is
  `feeds/e7`. A name part may not hold a `.` or a `:`.
- In both, files and folders starting with `_` or `.` are skipped.
- A module-level `build_studies()` in a design file, the catalog's or yours,
  is refused by name, with a message saying it belongs in the studies
  directory. A Builder's `build_studies(self)` method stays in the design.

A study file is Python, so it is gated like a user design: it **does not run
until you allow it** (see [Allowing user designs to run](#allowing-user-designs-to-run)).
Until then it is listed with the command that allows it, and it is never
imported, so nothing in it runs to find out what it compares.

A study's full name is its source, a colon, and its own name:
`dipoles.apex_feed_on_invvee:feed spelling (E7)`, `feeds/e7:bridge vs apex`, or
`user.my_vee:vs the references` for a method study. The source keeps names
from colliding: two studies of one name in one source are both refused, and
that includes a catalog study file named like a design and that design's
Builder method.

```bash
# every study, with the reason any cannot run here
python -m antennaknobs analyze --list-studies
# what a design's tab lists: the studies naming it, and its own method studies
python -m antennaknobs analyze --list-studies --builder dipoles.invvee_apex
# run one: by its full name, by its source when that holds one study, or by
# its own name when only one study has it
python -m antennaknobs analyze --study "feed spelling (E7)" --fn e7.png
python -m antennaknobs analyze --study feeds/e7 --csv e7.csv
python -m antennaknobs analyze --study "feed spelling (E7)" --code
```

`--study` takes the same `--fn`, `--csv`, `--code`, `--ground` and `--z0` as
`--analysis`. Each design in a study is solved at its own defaults, exactly
as a `designs=` cross is in an analysis. A method study is found through its
design: give `--builder`, or its full name, whose source is that design.
With `--builder` naming a design the study compares, the run is summarised
on that design; otherwise on the study's first.

### Cells: comparing settings that are not a product

Every cross multiplies: two states and two engines are four curves. A set of
settings you picked one by one usually is not a product (5 m on NEC-5 beside
12 m on the B-spline is two curves, not four), so `an.Cross(cells=...)` lists
whole cells instead. It is a union: one curve per `an.Cell`, in order, under
the same cap of 6, and it is never multiplied with another cross.

```python
an.band_swr(
    name="two masts, two engines",
    cross=an.Cross(
        cells=(
            an.Cell(an.State("low", design="dipoles.invvee", base=5.0), engine="nec5"),
            an.Cell(
                an.State("tall", design="dipoles.invvee", variant="dipole", base=12.0),
                engine="momwire:bspline",
            ),
        ),
    ),
    ground="finite-fast",
)
```

- A cell names its state (and through it the design), its engine, its ground
  and its plane. What it leaves out follows the analysis, as a cross cell's
  does: `ground="finite-fast"` above is both cells' ground.
- `variant=` sets a state over that variant's defaults
  (`dipoles.invvee:dipole`, as the registry spells it). It needs `design=`.
- A group knob takes a tuple of its entries, each a dict of the group's own
  leaves: `bands=({"freq": 14.3, "length_factor": 0.49}, ...)` for
  `multiband.fandipole`. A value of the wrong shape is refused by name.

The workbench writes exactly these when it keeps what you built (see
[keeping a chart or pins](/reference/web/#keeping-a-chart-or-pins)): pins
that are a product become the plain cross, and pins that are not become
`cells=`. A study it saves lands in the studies folder, **trusted with your
edits allowed** (`allow --edits`), so it runs without asking and a hand edit
does not ask again. A file that merely appears in the folder still asks. Run a
kept study at the density its pins were solved at, which its header names:

```bash
python -m antennaknobs analyze --study "feeds/two:two pins" --nominal-nsegs 15
```

## Drawing the feed network

`schematic` renders a design's `build_network()` — feedline, tuner, balun, and
the port the source sits on — as an SVG:

```bash
python -m antennaknobs schematic --builder wire.doublet_ladder_tuner --out tuner.svg
# annotate each box with the watts it burns
python -m antennaknobs schematic --builder verticals.stub_matched_vertical --power --out m.svg
```

Needs the optional extra: `pip install 'antennaknobs[schematic]'` (schemdraw —
MIT, and with no dependencies of its own).

The circuit half of a design is otherwise visible only as
[power-budget](/reference/web/#power-budget) rows, which means an element that
burns nothing — an ideal `TL`, a `bypass()` — appears **nowhere**. This draws
every branch whether it dissipates or not, groups them under the box they came
from, and marks where the source sits, which is the design's reference plane.

Boxes may carry their own drawing. `station.t_network_tuner` declares one, so
it renders as the tee it is, with the coil between the capacitors — an ordering
the branch list cannot express, because "the coil goes in the middle" lives in
the head of whoever wrote the factory. A box without a fragment still draws,
from per-branch default symbols; it is simply more anonymous. Fragments are
written with `schematic.series` / `retn` / `shunt`, which are plain data, so
declaring one costs `station.py` no drawing-library import:

```python
Composite(
    ports=("rig", "out"),
    branches=(...),
    schematic=(
        series("capacitor", "81 pF"),
        shunt("inductor", "4.2 µH"),
        series("capacitor", "500 pF"),
    ),
)
```

**Balanced sections are drawn as two conductors.** Past a `FloatingBalun`'s
secondary, or along a `BalancedLine`, the return current rides the partner wire
rather than the common datum — so there is a second rail, the isolation barrier
is drawn through the balun, and no ground symbol appears beyond it. A roller
inductance split half into each leg of a balanced tuner is two coils facing
each other; a differential capacitor across the output is a rung between the
rails. A `Shunt` keeps its ground wherever it sits, because that is what a
`Shunt` is — a 100 MΩ common-mode pin draws as the connection to common it
actually makes.

Not every network is a chain, and nothing is invented for the ones that are
not. A trap in a dipole leg, or a Sterba curtain's risers bridging points on
the structure, are drawn beneath the antenna and labelled with the nodes they
bridge. A second antenna fed in parallel from the same point is noted rather
than drawn in line, which would say the two are in series. Designs with no feed
circuit are refused with a message rather than an empty picture, and a
multi-feed antenna (16 driven ports, no chain) says so.

### Capturing from a VNA

`capture` sweeps a USB-attached NanoVNA and writes the `.s1p` the overlay and
`fit` read:

```bash
# list what's attached
python -m antennaknobs capture --list
# sweep 27-30 MHz and save it
python -m antennaknobs capture --out bench_10m.s1p --start 27 --stop 30 --points 101
```

Needs the optional extra: `pip install 'antennaknobs[vna]'` (pyserial). Pass
`--port /dev/ttyACM0` when more than one analyzer is attached; `--driver` selects
the protocol (`nanovna` today — the driver registry is the extension point for
others). Both NanoVNA console dialects are handled: the `scan` command on
current firmware, falling back to `sweep` + `data 0` on the original. Whatever
the device measures is what you get — a firmware that caps the sweep at 101
points reports 101 points rather than being padded out.

Capture is **CLI-only and local by design**. The web workbench never opens a
serial port: its backend often runs on another machine, where the serial ports
aren't yours (and on the hosted instance aren't anyone's business). The
workflow across a remote backend is capture locally, then upload the file in
the workbench.

### Overlaying a VNA measurement

`--measured <file.s1p>` draws a **measured** sweep alongside the modeled one —
the "did my model match reality?" chart. A NanoVNA (or any VNA) exports the
one-port Touchstone `.s1p` this reads; files written as R+jX instead of S11
work too.

```bash
# the antenna on the bench, against the model of it
python -m antennaknobs sweep --builder dipoles.invvee --swr \
    --range 28.0 29.0 --npoints 21 --measured bench_10m.s1p --fn compare.png
# same comparison on the Smith chart, or as R and X
python -m antennaknobs sweep --builder dipoles.invvee --use_smithchart \
    --measured bench_10m.s1p
```

The overlay works on all three impedance chart forms (SWR, Smith, R/X); the
measured trace is dashed with `×` markers against the modeled solid line. Some
details worth knowing:

- **Reference impedance.** The file declares its own (a NanoVNA writes 50 Ω);
  the trace is renormalized through its impedance to whatever `--z0` the chart
  uses, so a 75 Ω calibration overlays correctly on a 50 Ω chart.
- **Bands.** The measurement is interpolated onto the sweep grid and drawn only
  where the two bands overlap — a single-band measurement against a wide sweep
  renders over its own band, and nothing is extrapolated. Disjoint bands are an
  error, not an empty chart.
- **Frequency only.** Measured data is indexed by frequency, so `--measured`
  needs `--param freq` (the default).
- **Measurement plane.** The comparison happens at whatever plane the chart
  already plots — normally the antenna feedpoint, so calibrate the VNA at the
  feedpoint. A design whose `build_network()` includes a
  [station chain](/concepts/station-modelling/) plots the station plane
  instead, which is what a shack-end measurement sees.

Expect some irreducible disagreement: common-mode current on a real feedline
perturbs a measurement in ways a differential model does not reproduce. A
*structured* residual — the two curves offset the same way across the band — is
usually pointing at something physical (line length, ground, a connector),
which is the diagnostic value of drawing them together.

### Fitting a model to a measurement

`fit` goes the other way: instead of drawing the measurement next to the model,
it solves for the model parameters that reproduce it — site ground constants,
as-built length, feedline electrical length, stray feedpoint reactance.

```bash
python -m antennaknobs fit --builder dipoles.invvee --measured bench_10m.s1p \
    --params length_factor angle_deg --npoints 15 --fractions 0.15 --fn fit.png
```

It prints the fitted values with their shifts, the RMS |ΔΓ| before and after, a
paste-ready variant block, and warnings when the fit is under-determined or a
parameter ended pinned at a bound. `--plane station --line RG-213:30.5` moves
the comparison to the far end of a known feedline for a shack-end sweep.

The full treatment — how to read the residual, why identifiability is the hard
part, and what a fit does and doesn't prove — is in
[Calibrating a model against your VNA](/advanced/calibrating/).

## Choosing an engine

The `--engine` flag selects the solver:

```bash
--engine momwire                 # momwire (default), default (B-spline) basis
--engine momwire:sinusoidal      # NEC-2's own formulation (basis, testing and feed)
--engine momwire:sinusoidal-galerkin            # same basis, Galerkin testing, converged feed
--engine momwire:bspline         # B-spline Galerkin basis
--engine momwire:bspline-d1      # …at degree 1 (bs1) — the cheapest d1-vs-d2 convergence check
--engine momwire:hmatrix         # B-spline + hierarchical-matrix (ACA) acceleration
--engine momwire:arrayblock      # element-aware block solver for arrays
--engine momwire:razor-2p      # NEC-5 formulation twin, NEC-5's identified quadrature — the interactive lane
--engine pynec                   # the NEC-2 reference backend (needs pynec-accel)
--engine nec5                    # a licensed LOCAL NEC-5 binary (joins the roster only when $NEC5_EXE points at one)
```

`nec5` is the real engine, not to be confused with `momwire:razor-2p`:
the latter is momwire's independently written formulation *twin* (same
basis and testing rule, transcribed from the manual), while `--engine nec5`
drives an actual user-licensed NEC-5 binary through its card deck and
printout. It never appears in the roster unless `$NEC5_EXE` points at the
binary — see [NEC-5 as a third engine](/reference/nec5/) for setup,
capabilities, and the license terms that keep it strictly local.

**There is no `-converged` suffix any more** (momwire#654). It bound a
zero-width gap in place of the sinusoidal-Galerkin solver's NEC-style
segment-wide one, and that zero-width gap is now the solver's own default —
so the plain `sinusoidal-galerkin` name means what the suffixed one used to,
and a command line carrying the old spelling should simply drop it. The
impedance converges to the B-spline answer instead of reproducing NEC's
mesh-dependent reactance drift, which is worth two to three orders of
magnitude of apparent cross-basis disagreement on near-open high-Q feeds
(`wire.lazy_h`, `wire.vbeam` class).

If you specifically want NEC's segment-wide gap back — cross-checking against
a NEC or EZNEC result, where reproducing the mesh walk is the point — it
survives as a solver option rather than a roster name: pick it from the web
panel's feed-model control, or pass `feed_model="segment"` when constructing
the solver yourself. See [Solvers & accuracy](/reference/solver/).

`razor-2p` is `RazorSolver`'s only `--basis` roster name — a tent basis
tested by NEC-5's own razor-blade (mixed-potential path) rule, transcribed
from the NEC-5 manual rather than chosen for convenience, so its
convergence behaviour is checkable without the licensed binary. It binds
the two-point testing-path rule (momwire#316), reproduces NEC-5's testing
*formulation* without the licensed binary, and at a working mesh it does
track the licensed engine closely (0.003–0.007 Ω, momwire#603). Its limit
is `bspline-d2`'s, reached more slowly — it does not converge somewhere
NEC-5-specific. `razor-nec5` remains as a deprecated alias, so an existing
command line keeps working.

The class's other quadrature — the default, converged Gauss-Legendre lane
— is not a `--basis` name: it left the roster in momwire#753 (2026-09-02,
"a roster entry is a menu item that must be worth ordering", momwire#654),
and is reached only by constructing `RazorSolver(...)` directly. It came
first, built as the twin before momwire#316's residue study identified the
two-point quadrature rule that made the match near-exact; keeping
full-order Gauss-Legendre on the testing path is now useful for exactly
one question — whether a coarse-mesh disagreement is the testing rule's
own error or NEC-5's quadrature shortcut — and it costs about 20× the
time to ask it versus `razor-2p`
(free space N=1600, one box, momwire 0.44.0: 20.2 s against 0.97 s; over
a finite ground at N=800, 11.1 s against 0.64 s). Memory is no longer the
differentiator it once was: since momwire#742 gave both lanes the same
C++ fill — the razor family had no accelerated path at all before that —
they sit within a tenth of each other (520 MB against 479 MB, free
N=1600). And at a fine mesh the answers converge anyway: 0.001 Ω apart at
N=1600. Both serve the extended kernel, series node gaps, and ground
contact over PEC and the Sommerfeld ground; neither serves junction ports —
see [Solvers & accuracy](/reference/solver/#razor-the-nec-5-formulation-twin)
for the full guidance and refusal boundary.

`momwire` is the default so a plain install works without the optional
`pynec-accel` package. See [The solver & accuracy](/reference/solver/) for which
engine to reach for — including when the accelerated `hmatrix` / `arrayblock`
solvers pay off.

### Segments per wire

Naming a basis also picks that basis's mesh density, because what N a solver
needs to be converged is a property of its basis. N is segments per quarter
wavelength at the design frequency, so a long wire gets proportionally more:

| `--engine` | N (segments per λ/4) |
| --- | --- |
| `momwire:razor-2p`, `nec5` | 40 |
| `momwire:bspline` | 15 |
| `momwire:bspline-d1` | 20 |
| `momwire:pulse` | 41 |
| `momwire:sinusoidal-galerkin` | 20 |
| `momwire:hmatrix` | 30 |
| `momwire:sinusoidal`, `momwire:arrayblock`, `pynec`, `nec2`, `nec42` | 21 |
| `momwire` (no basis) | 21 |

The number is segments per quarter-wave at the design frequency, so it is
comparable across designs, and the run prints it beside the engine name:

```
engine momwire:razor-2p: N=40 segments/wire (engine default)
```

These are the same values the app's solver slots use. `--nominal-nsegs N`
overrides any of them:

```bash
python -m antennaknobs pattern --builder beams.yagi \
    --engine momwire:razor-2p --nominal-nsegs 61
```

A bare `--engine momwire` keeps the framework default of 21 — it is the
default engine, so naming the basis is what asks for the basis's density. A
design that pins `nominal_nsegs` in its own params keeps winning, and a
`@file.nec` deck is unaffected either way: a deck's only mesh is its own `GW`
segment counts, and the run says so instead of naming a density:

```
engine momwire:razor-2p: the file's own segment counts
```

### Convergence studies

`sweep --param nominal_nsegs` runs a convergence study the way the app's
convergence overlay is one checkbox: a ladder of mesh densities, one cold
solve per rung per engine, a Smith-chart trajectory per engine, and a table
on stdout.

```bash
python -m antennaknobs sweep --builder dipoles.invvee:dipole \
    --param nominal_nsegs --engine momwire:bspline,momwire:razor-2p \
    --use_smithchart --fn convergence.png
```

`--engine` takes a comma-separated list (or repeat the flag) — one
trajectory per engine on one chart, same colour keying the whole way through.
With neither `--range` nor `--npoints`, the rungs are the app's own ladder,
`8 12 17 24 34 48 68` (`DENSITY_LADDER` in the frontend). `--npoints k`
alone walks that ladder's 8 to 68 in `k` geometric steps; `--range lo hi`
alone takes seven rungs across the range; both together space `k` rungs
across `lo`..`hi`. Every rung is rounded to an int and duplicates are dropped.
`--markers 15 16 20` solves those densities too — the served numbers a
study usually wants to see — starred in the table and squared on the
chart. Beside a ladder they are observations on the trajectory, not rungs
of the `Z∞` estimate; given alone, with neither `--range` nor
`--npoints`, they are the whole ladder: `--markers 15 16 20` solves just
those three.
A ladder given that way is ordinary rungs, not observations: no squares,
and `--callouts` labels only its two ends.

For a geometric ladder, prefer `--range LO HI --npoints N --log` to listing
the rungs as `--markers`: the rungs are spaced by a fixed ratio and rounded
to integers, which is what SimNEC's `logStep` sweep does (`--log` is implied
for `nominal_nsegs`, and accepted so the same line works for any integer
knob). Keep `--markers` for the few densities you want to see beside it.

The table is grouped one block per engine:

```text
== nominal_nsegs convergence: momwire:bspline ==
ground: free space
nominal_N  N_ach     R (Ω)     X (Ω)      |ΔΓ|
        8     17    71.240    -5.612    0.0038
       13     25    71.266    -5.388    0.0023
       21     41    71.291    -5.183    0.0009
       34     65    71.309    -5.051    0.0000
momwire:bspline  Z∞ = 71.339-4.826j  (rough: not yet asymptotic, first order assumed)
```

`nominal_N` is the rung asked for; `N_ach` is the total segment count the
engine actually meshed at that rung — engines round the density to their own
parity (razor-2p and nec5 even; bspline, nec2, and pynec odd), so two engines
given the same `nominal_N` do not mesh at the same `N_ach`, and this column
is where that shows up. `|ΔΓ|` is the reflection-coefficient distance to that
engine's own finest rung, the same ladder metric the density studies (#1525)
are judged on.

`Z∞` is the extrapolated value as N grows without limit, computed against
`N_ach` by the same estimator the workbench uses (see [Where the extrapolated
value comes from](/advanced/convergence/#where-the-extrapolated-value-comes-from)).
Its line ends with how it was reached:

- `(p = 0.98, asymptotic)`: the step between rungs shrinks as a straight line
  on log–log axes, so the observed order p is used, fitted through the last
  three rungs.
- `(rough: not yet asymptotic, first order assumed)`: the ladder is too short
  (three rungs), its steps are not yet shrinking at a steady rate, or they
  change direction. `Z∞` then extrapolates at first order from the last two
  rungs; treat it as a rough figure and add finer rungs. When the feed mesh
  is the reason, a second line names the step, e.g. `the fed segment went
  100.0 → 33.3 mm between N = 65 and 95: the feed mesh does not refine with
  the ladder (AK#1767)`. A short feed wire gains segments two at a time, so
  the fed segment stays put for several rungs and then jumps (see
  [Where the extrapolated value comes from](/advanced/convergence/#where-the-extrapolated-value-comes-from)).
- `(converged)`: the last step is below one part in a million of `|Z|`, and
  `Z∞` is the finest rung's value.
- `Z∞ unavailable (need >= 3 rungs)`: fewer than three rungs.

On the Smith chart, each engine's trajectory carries a hollow ring at its
coarsest rung, a filled disc at its finest, and a diamond at its `Z∞`
(clipped inside the unit circle, since an early-ladder extrapolation can fly
past it) — the same conventions as the app's convergence overlay. Without
`--use_smithchart`, the chart is one panel per engine, side by side: R (left
axis) and X (right axis) against the achieved segment count on a log axis,
each axis ranged on its own, with `Z∞` drawn as a dotted line on each.
`--r-range`, `--x-range`, and `--callouts` apply here as in [R and X
charts](#r-and-x-charts). A multi-port design draws port 0 only, noted in the
title; the app's own per-port convergence view is out of scope here.

```bash
# AC6LA's free-space convergence chart, on the catalog dipole at 14 MHz
python -m antennaknobs sweep --builder dipoles.invvee:dipole \
    --set freq=14 design_freq=14 --param nominal_nsegs \
    --range 10 500 --npoints 20 --engine nec2,nec5 --callouts --fn conv.png
```

`--nominal-nsegs`, `--swr`, `--gain`, and `--measured` are frequency-sweep or
fixed-density notions and each refuses by name alongside `--param
nominal_nsegs` — the sweep sets `nominal_nsegs` itself, rung by rung, so a
fixed override would fight it silently rather than visibly.

### The extended kernel

`--extended-kernel` applies NEC's extended thin-wire kernel (the `EK` card) on
the momwire engine, wherever `--engine` is accepted:

```bash
python -m antennaknobs sweep --builder wire.dipole --extended-kernel
```

It matters for **fat wires** — segments not much longer than the wire radius —
and is a fraction of a percent on ordinary thin wire; see
[the extended thin-wire kernel](/reference/solver/#the-extended-thin-wire-kernel-ek).
Every momwire basis but `pulse` serves it — `sinusoidal-galerkin` since
momwire 0.27.0 (momwire#246/#287/#299), and `razor-2p` with it. The
refusals left are combinations: with `use_singular_enrichment`
(momwire#271), with a wire below the ground plane, and with a radius step at
a junction on `sinusoidal-galerkin`. Each exits with a named message rather
than a reduced-kernel answer under an extended-kernel request. The flag applies only to momwire: passing it with `--engine pynec` is an
error.

An imported deck brings its own. A `@file.nec` deck read as NEC-2 whose deck
carries an `EK` card is solved with the kernel on without the flag (`EK -1`,
like an absent card, leaves it off). A deck read as **NEC-4 or NEC-5**
(detected, or chosen) is solved with the kernel on by default, as its own
program solves it: NEC-5's kernel behaves as the extended one, and NEC-4's
thin-wire model is equivalent to it and ignores an `EK` card, which the
import note says. Where the basis or the deck refuses the kernel (`pulse`, a
buried wire), that default falls back to the reduced kernel with an
`advisory:` line on stderr instead of refusing. `--no-extended-kernel`
turns the kernel off whatever the deck says; `--extended-kernel` asks for it
outright, and still refuses where it cannot run. The same goes for
ground since v0.75.1: with no `--ground`, a `@file.nec` design is solved
under the ground its own `GE` / `GN` cards model — `GE 0` free space, `GE 1`
or `GN 1` perfect, `GN 2` finite with the card's ε<sub>r</sub> and σ, `GN 0`
the reflection-coefficient model (Sommerfeld in a NEC-5 deck, which has no
reflection-coefficient ground), and the MININEC-type ground for a NEC-5
deck's bare `GD`, NEC-2's `GN 1` + `GD` cliff at 0, or 4nec2's `GN 3` — and
an explicit `--ground` still wins.
Since v0.81.0 the ground is settled ONCE per run and handed to every engine
named: an explicit `--ground`, else the file design's own, else `finite`
(Sommerfeld over average soil, ε<sub>r</sub> 13, σ 0.005 S/m), the same
ground the workbench starts on. Before v0.95.0 that last default was free
space; pass `--ground free` for it.
The engines' own defaults disagree (PyNEC and NEC-2 assume a finite ground,
momwire and NEC-5 free space), and a multi-engine study that let each engine
pick was comparing two physics without saying so; the convergence table now
prints the ground under each engine's header.

## Comparing engines

Solve the same design two ways and overlay the patterns — the built-in
cross-validation:

```bash
python -m antennaknobs compare_patterns \
  --builders beams.moxon beams.moxon \
  --engines pynec momwire:bspline --fn check.png
```

With a licensed NEC-5 binary on the machine (`export NEC5_EXE=...`), `nec5`
joins the roster and the comparison becomes a three-way triangle of
independently written solvers — see [NEC-5 as a third
engine](/reference/nec5/) for setup, capabilities, and the license terms
that keep it strictly local:

```bash
python -m antennaknobs compare_patterns \
  --builders beams.moxon beams.moxon beams.moxon \
  --engines momwire pynec nec5 --fn triangle.png
```

Alongside the overlaid plot, `compare_patterns` prints a metrics table — peak
gain (dBi), takeoff angle, front-to-back, −3 dB azimuth/elevation beamwidths,
and the RDF — one row per antenna, so the comparison comes with numbers, not
just shapes:

```text
design          peak dBi  takeoff°    F/B dB    az bw°    el bw°    RDF dB
--------------------------------------------------------------------------
dipoles.invvee      1.92         1       0.0        85        89       1.9
beams.yagi          8.89         1       8.3        60        42       8.9
```

**RDF** is the receiving directivity factor: the peak gain minus the
pattern's average gain, 10·log10 of (1/4π)∬G dΩ. The average is always
normalised by the whole sphere. Over a ground the lower hemisphere adds
nothing to it, which is how EZNEC's "Average Gain" works and what published
RDF figures subtract. Loss cancels, so a lossless free-space antenna reads
its peak gain, as the two rows above do. A receiving antenna is judged on it
rather than on gain: a Beverage at −9 dBi reads about 12 dB. In free space
the RDF needs the whole sphere, which the momwire engine samples; a NEC
engine's pattern stops at the horizon, so its free-space row prints `—`.

### A refinement ladder for an imported deck

A catalog design refines through its own mesh knobs, but an imported `.nec`
deck's only mesh is its `GW` segment counts. `ladder` multiplies every wire's
count by each odd factor, re-solves on every engine you name, and prints the
impedance at each rung, the step between rungs, and `Z∞` against the
refinement factor, read the same way as the [density study's](#convergence-studies)
line (three factors are the minimum, and three always give the rough,
first-order figure):

```bash
python -m antennaknobs ladder --builder @my_dipole.nec \
  --refine 1 3 9 --engines momwire nec5
```

The factors are odd so that a centre gap stays a centre gap and a knot source
stays a knot source. The default is `1 3 9`.

## Optimizing across bands

`optimize --bands` tunes one design for several frequencies at once — a fan
dipole's lengths for 12 m and 10 m together, or a three-band vertical whose
height, top wire and coupling capacitor each move every band. Each evaluation
is **one build of the design solved at every band's frequency**: the geometry
and its mesh are built once, at the design's own frequency, and the bands are
points of the same frequency sweep. A band's own `freq` knob (the multiband
designs size each element from one) never moves while another band is read.

```bash
# Both bands' SWR, worst band first (the default form)
python -m antennaknobs optimize --builder multiband.twoband_fan_dipole:current_physical \
    --bands 26.6,29.3 --params bands.0.length bands.1.length

# A NEC deck's SY constants are its knobs
python -m antennaknobs optimize --builder @vert_inv_L.nec \
    --bands 1.83,3.7,7.1 --params sy_w5hgt sy_w6len sy_cap2 \
    --bound sy_cap2=10:150
```

**Bands.** `--bands` is a comma-separated list, each
`FREQ[:OBJECTIVE][:feed=N][:z0=OHM][:knobs=A+B]`:

- `OBJECTIVE` is `swr` (the default), `res` (X = 0) or `z0` (Z = Z₀). All the
  bands of one run share a unit, so `swr` is not mixed with `res` / `z0`.
- `feed` is the port the band is read at, default 0. A design that drives one
  feed per band (`multiband.hexbeam_5band` with `daisy_chain` off) reads band
  *i* at feed *i*; a feed the design does not have is refused by name.
- `z0` overrides `--z0` for that band.
- `knobs` names the band's own knobs, for `--mode sequential`.

A spec starting with `[` is JSON instead: a list of
`{"freq", "objective", "feed", "z0", "knobs"}` objects.

**Knobs.** `--params` names them, a group's leaf spelled `bands.<i>.<leaf>`.
Each searches its `--bound NAME=LO:HI`, else its slider's `ui_params` range,
else ±20 % of its value. With no `--params` the bands' `knobs` are the knobs.
A bound is in the knob's own unit, which the run prints before it starts
(`# knob sy_cap1 = 340 pF, range 100..1000 pF`): an opened deck's `SY cap1 =
340pF` is bounded `100:1000`, not `100e-12:1000e-12`. A bound that excludes the
knob's current value is refused, and a run whose answer leaves a knob at the
edge of its range, or no band near a match, says so under its table.

**Forms** (`--mode`):

- `minimax` (the default) minimizes
  **J = (1 − w) · worst band + w · mean of the bands**, with `w` from
  `--mean-weight` (default 0.5). The worst band alone (`w = 0`) says nothing
  about the others, so the search is free to make every band as bad as the
  hardest one; the mean term stops that by trading a little on the worst band
  for a lot on the rest. On a three-band vertical with a coupled inverted L
  (160/80/40 m), `w = 0.2` settled on SWR 1.86 on all three bands, while
  `w = 0.5` gave 1.93 / 1.93 / 1.34: 0.07 worse on the worst band, half an SWR
  unit better on 40 m. The run prints the worst band, the mean and J
  separately, and the worst SWR it reports is the largest SWR any band read.
  It is a local search: it starts from the better of the knobs' values and a
  fit that brings every band's reactance as near zero as the knobs allow, and
  refines from there.
- `root` (opt-in) solves for exact resonance or an exact match on every band,
  by Newton. It needs as many equations as knobs (`res` is one per band, `z0`
  two) and says whether a root exists: `root`, `no root in the box`,
  `singular` (naming the knob that moves no band, or the knobs that only move
  them together), `parallel resonance` (X = 0 with X *falling* through the
  band, kilohms of R — a resonance, but not one to feed), or
  `out of evals`. A near miss is never reported as a root, and the run does
  not fall back to another form. Exact resonance on every band often has no
  solution with the knobs given; `minimax` is the form to reach for first.
- `sequential` (opt-in) tunes each band with its own `knobs`, the others held,
  band after band, in passes (`--passes`, default 8), until every band's
  residual is under `--tol` (default 0.5 Ω). It converges when each knob
  mostly drives its own band, and not otherwise.

`--max-evals` caps the distinct points solved (default 60 per knob plus 40,
at most 400). The run ends with the per-band table before and after, and the usual
paste-ready params block.

### Keeping a run

`--keep PATH` keeps the run as a [study](#studies): a file at `PATH` under the
studies folder (`~/.antennaknobs/studies/PATH.py`), recorded trusted as the
workbench's kept studies are, whose `build_studies()` returns one
`an.Optimize`. It holds where the run started (an `an.State` naming the
design, its variant and the knobs set off their defaults), the knobs it moved
with their ranges, the bands, the form, the engine and ground, and what it
found (`an.Result`: each knob's value and the per-band table). `--keep-name`
names it; by default it is the design and the bands.

```bash
python -m antennaknobs optimize --builder multiband.twoband_fan_dipole:current_physical \
    --bands 26.6,29.3 --params bands.0.length bands.1.length --keep fan/12-10
python -m antennaknobs analyze --study "fan/12-10:multiband.twoband_fan_dipole:current_physical across 26.6/29.3 MHz"
python -m antennaknobs analyze --study "fan/12-10:..." --apply
```

- `analyze --study NAME` runs the search again from the kept start and
  prints the table, then each knob and each band's SWR against the stored
  result (`stored`, `now`, the change). Run on a newer momwire, that is the
  check that the answer has not moved.
- `--apply` loads the stored result without searching: every knob at exactly
  its stored value, each band read once there, against what was stored.
- `--code` prints it as Python, as for any study.

A deck run (`--builder @deck.nec`) is kept by the path it was given. The
workbench keeps one from its band readout too (see
[Optimizing](/reference/web/#optimizing)).

## Copying params back to code

After tuning — in the workbench or with `optimize` — turn the knob values back
into source you can paste into a design file. `params` prints a design's current
values as a `default_params = {...}` block:

```bash
python -m antennaknobs params --builder beams.yagi
python -m antennaknobs params --builder specialty.hentenna:z100 --wrap mappingproxy
```

For a **`name:variant`** it prints a `<variant>_params` block instead — and that
block carries **only the keys that differ from `default_params`**, because a
variant is stored as an *overlay* on the defaults (just the deltas; the resolver
fills the rest in — see [Variants are overlays](#variants-are-overlays)). So the
second command above emits a minimal `z100_params = {...}` you can paste straight
back as the variant. A bare design (or `:default`) prints the full
`default_params`, since that is the baseline everything overlays.

Useful flags: `--name <var>` (name the emitted block), `--no-ui` (knob values
only, drop the `ui_params` block), and `--wrap mappingproxy` (match the
catalog's frozen-params style). An `optimize` run ends by printing the same
paste-ready block for its result, so the tuned values go straight into code.

## Variants are overlays

A design can ship named **variants** — alternate knob-sets selected with
`name:variant` (`beams.moxon:original`, `specialty.hentenna:z100`). A variant is
declared as a `<variant>_params` mapping on the `Builder` class, and it is an
**overlay on `default_params`**: it lists *only the keys it changes*, and every
other key is inherited from `default_params`.

```python
class Builder(AntennaBuilder):
    default_params = {"freq": 28.5, "halfdriver": 2.46, "tipspacer_factor": 0.077}
    original_params = {"halfdriver": 2.4336}  # just the delta — the rest inherit
```

That is exactly the form `params name:variant` emits, so the round-trip is
lossless: copy a tuned variant, paste it back as its `<variant>_params`, and it
means the same thing. (A variant written out in full still works — overlaying a
complete dict reproduces that dict — but the minimal delta form is the idiom.)

## Exporting to NEC

```bash
python -m antennaknobs export --builder beams.yagi --out yagi.nec
python -m antennaknobs export --builder beams.yagi --out yagi_nec5.nec --dialect nec5
python -m antennaknobs export --builder beams.yagi --out yagi_nec4.nec --dialect nec4
```

The default deck (`--dialect nec2`) is validated against `nec2c`, so designs
round-trip into other NEC tools. `--dialect nec5` writes the deck the
[NEC-5 engine](/reference/nec5/) runs, with sources on knots, buried wires
meshed in the soil and a header naming the design, mesh and ground; writing it
needs no NEC-5 binary. That writer has no pattern switch, so `--no-pattern` is
refused under it. `--dialect nec4` writes [NEC-4.2's deck](/reference/nec42/#the-nec-4-deck)
(graded meshes as chained wires, `EX 6` current sources, `NOFILE` Sommerfeld
cards), also without a binary; `--nec42-sommerfeld 3` makes its ground `GN 3`,
and the same flag picks the NEC-4.2 engine's ground on `sweep`, `analyze` and the
other engine commands. The reverse direction — loading an existing `.nec` deck as a design —
is [`parse_nec` / `read_nec`](/reference/nec-import/).

## Allowing user designs to run

A design file in `~/.antennaknobs/designs/` is a full Python program that runs
with your user privileges, so it **does not run until you allow it** — like
VS Code's workspace-trust prompt. The decision is remembered per file, by its
contents: a new file always asks first, and an allowed file that later changes
asks again. Decisions live in `.trust.json` inside the design folder and are
keyed relative to it, so they travel with the folder — mount it into the
[Docker container](https://github.com/stevenmburns/antennaknobs/blob/main/DOCKER.md)
or move it to a new machine and your allowed designs stay allowed.

```bash
# A design someone sent you: review it first, then allow that exact version
python -m antennaknobs screen ~/Downloads/their_design.py
python -m antennaknobs allow their_design

# A design you author: allow your future edits too, so saves never re-prompt
python -m antennaknobs allow my_dipole --edits

# Stop allowing one
python -m antennaknobs disallow their_design
```

Study files in `~/.antennaknobs/studies/` (see [Studies](#studies)) go
through the same gate. `allow`, `disallow` and `screen` take a study by its
name under the folder, subfolders included, and its decision is kept in the
studies folder's own `.trust.json`, keyed the same relative way:

```bash
python -m antennaknobs allow feeds/e7
```

A name that is both a user design and a top-level study file is not guessed
at: give `user.<name>` for the design, or the study file's path.

`screen` prints what the file does that's unusual (imports outside the
antenna-modelling stack, file access, network use) *without running it*. The
report is advisory — it informs your decision, it isn't a verdict. See
[Authoring designs with Claude](/concepts/authoring-with-claude/) for the full
workflow, including the equivalent "needs your OK to run" panel in the web app.
