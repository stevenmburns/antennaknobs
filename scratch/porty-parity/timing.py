"""Old (pybind, one NEC run per port per reading) vs new (porty, one solve)
on network designs: a fresh engine, impedance() then the default 1-degree
far_field(), best of 3. Also the NEC runs / porty solves each made."""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases  # noqa: E402
import old_engine  # noqa: E402
import record_reference  # noqa: E402

from antennaknobs.engines.opennec import OpenNECEngine  # noqa: E402

DESIGNS = [
    ("verticals.tri_moxon", "free"),
    ("wire.efhw_autotransformer", "free"),
    ("verticals.tri_moxon", ("finite", 13.0, 0.005)),
    ("broadband.lpda", "free"),
]


def run(cls, design, ground):
    """(total, impedance-only, eng): build + impedance, then the pattern."""
    t0 = time.perf_counter()
    eng = cls(cases.builder(design), ground=ground)
    eng.impedance()
    t1 = time.perf_counter()
    eng.far_field()
    return time.perf_counter() - t0, t1 - t0, eng


def main():
    old = old_engine.load()
    warnings.simplefilter("ignore")
    for design, ground in DESIGNS:
        b = cases.builder(design)
        log: list[int] = []
        real = old._new_context
        old._new_context = lambda: record_reference._Counting(real(), log)
        olds = [run(old.OpenNECEngine, design, ground) for _ in range(3)]
        old._new_context = real
        runs_old = len(log) // 3
        t_old, z_old = min(t for t, _z, _e in olds), min(z for _t, z, _e in olds)
        best = [run(OpenNECEngine, design, ground) for _ in range(3)]
        t_new, z_new = min(t for t, _z, _e in best), min(z for _t, z, _e in best)
        eng = best[0][2]
        nseg = sum(w[1] for w in eng._deck.wires)
        print(
            f"{design:28s} {str(ground):28s} seg {nseg:4d} ports "
            f"{len(eng._real_port_names)} (porty {len(eng._port_segs)}) "
            f"old {t_old * 1e3:7.1f} ms / {runs_old} NEC runs   "
            f"new {t_new * 1e3:7.1f} ms / {len(eng.solve_log)} solve   "
            f"x{t_old / t_new:.1f}  | impedance only: old {z_old * 1e3:.1f} ms, "
            f"new {z_new * 1e3:.1f} ms, x{z_old / z_new:.1f}  f={b.freq}",
            flush=True,
        )


if __name__ == "__main__":
    main()
