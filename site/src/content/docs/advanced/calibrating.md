---
title: Calibrating a model against your VNA
description: fit mode — solve for the parameters a tape measure can't give you (ground constants, as-built length, feedline electrical length) by fitting a measured .s1p, and read the residual to know how far to trust the answer.
---

[Overlaying a measured sweep](/reference/cli/#overlaying-a-vna-measurement)
answers *does the model match the bench?* The `fit` command inverts the
question: **what would the model have to believe to reproduce this
measurement?**

That inversion is worth something because the parameters you'd most like to
know are the ones you cannot measure with a tape:

- the ground constants under *this* yard — not the "average soil" from a table,
- the as-built length after sag, end effects, and insulated-wire velocity factor,
- the electrical length and loss of the feedline that's actually buried,
- stray reactance at the feedpoint from the connector and the balun.

A VNA sweep constrains all of these. `fit` turns that constraint into numbers,
and — just as importantly — tells you when the measurement *doesn't* constrain
what you asked it to.

## The basic run

```bash
python -m antennaknobs fit --builder dipoles.invvee \
    --measured bench_10m.s1p \
    --params length_factor angle_deg \
    --npoints 15 --fractions 0.15 --fn fit.png
```

`--params` takes the same dotted paths `optimize` resolves, so builder knobs,
per-band dicts, and terrain facets are all reachable
(`length_top`, `bands.1.halfdriver_factor`, `terrain.facets.0.eps_r`).

```
fit against 'bench_10m': 15 points, 26–31 MHz, z0 = 50 Ω

parameter                         nominal       fitted        shift
length_factor                      0.9719     0.992629   +0.0207291  +2.13%
angle_deg                         31.6846      34.6707     +2.98609   +9.42%

RMS |ΔΓ|   nominal 0.1858  →  fitted 0.0044   (20 model evaluations)
```

The plot is two panels: the three SWR traces (measured, nominal model, fitted
model) on top, and **the residual |ΔΓ| versus frequency** underneath, before and
after. The bottom panel is the one to read carefully.

## Reading the residual

The fitted RMS is the honest bottom line — it says how much of the measurement
the model can account for at all. Its *shape* says what's missing.

Take the same measurement, fitted two ways:

```bash
# just the length
--params length_factor            #  RMS 0.1869 → 0.0200
# length and droop angle
--params length_factor angle_deg  #  RMS 0.1858 → 0.0044
```

The one-parameter fit converges happily and reports a plausible +1.9% length
correction. But its residual doesn't look like noise — it has structure across
the band, because the antenna differs from the model in a way length alone
can't express. Adding the droop angle drops the residual by 4.5×, and *that*
residual is flat.

So:

- **Flat, small residual** → the model explains the measurement. The fitted
  parameters mean what they say.
- **Structured residual** (a tilt, a bump at one end, a peak at resonance) →
  something physical is missing from the model. More often than not the
  culprit is **common-mode current on the feedline**, which a differential
  model cannot reproduce at all. Fitting harder will not remove it; it will
  only push a parameter somewhere nonphysical to hide it.
- **Large residual** (the report calls out anything over 0.05 RMS) → treat the
  numbers as meaningless until you know why.

This is why `fit` reports the residual instead of just the parameters. A fit
with small residual is a much stronger statement about a model than an overlay
is — and a fit with *structured* residual is a pointer at the physics you
haven't modelled yet.

## Identifiability is the hard part

Length, ground, and feedline length all bend S11 in similar ways. Over one
narrow band they are barely distinguishable, so a fit can be simultaneously
well-converged and meaningless. `fit` caps you at **four** free parameters and
reports the conditioning of what it solved:

```
WARNING: under-determined (Jacobian condition 789). These data barely constrain
         the combination
         +0.71·length_factor  +0.71·design_freq
         — its fitted value is close to arbitrary. Fit fewer parameters, or
         measure a wider / second band.
```

That is `fit` naming the degeneracy: `length_factor` and `design_freq` both
scale the element, so moving them together changes nothing the measurement can
see. The *identified* direction is still solid — it's the blind combination
whose split between the two knobs is arbitrary.

What actually fixes it is data, not settings: **a wider sweep, or a second
band.** Two bands separate length from ground in a way one band never can.

A related warning covers bounds:

```
WARNING: angle_deg ended at a bound — the fit wanted to go further than you
         allowed.
```

Either the bound is too tight, or that knob is standing in for something the
model is missing. Both are worth knowing before you paste the value into a
design.

Free parameters default to a ±10% window (`--fractions 0.15` for ±15%, one
value or one per parameter; `--bounds lo hi lo hi` for explicit ones). The
default is deliberately tighter than `optimize`'s: a calibration is a
*correction* to a design you already believe, and a wide window invites the
optimizer to explain a bad measurement with an absurd antenna.

## Where was the VNA calibrated?

The fit compares at the plane the model's port sits on — normally the antenna
feedpoint. If you calibrated at the feedpoint, that's already like-for-like and
there is nothing to do.

For a sweep taken at the **shack end**, tell `fit` what's in between:

```bash
python -m antennaknobs fit --builder dipoles.invvee --measured shack_10m.s1p \
    --params length_factor angle_deg --plane station --line RG-213:30.5
```

`--line <cable>:<length_m>` uses the same cable catalog and matched-loss model
as the `TL` element, so the line embeds exactly as it would inside a network.
Skipping it doesn't produce an obvious error — it produces a *plausible wrong
answer*: the fit can still land the resonance about right while the feedpoint
resistance it infers is badly off, because loss and rotation in the line are
being blamed on the antenna.

If your design already models its feedline in `build_network()` (see
[station modelling](/concepts/station-modelling/)), its port **is** the station
plane — keep `--plane feedpoint` and change nothing.

## Saving the result

The command prints a paste-ready variant block of the deltas from the design's
defaults:

```python
measured_params = {
    'length_factor': 0.992629,
    'angle_deg': 34.670689,
}
```

Drop that into the design class as a named variant and every later run can
select the *calibrated* antenna with `--builder dipoles.invvee:measured` —
your model of the antenna in your yard, rather than the antenna on paper.

## Limits worth stating

- **One port.** A VNA sweep is one-port data; multi-feed designs are fitted at
  port 0.
- **Ground fitting needs a ground.** `terrain.facets.0.eps_r` is only meaningful
  with a real-ground solve (`--ground finite`), and ground is exactly the
  parameter most likely to be degenerate with length over a single band.
- **A fit is not a measurement of truth.** It's the parameter set that best
  explains one sweep under one model. The residual is what tells you how much
  of the antenna that model actually captured — which is why every run reports
  it.
