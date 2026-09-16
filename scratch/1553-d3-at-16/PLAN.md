# d=3 at 16 — turning a decision into a measurement

Registered 2026-09-16 **before the first cell**. Steve moved bspline d=3's served
density from **12 to 16** (AK PR #1553, open) on the ΔΓ re-cut; 16 is a decision,
not yet a measured rung. This measures it.

`density.py` is **not touched** — the PR already carries the 16, and the harness
takes the density directly, so this does not need #1553 merged.

## Setup

| axis | value |
|---|---|
| antennaknobs | main `b492546ca` |
| momwire | main **`cbe6404`** (`v0.56.0-26-gcbe6404`), rebuilt |
| rung | **d=3 at 16**, one rung, 103 designs × 2 grounds = 206 cells |
| reference | bs2@160 from the AK#1525 ladder |
| rule | one-third admissibility, stated on ΔΓ |
| metrics | ΔΓ (vector norm over ports) **and** relative Z, side by side |

### The reference was re-validated again, and the build note was not right

The brief says momwire has had "reader-side changes only" since my last build.
The diff `ec4047c → cbe6404` touches **`bspline.py`** (13 insertions) and
**`_wire_loading.py`** (+180, "the seam takes a per-metre RLC beside the metal and
the jacket") — solver-path files, not reader-side. Since bs2@160 *is* the
reference for every number here, that had to be settled rather than assumed:
**32 cells re-measured (bs2@80 and bs2@160 across the three tail designs plus
four_square, bowtie16x1, buried_dipole, trap_fan_dipole and pota_invvee) are
bit-identical to the stored records.** The new per-metre RLC path is simply not
exercised by these designs. The reference stands; the characterisation did not.

## Predictions

At d=3 the ladder already measured ΔΓ **0.9001 / 0.8153 / 0.6284 / 0.4486** at
N = 12 / 15 / 20 / 30 on `short_dipole_loaded`, and a catalog median of **0.0040**
at N = 12.

* **K1 — catalog median ΔΓ at d=3@16 lands in 0.0025–0.0040**, i.e. better than
  12's 0.0040 and not dramatically below d=2@15's 0.0037. A 12→16 step is 1.33×.
* **K2 — `short_dipole_loaded`'s worst row falls to 0.70–0.82**, from 0.9001.
  Interpolating the measured ladder between N=15 (0.8153) and N=20 (0.6284) at a
  local order of ~0.9 puts 16 at ≈ 0.77. **This is the load-bearing prediction:
  16 improves that design and does not rescue it.** If the verdict on d=3 rests
  on fixing the loaded dipole, 16 is not the number that does it.
* **K3 — the catalog cold-solve total rises by 1.2–1.8×** over the 12 rung. An
  O(N²) fill at 1.33× would be 1.78×, but most catalog designs are small enough
  that a fixed interpreter-and-setup floor dominates — measured on AK#1525, the
  80-vs-40 wall ratio was 3.99 on designs above 2000 segments and 2.22 below.

## Deliverable

A dated **"d=3 at 16"** section appended to the served-rung record's README, with
the 16 row beside the 12 row: median / p90 / worst ΔΓ, admissible counts, the
three per-design tail rows, and the cost columns so the price of 12→16 is on the
record. Relative-Z columns beside, as before. Nothing posted to any issue.
