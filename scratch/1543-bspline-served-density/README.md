# AK#1543 — the bspline family at the densities #1547 serves

**Builds.** antennaknobs main `54ca0978b` (v0.79.0); momwire `a6a67f93a` (`v0.56.0-9-ga6a67f9`, v0.56.0), detached at the briefed commit and rebuilt; accelerator `_accelerators_avx2`. **Reference: bs2@160 from the AK#1525 ladder**, re-validated on this build before use — 32 cells across 7 designs × 2 grounds spanning buried, Sommerfeld, multi-port, network and the largest catalog design are bit-identical to the stored records. Provenance is the first line of `records.jsonl`.

**Metric.** `|ΔZ|` over all ports as a vector; the percentage is that over `|Z_ref|`. Identical to the AK#1525 ladder's, so these rows and razor-2p's sit on one footing.

> **One rung per degree, so there is no convergence class and no fitted order here.** The AK#1525 ladder classified rows because it had four rungs; this has one. The only classification available is **admissibility** — whether bs2's own ×80→×160 move stayed under a third of the error being judged, so the reference can arbitrate the row at all. A row that is not admissible is *unresolved*, not *failing*.

## Error at the served density

| basis | served N | admissible rows | median | p90 | worst |
|---|---:|---:|---:|---:|---:|
| B-spline d=1 | 20 | 149 | 1.53 % | 6.01 % | 20.2 % |
| B-spline d=2 | 15 | 147 | 0.964 % | 8.51 % | 133 % |
| B-spline d=3 | 12 | 158 | 1.11 % | 18.3 % | 240 % |

For comparison, on the same metric, the same reference **and the same admissibility rule**, **razor-2p at its served 40** measures a median **2.72 %** over 145 admissible rows. AK#1525 quotes **2.42 %** for razor-2p at 40; that is a median over its *converging* rows, a different population, and over all 199 comparable rows it is 1.97 %. The 2.72 % above is the only one of the three that is like-for-like with this table.

## Rows the reference cannot arbitrate

| basis | admissible | unresolved (one-third rule) | not solved |
|---|---:|---:|---:|
| B-spline d=1 | 149 | 55 | 2 |
| B-spline d=2 | 147 | 57 | 2 |
| B-spline d=3 | 158 | 46 | 2 |

Unresolved means bs2 itself had not settled between ×80 and ×160 on that design by more than a third of the error being judged. It is a statement about the reference, not about the basis under test.

## Cost at the served density

| basis | served N | catalog cold total | median cold | worst single | worst peak RSS |
|---|---:|---:|---:|---:|---:|
| B-spline d=1 | 20 | 96.2 s | 0.095 s | 34.73 s | 2540 MB |
| B-spline d=2 | 15 | 174.8 s | 0.095 s | 80.60 s | 5180 MB |
| B-spline d=3 | 12 | 68.6 s | 0.149 s | 5.79 s | 776 MB |

## Predictions G1–G4, scored

| prediction | bar | measured | verdict |
|---|---|---|---|
| **G1** | bs2@15 median in 0.6–1.5 % | 0.964 % | **HIT** |
| **G2** | all three medians below razor-2p@40's 2.72 % | B-spline d=1 1.53 %, B-spline d=2 0.964 %, B-spline d=3 1.11 % | **HIT** |
| **G3** | the three medians within a factor of 3 | 1.59× | **HIT** |
| **G4** | 120–175 admissible rows per degree | B-spline d=1 149, B-spline d=2 147, B-spline d=3 158 | **HIT** |

Hit 4 of 4.

## Reading this

### The comparison with razor-2p had to be re-cut, and the number moves

AK#1525 quotes **2.42 %** for razor-2p at 40. That is a median over its
*converging* rows — a population this run cannot reproduce, because one rung per
degree yields no convergence class. Quoting it beside these medians would compare
two different populations.

Re-cut on this table's own rule, razor-2p at 40 measures:

| population | median |
|---|---:|
| converging rows (what AK#1525 quotes) | 2.42 % |
| all comparable rows | 1.97 % |
| **admissible rows, the one used here** | **2.72 %** |

All three bspline degrees sit below the like-for-like 2.72 %, and below 2.42 %
too, so the conclusion is not sensitive to which cut is taken — but the figures in
the table above are only comparable to the **2.72 %**, and anyone quoting them
beside 2.42 % is mixing populations.

### What the three served densities buy

| basis | served N | median | p90 | worst |
|---|---:|---:|---:|---:|
| d=1 at 20 | 20 | 1.53 % | 6.01 % | 20.2 % |
| d=2 at 15 | 15 | 0.964 % | 8.51 % | 133 % |
| d=3 at 12 | 12 | 1.11 % | 18.3 % | 240 % |

The medians are close — a 1.59× spread across the family, which is what the
basis-convergence census intended when it picked 15 / 20 / 12. **The tails are
not close.** d=1 at 20 has both the best-behaved tail and the highest median;
d=3 at 12 has a p90 three times d=1's and a worst case an order of magnitude
beyond it.

**d=3 at 12 is the newest row in `density.py` (added on #1543, 2026-09-16) and
the least evidenced.** Nothing here says it is wrong — its median is fine — but
its tail is the widest of the three on this metric, and that is worth knowing
before it is treated as settled.

### The tail is one design, and it is a familiar one

The worst rows are not scattered:

| basis | design | ground | Ω | relative | \|Z_ref\| |
|---|---|---|---:|---:|---:|
| d=3 | `dipoles.short_dipole_loaded` | Sommerfeld | 40.8 | 240 % | 17.0 |
| d=3 | `dipoles.short_dipole_loaded` | free | 40.6 | 226 % | 18.0 |
| d=2 | `dipoles.short_dipole_loaded` | Sommerfeld | 22.7 | 133 % | 17.0 |
| d=2 | `dipoles.short_dipole_loaded` | free | 22.6 | 125 % | 18.0 |
| d=3 | `specialty.continuous_helix` | free | 9.3 | 41.6 % | 22.4 |
| d=3 | `wire.zepp` | free | 5.2 | 31.0 % | 16.8 |

`dipoles.short_dipole_loaded` is the same design that led the published catalog
page's widest-row table and was classed *reference unsettled* there. It is a
low-impedance loaded dipole — a ~17 Ω driving point — so the ohm column matters:
a 22–41 Ω absolute difference, not a rounding artefact of a small denominator.

### An honest limit of the admissibility rule

`short_dipole_loaded` is marked **admissible** here and was **unresolved** on the
#1525 ladder. Both are correct, and the difference is instructive: the one-third
rule compares the reference's own movement against *the error being judged*. When
that error is 40 Ω, the reference's movement is a small fraction of it and the row
passes; when the error was razor's smaller one, the same reference movement
tripped the rule.

So **a row can become admissible precisely because its error is large.** The rule
bounds the reference's *relative* contribution to a comparison; it does not
certify that the comparison is a good one. Read the admissible counts as "the
reference is not the dominant term here", not as "this row is trustworthy".

### What this run does not say

* Nothing about convergence or order — one rung per degree cannot produce either.
* Nothing about NEC-5 at 40, which stays at its 8 free-space rows until
  momwire#1084 lands.
* Nothing about razor-2p at 15 or 20, the densities the app served before #1547;
  that remains unmeasured and the AK#1525 record says so.

## Reproducing

```
NEC5_EXE=<nec5cl-3b75639> python scratch/1543-bspline-served-density/run_served.py \
  --plan bs2:15 bs1:20 bs3:12 --out scratch/1543-bspline-served-density/records.jsonl
python scratch/1543-bspline-served-density/report.py
```

618 cells in 838 s. The staleness guard runs first and its output is the records
file's first line. The reference is the AK#1525 ladder's bs2@160, re-validated on
this build before use.

## ΔΓ re-cut, 2026-09-16

Same rows, same reference, **no cell re-solved** — re-scored on **ΔΓ**, with the admissibility rule itself re-stated on ΔΓ (bs2's own ×80→×160 move in Γ under a third of the ΔΓ being judged). Relative-Z columns above are unchanged. ΔΓ is the **vector norm over ports**.

| basis | served N | admissible | median ΔΓ | p90 | worst | median rel-Z (above) |
|---|---:|---:|---:|---:|---:|---:|
| d=1 | 20 | 151 | 0.0076 | 0.0257 | 0.1049 | 1.53 % |
| d=2 | 15 | 147 | 0.0037 | 0.0390 | 0.5446 | 0.964 % |
| d=3 | 12 | 158 | 0.0040 | 0.0796 | 0.9001 | 1.11 % |

**razor-2p at 40 on the same rule**: median ΔΓ **0.0129** over 145 admissible rows. On ΔΓ there is no 2.42-versus-2.72 population question — that split was an artefact of two relative-Z cuts, and it retires here.

| basis | admissible on rel-Z | admissible on ΔΓ | unresolved on ΔΓ |
|---|---:|---:|---:|
| d=1 | 149 | 151 | 53 |
| d=2 | 147 | 147 | 57 |
| d=3 | 158 | 158 | 46 |

