---
title: "Your own study"
description: A worked walkthrough of the sweep framework's studies — M0AGP's 160 m inverted L against a full-size vertical, as a design file in your own folder, run from the command line and the workbench, beside his own table.
---

:::note[New, and feedback is welcome]
Studies, holds and metrics you define are new, and they may still change. If
something is awkward or wrong, say so on the QRZ thread
[Running AntennaKNoBs on a windows machine](https://forums.qrz.com/index.php?threads/running-antennaknobs-on-a-windows-machine.1003328/)
or in the [GitHub issues](https://github.com/stevenmburns/antennaknobs/issues).
:::

An *analysis* is a sweep a design names as worth running: a knob, a range,
what to cross it with and how to draw it. A **study** is an analysis that
spans more than one design, or more than one setting of a design. It is the
same `an.Analysis` value, run by the same code; what changes is where it lives
and which designs list it.

There are three places one can live:

- a design's `build_analyses()`, for an analysis of that design alone;
- a `Builder.build_studies()` method, for this design against a few
  references, listed only on this design;
- a module-level `build_studies()` in a studies folder, for a study of peers,
  listed on every design it names. The catalog's are under
  `src/antennaknobs/studies/<family>/`, and yours go in
  `~/.antennaknobs/studies/`.

The reference pages hold the rules: [Analyses](/reference/cli/#analyses),
[Studies](/reference/cli/#studies), [States](/reference/cli/#states),
[Holds](/reference/cli/#holds),
[Metrics you define](/reference/cli/#metrics-you-define) and
[Cells](/reference/cli/#cells-comparing-settings-that-are-not-a-product) on
the command line, and
[Keeping a chart or pins](/reference/web/#keeping-a-chart-or-pins) and
[Linking to a chart](/reference/web/#linking-to-a-chart) in the workbench.
This page works one example from end to end instead.

## The question

M0AGP asked it on QRZ, in
[Inverted L vs full-size vertical — "DX Gain" comparison](https://forums.qrz.com/index.php?threads/1005128/)
(first post): how much does a 160 m inverted L give up against a full-size
quarter-wave vertical as its vertical section gets shorter, with the top wire
re-cut for resonance at every height?

His setup, which the study reproduces:

- 1.83 MHz, fed at the foot of the riser, 5 ft above ground;
- two quarter-wave radials at the feed height, perpendicular to the top wire;
- Sommerfeld average ground, εr 13 / σ 0.005 S/m;
- the vertical section from 20 to 100 ft, the top wire cut for resonance at
  each;
- his figure of merit, **DX gain**: the power average of the gain over 2–10°
  of elevation, 0.1° apart, converted back to dB, and each inverted L read
  relative to the vertical.

He modelled it on NEC-5. His azimuth isn't stated; the elevation cut at
azimuth 0 (along the radials, broadside to the top wire) is the one that
reproduces his table, so the study states it.

## The design, in your own folder

The whole thing is one design file. Put it in `~/.antennaknobs/designs/` as
`m0agp_invl.py` and it is the design `user.m0agp_invl`. It is the same file
the catalog ships as `verticals.m0agp_invl`, with one line different: the
name its states give their design. The pieces, in order.

### The Builder and its knobs

```python
import math
from types import MappingProxyType

import antennaknobs.analyses as an
from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire

#: One foot, in metres.
FT = 0.3048

#: The full-size vertical: resonant with no top wire at 1.83 MHz over
#: Sommerfeld 13/0.005 with these two radials (131.22 ft on NEC-5, 131.10 ft
#: on momwire).
VERTICAL_FT = 131.2


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 1.83,
            "freq": 1.83,
            # The feed and the radials: 5 ft up.
            "base": 1.524,
            # The vertical section and the top wire, in feet. The top wire
            # is cut for resonance at 70 ft of vertical section.
            "vert_ft": 70.0,
            "horiz_ft": 63.9,
            "n_radials": 2,
            "ui_params": MappingProxyType(
                {
                    "default_view": "iso",
                    "base": {"min": 0.5, "max": 10.0},
                    "vert_ft": {"min": 10.0, "max": 140.0},
                    # The hold's bounds: every resonant top from 100 ft of
                    # vertical (33 ft) to 20 ft (112 ft) is inside, and the
                    # top end stays clear of the half-wave antiresonance.
                    "horiz_ft": {"min": 1.0, "max": 135.0},
                    "n_radials": {"min": 1, "max": 16},
                }
            ),
        }
    )
```

The two knobs the study moves are `vert_ft` and `horiz_ft`, in feet because
his table is in feet. The design carries no ground of its own; the study
states his.

### A 0 ft top wire is the vertical

```python
    def build_wires(self):
        eps = 0.05
        z = self.base
        vert = self.vert_ft * FT
        horiz = self.horiz_ft * FT
        radial_len = 0.25 * self.design_wavelength

        tups = [Wire((0.0, 0.0, z), (0.0, 0.0, z + eps), ex=1 + 0j)]
        tups.append(Wire((0.0, 0.0, z + eps), (0.0, 0.0, z + vert)))
        if horiz > 0:
            # No top wire at all is the plain vertical (a zero-length wire
            # would not mesh).
            tups.append(Wire((0.0, 0.0, z + vert), (0.0, horiz, z + vert)))
        n = int(self.n_radials)
        for i in range(n):
            a = 2 * math.pi / n * i
            tups.append(
                Wire(
                    (0.0, 0.0, z),
                    (radial_len * math.cos(a), radial_len * math.sin(a), z),
                )
            )
        return tups
```

A 5 cm driven gap at the foot, the riser along z, the top wire along +y, and
the radials spread evenly from +x. The one line that matters for the study is
`if horiz > 0`: with no top wire the design *is* the full-size vertical, with
the same feed and the same radials. So the vertical needs no second design.
It is a [state](/reference/cli/#states) of this one.

### `build_studies()`

```python
class Builder(AntennaBuilder):
    # default_params and build_wires, as above

    def build_studies(self):
        me = "user.m0agp_invl"
        dx = an.ElevationWindow("DX gain", 2, 10, step=0.1, mean="power", az=0)
        return [
            an.Analysis(
                "DX gain vs the vertical",
                an.Sweep(
                    "vert_ft",
                    values=(20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0),
                ),
                cross=an.Cross(
                    states=(
                        an.State("inverted L", design=me),
                        an.State(
                            "vertical", design=me, vert_ft=VERTICAL_FT, horiz_ft=0.0
                        ),
                    )
                ),
                hold=an.Hold("resonance", adjust=("horiz_ft",)),
                views=(an.MetricPlot(dx, relative_to="vertical"), an.Knobs()),
                ground="finite:13,0.005",
            ),
        ]
```

It is a Builder *method*, so the study is listed on this design only. It
compares the design with a setting of itself, which makes it a study rather
than one of its own analyses. Reading it a line at a time:

- **The sweep.** `vert_ft` at his nine heights, given as `values=` so the
  points are exactly his.
- **Two states.** `"inverted L"` is the design at its defaults, and the sweep
  moves its `vert_ft`. `"vertical"` sets `vert_ft` to the full-size height and
  `horiz_ft` to 0, which by `build_wires` is no top wire at all. Both name
  their design (`design=me`), because a study's cells say whose they are.
- **The fixed reference.** The vertical's state sets `vert_ft`, the knob the
  sweep moves. A state that does that is normally refused, but this one is the
  cell the metric is drawn `relative_to`, which makes it a *fixed* reference:
  it is solved once, at its own setting, outside the sweep and the hold, and
  drawn flat. That is the comparison he made: every inverted L against one
  vertical.
- **The hold.** `an.Hold("resonance", adjust=("horiz_ft",))` re-solves
  `horiz_ft` at every height until X = 0, which is "the top wire re-cut for
  resonance". The optimizer searches between the knob's own `ui_params`
  `min` and `max`, and a held knob without both is refused by name. That is
  why the `horiz_ft` entry above carries a comment: 1 to 135 ft contains every
  resonant top from 33 ft (at 100 ft of vertical) to 112 ft (at 20 ft), and
  stays clear of the half-wave antiresonance, so the one X = 0 between the
  bounds is the resonance wanted. Each height warm-starts from the previous one's
  answer.
- **The metric.** `an.ElevationWindow("DX gain", 2, 10, step=0.1,
  mean="power", az=0)` is his definition word for word: elevations 2 to 10°
  inclusive, 0.1° apart, power-averaged and converted back to dB, on the cut
  at azimuth 0.
- **The views.** `an.MetricPlot(dx, relative_to="vertical")` solves the far
  field at every point and plots DX gain less the vertical's, in dB.
  `an.Knobs()` draws what the hold did: `horiz_ft` against `vert_ft`.
- **The ground.** `"finite:13,0.005"`, his average ground.

## Allow it, then run it

A design file in your folder is a Python program, so it does not run until
you allow it (see
[Allowing user designs to run](/reference/cli/#allowing-user-designs-to-run)):

```bash
python -m antennaknobs allow m0agp_invl
```

```text
m0agp_invl.py: nothing unusual — only geometry math.

allowed m0agp_invl.py (this version).
```

In the workbench the same gate is the **designs need your OK to run** prompt.
Add `--edits` if you will keep editing the file, so a save does not ask again.

The design's tab lists its studies:

```bash
python -m antennaknobs analyze --list-studies --builder user.m0agp_invl
```

```text
user.m0agp_invl:DX gain vs the vertical  vert_ft at 20, 30, 40, 50, 60, 70, 80, 90, 100; 2 curves (2 states); hold resonance on horiz_ft; views MetricPlot, Knobs
                                           crosses user.m0agp_invl
```

And the study runs by its full name, the design, a colon, and the study's own
name:

```bash
python -m antennaknobs analyze --study "user.m0agp_invl:DX gain vs the vertical" --fn m0agp.png
```

```text
analysis 'DX gain vs the vertical': vert_ft at 20, 30, 40, 50, 60, 70, 80, 90, 100; 2 curves (2 states); hold resonance on horiz_ft; views MetricPlot, Knobs
== DX gain (dBi) vs vert_ft: user.m0agp_invl, inverted L ==
relative to user.m0agp_invl, vertical
     vert_ft        DX gain vs user.m0agp_invl, vertical
          20        -13.086         -9.494
          30         -9.435         -5.843
          40         -7.279         -3.687
          50         -5.960         -2.369
          60         -5.125         -1.533
          70         -4.576         -0.984
          80         -4.208         -0.616
          90         -3.957         -0.365
         100         -3.788         -0.196
== DX gain (dBi) vs vert_ft: user.m0agp_invl, vertical ==
fixed reference, solved once: -3.592
user.m0agp_invl, inverted L: held resonance on horiz_ft: 9 of 9 points held, 0 gaps, 46 solves, worst residual 2.55e-05 ohm
```

The first column is each inverted L's DX gain in dBi, the second the same
less the vertical's −3.592 dBi. The last line is the hold's report: every
height held, in 46 solves, none of them more than 3·10⁻⁵ Ω from resonance.
It runs in about 15 seconds on a laptop. `m0agp.png` is the DX-gain plot and
`m0agp-knobs.png` the held top wire, falling from 112 ft at 20 ft of vertical
to 33 ft at 100 ft. `--csv m0agp.csv` writes the same numbers at full
precision.

In the **workbench**, pick the design, then **DX gain vs the vertical** under
**Studies** in the chart's **analysis** list, and press **run**. A held sweep
waits for **run** rather than starting on the pick, unless
[`[workbench.run_on_pick]`](/reference/web/#where-the-workbench-starts-settingstoml)
says otherwise. The **Metric** view is the DX-gain plot and **Knobs** the top
wire.

## Your own function instead

`ElevationWindow` covers his definition, but a figure of merit is often not
one of the declarative metrics. Then write the function, and hand it to
`an.Metric`. The same DX gain, with the window chosen by `lo=` and `hi=`:

```python
import numpy as np

import antennaknobs.analyses as an


def dx_gain(cut):
    """The power mean of the cut, back in dB: lo= and hi= chose the window."""
    return 10 * np.log10(np.mean(10 ** (cut.gain_dbi / 10)))


DX = an.Metric("DX gain", dx_gain, over="elevation", lo=2, hi=10, step=0.1, az=0)
```

or with the window chosen inside the function, from the cut's angles, over
the default 0–90° cut:

```python
def dx_gain_masked(cut):
    """The same, choosing the 2-10 degree window inside the function."""
    window = (cut.el >= 2) & (cut.el <= 10)
    return 10 * np.log10(np.mean(10 ** (cut.gain_dbi[window] / 10)))


DX = an.Metric("DX gain", dx_gain_masked, step=0.1, az=0)
```

Either goes in `an.MetricPlot(DX, relative_to="vertical")` in place of the
`ElevationWindow`. Run through this study, both give the `ElevationWindow`'s
numbers to the last bit, at every height. The function must be a named,
module-level one; a lambda is refused, because a kept study writes the
function by reference.

A callable metric runs wherever its file runs: locally, from your own design
or study file, once allowed. The hosted workbench runs only the catalog's
functions, so a study with a function of your own is a local one.

## The results, beside his

DX gain of each inverted L relative to the full-size vertical, in dB:

| vertical section (ft) | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 |
|---|---|---|---|---|---|---|---|---|---|
| this study (momwire, az 0) | −9.494 | −5.843 | −3.687 | −2.369 | −1.533 | −0.984 | −0.616 | −0.365 | −0.196 |
| M0AGP (NEC-5) | −9.64 | −6.54 | −3.84 | −2.51 | −1.66 | −1.10 | −0.72 | −0.45 | −0.26 |

Run on our licensed NEC-5 instead of momwire, the same study agrees with the
momwire row to within 0.01 dB at every height, so the study's numbers stand
on two engines.

Against his table, eight of the nine heights agree to within 0.16 dB, the
study reading slightly less loss throughout. The ninth is 30 ft, where the
two differ by 0.70 dB. His own table breaks its step pattern there: from 40 ft
up, each 10 ft step changes the loss by about two-thirds of the step before
it (1.33, 0.85, 0.56, 0.38, 0.27, 0.19 dB), while his 20→30 and 30→40 ft
steps are 3.10 and 2.70 dB. The study's steps follow the pattern on both
sides of 30 ft (3.65, 2.16, 1.32 dB).

## The catalog's copy, and a link to it

The same study ships in the catalog, so it runs on any install without
allowing anything, and on the hosted workbench:

```bash
python -m antennaknobs analyze --list-studies --builder verticals.m0agp_invl
python -m antennaknobs analyze --study "verticals.m0agp_invl:DX gain vs the vertical" --fn m0agp.png
```

```text
verticals.m0agp_invl:DX gain vs the vertical  vert_ft at 20, 30, 40, 50, 60, 70, 80, 90, 100; 2 curves (2 states); hold resonance on horiz_ft; views MetricPlot, Knobs
                                                crosses verticals.m0agp_invl
```

The run prints the same table as above, to the last digit, labelled
`verticals.m0agp_invl`.

A workbench [link](/reference/web/#linking-to-a-chart) opens it with the
chart picked. On whichever host serves your workbench, local or hosted, add
this to its address:

```
/?design=verticals.m0agp_invl&analysis=DX%20gain%20vs%20the%20vertical&view=Metric
```

Add `&run=1` to press **run** as well. A link to `user.m0agp_invl` opens only
on the machine that has that file.

## Building one in the workbench instead

You do not have to start from Python. Build the chart in the workbench, by
picking an analysis, ticking engines or grounds and editing its range, or by
pinning sweeps from several designs. Then **keep** on the chart's header turns
it into a study, and **copy** turns a chart about one design into an analysis
for its `build_analyses()`. Either opens a dialog with the Python first. On a
local workbench, **save as study** writes it under `~/.antennaknobs/studies/`,
already allowed, and it appears under **Studies** on every design it names;
the hosted one offers copy only. See
[Keeping a chart or pins](/reference/web/#keeping-a-chart-or-pins).
