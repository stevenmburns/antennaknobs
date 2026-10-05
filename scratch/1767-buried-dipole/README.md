# AK#1767: specialty.buried_dipole, gap wire vs one wire fed at its middle

`measure.py` builds the shipped spelling (`old`: arm, 5 cm gap, arm) and the
merged one (`new`: one wire, `ex` at its middle) and reads momwire bs2,
razor-2p and sinusoidal-Galerkin ladders; NEC-5 and NEC-4.2 ran as black
boxes on the laptop on the decks the wrappers write. 2026-10-04, main
6c43a1484, soil eps_r 13 / sigma 0.005, 7.1 MHz, depth 0.15 m.

    NEC5_EXE=/bin/true python scratch/1767-buried-dipole/measure.py <outdir>

| engine @ nominal | old (gap wire) | new (one wire) | new fed segment |
|---|---|---|---|
| bs2 @ 15 (app default) | 146.795 + 45.873j | 147.113 + 47.913j | 160 mm |
| bs2 @ 30 | 146.785 + 45.775j | 146.888 + 46.396j | 81 mm |
| bs2 @ 60 | 146.774 + 45.684j | 146.741 + 45.496j | 41 mm |
| bs2 @ 120 | 146.618 + 44.780j (gap 1 -> 3 segs) | 146.642 + 44.914j | 21 mm |
| razor-2p @ 40 | 146.469 + 44.384j | 146.532 + 44.758j | |
| razor-2p @ 160 | 146.500 + 44.245j | 146.512 + 44.311j | |
| NEC-5 @ 40 | 146.48 + 44.380j | 146.54 + 44.753j | |
| NEC-5 @ 160 | 146.51 + 44.241j | 146.52 + 44.306j | |
| NEC-4.2 @ 21 | 136.482 + 41.714j | 146.780 + 46.626j | |
| NEC-4.2 @ 42 | 144.850 + 44.236j | 146.503 + 44.991j | |
| NEC-4.2 @ 84 | 145.645 + 43.311j | 146.326 + 44.013j | |

Not built. The merge fixes NEC-4.2 (10 ohm off at its default rung, now 0.3)
and removes the gap's step on bs2 (-0.9 ohm X at nominal 60 -> 120), but at
the app's default engine and density it moves Z +0.32 + 2.04j ohm AWAY from
the fine-mesh value, because the fed segment grows from the 50 mm gap to the
design's own 160 mm in-medium segment. See the batch report for the options.

## Option (b): the gap wire's count pinned (`gap_pin.py`), 2026-10-04

Steve chose to keep the gap wire and pin its count. The merged ladder above
never settles (the delta gap drifts with the fed segment, momwire#1330; out
to nominal 480 each doubling still moves X by 0.28 ohm).

bs2 (Skylake, main aad8926b4). Each pinned count is flat. The auto count
steps where it changes (1 -> 3 at nominal ~106, 3 -> 5 at ~318):

| nominal | auto | pinned 1 | pinned 3 | pinned 5 |
|---|---|---|---|---|
| 15 | 146.7949 + 45.8732j | same | 146.5964 + 44.7344j | 146.5494 + 44.4783j |
| 21 | 146.7897 + 45.8227j | same | 146.6010 + 44.7432j | 146.5531 + 44.4819j |
| 60 | 146.7737 + 45.6842j | same | 146.6131 + 44.7703j | 146.5638 + 44.5005j |
| 120 | 146.6182 + 44.7804j (3) | 146.7637 + 45.6060j | 146.6182 + 44.7804j | 146.5691 + 44.5116j |
| 240 | 146.5733 + 44.5206j (5) | 146.7555 + 45.5432j | 146.6217 + 44.7856j | 146.5733 + 44.5206j |

NEC-4.2 and NEC-5 through the engines' own decks (laptop, black box):

| rung | gap | NEC-4.2 | NEC-5 |
|---|---|---|---|
| default (21) | 1 | 136.482 + 41.714j | 146.39 + 44.382j |
| default (21) | 3 | 137.469 + 40.903j | 146.35 + 44.158j |
| default (21) | 5 | 137.353 + 40.584j | 146.33 + 44.041j |
| refined (42) | 1 | 144.850 + 44.236j | 146.48 + 44.382j |
| refined (42) | 3 | 143.194 + 42.574j | 146.44 + 44.159j |
| refined (42) | 5 | 142.886 + 42.182j | 146.42 + 44.044j |

Pinning more segments does NOT close NEC-4.2's gap here, unlike the buried
vertical. There the 50 mm gap was LONGER than its 6.25 mm graded neighbours;
here it is SHORTER than the 118 mm arm segments (2.4:1 at the default rung),
and three segments make that step 7:1. NEC-4.2's error tracks the arm/gap
step: 10 ohm at 2.4:1 (rung 21), 1.6 ohm at 1.2:1 (rung 42); the merged,
uniform wire read 146.780 at rung 21. No pinned count fixes that without
changing the gap's width, which is the antenna.

Chosen: ONE segment. It keeps every shipped number (bs2's default, both
catalog rungs' NEC-5 and NEC-4.2 decks are byte-identical), and it removes
the auto count's steps. Three would move bs2's default by 0.20 + 1.14j ohm
and make NEC-4.2 worse on the refined rung.
