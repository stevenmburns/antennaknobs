# AK#1523 surface option: #1532's pair near ground

Registration: `PLAN.md`. Records: `rows_main.jsonl`, `rows_pre.jsonl` (`study_surface.py`).
antennaknobs main `b4aa104b0325174b201c2d51f4a40ca36da21f57`, pre-#1532 `e7317cb192f0278ae8866ab1027f9f4a26c12bdb`; momwire `227491dc24b7b4f0cf0d51c85e65b647ecfeb463`; NEC-5 sha256 `7ebf343d`.

## Checks and predictions

| id | verdict | instances | failing |
|---|---|---:|---|
| K0 | FAIL | 51 | m0-18 nec5, m1-28 nec5, m1-28 nec5_lonly, m2-20a nec5, q1-18-awg-pvc nec5, q1-18-awg-pvc nec5_lonly, q1-18-awg-pvc nec5_pre, q1-22-awg-pvc nec5 … (+14) |
| K1 | hit | 7 | — |
| A0 | hit | 25 | — |
| A1 | hit | 34 | — |
| B1 | hit | 3 | — |
| B1o | hit | 1 | — |
| B2a | hit | 3 | — |
| B2b | hit | 3 | — |
| B3 | hit | 3 | — |
| C1 | hit | 2 | — |
| C2 | MISS | 1 | 5b <= b/5 |
| C3 | hit | 3 | — |
| C4 | MISS | 1 | shift 20a < b |
| M | MISS | 5 | m1-28 bs2 <= 1 % |
| S1 | hit | 1 | — |
| S2 | hit | 3 | — |
| S3 | hit | 1 | — |

**Answer rule:** stop: K0 did not pass.

## Q0: every row

| cell | arm | status | segments | Z Ω | advisories | warnings | s |
|---|---|---|---:|---|---:|---:|---:|
| m0-18 | bs2 | ok | 143 | 60.581+60.921j | 1 | 0 | 8.109 |
| m0-18 | nec5 | ok | 144 | 60.176+59.422j | — | 0 | 0.321 |
| m0-18 | razor | ok | 144 | 60.477+60.250j | 1 | 0 | 0.247 |
| m1-28 | bs2 | ok | 143 | 67.817+84.967j | 1 | 0 | 19.89 |
| m1-28 | nec5 | ok | 144 | 67.331+83.392j | — | 0 | 0.321 |
| m1-28 | nec5_lonly | ok | 144 | 62.677+71.303j | — | 0 | 0.325 |
| m1-28 | razor | ok | 144 | 67.306+83.416j | 1 | 0 | 0.328 |
| m2-20a | bs2 | ok | 143 | 53.247+18.751j | 0 | 0 | 0.209 |
| m2-20a | nec5 | ok | 144 | 53.100+17.938j | — | 0 | 0.323 |
| m2-20a | razor | ok | 144 | 53.103+18.047j | 1 | 0 | 0.073 |
| q1-18-awg-pvc | bs2 | ok | 74 | 60.618+60.952j | 1 | 0 | 5.536 |
| q1-18-awg-pvc | bs2_lonly | ok | 74 | 57.774+53.310j | 1 | 0 | 5.491 |
| q1-18-awg-pvc | nec5 | ok | 75 | 59.930+58.539j | — | 0 | 0.281 |
| q1-18-awg-pvc | nec5_lonly | ok | 75 | 57.365+51.396j | — | 0 | 0.286 |
| q1-18-awg-pvc | nec5_pre | ok | 75 | 57.365+51.396j | — | 0 | 0.278 |
| q1-18-awg-pvc | razor | ok | 75 | 60.009+58.828j | 1 | 0 | 0.558 |
| q1-18-awg-pvc | razor_lonly | ok | 75 | 57.324+51.301j | 1 | 0 | 0.115 |
| q1-22-awg-pvc | bs2 | ok | 74 | 63.055+71.369j | 1 | 0 | 5.492 |
| q1-22-awg-pvc | bs2_lonly | ok | 74 | 59.319+61.427j | 1 | 0 | 5.485 |
| q1-22-awg-pvc | nec5 | ok | 75 | 62.209+68.614j | — | 0 | 0.277 |
| q1-22-awg-pvc | nec5_lonly | ok | 75 | 58.857+59.234j | — | 0 | 0.279 |
| q1-22-awg-pvc | nec5_pre | ok | 75 | 58.857+59.234j | — | 0 | 0.277 |
| q1-22-awg-pvc | razor | ok | 75 | 62.050+68.313j | 1 | 0 | 0.115 |
| q1-22-awg-pvc | razor_lonly | ok | 75 | 58.690+58.591j | 1 | 0 | 0.116 |
| q1-28-awg-pvc | bs2 | ok | 74 | 68.758+86.884j | 1 | 0 | 5.487 |
| q1-28-awg-pvc | bs2_lonly | ok | 74 | 63.292+74.091j | 1 | 0 | 5.517 |
| q1-28-awg-pvc | nec5 | ok | 75 | 67.056+82.438j | — | 0 | 0.278 |
| q1-28-awg-pvc | nec5_lonly | ok | 75 | 62.472+70.385j | — | 0 | 0.281 |
| q1-28-awg-pvc | nec5_pre | ok | 75 | 62.472+70.385j | — | 0 | 0.278 |
| q1-28-awg-pvc | razor | ok | 75 | 66.094+80.295j | 1 | 0 | 0.116 |
| q1-28-awg-pvc | razor_lonly | ok | 75 | 61.944+68.105j | 1 | 0 | 0.114 |
| q2-20a | bs2 | ok | 74 | 53.236+18.683j | 0 | 0 | 0.13 |
| q2-20a | nec5 | ok | 75 | 52.902+17.142j | — | 0 | 0.278 |
| q2-20a | nec5_lonly | ok | 75 | 52.654+11.263j | — | 0 | 0.278 |
| q2-20a | nec5_pre | ok | 75 | 52.654+11.263j | — | 0 | 0.277 |
| q2-20a | razor | ok | 75 | 52.887+17.066j | 1 | 0 | 0.046 |
| q2-2b | bs2 | ok | 74 | 56.090+46.546j | 1 | 0 | 2.059 |
| q2-2b | nec5 | ok | 75 | 55.728+44.817j | — | 0 | 0.277 |
| q2-2b | nec5_lonly | ok | 75 | 54.981+38.074j | — | 0 | 0.279 |
| q2-2b | nec5_pre | ok | 75 | 54.981+38.074j | — | 0 | 0.278 |
| q2-2b | razor | ok | 75 | 55.776+45.138j | 1 | 0 | 0.179 |
| q2-5b | bs2 | ok | 74 | 54.107+29.814j | 1 | 0 | 0.35 |
| q2-5b | nec5 | ok | 75 | 53.772+28.251j | — | 0 | 0.278 |
| q2-5b | nec5_lonly | ok | 75 | 53.479+22.152j | — | 0 | 0.28 |
| q2-5b | nec5_pre | ok | 75 | 53.479+22.152j | — | 0 | 0.278 |
| q2-5b | razor | ok | 75 | 53.784+28.420j | 1 | 0 | 0.068 |
| severns | bs2 | ok | 184 | 50.782+14.739j | 1 | 0 | 34.003 |
| severns | nec5 | ok | 183 | 49.993+13.431j | — | 0 | 0.538 |
| severns | nec5_lonly | ok | 183 | 48.339+17.267j | — | 0 | 0.541 |
| severns | nec5_pre | ok | 183 | 48.339+17.267j | — | 0 | 0.538 |
| severns | razor | ok | 183 | 49.457+13.510j | 1 | 0 | 3.384 |

### Refusals, verbatim

None.

### momwire advisories and warnings, verbatim (first of each)

- first seen on m0-18 bs2:

  ```text
  {"category": "SurfaceRadialHeight", "text": "a conductor lies within a few radii of the ground: 4 near-ground wire(s) at h = 1.05 mm, h/a = 2.1. At this stand-off the driving-point impedance is a STRONG function of h \u2014 a wire on a lossy dielectric is a slow-wave line, so the conductor is electrically longer than its free-space length and a sparse screen detunes as h falls. Measured on the reference deck, |dR/dh| is about 50 ohm per MILLIMETRE at N = 4 near 1.5 mm (it swings through a resonance and changes sign), against roughly 4 ohm/mm at N >= 16, where the class becomes quotable. This deck is in the sparse regime, so treat its impedance as indicative rather than predictive: the same wire in deeper grass is a measurably different antenna. The height IS the model here \u2014 there is no coating model, so h stands in for radius plus jacket (1.0 mm for a No. 18 insulated wire lying on soil) and for however the wire sits in the grass. Below h/a = 2 the fill is refused by name, because the mesh check already moves 4 % there. For the deck's OWN slope rather than the class figure, call `momwire.surface_height_slope()` \u2014 it costs a second solve, which is why it is not done here. Advisory: nothing is moved and nothing is refused. See stevenmburns/momwire#865 (antennaknobs scratch/buried-flow/unit5-surface-radials.md)."}
  ```

- first seen on m0-18 razor:

  ```text
  {"category": "RazorFarMeshClass", "text": "razor-2p is first order in the far mesh: its path (razor-blade) testing rule is NEC-5's, which converges more slowly than a Galerkin-tested basis, so a coarse answer is systematically off rather than noisy. Measured over 88 antennaknobs catalog decks at their shipped mesh density, the driving-point impedance is a median 3.3 % from converged, with a tail to 34 % (2.29 ohm median in absolute terms, though the relative figure is the readable one: in ohms the ranking follows |Z| rather than accuracy). The ground barely matters \u2014 free-space and Sommerfeld medians agree to 2 %. It is order 1 in the mesh, so DOUBLING the segment count on the razor path roughly HALVES the error; there is no mesh at which it is free. For a converged answer use BSplineSolver (degree 2), which is already converged at these same segment counts. Advisory: nothing is remeshed and nothing is refused \u2014 a coarse mesh is a legitimate thing to ask for, and every rung of a convergence ladder but the last is one. See stevenmburns/momwire#845 (antennaknobs scratch/845-mesh-policy, commit 6bafd991d)."}
  ```

- first seen on severns bs2:

  ```text
  {"category": "SurfaceRadialHeight", "text": "a conductor lies within a few radii of the ground: 16 near-ground wire(s) at h = 1.60 mm, h/a = 3.1. At this stand-off the driving-point impedance is a STRONG function of h \u2014 a wire on a lossy dielectric is a slow-wave line, so the conductor is electrically longer than its free-space length and a sparse screen detunes as h falls. Measured on the reference deck, |dR/dh| is about 50 ohm per MILLIMETRE at N = 4 near 1.5 mm (it swings through a resonance and changes sign), against roughly 4 ohm/mm at N >= 16, where the class becomes quotable. This deck is at or above N = 16, the quotable end of the class. The height IS the model here \u2014 there is no coating model, so h stands in for radius plus jacket (1.0 mm for a No. 18 insulated wire lying on soil) and for however the wire sits in the grass. Below h/a = 2 the fill is refused by name, because the mesh check already moves 4 % there. For the deck's OWN slope rather than the class figure, call `momwire.surface_height_slope()` \u2014 it costs a second solve, which is why it is not done here. Advisory: nothing is moved and nothing is refused. See stevenmburns/momwire#865 (antennaknobs scratch/buried-flow/unit5-surface-radials.md)."}
  ```


## Q1: the three PVC wires at h = b, nominal_nsegs 21

| wire | nec5 | nec5_lonly | nec5_pre | razor | bs2 | razor_lonly | bs2_lonly |
|---|---|---|---|---|---|---|---|
| 18-awg-pvc | 59.930+58.539j | 57.365+51.396j | 57.365+51.396j | 60.009+58.828j | 60.618+60.952j | 57.324+51.301j | 57.774+53.310j |
| 22-awg-pvc | 62.209+68.614j | 58.857+59.234j | 58.857+59.234j | 62.050+68.313j | 63.055+71.369j | 58.690+58.591j | 59.319+61.427j |
| 28-awg-pvc | 67.056+82.438j | 62.472+70.385j | 62.472+70.385j | 66.094+80.295j | 68.758+86.884j | 61.944+68.105j | 63.292+74.091j |

gap_t = \|Z_nec5,t − Z_razor\|/\|Z_razor\|; shift_e = \|Z_e − Z_e,Lonly\|/\|Z_e,Lonly\|.

| wire | shift nec5 % | shift razor % | shift bs2 % | B3 ratio | gap_pair % | gap_Lonly % | nec5 vs bs2 % | razor vs bs2 % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 18-awg-pvc | 9.85 | 10.39 | 10.37 | 0.950 | 0.356 | 9.387 | 2.919 | 2.570 |
| 22-awg-pvc | 11.93 | 12.40 | 12.44 | 0.968 | 0.369 | 10.428 | 3.026 | 3.378 |
| 28-awg-pvc | 13.70 | 13.99 | 14.28 | 1.001 | 2.258 | 10.146 | 4.297 | 6.414 |

## Q2: 18-awg-pvc stand-off ladder, nominal_nsegs 21

| h | h mm | h/a | h/a′ | nec5 | nec5_lonly | razor | bs2 | gap_pair % | gap_Lonly % | nec5 vs bs2 % | razor vs bs2 % | shift nec5 % |
|---|---:|---:|---:|---|---|---|---|---:|---:|---:|---:|---:|
| b | 1.050 | 2.05 | 1.23 | 59.930+58.539j | 57.365+51.396j | 60.009+58.828j | 60.618+60.952j | 0.356 | 9.387 | 2.919 | 2.570 | 9.85 |
| 2b | 2.100 | 4.10 | 2.46 | 55.728+44.817j | 54.981+38.074j | 55.776+45.138j | 56.090+46.546j | 0.452 | 9.907 | 2.424 | 1.980 | 10.14 |
| 5b | 5.250 | 10.25 | 6.14 | 53.772+28.251j | 53.479+22.152j | 53.784+28.420j | 54.107+29.814j | 0.278 | 10.315 | 2.587 | 2.316 | 10.55 |
| 20a | 10.240 | 20.00 | 11.97 | 52.902+17.142j | 52.654+11.263j | 52.887+17.066j | 53.236+18.683j | 0.140 | 10.450 | 2.794 | 2.932 | 10.93 |

## Mesh: nominal_nsegs 21 → 42

| cell | bs2 move % | razor move % | nec5 move % | gap_pair at 21 % | gap_pair at 42 % |
|---|---:|---:|---:|---:|---:|
| m0-18 | 0.056 | 1.782 | 1.094 | 0.356 | 1.032 |
| m1-28 | 1.928 | 3.219 | 0.934 | 2.258 | 0.032 |
| m2-20a | 0.123 | 1.809 | 1.475 | 0.140 | 0.195 |

## Severns surface deck (N = 16, h = 1.6 mm)

Measured 56.100+6.200j; momwire's docstring a′ + L 49.380+14.930j.

| arm | Z | R − 56.1 | X − 6.2 | \|Z − docstring\| |
|---|---|---:|---:|---:|
| nec5 | 49.993+13.431j | -6.11 | +7.23 | 1.62 |
| nec5_lonly | 48.339+17.267j | -7.76 | +11.07 | 2.56 |
| nec5_pre | 48.339+17.267j | -7.76 | +11.07 | 2.56 |
| razor | 49.457+13.510j | -6.64 | +7.31 | 1.42 |
| bs2 | 50.782+14.739j | -5.32 | +8.54 | 1.41 |

## K1: the monkeypatched inductance-only spelling against pre-#1532

| cell | nec5_lonly (main) | nec5_pre | \|Δ\| Ω |
|---|---|---|---:|
| q1-18-awg-pvc | 57.365+51.396j | 57.365+51.396j | 0.0000 |
| q1-22-awg-pvc | 58.857+59.234j | 58.857+59.234j | 0.0000 |
| q1-28-awg-pvc | 62.472+70.385j | 62.472+70.385j | 0.0000 |
| q2-20a | 52.654+11.263j | 52.654+11.263j | 0.0000 |
| q2-2b | 54.981+38.074j | 54.981+38.074j | 0.0000 |
| q2-5b | 53.479+22.152j | 53.479+22.152j | 0.0000 |
| severns | 48.339+17.267j | 48.339+17.267j | 0.0000 |
