# AK#1552 — the bspline tail: density, reference, or placement?

Registered 2026-09-16 **before the first cell**. Branched from
`scratch/1543-bspline-served-density` (PR #1551) rather than main, because #1551
is open; it rebases onto main when that merges.

## 1. The three rows

From #1543's served-rung run: `dipoles.short_dipole_loaded` (both grounds, d=2
and d=3), `specialty.continuous_helix` (d=3), `wire.zepp` (d=3) sit 100–240 % from
bs2@160 while the family medians are within 1.6× of each other.

## 2. Setup

| axis | value |
|---|---|
| antennaknobs | main `b492546ca` (branch point: my #1543 record) |
| momwire | main **`ec4047c`** (`v0.56.0-18-gec4047c`), rebuilt; #1089/#1093 are deck-reader only |
| metric | the #1525 ladder's: `|ΔZ|` over all ports as a vector, relative over `|Z_ref|` |
| ladders | d=3 at **12 / 15 / 20 / 30**, d=2 at **15 / 20 / 30**, both grounds |
| arbitration | **bs2 at 240 and 320** on these three designs, plus **razor-2p at 160 and 320**, plus NEC-5 where the export parses |

All three are small — the largest is `continuous_helix` at 1,634 segments on the
320 rung — so the deep rungs cost little. One heavy solve at a time is kept.

## 3. What the geometry already says, before any solve

`dipoles.short_dipole_loaded` is **one wire**, 2.6767 m at 28.0 MHz — 0.25 λ
end to end, so a genuinely short dipole — carrying a single
`Load(port='feed', l=4.65e-06)` at a `PortOnWire` gap in its middle.

At 28.0 MHz that inductor is **+j818 Ω**. A 0.25 λ dipole's own reactance is
large and capacitive, of the same order. The served driving point is therefore
**the residual of two large opposed reactances**, and #1543 measured `|Z_ref|` at
about **17 Ω** on this design.

That has a consequence for every relative figure on this row: a **1 %** error in
the antenna's own X is ~8 Ω, which against a 17 Ω residual is **~47 %**. The
relative error is amplified by the cancellation by a factor of roughly
`X_L / |Z|` ≈ **48**. So a row like this can show a huge *relative* error while the
underlying quantity is converging perfectly well in ohms — and the issue's third
option, "placement artefact", is not the only alternative to density and
reference.

**This is a structural reading, not a measurement**, and it is why H1 below is
what it is. It is registered so that if the data disagrees, the disagreement is
visible rather than absorbed.

## 4. Predictions — the three verdicts, registered

* **H1 — `dipoles.short_dipole_loaded` is a REFERENCE row**, by way of the
  cancellation above. Bars, both required:
  1. the **absolute** ohm error of d=3 falls by **≥ 40 %** from N=12 to N=30, i.e.
     density behaves normally underneath;
  2. bs2@160 → bs2@320 moves by **more than 10 %** of `|Z(bs2@320)|` on this
     design, i.e. the reference itself is not settled at a 17 Ω residual.
* **H2 — `specialty.continuous_helix` is a DENSITY row.** Bars: d=3's error falls
  by **≥ 60 %** from N=12 to N=30, and bs2@160 → bs2@320 moves by **< 2 %**.
* **H3 — `wire.zepp` is a DENSITY row.** Same bars as H2.

**The placement check runs regardless of the verdicts**: `fed_segments()` is
recorded at every rung for `short_dipole_loaded`, so where the load's knot lands
as N changes is on the record whether or not it turns out to matter.

If a design's absolute error does **not** fall with N and the reference **is**
settled, the verdict is placement — and none of H1–H3 predicts that, so such a
result is a clean miss rather than an unfalsifiable third option.

## 5. Deliverable

One line per design — density / reference / placement — with the ladder numbers
behind it. **No change to `density.py` is proposed**; the verdicts are what would
justify one, and that is Steve's call. Nothing is posted to the issue.
