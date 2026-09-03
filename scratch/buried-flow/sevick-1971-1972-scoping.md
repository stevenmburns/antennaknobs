# Sevick W2FMI, QST July 1971 and June 1972 — scoping read (2026-09-03)

Read from Steve's PDFs (ARRL archive scans, 1-bit ~150 dpi, 6 pages each) by
an Opus subagent per the cheap-model scan rule; tables transcribed twice, both
passes agreeing on every cell. Purpose: is there a buried-radial R-vs-N series
with stated soil to sit beside Brown-Lewis-Epstein 1937? **No.**

## 1971, "The Ground-Image Vertical Antenna" (pp. 16–19, 22)

- **Placement, as measured: not stated.** The only depth language is a
  recommendation: "I found that burying the wires slightly below the surface
  is the best way of installing the system" and "the radial wires need be
  buried only as deep as necessary to escape children's feet and the lawn
  mower." "Six feet down" and "more than a few feet" are the rules he rejects;
  "a foot or two" is his field-penetration remark. No inch or centimetre.
- **Soil: no statement** — no conductivity, permittivity, soil type or
  measurement method anywhere; only "the earth is a somewhat conducting
  medium" and "the dielectric property of the earth plays a major role".
- Geometry: 14.25 MHz; quarter-wave vertical (height/diameter not given;
  Fig. 1 text says "effective height-to-radius ratio of 300"); radials
  "eight bundles of wires, each 25 feet long, and each made up of five No. 18
  copper wires", called 0.4 λ throughout (25 ft is 0.362 λ at 14.25 MHz — both
  as printed); 4 / 8 / 40 radials by fanning the bundles; insulation not
  stated; eleven added 3/2 λ radials at 5°.
- **Fig. 1, input resistance vs number of 0.4 λ radials** (a smooth curve, no
  plotted markers; y ticks every 10 Ω legible; x numerals destroyed by the
  scan and calibrated from Fig. 2's identical grid, 0–55 at 5 per tick — an
  inference). Read ±1 Ω:

  | radials | 0 | 2 | 4 | 6 | 8 | 10 | 15 | 20 | 30 | 40 | 55 |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | R (Ω) | 77.9 | 72.4 | 66.5 | 62.1 | 58.9 | 55.7 | 50.7 | 46.5 | 42.0 | 39.5 | 36.7 |

  Dashed "THEORETICAL VALUE" at 34.4 Ω. Measured "with a simple impedance
  bridge", "resonated before each measurement"; bridge calibrated with carbon
  resistors at 14.25 MHz. No repeatability or error statement.
- Table I (field strength λ/4 vs 5/8 λ at 0.1–3°) and Figs. 2–3 (dB above S9
  vs radials) transcribed in the subagent report; not radial-count impedance
  data beyond Fig. 1.

## 1972, "The W2FMI 20-Meter Vertical Beam" (pp. 14–18)

- Placement: **not stated** ("mounted at ground level", "three, short, thin
  aluminum poles on the ground"); no depth. Soil: **no statement**.
- Image plane: inner square of diagonal 4/10 λ (25 ft), No. 14 outer / No. 18
  inner wires; 0.4 λ No. 18 outer radials, 25 per corner and 9 per side.
- No R-vs-N table or figure; the radial-count result is prose (removing the
  outer radials one by one dropped F/B 19 → 7 dB and forward gain ~2 dB).

## Verdict

Neither paper states depth or soil. The 1971 Fig. 1 curve is a real R-vs-N
series at 14.25 MHz (78 → 39.5 Ω over 0 → 40 radials), but it would enter any
gate with an assumed ε_r, an assumed σ, an assumed depth AND an assumed
wire radius/height — four assumptions where BLE carries one (ε_r) and the
Severns elevated anchor (momwire#866) carries none that matter. **Parked**, as
Haswell recommended on momwire#838 from the 1973 paper; the 2003 book stays a
no (Steve). If a surface serve lands (momwire#865), the 1971 curve becomes a
weak third shape check at best, behind Severns 2009 who measured his soil.
