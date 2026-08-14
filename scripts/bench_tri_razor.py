"""Tent basis + razor-blade testing: does it reproduce NEC-5's convergence?

The NEC-5 Users Manual (§1) states the formulation: linear (triangular)
current expansion with the mixed-potential method of Rao, Wilton and
Glisson — the E-field boundary condition enforced on path integrals
between centroids of connected elements ("razor-blade" testing), NOT the
point matching of NEC-2/4 and NOT the Galerkin testing of momwire's
BSplineSolver(degree=1). The manual also predicts slower convergence than
the sinusoidal expansion. This instrument tests whether that testing rule
alone reproduces NEC-5's O(1/N) impedance walk (the #890/#896 finding) on
the ByDipole1 wire in FREE SPACE — free space so the comparison is not
contaminated by NEC-5's Michalski ground, which has its own limit offset.

Lanes (all the same wire: L=10.18946 m, a=1.0262 mm, 14 MHz, center-fed):
  razor  this file's solver — tents on knots, path-integral testing
         between adjacent segment centroids, reduced kernel, delta-gap V
         landing entirely in the feed knot's row (NEC-5's EX-at-knot)
  1ptA   variant: vector-potential path integral collapsed to h*A(knot)
  nec5   $NEC5_EXE on the free-space deck, EX at the center knot
  bs1    momwire BSplineSolver(degree=1) — same basis, Galerkin testing

Usage:
  .venv/bin/python scripts/bench_tri_razor.py            # all lanes
  .venv/bin/python scripts/bench_tri_razor.py --no-nec5  # skip binary
Writes scratch/tri-razor-ladders.json and prints the comparison table.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scratch" / "tri-razor-ladders.json"

C0 = 299792458.0
EPS0 = 8.8541878128e-12
MU0 = 4e-7 * np.pi

FREQ_HZ = 14.0e6
L = 10.18946
RAD = 0.0010262
EVEN = list(range(12, 101, 4))


# --------------------------------------------------------------------------
# the razor solver


def _static_m0_m1(y, s0, s1, a):
    """Closed-form ∫_{s0}^{s1} dy'/R and ∫_{s0}^{s1} y' dy'/R with
    R = sqrt((y-y')^2 + a^2). Vectorized over the segment arrays s0, s1."""
    u0 = s0 - y
    u1 = s1 - y
    m0 = np.arcsinh(u1 / a) - np.arcsinh(u0 / a)
    m1 = y * m0 + (np.sqrt(u1 * u1 + a * a) - np.sqrt(u0 * u0 + a * a))
    return m0, m1


def _seg_moments(y, seg_lo, seg_hi, a, k, xg, wg):
    """M0_j(y) = ∫_{seg j} g(y,y')dy' and M1_j(y) = ∫ y' g dy', with
    g = exp(-jkR)/(4πR): analytic static part + GL on the smooth
    remainder (exp(-jkR)-1)/(4πR). y scalar; seg arrays shape (N,)."""
    m0s, m1s = _static_m0_m1(y, seg_lo, seg_hi, a)
    # remainder nodes: shape (N, q)
    mid = 0.5 * (seg_lo + seg_hi)[:, None]
    half = 0.5 * (seg_hi - seg_lo)[:, None]
    yp = mid + half * xg[None, :]
    R = np.sqrt((y - yp) ** 2 + a * a)
    rem = (np.exp(-1j * k * R) - 1.0) / R
    m0r = (rem * wg[None, :]).sum(axis=1) * half[:, 0]
    m1r = (rem * yp * wg[None, :]).sum(axis=1) * half[:, 0]
    return (m0s + m0r) / (4 * np.pi), (m1s + m1r) / (4 * np.pi)


def _tent_potentials(y, knots, a, k, xg, wg):
    """A_n(y) (without mu0) for every interior knot n at observation y:
    A_n = ∫ Λ_n(y') g(y,y') dy', Λ_n the unit tent at knot n."""
    h = knots[1] - knots[0]
    m0, m1 = _seg_moments(y, knots[:-1], knots[1:], a, k, xg, wg)
    # tent n spans segments n-1 and n (0-based segs); rising then falling
    rise = (m1[:-1] - knots[:-2] * m0[:-1]) / h
    fall = (knots[2:] * m0[1:] - m1[1:]) / h
    return rise + fall


def razor_impedance(
    n: int,
    *,
    a: float = RAD,
    length: float = L,
    freq_hz: float = FREQ_HZ,
    n_gl_outer: int = 32,
    n_gl_rem: int = 12,
    one_point_a: bool = False,
) -> complex:
    """Center-fed straight-wire input impedance, tent basis + razor testing.

    Row m (interior knot m): jω∫_{c_m}^{c_{m+1}} A dy + Φ(c_{m+1}) − Φ(c_m)
    = V_m, the path spanning the centroids of the two segments meeting at
    knot m. Charge doublet Φ from the tent derivative (±1/h pulses). The
    delta-gap V sits inside exactly one path — the feed knot's row."""
    if n % 2:
        raise ValueError("center knot feed needs even n")
    w = 2 * np.pi * freq_hz
    k = w / C0
    h = length / n
    knots = np.arange(n + 1) * h
    cent = (np.arange(n) + 0.5) * h
    m_int = n - 1  # interior knots 1..n-1

    xg_r, wg_r = np.polynomial.legendre.leggauss(n_gl_rem)
    xg_o, wg_o = np.polynomial.legendre.leggauss(n_gl_outer)

    # scalar-potential ingredient: M0_j at every centroid (obs points)
    M0c = np.empty((n, n), dtype=complex)  # [centroid j, segment s]
    for j in range(n):
        M0c[j], _ = _seg_moments(cent[j], knots[:-1], knots[1:], a, k, xg_r, wg_r)

    Z = np.empty((m_int, m_int), dtype=complex)
    for m in range(1, n):  # row = interior knot m
        # vector-potential term over the path c_{m-1..m} .. knot .. c_{m..m+1}
        if one_point_a:
            t1 = h * _tent_potentials(knots[m], knots, a, k, xg_r, wg_r)
        else:
            t1 = np.zeros(m_int, dtype=complex)
            for lo, hi in ((cent[m - 1], knots[m]), (knots[m], cent[m])):
                mid, half = 0.5 * (lo + hi), 0.5 * (hi - lo)
                for xq, wq in zip(xg_o, wg_o):
                    t1 += (wq * half) * _tent_potentials(
                        mid + half * xq, knots, a, k, xg_r, wg_r
                    )
        # scalar-potential difference term: tent n' has charge +1/h on its
        # rising segment (index n'-1) and -1/h on its falling one (index n')
        dM0 = M0c[m] - M0c[m - 1]  # obs c_{m+1} minus c_m, all segments
        t2 = (dM0[:-1] - dM0[1:]) / h
        Z[m - 1] = 1j * w * MU0 * t1 - t2 / (1j * w * EPS0)

    rhs = np.zeros(m_int, dtype=complex)
    feed_row = n // 2 - 1  # interior knot n/2, the wire's exact center
    rhs[feed_row] = 1.0
    current = np.linalg.solve(Z, rhs)
    return 1.0 / current[feed_row]


# --------------------------------------------------------------------------
# comparison lanes


def bs1_impedance(n: int) -> complex:
    from momwire.bspline import BSplineSolver

    wires = [np.array([[0.0, 0.0, 0.0], [0.0, L, 0.0]])]
    z, _ = BSplineSolver(
        wires=wires,
        nsegs=n,
        degree=1,
        wire_radius=RAD,
        wavelength=C0 / FREQ_HZ,
    ).compute_impedance()
    return z


def nec5_impedance(n: int, eng) -> complex:
    deck = (
        "CM tri-razor free-space ladder\nCE\n"
        f"GW 1 {n} 0.000000E+00 0.000000E+00 0.000000E+00 "
        f"0.000000E+00 {L:.6E} 0.000000E+00 {RAD:.6E}\n"
        "GE 0\n"
        f"EX 0 1 {n // 2} 2 1.000000E+00 0.000000E+00\n"
        f"FR 0 1 0 0 {FREQ_HZ / 1e6:.6E} 0.000000E+00\nXQ 0\nEN\n"
    )
    return eng.run_deck(deck)[0][0][2]


def _ri(z: complex) -> list[float]:
    return [round(z.real, 5), round(z.imag, 5)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-nec5", action="store_true")
    ap.add_argument("--quad-check", action="store_true")
    args = ap.parse_args()

    if args.quad_check:
        for n in (12, 48):
            z0 = razor_impedance(n)
            z1 = razor_impedance(n, n_gl_outer=64, n_gl_rem=24)
            print(f"quad self-check N={n}: {z0:.6f} vs doubled {z1:.6f} "
                  f"(|Δ|={abs(z1 - z0):.2e})")
        return

    data: dict[str, list] = {}
    data["razor"] = [[n, *_ri(razor_impedance(n))] for n in EVEN]
    print("razor done", flush=True)
    data["razor_1ptA"] = [
        [n, *_ri(razor_impedance(n, one_point_a=True))] for n in EVEN
    ]
    print("razor_1ptA done", flush=True)
    data["bs1"] = [[n, *_ri(bs1_impedance(n))] for n in EVEN]
    print("bs1 done", flush=True)

    if not args.no_nec5:
        sys.path.insert(0, str(ROOT / "scripts"))
        from bench_nec5_walk_why import make_dipole

        from antennaknobs.engines.nec5 import NEC5Engine

        eng = NEC5Engine(
            make_dipole(20),
            ground=None,
            capture_dir=Path.home() / ".antennaknobs" / "nec5-captures",
        )
        data["nec5"] = [[n, *_ri(nec5_impedance(n, eng))] for n in EVEN]
        print("nec5 done", flush=True)

    OUT.write_text(json.dumps(data))

    lanes = [k for k in ("nec5", "razor", "razor_1ptA", "bs1") if k in data]
    hdr = "  N   " + "".join(f"{k:>22}" for k in lanes)
    print("\n" + hdr)
    for i, n in enumerate(EVEN):
        row = f"{n:4d}  "
        for k in lanes:
            r, x = data[k][i][1], data[k][i][2]
            row += f"{r:9.3f} {x:+9.3f}j  "
        print(row)

    # Richardson-pair character: X(2N) - X(N) halving down the ladder
    print("\npair diffs X(2N)-X(N):")
    idx = {n: i for i, n in enumerate(EVEN)}
    for k in lanes:
        pairs = []
        for n in (12, 24, 48):
            if n in idx and 2 * n in idx:
                pairs.append(data[k][idx[2 * n]][2] - data[k][idx[n]][2])
        ratios = [pairs[i] / pairs[i + 1] for i in range(len(pairs) - 1)]
        print(f"  {k:>10}: " + "  ".join(f"{d:+.3f}" for d in pairs)
              + "   ratios " + "  ".join(f"{r:.2f}" for r in ratios))


if __name__ == "__main__":
    main()
