---
title: "How thin can you go? Wire gauge for POTA"
description: An advanced worked example — weigh 28 vs 22 vs 18 AWG antenna wire against SWR bandwidth and radiated power, with skin-effect loss and insulation modelled for real.
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
or 18 AWG copper, bare or PVC-insulated, each entry carrying its real
radius, conductivity, jacket, and grams per meter.

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
  to the wire, which acts as distributed series inductance — the wave on
  the wire slows down, and the antenna tunes a few percent *lower* than
  bare wire cut to the same length. That's the velocity factor behind
  "my cut-to-formula insulated dipole came out long."

Both engines model both effects. Conductor loss: the momwire loading and
PyNEC's native `LD 5` card agree on the added resistance to half a
percent. Insulation: NEC-2 has no insulated-wire card, but the same
jacket inductance enters as a distributed series load (`LD 2`, henries
per metre), and the two engines agree on the resonance shift to a few
percent. Each pairing is a cross-engine oracle in the test suite — two
independent implementations of the same physics, kept honest against
each other.

## The numbers

Stock design, PVC-insulated wire, retuned length per gauge not required —
the numbers below are the dropdown flipped with everything else constant
(2:1 SWR window from the band-locked sweep; weight for the full ~10 m of
wire; loss relative to a perfect conductor):

| wire | weight | 2:1 SWR window | radiated power |
|---|---|---|---|
| 28 AWG PVC | **17 g** | 550 kHz | −0.36 dB (92 %) |
| 22 AWG PVC | 53 g | 605 kHz | −0.18 dB (96 %) |
| 18 AWG PVC | 111 g | **645 kHz** | **−0.11 dB (97.5 %)** |

Three readings worth taking home:

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
   ~100 kHz broader than 28 AWG *and* radiates more. Thin wire's loss
   does not buy its bandwidth back.
3. **The insulation is a bigger tuning effect than the gauge.** Flip any
   PVC entry to its bare twin and the resonance jumps ~500 kHz — several
   times the entire gauge-to-gauge bandwidth difference. Cut your antenna
   for the wire you'll actually hang.

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
