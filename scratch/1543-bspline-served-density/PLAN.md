# AK#1543 — the bspline family at the densities #1547 now serves

Registered 2026-09-16 **before the first cell**. Extends `scratch/1525-razor-density/`
rather than forking it: the reference is that ladder's **bs2@160**, already on disk.

## 1. The question

`density.py` (AK main, after #1547/#1543) serves the bspline family **per degree**
— `{1: 20, 2: 15, 3: 12}` — because the degree *is* the basis. The #1525 ladder's
lowest bs2 rung was 21 and it never ran d=1 or d=3, so **none of the three served
densities has been measured on this ladder's metric**. The table's bspline rows
currently rest on the July 2026 basis-convergence census. This run puts them on
the same footing as razor-2p's 2.42 % at 40.

razor-2p at 40 is already measured and is **not** re-run. NEC-5 at 40 stays at its
8 free-space rows until momwire#1084 (`GN NOFILE`) lands, and is left out.

## 2. Setup

| axis | value |
|---|---|
| antennaknobs | main **`b492546ca`** — `density.py` and `--nominal-nsegs` present; #1548 (the ladder record) is merged here |
| momwire | **`a6a67f93a`**, the briefed commit, detached and rebuilt with `make build` |
| reference | **bs2@160** from `scratch/1525-razor-density/records.jsonl` |
| rungs | **bs2 at 15, bs1 at 20, bs3 at 12** — one per degree, from `density.py` |
| grounds | free and Sommerfeld `("finite", 13.0, 0.005)`, the ladder's own rows |
| metric | `|ΔZ|` over all ports as a vector; relative is that over `|Z_ref|` |
| rule | #845's one-third: a row counts only if bs2's own ×80→×160 move stayed under a third of the error being judged |

618 cells: 103 designs × 2 grounds × 3 degrees.

**momwire main is one commit ahead of the briefed `a6a67f93a`** (`03e483d`, a
test-only change touching no `src/`), so the briefed commit is numerically current
and is what is used.

### The reference was re-validated, not assumed

bs2@160 was measured at momwire `a925d37`; this run is at `a6a67f93a`, and the
diff between them removes 37 lines from `_medium_spec.py` — a file that could
plausibly touch the ground path. Reusing a reference across that without checking
is the mistake this study has already made twice in other forms, so it was
checked: **bs2@160 and razor@160 re-measured on 7 designs × 2 grounds (32 cells)
spanning buried, Sommerfeld, multi-port, network and the largest catalog design
are bit-identical to the stored records.** The stored reference is therefore valid
for these cells.

## 3. What this run can and cannot say

**One rung per degree means there is no convergence class and no fitted order.**
The #1525 ladder classified rows because it had four rungs; this has one. The only
classification available here is **admissibility** — whether the reference is
settled enough under the one-third rule for the row to count — and that is what
the "class counts" below report. Nothing here says a degree is converging.

## 4. Predictions

Anchored on the ladder's own bs2 rows, which measure bs2 against bs2@160 at 21,
40 and 80: medians **0.617 %**, **0.320 %**, **0.138 %**, implying a local order
near 1.0–1.2 for bs2 on this metric.

* **G1.** bs2@15's median error against bs2@160 lands in **0.6–1.5 %** —
  extrapolating bs2@21's 0.617 % down to 15 at order ≈ 1.1 gives ≈ 0.90 %.
* **G2.** All three served rungs have a median error **below razor-2p@40's
  2.42 %**. The bspline family at its served densities should be closer to its
  own limit than the first-order pair is at theirs; if that fails, the density
  table's bspline rows are not doing what the census claimed.
* **G3.** The three medians agree within a factor of **3** of each other. 15 / 20
  / 12 were chosen to be comparable across degrees, so no degree should be an
  outlier.
* **G4.** Admissible rows under the one-third rule number **120–175** of 206 for
  each degree, anchored on **145 of 204** measured for bs2@21 on the ladder.

Misses are reported as misses.

## 5. Deliverable

Per degree at its served rung: admissibility counts, median / p90 / worst over the
counted rows, and cost — catalog cold-solve total, median cold, worst single solve,
worst peak RSS. Records extend `scratch/1525-razor-density/`'s on the same metric.
