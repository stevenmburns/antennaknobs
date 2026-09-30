# Sweep framework, step 8: metrics you define (design note)

Status: proposal for review (2026-09-30). It follows step 7 (studies, states,
patterns, keep) and is built after step 7's unit 4 (#1827) lands.

## The example that motivates it

M0AGP's QRZ post "Inverted L vs full-size vertical — 'DX Gain' comparison"
(thread 1005128, first post only) compares a 160 m quarter-wave vertical
(about 130 ft) with inverted Ls made by shortening the vertical section and
bending the rest horizontal. Each antenna has two elevated radials 5 ft up, over
"Average" ground (13, 0.005). The modelling is NEC-5 through AutoEZ.

His figure of merit is **DX gain**:
- take the gain in 0.1° steps over 2°–10° elevation;
- convert each dB value to a power ratio;
- average the ratios, and convert the average back to dB.

He points out, correctly, that averaging dB values is meaningless. He then
reports each inverted L's DX gain **relative to the vertical's**:

| vertical section (ft) | % of the vertical | DX gain vs vertical (dB) |
|---|---|---|
| 100 | 77 % | −0.26 |
| 90 | 69 % | −0.45 |
| 80 | 62 % | −0.72 |
| 70 | 54 % | −1.10 |
| 60 | 46 % | −1.66 |
| 50 | 38 % | −2.51 |
| 40 | 31 % | −3.84 |
| 30 | 23 % | −6.54 |
| 20 | 15 % | −9.64 |

This is the Builder-study case from step 7's addendum, where a new antenna is
compared against a standard reference. It also needs a quantity we don't
compute, and would not have thought to build in. Figures of merit like this are
personal: every serious modeller has one. So the framework should let the user
define the metric, not just ship ours.

## What exists

- **Pattern analyses** (`sweep=None`) draw `Elevation(az=)`, `Azimuth(el=)`
  and `PatternTable()`.
  - The table's columns are fixed: `/pattern_metrics`'s peak gain, take-off,
    azimuth, F/B, beamwidths and RDF.
- **Swept analyses** draw only Z-derived views (`Rx`, `Swr`, `S11`, `Smith`,
  `Map`, `Table`, `Knobs`). No swept view reads the far field.
- **`an.Hold("resonance", adjust=(...))`** re-solves knobs at every sweep
  point. That is how an inverted L can stay resonant while its vertical
  section shrinks.
- **The catalog `verticals/inverted_l`** (knobs `vert_frac`, `horiz_frac`,
  `length_factor`, `base`) and `verticals/vertical` (`length`, `base`)
  hard-code 4 and 3 radials. Both are modelled in free space by default.

## Proposal

### 1. A metric is a value computed from a pattern cut

```python
DX = an.ElevationWindow("DX gain", 2, 10, step=0.1, mean="power", az=an.PEAK_AZ)
```

- **Declarative metrics** form a small family, all frozen dataclasses like
  every other spec object:
  - `ElevationWindow(lo, hi, step, mean="power"|"db"|"max")`
  - `GainAt(el=, az=)`
  - `TakeOff()`
  - `PeakGain()`
  - and the table's existing columns, re-expressed as metrics so there is only
    one path.
- **They are data:**
  - they round-trip through `to_code()`/`to_data()`;
  - "keep as study" can write them;
  - the hosted instance serves them, since no user code runs;
  - the workbench can show their parameters.
- **`az=`** is the cut's azimuth:
  - a number fixes the cut;
  - `an.PEAK_AZ` uses the azimuth of peak gain;
  - `an.MEAN_AZ` power-averages over azimuth.

  M0AGP doesn't say which he used. The inverted L is asymmetric, so the choice
  matters and the study must state it.

### 2. A callable escape hatch

```python
def dx_gain(cut: an.Cut) -> float:
    lin = 10 ** (cut.gain_dbi[(cut.el >= 2) & (cut.el <= 10)] / 10)
    return 10 * np.log10(lin.mean())


DX = an.Metric("DX gain", dx_gain, over="elevation", step=0.1, az=an.PEAK_AZ)
```

- **The input contract, `an.Cut`:**
  - the angles, `el` or `az`, in degrees;
  - `gain_dbi` for total, vertical and horizontal polarisation;
  - the frequency and the cut's fixed angle.

  `over="pattern"` (the full 2-D grid, for RDF-like metrics) is a later
  extension, not part of v1.
- **Trust is unchanged.** A callable can only come from a `.py` that already
  runs: the catalog, a trusted user design, or a trusted study. The hosted
  instance runs only the catalog.
- **Printing it back.** `to_code()` cannot print a lambda, so `Metric` takes a
  **named module-level function** and writes it by reference. A lambda is
  refused by name.
  - "Keep as study" can write a reference only when the function is
    importable by a qualified name (a catalog function).
  - A metric defined in a user study is written as a comment that says to
    copy the function across. That is the same pattern as unit 4's
    engine-option comments.

### 3. Metrics as swept output: a far-field solve per sweep point

```python
an.Analysis(
    "DX gain vs vertical section",
    an.Sweep("vert_ft", 20, 130, points=12),
    hold=an.Hold("resonance", adjust=("horiz_frac",)),
    views=(an.MetricPlot(DX, relative_to="vertical"),),
    ...
)
```

- **`MetricPlot(metric, relative_to=None)`** is a new swept view. It plots a
  metric against x, which costs one far-field cut per sweep point: 81 angles
  for the 2°–10° window, cheap next to the solve itself.
- **`relative_to=`** names a cell (a state or a design). It plots the
  difference in dB, which is M0AGP's "vertical = 0" and his way of reducing the
  dependence on ground.
- **`PatternTable(metrics=(DX, ...))`**: pattern analyses gain user columns
  beside the fixed ones.
- **The CLI** (`analyze`) prints metric columns in its table and in `--csv`.

### 4. The M0AGP study itself

- **Knobs:**
  - `verticals/inverted_l` and `verticals/vertical` gain an `n_radials` knob.
    The current 4 and 3 stay as defaults, so existing numbers don't move.
  - A vertical-section length knob in feet or metres is needed, or the study
    sweeps `vert_frac` and labels the axis in feet.
  - The design needs a 160 m band preset if it lacks one.
- **Form:** `inverted_l`'s `Builder.build_studies()`, with the full vertical
  as the reference. This is either `verticals/vertical`, or an
  inverted L with the top wire removed, if the builder can drop a zero-length
  wire cleanly. Decide when building.
- **Radials and ground:** two radials at 5 ft (1.524 m), over finite ground
  (13, 0.005).

## Gates

1. **The two metric forms agree.** The declarative `ElevationWindow` and a
   hand-written callable equal to it give identical numbers on the same
   pattern. They are `==`, not approximately equal: same cut, same arithmetic.
2. **M0AGP's table is reproduced on NEC-5 first.** The target is −1.10 dB at
   70 ft (54 %), and the whole table within a stated tolerance. Only then run it
   on momwire, and report both engines. Given the uncertainty in `az=`, run
   `PEAK_AZ`, `MEAN_AZ` and a fixed cut, and say which reproduces him.
3. **Keeping round-trips.** Keeping a `MetricPlot` chart gives back the same
   curve bit-equal, as unit 4's core gate does.
4. **Hosted.** A study with a callable metric is never offered there: the
   hosted instance runs only the catalog.

## Units (after review)

1. **Declarative metrics** plus `PatternTable(metrics=)` and the CLI and CSV
   columns. The existing fixed columns are re-expressed as metrics, bit-equal
   to today's `/pattern_metrics`.
2. **`MetricPlot`**, a far-field cut per sweep point, `relative_to=`, and the
   workbench chart.
3. **The callable `Metric`** with the `Cut` contract, its reference printing,
   and keep's comment fallback.
4. **The M0AGP study:** the knobs, `build_studies()`, and the NEC-5
   reproduction of the table.

## Questions for review

1. **`az=` default.** Recommendation: `PEAK_AZ`, the cut through the main
   lobe, which is what an elevation plot in EZNEC/AutoEZ usually shows.
2. **`over="pattern"` in v1?** Recommendation: **no**. Elevation and azimuth
   cuts cover DX gain and every column in the table except RDF, and RDF
   already exists.
3. **Can a callable metric reach the workbench, or only the CLI?**
   Recommendation: **both**, locally. Studies already run their `.py` on the
   local workbench.
4. **Public use.** M0AGP's post is public, but per the release rule nothing is
   posted until this ships in a release. A reply showing his table reproduced
   on NEC-5 and momwire, with the study attached, is the natural post then.
