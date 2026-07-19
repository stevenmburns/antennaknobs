"""Session-shaped Sommerfeld benchmark: cold first solve + a band-locked sweep.

``bench_catalog.py`` is deliberately cold: one fresh interpreter per solve, one
frequency per design. That is the right harness for cold-solve cost and peak
RSS, but it is structurally blind to the momwire #159 work, whose whole point
is what happens on the SECOND and later solves of a session: the near/far grid
split (momwire PR #160) shows up only in the >4 lambda tail, and the
frequency-axis grid reuse (PR #162) does not show up at all.

This benchmark measures the session shape instead. Per (design, engine), one
worker process runs:

  1. a COLD first solve at the design's default frequency (grid fill included);
  2. a 21-point band-locked sweep (default +-1.5% around the default
     frequency — a realistic amateur-band width), fresh builder + engine per
     point exactly like a web knob-drag, module-level grid cache carrying
     whatever reuse momwire provides.

Reported per cell: cold ms, sweep total ms, number of Sommerfeld grid fills
during the sweep (momwire engines only — PyNEC rebuilds its SOMNEC table
internally every solve), and the median WARM tick (sweep points that filled no
grid; '-' if every point filled). The interesting cross-over: PyNEC pays its
~tens-of-ms Sommerfeld setup on every tick, momwire now pays per eps-ladder
rung — so momwire's warm tick can undercut PyNEC's steady state.

Fill counts depend on the band's fractional width (the Im-eps ladder is 1%):
a +-1.5% sweep lands ~3-4 fills, a single-channel sweep 1-2. That is expected
behavior, not noise — hence fills are printed next to the times.

Safety mirrors bench_catalog.py: per-worker RLIMIT_AS cap and a finite-ground
Sigma-seg guard whose default excludes only ``verticals.elt_whip`` (the 4392-seg
stress design) so nothing OOMs the box.

Usage:
    python scripts/bench_somm_sweep.py                        # full catalog
    python scripts/bench_somm_sweep.py --designs dipoles.invvee loops.quad
    python scripts/bench_somm_sweep.py --engines pynec bs2
    python scripts/bench_somm_sweep.py --out bench_out/somm_sweep.json
"""

from __future__ import annotations

# Mirror bench_nec_corpus.py: libgomp reads these once, before the scientific
# stack loads. Fresh worker subprocesses inherit them.
import os

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")

import argparse  # noqa: E402
import json  # noqa: E402
import resource  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_catalog as cat  # noqa: E402
import bench_converge as cvg  # noqa: E402
import bench_nec_corpus as bnc  # noqa: E402

ENGINES = ("pynec", "sin", "bs2")
ENGINE_LABEL = {"pynec": "PyNEC", "sin": "Sinusoidal", "bs2": "BSpline d=2"}

N_SWEEP = 21
SPAN_FRAC = 0.015  # +-1.5% band around the default frequency

# Same guards as bench_catalog: Sigma-seg cap excludes only elt_whip from the
# finite-ground solves; RLIMIT_AS keeps a runaway worker from OOMing the box.
DEFAULT_MAX_SEG = cat.DEFAULT_MAX_SEG_FINITE  # 2000
DEFAULT_MEM_GB = 12.0


def _solve_once(cls, engine, ground, freq=None):
    """One fresh builder + engine solve — the web knob-tick pattern."""
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver, SinusoidalSolver

    b = cls()
    if freq is not None:
        b.freq = freq
    if engine == "pynec":
        from antennaknobs.engines.pynec import PyNECEngine

        eng = PyNECEngine(b, ground=ground)
    elif engine == "sin":
        eng = MomwireEngine(b, solver=SinusoidalSolver, ground=ground)
    else:  # bs2
        eng = MomwireEngine(
            b, solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=ground
        )
    eng.impedance()


def worker_main(design, engine, ground_json, mem_gb):
    """Fresh interpreter: cold solve + band sweep; one JSON line to stdout."""
    result = {"error": None}
    try:
        if mem_gb and mem_gb > 0:
            cap = int(mem_gb * 1024**3)
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        bnc.apply_server_thread_policy()
        ground = json.loads(ground_json)
        if isinstance(ground, list):
            ground = tuple(ground)
        cls = cvg.load_design(design)

        # Count momwire grid fills (PyNEC's SOMNEC setup is internal to the
        # C++ engine — every solve pays it, nothing to count).
        fills = [0]
        try:
            from momwire import _sommerfeld as sm

            orig = sm.SommerfeldGrid.__init__

            def counting(self, *a, **kw):
                fills[0] += 1
                orig(self, *a, **kw)

            sm.SommerfeldGrid.__init__ = counting
        except ImportError:
            pass

        f0 = cls().freq

        t0 = time.perf_counter()
        _solve_once(cls, engine, ground)
        cold_s = time.perf_counter() - t0
        cold_fills = fills[0]

        ticks = []  # (seconds, fills_this_tick)
        for f in [
            f0 * (1.0 - SPAN_FRAC + 2.0 * SPAN_FRAC * i / (N_SWEEP - 1))
            for i in range(N_SWEEP)
        ]:
            before = fills[0]
            t0 = time.perf_counter()
            _solve_once(cls, engine, ground, freq=f)
            ticks.append((time.perf_counter() - t0, fills[0] - before))

        warm = [s for s, n in ticks if n == 0]
        result = {
            "error": None,
            "cold_s": cold_s,
            "cold_fills": cold_fills,
            "sweep_s": sum(s for s, _ in ticks),
            "sweep_fills": sum(n for _, n in ticks),
            "warm_tick_s": statistics.median(warm) if warm else None,
            "n_warm": len(warm),
        }
    except MemoryError:
        result["error"] = f"MemoryError: exceeded {mem_gb:g} GB cap"
        result["error_kind"] = "mem"
    except Exception as e:  # noqa: BLE001 — report, never crash the sweep
        import traceback

        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-800:]
    print(json.dumps(result))


def run_cell(design, engine, ground, timeout, mem_gb):
    try:
        proc = subprocess.run(
            [
                sys.executable,
                __file__,
                "--worker",
                design,
                engine,
                json.dumps(ground),
                str(mem_gb),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timeout > {timeout}s", "error_kind": "timeout"}
    if proc.returncode != 0 and not proc.stdout.strip():
        tail = (proc.stderr or "").strip()[-200:]
        kind = "mem" if proc.returncode in (-9, 137) else "err"
        return {"error": f"worker exited {proc.returncode}: {tail}", "error_kind": kind}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"error": f"unparseable worker output: {proc.stdout[-200:]!r}"}


def _cell_str(res):
    if not res or res.get("error"):
        kind = (res or {}).get("error_kind", "err")
        return (
            f"{'MEM' if kind == 'mem' else 'TIME' if kind == 'timeout' else 'ERR':>28}"
        )
    warm = res.get("warm_tick_s")
    warm_str = f"{warm * 1e3:6.1f}" if warm is not None else "     -"
    return (
        f"{res['cold_s'] * 1e3:7.0f} {res['sweep_s'] * 1e3:7.0f} "
        f"{res['sweep_fills']:2d} {warm_str}"
    )


def print_report(rows, engines):
    ok = [r for r in rows if r.get("engines")]
    print("\n" + "=" * 100)
    print("ROLLUP — median over designs, per engine")
    print("=" * 100)
    print(
        f"{'engine':<12} {'n':>3} {'cold':>9} {'sweep(21)':>10} "
        f"{'fills':>6} {'warm tick':>10}"
    )
    for e in engines:
        cells = [r["engines"][e] for r in ok if not r["engines"][e].get("error")]
        if not cells:
            print(f"{ENGINE_LABEL[e]:<12}   0  (no successful cells)")
            continue
        med = lambda k: statistics.median(c[k] for c in cells)  # noqa: E731
        warms = [c["warm_tick_s"] for c in cells if c["warm_tick_s"] is not None]
        print(
            f"{ENGINE_LABEL[e]:<12} {len(cells):>3} "
            f"{med('cold_s') * 1e3:>7.0f}ms {med('sweep_s') * 1e3:>8.0f}ms "
            f"{med('sweep_fills'):>6.0f} "
            f"{statistics.median(warms) * 1e3 if warms else float('nan'):>8.1f}ms"
        )

    # The cross-over: designs where a momwire warm tick beats PyNEC's tick.
    if "pynec" in engines:
        for e in [x for x in engines if x != "pynec"]:
            wins = total = 0
            for r in ok:
                p = r["engines"].get("pynec", {})
                m = r["engines"].get(e, {})
                if p.get("error") or m.get("error") or m.get("warm_tick_s") is None:
                    continue
                p_tick = p["sweep_s"] / N_SWEEP
                total += 1
                if m["warm_tick_s"] < p_tick:
                    wins += 1
            if total:
                print(
                    f"\nwarm-tick cross-over: {ENGINE_LABEL[e]} beats PyNEC's "
                    f"per-tick steady state on {wins}/{total} designs"
                )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--worker",
        nargs=4,
        metavar=("DESIGN", "ENGINE", "GROUND", "MEM_GB"),
        help=argparse.SUPPRESS,
    )
    ap.add_argument("--designs", nargs="+", default=None)
    ap.add_argument("--engines", nargs="+", default=list(ENGINES), choices=ENGINES)
    ap.add_argument(
        "--max-seg",
        type=int,
        default=DEFAULT_MAX_SEG,
        help=f"skip designs whose Sigma-seg exceeds this (default {DEFAULT_MAX_SEG}, "
        "which excludes only verticals.elt_whip; 0 = no cap)",
    )
    ap.add_argument(
        "--mem-gb",
        type=float,
        default=DEFAULT_MEM_GB,
        help=f"per-worker address-space cap in GB (default {DEFAULT_MEM_GB}; 0 = none)",
    )
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.worker:
        design, engine, ground, mem_gb = args.worker
        worker_main(design, engine, ground, float(mem_gb))
        return

    ground = cat.GROUNDS["somm"]
    designs = args.designs if args.designs is not None else cat.all_designs()
    cores = bnc.physical_cpu_count()
    print(
        f"Sommerfeld session benchmark   designs: {len(designs)}   "
        f"engines: {', '.join(ENGINE_LABEL[e] for e in args.engines)}"
    )
    print(
        f"per design: cold solve + {N_SWEEP}-pt band sweep (+-{SPAN_FRAC * 100:g}%)  "
        f"ground: {ground}"
    )
    print(
        f"Sigma-seg cap: {args.max_seg or 'none'}   mem cap: {args.mem_gb or 'none'} GB   "
        f"BLAS=OpenMP={cores}, serial dispatch"
    )
    print("-" * 100)
    hdr = " | ".join(f"{ENGINE_LABEL[e]:^28}" for e in args.engines)
    print(f"{'design':<38} | {hdr}")
    print(
        f"{'':<38} | "
        + " | ".join(f"{'cold  sweep21 fl  warm':^28}" for _ in args.engines)
    )

    rows = []
    for d in designs:
        try:
            seg = cvg.total_nominal_segs(cvg.load_design(d), cat.default_nseg(d))
        except Exception as e:  # noqa: BLE001
            rows.append({"design": d, "load_error": f"{type(e).__name__}: {e}"})
            print(f"{d:<38} | LOAD-ERR {e}")
            continue
        if args.max_seg and seg > args.max_seg:
            rows.append({"design": d, "skipped": f"Sigma-seg {seg} > {args.max_seg}"})
            print(f"{d:<38} | skipped (Sigma-seg {seg} > {args.max_seg})")
            continue
        row = {"design": d, "total_nominal_segs": seg, "engines": {}}
        for e in args.engines:
            row["engines"][e] = run_cell(d, e, ground, args.timeout, args.mem_gb)
        rows.append(row)
        print(
            f"{d:<38} | "
            + " | ".join(_cell_str(row["engines"][e]) for e in args.engines),
            flush=True,
        )

    print_report(rows, args.engines)
    if args.out:
        args.out.write_text(json.dumps(rows, indent=2))
        print(f"\nfull results -> {args.out}")


if __name__ == "__main__":
    main()
