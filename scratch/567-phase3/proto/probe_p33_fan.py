"""#567 phase 3, probe P3.3 — the fan BLIND TRANSFER (the kill test).

The ghost spelling exactly as P3.1 selected it on the lone deck — tau=1
(doctrine), decay k_m (anchor-selected), L=8.4 m (truncation-converged),
d2 ghost mesh (mesh-converged) — applied to the four-radial fan anchor
with NO refit of anything. Phase 0's scalar-weight axis died on exactly
this test (w*(lone) transferred blind made the fan WORSE than plain
drop); a real coupling mechanism must transfer.

Regression cell first: fan M-only must reproduce probe35's
105.2020-78.7769j. Then M+ghost vs the re-banked anchor 90.051-70.731j
(pre-ghost miss 17.155).

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/567-phase3/proto/probe_p33_fan.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scratch" / "524-phase2" / "proto"))
sys.path.insert(0, str(ROOT / "momwire" / "tests"))

from momwire import _crossing_fill, _medium_spec  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402,F401
from probe9_sense import capture  # noqa: E402
from probe_p31_ghost import LAM0, k_soil, seeded, wire_bases  # noqa: E402
from test_buried_serve_553 import fan_deck  # noqa: E402

ANCHOR = 90.051 - 70.731j
M_ONLY_BANK = 105.2020 - 78.7769j  # probe35, 2026-08-27

# The P3.1-selected ghost, verbatim (no refit anywhere below).
L, DENS = 8.4, 2
BREAKS = [0.15, 0.5, 1.2, 2.4, 4.2, 8.4]
N_PER = [DENS * n for n in [3, 4, 4, 4, 6, 8]]


def aux_deck():
    """The fan's below system (4 radials + hub junction, mesh-matched to
    the primary [10] per radial) plus the ghost. The ghost's one-member
    junction keeps its value-1 top tent (P3.1's first-run lesson)."""
    b = fan_deck()
    radials = [np.asarray(w) for w in b["wires"][1:]]
    ghost = [[0.0, 0.0, 0.0]] + [[0.0, 0.0, -z] for z in BREAKS]
    return dict(
        wires=radials + [np.asarray(ghost, dtype=float)],
        n_per_edge_per_wire=[[10]] * 4 + [N_PER],
        junctions=[
            [(0, "start"), (1, "start"), (2, "start"), (3, "start")],
            [(4, "start")],
        ],
        feeds=[(0, 2.5, 1 + 0j)],
        wavelength=LAM0,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=(13.0, 0.005),
        ground_model="sommerfeld",
    )


def main():
    km = k_soil()
    out = {}

    # ---- aux: harvest ghost x below-system coupling ----
    s_aux = seeded(aux_deck(), (_medium_spec.BELOW,) * 5)
    geom_aux = s_aux._build_geometry()
    aux_below = sorted(m for w in range(4) for m in wire_bases(s_aux, geom_aux, w))
    g_gho = wire_bases(s_aux, geom_aux, 4)
    off = geom_aux["seg_offsets"]
    gho_segs = np.arange(int(off[4]), int(off[5]))

    ax = _crossing_fill.axis_data(s_aux, geom_aux, gho_segs)
    z = ax["nodes"][:, 2]
    sqw = np.sqrt(ax["w"])
    A = (ax["F"][g_gho] * sqw).T
    b = np.exp(-1j * km * np.abs(z)) * sqw
    w_fit, *_ = np.linalg.lstsq(A, b, rcond=None)
    fit_rel = float(np.linalg.norm(A @ w_fit - b) / np.linalg.norm(b))
    g0 = complex(
        sum(
            w_fit[i] * fv[g_gho[i]]
            for pt, sign, fv in ax["ends"]
            if abs(pt[2]) < 1e-9
            for i in range(len(g_gho))
        )
    )
    t0 = time.time()
    st = capture(s_aux)
    Z_aux = st["Z"]
    row = w_fit @ Z_aux[np.ix_(g_gho, aux_below)]
    print(
        f"aux: fit_rel={fit_rel:.2e} g0={g0:.6f} "
        f"n_below={len(aux_below)} n_ghost={len(g_gho)} "
        f"({time.time() - t0:.0f}s)",
        flush=True,
    )
    out["aux diag"] = dict(fit_rel=fit_rel, g0=f"{g0:.6f}", n_below=len(aux_below))

    # ---- primary: fan M-only + the transferred ghost row ----
    build = fan_deck()
    media = (_medium_spec.ABOVE,) + (_medium_spec.BELOW,) * 4
    s = seeded(build, media)
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])
    ax_a = _crossing_fill.axis_data(s, geom, a_seg)
    ax_b = _crossing_fill.axis_data(s, geom, b_seg)
    t0 = time.time()
    t_ab = _crossing_fill.cross_complete_block(
        s, geom, dict(ax_a, ends=[]), dict(ax_b, ends=[])
    )
    print(f"fan M-only cross block built ({time.time() - t0:.0f}s)", flush=True)

    m0 = None
    for pt, sign, fv in ax_a["ends"]:
        if abs(pt[2]) < 1e-9:
            m0 = int(np.argmax(np.abs(fv)))
            assert abs(fv[m0] - 1.0) < 1e-9
    assert m0 is not None
    prim_below = sorted(m for w in range(1, 5) for m in wire_bases(s, geom, w))
    assert len(prim_below) == len(aux_below), (len(prim_below), len(aux_below))
    print(f"m0 = {m0}, below bases = {len(prim_below)}", flush=True)

    def solve(cell, hook=None):
        t0 = time.time()
        st = capture(
            seeded(fan_deck(), media),
            t_ab=t_ab,
            a_seg=a_seg,
            b_seg=b_seg,
            z_hook=hook,
        )
        zz = st["z_in"]
        miss = abs(zz - ANCHOR)
        print(
            f"  {cell:>18}: Z = {zz:9.4f}   miss = {miss:7.3f} ohm"
            f"   ({time.time() - t0:.0f}s)",
            flush=True,
        )
        out[cell] = dict(z=f"{zz:.4f}", miss_ohm=round(miss, 3))
        return zz

    z_m = solve("P3.3 fan M-only")
    drift = abs(z_m - M_ONLY_BANK)
    print(f"  drift vs probe35 bank: {drift:.4f} ohm", flush=True)
    out["fan M-only drift_vs_bank_ohm"] = round(drift, 4)
    print(f"  needed move: {ANCHOR - z_m:.4f}", flush=True)

    def hook(Z):
        Z[m0, prim_below] += row
        Z[prim_below, m0] += row
        return Z

    solve("P3.3 fan M+ghost", hook)

    fp = HERE.parent / "results" / "probe-p33-fan.json"
    fp.parent.mkdir(exist_ok=True)
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
