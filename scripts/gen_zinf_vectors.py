"""Regenerate the shared Z∞ test vectors (AK#1781).

    PYTHONPATH=src python scripts/gen_zinf_vectors.py

writes ``src/antennaknobs/web/frontend/src/__tests__/fixtures/zinfVectors.json``
from the PYTHON estimator (``antennaknobs.zinf.zinf_estimate``). pytest
(``tests/test_zinf_vectors_1781.py``) and vitest (``zinf.test.ts``) both
iterate that file, so a case added to ``CASES`` below gates both languages.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src/antennaknobs/web/frontend/src/__tests__/fixtures/zinfVectors.json"
COMMAND = "PYTHONPATH=src python scripts/gen_zinf_vectors.py"

HEN_X = [60, 116, 230, 460, 914, 1828, 3660]
BS_X = [59, 115, 231, 459, 915, 1829, 3661]
BRV_X = [103, 192, 367, 717, 1414, 2810]


def _synthetic(p, xs):
    zs = [complex(50, 10) + complex(3, -2) * x**-p for x in xs]
    return [z.real for z in zs], [z.imag for z in zs]


def _cases():
    doublings = [10, 20, 40, 80, 160, 320]
    cases = [
        # Real ladders quoted in AK#1781 (3-decimal prints).
        {
            "name": "hentenna razor-2p (R, X)",
            "x": HEN_X,
            "re": [42.905, 42.965, 43.027, 43.072, 43.095, 43.111, 43.121],
            "im": [46.449, 44.793, 42.232, 40.607, 39.746, 39.296, 39.072],
        },
        {
            "name": "hentenna razor-2p X only",
            "x": HEN_X,
            "re": [0.0] * 7,
            "im": [46.449, 44.793, 42.232, 40.607, 39.746, 39.296, 39.072],
        },
        {
            "name": "hentenna bspline (R, X)",
            "x": BS_X,
            "re": [43.040, 43.038, 43.085, 43.083, 43.102, 43.112, 43.119],
            "im": [38.754, 38.827, 38.883, 38.906, 38.915, 38.915, 38.915],
        },
        {
            "name": "hentenna bspline X only",
            "x": BS_X,
            "re": [0.0] * 7,
            "im": [38.754, 38.827, 38.883, 38.906, 38.915, 38.915, 38.915],
        },
        {
            "name": "BRV point-matched (R, X)",
            "x": BRV_X,
            "re": [84.374, 82.385, 80.984, 79.993, 79.289, 78.715],
            "im": [50.910, 49.475, 48.531, 47.873, 47.407, 47.024],
        },
        {
            "name": "BRV point-matched R only",
            "x": BRV_X,
            "re": [84.374, 82.385, 80.984, 79.993, 79.289, 78.715],
            "im": [0.0] * 6,
        },
    ]
    for p in (1.0, 2.0, 0.5):
        re, im = _synthetic(p, doublings)
        cases.append(
            {"name": f"synthetic exact p={p:g}", "x": doublings, "re": re, "im": im}
        )
    re, im = _synthetic(1.0, [8, 12, 17, 24, 34, 48, 68])
    cases.append(
        {
            "name": "synthetic p=1 on the app ladder (non-doubling)",
            "x": [8, 12, 17, 24, 34, 48, 68],
            "re": re,
            "im": im,
        }
    )
    re, im = _synthetic(1.0, [10, 20, 40])
    cases.append({"name": "three rungs (rough)", "x": [10, 20, 40], "re": re, "im": im})
    re, im = _synthetic(1.0, [1, 3, 9])
    cases.append(
        {"name": "ladder refine factors 1,3,9", "x": [1, 3, 9], "re": re, "im": im}
    )
    osc = [
        complex(50, 10) + (-1) ** k * complex(3, -2) / x
        for k, x in enumerate(doublings)
    ]
    cases.append(
        {
            "name": "oscillating",
            "x": doublings,
            "re": [z.real for z in osc],
            "im": [z.imag for z in osc],
        }
    )
    conv = [complex(50, 10) + complex(1e-9, 0) * k for k in range(5)]
    cases.append(
        {
            "name": "converged",
            "x": [10, 20, 40, 80, 160],
            "re": [z.real for z in conv],
            "im": [z.imag for z in conv],
        }
    )
    cases.append(
        {"name": "two rungs", "x": [10, 20], "re": [51.0, 50.5], "im": [9.0, 9.5]}
    )
    cases.append(
        {
            "name": "x not increasing",
            "x": [10, 20, 20, 40],
            "re": [53.0, 51.5, 51.4, 50.8],
            "im": [8.0, 9.0, 9.1, 9.5],
        }
    )
    return cases


def main():
    sys.path.insert(0, str(ROOT / "src"))
    from antennaknobs.zinf import zinf_estimate

    out = []
    for c in _cases():
        est = zinf_estimate(
            c["x"], [complex(r, i) for r, i in zip(c["re"], c["im"], strict=True)]
        )
        c = dict(c)
        c["expected"] = {
            "re": None if est.z_inf is None else est.z_inf.real,
            "im": None if est.z_inf is None else est.z_inf.imag,
            "p": est.p,
            "status": est.status,
        }
        out.append(c)
    doc = {
        "about": "Shared Z∞ estimator vectors (AK#1781); expected values come "
        "from the Python implementation, antennaknobs/zinf.py. Do not edit "
        "by hand: regenerate.",
        "generator": COMMAND,
        "cases": out,
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    for c in out:
        e = c["expected"]
        z = "—" if e["re"] is None else f"{e['re']:.4f}{e['im']:+.4f}j"
        p = "—" if e["p"] is None else f"{e['p']:.4f}"
        print(f"{c['name']:<48} {e['status']:<12} p={p:<8} Z∞={z}")


if __name__ == "__main__":
    main()
