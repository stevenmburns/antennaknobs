"""A-3 (#680) measurement round, probe 40 — where does a crossing solve
actually spend its time?

cProfiles the K=2 g1 adjudication solve (grids warm from this box's disk
cache) and reports the cumulative-time shares of the named layers:

  six_point / _adaptive_segment / _head   - the designed evaluator
  cross_complete_block / self_completions / axis_data - the crossing fill
  _field_galerkin_block / _build_J_blocks_subset / _image_Z_weighted -
     the standard buried fills
  get_grid_below / get_grid_below_above / _somm_grid - grid fills (warm?)

plus call counts for six_point (per-point cost) and the exact-duplicate
(rho_eff, z, zp) census on BOTH the K=2 and fan cross meshes (the
symmetry-dedup opportunity — no solve needed for the census).

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe40_accel_profile.py [profile|census ...]
"""

from __future__ import annotations

import cProfile
import io
import json
import pstats
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from momwire import _crossing_fill  # noqa: E402
from test_crossing_serve_524 import crossing_deck, fan_rise_deck  # noqa: E402

NAMED = [
    "six_point",
    "_adaptive_segment",
    "_head",
    "_ray_integral",
    "cross_complete_block",
    "self_completions",
    "axis_data",
    "radius_tables",
    "designed_tables",
    "_field_galerkin_block",
    "_build_J_blocks_subset",
    "_image_Z_weighted",
    "get_grid_below",
    "get_grid_below_above",
    "_somm_grid",
    "compute_impedance",
]


def run_profile(out):
    s = BSplineSolver(**crossing_deck(1))
    pr = cProfile.Profile()
    t0 = time.time()
    pr.enable()
    z, _ = s.compute_impedance()
    pr.disable()
    wall = time.time() - t0
    print(
        f"[profile] g1 K=2 solve Z = {z:.4f}  wall {wall:.0f}s "
        f"(cProfile overhead included)",
        flush=True,
    )

    st = pstats.Stats(pr)
    rows = {}
    for (fn_file, _line, fn_name), (cc, nc, tt, ct, _callers) in st.stats.items():
        if fn_name in NAMED:
            r = rows.setdefault(fn_name, dict(ncalls=0, tottime=0.0, cumtime=0.0))
            r["ncalls"] += nc
            r["tottime"] += tt
            # cumtime double-counts recursion; keep the max entry's ct
            r["cumtime"] = max(r["cumtime"], ct)
    for name in NAMED:
        if name in rows:
            r = rows[name]
            print(
                f"  {name:28s} ncalls {r['ncalls']:>9d}  tottime "
                f"{r['tottime']:8.1f}s  cumtime {r['cumtime']:8.1f}s",
                flush=True,
            )
    buf = io.StringIO()
    pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(25)
    (HERE.parent / "results" / "probe40-profile-g1.txt").write_text(buf.getvalue())
    out["g1-profile"] = dict(
        wall_s=round(wall, 1),
        z=f"{z:.4f}",
        named={
            k: {
                kk: round(vv, 2) if isinstance(vv, float) else vv
                for kk, vv in v.items()
            }
            for k, v in rows.items()
        },
    )
    if "six_point" in rows:
        sp = rows["six_point"]
        out["g1-profile"]["ms_per_point"] = round(
            1000.0 * sp["cumtime"] / max(sp["ncalls"], 1), 3
        )
        print(
            f"  -> six_point {sp['ncalls']} calls, "
            f"{out['g1-profile']['ms_per_point']} ms/point "
            f"(cumtime share {100 * sp['cumtime'] / wall:.0f}% of wall)",
            flush=True,
        )


def _cross_mesh_census(build, tag, out):
    """The exact-duplicate (rho_eff, z, zp) census on the cross mesh —
    the symmetry-dedup ceiling, computed without solving."""
    s = BSplineSolver(**build)
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    A = _crossing_fill.axis_data(s, geom, a_idx)
    B = _crossing_fill.axis_data(s, geom, b_idx)
    gz = float(s.ground_z)
    a_w = float(s._radius_per_wire[0])
    dx = A["nodes"][:, 0][:, None] - B["nodes"][:, 0][None, :]
    dy = A["nodes"][:, 1][:, None] - B["nodes"][:, 1][None, :]
    rho_eff = np.hypot(np.hypot(dx, dy), a_w)
    z = np.broadcast_to((A["nodes"][:, 2] - gz)[:, None], rho_eff.shape)
    zp = np.broadcast_to((B["nodes"][:, 2] - gz)[None, :], rho_eff.shape)
    triples = np.stack([rho_eff.ravel(), z.ravel(), zp.ravel()], axis=1)
    n_total = triples.shape[0]
    n_unique = np.unique(triples, axis=0).shape[0]
    print(
        f"[census] {tag}: nA {len(A['nodes'])} x nB {len(B['nodes'])} = "
        f"{n_total} pairs, {n_unique} unique exact triples "
        f"({n_total / n_unique:.2f}x duplication)",
        flush=True,
    )
    out[f"census-{tag}"] = dict(
        nA=len(A["nodes"]),
        nB=len(B["nodes"]),
        pairs=int(n_total),
        unique=int(n_unique),
        dup_factor=round(n_total / n_unique, 2),
    )


def run_census(out):
    _cross_mesh_census(crossing_deck(1), "g1-k2", out)
    _cross_mesh_census(fan_rise_deck(), "fan-n4", out)


def _unique_triples(build):
    """The unique exact (rho_eff, z, zp) list of a deck's cross mesh —
    exactly what the U1 memo hands the C++ batch."""
    s = BSplineSolver(**build)
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    A = _crossing_fill.axis_data(s, geom, a_idx)
    B = _crossing_fill.axis_data(s, geom, b_idx)
    gz = float(s.ground_z)
    a_w = float(s._radius_per_wire[0])
    dx = A["nodes"][:, 0][:, None] - B["nodes"][:, 0][None, :]
    dy = A["nodes"][:, 1][:, None] - B["nodes"][:, 1][None, :]
    rho_eff = np.hypot(np.hypot(dx, dy), a_w)
    z = np.broadcast_to((A["nodes"][:, 2] - gz)[:, None], rho_eff.shape)
    zp = np.broadcast_to((B["nodes"][:, 2] - gz)[None, :], rho_eff.shape)
    triples = np.stack([rho_eff.ravel(), z.ravel(), zp.ravel()], axis=1)
    return np.unique(triples, axis=0), s


def run_accel(out):
    """U2's speed proof: the C++ twin on the g1 cross mesh's unique
    triples (parallel batch + a serial per-point sample), the numpy walk
    on the same sample as the baseline, and the g1 K=2 + fan soil-A
    solve walls through the accel path."""
    from momwire import _near_interface as ni

    assert ni._HAVE_NEAR_INTERFACE_ACCEL and ni._use_near_interface_accel(), (
        "accel not built/routed — the Python fallback would silently "
        "masquerade as the twin (the stale-.so lesson)"
    )
    tri, s = _unique_triples(crossing_deck(1))
    eps_t, _eps_m, k_p, k_m, _c2, _a_m = s._buried_medium()
    args = (
        float(k_p),
        complex(k_m),
        np.ascontiguousarray(tri[:, 0]),
        np.ascontiguousarray(tri[:, 1]),
        np.ascontiguousarray(tri[:, 2]),
        1e-10,
        ni._LAM_MULT,
        ni._ADAPT_DEPTH,
        ni._DETOUR,
        ni._GX,
        ni._GW,
    )
    ni._nia.near_interface_six_batch(*args)  # warm (thread pool, pages)
    t0 = time.time()
    vals = ni._nia.near_interface_six_batch(*args)
    t_par = time.time() - t0
    n = tri.shape[0]

    rng = np.random.default_rng(680)
    sample = tri[rng.choice(n, size=min(64, n), replace=False)]
    t0 = time.time()
    for r, zz, zp in sample:
        ni._nia.near_interface_six_batch(
            float(k_p),
            complex(k_m),
            np.array([r]),
            np.array([zz]),
            np.array([zp]),
            1e-10,
            ni._LAM_MULT,
            ni._ADAPT_DEPTH,
            ni._DETOUR,
            ni._GX,
            ni._GW,
        )
    t_ser = time.time() - t0
    t0 = time.time()
    for r, zz, zp in sample:
        ni.six_point(eps_t, k_p, r, zz, zp)
    t_py = time.time() - t0
    ms_par = 1000.0 * t_par / n
    ms_ser = 1000.0 * t_ser / len(sample)
    ms_py = 1000.0 * t_py / len(sample)
    print(
        f"[accel] g1-k2 unique triples n={n}: batch {t_par:.2f}s "
        f"({ms_par:.3f} ms/pt parallel), serial sample {ms_ser:.3f} ms/pt, "
        f"numpy walk {ms_py:.2f} ms/pt ({ms_py / ms_ser:.0f}x serial)",
        flush=True,
    )
    out["accel-microbench"] = dict(
        n_unique=int(n),
        batch_s=round(t_par, 3),
        ms_per_point_parallel=round(ms_par, 4),
        ms_per_point_serial=round(ms_ser, 4),
        ms_per_point_numpy=round(ms_py, 3),
        speedup_serial=round(ms_py / ms_ser, 1),
        sample=len(sample),
    )
    del vals

    for tag, build in (("g1-k2", crossing_deck(1)), ("fan-n4", fan_rise_deck())):
        sv = BSplineSolver(**build)
        t0 = time.time()
        z, _ = sv.compute_impedance()
        wall = time.time() - t0
        print(f"[accel] {tag} solve Z = {z:.4f}  wall {wall:.1f}s", flush=True)
        out[f"accel-solve-{tag}"] = dict(wall_s=round(wall, 1), z=f"{z:.4f}")


def main():
    fp = HERE.parent / "results" / "probe40-accel-profile.json"
    out = json.loads(fp.read_text()) if fp.exists() else {}
    for name in sys.argv[1:] or ["census", "profile"]:
        {"profile": run_profile, "census": run_census, "accel": run_accel}[name](out)
        fp.write_text(json.dumps(out, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
