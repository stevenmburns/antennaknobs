"""Dissect the sinusoidal lane's loop residual: which channel, which nodes.

The assembled collocation matrix is G = Phi_const @ M_A + Phi_sin @ M_B +
Phi_cos @ M_C — three additive shape channels. A channel-masked subclass
zeroes chosen coefficients after `_basis_coefs`, so w^T G_channel alpha
decomposes the measured loop-circulation residual additively.

Geometries:
  * isolated regular n-gon loops (square / octagon / 16-gon), equal
    perimeter 320 m, equal segment count, uniform unit circulating
    current — corner-angle dependence at fixed everything else;
  * Roy's 6-wire model (k=1), clean mapped current — which channel the
    real model's residual lives in.

Also: n_qp_const sensitivity (8 vs 32) on the square — is any of it the
one numerical quadrature in the fill (Ez_const's regular part)?

Usage:  python scripts/loop_pathology_dissect.py
"""

import numpy as np

from momwire import HarringtonSolver
from momwire.sinusoidal import SinusoidalSolver

MHZ = 0.0005
WL = 299.8 / MHZ
RADIUS = 0.005


class ChannelMasked(SinusoidalSolver):
    """SinusoidalSolver whose fill keeps only the named shape channels."""

    def __init__(self, *, channels=("A", "B", "C"), **kw):
        self._channels = frozenset(channels)
        super().__init__(**kw)

    def _basis_coefs(self, geom, k):
        sv = dict(super()._basis_coefs(geom, k))
        for name in ("A", "B", "C"):
            if name not in self._channels:
                sv = {**sv, name: np.zeros_like(sv[name])}
        return sv


def ngon_wires(n_sides, perimeter=320.0, segs_total=32):
    """Closed regular n-gon in the z=0 plane, one wire per side."""
    side = perimeter / n_sides
    r = side / (2.0 * np.sin(np.pi / n_sides))
    pts = [
        (r * np.cos(2 * np.pi * i / n_sides), r * np.sin(2 * np.pi * i / n_sides), 0.0)
        for i in range(n_sides)
    ]
    wires = [np.array([pts[i], pts[(i + 1) % n_sides]], float) for i in range(n_sides)]
    per_side = segs_total // n_sides
    npe = [[per_side]] * n_sides
    junctions = [[(i, "end"), ((i + 1) % n_sides, "start")] for i in range(n_sides)]
    return wires, npe, junctions


def flatten_knots(per_wire):
    return np.concatenate([np.asarray(c) for c in per_wire])


def knot_map(s, n):
    cols = []
    for j in range(n):
        e = np.zeros(n, dtype=np.complex128)
        e[j] = 1.0
        cols.append(flatten_knots(s.currents_at_knots(e)))
    return np.column_stack(cols)


def circ_residual(make_solver, target_knots, w_rows=None):
    """w^T G_channel alpha for each channel; alpha fits target_knots once
    (on the full-channel solver so every channel sees the same current)."""
    s_full = make_solver(("A", "B", "C"))
    geom = s_full._build_geometry()
    n = geom["n_segs"]
    K = knot_map(s_full, n)
    alpha, *_ = np.linalg.lstsq(K, target_knots, rcond=None)
    fit = float(np.max(np.abs(K @ alpha - target_knots)))
    w = np.zeros(n)
    rows = np.arange(n) if w_rows is None else w_rows
    w[rows] = geom["seg_h"][rows]
    out = {}
    for ch in (("A",), ("B",), ("C",), ("A", "B", "C")):
        s = make_solver(ch)
        G, _ = s._assemble_Z(s._build_geometry(), s.k)
        out["+".join(ch)] = complex(w @ (G @ alpha))
    return out, fit


def report(tag, out, fit):
    tot = out["A+B+C"]
    print(f"{tag}  (repr fit {fit:.1e})")
    for name in ("A", "B", "C", "A+B+C"):
        v = out[name]
        print(f"   {name:5s} {abs(v):12.4e} V   ({v.real:+.3e} {v.imag:+.3e}j)")
    chk = out["A"] + out["B"] + out["C"]
    print(f"   sum-check |A+B+C - sum| = {abs(tot - chk):.2e}")


ROY_WIRES = [
    ((20, -40, 300), (20, -40, 0), 15),
    ((40, -40, 0), (40, 40, 0), 4),
    ((40, 40, 0), (-40, 40, 0), 4),
    ((-40, 40, 0), (-40, -40, 0), 4),
    ((-40, -40, 0), (20, -40, 0), 3),
    ((20, -40, 0), (40, -40, 0), 1),
]
ROY_JUNCTIONS = [
    [(0, "end"), (4, "end"), (5, "start")],
    [(5, "end"), (1, "start")],
    [(1, "end"), (2, "start")],
    [(2, "end"), (3, "start")],
    [(3, "end"), (4, "start")],
]


def ngon_experiments():
    """Corner-angle ladder: 2-wire corners are nearly clean at any angle."""
    for n_sides in (4, 8, 16):
        wires, npe, J = ngon_wires(n_sides, segs_total=32)

        def mk(ch, wires=wires, npe=npe, J=J):
            return ChannelMasked(
                channels=ch,
                wires=wires,
                n_per_edge_per_wire=npe,
                feeds=[(0, 1.0, 0j)],
                junctions=J,
                wire_radius=RADIUS,
                wavelength=WL,
            )

        target = np.ones(sum(e[0] + 1 for e in npe), dtype=np.complex128)
        out, fit = circ_residual(mk, target)
        report(f"{n_sides:2d}-gon, 32 segs, uniform 1 A", out, fit)


def stub_experiments():
    """THE smoking gun: a 3-wire junction stub carrying ZERO current
    multiplies the square loop's residual ~50,000x; the residual is
    radius-independent (kills every kernel/substitution story); a
    disconnected stub (same geometry, no junction declaration) is clean."""
    pts = [(40, -40, 0), (40, 40, 0), (-40, 40, 0), (-40, -40, 0)]
    loop_wires = [np.array([pts[i], pts[(i + 1) % 4]], float) for i in range(4)]
    stub = np.array([(40, -40, 0), (40, -40, 60)], float)
    npe = [[8]] * 4 + [[3]]
    J_conn = [
        [(3, "end"), (0, "start"), (4, "start")],
        [(0, "end"), (1, "start")],
        [(1, "end"), (2, "start")],
        [(2, "end"), (3, "start")],
    ]
    J_disc = [[(3, "end"), (0, "start")]] + J_conn[1:]
    target = np.concatenate([np.ones(9)] * 4 + [np.zeros(4)]).astype(np.complex128)

    def run(radius, J, tag):
        def mk(ch):
            return ChannelMasked(
                channels=ch,
                wires=loop_wires + [stub],
                n_per_edge_per_wire=npe,
                feeds=[(0, 1.0, 0j)],
                junctions=J,
                wire_radius=radius,
                wavelength=WL,
            )

        geom = mk(("A", "B", "C"))._build_geometry()
        rows = np.arange(geom["wire_first"][0], geom["wire_last"][3] + 1)
        out, fit = circ_residual(mk, target, w_rows=rows)
        print(
            f"{tag:34s} a={radius:7.4f}  |residual| "
            f"{abs(out['A+B+C']):.4e} V/A  (fit {fit:.0e})"
        )

    for a in (0.0005, 0.005, 0.05):
        run(a, J_conn, "stub CONNECTED (3-wire junction)")
    run(0.005, J_disc, "stub DISCONNECTED (control)")


def roy_experiment():
    """Channel split of the loop residual on Roy's model with the clean
    (Harrington-lane) current mapped into the sin basis."""
    ws = [np.array([a, b], float) for a, b, _ in ROY_WIRES]
    npe6 = [[n] for _, _, n in ROY_WIRES]
    h = HarringtonSolver(
        wires=ws,
        n_per_edge_per_wire=npe6,
        feeds=[(0, 270.0, -404675.9j)],
        wire_radius=RADIUS,
        wavelength=WL,
    )
    _, c_h = h.compute_impedance()
    t_clean = flatten_knots(h.currents_at_knots(c_h))

    def mk6(ch):
        return ChannelMasked(
            channels=ch,
            wires=ws,
            n_per_edge_per_wire=npe6,
            feeds=[(0, 270.0, 0j)],
            junctions=ROY_JUNCTIONS,
            wire_radius=RADIUS,
            wavelength=WL,
        )

    geom6 = mk6(("A", "B", "C"))._build_geometry()
    firsts, lasts = geom6["wire_first"], geom6["wire_last"]
    loop_rows = np.concatenate(
        [np.arange(firsts[w], lasts[w] + 1) for w in range(1, 6)]
    )
    out, fit = circ_residual(mk6, t_clean, w_rows=loop_rows)
    report("Roy's model k=1, clean current, loop rows", out, fit)


if __name__ == "__main__":
    ngon_experiments()
    stub_experiments()
    roy_experiment()
