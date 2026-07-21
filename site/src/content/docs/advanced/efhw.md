---
title: "The end-fed question: where do the watts go in a 49:1?"
description: An advanced worked example — a POTA end-fed half-wave sloper with a real transformer, real coax, and real wire, itemized watt by watt.
---

The end-fed half-wave is the most argued-about antenna in portable radio.
Its fans point at the convenience — one wire over a branch, feed it at
the bottom, no feedpoint dangling mid-air. Its critics point at the black
box that makes it possible: the little 49:1 transformer, plus the
counterpoise question, plus whatever the coax is quietly doing. The
argument is usually conducted in folklore because the system is hard to
reason about piecemeal — every piece interacts.

[`wire.efhw_sloper`](/reference/catalog/) models the whole chain at once:
~9.5 m of thin wire sloping down at ~63° (the `slope_deg` knob — the
apex, ≈10 m at the defaults, is derived from it) to a feed point at
1.5 m, into a step-down unun with a real magnetizing branch and core
loss, a compensation capacitor, a short counterpoise, and 5 m of RG-58 to
the rig. Every stage is a knob, and the power budget itemizes each one.

## Why a transformer at all

The end of a half wave is a voltage antinode: the model's feedpoint
impedance at resonance is **~2.2 kΩ** — no rig drives that directly.
`unun_ratio` picks the classic step-downs (49:1, 64:1, or 225:4); at the
stock 49:1 the rig sees 58 − 3j Ω, **SWR 1.17**, on 14.1 MHz. The
transformer composition is exact in the network layer: idealize the unun
(huge magnetizing L, no comp cap, zero-length line) and the rig impedance
is the feedpoint divided by turns² to numerical precision — an oracle the
test suite pins. Flip the ratio dropdown and the differences are honest
too: 64:1 lands SWR 1.40 and 225:4 lands 1.26 on this particular wire,
because the "right" ratio depends on a feed impedance the antenna's
height and slope keep moving.

Anti-resonance trivia worth knowing: an *ideal-wire* end-fed is a
numerically nasty solve — the impedance peak at the half-wave point is a
near-singularity. The real wire loss modelled since v0.23 damps it, which
is both why this design solves cleanly and why physical EFHWs are more
forgiving than lossless theory suggests.

## Where the watts go

At the stock operating point the budget reads (fractions of input power):

| stage | share |
|---|---|
| unun core loss (magnetizing branch) | ~0.6 % |
| 5 m RG-58 | ~6.0 % |
| wire loss (I²R), 28 AWG PVC | ~6.1 % |
| **structural efficiency** | **~87 %** |

One label deserves care: that ~87 % is **structural efficiency** — the
input power not burned in components and conductors — and it is the
number this page's knobs can move. It is *not* the fraction that leaves
as sky wave: this sloper runs steep and low, and over average ground
the dirt takes its share of what the structure delivers. The pattern
integral puts **radiated (incl. ground) at ~32 %** for the stock 20 m
setup (~39 % for the 40 m variant below — the flatter 30° slope gives
back more from the dirt's ledger than its extra wire loss costs). Both
numbers are true, in different ledgers — the accounting is the subject
of [Three ledgers of efficiency](/advanced/pota-performer/#the-efficiency-claim-true-in-its-ledger).

Three readings worth taking home:

1. **The wire is the transformer's equal.** The scary lossy-looking
   ferrite box burns under a percent at mid-band with the stock
   magnetizing Q; the innocent-looking 28 AWG wire burns six times that,
   because the half-wave's current maximum lives in the middle of the
   thin wire. Flip `wire_type` to 18 AWG PVC and the wire row drops to
   ~1.9 % (structural efficiency 91 %) — the same gauge story as
   [wire gauge for POTA](/advanced/wire-gauge/), amplified by the
   end-fed's current distribution. The whole antenna still weighs 18 g
   in 28 AWG.
2. **The counterpoise is load-bearing.** The stock 1.05 m is the classic
   0.05 λ. Shrink it to 0.3 m and the match collapses to SWR 4.3;
   stretch it to 3 m and it detunes the system the other way (SWR 1.5).
   "The coax shield is my counterpoise" works precisely because a short
   deliberate one like this is all the return path the feed needs.
3. **Loss buys bandwidth, again honestly.** The stepped-down 2.2 kΩ feed
   plus the wire loss flatten the SWR curve: the model holds the *entire*
   20 m band under 2:1. That's the EFHW's famously friendly SWR curve —
   and the budget shows what it costs.

The unun defaults (`lmag_uH` = 8, `qlmag` = 10) put the core in the
85–90 % efficiency range bench-measured for FT240-43-class 49:1 builds.
The model is deliberately minimal — a magnetizing branch with finite Q,
not a full transformer characterization — so treat the (mag) row as the
shape of the loss, and tune `qlmag` against a measurement if you have
one: Q = 5 doubles the core's share, Q = 20 halves it.

## The 40 m variant

`wire.efhw_sloper:band40` is the same POTA box — unun, comp cap, and
coax untouched — with twice the wire: ~19 m of 28 AWG PVC retuned to
put the rig-side SWR minimum at 7.1 MHz (SWR 1.36, and the whole band
under about 2:1). Two things change with the band, and both are honest
physics rather than knob-turning:

- **The slope comes down.** A 63° rise would put the apex at ~18 m; the
  variant's 30° lands it near 11 m — a tall mast or a friendly tree
  limb. At ~0.26 λ up the pattern is near-NVIS (takeoff ≈ 78°,
  essentially omnidirectional), which is exactly how 40 m POTA operates:
  regional skywave, not DX.
- **The wire loss doubles.** The longer high-current half wave burns
  ~10 % in I²R (vs ~6 % on 20 m), for 84 % structural efficiency. The 100 pF
  comp cap is a 20 m-flavored compromise, too — ~200 pF would buy
  SWR 1.19 here, if you'd rather rebuild the unun than accept 1.36.

## Try it

Open [`wire.efhw_sloper`](https://app.antennaknobs.dev/) in the
simulator with the sweep locked to 20 m. Flip `unun_ratio` and watch the
match move; drag `cp_len_m` and watch it matter more; flip `wire_type`
to bare wire and watch resonance jump up the band (retune with
`length_factor` — insulated wire is a few percent electrically longer).
Then drag the measurement frequency across the band and watch the power
budget re-divide itself between the coax, the core, and the wire — the
end-fed question, answered per watt.
