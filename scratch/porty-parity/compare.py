"""The porty OpenNECEngine against the recorded pybind references.

Prints, per case, the worst relative Z error (impedance and sweep), the worst
current error relative to the largest current, the worst gain error (dB)
over the whole recorded grid and on max/min gain, and the solve log.
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases  # noqa: E402

from antennaknobs.engines.opennec import OpenNECEngine  # noqa: E402

REF = HERE.parents[1] / "tests" / "fixtures" / "opennec_porty_reference.json"


def _c(rows):
    a = np.asarray(rows, float)
    return a[..., 0] + 1j * a[..., 1]


def main(only=None):
    ref = json.loads(REF.read_text())
    worst = {"z": 0.0, "i": 0.0, "g": 0.0}
    for r in ref["cases"]:
        if only and r["id"] not in only:
            continue
        ground = tuple(r["ground"]) if isinstance(r["ground"], list) else r["ground"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t0 = time.perf_counter()
            eng = OpenNECEngine(
                cases.builder(r["design"]), ground=ground, **r["kwargs"]
            )
            z = np.asarray(eng.impedance(), complex).ravel()
            cur = eng.current_distribution()
            dg = dmm = float("nan")
            if "gain" in r:
                ff = eng.far_field(**cases.PATTERN)
                g = np.asarray(ff.rings, float)
                g0 = np.asarray(r["gain"], float)
                dg = float(np.max(np.abs(g - g0)))
                dmm = max(
                    abs(ff.max_gain - r["max_gain"]), abs(ff.min_gain - r["min_gain"])
                )
            secs = time.perf_counter() - t0
            log = list(eng.solve_log)
            e2 = OpenNECEngine(cases.builder(r["design"]), ground=ground, **r["kwargs"])
            sw = np.asarray(e2.impedance_sweep(np.asarray(r["sweep_freqs"])), complex)
            log2 = list(e2.solve_log)
        z0 = _c(r["z"])
        dz = float(np.max(np.abs(z - z0) / np.abs(z0)))
        s0 = _c(r["sweep"]).reshape(sw.shape)
        dzs = float(np.max(np.abs(sw - s0) / np.abs(s0)))
        i = np.concatenate([np.asarray(w.knot_currents) for w in cur])
        i0 = _c(r["currents"])
        di = float(np.max(np.abs(i - i0)) / np.max(np.abs(i0)))
        de = abs(eng._excited_efficiency - r["efficiency"])
        dp = abs((eng._excited_p_in or 0.0) - r["p_in"]) / max(abs(r["p_in"]), 1e-300)
        print(
            f"{r['id']:32s} {r['route']:7s} dZ {max(dz, dzs):.2e} dI {di:.2e} "
            f"dG {dg:.2e} dGmm {dmm:.2e} deff {de:.1e} dPin {dp:.1e} "
            f"t {secs:.2f}s (old {r['seconds']:.2f}s) solves {[len(x) for x in log]} "
            f"sweep {[len(x) for x in log2]}",
            flush=True,
        )
        worst["z"] = max(worst["z"], dz, dzs)
        worst["i"] = max(worst["i"], di)
        if dg == dg:
            worst["g"] = max(worst["g"], dg, dmm)
    print("worst", worst)


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
