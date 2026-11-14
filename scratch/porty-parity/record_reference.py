"""Record the pybind OpenNECEngine's answers over `cases.CASES`.

Writes tests/fixtures/opennec_porty_reference.json, which
tests/test_opennec_porty_parity.py holds the porty engine to. Also counts the
NEC runs (XQ cards) the old engine makes per reading, for the solve-count
comparison. Run from the worktree root with PYTHONPATH=src.
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
import old_engine  # noqa: E402

OUT = HERE.parents[1] / "tests" / "fixtures" / "opennec_porty_reference.json"


class _Counting:
    """A context proxy counting the NEC runs (XQ) and the frequencies each
    one solves (the FR card in force)."""

    def __init__(self, c, log):
        self._c, self._log, self._nf = c, log, 1

    def fr_card(self, ifrq, nfrq, f, df):
        self._nf = int(nfrq)
        return self._c.fr_card(ifrq, nfrq, f, df)

    def xq_card(self, i):
        self._log.append(self._nf)
        return self._c.xq_card(i)

    def __getattr__(self, name):
        return getattr(self._c, name)


def _r(x):
    """Twelve significant figures: the gates are 1e-6 and 1e-3 dB, and the
    engines agree to ~1e-10, so the last five digits only cost bytes."""
    return float(f"{float(x):.12g}")


def _cx(a):
    a = np.asarray(a, complex).ravel()
    return [[_r(v.real), _r(v.imag)] for v in a]


def record(mod, cid, design, ground, kwargs):
    log: list[int] = []
    real = mod._new_context
    mod._new_context = lambda: _Counting(real(), log)
    try:
        out = {"id": cid, "design": design, "ground": ground, "kwargs": kwargs}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t0 = time.perf_counter()
            eng = mod.OpenNECEngine(cases.builder(design), ground=ground, **kwargs)
            out["route"] = "reducer" if eng._use_reducer else "native"
            mark = len(log)
            z = eng.impedance()
            out["runs_impedance"] = log[mark:]
            mark = len(log)
            cur = eng.current_distribution()
            out["runs_currents"] = log[mark:]
            if cid not in cases.NO_PATTERN:
                mark = len(log)
                ff = eng.far_field(**cases.PATTERN)
                out["runs_far_field"] = log[mark:]
                out["gain"] = [[_r(g) for g in ring] for ring in ff.rings]
                out["max_gain"] = float(ff.max_gain)
                out["min_gain"] = float(ff.min_gain)
            out["seconds"] = time.perf_counter() - t0
            out["z"] = _cx(z)
            out["currents"] = _cx(
                np.concatenate([np.asarray(w.knot_currents) for w in cur])
            )
            out["efficiency"] = float(eng._excited_efficiency)
            out["p_in"] = float(eng._excited_p_in or 0.0)
            out["budget"] = [[str(k), float(w)] for k, w in eng._excited_power_budget]
            b2 = cases.builder(design)
            freqs = [s * b2.freq for s in cases.SWEEP_SPAN]
            mark = len(log)
            sweep = mod.OpenNECEngine(b2, ground=ground, **kwargs).impedance_sweep(
                np.asarray(freqs)
            )
            out["runs_sweep"] = log[mark:]
            out["sweep_freqs"] = freqs
            out["sweep"] = [_cx(row) for row in np.asarray(sweep, complex)]
        return out
    finally:
        mod._new_context = real


def main():
    mod = old_engine.load()
    rows = []
    for cid, design, ground, kwargs in cases.CASES:
        rows.append(record(mod, cid, design, ground, kwargs))
        r = rows[-1]
        print(cid, r["route"], len(r["z"]), f"{r['seconds']:.2f}s", flush=True)
    import pyopennec

    meta = {
        "engine": f"OpenNECEngine at {old_engine.OLD_COMMIT} (pybind nec_context)",
        "opennec": getattr(pyopennec, "OPENNEC_VERSION", "?"),
        "backend": getattr(pyopennec, "BACKEND", "?"),
        "pattern": cases.PATTERN,
    }
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    out.write_text(json.dumps({"meta": meta, "cases": rows}, indent=None) + "\n")
    print("wrote", out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
