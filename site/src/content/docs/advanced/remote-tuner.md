---
title: "A doublet into a remote tuner"
description: An advanced worked example — a 130 ft doublet on window line into a remote L-network tuner, tuned by hand on the Smith chart, band by band, with where the power goes.
---

A popular all-band HF station: a flat centre-fed doublet, window line down to
a balun, and an **L-network tuner at the bottom of the line**, with coax from
there to the rig. Mike, WA7ARK, posted the numbers for his on QRZ and asked
how one would do it in antennaknobs. The catalog design
`wire.doublet_remote_tuner` is that station:

```
rig (50 Ω) → L-network tuner → balun 1:1 or 1:4 → window line → doublet centre
```

[Open it in the workbench](https://app.antennaknobs.dev/?design=wire.doublet_remote_tuner).
The knobs are in **feet**, the units you would measure the real thing in:

| knob | stock | what it is |
|---|---|---|
| `length_ft` | 130 | the doublet, tip to tip |
| `height_ft` | 30 | its height |
| `line_ft` | 30 | window line from the feed to the balun |
| `balun_ratio` | 1:1 | 1:1 or 1:4 |
| `tuner_l_uH` | 1.87 | the tuner's series coil |
| `tuner_c_pF` | 413 | the tuner's shunt capacitor |
| `tuner_c_side` | rig | which side the capacitor sits on: across the **balun**, or across the **rig** |

The line is Mike's: Wireman #552 with his 0.97 velocity factor and the
nominal ~400 Ω he gives it. (Its loss comes from the catalog's `window-450`
entry: no citable loss figures for #552 turned up.) The coil and capacitor
range over an MFJ-926B remote tuner's published ranges, 0–24.86 µH and
0–3961 pF, so every setting is one that box can reach. The coil has a Q of
200 and the capacitors are ideal.

The stock tuner setting matches the stock station at 7.15 MHz. Because the
knobs are lengths in feet, the design has no band row: set the frequency
directly. Every band solves on the same mesh, one fine enough for 10 m.

## The planes

The readout's **plane** selector picks the point along the chain where the
impedance, SWR and Smith chart are read
([how planes work](/reference/web/#the-measurement-plane)). This design names
three, source to antenna:

- **rig (tuner input)**: what the rig sees, and the plane where SWR 1 means
  "tuned";
- **inside tuner (L–C)**: the node between the coil and the capacitor;
- **tuner output / balun input**: the load the tuner has to match, i.e. the
  doublet's feed impedance carried down the line and through the balun.

## Tuning it by hand on the Smith chart

An L network is two parts. You turn the one **nearer the antenna** until the
point lands on the circle that the other part moves it along. Then you turn
the other part to slide along that circle to the centre. The design draws the
circle for you.

When the load at the tuner has **more than 50 Ω** of resistance, put the
capacitor **across the balun**. The coil is then the last part, and a series
coil moves the point along a circle of constant resistance, R = 50 Ω.
When the load's resistance is **below 50 Ω**, put the capacitor **across the
rig**. The coil comes first, the capacitor last, and the circle is one of
constant conductance, G = 20 mS. The chart's **Y** button adds the
admittance grid that circle belongs to. With the 1:1 balun, only 40 m wants the
capacitor on the rig side.

### 20 m, at 14.3 MHz

1. Set the frequency to 14.3 MHz, and `tuner_c_side` to **balun**.
2. Pick the plane **tuner output / balun input**. The load is about
   308 + j921 Ω, an SWR of 61 on 50 Ω coax.
3. Pick **inside tuner (L–C)**. The chart highlights the R = 50 Ω circle.
   Turn `tuner_c_pF` until the point sits on it: **39 pF** puts it at about
   50 − j389 Ω. (*Sweep this knob…* in the knob's menu traces its path, so
   you can see where it crosses. By default it sweeps the knob's whole range
   in 11 steps, which for the capacitor is 396 pF a step, far too coarse
   here: narrow the range around where you expect the answer, say 10–100 pF
   on 20 m, and raise the points to 50 or more.)
4. Pick **rig (tuner input)** and turn `tuner_l_uH` until the point reaches the
   centre: **4.32 µH** gives SWR 1.05. The coil's Q is why it isn't exactly 1:
   the resistance at the rig is 52 Ω.

### 80 m, at 3.75 MHz

The same three moves. The load at the tuner is about 128 + j456 Ω, so the
capacitor goes across the balun again. **228 pF** puts the inside-tuner point
on the circle (about 50 − j291 Ω), and **12.38 µH** then gives SWR 1.03 at the
rig.

### How far can you QSY?

Run a frequency sweep at the rig plane after tuning. The parts are fixed, so
the curve shows how far the match holds:

- The 20 m tune at 14.3 MHz is still SWR 1.2 at 14.35 MHz, but 3.2 at
  14.0 MHz.
- The 80 m tune at 3.75 MHz reaches 6.5 at 3.6 MHz and 6.7 at 3.9 MHz.

A remote auto-tuner retunes for exactly this reason.

All of these numbers are on bs2 (momwire's B-spline solver) over the
workbench's default Sommerfeld ground (13 / 0.005 S/m).

You can also let the optimizer do it: mark `tuner_l_uH` and `tuner_c_pF`, set
the objective to SWR, and run it at the frequency you're on. The optimizer
can't flip `tuner_c_side`, so if a run ends far from SWR 1, switch the
capacitor's side and run it again. From the command line:

```bash
antennaknobs optimize --builder wire.doublet_remote_tuner --bands 14.2 \
    --params tuner_l_uH tuner_c_pF --set tuner_c_side=balun
```

## Band by band: what would an auto-tuner pick?

The design's analysis **tuner per band** puts the tuner in its automatic mode
(it picks its own parts at every frequency, capacitor side included) and
tabulates Mike's frequencies from 3.6 to 28.5 MHz, for both baluns. Each row
gives:

- the load at the tuner and the parts the tuner picks;
- the SWR at the rig;
- where the power goes: the line, the balun, the coil, and the share that
  reaches the antenna.

A band the MFJ's part ranges can't match is flagged.

```bash
antennaknobs analyze --builder wire.doublet_remote_tuner --analysis "tuner per band"
```

A few rows, with the 1:1 balun (bs2, Sommerfeld 13 / 0.005):

| MHz | load at the tuner | capacitor | coil | capacitor value | reaches the antenna |
|---|---|---|---|---|---|
| 3.6 | 73.9 + j293.9 Ω | across balun | 10.7 µH | 317.5 pF | 95.3 % |
| 7.0 | 27.2 − j79.8 Ω | across rig | 2.38 µH | 408.3 pF | 92.1 % |
| 14.0 | 211.8 + j712.7 Ω | across balun | 4.00 µH | 46.4 pF | 92.6 % |
| 28.0 | 98.1 + j186.8 Ω | across balun | 0.803 µH | 59.7 pF | 94.9 % |

With a 1:4 balun every load is a quarter of these. The balun is modelled as a
current balun: only its winding resistance, and no magnetizing inductance.

**Choosing the line length and the balun.** With an auto-tuner every band
matches, so the question becomes how much power is lost on the worst band.
`band-loss` answers it by retuning on every band at each line length:

```bash
antennaknobs band-loss --builder wire.doublet_remote_tuner \
    --each balun_ratio=1:1,1:4 --search line_ft=30:100:1
```

On this antenna:

- **With the 1:1 balun, the 30 ft line is already the best.** The worst band
  is 25 MHz, where 91.9 % reaches the antenna.
- **With the 1:4 balun, 30 ft gives 91.4 % (worst at 7 MHz), and the best
  length, 35.2 ft, gives 92.2 %.**

The spread is under a percentage point, a tenth of a dB. A tuner at the
bottom of 30 ft of window line is within a whisker of the best these parts
can do. (The line here is dry. Wet window line loses several times as much.)

## Against Mike's own table

Mike's EZNEC/AutoEZ model and this design agree at 3.6 MHz: 75.6 + j289.8 Ω
there against 73.9 + j293.9 Ω here, and parts within a few percent. On the
upper bands the loads differ.

The tuner and the line are not where the difference comes from:

- **The tuner:** fed his loads, the tuner arithmetic here picks his parts to
  within 2 %.
- **The line:** varying the line's impedance and length doesn't close the
  gap.

So the difference is in the antenna model itself: the ground, the wire and
any insulation, which his table doesn't state. Settling it needs his model.

If you have your own EZNEC model of a station like this, you don't need this
design at all. Since v0.101.0 you can **Open…** the `.ez` itself, and its
wires, transmission line and transformer come across as they are
([EZNEC `.ez` models](/reference/nec-import/#eznec-ez-models)). The source at
the end of the line is what your tuner sees, so a frequency sweep gives the
tuner's load on every band. One limit for now: a line with loss is held at the
model's own frequency, and the app flags the others.

## Engines

bs2 and PyNEC solve this design and agree to within 1.2 % on the tuner's load.
The NEC-5 engine solves it too from the release after v0.101.0, which refuses
it. The refusal was ours, not NEC-5's: the centre gap's two sides go to
different parts of the station, and antennaknobs, not the engine, connects
them (AK#1977). On the 20 m tune the three engines agree to about 2 Ω at the
rig.
