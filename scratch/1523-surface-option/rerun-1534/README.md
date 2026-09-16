# AK#1523 surface option: #1532's pair near ground

Registration: `PLAN.md`. Records: `rows_main.jsonl`, `rows_pre.jsonl` (`study_surface.py`).
antennaknobs main `34f533bb468467e0638f8b53776205f376466bd1`, pre-#1532 `None`; momwire `227491dc24b7b4f0cf0d51c85e65b647ecfeb463`; NEC-5 sha256 `7ebf343d`.

## Checks and predictions

| id | verdict | instances | failing |
|---|---|---:|---|
| K0 | FAIL | 44 | m0-18 bs2, m0-18 nec5, m0-18 razor, m1-28 bs2, m1-28 nec5, m1-28 nec5_lonly, m1-28 razor, m2-20a bs2 … (+26) |
| K0' | hit | 44 | — |
| K1 | n/a (Amendment 2) | 0 | — |
| A0 | hit | 18 | — |
| A1 | hit | 34 | — |
| B1 | hit | 3 | — |
| B1o | hit | 1 | — |
| B2a | hit | 3 | — |
| B2b | hit | 3 | — |
| B3 | hit | 3 | — |
| C1 | hit | 2 | — |
| C2 | MISS | 1 | 5b <= b/5 |
| C3 | hit | 3 | — |
| C4 | hit | 1 | — |
| M | MISS | 5 | m1-28 bs2 <= 1 % |
| S1 | hit | 1 | — |
| S2 | hit | 3 | — |
| S3 | hit | 1 | — |

**Answer rule:** near ground the pair narrows but does not close razor-2p vs NEC-5; the near-ground signature is gap_pair.

## Q0: every row

| cell | arm | status | segments | Z Ω | advisories | warnings | s |
|---|---|---|---:|---|---:|---:|---:|
| m0-18 | bs2 | ok | 143 | 58.502+35.110j | 1 | 0 | 8.081 |
| m0-18 | nec5 | ok | 144 | 58.115+33.704j | — | 0 | 0.322 |
| m0-18 | razor | ok | 144 | 58.416+34.526j | 1 | 0 | 0.279 |
| m1-28 | bs2 | ok | 143 | 64.700+43.768j | 1 | 0 | 20.363 |
| m1-28 | nec5 | ok | 144 | 64.236+42.312j | — | 0 | 0.32 |
| m1-28 | nec5_lonly | ok | 144 | 60.103+30.608j | — | 0 | 0.322 |
| m1-28 | razor | ok | 144 | 64.211+42.334j | 1 | 0 | 0.329 |
| m2-20a | bs2 | ok | 143 | 51.121-6.851j | 0 | 0 | 0.208 |
| m2-20a | nec5 | ok | 144 | 50.996-7.575j | — | 0 | 0.321 |
| m2-20a | razor | ok | 144 | 50.999-7.467j | 1 | 0 | 0.077 |
| q1-18-awg-pvc | bs2 | ok | 74 | 58.543+35.154j | 1 | 0 | 5.529 |
| q1-18-awg-pvc | bs2_lonly | ok | 74 | 56.019+27.714j | 1 | 0 | 5.514 |
| q1-18-awg-pvc | nec5 | ok | 75 | 57.907+32.903j | — | 0 | 0.282 |
| q1-18-awg-pvc | nec5_lonly | ok | 75 | 55.636+25.924j | — | 0 | 0.29 |
| q1-18-awg-pvc | razor | ok | 75 | 57.985+33.184j | 1 | 0 | 0.596 |
| q1-18-awg-pvc | razor_lonly | ok | 75 | 55.594+25.823j | 1 | 0 | 0.115 |
| q1-22-awg-pvc | bs2 | ok | 74 | 60.496+38.465j | 1 | 0 | 5.528 |
| q1-22-awg-pvc | bs2_lonly | ok | 74 | 57.176+28.824j | 1 | 0 | 5.544 |
| q1-22-awg-pvc | nec5 | ok | 75 | 59.709+35.906j | — | 0 | 0.277 |
| q1-22-awg-pvc | nec5_lonly | ok | 75 | 56.743+26.782j | — | 0 | 0.28 |
| q1-22-awg-pvc | razor | ok | 75 | 59.549+35.600j | 1 | 0 | 0.121 |
| q1-22-awg-pvc | razor_lonly | ok | 75 | 56.574+26.132j | 1 | 0 | 0.12 |
| q1-28-awg-pvc | bs2 | ok | 74 | 65.647+45.682j | 1 | 0 | 5.567 |
| q1-28-awg-pvc | bs2_lonly | ok | 74 | 60.716+33.319j | 1 | 0 | 5.541 |
| q1-28-awg-pvc | nec5 | ok | 75 | 64.012+41.474j | — | 0 | 0.278 |
| q1-28-awg-pvc | nec5_lonly | ok | 75 | 59.927+29.796j | — | 0 | 0.279 |
| q1-28-awg-pvc | razor | ok | 75 | 63.047+39.341j | 1 | 0 | 0.112 |
| q1-28-awg-pvc | razor_lonly | ok | 75 | 59.392+27.515j | 1 | 0 | 0.117 |
| q2-20a | bs2 | ok | 74 | 51.114-6.907j | 0 | 0 | 0.153 |
| q2-20a | nec5 | ok | 75 | 50.834-8.302j | — | 0 | 0.28 |
| q2-20a | nec5_lonly | ok | 75 | 50.867-14.103j | — | 0 | 0.277 |
| q2-20a | razor | ok | 75 | 50.818-8.384j | 1 | 0 | 0.047 |
| q2-2b | bs2 | ok | 74 | 54.005+20.861j | 1 | 0 | 2.113 |
| q2-2b | nec5 | ok | 75 | 53.694+19.284j | — | 0 | 0.278 |
| q2-2b | nec5_lonly | ok | 75 | 53.226+12.653j | — | 0 | 0.286 |
| q2-2b | razor | ok | 75 | 53.742+19.597j | 1 | 0 | 0.184 |
| q2-5b | bs2 | ok | 74 | 51.995+4.193j | 1 | 0 | 0.363 |
| q2-5b | nec5 | ok | 75 | 51.713+2.779j | — | 0 | 0.278 |
| q2-5b | nec5_lonly | ok | 75 | 51.700-3.235j | — | 0 | 0.278 |
| q2-5b | razor | ok | 75 | 51.724+2.941j | 1 | 0 | 0.059 |
| severns | bs2 | ok | 184 | 50.782+14.739j | 1 | 0 | 34.706 |
| severns | nec5 | ok | 183 | 49.993+13.431j | — | 0 | 0.538 |
| severns | nec5_lonly | ok | 183 | 48.339+17.267j | — | 0 | 0.536 |
| severns | razor | ok | 183 | 49.457+13.510j | 1 | 0 | 3.4 |

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
| 18-awg-pvc | 57.907+32.903j | 55.636+25.924j | — | 57.985+33.184j | 58.543+35.154j | 55.594+25.823j | 56.019+27.714j |
| 22-awg-pvc | 59.709+35.906j | 56.743+26.782j | — | 59.549+35.600j | 60.496+38.465j | 56.574+26.132j | 57.176+28.824j |
| 28-awg-pvc | 64.012+41.474j | 59.927+29.796j | — | 63.047+39.341j | 65.647+45.682j | 59.392+27.515j | 60.716+33.319j |

gap_t = \|Z_nec5,t − Z_razor\|/\|Z_razor\|; shift_e = \|Z_e − Z_e,Lonly\|/\|Z_e,Lonly\|.

| wire | shift nec5 % | shift razor % | shift bs2 % | B3 ratio | gap_pair % | gap_Lonly % | nec5 vs bs2 % | razor vs bs2 % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 18-awg-pvc | 11.96 | 12.63 | 12.57 | 0.948 | 0.437 | 11.422 | 3.425 | 2.998 |
| 22-awg-pvc | 15.29 | 15.92 | 15.92 | 0.967 | 0.497 | 13.338 | 3.735 | 4.209 |
| 28-awg-pvc | 18.49 | 18.91 | 19.22 | 0.999 | 3.150 | 13.513 | 5.645 | 8.569 |

## Q2: 18-awg-pvc stand-off ladder, nominal_nsegs 21

| h | h mm | h/a | h/a′ | nec5 | nec5_lonly | razor | bs2 | gap_pair % | gap_Lonly % | nec5 vs bs2 % | razor vs bs2 % | shift nec5 % |
|---|---:|---:|---:|---|---|---|---|---:|---:|---:|---:|---:|
| b | 1.050 | 2.05 | 1.23 | 57.907+32.903j | 55.636+25.924j | 57.985+33.184j | 58.543+35.154j | 0.437 | 11.422 | 3.425 | 2.998 | 11.96 |
| 2b | 2.100 | 4.10 | 2.46 | 53.694+19.284j | 53.226+12.653j | 53.742+19.597j | 54.005+20.861j | 0.554 | 12.173 | 2.776 | 2.230 | 12.15 |
| 5b | 5.250 | 10.25 | 6.14 | 51.713+2.779j | 51.700-3.235j | 51.724+2.941j | 51.995+4.193j | 0.314 | 11.920 | 2.765 | 2.456 | 11.61 |
| 20a | 10.240 | 20.00 | 11.97 | 50.834-8.302j | 50.867-14.103j | 50.818-8.384j | 51.114-6.907j | 0.162 | 11.105 | 2.759 | 2.920 | 10.99 |

## Mesh: nominal_nsegs 21 → 42

| cell | bs2 move % | razor move % | nec5 move % | gap_pair at 21 % | gap_pair at 42 % |
|---|---:|---:|---:|---:|---:|
| m0-18 | 0.088 | 2.109 | 1.243 | 0.437 | 1.290 |
| m1-28 | 2.670 | 4.321 | 1.137 | 3.150 | 0.043 |
| m2-20a | 0.109 | 1.814 | 1.445 | 0.162 | 0.210 |

## Severns surface deck (N = 16, h = 1.6 mm)

Measured 56.100+6.200j; momwire's docstring a′ + L 49.380+14.930j.

| arm | Z | R − 56.1 | X − 6.2 | \|Z − docstring\| |
|---|---|---:|---:|---:|
| nec5 | 49.993+13.431j | -6.11 | +7.23 | 1.62 |
| nec5_lonly | 48.339+17.267j | -7.76 | +11.07 | 2.56 |
| nec5_pre | — | — | — | — |
| razor | 49.457+13.510j | -6.64 | +7.31 | 1.42 |
| bs2 | 50.782+14.739j | -5.32 | +8.54 | 1.41 |

## K1: the monkeypatched inductance-only spelling against pre-#1532

| cell | nec5_lonly (main) | nec5_pre | \|Δ\| Ω |
|---|---|---|---:|
