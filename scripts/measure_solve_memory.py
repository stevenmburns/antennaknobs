#!/usr/bin/env python3
"""Measure a solve's peak memory (and time) vs segment count, per engine.

This is how the live-engine size caps in ``web/server.py`` were derived: the
caps bound a single solve's matrix memory so one oversized request can't OOM
the shared box. Re-run it when the deployment VM size changes to re-pick them.

Each N is measured in a *fresh subprocess* so ``ru_maxrss`` (peak RSS) reflects
that one solve, not the high-water mark of every prior solve in the loop. The
solve is called directly (not through the server), so the cap itself doesn't
reject the very runs we're trying to measure.

Usage:
    python scripts/measure_solve_memory.py <geometry> <engine> <N> [<N> ...]

    engine ∈ {sinusoidal, bspline, hmatrix, arrayblock, pynec}
    (retired names, e.g. "triangular", fall back to bspline)

Example:
    python scripts/measure_solve_memory.py arrays.bowtiearray2x4 arrayblock 21 41 81
    python scripts/measure_solve_memory.py arrays.bowtiearray2x4 pynec 21 41 81 121
"""

import resource
import subprocess
import sys
import time

_WORKER = "--worker"


def _measure_one(geometry: str, engine: str, n: int) -> None:
    """Worker: run one solve and print a result line. Run in its own process."""
    from antennaknobs.web.examples import REGISTRY

    ex = REGISTRY[geometry]
    use_pynec = engine == "pynec"
    req = {
        "geometry": geometry,
        "n_per_wire": n,
        "measurement_freq_mhz": 28.5,
        "design_freq_mhz": 28.5,
    }
    if use_pynec:
        req["solver"] = "pynec"
        solve = ex.pynec_solve
    else:
        req["momwire_model"] = engine
        solve = ex.momwire_solve

    # momwire-basis proxy (the count the caps use). NEC's own segment count is
    # close enough that PyNEC's RSS still tracks (basis**2 * 16) — see deploy.md.
    basis = ex.count_basis(req)
    rss_pre = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # MB
    t0 = time.perf_counter()
    out = solve(req)
    dt_ms = (time.perf_counter() - t0) * 1e3
    rss_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # MB
    dense_mb = (basis * basis * 16) / (1024 * 1024)
    print(
        f"N={n:4d}  basis~{basis:6d}  solve={dt_ms:9.0f} ms  "
        f"peak={rss_peak:7.0f} MB  delta={rss_peak - rss_pre:7.0f} MB  "
        f"dense_NxN~{dense_mb:7.0f} MB  "
        f"Z={out['z_in_re']:.0f}{out['z_in_im']:+.0f}j",
        flush=True,
    )


def main() -> None:
    if len(sys.argv) >= 5 and sys.argv[1] == _WORKER:
        _measure_one(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        return
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    geometry, engine, *ns = sys.argv[1:]
    print(f"# {geometry}  engine={engine}  (peak = total process RSS)")
    for n in ns:
        proc = subprocess.run(
            [sys.executable, __file__, _WORKER, geometry, engine, n],
            capture_output=True,
            text=True,
        )
        line = next(
            (ln for ln in proc.stdout.splitlines() if ln.startswith("N=")), None
        )
        print(line if line else f"N={n:>4}  FAILED\n{proc.stderr.strip()[-500:]}")


if __name__ == "__main__":
    main()
