"""A-2 session 6, probe 33 — adjudicator 2 (momwire side): the complete
spelling along the sigma ladder. As sigma -> inf the stub becomes a
perfect stake and the contact fiction becomes exact, so BOTH conventions
must converge: momwire-complete crossing must approach momwire's shipped
mono (Delta -> 0), the way engine crossing -> engine mono does
(probe32: -2.82-1.69j -> -0.17-0.09j at sigma 5).

Per-medium grades resolve the soil decay length; the designed corner
tables carry the medium explicitly. Corner sign = +c1*V(a) (the
soil-A-calibrated structural sign, NOT re-picked per medium).

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe33_highsigma_momwire.py [tags...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

import corner_tables as ct  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from momwire._sommerfeld_transmitted import _c1_moment  # noqa: E402
from probe1_baseline import seeded  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402
from probe25_node_cell import cross_pieces_on_axes, graded_axis_data  # noqa: E402
from probe27_complete import self_complete_hook  # noqa: E402
from test_buried_serve_553 import WL7  # noqa: E402

A_WIRE = 0.001
ct.install(wire_radius=A_WIRE)

# The shipped transmitted plan's z' ladder reaches 0.25 lambda_m only
# (lambda_m = 2 pi / |k_m|); at sigma >= 0.05 a 2 m stub is out of scope.
# The stub is therefore SHORTENED per medium to ~0.9x the ladder limit —
# still >= ~1 decay length, and the ENGINE is re-run on the IDENTICAL
# short-stub decks so the Delta comparison is deck-matched.
#
# tag -> (eps_r, sigma, stub_len, engine_nb, below grading, above grading)
LADDER = {
    "sig0.05": (
        13.0,
        0.05,
        0.84,
        24,
        ([-0.84, -0.3, -0.1], [3, 2, 2]),
        ([0.1, 0.5, 10.0], [2, 2, 19]),
    ),
    "sig0.5": (
        13.0,
        0.5,
        0.27,
        16,
        ([-0.27, -0.1, -0.03], [3, 2, 2]),
        ([0.03, 0.5, 10.0], [3, 2, 19]),
    ),
    "sig5": (
        13.0,
        5.0,
        0.085,
        10,
        ([-0.085, -0.03, -0.01], [3, 2, 2]),
        ([0.01, 0.1, 0.5, 10.0], [2, 3, 2, 19]),
    ),
}

NA_ENGINE = 75  # x5 above mesh, feed = seg 33 (center 4.333 m)


def engine_deltas(tag):
    """Run the engine on the SAME short-stub geometry (capture-cached)."""
    from antennaknobs.engines.nec5 import NEC5Engine

    sys.path.insert(0, str(Path.home() / "antennas/antennaknobs/scripts"))
    from bench_nec5_walk_why import make_dipole

    eps_r, sigma, stub, nb, _below, _above = LADDER[tag]
    cap = HERE.parent / "results" / "probe32-nec5-cap"
    eng = NEC5Engine(make_dipole(20), ground=None, capture_dir=cap)
    mono = (
        "CM probe33 mono\nCE\n"
        f"GW 1,{NA_ENGINE},0.,0.,0.,0.,0.,10.,.001\n"
        "GE 1,-1\nFR 0,1,0,0,7.\n"
        f"GN 0,0,0,0,{eps_r},{sigma}\n"
        "EX 4,1,33,0,1.,0.\nPQ 0\nXQ 0\nEN\n"
    )
    crossing = (
        "CM probe33 crossing short stub\nCE\n"
        f"GW 1,{nb},0.,0.,{-stub},0.,0.,0.,.001\n"
        f"GW 2,{NA_ENGINE},0.,0.,0.,0.,0.,10.,.001\n"
        "GE 1,-1\nFR 0,1,0,0,7.\n"
        f"GN 0,0,0,0,{eps_r},{sigma}\n"
        "EX 4,2,33,0,1.,0.\nPQ 0\nXQ 0\nEN\n"
    )
    zm = complex(NEC5Engine._parse_input_parameters(eng._run(mono))[0][0][2])
    zc = complex(NEC5Engine._parse_input_parameters(eng._run(crossing))[0][0][2])
    return zm, zc


def crossing_deck(tag):
    eps_r, sigma, _stub, _nb, below, above = LADDER[tag]
    below_pts = np.array([(0.0, 0.0, z) for z in below[0] + [0.0]])
    above_pts = np.array([(0.0, 0.0, z) for z in [0.0] + above[0]])
    return dict(
        wires=[below_pts, above_pts],
        n_per_edge_per_wire=[below[1], above[1]],
        junctions=[[(0, "end"), (1, "start")]],
        feeds=[(1, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=A_WIRE,
        ground_z=0.0,
        ground_eps=(eps_r, sigma),
        ground_model="sommerfeld",
    )


def mono_deck(tag):
    eps_r, sigma, _stub, _nb, _below, above = LADDER[tag]
    pts = np.array([(0.0, 0.0, z) for z in [0.0] + above[0]])
    return dict(
        wires=[pts],
        n_per_edge_per_wire=[above[1]],
        feeds=[(0, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=A_WIRE,
        ground_z=0.0,
        ground_eps=(eps_r, sigma),
        ground_model="sommerfeld",
    )


def corner_sanity(s):
    """Cheap probe21c-style pin at this medium: s*U -> 1, s*k^2*V*(1+e)/2
    -> 1 at small s, rho = 0."""
    eps_t, _em, k_p, _km, _c2, _am = s._buried_medium()
    sv = 1e-4
    six = ct.six_point(eps_t, k_p, 0.0, 0.0, -sv, rtol=1e-9)
    u_err = abs(sv * six[0] - 1.0)
    v_err = abs(sv * k_p * k_p * six[1] * (1.0 + eps_t) / 2.0 - 1.0)
    print(
        f"  corner sanity at eps_t={eps_t:.1f}: |s*U-1| = {u_err:.2e}, "
        f"|s*k2V*(1+e)/2-1| = {v_err:.2e}",
        flush=True,
    )
    assert u_err < 1e-2 and v_err < 1e-2


def cross_complete_med(s, tag):
    fp = HERE.parent / "results" / f"probe33-blocks-{tag}.npz"
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    if fp.exists():
        d = np.load(fp)
        pieces = {k: d[k] for k in ("M", "SW", "SQ", "BT")}
    else:
        axA = graded_axis_data(s, geom, a_idx)
        axB = graded_axis_data(s, geom, b_idx)
        t0 = time.time()
        M, SW, SQ, BT = cross_pieces_on_axes(s, axA, axB)
        print(
            f"  {tag}: designed graded cross pieces {time.time() - t0:.0f}s", flush=True
        )
        pieces = dict(M=M, SW=SW, SQ=SQ, BT=BT)
        np.savez(fp, **pieces)
    eps_t, _em, k_p, _km, _c2, _am = s._buried_medium()
    nb, na = node_indices(s, geom)
    c1 = _c1_moment(s.omega, s.mu)
    v_corner = complex(ct.six_point(eps_t, k_p, A_WIRE, 0.0, 0.0, rtol=1e-10)[1])
    corner = c1 * v_corner  # structural sign from the soil-A calibration
    print(f"  {tag}: corner c1*V(a) = {corner:.4f}", flush=True)
    CORNER = np.zeros_like(pieces["M"])
    CORNER[na, nb] = corner
    t_A = pieces["M"] + pieces["SW"] + pieces["SQ"] + pieces["BT"] + CORNER
    return t_A


def cfmt(z):
    return f"{z.real:+.4f}{z.imag:+.4f}j"


def main():
    tags = sys.argv[1:] or ["sig0.05", "sig0.5", "sig5"]
    out = {}
    for tag in tags:
        print(f"\n== {tag} ==", flush=True)
        s = seeded(crossing_deck(tag))
        geom = s._build_geometry()
        below = s._below_segments(geom)
        b_seg = np.sort(np.nonzero(below)[0])
        a_seg = np.sort(np.nonzero(~below)[0])
        h_min = float(geom["h_per_seg"].min())
        print(
            f"  {int(below.sum())} below / {int((~below).sum())} above, "
            f"h_node = {h_min:.4f} m",
            flush=True,
        )
        corner_sanity(s)

        t0 = time.time()
        z_mono = capture(BSplineSolver(**mono_deck(tag)))["z_in"]
        print(
            f"  mono (shipped serve) = {cfmt(z_mono)} ({time.time() - t0:.0f}s)",
            flush=True,
        )

        t_A = cross_complete_med(s, tag)
        d_self = self_complete_hook(s, geom)

        def corr_hook(Zp, add=d_self):
            return Zp + add

        t0 = time.time()
        st = capture(
            seeded(crossing_deck(tag)),
            t_ab=t_A,
            a_seg=a_seg,
            b_seg=b_seg,
            z_hook=corr_hook,
        )
        z = st["z_in"]
        d = z - z_mono
        em, ec = engine_deltas(tag)
        print(f"  complete+split crossing = {cfmt(z)} ({time.time() - t0:.0f}s)")
        print(
            f"  momwire Delta = {cfmt(d)}   engine Delta = {cfmt(ec - em)}"
            f"   (matched short-stub decks)"
        )
        print(f"  [engine mono {cfmt(em)}  crossing {cfmt(ec)}]", flush=True)
        out[tag] = dict(
            stub_len=LADDER[tag][2],
            mono=str(z_mono),
            crossing=str(z),
            delta=str(d),
            engine_mono=str(em),
            engine_crossing=str(ec),
            engine_delta=str(ec - em),
        )

        fp = HERE.parent / "results" / "probe33-highsigma-momwire.json"
        old = json.loads(fp.read_text()) if fp.exists() else {}
        old.update(out)
        fp.write_text(json.dumps(old, indent=1))
    print(f"\nsaved {fp}")


if __name__ == "__main__":
    main()
