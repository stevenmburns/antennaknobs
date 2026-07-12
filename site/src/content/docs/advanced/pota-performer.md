---
title: "Three ledgers of efficiency: modeling the POTA PERformer"
description: An advanced worked example — duplicating the published claims for KJ6ER's elevated vertical, and the difference between "90% efficient" and "30% radiated". Both are true.
---

Greg Mihran KJ6ER's **PERformer** is one of the most popular published
portable antennas: an elevated quarter-wave vertical for 40M–6M — a 17'
telescoping stainless whip with the feedpoint 52" up on a tripod or
spike, and two elevated tuned radials sloping down to stakes. The
[free plans](https://www.vhfclub.org/pdf/PERformer%20Antenna%20by%20KJ6ER%20%282025-02%29.pdf)
include 4NEC2 model results and a headline claim: **over 90% efficient**,
versus "only 37%" for a typical ground-mounted quarter-wave with four
ground-coupled radials.

[`verticals.pota_performer`](/reference/catalog/) models it faithfully —
the plans' 15M reference geometry, per-band variants straight from the
whip/radial tables, the 90° directional and 180° omni radial spans, and
VA3KOT's single-radial simplification. This page is about what happens
when you check the numbers: **almost every claim duplicates**, and the
one that needs an asterisk teaches the most useful lesson in portable
antenna modeling.

## The claims duplicate

Three independent engines (and two independent modelers) on the 15M
configuration, two radials, average ground:

| Model | Peak gain | Takeoff | F/B (90° span) | El. beamwidth |
|---|---|---|---|---|
| KJ6ER, 4NEC2 (published) | +0.31 dBi | 24° | 3.37 dB | 46° |
| VA3KOT, EZNEC (independent) | +1.19 dBi | 25° | 3.34 dB | 47° |
| antennaknobs, momwire | +1.06 dBi | 24° | 2.91 dB | 44° |
| antennaknobs, PyNEC | +1.02 dBi | 23° | ~3 dB | 44° |

The beam *shape* is unanimous: takeoff 23–25°, a mild ~3 dB
front-to-back toward the radial span, mid-40s elevation beamwidth. The
directional-vs-omni delta duplicates too (KJ6ER +0.98 dB, we measure
+0.76 dB), and so do VA3KOT's single-radial trends (more F/B, wider
elevation, narrower azimuth). Absolute peak gain spreads about 0.9 dB
across engines, with KJ6ER's own figure the lowest of the four —
ordinary cross-model variation in ground constants and whip
idealization.

The SWR story holds up as well: at the plans' exact 15M lengths the
directional feedpoint solves to 45 + 1j Ω — SWR 1.10, matching the
"better than 1.1:1" field measurements (and the omni span solves lower,
just as the plans say elevating radials should).

## The efficiency claim: true, in its ledger

"Over 90% efficient" is a **structural** efficiency: input power that
isn't burned in conductors and components. We *confirm* it. Solving the
same geometry with lossless wire and taking the ratio: the stainless
whip plus radials cost only ~2–3%, structural efficiency ≈ 98% (KJ6ER's
90.8% additionally carries his −0.12 dB choke and the whip's thin tip
sections). And the physics behind his 90%-vs-37% comparison is real:
elevated tuned radials remove the ground-coupled loss *resistance* that
sits in series with a ground-mounted vertical's feed and eats half its
power in-circuit.

But there is a second ledger, and it's already visible in the table
above. **Gain and efficiency are the same measurement.** Gain is power
density per input watt; average linear gain over the sphere is exactly
P<sub>radiated</sub>/P<sub>input</sub> (`radiated_fraction` in the
library computes it from any pattern). Equivalently: this beam shape has
a directivity of ~6.5 dBi — that's what the peak would read if every
input watt were radiated. The peaks actually read about +1 dBi:

| Model | Peak gain | Implied radiated fraction |
|---|---|---|
| KJ6ER, 4NEC2 | +0.31 dBi | ~24% |
| VA3KOT, EZNEC | +1.19 dBi | ~30% |
| momwire (integrated directly) | +1.06 dBi | 29% |
| PyNEC (integrated directly) | +1.02 dBi | 34% |

So for 100 W in: **~2 W warms the stainless, ~68 W warms the ground
within a few wavelengths, ~30 W leaves as sky wave.** The missing
4.5–6 dB between "+5.5 dBi if lossless" and "+1 dBi as modeled" *is*
the Fresnel-zone ground absorption, and it appears in nobody's
"efficiency" figure — including the 90.8% — because structural
efficiency by definition stops at the antenna's terminals-and-metal.
KJ6ER's own published +0.31 dBi peak is a ~25% radiated fraction,
stated in dB.

## The tax everyone pays

Ground absorption at these heights is nearly identical for every
portable vertical. For calibration, the same integration on a 7 m-high
inverted vee gives 72% radiated on 20m, 72% on 15m, 69% on 10m — the
classic reason horizontal wire beats a vertical over real ground when
you have the supports, and the vertical's counter-argument is the low
takeoff angle (23° here vs the vee's 51° on 20m), not efficiency. You
cannot pack better dirt. That's precisely why the convention in
antenna write-ups is to quote structural efficiency: it's the part the
*builder* controls, and on that score the PERformer is genuinely
excellent — the elevated-radial design earns its numbers, and the
*relative* claims (beats ground-mounted, 3 dB of steerable F/B from a
90° radial span, resonant with no tuner) all survive independent
modeling.

The lesson is about reading claims, not doubting this antenna: when a
spec sheet says "90% efficient" and the same page's pattern plot peaks
near 0 dBi, both numbers are correct — they are different ledgers. The
gain plot is the one the ionosphere sees.

## The rest of the trio: Challenger and Dominator

KJ6ER publishes two more antennas in the same family, and both are now
in the tree: [`verticals.challenger`](/reference/catalog/) (off-center-fed
halfwave vertical: 25' whip is ~77% of the halfwave, a short ~10% λ
counterpoise completes it through a 4:1 unun) and
[`verticals.dominator`](/reference/catalog/) (a true vertical EFHW: the
whip is the whole halfwave, fed through a 49:1 with a long ~33% λ
counterpoise). Same duplication exercise, same result — the claims hold:

| Claim (4NEC2, 15M) | Published | antennaknobs |
|---|---|---|
| Challenger peak / takeoff / el BW | −0.32 dBi / 20° / 33° | +0.14 dBi / 21° / 34° |
| Dominator peak / takeoff / el BW | +0.60 dBi / 18° / 27° | +0.34 dBi / 17° / 26° |
| Takeoff ordering, trio | 18° < 21° < 24° | 17° < 21° < 23° |

The transformers are where these two get interesting, because KJ6ER
*measures* their insertion losses and itemizes them honestly — and our
`Transformer` branch puts the same numbers in the power budget: the
stock 49:1 burns **−0.96 dB (~20% of input power)**, the Challenger's
4:1 only −0.34 dB, with the "plus" upgrades at −0.40/−0.24 dB
(`plus` variants; the magnetizing branch is calibrated to the measured
loss at 15M, not derived from core datasheets). His own comparison
table shows the paradox: the Dominator has the trio's *highest*
"structural efficiency" (99.5% — it's just one aluminum tube) and the
trio's *lossiest* component. Both facts are itemized in our budget
instead of living in separate ledgers.

And the third ledger says: Challenger radiates 25%, Dominator 25%
(transformer included), PERformer 29%. Nobody escapes the dirt. What
actually separates these three antennas — exactly as KJ6ER's "primary
reach" table frames it — is the takeoff angle, and that claim
reproduces perfectly.

## Try it

Open [`verticals.pota_performer`](https://app.antennaknobs.dev/) in the
simulator. Flip `radial_span_deg` between 90 and 180 and watch the
front-to-back appear and vanish; drop `n_radials` to 1 for VA3KOT's
fast-deploy config; walk the band variants (`band20` … `band6`) and
watch the droop angle steepen as the radials shorten against the fixed
stake height — exactly the table in the plans.

*Sources: [KJ6ER's PERformer plans (rev 2025-02)](https://www.vhfclub.org/pdf/PERformer%20Antenna%20by%20KJ6ER%20%282025-02%29.pdf);
[VA3KOT, "Testing and modifying the POTA PERformer antenna" (2025-05)](https://hamradiooutsidethebox.ca/2025/05/28/testing-and-modifying-the-pota-performer-antenna/).*
