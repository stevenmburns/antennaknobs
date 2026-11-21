# The W8IO ELT whip on momwire's NEC-2 launcher: 0.95.1 against 0.96.0

**The question.** momwire 0.96.0 shipped the first part of the NEC-2 speed arc: the sinusoidal fill fused and tiled (momwire#2069, #2070 by #2080), the remainder source cache (#2073 by #2077), and NEC-2's interaction approximation as an opt-in (`nec2_far_approx`, #2085). How much of that reaches a whole deck run through the drop-in launcher, and where does the remaining time go?

**The answer, measured.** On default settings the whole run is **11 % faster** (14.16 → 12.56 s), from a fill that is **34 % faster** per frequency (422 → 277 ms). With `pair_reuse` the gain is small (11.21 → 10.96 s), because reuse had already removed most of the fill. The LU factor did not move (about 585 ms per frequency) and is now **about 7.6 s of a 12.6 s run**: it is the next cost to attack (momwire#2071, the copy before the factor on the launcher's path). `nec2_far_approx` does **not** run on the launcher: its reach is level 1 (the hosted app, Python on Linux avx2) and the drop-in route is level 4, so the launcher refuses it by name.

**This is a Linux diagnostic, not a benchmark entry.** Every number here is from one Linux desktop. The W8IO comparison page lists Windows runs, and Linux and Windows have ranked these engines differently before, so nothing here is comparable with that page's entries or should be quoted beside them.

**The builds.**

* momwire 0.95.1 and 0.96.0, each installed from PyPI into its own Python 3.12 venv, run through the `momwire-nec2c-sinusoidal` console script (the Python drop-in, not a standalone executable). Default settings, plus `MOMWIRE_X_PAIR_REUSE=1` for the reuse rows. Both versions run the NEC-2 free-end cap by default on this route.
* nec2++ from python-necpp's accelerated build with our fill-pair reuse branch (`nec2++-accel-reuse-62dacd4`), `PYNEC_FILL_REUSE=0` / `1`.
* Machine: Intel i7-11700K (8 cores, 16 threads), Linux 7.0, idle (load 0.0 before the run). `MOMWIRE_THREADS`, `OMP_NUM_THREADS` and `OPENBLAS_NUM_THREADS` all 8.

**The deck.** W8IO's ELT whip on a 96-inch rounded ground plane, `whip_antenna_8ft_groundplane.nec` from the W8IO benchmark page: 434 `GW` wires, 4,392 segments, free space, `FR` 13 frequencies at 400–412 MHz, `EX 0` at 1,1, and an `RP` elevation cut. Wires of two radii meet at a junction, so every momwire run prints a `RadiusStepJunction` advisory on stderr; it does not stop the run.

## Whole-run wall time

Three repeats, the configurations interleaved in each repeat, wall clock around the process:

| run | 0.95.1 | 0.96.0 | change |
|---|---|---|---|
| momwire, default | 14.16 s (14.04, 14.16, 14.50) | **12.56 s** (11.93, 12.56, 12.66) | −11 % |
| momwire + `pair_reuse` | 11.21 s (10.84, 11.25, 11.21) | **10.96 s** (10.70, 10.96, 11.01) | −2 % |
| nec2++, fill reuse off | | 12.84 s (12.33, 12.84, 12.84) | |
| nec2++, fill reuse on | | 9.85 s (9.37, 9.85, 9.85) | |

Medians, with the three runs in brackets. On default settings momwire 0.96.0 is now level with plain nec2++ (12.56 against 12.84 s); with both programs' reuse on, momwire is 11 % behind (10.96 against 9.85 s).

## Where the time goes

From the `MATRIX TIMING` lines of each printout, the mean over the 13 frequencies:

| run | fill / freq | factor / freq | fill, whole run | factor, whole run |
|---|---|---|---|---|
| 0.95.1 default | 422 ms | 582 ms | 5.48 s | 7.57 s |
| 0.95.1 + `pair_reuse` | 178 ms | 577 ms | 2.31 s | 7.50 s |
| 0.96.0 default | 277 ms | 589 ms | 3.60 s | 7.65 s |
| 0.96.0 + `pair_reuse` | 157 ms | 585 ms | 2.04 s | 7.60 s |

The factor is the same in all four, so the whole-run gain is the fill's. nec2++ prints its `MATRIX TIMING` in CPU time summed over threads (its fill and factor sum to more than the wall time), so its lines are not comparable with momwire's and are left out.

## `nec2_far_approx` on this route

Run with `MOMWIRE_X_NEC2_FAR_APPROX=1`, 0.96.0's launcher stops before solving (0.39 s, exit 0) and prints:

```
ERROR: nec2_far_approx is not certified for the dropin route on linux (support level 4, dropin-linux-windows; it reaches level 1, ak-linux-avx2); unset MOMWIRE_X_NEC2_FAR_APPROX to run without it
```

That is the feature system working as designed, not a defect. 0.95.1 predates the switch and ignores the variable, so its "far approx" runs were default runs and are not reported. The approximation's own measurements (fill-only, on whips of 1,400–4,400 segments: 0.52–0.68 of the exact fill's time, nec2c's printed digits reproduced) are in momwire#2085.

The standalone executable does not carry it either: the C++ kernel (`_sinusoidal_far_core.cpp`) is reached only from Python, and the `nec2c_sin` build does not compile it in.

**Measured on the Python route instead.** On this machine, Python with the avx2 accelerator is level 1, where the feature is certified. A driver parses the deck with `parse_nec2`, then for each of the 13 frequencies calls `build_solver(model, basis="sinusoidal", frequency_mhz=f)` and `compute_impedance()`, with the end cap on. Same threads, three repeats interleaved:

| run | wall | per frequency | \|ΔZ\|/\|Z\| against exact |
|---|---|---|---|
| exact | 11.23 s (11.17–11.38) | 861 ms | — |
| `nec2_far_approx` | 11.69 s (11.58–11.80) | 896 ms | 3.0e-5 at 400 MHz, 1.6e-5 at 412 |
| exact + `pair_reuse` | 9.86 s (9.82–10.24) | 755 ms | 7e-14 |
| `nec2_far_approx` + `pair_reuse` | 9.94 s (9.83–10.15) | 762 ms | 3.0e-5 |

On the whip the approximation is **4 % slower**, not faster. The cause is in `sinusoidal.py`: with it on, the fused fill from #2080 declines (the far pairs are lumped inside the field tensor, which the fused pass does not call), so the fill takes the two-pass route that the fusion replaced. #2085's 0.52–0.68 was measured against the unfused fill. Putting the lumping inside the fused kernel is what would turn it into a gain; that is an estimate, not a measurement.

Two caveats on this table. `compute_impedance()` on the bare solver leaves out the deck's two `LD` loads (a series 90 nH and a series 3 pF), so its impedances are the unloaded whip's (1.33 + j33.21 Ω at 400 MHz, against the launcher's loaded 61.26 − j1.54 Ω); the loads touch only the small reduction over the port rows, not the 4,392-segment fill and factor timed here. And this route factors Z in place, which is why it is 1.3 s faster than the launcher's 12.56 s: that difference is, mostly, momwire#2071's copy.

## What this leaves

* **momwire#2071** (open), the largest exact item: the Python route's in-place factor runs the same deck about 1.3 s faster than the launcher (above). `compute_port_solution`, the launcher's path, copies Z to Fortran order and takes its 1-norm before the LU; `compute_impedance` already factors in place. The fused fill (#2080) can write either order, so the remaining work is an in-place `_lapack.solve` and a threaded in-place 1-norm. Its share of the 585 ms factor line is not separated by these printouts; measure it before and after.
* The no-Python NEC-2 executable (`momwire-nec2c-sinusoidal` standalone, momwire#2078) is built and gated in momwire's `linux-nec2c` CI job but is not attached to any release yet, so it is not in this comparison.

## Rerun

On the benchmark box, with the deck at `$D`:

```
for v in 0.95.1 0.96.0; do python3.12 -m venv v$v && v$v/bin/pip install "momwire==$v"; done
export MOMWIRE_THREADS=8 OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8
time v0.96.0/bin/momwire-nec2c-sinusoidal < $D > out.txt
time env MOMWIRE_X_PAIR_REUSE=1 v0.96.0/bin/momwire-nec2c-sinusoidal < $D > out.txt
grep -A1 "MATRIX TIMING" out.txt
```

Each run gets its own `XDG_CACHE_HOME` and `MOMWIRE_SOMM_CACHE_DIR` per version, so one version's caches never serve the other.
