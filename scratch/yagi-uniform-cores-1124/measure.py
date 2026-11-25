"""The Yagi before and after uniform cores, through the app's engine path.

The 10-element Yagi (beams.yagi, 8 directors) at the workbench's segments
knob n_per_wire = 120, once with the default layout and once with
``uniform_cores``, each with pair reuse off and on. Each run is a fresh
engine (no cache), as measure.py in scratch/faster-solves-1123 does, and
records the wall time of ``impedance()``, momwire's fill / factor / census
times and the fill report's reuse counts.

usage: measure.py ENGINE GROUND(free|sommerfeld) UNIFORM(0|1) REUSE(off|on) REPEATS
One JSON line per run on stdout; rep 0 is the cold solve.
"""

import json
import sys
import time
import warnings

import numpy as np

import antennaknobs.web.server  # noqa: F401  (resolves the adapter import cycle)
from antennaknobs.cli import resolve_class
from antennaknobs.web.adapter import _build_builder, _make_momwire_engine


def run(engine, ground, uniform, reuse):
    g = (
        {"ground": False}
        if ground == "free"
        else {"ground": True, "ground_model": ground}
    )
    req = {
        "geometry": "beams.yagi",
        "solver": "momwire",
        "momwire_model": engine,
        "model_options": {"pair_reuse": reuse},
        "n_per_wire": 120,
        "n_directors": 8,
        "uniform_cores": uniform,
        **g,
    }
    builder = _build_builder(resolve_class("beams.yagi"), req)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eng = _make_momwire_engine(req, builder)
        t0 = time.perf_counter()
        z = complex(np.asarray(eng.impedance(), dtype=complex).ravel()[0])
        wall = time.perf_counter() - t0
    rep = eng.fill_report() or {}
    sim = eng._solved_cache[1][0]
    per_edge = getattr(sim, "n_per_edge_per_wire", None)
    r = rep.get("reuse") or {}
    t = rep.get("times") or {}
    return {
        "engine": engine,
        "ground": ground,
        "uniform": uniform,
        "reuse": reuse,
        "segments": sum(sum(w) for w in per_edge) if per_edge else None,
        "wall_s": wall,
        "fill_s": t.get("fill_s"),
        "factor_s": t.get("factor_s"),
        "census_s": t.get("census_s"),
        "reuse_state": r.get("state"),
        "reuse_declined": r.get("declined"),
        "pairs": r.get("pairs"),
        "computed": r.get("computed"),
        "near": r.get("near"),
        "z_re": z.real,
        "z_im": z.imag,
    }


if __name__ == "__main__":
    engine, ground = sys.argv[1], sys.argv[2]
    uniform, reuse = sys.argv[3] == "1", sys.argv[4] == "on"
    for i in range(int(sys.argv[5])):
        row = run(engine, ground, uniform, reuse)
        row["rep"] = i
        print(json.dumps(row, default=str), flush=True)
