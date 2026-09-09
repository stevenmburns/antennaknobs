---
title: "Buried radials: two engines on the same dirt"
description: The elevated-vertical-over-buried-radials class through momwire and a licensed NEC-5 — same card files, convergence ladders on both sides, a feed-convention lesson that scales as Z², and one measured disagreement with a three-instrument attribution.
---

Buried radials are the reason a lot of people keep NEC-5 around: it
models wires inside real soil, and the counterpoise under a vertical is
the classic case. momwire serves the same class — a Sommerfeld
half-space with the wire's fields solved inside the lower medium — so
for the first time we can put **the same antenna, the same dirt, the
same card file** through both engines and compare printed impedances.

This page is that comparison, done the careful way: convergence ladders
on both sides (never single meshes), matched drive points, and every
number below taken from printed engine output against momwire's served
answers. The class under test is the **elevated-detached** family: a
vertical whose base sits *above* the ground (0.25–1 m), over one or
four detached 5 m radials buried 15 cm deep, in average soil
(ε_r 13, σ 0.005 S/m) at 7 MHz. Neither engine has a wire touching the
interface here, so both are solving the same well-posed problem — real
parasitic coupling through the soil, the Yagi mechanism pointed
downward. (Why not the base-*on*-the-ground deck? That one is a
different story, and momwire refuses it on purpose — see
[the counterpoise question](https://momwire.antennaknobs.dev/act-5/counterpoise/)
on the momwire primer.)

## The drop-in table

momwire's EZNEC-dialect seam runs NEC-5 deck text directly — same
cards, zero hand-translation, feed addressing included:

```bash
python -m momwire.eznec vertical-radials.nec printout.txt
```

Here is the resonant family (21 m center-fed vertical dipole, lower tip
0.25 m up, radials as labeled) through both readers of the same file.
The engine columns are its own refinement ladder (×1 = 22 segments on
the vertical, then ×3, ×8) plus the Richardson-extrapolated limit;
"seam ×3" is momwire solving the identical ×3 card:

| deck | seam ×1 | seam ×3 | engine ×1 | engine ×3 | engine ×8 | engine → limit | \|seam ×3 − limit\| |
|---|---|---|---|---|---|---|---|
| no radials | 100.54+19.70j | 100.62+20.01j | 98.74+12.28j | 100.06+17.77j | 100.42+19.21j | 100.64+20.08j | **0.07 Ω** |
| 1 radial | 100.46+19.94j | 100.55+20.25j | 98.89+13.08j | 100.21+18.62j | 100.56+20.07j | 100.76+20.95j | **0.73 Ω** |
| 4 radials | 100.09+20.43j | 100.18+20.74j | 98.84+14.56j | 100.15+20.14j | 100.50+21.60j | 100.70+22.49j | **1.82 Ω** |

:::note[The momwire columns are converged in quadrature, not just in mesh]
An earlier version of this table was computed at `n_qp_pair = 4`, momwire's
cross-edge quadrature default when the study ran (August 2026). That mattered
more than routine bookkeeping: momwire#760 had, at the time, read the
cross-edge error at a lossy-soil interface as falling only as `1/n_qp` — on
momwire's side only, and growing with the number of buried members meeting at a
junction. Same side, same direction, and the same ordering as the residual in
the last column, which made that residual unfalsifiable from this page. (That
first-order reading was later corrected — the error is superalgebraic on every
shipped deck, and the `C/q` was the bottom of one ladder read as a rate — but
the correction does not change what had to be done here: sweep it.)

It has now been swept, q = 4 through 128, and the columns above are the
converged answer (identical at 32, 64 and 128). **The residual is not
quadrature.** Quadrature is worth 0.10 Ω on the four-radial deck — and 0.10 Ω
on the no-radial deck, which has no buried wire at all. It is a common-mode
shift, so it cannot produce a residual that grows by 1.75 Ω across that same
span, and it does not: the four-radial-minus-no-radial spread was 1.75 Ω at
`n_qp_pair = 4` and is 1.75 Ω converged.

The delta instrument in
[the disagreement section](#the-one-real-disagreement-and-whos-right) is
unaffected to four decimals, by the same cancellation.

Reproducing these rows: on a deck like this one — wire below the interface —
momwire now chooses `n_qp_pair = 32` for itself rather than the free-space
default of 8, so the rows reproduce without setting the knob at all. The web
UI leaves it on **auto** for the same reason, and sends nothing. Pin a number
only to reproduce a specific older run; `n_qp_pair = 8` was the shipped value
before momwire 0.47.0 and lands within 0.02 Ω of the converged values above.
Measured in
[antennaknobs#1068](https://github.com/stevenmburns/antennaknobs/issues/1068),
default per deck since
[momwire#863](https://github.com/stevenmburns/momwire/issues/863).
:::

Two things worth absorbing before any conclusion:

1. **The engine's coarse print is 7–8 Ω from its own converged value**
   on this deck (98.74+12.28j at ×1 against 100.64+20.08j at the
   limit). A single-mesh cross-engine comparison on this class measures
   discretization error, not physics. Ladders or nothing.
2. Once both sides converge, the no-radial decks agree to a
   **fraction of an ohm**, and the residual **grows with radial
   count** — 0.07 → 0.7 → 1.8 Ω. That ordering is not noise; it is the
   one genuine disagreement this study found, and it gets its own
   section below.

## Converged-vs-converged, the full panel

Running both engines' ladders on the whole family (heights 0.25, 0.5,
1.0 m; no-radial reference, one radial, four radials) and extrapolating
each side's own ladder:

- **Resonant family (~95–100 Ω)**: no-radial decks agree to
  0.19–0.22 Ω; one radial 0.29–0.44 Ω; four radials 1.13–1.53 Ω.
- **Insulated-base family (10 m vertical fed 4.67 m from the top,
  \|Z\| ≈ 960)**: 0.26–1.17 Ω converged — **0.03–0.12 %** on a
  thousand-ohm reactive deck.

These panel columns come from momwire's *native* builder rather than the
seam above, and they are already converged in quadrature: `n_qp_pair` = 4 and
128 agree to 1.2e-4 Ω on all nine combinations, with q = 2 as a live control
that does move. The sweep described above does not shift them.

For a class of antenna that people actually build — a vertical raised a
little above its buried counterpoise — the two independently-derived,
independently-coded formulations land within an ohm or so of each
other, and within a fraction of an ohm when no buried wire is present.

## The feed lesson (it scales as Z²)

Getting that agreement required matching **drive points**, not just
geometry, and the cost of getting this wrong is worth naming because it
bit us during this study.

A feed convention difference behaves like a small parasitic capacitance
at the drive point: ΔZ ≈ −jωC·Z². On a resonant deck (\|Z\| ≈ 100) a
half-picofarad of feed-region difference is invisible — a quarter of an
ohm. On the insulated-base family (\|Z\| ≈ 960) the *same* convention
difference is tens of ohms: momwire's own three feed spellings spread
~26 Ω among themselves there, and mis-locating the drive by half a
segment costs ~14 Ω. (We measured exactly that: an addressing
convention put our comparison feed half a segment from the engine's
actual drive node for a while, and every high-Z comparison inherited
the offset until it was found and fixed.)

Practical rules that fall out:

- **Compare engines raw only on resonant decks.** On reactive decks,
  compare at matched drive points and expect the feed-region
  convention to show at the Z² scale.
- On high-impedance decks, momwire's **knot feed** (split the wire at
  the driven node, drive across the join) is the spelling that matches
  engine feed conventions; the smooth point feed differs by the
  parasitic-C class above.

## The buried-radial coupling, three ways

> **Correction (2026-09-09).** An earlier version of this section reported
> the engine's buried-radial coupling at 2.8–5.2× momwire's and attributed
> the gap to the engine's below-ground fields. The engine column had been
> captured with its ground card's two fields transposed — the setting its
> manual documents as not usable when wires go below the surface, the same
> capture defect found later on the buried-dipole decks. Re-run under the
> documented card, the two engines agree on the coupling to about 0.01 Ω on
> every deck and every mesh rung, and the attribution is withdrawn. The
> printed near-field observation below is unaffected by the card and is kept
> as a measurement; the inference that was drawn from it is not.

Subtract each engine's no-radial reference from its radial decks at
matched meshes and the feed convention cancels entirely. What remains
is each engine's opinion of **the buried-radial coupling itself** — and,
under the engine's documented below-ground card, they agree:

| deck | height | engine ΔZ | momwire ΔZ |
|---|---|---|---|
| 1 radial | 0.25 m | −0.080+0.238j | −0.07+0.24j |
| 1 radial | 1.0 m | −0.038+0.094j | −0.04+0.09j |
| 4 radials | 0.25 m | −0.448+0.727j | −0.45+0.73j |
| 4 radials | 1.0 m | −0.208+0.303j | −0.21+0.30j |

The engine values are the ×8 rung (176 segments on the vertical) and
move by under 0.01 Ω from ×1 to ×8; the no-radial reference does not move
at all between the two ground-card settings, which is the control that
says the card touches only the buried conductors. A third reading landed
on the same numbers in September 2026: momwire's sinusoidal-Galerkin
solver, which shares no fill code with its B-spline solver below the
interface, gives −0.0746+0.2401j and −0.4499+0.7290j for the two 0.25 m
decks — the B-spline values to four decimals.

The effect is small — single ohms at most on these decks, dominated by
reactance, shrinking with height — and all three readings say so.

One printed-output observation survives from the earlier version, as a
fact about the engine's near-field tables on this deck class and nothing
more. Against **empymod**, the open-source electromagnetic reference for
layered media, momwire's below-ground fields match to **0.5 %**, with
depth-decay profiles identical to three decimals (1 / 0.679 / 0.422 /
0.207 down the 0.15–2 m ladder at 1 m radius — both instruments). The
engine's *printed* near-field tables for the same points decay more
slowly with depth (1 / 0.602 / 0.326 / 0.286) and at 2.5 m radius are
non-monotonic (1 / 0.601 / 0.198 / 0.398). Those tables print the same
under either ground-card setting. They are not the coupling: the
impedances above are what the engine solves, and on those the two agree.

## What to take away

- The elevated-detached class is **served and cross-validated**: same
  card files through both engines, converged agreement at the
  0.2–2 Ω level, sub-ohm where no buried wire is present.
- Radial effects on an *elevated* vertical are genuinely small —
  single ohms at 15 cm depth, shrinking with height. If your feed is
  clear of the ground, your radials are a second-order refinement, and
  either engine will tell you so.
- Quote ladders. On buried-soil decks the coarse-mesh prints of
  *either* engine can sit many ohms from that engine's own converged
  value.
- The buried-coupling delta agrees between the engines to about
  0.01 Ω under the documented ground card (correction above).
- **Since this page was written** (September 2026) the below-ground
  reference has changed from another engine to a measurement: momwire
  gates Brown, Lewis and Epstein's 1937 buried-radial screens, and its
  second reading underground is the same solver at a different basis
  degree. The [validation page](/reference/validation/) carries the
  current state.
- **Where the two engines stand below ground** (September 2026). On the
  1937 geometry NEC-5's radial-count law has the measured shape, steep at
  low radial count and flat past about thirty, and on a bonded-base
  vertical over buried radials the two engines agree to a few percent in
  resistance. The NEC-5 column in the drop-in table above was captured with one
  setting of the engine's ground card; with its documented below-ground
  setting the buried-radial decks move by up to 1.7 % in impedance — the
  same size as the coupling itself, which is why the coupling section
  carries a correction and the drop-in table's converged agreement
  (0.2–2 Ω) does not change.

The companion piece on the momwire primer —
[the counterpoise question](https://momwire.antennaknobs.dev/act-5/counterpoise/) —
covers the deck this page deliberately avoided: the vertical whose base
*touches* the ground over detached buried radials, why that deck
underspecifies its own physics, and why momwire refuses it rather than
answering it a few ohms wrong.
