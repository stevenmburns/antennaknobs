# Clean-room NEC-5 build 3b75639 — Skylake pinned-4 map against x13, 2026-09-13

Timing, statuses and exit codes only; no printouts, no binaries, no source. The
build is **dynamic**, `sha256 82272474cabafb960e2b695913017b329bef736af7aea9132e890f11b91d9297`,
1,280,552 bytes, distinct by hash from the five builds already on this box. It
ships unstripped with debug info — recorded as metadata; nothing inside it was
read. **No notes or report file arrived with the executable.**

## Conditions

The conditions `scratch/nec5-clean-d8e2147/README.md` names, so this map is
comparable with the published d8e2147 one: **`--jobs 1`, `OMP_NUM_THREADS=4` and
`OPENBLAS_NUM_THREADS=4`** (and `MKL_NUM_THREADS=4`), one deck at a time, 300 s
cap, over `~/nec5-timing/nec5` — the same translated tree `check-x13-t4.jsonl`
used, not the newer 1.11 tree. Box otherwise idle.

**Four passes, in opposite order: x13 → 3b75639 → 3b75639 → x13.** The two x13
passes bracket the run, so any monotone change in the machine lands on both builds
equally and the bracket's own spread is a measured number.

| pass | build | wall |
|---|---|---:|
| 1 | x13 | 2,326 s |
| 2 | 3b75639 | 1,187 s |
| 3 | 3b75639 | 1,188 s |
| 4 | x13 | 2,328 s |

**x13 bracket: 0.09 % apart. 3b75639 pair: 0.08 %.** Nothing needs flagging at the
top of the map.

## The pairing

`speedup-3b75639-vs-x13-t4.csv` is built from the **mean of each build's two
passes**, per deck (`merge_passes.py`), so all four passes carry into the answer
and neither round decides it alone. A deck whose status differed between a build's
two passes would be carried unaveraged and flagged; **none did**, on either build.

Computed from the two rounds separately instead, the median is 1.707 (round 1) and
1.703 (round 2) — 0.2 % apart, so the pairing does not decide the result either.

## The map

| | |
|---|---:|
| comparable decks | 1,243 of 3,076 |
| **median speedup** | **1.703** |
| p10 / p90 | 1.531 / 3.102 |
| min / max | 1.022 / 7.462 |
| total wall over comparable decks | 1,542 s → **655 s** |
| long decks (≥ 2 s) | **83 faster, 0 slower** |

Sub-floor band (1,702 decks under 50 ms on one side): median ratio 1.310. Those
are start-up, not solver, which is what the floor is for.

## Statuses: the stack-overflow fixes, and three decks the other way

| status | x13 | 3b75639 |
|---|---:|---:|
| `ok` | 2,946 | **2,989** |
| **`crash`** | **43** | **0** |
| `error` | 10 | 13 |
| `no-impedance` | 8 | 7 |
| `ok-no-source` | 67 | 66 |
| `timeout` | 2 | 1 |

**Every deck x13 crashes on now runs**, plus `4nec2-models/HFbeams/Bowtie.nec`
(`timeout` → `ok`): **44 recovered**. They are almost one family — 41 of the 43
crashes are under `g1ojs/Verticals/others/` (the `general 2-xx` optimiser sweep and
the bicone set), with two 2 m helices and
`nec-simulations/nec/wireAntennaPerfectGround.nec`.

Three go the other way, all three reporting `ERROR: ZGETRF - Singular matrix
CMA, KA= 1`:

| deck | x13 | 3b75639 |
|---|---|---|
| `necpp/plane.nec` | `ok-no-source` | `error` |
| `qantenna/airplane.nec` | `ok` | `error` |
| `necpp/patch_999_2.nec` | `no-impedance` | `error` |

The first two are the pre-existing unit-1 differences the 2461035 gate already
recorded against x13 (d8e2147 shows them too). The third is worth naming rather
than chasing: `patch_999_2` is one of the decks **AK#1430 refuses as invalid** for
listing the same wire twice, which makes the moment matrix singular — so a
singular-matrix error is the correct answer and x13's silent `no-impedance` was the
worse one. Full list in `status-differences.csv`.

## A claim withdrawn: this box does not drift

Two earlier reports of mine, including the merged #1458, say this box drifts 33 %
between sessions. **It does not, and this run is what settles it.** x13 in the
identical condition:

| pass | wall over the `ok` decks |
|---|---:|
| `check-x13-t4.jsonl`, 2026-09-11 | 1,541.2 s |
| pass 1, 2026-09-13 | 1,541.9 s |
| pass 4, 2026-09-13 | 1,543.8 s |

**0.17 % across three passes two days apart.** What I called drift was a condition
mismatch I mislabelled: the 852 s figure was d8e2147 at `--jobs 1 × OMP 4` and the
1,135 s figure was the same build at `--jobs 4 × OMP 1`, so the 1.33× between them
was the **thread count**, not the machine. The bracket was still the right thing to
run — it is what proved the box steady — but its stated justification was wrong.

The governor question that prompted the check: the box runs `powersave` under
`intel_pstate`, which is demand-driven, and all eight cores sit at **4.2 GHz**
under load. Pinning `performance` could not buy anything measurable at these
durations; it would only matter for decks under the 50 ms floor.

## Reproducing

```
bash scratch/nec5-clean-3b75639/run_pinned4_bracket.sh
python scratch/nec5-clean-3b75639/merge_passes.py check-x13-p1.jsonl check-x13-p4.jsonl check-x13-mean.jsonl
python scratch/nec5-clean-3b75639/merge_passes.py check-3b75639-p2.jsonl check-3b75639-p3.jsonl check-3b75639-mean.jsonl
python ~/nec5-timing/speedup_csv.py check-x13-mean.jsonl check-3b75639-mean.jsonl > speedup-3b75639-vs-x13-t4.csv
python scratch/nec5-clean-d8e2147/skylake_csv_to_plot.py speedup-3b75639-vs-x13-t4.csv ~/nec5-timing/nec5 plot-input-3b75639-vs-x13-t4.csv
python scratch/nec5-beta-a43/plot_runtime_vs_speedup.py plot-input-3b75639-vs-x13-t4.csv map.png \
    --old "x13 (reference)" --new "3b75639 (clean room)" \
    --title "NEC-5 corpus: 3b75639 against x13, 4 threads (jobs 1 x OMP 4), 2026-09-13"
```

PNGs are gitignored; the CSVs they are drawn from are committed.
