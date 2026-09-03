# BLE 1937 / NEC-5 Validation Manual screen record (2026-09-02)

Every NEC-5 number below was printed by the licensed `nec5cl` (Linux build, `~/antennas/NEC5-downloads/nec5-linux/`) on the deck of the same name in `decks/`. Regenerate a deck with the generator named in each section; run with `nec5cl <deck>.nec <out>` in a scratch directory (it writes a `SOMMPD.NEX` table beside the deck).

Conclusions are on momwire#838 and antennaknobs#1104; the memory note is `nec5-radial-screen-reference`.

## 1. NEC-5 Validation Manual §4.3 / Appendix B screen (`appb_deck.py N slope|hub ex0 [mono_segs]`)

λ/4 monopole (the PDF renders λ as "9": "9 /4" = λ/4), N radials at depth 1e-4 λ, wire radius 1e-5 λ, ε̃r = 15 − j15; scaled to 1 MHz: 74.95 m, 3 cm, 3 mm, σ 8.345e-4 S/m. 23 segments per radial; base feed `EX 0` on the monopole's first segment (`EX 4` prints identically). `slope` = the manual's construction (first radial segment slopes from the interface junction to depth); `hub` = one vertical rise then horizontal radials, the antennaknobs shape.

| N | slope (manual) | hub |
|---|---|---|
| 2 | 50.681 +22.966j |  |
| 4 | 49.809 +22.714j |  |
| 8 | 48.230 +22.297j | 48.196 +22.193j |
| 16 | 45.855 +21.701j |  |
| 32 | 43.092 +20.965j | 43.097 +20.914j |
| 128 | 39.039 +19.617j |  |

Resistance sits on Fig. B.2's contours at every N. Monopole mesh ladder at N=32 hub (radials fixed at 23): 23 → 43.097 +20.914j, 46 → 43.200 +21.578j, 92 → 43.296 +21.891j, 184 → 43.360 +22.053j (EX 4 at 46: 43.200 +21.578j). N=8 at 92: 48.433 +23.264j; N=128 at 92: 39.235 +20.557j.

## 2. Deep variant both engines serve (`appb_deck.py` with DEPTH=1.5 RFAC=0.6 RAD=0.0005, hub, 46 monopole segs)

1 MHz, ε̃ = 15 − j15, depth 1.5 m, radials 0.6 × λ/4 = 44.97 m, wire radius 0.5 mm (antennaknobs' default).

| N | NEC-5 hub | momwire, AK `buried_radial_vertical` slot | momwire time |
|---|---|---|---|
| 2 | 50.340 +23.505j | 113.778 +85.695j | 8 s |
| 4 | 49.836 +23.502j | 81.309 +100.510j | 9 s |
| 8 | 48.843 +23.449j | 62.399 +106.803j | 24 s |
| 16 |  | 50.455 +107.154j | 158 s |

momwire's own single-rise hub spelling (declared junction, ungraded node) at N=2 / 4: 115.644+49.254j / 80.372+46.601j — same resistances as the coincident-rise bundle. momwire run: `ak_slot_momwire.py 1.5 0.6 2 4 8 16`. At the manual's depth (3 cm) momwire REFUSES: full radials exceed the 2 λ_m below/below cap (2.3 λ_m); truncated radials hit the 1° grazing floor (θ = 0.038° between the rise's node panel and a radial tip).

## 3. antennaknobs `buried_radial_vertical` default geometry in NEC-5 (`brv_default_deck.py hub|detached`)

7.1 MHz, soil (13, 0.005), monopole 10.56 m (15 segs), 4 radials 6.33 m (10 segs) at 0.15 m, wire 0.5 mm.

| spelling | NEC-5 | momwire (design docstring, n_qp_pair 8) |
|---|---|---|
| hub-connected (one rise) | 49.783 +20.952j | 75.862+43.576j (connected, coincident rises) |
| detached (stake) | 50.111 +21.459j | refused by name |

NEC-5 reads the same connected or detached: the ~30 Ω gap to momwire is its interface-node treatment (momwire#524 / #567), not a convention difference.

## 4. Brown, Lewis & Epstein 1937, Fig. 36 / 37 geometry in NEC-5 (`ble_deck.py N L_ft [eps_r]`)

Proc. IRE 25(6) p. 753, June 1937 (PDF: worldradiohistory.com/Archive-IRE/30s/IRE-1937-06.pdf, paper on pdf pages 117–150; fetch with a browser User-Agent). 3.000 MHz; 2.5 in galvanized mast at 77° (21.4 m, 23 segs); No. 8 copper radials (r 1.63 mm) plowed in ≈ 6 in (0.152 m) deep, 23 segs; σ = 0.2e-4 mho/cm³ = 2e-3 S/m; ε not stated (15 assumed; 5 and 30 shown). Hub spelling, base feed.

| N | BLE Fig. 36 (135 ft), read | NEC-5 135 ft, ε 15 | NEC-5 135 ft, ε 5 | NEC-5 135 ft, ε 30 | BLE Fig. 37 (45 ft), read | NEC-5 45 ft, ε 15 |
|---|---|---|---|---|---|---|
| 2 | ≥ 50 (off scale) | 35.816 -59.767j | 38.545 -60.961j | 35.153 -58.843j | ≥ 50 | 35.708 -59.878j |
| 15 | 34 | 32.748 -60.185j |  |  | 33 | 32.218 -61.331j |
| 30 | 30 | 30.947 -60.429j |  |  | 31 | 30.466 -62.374j |
| 60 | 26 | 29.352 -60.605j |  |  | 31 |  |
| 113 | 24.3 | 28.300 -60.703j | 29.823 -60.742j | 27.779 -60.139j | 31 | 28.361 -63.855j |

Readings are from `ble_fig36_crop.png` (260 dpi crop of pdf page 142): the resistance axis runs 10–40 Ω at ≈ 183 px per 10 Ω; the paper's "theoretical R" line sits at 24.3 Ω and the 113-radial point lands on it. Fig. 37 values beyond N=15 are the plateau read at ±1 Ω.

Cross-check, N6LF (QEX Mar/Apr 2009 part 3, Table 1; 7.2 MHz; 33 ft No. 18 radials ON the surface; σ 0.015–0.02, εr 30): 64 → 39.7−1.2j, 32 → 42.9+2.1j, 16 → 56.1+6.2j, 8 → 85.5+8.0j, 4 → 137+14.9j. QEX Jan/Feb 2009 part 2, Table 4 (33 ft): 4 → 89.8, 8 → 51.8, 16 → 40.5.


## 2026-09-03 — G1-A: the 1.75-vs-6.7 Ω separation is the ε_r assumption

The paper states σ = 2e-3 S/m and no permittivity; the gate assumes ε_r = 15.
At that soil momwire separates the 45 ft and 135 ft screens by 1.75 Ω at
N = 113 where the figures separate by 6.7, with the 45 ft series reading low.
Sweeping ε_r and σ at N = 30 (momwire main 84211f8 / v0.47.0, `ble_deck`,
q = 16, auto default otherwise; laptop):

45 ft, N = 30 (Fig. 37 reads ~31 on the plateau):

| ε_r | σ 0.001 | σ 0.002 | σ 0.005 | σ 0.01 |
|---|---|---|---|---|
| 5 | 30.90 | **31.53** | 30.25 | 29.14 |
| 15 | 26.94 | 28.51 | 29.47 | 28.99 |
| 30 | 27.53 | 27.94 | 28.72 | 28.74 |

135 ft at N = 30 (Fig. 36 reads 30): ε_r 5 / σ 0.002 → 29.72 (ε_r 15 → 30.52).
ε_r 5 with σ ≥ 0.005, and ε_r 30 at σ 0.002, refuse the 135 ft screen on the
4 λ_m below/below cap (λ_m grows as |ε̃| falls).

Both ladders at ε_r 5, σ 0.002 (the paper's σ):

| N | 45 ft momwire | Fig. 37 | 135 ft momwire | Fig. 36 |
|---|---|---|---|---|
| 2 | 83.59 | ≥ 50 | | ≥ 50 |
| 4 | 54.03 | | | |
| 8 | 40.40 | | | |
| 15 | 34.58 | | 35.33 | 34 |
| 30 | 31.53 | ~31 | 29.72 | 30 |
| 60 | 30.12 | | 26.03 | 26 |
| 113 | 29.47 | ~31 | 23.96 | 24.3 |

Separation at N = 113: **5.51 Ω** against the measured 6.7 (1.75 at ε_r 15).
Every 135 ft rung is within 1.3 Ω of the figure and the plateau rungs within
0.35; the 45 ft plateau sits 1.5 Ω low at N = 113 and on the figure at N = 30.

Reading: a single permittivity in the plausible band for a σ = 0.002 S/m soil
(dry-to-medium ground) brings nine readings across two radial lengths to
within the figures' reading error, so the residual the gate carried as
"everything else" is mostly the ε_r term, and it acts through the SHORT
screen — the loss outside a 0.137 λ screen is set by the soil, and the long
screen covers that region. This is a one-parameter fit, so the gate keeps its
a-priori ε_r = 15 and its measurement-built envelope (the rule: envelopes
come from the measurement, not from what makes the test pass); what changes
is the record — the envelope's ±3.2 "everything else" term is now mostly
attributable. A follow-up gate could marginalise ε_r over the plausible band
instead of fixing it; that is a design question for the BLE test, not a
result here.

Not done: N = 4 and 8 at 135 ft (cheap; not needed for the reading), and the
ε_r 5 ladder on the 90 ft radials (Fig. 36's middle series, not yet in the
test). The 45 ft N = 113 solve is 386 s and the 135 ft one 365 s on the
laptop.
