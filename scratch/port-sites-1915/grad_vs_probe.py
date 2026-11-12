"""Gradients against probes on the four-knob test design, and the gradient
check, on the port-sites path.

The design is `tests/test_optimize_port_sites_1915._CoilL` (invented): a
geometry knob, the coil's position as a percentage, the coil's inductance and
the station line's length. Prints each no-solve gradient's error against a
central difference of whole-wire rebuilds, then a run with the gradients and
one without (the same cache, every knob probed) at two budgets: wall time,
sweep calls, real solves (builds + rebuilds) and the final J.

    python scratch/port-sites-1915/grad_vs_probe.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import numpy as np
import test_port_sites_gradients_1915 as t
from test_optimize_port_sites_1915 import FREQS, PCTS, _builder

from antennaknobs import port_sites
from antennaknobs.band_opt import builder_sweep_fn
from antennaknobs.engines.momwire import MomwireEngine


def check():
    for pct in (PCTS[0], PCTS[1], PCTS[2], PCTS[3]):
        params = {**t.START, "coil_pct": pct}
        _s, sweep = t._session_at(params)
        dzs = sweep(params, FREQS, grad_knobs=params)["dzs"]
        errs = []
        for name, h in {
            "coil_pct": 1e-4,
            "coil_uh": 1e-5 * 4.7,
            "line_m": 1e-5 * 6.4,
        }.items():
            fd = (
                t._rebuild_z(**{**params, name: params[name] + h})
                - t._rebuild_z(**{**params, name: params[name] - h})
            ) / (2 * h)
            errs.append(f"{name} {np.max(np.abs(dzs[name] - fd) / np.abs(fd)):.2e}")
        print(
            f"  {pct:6.2f}%  "
            + "  ".join(errs)
            + f"  (no gradient for: {set(params) - set(dzs)})"
        )


def compare(evals):
    for label, grad in (("grads", True), ("probes", False)):
        s = port_sites.PortSitesSession()
        inner = builder_sweep_fn(_builder(), MomwireEngine, 50.0, port_sites=s)
        fn = inner if grad else (lambda req, freqs, inner=inner: inner(req, freqs))
        t0 = time.perf_counter()
        res = t._run(fn, max_evals=evals)
        wall = time.perf_counter() - t0
        c = s.counts
        print(
            f"  {label:6s} budget {evals:3d}  {wall:6.2f} s  sweep calls {res['n_solves']:3d}  "
            f"real solves {c['first'] + c['rebuild']:3d} (first {c['first']}, rebuild "
            f"{c['rebuild']})  J {res['objective_before']:.4f} -> {res['objective_after']:.6f}"
        )
        g = res.get("gradients")
        if g:
            print(f"         probes per gradient point {g['probes_per_point']}")


if __name__ == "__main__":
    print("gradient vs central difference of rebuilds (relative):")
    check()
    for evals in (40, 150):
        compare(evals)
