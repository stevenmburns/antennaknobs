# 2026-07-11 — station loss comparison: coax-fed inv-vee vs doublet + open-wire + tuner

Closes the loop on the station-modelling arc (#297 lossy TL, #298 finite-Q
components, #299 power budget, #300 this comparison). Two designs model the
whole station from a virtual **rig** port, so impedance, SWR, gain, and the
power budget are referenced to the transmitter:

- `dipoles.invvee_coax_station` — the stock 28.47 MHz inv-vee + 100 ft of
  50 Ω coax (cable preset dropdown).
- `wire.doublet_ladder_tuner` — an 88 ft flat doublet + 100 ft of 600 Ω
  open-wire line + T-network tuner (series C / shunt L with `coil_q` /
  series C), stock-tuned for 40 m.

All numbers below: momwire SinusoidalSolver, free space, `line_len_m` =
30.48 m (100 ft), budget fractions of rig input power. Cross-engine check:
PyNEC agrees on Z_rig within 0.2 % on both designs at defaults.

## Coax station: the cable is the knob

On its design band the V presents SWR ≈ 1.2 at the rig, so the line runs
essentially matched — the budget is just the cable's matched loss. Worked
one band down (24.94 MHz, where the antenna is far off resonance), the
SWR-multiplied loss appears by itself out of the circuit solve:

| Cable | 28.47 MHz (SWR≈1.2) | 24.94 MHz (off-band) |
| --- | --- | --- |
| RG-58 | 57.6 % radiated (−2.4 dB) | 14.3 % (−8.4 dB) |
| RG-8X (default) | 68.8 % (−1.6 dB) | 20.3 % (−6.9 dB) |
| RG-213 | 78.3 % (−1.1 dB) | 28.3 % (−5.5 dB) |
| LMR-400 | 85.7 % (−0.7 dB) | 38.6 % (−4.1 dB) |

Two folklore items land as numbers: coax at 10 m is not cheap even when
matched (100 ft of RG-8X eats a third of the power), and an off-resonance
antenna on coax is brutal — the same RG-8X run swallows ~80 %.

## Doublet station: the tuner coil is where multiband is paid for

Stock tune (7.1 MHz, C1 = 74.2 pF, L = 4.70 µH, C2 = 1618 pF, Q = 200)
lands Z_rig = 50.0 + 0.0j:

| Operating point | line | tuner coil | radiated |
| --- | --- | --- | --- |
| 40 m (7.1 MHz), Q=200 | 3.7 % | 4.5 % | **91.8 % (−0.4 dB)** |
| 40 m, ideal coil (Q=0 knob) | ~3.9 % | 0 | 96.1 % |
| 80 m retune (3.8 MHz)¹, Q=200 | 14.4 % | 13.7 % | **71.9 % (−1.4 dB)** |
| 80 m retune, ideal coil | — | 0 | 83.3 % |

¹ 80 m values: C1 = 44.6 pF, L = 27.05 µH, C2 = 6865 pF. At 3.8 MHz the
88 ft doublet is electrically short (feed ≈ 23 − j504 Ω), so both the
line's SWR loss and the coil's circulating-current loss climb — the honest
cost of working a too-short wire. The T-network caps (ideal here) burn
nothing; the coil is the entire tuner cost, scaling as expected with Q
(`test_doublet_coil_loss_scales_with_q`).

## The headline

Same 100 ft of feedline, both stations matched at the rig:

- **On a band each is built for**: doublet + open wire + Q-200 tuner
  radiates 92 % (−0.4 dB); the resonant inv-vee on RG-8X radiates 69 %
  (−1.6 dB) at 10 m. The "lossy tuner" station *wins* — open-wire line is
  that much better than coax, and a decent coil costs less than the
  difference.
- **Flexibility**: retuned to 80 m the doublet still delivers 72 %; the
  coax station worked equivalently off-band delivers ~20 %. Ladder line +
  tuner degrades gracefully; coax + SWR does not.

Every number above is read off the Info pane's power-budget table (or
`antennaknobs pattern`); nothing is a formula overlay. Pinned by
`tests/test_station_designs.py`.
