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
