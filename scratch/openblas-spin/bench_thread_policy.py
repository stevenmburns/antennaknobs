"""Thread-policy bench: OpenBLAS spin-wait, and physical vs logical cores.

Two questions, one harness, so that two machines produce comparable rows:

  1. Does ``OPENBLAS_THREAD_TIMEOUT=1`` (workers sleep instead of busy-waiting
     after a factorization) change solve latency?  See AK#1050.
  2. Does the optimal thread count sit at the physical-core count or the
     logical one, and does that answer depend on the engine or on the kernel
     path?  See AK#1051 and ``web/server.py:54-76``.

Run it the same way on every box; do not re-implement it locally, or the rows
stop being comparable::

    python bench_thread_policy.py --workload refl --nsegs 100,200,400 \
        --threads 4,8 --spin both --budget 8 > rows.jsonl

Output is one JSON object per (workload, N, threads, spin) cell on stdout, and
a single provenance object first.  Everything a reader needs to distrust a row
travels in the row.

PROTOCOL, and why it is this and not something simpler
------------------------------------------------------
Each cell is looped for a wall-time budget and scored on the MEDIAN OF THE
LAST HALF of its iterations.  The obvious alternative -- ``min`` of a few short
runs -- is wrong on any thermally-limited part: it selects the least-throttled
sample, so it measures how much turbo budget was left rather than how fast the
code is.  That is not hypothetical.  It produced a "2 threads beats 4 by 34%"
reading on a 15W i7-8550U that evaporated under this protocol, where iteration
time within a single 2-thread run degraded 60.5% as the package clock fell
3700 -> 2413 MHz.

So every row also carries its own thermal evidence: ``first_fifth_ms`` vs
``last_fifth_ms`` (their ratio is ``drift_pct``) and the per-core clock
sampled continuously across the cell.  On a quiet desktop drift is under 1%
and the row can be read at face value.  Where drift is large the row is
reporting a machine, not a code path, and should be read as such.

``OPENBLAS_THREAD_TIMEOUT`` must be set BEFORE the first OpenBLAS import --
each copy reads it at its own init, and there are three copies in this process
(numpy.libs, scipy.libs, pynec_accel.libs) plus system libgomp.  A late
``os.environ`` assignment silently does nothing, which is the same trap
``web/server.py``'s thread-policy block documents for its own env vars
(issue #377).  Rather than leave that to the caller, ``--spin`` re-executes
the interpreter with the right environment; ``_spin_state()`` records what was
actually in force so a row can never lie about it.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import threading
import time

# --- provenance -------------------------------------------------------------


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _core_counts() -> tuple[int | None, int]:
    """(physical, logical).  Physical is None when it cannot be determined."""
    logical = os.cpu_count() or 1
    try:
        import psutil

        return psutil.cpu_count(logical=False), logical
    except ImportError:
        pass
    try:
        cores, phys, coreid = set(), None, None
        with open("/proc/cpuinfo") as f:
            for line in f:
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                if key == "physical id":
                    phys = val
                elif key == "core id":
                    coreid = val
                elif not line.strip() and phys is not None and coreid is not None:
                    cores.add((phys, coreid))
                    phys, coreid = None, None
        if phys is not None and coreid is not None:
            cores.add((phys, coreid))
        if cores:
            return len(cores), logical
    except OSError:
        pass
    return None, logical


def _loadavg() -> list[float]:
    try:
        return list(os.getloadavg())
    except OSError:
        return []


def _spin_state() -> str:
    """What is ACTUALLY in force, not what the caller meant to ask for."""
    v = os.environ.get("OPENBLAS_THREAD_TIMEOUT")
    return "off" if v else "on"


def _pools() -> list[dict]:
    """Every thread pool the env vars have to reach.  Import the engines first
    so the pynec-bundled OpenBLAS is loaded and therefore visible."""
    import threadpoolctl

    return [
        {
            "user_api": p.get("user_api"),
            "internal_api": p.get("internal_api"),
            "num_threads": p.get("num_threads"),
            "lib": p.get("filepath", "").split("site-packages/")[-1],
        }
        for p in threadpoolctl.threadpool_info()
    ]


def provenance(args) -> dict:
    physical, logical = _core_counts()
    return {
        "kind": "provenance",
        "host": socket.gethostname(),
        "cpu": _cpu_model(),
        "cores_physical": physical,
        "cores_logical": logical,
        "loadavg": _loadavg(),
        "python": platform.python_version(),
        "spin": _spin_state(),
        "env": {
            k: os.environ.get(k)
            for k in (
                "OPENBLAS_THREAD_TIMEOUT",
                "OMP_WAIT_POLICY",
                "GOMP_SPINCOUNT",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
            )
        },
        "args": vars(args),
        "pools": _pools(),
        "versions": _versions(),
        "harness": _git_rev(),
        "topology": _topology(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _git_rev() -> dict:
    """Which commit produced this row.

    "Both boxes ran the same harness" is the premise of every cross-machine
    comparison here, and until this field existed nothing in a row backed it.
    A dirty tree is recorded rather than hidden: a locally-edited harness is
    exactly the thing that silently breaks comparability.
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        rev = subprocess.run(
            ["git", "-C", here, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        dirty = subprocess.run(
            ["git", "-C", here, "status", "--porcelain", "--", __file__],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if rev.returncode:
            return {"commit": None, "dirty": None}
        return {
            "commit": rev.stdout.strip()[:12],
            "dirty": bool(dirty.stdout.strip()),
        }
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def _topology() -> dict:
    """Per-core max frequency, so heterogeneous parts are visible.

    ``psutil.cpu_count(logical=False)`` returns P-cores + E-cores as ONE number
    on Alder Lake and later, over members with very different throughput. For a
    barrier-synchronised OpenMP fill the slowest thread gates the team, so a
    "physical core count" is not a meaningful policy input on such a part. This
    records the distinct max clocks: more than one value means the pin question
    is not the question we have been measuring.
    """
    try:
        import glob

        freqs = []
        for p in sorted(
            glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/cpuinfo_max_freq")
        ):
            with open(p) as fh:
                freqs.append(int(fh.read().strip()) // 1000)
        if not freqs:
            return {}
        distinct = sorted(set(freqs))
        return {
            "max_mhz_distinct": distinct,
            "heterogeneous": len(distinct) > 1,
            "cpus": len(freqs),
        }
    except (OSError, ValueError):
        return {}


def _versions() -> dict:
    out = {}
    for name in ("numpy", "scipy", "momwire", "antennaknobs"):
        try:
            import importlib.metadata as md

            out[name] = md.version(name)
        except Exception:  # noqa: BLE001 — provenance is best-effort; a missing
            # distribution must not abort a bench run
            out[name] = None
    try:
        from momwire import _accel

        out["momwire_accel_loaded"] = bool(_accel.LOADED)
    except Exception:  # noqa: BLE001 — same: record the failure, do not raise
        out["momwire_accel_loaded"] = None
    return out


# --- clock sampling ---------------------------------------------------------


class ClockSampler:
    """Per-core MHz across a cell, so a row carries its own turbo evidence."""

    def __init__(self, interval: float = 0.25) -> None:
        self.interval = interval
        self.samples: list[float] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _read(self) -> tuple[float, float] | None:
        """(busiest core MHz, mean across cores).

        The busiest core is the throttle indicator.  A mean over all cores
        conflates "the idle cores are parked at minimum clock" with "the
        working cores are being clocked down", and on a box running T threads
        of N logical CPUs the parked majority dominates that mean.
        """
        try:
            vals = []
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("cpu MHz"):
                        vals.append(float(line.split(":", 1)[1]))
            return (max(vals), statistics.mean(vals)) if vals else None
        except (OSError, ValueError):
            return None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            v = self._read()
            if v is not None:
                self.samples.append(v)

    def __enter__(self) -> ClockSampler:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def summary(self) -> dict:
        """Busiest-core clock over the cell.  ``busy_first_fifth`` vs
        ``busy_last_fifth`` is the turbo-window evidence: on a thermally
        limited part the second is materially lower."""
        if not self.samples:
            return {}
        busy = [s[0] for s in self.samples]
        allc = [s[1] for s in self.samples]
        n = len(busy)
        fifth = max(1, n // 5)
        return {
            "busy_mhz_mean": round(statistics.mean(busy)),
            "busy_mhz_min": round(min(busy)),
            "busy_mhz_max": round(max(busy)),
            "busy_first_fifth": round(statistics.mean(busy[:fifth])),
            "busy_last_fifth": round(statistics.mean(busy[-fifth:])),
            "all_core_mean": round(statistics.mean(allc)),
            "samples": n,
        }


# --- LU attribution ---------------------------------------------------------
#
# Both scipy.linalg.solve AND numpy.linalg.solve are wrapped: momwire's dense
# path calls the former (bspline.py:3480-3506) but the swept path batches
# through the latter (bspline.py:3525-3558).  Wrapping only one reports a fill
# fraction of ~100% by construction on whichever path it missed.  The wrap is
# an attribute swap on the module, which works because the call sites resolve
# the name at call time.
#
# It reaches the momwire engines only.  PyNEC factorizes in C via LAPACKE
# zgetrf, invisible from Python, so pynec rows report fill_frac = null rather
# than a number that would be wrong.

_LU = {"t": 0.0}


def _install_lu_probe() -> None:
    import numpy as np
    import scipy.linalg

    def wrap(mod, name):
        orig = getattr(mod, name)

        def timed(*a, **k):
            t0 = time.perf_counter()
            try:
                return orig(*a, **k)
            finally:
                _LU["t"] += time.perf_counter() - t0

        setattr(mod, name, timed)

    wrap(scipy.linalg, "solve")
    wrap(np.linalg, "solve")


# --- workloads --------------------------------------------------------------
#
# Each returns a callable timing ONE solve and returning (total_s, lu_s).
# Construction stays outside the timed region: it is not the phase under test.

SWEPT_FREQS = 9


def _k_array():
    import numpy as np

    return 2 * np.pi / np.linspace(18.0, 22.0, SWEPT_FREQS)


def _momwire(path: str, n: int):
    from momwire import BSplineSolver

    common = dict(nsegs=n, wire_radius=0.005, wavelength=20.0, feed_arclength=5.0)
    if path == "free":

        def go():
            s = BSplineSolver(wires=[[(0.0, 0.0, -5.0), (0.0, 0.0, 5.0)]], **common)
            _LU["t"] = 0.0
            t0 = time.perf_counter()
            s.compute_impedance()
            return time.perf_counter() - t0, _LU["t"]

        return go

    ground_model = {"refl": "refl-coef", "somm": "sommerfeld"}[path]
    k = _k_array()

    def go():
        s = BSplineSolver(
            wires=[[(-5.0, 0.0, 10.0), (5.0, 0.0, 10.0)]],
            ground_z=0.0,
            ground_eps=13.0,
            ground_model=ground_model,
            **common,
        )
        _LU["t"] = 0.0
        t0 = time.perf_counter()
        s.compute_impedance_swept(k)
        return time.perf_counter() - t0, _LU["t"]

    return go


def _pynec(deck: str, n: int):
    from antennaknobs.engines.pynec import PyNECEngine

    if deck == "yagi":
        from antennaknobs.designs.beams.yagi import Builder

        ground = "free"
    else:
        from antennaknobs.designs.verticals.four_square import Builder

        ground = ("finite-fast", 13.0, 0.005)

    def go():
        b = Builder()
        b.nominal_nsegs = n
        t0 = time.perf_counter()
        PyNECEngine(b, ground=ground).impedance()
        # LU is inside the C extension; not attributable from Python.
        return time.perf_counter() - t0, None

    return go


WORKLOADS = {
    "free": ("momwire", "free-space dipole, dense solve"),
    "refl": ("momwire", "swept ground, refl-coef, 9 freqs"),
    "somm": ("momwire", "swept ground, sommerfeld, 9 freqs"),
    "pynec-yagi": ("pynec", "yagi, free space"),
    "pynec-4sq": ("pynec", "four_square vertical array, finite-fast ground"),
}


def build(workload: str, n: int):
    if workload.startswith("pynec-"):
        return _pynec(workload.split("-", 1)[1], n)
    return _momwire(workload, n)


# --- the loop ---------------------------------------------------------------


def run_cell(go, threads: int, budget: float) -> dict:
    import threadpoolctl

    with threadpoolctl.threadpool_limits(limits=threads), ClockSampler() as clk:
        # Warm for a slice of the budget rather than a single call: at small
        # N one call leaves first_fifth cold-cache dominated, which surfaces
        # as large negative drift and masks the thermal signal drift is for.
        warm_until = max(0.5, budget / 8)
        warmed = 0.0
        while warmed < warm_until:
            warmed += go()[0]
        totals: list[float] = []
        lus: list[float] = []
        spent = 0.0
        while spent < budget:
            total, lu = go()
            totals.append(total)
            if lu is not None:
                lus.append(lu)
            spent += total

    half = max(1, len(totals) // 2)
    fifth = max(1, len(totals) // 5)
    steady = statistics.median(totals[-half:])
    first_fifth = statistics.mean(totals[:fifth])
    last_fifth = statistics.mean(totals[-fifth:])
    lu_ms = statistics.median(lus[-half:]) * 1000 if lus else None
    return {
        "threads": threads,
        "iters": len(totals),
        "steady_ms": steady * 1000,
        "first_fifth_ms": first_fifth * 1000,
        "last_fifth_ms": last_fifth * 1000,
        "drift_pct": (last_fifth / first_fifth - 1) * 100,
        "lu_ms": lu_ms,
        "fill_frac": None
        if lu_ms is None
        else (steady * 1000 - lu_ms) / (steady * 1000),
        "clock": clk.summary(),
    }


def run_paired(go, threads_a: int, threads_b: int, budget: float, block: int) -> dict:
    """Interleave two thread counts so both see the same thermal envelope.

    Why this exists: on a thermally limited part the dominant noise source is
    slow clock drift, which is COMMON MODE between measurements taken close
    together in time. Measuring all of A and then all of B puts minutes between
    the arms and lets that drift land entirely in the difference -- which is the
    quantity of interest. Measured that way on an xps13 the repeat spread was
    24-37% against a pin effect of 7-15%: ~39 repeats per cell to resolve, ~46
    hours for the matrix. Interleaving in short blocks makes the drift cancel in
    the RATIO instead of accumulating in it.

    The statistic is the median of per-pair ratios, not a ratio of medians. Each
    pair is self-contained, so a pair spanning a thermal excursion is one noisy
    sample rather than a shift of a whole arm.

    Blocks rather than single iterations because changing a pool's thread count
    is not free: OpenBLAS may tear down and respawn workers, which is itself
    entangled with the spin behaviour under test.
    """
    import threadpoolctl

    def block_median(threads: int) -> float:
        with threadpoolctl.threadpool_limits(limits=threads):
            return statistics.median([go()[0] for _ in range(block)])

    with ClockSampler() as clk:
        warm_until = max(0.5, budget / 8)
        warmed = 0.0
        while warmed < warm_until:
            warmed += go()[0]

        a_blocks: list[float] = []
        b_blocks: list[float] = []
        spent = 0.0
        while spent < budget:
            t0 = time.perf_counter()
            a_blocks.append(block_median(threads_a))
            b_blocks.append(block_median(threads_b))
            spent += time.perf_counter() - t0

    ratios = [b / a for a, b in zip(a_blocks, b_blocks, strict=False)]
    if not ratios:
        return {"kind": "paired", "pairs": 0, "clock": clk.summary()}
    ordered = sorted(ratios)
    med = statistics.median(ratios)
    return {
        "kind": "paired",
        "threads_a": threads_a,
        "threads_b": threads_b,
        "pairs": len(ratios),
        "block": block,
        "ratio_median": med,
        "ratio_pct": (med - 1) * 100,
        "ratio_spread_pct": (max(ratios) - min(ratios)) / med * 100,
        "ratio_p25": ordered[len(ordered) // 4],
        "ratio_p75": ordered[3 * len(ordered) // 4],
        "a_median_ms": statistics.median(a_blocks) * 1000,
        "b_median_ms": statistics.median(b_blocks) * 1000,
        "clock": clk.summary(),
    }


# --- spin re-exec -----------------------------------------------------------


def maybe_reexec(args) -> None:
    """Re-run under the right environment rather than trusting the caller.

    ``OPENBLAS_THREAD_TIMEOUT`` and the libgomp pair are read at library init,
    long before this module's body runs, so they cannot be set from here.  A
    re-exec is the only way this script can guarantee the environment its rows
    claim.  ``_AK_SPIN_SET`` marks the child so it does not recurse.
    """
    if os.environ.get("_AK_SPIN_SET"):
        return
    env = dict(os.environ)
    env["_AK_SPIN_SET"] = "1"
    env.setdefault("OMP_WAIT_POLICY", "PASSIVE")
    env.setdefault("GOMP_SPINCOUNT", "0")
    if args.spin == "off":
        env["OPENBLAS_THREAD_TIMEOUT"] = "1"
    else:
        env.pop("OPENBLAS_THREAD_TIMEOUT", None)
    raise SystemExit(subprocess.call([sys.executable, *sys.argv], env=env))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--workload", required=True, choices=sorted(WORKLOADS))
    p.add_argument("--nsegs", required=True, help="comma-separated, e.g. 100,200,400")
    p.add_argument("--threads", default="4,8", help="comma-separated thread counts")
    p.add_argument(
        "--spin",
        default="both",
        choices=("on", "off", "both"),
        help="OpenBLAS spin-wait: 'on' is the stock default, "
        "'off' sets OPENBLAS_THREAD_TIMEOUT=1",
    )
    p.add_argument("--budget", type=float, default=8.0, help="seconds per cell")
    p.add_argument(
        "--cooldown",
        type=float,
        default=0.0,
        help="seconds to park between the two halves of --spin both; use 60-120 "
        "on a thermally limited part so the second half does not inherit heat",
    )
    p.add_argument(
        "--spin-order",
        default="on-first",
        choices=("on-first", "off-first"),
        help="which half of --spin both runs first; alternate it across "
        "workloads so any residual thermal bias cancels",
    )
    p.add_argument(
        "--repeats", type=int, default=1, help="independent repeats per cell"
    )
    p.add_argument(
        "--paired",
        action="store_true",
        help="interleave the two --threads values in short blocks so both see "
        "the same thermal envelope; reports the median per-pair RATIO. Use on any "
        "box whose repeat spread is comparable to the effect being chased",
    )
    p.add_argument(
        "--pair-block",
        type=int,
        default=3,
        help="iterations per arm before switching, with --paired",
    )
    args = p.parse_args()

    if args.spin == "both":
        # Each half needs its own process: the variable is read at import.
        #
        # Order and cooldown are NOT cosmetic. Back-to-back halves hand the
        # second one a hotter machine, which is a systematic bias against
        # whichever spin state runs second -- and that is precisely the
        # comparison this script exists to make. Free on a quiet desktop,
        # decisive on a 15W part. --cooldown parks between halves and
        # --spin-order alternates which goes first, so residual bias cancels
        # across a matrix instead of accumulating in one direction.
        order = ("off", "on") if args.spin_order == "off-first" else ("on", "off")
        for k, spin in enumerate(order):
            if k and args.cooldown:
                time.sleep(args.cooldown)
            child = [*sys.argv]
            i = child.index("--spin")
            child[i + 1] = spin
            rc = subprocess.call([sys.executable, *child])
            if rc:
                raise SystemExit(rc)
        return

    maybe_reexec(args)

    _install_lu_probe()
    print(json.dumps(provenance(args)), flush=True)

    thread_list = [int(x) for x in args.threads.split(",")]
    if args.paired and len(thread_list) != 2:
        raise SystemExit(
            "--paired needs exactly two --threads values, e.g. --threads 4,8"
        )

    for n in [int(x) for x in args.nsegs.split(",")]:
        go = build(args.workload, n)
        if args.paired:
            for rep in range(args.repeats):
                row = run_paired(
                    go, thread_list[0], thread_list[1], args.budget, args.pair_block
                )
                row.update(
                    workload=args.workload,
                    engine=WORKLOADS[args.workload][0],
                    n=n,
                    spin=_spin_state(),
                    rep=rep,
                )
                print(json.dumps(row), flush=True)
            continue
        for threads in thread_list:
            for rep in range(args.repeats):
                row = run_cell(go, threads, args.budget)
                row.update(
                    kind="cell",
                    workload=args.workload,
                    engine=WORKLOADS[args.workload][0],
                    n=n,
                    spin=_spin_state(),
                    rep=rep,
                )
                print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
