---
title: "How thin can you go? Wire gauge for POTA"
description: An advanced worked example — weigh 28 through 12 AWG antenna wire against SWR bandwidth and radiated power, with skin-effect loss and insulation modelled for real.
---

Every portable operator has packed this decision. The 28 AWG magnet-wire
dipole weighs nothing and disappears into a tree; the 18 AWG version
survives being yanked out of one. Between them sits a real three-way
tradeoff — **weight vs. SWR bandwidth vs. radiated power** — that mostly
gets settled by folklore ("thin wire is lossy", "thick wire is broader").
This example settles it with a solver instead.

One catalog design carries the whole comparison:
[`dipoles.pota_invvee`](/reference/catalog/) — a half-wave 20 m inverted-V
on a 7 m telescoping pole over average ground, where **the wire itself is
a knob**. The `wire_type` dropdown selects from a wire catalog the same
way the station designs pick a feedline from the cable catalog: 28, 22,
18, 16, 14 or 12 AWG copper, bare or PVC-insulated, each entry carrying its
real radius, conductivity, jacket, and grams per meter.

## What the wire actually does in the model

This isn't a lookup-table correction. Since momwire's distributed-loading
release, the wire's material enters the impedance matrix itself as a
per-meter series impedance:

- **Skin-effect resistance.** At 14 MHz current flows in the outer
  ~17 µm of the copper, so RF resistance runs 5–15× the DC value —
  about 1 Ω/m for 28 AWG, 0.3 Ω/m for 18 AWG. The solver uses the exact
  solid-round-conductor law (the same one NEC's `LD 5` card implements),
  valid from DC through full skin effect.
- **Insulation loading.** A dielectric jacket stores E-field energy next
  to the wire, which slows the wave on the wire, and the antenna tunes a
  few percent *lower* than bare wire cut to the same length. That's the
  velocity factor behind
  "my cut-to-formula insulated dipole came out long."

Both engines model both effects. Conductor loss: the momwire loading and
PyNEC's native `LD 5` card agree on the added resistance to half a
percent. Insulation: NEC has no insulated-wire card, so the NEC deck
spells the jacket the way momwire models it, as a pair. The wire card
carries a slightly larger *equivalent radius* (the jacket's effect on the
charge), a distributed series load (`LD 2`, henries per metre) puts back
the inductance the larger radius removed, and `LD 5` is rescaled so the
copper loss stays the real conductor's. Each pairing is a cross-engine
oracle in the test suite — two independent implementations of the same
physics, kept honest against each other.

## The numbers

The stock design, PVC-insulated wire, with the dropdown flipped and
everything else held — the same length for every wire. The 2:1 SWR window is
on 50 Ω over average ground; the weight is for the full ~10 m of wire; the
loss is relative to a perfect conductor:

| wire | weight | resonance | 2:1 SWR window | gain vs lossless wire |
|---|---|---|---|---|
| 28 AWG PVC | **17 g** | 14.00 MHz | 590 kHz | −0.35 dB (92 %) |
| 22 AWG PVC | 53 g | 14.08 MHz | 640 kHz | −0.17 dB (96 %) |
| 18 AWG PVC | 111 g | 14.17 MHz | 680 kHz | −0.11 dB (97.5 %) |
| 16 AWG PVC | 162 g | 14.21 MHz | 700 kHz | −0.09 dB (98 %) |
| 14 AWG PVC | 249 g | 14.22 MHz | 710 kHz | −0.07 dB (98.5 %) |
| 12 AWG PVC | 377 g | 14.25 MHz | **740 kHz** | **−0.05 dB (99 %)** |

Re-cutting each wire to resonance at 14.1 MHz moves its window by 10 kHz
or less and its loss not at all, so the table reads the same either way.

Four readings worth taking home:

1. **The loss argument is real but small.** Going from 18 AWG all the way
   down to 28 AWG costs a quarter of a decibel — nobody on the other end
   will hear it. The power budget in the workbench shows exactly where it
   went: a **wire loss (I²R)** row that grows from ~2.5 % to ~8 % of the
   input power as the wire thins.
2. **Bandwidth favors thick wire, for the geometric reason.** Two effects
   stack here and pull the same way with different price tags: a fatter
   conductor is intrinsically broader (lower ln(L/a) Q — free), and a
   lossier conductor is *also* broader (resistance flattens the SWR
   curve — paid for in watts). The table shows the honest sum: 18 AWG is
   ~90 kHz broader than 28 AWG *and* radiates more. Thin wire's loss
   does not buy its bandwidth back.
3. **Past 18 AWG the returns flatten.** From 18 to 12 AWG buys 0.06 dB and
   60 kHz of window for 3.4× the weight. The case against thin wire is
   mostly made by 22 AWG; the heavy gauges are for strength, not signal.
4. **The insulation is a bigger tuning effect than the gauge.** Flip any
   PVC entry to its bare twin and the resonance jumps 370–670 kHz, to about
   14.65 MHz — several times the entire gauge-to-gauge bandwidth
   difference. Even among the PVC wires, most of the 250 kHz the
   resonance walks from 28 to 12 AWG is the jacket: a thin conductor
   carries a proportionally thicker one, and bare wire of every gauge
   resonates within 50 kHz of the others. Cut your antenna for the wire
   you'll actually hang.

And the weight column is the one the solver can't argue with: the 28 AWG
antenna is **17 grams**. For a summit activation where every antenna is a
compromise, −0.36 dB for a 6× lighter pack is a fine trade — now it's a
number instead of a guess.

## Try it

Open [`dipoles.pota_invvee`](https://app.antennaknobs.dev/) in the
simulator, put the sweep on 20 m, and flip `wire_type` through the
catalog. Watch the **wire weight** row in the Info pane, the **wire loss
(I²R)** row in the power budget, and the SWR trace breathe as the gauge
changes. Then flip 22 AWG PVC to bare 22 AWG and watch the whole
resonance walk up the band — the velocity factor, live.

The design also carries the comparison as charts, under **Wire gauge** in
the chart picker, each with one curve per PVC gauge:

- **Z vs length by gauge** — R and X against `length_factor`. Each wire's
  X = 0 crossing is its resonant length, from 0.934 for 28 AWG to 0.951 for
  12 AWG.
- **resonant length by gauge** — the length re-held at resonance as the
  mast goes from 4 to 10 m, with the held `length_factor` drawn beside it.
- **patterns by gauge** — the elevation and azimuth cuts and the pattern
  table. The shapes lie on top of each other; only the peak gain moves,
  by the loss column above (4.94 dBi for 28 AWG, 5.23 dBi for 12 AWG).
- **band-tuned SWR by gauge** — each wire with its length *and* droop angle
  tuned for the band edges (the worse of the SWRs at 14.0 and 14.35 MHz as
  low as it goes), swept wide enough to show the whole 2:1 window.

That last chart answers the question the table above leaves open: what if
you cut each wire for the band instead of keeping one length? Every gauge
then lands at about 42–43° of droop, bottoms out near 1.07 at 14.18 MHz,
and covers all of 20 m:

| wire | 2:1 SWR window | worst band-edge SWR |
|---|---|---|
| 28 AWG PVC | 603 kHz | 1.51 |
| 22 AWG PVC | 644 kHz | 1.47 |
| 18 AWG PVC | 673 kHz | 1.45 |
| 16 AWG PVC | 689 kHz | 1.44 |
| 14 AWG PVC | 708 kHz | 1.42 |
| 12 AWG PVC | 726 kHz | 1.41 |

Tuned for the band, gauge is worth about a tenth of an SWR unit at the
edges. On this antenna, bandwidth alone is no reason to carry heavier wire.
The tunings are fixed numbers for the stock 7 m mast; move the mast and
they no longer apply.

The same four run from the command line:

```bash
python -m antennaknobs analyze --builder dipoles.pota_invvee --list
python -m antennaknobs analyze --builder dipoles.pota_invvee \
    --analysis "Z vs length by gauge" --fn gauge.png
```
