---
title: "Tuning for several bands"
description: One feed, several bands — tuning a multiband antenna by hand while watching every band's impedance on the Smith chart, and handing the same job to the band optimizer when the knobs fight each other.
---

A fan dipole, a trap vertical, a multiband EFHW: one feed line, several bands,
and every knob you turn can move all of them. Tuning such an antenna means
watching more than the band you are on. The workbench gives you two ways to
do it, and both start from the same list of bands:

- **By hand.** Turn the knobs yourself and watch every band's impedance move
  on the Smith chart at once.
- **With the optimizer.** Mark the knobs it may move and let it balance the
  bands for you, worst band first.

Which one to reach for depends on how much the knobs interact, and the
antenna below shows how to tell.

## The example: a fan dipole for 12 and 10 m

[`multiband.twoband_fan_dipole`](/reference/catalog/) is two dipoles bonded at
one feed, one cut for 12 m and one for 10 m. Its per-band knobs are grouped
under **band 0** (the 12 m element) and **band 1** (the 10 m element); the one
that matters here is each band's **length**. The numbers on this page are
momwire over average ground, the workbench's default.

## Set up the bands

Both ways start from the band list, in the **Optimize** gear menu (the gear
beside the **Optimize** toggle, next to **Live**):

1. Open the gear menu and tick **Several bands at once**. On a design whose
   bands have their own frequency knobs, as this one's do, the list starts
   with those: here **24.94** and **28.5**, the middle of each band. On other
   designs it starts with the measurement frequency.
2. Add any other band you care about: type it in MHz and press **add**. Up to
   eight; **×** removes one.
3. Close the menu.

The list belongs to the design you set it on, and it stays while you work on
that design.

## Tuning by hand

With a band list set, the Smith chart lists its bands in its bottom-left
corner, each in the colour its marker will be drawn in. **Click a band to
show it.** From then on, every knob you drag shows that band's impedance
moving on the chart with a short trail behind it, alongside the live dot for
the measurement frequency. Click it again to hide it.

Each band shown costs one more solve per knob change. That is why none is
shown to start with, and why the toggles sit on the chart: show the bands the
knob in your hand affects, hide the rest. The extra solves are cheap (the
design is built once and read at every band, about twice as fast as a full
solve per band), but on a large design they add up.

Now drag **band 0 length**. Measured on this antenna, 5 cm either way:

| Change | 12 m (24.94 MHz) | 10 m (28.5 MHz) |
|---|---|---|
| as designed | 52.1 − j6.8 Ω, SWR 1.15 | 51.5 − j2.4 Ω, SWR 1.06 |
| band 0 (12 m) length −5 cm | 50.1 − j17.2 Ω, SWR 1.41 | 51.4 − j2.9 Ω, SWR 1.07 |
| band 0 (12 m) length +5 cm | 54.4 + j4.6 Ω, SWR 1.13 | 51.5 − j2.0 Ω, SWR 1.05 |
| band 1 (10 m) length −5 cm | 52.1 − j6.9 Ω, SWR 1.15 | 45.0 − j35.2 Ω, SWR 2.08 |
| band 1 (10 m) length +5 cm | 52.1 − j6.6 Ω, SWR 1.14 | 57.0 + j23.5 Ω, SWR 1.58 |

Each element moves its own band and barely touches the other: 5 cm on the
12 m element swings 12 m's reactance by about 11 Ω and 10 m's by half an ohm.
On the chart, the 12 m ring travels while the 10 m ring sits still. An
antenna like this tunes by hand, one knob per band, in turn: set band 0's
length until the 12 m ring crosses the real axis near the centre, then band 1's
for the 10 m ring, then a final touch on the first.

A few things help along the way:

- **The live dot is the measurement frequency**, and the readout, the SWR and
  the pattern follow it. It is drawn over the band rings, so it stays visible
  when the dial sits on one of your bands.
- **Touching a band's knob moves the dial**, on this design, while the dial's
  lock is closed: the dial jumps to that band's own **freq** knob, the same
  frequency the band list started from. So the live dot lands on the ring of
  the band you are tuning, with its numbers in the readout. Open the lock to
  keep the dial where you put it.
- **To see the whole span**, a frequency sweep across both bands (the SWR view
  is the plainest) shows both dips. With **auto re-run** on, it re-sweeps half
  a second after you let go of a knob; with it off, the curve fades as stale
  until you press **run**, and the ring that marks the measurement frequency
  on it disappears, since it would mark the antenna as it was.

## When the knobs fight

Hand tuning works because each knob here mostly drives one band. Not every
multiband antenna is that kind. On UR0GT's three-band vertical (160/80/40 m),
the height, the top wire and the coupling capacitor each move every band: fix
40 m and 80 m drifts, fix 80 m and 160 m drifts. You can still watch all three
rings while you try, and the chart shows you quickly that you are chasing your
tail. That is the job for the optimizer.

## Letting the optimizer do it

The band optimizer uses the same band list. It tunes the knobs you mark for
the best compromise across all the bands at once.

1. **Mark the knobs it may move.** Right-click a knob, tick **Optimize this
   knob**, and set its **Optimize range**, the bounds it searches. (With a knob
   focused, **o** toggles the mark.) Knobs inside a band group are marked like
   any other. Here: **band 0 length** and **band 1 length**, each left on the
   range the design gives it.
2. **Turn on Optimize.** With the band list set, the run tunes for every band
   in it rather than for the measurement frequency.
3. **Watch it run.** The readout shows each band's SWR and the worst one, and
   each band's impedance moves on the Smith chart in its own colour, the worst
   band's ring drawn brightest.

It minimizes a blend of the worst band and the average:

  (1 − w) · worst band's SWR + w · mean of the bands' SWR

**Balance** in the gear menu sets w (default 0.5). At 0 it improves the worst
band only, which lets it drag the easy bands down to the hardest one's SWR;
the average term stops that, trading a little on the worst band for a lot on
the rest. On the UR0GT vertical, w = 0.2 settles on SWR 1.86 on all three
bands, and w = 0.5 on 1.93 / 1.93 / 1.34: 0.07 worse on the worst band, half
an SWR unit better on 40 m.

When it finishes, a table gives each band's SWR before and after, plus the
worst and the mean. On the fan dipole, from the design's own lengths:

| Band | Before | After |
|---|---|---|
| 12 m, 24.94 MHz | 52.1 − j6.8 Ω, SWR 1.149 | 53.3 − j0.7 Ω, SWR 1.068 |
| 10 m, 28.5 MHz | 51.5 − j2.4 Ω, SWR 1.057 | 51.9 − j0.4 Ω, SWR 1.038 |

It got there by lengthening the 12 m element 2.7 cm (5.877 → 5.904 m) and the
10 m element 3 mm (5.190 → 5.193 m), in 59 evaluations. Small moves, because
the design was close; from an antenna you have dragged far off, it travels
further and the before column is worse. Read the notes under the table: one
says when a knob ended at the edge of its range (the best value may lie past
it: widen the range and run again), another when no band is near a match.

Opening the gear menu pauses Optimize, and closing it resumes with one run for
all the edits, so changing the bands or the balance never starts several runs.

### Exact resonance on every band

The workbench's band run minimizes SWR. The command line can also solve for
an exact condition on every band, which is worth trying when you have as many
knobs as conditions. Resonance (X = 0) is one condition per band, so two bands
and two lengths:

```bash
python -m antennaknobs optimize --builder multiband.twoband_fan_dipole \
    --bands 24.94:res,28.5:res --mode root \
    --params bands.0.length bands.1.length
```

On the fan dipole this finds both reactances below 10 µΩ in 9 evaluations,
SWR 1.069 / 1.039. When there is no exact answer within the knobs' ranges,
the root form says so (`no root in the box`, or which knob moves no band)
rather than returning a near miss; the minimax form is the one to reach for
first. [Optimizing across bands](/reference/cli/#optimizing-across-bands) covers
the forms, the per-band objective, feed and Z₀, and the band-by-band
`sequential` mode.

## Keeping a run

A run you want to come back to can be kept. Under a finished band run's
table, **Keep…** saves it as a study: where it started, the knobs it moved
with their ranges, the bands, the balance, and the answer. It is listed under
**Studies** in the design's analysis picker afterwards, where picking it jumps
the knobs to its answer and **Run again from its start** repeats it. That is
the easy way back to the same setup after you change something else about the
antenna. The command line's `optimize --bands … --keep NAME` does the same;
see [Keeping a run](/reference/cli/#keeping-a-run).

## On the command line

The same run as the workbench's, as one command:

```bash
python -m antennaknobs optimize --builder multiband.twoband_fan_dipole \
    --bands 24.94,28.5 --params bands.0.length bands.1.length
```

It prints the knobs' ranges, the per-band table before and after, and a
params block to paste over the design's. `--mean-weight` is the balance,
`--bound NAME=LO:HI` a knob's range, and `--ground` the ground (average ground
when not given).
