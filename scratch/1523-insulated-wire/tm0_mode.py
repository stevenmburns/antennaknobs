"""AK#1523, step 2: the exact TM0 guided mode of a dielectric-coated, perfectly
conducting wire in free space (the Goubau-line boundary-value problem), against
the two per-unit-length readings of the jacket.

  python scratch/1523-insulated-wire/tm0_mode.py scratch/1523-insulated-wire/reference.json

The coating a < rho < b has permittivity eps_r, free space is outside, and the
fields go as exp(-j beta z). With p^2 = eps_r k0^2 - beta^2 and
q^2 = beta^2 - k0^2:

  E_z = A F(p rho),  F(x) = J0(x) Y0(pa) - Y0(x) J0(pa)   inside
  E_z = C K0(q rho)                                        outside

and continuity of E_z and H_phi at b gives

  eps_r F'(pb) / (p F(pb)) = K1(qb) / (q K0(qb)).

Z0 = V/I, where V is the radial line integral of E_rho from a to infinity and
I = 2 pi a H_phi(a). The closed form, -beta (1 + p^2/q^2) F(pb) / (4 omega eps0
eps_r), is checked here against quadrature. The power-based 2P/I^2 and V^2/2P
are recorded beside it.

The two treatments as lines, at the exact mode's Lambda = K0(qb) / (qb K1(qb))
and l = ln(b/a):

  pair    C' = 2 pi eps0 / (Lambda + l/eps_r)   L' = mu0/2pi (Lambda + l)
  L-only  C' = 2 pi eps0 / (Lambda + l)         L' = mu0/2pi (Lambda + 2l - l/eps_r)

No antennaknobs or momwire import: the reference is independent of both.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import scipy
from scipy import constants, integrate, optimize, special

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jackets import FREQ_MHZ, JACKETS

MU0 = constants.mu_0
EPS0 = constants.epsilon_0
C0 = constants.c
ETA0 = MU0 * C0


def _log_quad(f, lo, hi):
    """The integral of f over [lo, hi], taken in t = ln(rho)."""
    val, _err = integrate.quad(
        lambda t: f(math.exp(t)) * math.exp(t),
        math.log(lo),
        math.log(hi),
        epsabs=0.0,
        epsrel=1e-11,
        limit=400,
    )
    return val


def mode(a, b, eps_r, freq_hz):
    omega = 2.0 * math.pi * freq_hz
    k0 = omega / C0

    def pq(s):
        return (
            k0 * math.sqrt(eps_r - (1.0 + s) ** 2),
            k0 * math.sqrt(s * (2.0 + s)),
        )

    def F(x, p):
        return special.j0(x) * special.y0(p * a) - special.y0(x) * special.j0(p * a)

    def dF(x, p):
        return special.y1(x) * special.j0(p * a) - special.j1(x) * special.y0(p * a)

    def mismatch(u):
        p, q = pq(math.exp(u))
        lhs = eps_r * dF(p * b, p) / (p * F(p * b, p))
        rhs = special.k1(q * b) / (q * special.k0(q * b))
        return math.log(lhs / rhs)

    s_max = math.sqrt(eps_r) - 1.0
    u = optimize.brentq(
        mismatch,
        math.log(1e-14),
        math.log(s_max * (1.0 - 1e-12)),
        xtol=1e-15,
        rtol=4.0 * sys.float_info.epsilon,
        maxiter=500,
    )
    s = math.exp(u)
    beta = k0 * (1.0 + s)
    p, q = pq(s)
    eps1 = EPS0 * eps_r
    Fb = F(p * b, p)
    z_vi = -beta * (1.0 + p * p / (q * q)) * Fb / (4.0 * omega * eps1)

    # Quadrature with A = 1 (the common -j dropped from E_rho and H_phi).
    C = Fb / special.k0(q * b)
    rho_far = b * 60.0 / (q * b)  # K1 has decayed by e^-60

    def e_in(r):
        return beta * dF(p * r, p) / p

    def h_in(r):
        return omega * eps1 * dF(p * r, p) / p

    def e_out(r):
        return beta * C * special.k1(q * r) / q

    def h_out(r):
        return omega * EPS0 * C * special.k1(q * r) / q

    V = _log_quad(e_in, a, b) + _log_quad(e_out, b, rho_far)
    current = 2.0 * math.pi * a * h_in(a)
    P = 0.5 * (
        _log_quad(lambda r: e_in(r) * h_in(r) * 2.0 * math.pi * r, a, b)
        + _log_quad(lambda r: e_out(r) * h_out(r) * 2.0 * math.pi * r, b, rho_far)
    )

    lam = special.k0(q * b) / (q * b * special.k1(q * b))
    ell = math.log(b / a)
    return {
        "a": a,
        "b": b,
        "eps_r": eps_r,
        "freq_hz": freq_hz,
        "a_eq": a * (b / a) ** ((eps_r - 1.0) / eps_r),
        "L_ins": MU0 / (2.0 * math.pi) * (1.0 - 1.0 / eps_r) * ell,
        "s_exact": s,
        "beta_over_k0_exact": 1.0 + s,
        "s_mode": 1.0 - 1.0 / (1.0 + s),
        "q": q,
        "p": p,
        "Lambda": lam,
        "ell": ell,
        "x": (1.0 - 1.0 / eps_r) * ell / (lam + ell),
        "beta_over_k0_pair": math.sqrt((lam + ell) / (lam + ell / eps_r)),
        "beta_over_k0_lonly": math.sqrt((lam + 2.0 * ell - ell / eps_r) / (lam + ell)),
        "z0_exact_vi": z_vi,
        "z0_exact_vi_quad": V / current,
        "z0_exact_pi": 2.0 * P / current**2,
        "z0_exact_pv": V**2 / (2.0 * P),
        "z0_pair": ETA0
        / (2.0 * math.pi)
        * math.sqrt((lam + ell) * (lam + ell / eps_r)),
        "z0_lonly": ETA0
        / (2.0 * math.pi)
        * math.sqrt((lam + 2.0 * ell - ell / eps_r) * (lam + ell)),
    }


def main():
    out = Path(sys.argv[1])
    freq_hz = FREQ_MHZ * 1e6
    rec = {
        "_meta": {"scipy": scipy.__version__, "freq_hz": freq_hz},
        "jackets": {
            name: mode(a, b, eps, freq_hz) for name, (a, b, eps) in JACKETS.items()
        },
        "limit_eps_1.001": mode(*JACKETS["22-awg-pvc"][:2], 1.001, freq_hz),
    }
    out.write_text(json.dumps(rec, indent=1))
    print(
        f"{'jacket':>12} {'s_exact':>10} {'Lambda':>7} {'x':>7} "
        f"{'bp/be-1':>9} {'bL/be-1':>9} {'Z0 exact':>9} {'pair/ex-1':>9} "
        f"{'Lonly/ex-1':>10} {'quad/cf-1':>9} {'PI/VI-1':>8}"
    )
    rows = [*rec["jackets"].items(), ("eps 1.001", rec["limit_eps_1.001"])]
    for name, m in rows:
        be = m["beta_over_k0_exact"]
        ze = m["z0_exact_vi"]
        print(
            f"{name:>12} {m['s_exact']:10.3e} {m['Lambda']:7.3f} {m['x']:7.4f} "
            f"{m['beta_over_k0_pair'] / be - 1:9.2e} "
            f"{m['beta_over_k0_lonly'] / be - 1:9.2e} {ze:9.3f} "
            f"{m['z0_pair'] / ze - 1:9.2e} {m['z0_lonly'] / ze - 1:10.2e} "
            f"{m['z0_exact_vi_quad'] / ze - 1:9.2e} {m['z0_exact_pi'] / ze - 1:8.1e}"
        )


if __name__ == "__main__":
    main()
