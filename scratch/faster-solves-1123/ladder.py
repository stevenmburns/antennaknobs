"""Dense fill and factor time against segment count, with the mixed-precision
factor (momwire#2125, PR #2129, branch mixed-lu-all) beside the ordinary one.

One process per (engine, ground, N): a cold solve (pays the Sommerfeld table),
then an ordinary solve and a mixed_lu solve, each with a fresh engine, reuse
and symmetry off. Each row records momwire's own fill and factor times from the
fill report, and for the mixed row the change in `momwire._lapack.MIXED_SOLVES`
(refined / fallback / declined), so a row that did not run the mixed route says
so.

usage: ladder.py ENGINE GROUND(somm|free) N_PER_WIRE [DESIGN [PARAMS_JSON]]
"""

import json
import sys
import time
import warnings

import numpy as np

import antennaknobs.web.server  # noqa: F401  (resolves the adapter import cycle)
from antennaknobs.cli import resolve_class
from antennaknobs.web.adapter import _build_builder, _make_momwire_engine
from momwire import _lapack

GROUNDS = {
    "somm": {"ground": True, "ground_model": "sommerfeld"},
    "free": {"ground": False},
}


def solve(engine, ground, n, mixed, design="wire.longwire", params=None):
    req = {
        "geometry": design,
        "solver": "momwire",
        "momwire_model": engine,
        "model_options": {"pair_reuse": False, "mixed_lu": mixed},
        "n_per_wire": n,
        **GROUNDS[ground],
        **(params or {}),
    }
    builder = _build_builder(resolve_class(design), req)
    before = dict(_lapack.MIXED_SOLVES)
    before_fb = dict(_lapack.MIXED_FALLBACKS)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eng = _make_momwire_engine(req, builder)
        t0 = time.perf_counter()
        z = complex(np.asarray(eng.impedance(), dtype=complex).ravel()[0])
        wall = time.perf_counter() - t0
    rep = eng.fill_report() or {}
    sim = eng._solved_cache[1][0]
    per_edge = getattr(sim, "n_per_edge_per_wire", None)
    times = rep.get("times", {})
    return {
        "design": design,
        "engine": engine,
        "ground": ground,
        "n_per_wire": n,
        "segments": sum(sum(w) for w in per_edge) if per_edge else None,
        "mixed_asked": mixed,
        "mixed": {k: _lapack.MIXED_SOLVES[k] - before[k] for k in before},
        "fallbacks": {
            k: _lapack.MIXED_FALLBACKS[k] - before_fb[k]
            for k in before_fb
            if _lapack.MIXED_FALLBACKS[k] != before_fb[k]
        },
        "mixed_last": dict(_lapack.MIXED_LAST) if mixed else None,
        "route": rep.get("route"),
        "wall_s": wall,
        "fill_s": times.get("fill_s"),
        "factor_s": times.get("factor_s"),
        "z_re": z.real,
        "z_im": z.imag,
    }


def lapack_reference(n: int) -> dict:
    """Bare LAPACK LU of a random n x n matrix: zgetrf (complex128) against
    cgetrf (complex64), the factor alone with no refinement, so the graph has
    a single-precision factor line wherever momwire's route is not reached."""
    from scipy.linalg import lapack

    rng = np.random.default_rng(0)
    a = rng.standard_normal((n, n)) + 1j * rng.standard_normal((n, n))
    out = {"lapack_n": n}
    for name, fn, dt in (
        ("zgetrf_s", lapack.zgetrf, np.complex128),
        ("cgetrf_s", lapack.cgetrf, np.complex64),
    ):
        best = None
        for _ in range(2):
            m = np.asfortranarray(a, dtype=dt)
            t0 = time.perf_counter()
            fn(m, overwrite_a=True)
            dt_s = time.perf_counter() - t0
            best = dt_s if best is None else min(best, dt_s)
        out[name] = best
    return out


if __name__ == "__main__":
    engine, ground, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    design = sys.argv[4] if len(sys.argv) > 4 else "wire.longwire"
    params = json.loads(sys.argv[5]) if len(sys.argv) > 5 else {}
    solve(engine, ground, n, False, design, params)  # cold: tables, first-touch
    rows = [solve(engine, ground, n, m, design, params) for m in (False, True)]
    ref = lapack_reference(rows[0]["segments"])
    for row in rows:
        print(json.dumps({**row, **ref}, default=str), flush=True)
