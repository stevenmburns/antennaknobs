"""Measure the two speed switches through the app's own engine path.

Each run builds the request the workbench sends (`_build_builder` +
`_make_momwire_engine` with the option in `model_options`), solves once with a
fresh engine (no cache), and records the wall time of `impedance()`, momwire's
own fill / factor / census times and the fill report's route and reuse state
(`eng.fill_report()`, the payload the Fill view reads).

usage: measure.py CASE SWITCH(off|on) REPEATS [N_PER_WIRE]
One JSON line per run on stdout.
"""

import json
import sys
import time
import warnings

import numpy as np

import antennaknobs.web.server  # noqa: F401  (resolves the adapter import cycle)
from antennaknobs.cli import resolve_class
from antennaknobs.web.adapter import _build_builder, _make_momwire_engine

# name -> (design, backend, option key, request extras, builder params)
SOMM = {"ground": True, "ground_model": "sommerfeld"}
FREE = {"ground": False}


def _case(design, backend, option, ground, n, params=None):
    return (design, backend, option, {**ground, "n_per_wire": n}, params or {})


# name -> (design, backend, option key, request extras, builder params).
# n_per_wire is the workbench's segments knob; the counts it gives are
# recorded per row ("segments").
CASES = {}
for _b, _tag in (("bs2", "bs2"), ("sinusoidal", "sin"), ("razor2p", "razor")):
    # The stock vertical at its slider's maximum, 16 elevated radials.
    CASES[f"vertical16_sector_{_tag}"] = _case(
        "verticals.vertical", _b, "rotational_symmetry", SOMM, 150, {"n_radials": 16}
    )
    CASES[f"vertical16_reuse_{_tag}"] = _case(
        "verticals.vertical", _b, "pair_reuse", SOMM, 150, {"n_radials": 16}
    )
    # A long uniform wire (3.5 wavelengths at 7 m).
    CASES[f"longwire_reuse_{_tag}"] = _case(
        "wire.longwire", _b, "pair_reuse", SOMM, 180
    )
    CASES[f"longwire_free_reuse_{_tag}"] = _case(
        "wire.longwire", _b, "pair_reuse", FREE, 180
    )
    # A 10-element Yagi: the stock yagi at 8 directors.
    CASES[f"yagi10_reuse_{_tag}"] = _case(
        "beams.yagi", _b, "pair_reuse", SOMM, 120, {"n_directors": 8}
    )
    CASES[f"yagi10_free_reuse_{_tag}"] = _case(
        "beams.yagi", _b, "pair_reuse", FREE, 120, {"n_directors": 8}
    )
    # The same Yagi with every element on one core (uniform_cores).
    CASES[f"yagi10uc_reuse_{_tag}"] = _case(
        "beams.yagi", _b, "pair_reuse", SOMM, 120,
        {"n_directors": 8, "uniform_cores": True},
    )  # fmt: skip
    CASES[f"yagi10uc_free_reuse_{_tag}"] = _case(
        "beams.yagi", _b, "pair_reuse", FREE, 120,
        {"n_directors": 8, "uniform_cores": True},
    )  # fmt: skip


def run(case: str, on: bool) -> dict:
    design, backend, key, extras, params = CASES[case]
    cls = resolve_class(design)
    req = {
        "geometry": design,
        "solver": "momwire",
        "momwire_model": backend,
        "model_options": {key: on},
        **extras,
        **params,
    }
    builder = _build_builder(cls, req)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eng = _make_momwire_engine(req, builder)
        t0 = time.perf_counter()
        z = complex(np.asarray(eng.impedance(), dtype=complex).ravel()[0])
        wall = time.perf_counter() - t0
    rep = eng.fill_report() or {}
    sim = eng._solved_cache[1][0]
    per_edge = getattr(sim, "n_per_edge_per_wire", None)
    nseg = sum(sum(w) for w in per_edge) if per_edge else None
    reuse = rep.get("reuse") or {}
    sector = rep.get("sector") or {}
    return {
        "case": case,
        "design": design,
        "backend": backend,
        "option": key,
        "on": on,
        "params": params,
        "extras": extras,
        "segments": nseg,
        "wall_s": wall,
        "fill_s": rep.get("times", {}).get("fill_s"),
        "factor_s": rep.get("times", {}).get("factor_s"),
        "census_s": rep.get("times", {}).get("census_s"),
        "route": rep.get("route"),
        "solver": rep.get("solver"),
        "reuse_asked": rep.get("reuse_asked"),
        "reuse_state": reuse.get("state"),
        "reuse_declined": reuse.get("declined"),
        "pairs": reuse.get("pairs"),
        "computed": reuse.get("computed"),
        "reused": reuse.get("reused"),
        "near": reuse.get("near"),
        "uncounted": reuse.get("uncounted"),
        "families": reuse.get("families"),
        "sector": {
            k: sector.get(k)
            for k in ("n_sectors", "axial", "computed_pairs", "pairs", "declined")
        }
        if sector
        else None,
        "z_re": z.real,
        "z_im": z.imag,
    }


if __name__ == "__main__":
    case, sw, reps = sys.argv[1], sys.argv[2] == "on", int(sys.argv[3])
    if len(sys.argv) > 4:  # n_per_wire override, for sizing probes
        CASES[case][3]["n_per_wire"] = int(sys.argv[4])
    for rep in range(reps):
        row = run(case, sw)
        row["rep"] = rep  # rep 0 is the cold solve; the tables use 1..
        print(json.dumps(row, default=str), flush=True)
