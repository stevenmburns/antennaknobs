---
title: Command line
description: Driving antennaknobs from the terminal — list, draw, sweep, pattern, optimize, compare, params, .nec export, and allowing user designs.
---

antennaknobs has a command-line interface for batch work. The subcommands:

```text
python -m antennaknobs {draw,sweep,optimize,pattern,compare_patterns,params,export,list,screen,allow,disallow}
```

| Command | What it does |
| --- | --- |
| `list` | List available designs (built-in and user) |
| `draw` | Draw the antenna geometry |
| `sweep` | Sweep a parameter or frequency |
| `pattern` | Plot the far-field pattern |
| `compare_patterns` | Overlay the patterns of several antennas / engines |
| `optimize` | Optimize an antenna's parameters |
| `params` | Print a design's knob values as paste-ready Python |
| `export` | Export the design to a NEC-2 `.nec` card deck |
| `screen` | Show what a design file does that's unusual, without running it |
| `allow` | Allow a user design to run (it runs code on your machine) |
| `disallow` | Stop allowing a user design to run |

## Naming a design

Designs are addressed as `family.name` (the same names `list` prints):

```bash
python -m antennaknobs list            # arrays.bowtiearray, beams.yagi, loops.delta_loop, ...
```

## Patterns

```bash
# Far-field pattern of a Yagi, solved with momwire's default (B-spline) basis
python -m antennaknobs pattern --builder beams.yagi --engine momwire
```

Useful `pattern` flags: `--fn out.png` (write to a file instead of the screen),
`--ground free|pec|finite|finite:<eps_r>,<sigma>`, `--wireframe`, and
`--elevation_angle`.

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

Frequency sweeps use the vectorized impedance sweep (one geometry, many
frequencies), so they are much faster than scripting one solve per point.
Note that knob sweeps in **free space** can be perfectly flat by design —
translation-invariant knobs like a height `base` only matter over a ground
(`--ground finite`).

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
--engine momwire:sinusoidal      # NEC-2-style three-term basis
--engine momwire:sinusoidal-galerkin            # same basis, Galerkin testing
--engine momwire:sinusoidal-galerkin-converged  # …with the converged feed model
--engine momwire:bspline         # B-spline Galerkin basis
--engine momwire:hmatrix         # B-spline + hierarchical-matrix (ACA) acceleration
--engine momwire:arrayblock      # element-aware block solver for arrays
--engine pynec                   # the NEC-2 reference backend (needs pynec-accel)
```

The `-converged` variant swaps the sinusoidal-Galerkin solver's NEC-style
segment-wide gap for a zero-width one: the impedance converges to the
B-spline answer instead of reproducing NEC's mesh-dependent reactance
drift. Use the plain form when cross-checking against NEC/EZNEC results;
use `-converged` on near-open high-Q feeds (`wire.lazy_h`, `wire.vbeam`
class), where it removes two to three orders of magnitude of the apparent
disagreement between solver bases — see
[Solvers & accuracy](/reference/solver/) for the details.

`momwire` is the default so a plain install works without the optional
`pynec-accel` package. See [The solver & accuracy](/reference/solver/) for which
engine to reach for — including when the accelerated `hmatrix` / `arrayblock`
solvers pay off.

## Comparing engines

Solve the same design two ways and overlay the patterns — the built-in
cross-validation:

```bash
python -m antennaknobs compare_patterns \
  --builders beams.moxon beams.moxon \
  --engines pynec momwire:bspline --fn check.png
```

Alongside the overlaid plot, `compare_patterns` prints a metrics table — peak
gain (dBi), takeoff angle, front-to-back, and −3 dB azimuth/elevation
beamwidths — one row per antenna, so the comparison comes with numbers, not just
shapes:

```text
design            peak dBi  takeoff°    F/B dB    az bw°    el bw°
----------------------------------------------------------------
dipoles.invvee        1.93         1       0.0        85        89
beams.yagi            8.89         1       8.2        60        42
```

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
    original_params = {"halfdriver": 2.4336}   # just the delta — the rest inherit
```

That is exactly the form `params name:variant` emits, so the round-trip is
lossless: copy a tuned variant, paste it back as its `<variant>_params`, and it
means the same thing. (A variant written out in full still works — overlaying a
complete dict reproduces that dict — but the minimal delta form is the idiom.)

## Exporting to NEC

```bash
python -m antennaknobs export --builder beams.yagi --fn yagi.nec
```

The deck is validated against `nec2c`, so designs round-trip into other NEC
tools. The reverse direction — loading an existing `.nec` deck as a design —
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

`screen` prints what the file does that's unusual (imports outside the
antenna-modelling stack, file access, network use) *without running it*. The
report is advisory — it informs your decision, it isn't a verdict. See
[Authoring designs with Claude](/concepts/authoring-with-claude/) for the full
workflow, including the equivalent "needs your OK to run" panel in the web app.
