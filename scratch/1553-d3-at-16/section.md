
## d=3 at 16 — 2026-09-16

AK PR #1553 moves bspline d=3's served density from **12 to 16**. That was a decision; this is the measurement. Same 103 designs × 2 grounds, same bs2@160 reference, same one-third rule on ΔΓ. momwire `cbe6404da` (`v0.56.0-26-gcbe6404`), rebuilt; the reference was re-validated bit-for-bit on this build first. `density.py` is untouched — the harness takes the density directly.

| d=3 rung | admissible | median ΔΓ | p90 ΔΓ | worst ΔΓ | median rel-Z | worst rel-Z |
|---:|---:|---:|---:|---:|---:|---:|
| **12** | 158 | 0.0040 | 0.0796 | 0.9001 | 1.11 % | 240 % |
| **16** | 140 | 0.0035 | 0.0740 | 0.7426 | 1.09 % | 189 % |

Unresolved under the one-third rule: 46 at 12, 64 at 16.

### The three tail designs

| design | ground | ΔΓ at 12 | ΔΓ at 16 | change | rel-Z at 12 | rel-Z at 16 |
|---|---|---:|---:|---:|---:|---:|
| `dipoles.short_dipole_loaded` | free | 0.9001 | **0.7426** | -17 % | 225 % | 177 % |
| `dipoles.short_dipole_loaded` | somm | 0.8915 | **0.7374** | -17 % | 240 % | 189 % |
| `specialty.continuous_helix` | free | 0.2195 | **0.1441** | -34 % | 42 % | 28 % |
| `specialty.continuous_helix` | somm | 0.2174 | **0.1427** | -34 % | 41 % | 27 % |
| `wire.zepp` | free | 0.1657 | **0.1665** | +0 % | 31 % | 31 % |
| `wire.zepp` | somm | 0.1665 | **0.1672** | +0 % | 31 % | 31 % |

### The price of 12 → 16

| d=3 rung | catalog cold total | median cold | worst single | worst peak RSS |
|---:|---:|---:|---:|---:|
| **12** | 68.6 s | 0.149 s | 5.79 s | 776 MB |
| **16** | 96.4 s | 0.169 s | 9.59 s | 1240 MB |

Cold-total ratio 16/12: **1.41×**.

### K1–K3, scored

| prediction | bar | measured | verdict |
|---|---|---|---|
| **K1** | catalog median ΔΓ in 0.0025–0.0040 | 0.0035 | **HIT** |
| **K2** | `short_dipole_loaded` worst falls to 0.70–0.82 | 0.7426 | **HIT** |
| **K3** | catalog cold total rises 1.2–1.8× | 1.41× | **HIT** |

### What 16 buys, and the thing that changed underneath

**16 improves `short_dipole_loaded` and does not rescue it**: ΔΓ 0.9001 → 0.7426,
a 17 % reduction, still 0.74 on a [0, 2] scale. K2 predicted 0.70–0.82 from the
measured ladder and it landed at 0.7426. If the case for moving d=3 rests on
fixing the loaded dipole, **16 is not the number that does it** — the ladder says
N≈30 gets that design to 0.45, and even that is not close.

`specialty.continuous_helix` — the one genuine density row of the three — improves
most, **−34 %** (0.2195 → 0.1441), which is what a density row should do.

`wire.zepp` does not move at all (**+0 %**, 0.1657 → 0.1665). That is the AK#1552
placement verdict confirmed from a new rung: its fed wire is one fixed 0.05 m
segment at 12 and at 16 alike, so refining the knob cannot touch what its driving
point depends on.

### The reference is now the limiting factor, and that is new

**Admissible rows fell from 158 to 140, and unresolved rose from 46 to 64.**
Nothing got worse — the *errors* fell. The one-third rule compares bs2@160's own
×80→×160 movement against the error being judged, so as d=3's error shrinks the
reference's fixed uncertainty becomes a larger share of it, and 18 more rows stop
being arbitrable.

This is the limit recorded on AK#1543 running in reverse. There it was *"a row can
become admissible precisely because its error is large"*; here, **improving the
engine makes rows unresolved.** The practical consequence for the density
decision: **bs2@160 is close to the floor of what it can adjudicate at d=3's new
density.** Going further than 16 — or claiming much about the p90 at 16 — needs a
deeper reference (bs2@240 or 320 catalog-wide, not just on three designs), or the
comparison stops meaning anything. That is a measurement-design decision, not a
density one, and it is not proposed here.

### Cost

12 → 16 costs **1.41×** in catalog cold-solve total (68.6 s → 96.4 s), with the
worst single solve going 5.79 s → 9.59 s and worst peak RSS 776 MB → 1240 MB. An
O(N²) fill at 1.33× would be 1.78×; the shortfall is the fixed interpreter and
setup floor that dominates most catalog designs, the same effect measured on
AK#1525.
