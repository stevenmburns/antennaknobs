# M0AGP's "DX gain" table, reproduced (AK#1828 unit 4)

M0AGP's QRZ thread 1005128 (the first post) compares a 160 m inverted L with a
full-size vertical:

- each antenna has two radials 5 ft up, over Average ground (13, 0.005);
- the model is NEC-5, through AutoEZ;
- each inverted L's top wire is cut for resonance.

His DX gain is the power average of the gain over 2–10° elevation, 0.1°
apart, converted back to dB. He reports it relative to the vertical.

This folder is the record of how the reproduction was made:

- `reproduce.py ENGINE [OUT.json [FREQ]]` produces the tables.
- `summarize.py` turns their JSON into the tables below.
- `probe_variants.py` measures the unstated details, one at a time
  (`probe_variants-nec5.txt`).

`reproduce.py` runs the catalog's own pieces. The design is
`verticals.inverted_l:topband`: the vertical section and the top wire are
knobs in feet, with two radials 5 ft up at 1.83 MHz. The metric is the study's
`an.ElevationWindow("DX gain", 2, 10, step=0.1)`, read through
`antennaknobs.metrics` as `analyze` reads it. Ground is Sommerfeld `finite`
13/0.005.

The study's `an.Hold("resonance", adjust=("horiz_ft",))` is sweep-framework
step 6, which does not run yet, so the script does the hold by hand. At each
vertical section it scans the top wire up from 1 ft to the first sign change
of X, then runs Brent to X = 0. The vertical is cut the same way, with no top
wire.

The geometry has the riser along z, the top wire along +y, and the radials
along +x and −x, so they are perpendicular to the top wire. His azimuth is not
stated, so every point is read five ways:

- `PEAK_AZ`, the azimuth of the pattern's peak;
- `MEAN_AZ`, the azimuth average;
- az 0, along the radials and broadside to the top wire;
- az 90, toward the top wire's end;
- az 270, away from the top wire.

## Through the framework: `analyze --study` (step 6's hold)

Since step 6 the study runs end to end, with no script. On both engines the
hold reports 9 of 9 points held, 0 gaps and 46 solves, with a worst residual
of 0.000164 Ω on NEC-5 and 2.6e-5 Ω on momwire:

```bash
NEC5_EXE=~/bin/nec5-licensed python -m antennaknobs analyze \
    --study "verticals.inverted_l:DX gain vs the vertical (M0AGP)" --engine nec5
python -m antennaknobs analyze \
    --study "verticals.inverted_l:DX gain vs the vertical (M0AGP)" --engine momwire:bspline
```

At azimuth 0, 1.83 MHz, the inverted L relative to the vertical (dB):

| ft | M0AGP | study NEC-5 | script NEC-5 | study momwire | script momwire |
|---|---|---|---|---|---|
| 100 | −0.26 | −0.196 | −0.196 | −0.196 | −0.194 |
| 90 | −0.45 | −0.365 | −0.364 | −0.365 | −0.363 |
| 80 | −0.72 | −0.615 | −0.614 | −0.615 | −0.614 |
| 70 | −1.10 | −0.983 | −0.982 | −0.984 | −0.982 |
| 60 | −1.66 | −1.531 | −1.529 | −1.532 | −1.531 |
| 50 | −2.51 | −2.365 | −2.363 | −2.367 | −2.367 |
| 40 | −3.84 | −3.681 | −3.677 | −3.689 | −3.685 |
| 30 | −6.54 | −5.837 | −5.831 | −5.845 | −5.841 |
| 20 | −9.64 | −9.486 | −9.480 | −9.495 | −9.492 |

The study and the script agree to 0.006 dB. The difference has two parts:

- the study's vertical is the catalog's fixed 131.2 ft, where the script
  resonated its own (131.22 ft on NEC-5, 131.10 ft on momwire);
- the two root searches have their own tolerances.

The held top wires agree with the script's to within 0.05 ft.

## Result (the hand-held script, before step 6)

**NEC-5 reproduces his table with the elevation cut at azimuth 0.** At
1.83 MHz it is within 0.16 dB at eight of his nine points. His 70 ft target
of −1.10 dB reads −0.98. The ninth point, 30 ft, misses by 0.71 dB.

His 30 ft value breaks the pattern in his own table. Its steps either side
are −2.70 and −3.10 dB. Every model here steps about −2.15 and −3.65 dB at
those points, on every cut. So either his 30 ft point is not like the others,
or we differ in some detail that only shows there; it is not known which.

momwire agrees with NEC-5 to 0.02 dB or better everywhere.

The cut through the peak (`PEAK_AZ`, which is the side away from the top wire)
misses by up to 3.8 dB, and the azimuth average by up to 1.3 dB. So his
figures are not from either.

### NEC-5 (`~/bin/nec5-licensed`, our gfortran port; far field only), 1.83 MHz, vertical resonant at 131.22 ft

| vertical section (ft) | top wire (ft) | M0AGP | PEAK_AZ | MEAN_AZ | az0 | az90 | az270 |
|---|---|---|---|---|---|---|---|
| 100 | 33.07 | −0.26 | −0.08 | −0.18 | −0.20 | −0.26 | −0.07 |
| 90 | 43.43 | −0.45 | −0.15 | −0.33 | −0.36 | −0.47 | −0.15 |
| 80 | 53.73 | −0.72 | −0.26 | −0.56 | −0.61 | −0.77 | −0.26 |
| 70 | 63.90 | −1.10 | −0.46 | −0.90 | −0.98 | −1.21 | −0.45 |
| 60 | 73.96 | −1.66 | −0.76 | −1.40 | −1.53 | −1.83 | −0.76 |
| 50 | 83.91 | −2.51 | −1.26 | −2.15 | −2.36 | −2.76 | −1.26 |
| 40 | 93.67 | −3.84 | −2.09 | −3.34 | −3.68 | −4.19 | −2.09 |
| 30 | 103.22 | −6.54 | −3.49 | −5.26 | −5.83 | −6.44 | −3.49 |
| 20 | 112.34 | −9.64 | −5.86 | −8.41 | −9.48 | −10.06 | −5.86 |

The worst misses are PEAK_AZ 3.78 dB, MEAN_AZ 1.28, az0 0.71, az90 0.42 and
az270 3.78.

### momwire (`momwire:bspline`), 1.83 MHz, vertical resonant at 131.10 ft

| vertical section (ft) | top wire (ft) | M0AGP | PEAK_AZ | MEAN_AZ | az0 | az90 | az270 |
|---|---|---|---|---|---|---|---|
| 100 | 32.98 | −0.26 | −0.07 | −0.18 | −0.19 | −0.25 | −0.07 |
| 90 | 43.37 | −0.45 | −0.14 | −0.33 | −0.36 | −0.47 | −0.14 |
| 80 | 53.68 | −0.72 | −0.26 | −0.56 | −0.61 | −0.77 | −0.26 |
| 70 | 63.88 | −1.10 | −0.45 | −0.90 | −0.98 | −1.21 | −0.45 |
| 60 | 73.98 | −1.66 | −0.76 | −1.40 | −1.53 | −1.84 | −0.76 |
| 50 | 83.94 | −2.51 | −1.26 | −2.16 | −2.37 | −2.77 | −1.26 |
| 40 | 93.73 | −3.84 | −2.09 | −3.35 | −3.69 | −4.19 | −2.09 |
| 30 | 103.28 | −6.54 | −3.49 | −5.27 | −5.84 | −6.45 | −3.49 |
| 20 | 112.42 | −9.64 | −5.86 | −8.42 | −9.49 | −10.07 | −5.86 |

The worst misses are PEAK_AZ 3.78 dB, MEAN_AZ 1.27, az0 0.70, az90 0.43 and
az270 3.78.

### The same at 1.80 MHz (`nec5-1.80.json`, `momwire-1.80.json`)

At 1.80 MHz, az 0 comes even closer. On NEC-5 it reads −0.23, −0.40, −0.66,
−1.04, −1.59, −2.44, −3.77, −5.94 and −9.61, within 0.07 dB at every point
but 30 ft (0.60 dB). momwire agrees to 0.01 dB.

His percentages suggest a vertical of about 130 ft. That is resonant here near
1.83–1.85 MHz, while 1.80 MHz needs 134.4 ft, so his frequency is not pinned
down. The catalog variant stays at 1.83 MHz.

## What moves it (`probe_variants-nec5.txt`, NEC-5, the 70 ft and 20 ft points)

| change | 70 ft az0 | 20 ft az0 |
|---|---|---|
| baseline | −0.98 | −9.48 |
| mesh 3× finer (nominal_nsegs 63) | −0.98 | −9.49 |
| feed gap 1 m instead of 5 cm | −0.98 | −9.48 |
| frequency 1.80 MHz | −1.04 | −9.61 |
| frequency 1.85 MHz | −0.95 | −9.40 |
| radials turned parallel to the top wire | −0.75 | −4.47 |

- The mesh and the 5 cm feed gap don't matter. The 5 cm gap against 1.9 m
  riser segments looked like a NEC risk, and isn't one here.
- The frequency moves the short verticals by about 0.1 dB.
- The radials' direction is the large one. Turned to run along (and under)
  the top wire, the 20 ft point moves by 5 dB. His figures fit radials
  perpendicular to the top wire, as the catalog variant has them.
