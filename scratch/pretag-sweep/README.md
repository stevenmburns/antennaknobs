# Pre-tag performance sweep

This is a release step for momwire. Before tagging, run the whole catalog, plus a set of stress decks, on the candidate. Compare the result against the stored baseline from the previous release.

It was added on 2026-09-24, after momwire#1189 shipped a 7 GiB memory spike on a 48-radial surface screen that no per-PR gate exercised.

## What it runs

`cases.json` lists 643 cases. They cover every catalog design plus the named decks in `decks/` and the #1131 raw screen, over free space, finite-fast and Sommerfeld ground, on the default engine and on razor-2p.

Each case is one cold `impedance()` call in a fresh process. It records:
- the outcome (ok, refused, error, oom, timeout, killed);
- peak RSS;
- Z;
- solve wall time.

## The release-path run: `driver.py fast`, ~12 min on Skylake

```
cd ~/stevenmburns/sweep/harness        # the Skylake copy of this directory
python3 driver.py fast --python ~/stevenmburns/antennaknobs/.venv/bin/python \
    --tree ../mw-<candidate> --ak-src ../ak-src --cases cases.json \
    --out fast-<version>.jsonl --arm <version> --jobs 8 --order-by <baseline>.jsonl
python3 analyze.py <baseline>.jsonl fast-<version>.jsonl
```

- **Parallel tier:** every case not listed in `timed.txt`, 8 at a time, each with one BLAS/OpenMP thread. The whole batch waits for one idle check at the start. This tier records outcome, peak RSS and Z (2.1 min).
- **Timed tier:** the cases in `timed.txt`, one at a time, 4 threads each, each waiting for the box to go idle. Only these cases have their wall time compared (10.0 min).
- Every row carries a `mode` field (`par1` or `timed`). `analyze.py` compares memory and wall time only between rows of the same mode, because a process's peak RSS depends on its thread count. It compares Z and outcome across all rows.

**Validation (2026-09-24):** v0.63.0 run in this mode on Skylake against the serial run on Haswell:
- 643 of 643 cases, 0 outcome changes;
- Z compared on all 625 both-ok cases, largest difference 6.5e-12.

The serial run took about 2.3 h. Most of that was the per-case idle gate: about 26 min of waiting for the load average to fall, plus about 43 min spent in the gate's own 2 s CPU samples. The processes themselves took 18 min.

## Baselines

`results/fast-v0.63.0.jsonl` is the current baseline, v0.63.0 run in `fast` mode on Skylake. Each release's candidate run becomes the next baseline.

- **Compare on the same machine as the baseline.** Wall time only means something within one machine. Use `--cross-machine` otherwise, which flags wall only above 2×.
- **Keep `--ak-src` fixed** between the baseline and the candidate. The sweep compares momwire trees; a change in antennaknobs moves outcomes on its own. After an antennaknobs change that matters, re-run the baseline with the new ak-src.
- **Keep `timed.txt` fixed across releases**, so that both runs time the same cases. Add to it deliberately.

## Reading the flags

| flag | fires when | what to do |
|---|---|---|
| OUTCOME | a case was ok and now isn't | a regression: fix it before the tag |
| MEM | peak RSS grew more than 10 % and more than 30 MB (same mode) | attribute it to a PR, or fix it |
| TIME | a timed case's wall grew more than 10 % and more than 0.5 s | re-time with `driver.py run --only ...` on the same box |
| Z | Z moved more than 1e-6 relative | expected only from a PR that says so |

Other scripts:
- `driver.py run` is the old serial mode. It remains for re-timing with `--only`.
- `driver.py plan` regenerates `cases.json` from the catalog.
