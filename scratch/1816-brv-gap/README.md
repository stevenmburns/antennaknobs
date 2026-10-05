# AK#1816: the buried-radial vertical's 5 cm gap wire, 1 vs 3 segments

`measure.py` pins the gap wire's count (`None` = the design's own) and reads
momwire bs2 / razor-2p, and writes the NEC-5 and NEC-4.2 decks the wrappers
write for the same builder. Run 2026-10-04 at main 6c43a1484 (where `None`
was the auto count, one segment), Skylake for momwire, the licensed NEC-5
(`nec5cl`) and NEC-4.2 (`nec42cl-omp`, release-1ce4104) as black boxes on the
laptop. Soil eps_r 13 / sigma 0.005, 7.1 MHz, Sommerfeld.

    NEC5_EXE=/bin/true python scratch/1816-brv-gap/measure.py <outdir>

The neighbours of the gap are the graded node panels' 6.25 mm segments, so
one 50 mm gap segment is an 8:1 step; three 16.7 mm segments are 2.7:1. The
tent bases coerce the count to their even parity (1 -> 2, 3 -> 4).

## NEC-4.2 (the NEC-2-lineage basis) moves; nothing else does

| gap segs (NEC-4.2) | NEC-4.2 @ nominal 21 | NEC-4.2 @ 42 (refined) |
|---|---|---|
| 1 (shipped before) | 80.224 + 48.862j | 79.414 + 48.327j |
| 3 | 78.141 + 45.372j | 77.363 + 44.864j |
| 5 | 78.676 + 44.829j | 77.898 + 44.321j |
| 7 | 77.524 + 46.101j | 76.745 + 45.593j |

| gap segs (requested) | bs2 @ 15 | bs2 @ 30 | razor-2p @ 40 | NEC-5 @ 40 | NEC-5 @ 80 |
|---|---|---|---|---|---|
| 1 | 78.1232 + 46.2962j | 78.1380 + 46.3649j | 77.9361 + 45.2747j | 77.933 + 45.176j | 78.002 + 45.557j |
| 3 | 78.1352 + 46.2923j | 78.1500 + 46.3610j | 77.9420 + 45.2879j | 77.939 + 45.206j | 78.009 + 45.587j |
| 5 | 78.1397 + 46.2903j | 78.1545 + 46.3590j | 77.9447 + 45.2921j | 77.942 + 45.216j | 78.012 + 45.597j |
| 7 | 78.1422 + 46.2892j | 78.1570 + 46.3579j | 77.9463 + 45.2941j | 77.944 + 45.221j | 78.014 + 45.602j |

Against NEC-5 through the wrappers at the catalog rungs (the
`test_nec4_writer_binary_1803` pairs), NEC-4.2 goes from 5.6 % (default) and
3.8 % (refined) at one segment to 1.0 % and 0.76 % at three. Past three,
NEC-4.2 wanders about +-0.6 ohm with no trend: three is where the step stops
dominating, not the start of a convergence the design should chase.

The momwire bases and NEC-5 move by 0.006-0.03 ohm from one to three. bs2's
default moves +0.012 ohm in R, inside the knob-corner gate's 0.10 ohm; its
distance from the converged 78.154 + 46.445j (the design docstring) is 0.152
ohm before and 0.154 after, a wash.

## The knob corners (`corners.py`, bs2, nominal 21 = the pinned rung)

The gap count is a FEED-MODEL offset, not a mesh error: g3 - g1 is the same
at nominal x1, x2 and x4 to 1e-4 ohm on every corner, so refinement cannot
adjudicate it. The corner pins in `tests/test_buried_knob_corners_1131.py`
were re-banked to the g3 column.

| corner | g1 (old pin) | g3 (new pin) | g3 - g1 |
|---|---|---|---|
| default | 78.1321 + 46.3377j | 78.1441 + 46.3338j | +0.012 - 0.004j |
| n_radials_min | 170.6069 + 48.7379j | 170.6342 + 48.6970j | +0.027 - 0.041j |
| depth_max | 84.7118 + 70.6136j | 84.7315 + 70.6125j | +0.020 - 0.001j |
| length_max | 120.6456 + 231.8948j | 120.7367 + 231.9609j | +0.091 + 0.066j |
| radial_max | 78.0190 + 43.5740j | 78.0303 + 43.5697j | +0.011 - 0.004j |
| soil_B_dense | 59.4301 + 42.7550j | 59.4384 + 42.7551j | +0.008 + 0.000j |
| mild_sparse | 140.6354 - 342.4703j | 140.4796 - 342.3105j | -0.156 + 0.160j |
| all_knobs_max_soil_B | 108.9379 + 253.9648j | 109.0278 + 254.0530j | +0.090 + 0.088j |
