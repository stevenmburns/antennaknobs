"""Half-razor prototype v2: machine-accurate integrals.

Same formulation as half_razor_proto.py — NEC-2 basis and junction
conditions untouched, midpoint collocation for the -j*omega*A part, exact
end-difference testing for the scalar potential — but the shape integrals
are now evaluated to machine accuracy:

  int f(z') G_a dz'  =  int f (G_a - 1/r_a) dz'   (entire in r; Gauss-48)
                      + sum_p f_p * M_p            (closed-form moments)

with f Taylor-expanded about the observer's axial foot z0 (exact trig
derivative coefficients, P=12) for pairs where |k u|_max is small, and
plain Gauss-48 on the full integrand for far pairs. The moment recursion:
  M_0 = asinh(u/b),  M_1 = sqrt(u^2+b^2),
  M_p = u^(p-1) sqrt(u^2+b^2)/p - (p-1) b^2/p M_(p-2).

Run: .venv/bin/python scratch/qrz-lfa-thread/half_razor_proto2.py
"""

import numpy as np
from momwire.sinusoidal import SinusoidalSolver

MU = 1.25663706127e-6
EPS = 8.8541878188e-12
C0 = 299792458.0
P_TAYLOR = 12

GX, GW = np.polynomial.legendre.leggauss(48)


def _moments(u, b, pmax):
    """M_p(u) = ∫^u t^p/sqrt(t^2+b^2) dt (antiderivative), p = 0..pmax."""
    r = np.sqrt(u * u + b * b)
    M = [np.arcsinh(u / b), r.copy()]
    for p in range(2, pmax + 1):
        M.append((u ** (p - 1)) * r / p - (p - 1) * b * b / p * M[p - 2])
    return M


def _taylor_coeffs(kind, k, z0, pmax):
    """f_p = (1/p!) d^p/dz'^p shape at z' = z0, for shape/deriv kinds."""
    kz = k * z0
    out = []
    fac = 1.0
    for p in range(pmax + 1):
        if p:
            fac *= p
        cyc = p % 4
        if kind == "const":
            v = 1.0 if p == 0 else 0.0
        elif kind == "sin":  # sin(k z')
            v = (k**p) * (np.sin(kz), np.cos(kz), -np.sin(kz), -np.cos(kz))[cyc]
        elif kind == "cos":  # cos(k z')
            v = (k**p) * (np.cos(kz), -np.sin(kz), -np.cos(kz), np.sin(kz))[cyc]
        elif kind == "dsin":  # d/dz' sin = k cos(k z')
            v = (k ** (p + 1)) * (np.cos(kz), -np.sin(kz), -np.cos(kz), np.sin(kz))[cyc]
        elif kind == "dcos":  # d/dz' cos = -k sin(k z')
            v = (
                -(k ** (p + 1))
                * (np.sin(kz), np.cos(kz), -np.sin(kz), -np.cos(kz))[cyc]
            )
        else:
            raise ValueError(kind)
        out.append(v / fac)
    return out


def shape_integrals(obs, cen, tan, H, k, a, kinds):
    """∫ shape(z') G_a(|obs - p(z')|) dz' for each kind, to machine accuracy.

    obs (M,3); source segments (n): cen/tan/H. Returns dict kind -> (M,n).
    """
    rel = obs[:, None, :] - cen[None, :, :]
    z0 = np.einsum("mnd,nd->mn", rel, tan)
    rho2 = np.maximum((rel * rel).sum(-1) - z0 * z0, 0.0)
    b = np.sqrt(rho2 + a * a)
    u1, u2 = -H[None, :] - z0, H[None, :] - z0

    # quadrature points (shared): z' in [-H, H]
    zq = H[:, None] * GX[None, :]
    pq = cen[:, None, :] + zq[..., None] * tan[:, None, :]
    d = obs[:, None, None, :] - pq[None, :, :, :]
    ra_q = np.sqrt((d * d).sum(-1) + a * a)
    Gq = np.exp(-1j * k * ra_q) / ra_q
    smooth_q = (np.exp(-1j * k * ra_q) - 1.0) / ra_q  # entire in r_a

    kumax = np.abs(k) * np.maximum(np.abs(u1), np.abs(u2))
    near = kumax < 1.0  # Taylor P=12 good to ~1e-13 at |ku|=1

    Mo = _moments(u2, b, P_TAYLOR)
    Mo1 = _moments(u1, b, P_TAYLOR)

    out = {}
    for kind in kinds:
        base = {"dsin": "sin", "dcos": "cos"}.get(kind, kind)
        val_q = {
            "const": np.ones_like(zq),
            "sin": np.sin(k * zq),
            "cos": np.cos(k * zq),
            "dsin": k * np.cos(k * zq),
            "dcos": -k * np.sin(k * zq),
        }[kind]
        # far pairs: plain Gauss on the full integrand
        far_val = (val_q[None, :, :] * Gq * GW[None, None, :]).sum(-1) * H[None, :]
        # near pairs: smooth part by Gauss + singular part by moments
        smooth_val = (val_q[None, :, :] * smooth_q * GW[None, None, :]).sum(-1) * H[
            None, :
        ]
        coeffs = _taylor_coeffs(kind, k, z0, P_TAYLOR)
        sing = np.zeros_like(smooth_val)
        for p in range(P_TAYLOR + 1):
            sing = sing + coeffs[p] * (Mo[p] - Mo1[p])
        out[kind] = np.where(near, smooth_val + sing, far_val)
        _ = base
    return out


def build_half_razor2(s):
    geom = s._build_geometry()
    k = s.k
    omega = C0 * k
    n = geom["n_segs"]
    a = s._uniform_radius
    cen, tan, h = geom["seg_centers"], geom["seg_tangents"], geom["seg_h"]
    seg_l = cen - 0.5 * h[:, None] * tan
    seg_r = cen + 0.5 * h[:, None] * tan
    H = 0.5 * h

    node_pos, node_of = [], {}

    def nid(p):
        key = tuple(np.round(p / 1e-9).astype(np.int64))
        if key not in node_of:
            node_of[key] = len(node_pos)
            node_pos.append(p)
        return node_of[key]

    left = np.array([nid(p) for p in seg_l])
    right = np.array([nid(p) for p in seg_r])
    nodes = np.array(node_pos)

    # A part at midpoints
    A_int = shape_integrals(cen, cen, tan, H, k, a, ("const", "sin", "cos"))
    td = tan @ tan.T
    T_A = {
        nm: (-1j * omega * MU / (4 * np.pi)) * h[:, None] * td * A_int[nm]
        for nm in A_int
    }

    # phi at unique nodes: endpoint charges (exact) + line-charge integral
    d2 = nodes[:, None, :] - seg_r[None, :, :]
    d1 = nodes[:, None, :] - seg_l[None, :, :]
    r2 = np.sqrt((d2 * d2).sum(-1) + a * a)
    r1 = np.sqrt((d1 * d1).sum(-1) + a * a)
    Ga2 = np.exp(-1j * k * r2) / r2
    Ga1 = np.exp(-1j * k * r1) / r1
    line = shape_integrals(nodes, cen, tan, H, k, a, ("dsin", "dcos"))
    pref = 1.0 / (4 * np.pi * EPS * 1j * omega)
    e = {
        "const": (np.ones_like(H), np.ones_like(H)),
        "sin": (np.sin(k * H), np.sin(-k * H)),
        "cos": (np.cos(k * H), np.cos(-k * H)),
    }
    T_phi = {
        "const": pref * (e["const"][0] * Ga2 - e["const"][1] * Ga1),
        "sin": pref * (e["sin"][0] * Ga2 - e["sin"][1] * Ga1 - line["dsin"]),
        "cos": pref * (e["cos"][0] * Ga2 - e["cos"][1] * Ga1 - line["dcos"]),
    }

    sv = s._basis_coefs(geom, k)
    starts, jb, sig = sv["starts"], sv["jbasis"], sv["sigma"]
    n_idx = np.repeat(np.arange(n), starts[1:] - starts[:-1])
    coef = {"const": sig * sv["A"], "sin": sv["B"], "cos": sig * sv["C"]}

    Gp = np.zeros((n, n), dtype=np.complex128)
    for nm in ("const", "sin", "cos"):
        Mmat = np.zeros((n, n), dtype=np.complex128)
        Mmat[n_idx, jb] = coef[nm]
        rows = T_A[nm] - (T_phi[nm][right] - T_phi[nm][left])
        Gp += rows @ Mmat
    return Gp, geom


def solve2(s, V):
    Gp, geom = build_half_razor2(s)
    rhs = np.zeros(geom["n_segs"], dtype=np.complex128)
    rhs[geom["feed_segs"][0]] = -V
    return np.linalg.solve(Gp, rhs), geom


def i_at_feed(s, geom, alpha):
    sv = s._basis_coefs(geom, s.k)
    st = sv["starts"]
    fed = geom["feed_segs"][0]
    ent = slice(st[fed], st[fed + 1])
    return np.sum(
        (sv["sigma"][ent] * sv["A"][ent] + sv["sigma"][ent] * sv["C"][ent])
        * alpha[sv["jbasis"][ent]]
    )


if __name__ == "__main__":
    from momwire import BSplineSolver

    # dipole ladder: resonant + electrostatic limits
    for mhz in (15.0, 0.5, 0.05):
        wl = 299.8 / mhz
        mkw = dict(
            wires=[np.array([[0, 0, 0], [0, 10.0, 0]], float)],
            n_per_edge_per_wire=[[21]],
            feeds=[(0, 5.0, 1.0 + 0j)],
            wire_radius=0.001,
            wavelength=wl,
        )
        s = SinusoidalSolver(**mkw)
        z_stock, _ = s.compute_impedance()
        alpha, geom = solve2(s, 1.0 + 0j)
        zh = 1.0 / i_at_feed(s, geom, alpha)
        b = BSplineSolver(degree=2, **mkw)
        zb, _ = b.compute_impedance()
        print(f"{mhz * 1e6:>10.0f} Hz  stock {z_stock:.4g}  hr2 {zh:.4g}  bs2 {zb:.4g}")

    # Roy's model
    W = [
        ((20, -40, 300), (20, -40, 0), 15),
        ((40, -40, 0), (40, 40, 0), 4),
        ((40, 40, 0), (-40, 40, 0), 4),
        ((-40, 40, 0), (-40, -40, 0), 4),
        ((-40, -40, 0), (20, -40, 0), 3),
        ((20, -40, 0), (40, -40, 0), 1),
    ]
    J6 = [
        [(0, "end"), (4, "end"), (5, "start")],
        [(5, "end"), (1, "start")],
        [(1, "end"), (2, "start")],
        [(2, "end"), (3, "start")],
        [(3, "end"), (4, "start")],
    ]
    V = -404675.9j
    for mhz in (0.05, 0.005, 0.0005, 0.00005, 0.000005):
        s6 = SinusoidalSolver(
            wires=[np.array([p0, p1], float) for p0, p1, _ in W],
            n_per_edge_per_wire=[[nn] for _, _, nn in W],
            feeds=[(0, 270.0, 0j)],
            junctions=J6,
            wire_radius=0.005,
            wavelength=299.8 / mhz,
        )
        alpha, geom = solve2(s6, V)
        i_src = i_at_feed(s6, geom, alpha)
        knots = [np.asarray(c) for c in s6.currents_at_knots(alpha)]
        loop = max(float(np.max(np.abs(0.5 * (c[:-1] + c[1:])))) for c in knots[1:])
        print(
            f"Roy {mhz * 1e6:>9.1f} Hz  hr2: I_src {abs(i_src):.4e} A"
            f"   max loop {loop:.4e} A   ratio {loop / abs(i_src):.4f}"
        )
