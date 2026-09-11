# Clean-room NEC-5 build d8e2147 — Skylake gate, 2026-09-11

Timing and counters only; no printouts, no binaries, no source. All runs on the
Skylake box (4c/8t), `--jobs 1`, OMP_NUM_THREADS=4 and OPENBLAS_NUM_THREADS=4
pinned for every build compared ("unset" is not a configuration: two runtimes
default independently and the OpenMP builds nest BLAS inside parallel regions).

- `speedup-<new>-vs-<old>-t4.csv` — per deck: status under each build, wall
  seconds under each, ratio, and `comparable` (1 = both `ok` and both above the
  50 ms floor where the wall reading is mostly process start-up).
- `perf-rows-t1-t4.csv` — `perf stat` on three study decks at 1 and 4 threads
  for 63d0f93 and d8e2147: instructions, cycles, IPC, cache references/misses,
  misses per instruction. The binaries read the deck on stdin, so the rows were
  taken with run_set.sh's protocol, never `perf stat <binary> <deck>`.
- `skylake_csv_to_plot.py` — joins a speedup CSV with segment counts from the
  raw corpus tree into the columns `../nec5-beta-a43/plot_runtime_vs_speedup.py`
  reads (`--old` / `--new` name the builds on the axes).
- `heatmap-*-t4.png` — the three speedup-vs-runtime maps (PNGs are gitignored under scratch/; regenerate with the converter + plot script).

Headline: median speedup 1.617× vs the reference x13 (63d0f93: 1.514×), 1.087×
vs 63d0f93; study set 71 s / 21 s at 1 / 4 threads against 73 / 47 and 140 / 122.
Single-thread parity between the two SIMD builds is IPC-identical same work; the
four-thread gain is the old build's IPC collapsing (2.2→0.7) and the new one
holding it. Two decks (one wire-grid aircraft in two dialects) report a
singular matrix under d8e2147 only — under the clean room's review.
