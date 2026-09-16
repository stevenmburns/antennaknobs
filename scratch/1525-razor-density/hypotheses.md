## 7. Reading the ladder

### razor-2p is first order, and the order is measured not assumed

155 of 204 classifiable rows converge toward bs2@160, with a fitted order of
**median 0.90** (p10 0.82, p90 1.24) against the achieved segment count. That is
first order in the mesh, which is what momwire's own `RazorFarMeshClass` advisory
declares and what AK#1516 measured on four designs. It now holds across the
catalog rather than on four cases.

`loops.skyloop_lmatch` fits **2.08** on both grounds, against AK#1516's 1.94–2.34
for the bs2−NEC-5 gap on the same design — the one design in the study whose error
falls quadratically. Predicted in advance (E2b) and hit.

### What ×40 costs in accuracy — and a correction about what was served

**Correction, 2026-09-16.** Everything below said ×40 was "the density the app
serves". It is razor-2p's *declared roster default*, and the app never reached it.
No stock slot seeds razor-2p — the served seeds are bspline at 15, bspline d=1 at
20 and PyNEC — so razor-2p is only arrived at by swapping a slot's backend, and
`useSolverSlots.ts:setSlotBackend` preserves `nPerWire` across the swap, overriding
the very field the roster default would have set. Users ran razor-2p at **15 or
20**. AK#1547 fixes that.

Both are at or below this ladder's lowest rung, so **this study never measured the
density users actually had**, and every figure here understates the real error.
The nearest measured point is ×21: median **3.64 %**, p90 **10.7 %**, worst
**54.7 %** — and since error falls with N, that is a *lower bound* on what 15 gave.
Measuring 15 and 20 properly would need two more rungs; it is not done here.

At `default_n_per_wire=40` razor-2p sits a
**median 2.42 %** from bs2@160 over its 155 converging rows, p90 **7.64 %**, worst
**42.5 %**. Doubling to 80 removes about half of that: the median
`err(80)/err(40)` is **0.519**, which is what first order predicts and is the one
E3 component that landed inside its bar.

**No recommendation follows from this page.** Density is a product call; the curve
is here and the cost is below.

### What doubling density costs, and why my cost bars missed

E3's wall and RSS bars missed, and the reason is that **I set them from the two
biggest designs and then scored them on a median over a population of small
ones.** Split by size, the model is fine:

| population | rows | median wall ×80/×40 | median RSS ×80/×40 |
|---|---:|---:|---:|
| achieved N at ×80 **< 2000** | 183 | **2.22** | **1.25** |
| achieved N at ×80 **≥ 2000** | 16 | **3.99** | **3.20** |

The registered bars were 3.0–5.0 and 1.5–4.0. The large designs land inside both;
the small ones do not, because a ~90 MB interpreter-and-numpy floor and a fixed
per-solve setup dominate anything with a few hundred segments. The O(N²) fill only
governs once N is big enough to matter.

The practical form of that, which is the useful half: **doubling the
density is cheaper than the asymptotic model suggests for most of the catalog.**
Median cold solve goes 0.106 s at ×40 to 0.205 s at ×80; the catalog total goes
60 s to 160 s; the worst single solve goes 5.4 s to 20.3 s. The ×160 rung costs
641 s in total and 102 s on its worst design.

### 30 rows cannot be adjudicated, and that is the yardstick's own result

Under #845's one-third rule, **30 razor rows are `reference unsettled`**: bs2
itself moved between ×80 and ×160 by more than a third of the error being judged,
so bs2 at rung 160 cannot arbitrate those designs. E4 predicted 10–40 and hit.
This is the answer to "is bs2 a usable yardstick" — **mostly, with 30 named
exceptions** — and it is a measured output rather than the assumption the original
D4 would have made.

12 further rows are `non-monotone`: the error does not fall cleanly across the four
rungs. 5 are refusals (razor has no buried fill), 2 are `not converging`, and 2 are
the skipped design.

### E1 missed, and most of the change is the metric, not the code

**33 rows changed class** against probe3's prediction (75.5 % strict agreement,
82.4 % excluding the 17 rows probe3 never measured; the bar was 90 %). Before
reading those as regressions, note what changed between the two measurements:

* probe3 used **port 0 alone**; this ladder uses an **all-port norm**. On a
  multi-port design those differ by up to the square root of the port count.
* probe3's reference was **bs2 at 4× (84 segments)**; this ladder's is **bs2 at
  160**, and the one-third rule is applied against that finer reference. A finer
  reference with a smaller own-movement changes which rows trip the rule.
* probe3 swept **1× / 2× / 4×**; this ladder is **21 / 40 / 80 / 160**.
* probe3 ran on a **2026-09-03** build.

The largest single group of changes — 8 rows moving `converging` →
`reference unsettled` — is what a stricter, differently-scaled application of the
one-third rule produces, not a code regression. Four rows moved the other way
(`reference unsettled` / `unexplained` → `converging`), and the helices in
particular now resolve. **I am not claiming which cause applies to which row**:
the appendix carries the achieved counts, ohms and percentages for all of them,
and separating metric from code would need probe3 re-run on current code with this
metric, which is a different job.

### F2 missed: a design's source changing is not its answer changing

F1 held exactly — all 1,680 cells are bit-identical to the pre-v0.79.0 ladder —
which confirms the reading that momwire's six commits touch only the EZNEC
printout shell and nothing on the solver path.

F2 predicted `verticals.buried_radial_vertical` would move, because v0.79.0
changed 21 lines of that design. **It did not move at all.** The change gives the
mast and feed-gap wires an explicit bare spec so they stop inheriting a jacket
from `build_wire_material()` — but at this design's *default* parameters
`wire_type` is `None` and `build_wire_material()` returns `None`, so there was no
jacket to inherit and the change is a no-op. It bites only the `-pvc` variants,
which the catalog does not solve at defaults.

The lesson is narrow and worth keeping: **"this design's source changed" does not
imply "this design's default answer changed."** A variant-only change moves
nothing at catalog defaults, and F2 was a guess dressed as an inference.

## 8. Reproducing

```
NEC5_EXE=<nec5cl-3b75639> python scratch/1525-razor-density/run_density.py \
  --out scratch/1525-razor-density/records.jsonl
python scratch/1525-razor-density/report.py > scratch/1525-razor-density/README.md
```

1,680 cells in 3,746 s. The staleness guard runs first and aborts before the first
cell if a gating check fails; its output is the records file's first line. The
NEC-5 binary is licensed (LLNL-CODE-746721), lives outside this repo and is run as
an executable; nothing here carries its source or printouts.
