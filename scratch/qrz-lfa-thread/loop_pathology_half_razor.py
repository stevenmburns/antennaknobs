"""The half-razor experiment: phi tested by end-difference on the NEC-2 basis.

The dissection (`loop_pathology_dissect.py`) pins the coupled-loop
pathology to the TESTING side of the point-matched sinusoidal scheme:
collocation samples E at segment midpoints, so the loop sum of tested
equations is a midpoint-rule quadrature of the closed line integral of
grad phi — whose error is O(local phi) wherever the multi-wire-junction
basis conditions make phi vary at sub-segment scale, and which rides
1/omega (Burke's account, quoted publicly by W7EL in QRZ thread 1000972).

This script measures the SMALLEST-CHANGE candidate fix: keep the NEC-2
three-term basis and its junction conditions, keep midpoint collocation
for the smooth -j*omega*A part, but test the scalar potential as an exact
end-difference phi(right node) - phi(left node), with phi evaluated once
per unique node position (a scalar field value shared by every segment
meeting there) so any closed-loop sum telescopes by construction. The
shape channels are the well-scaled folded set {1, sin, cos-1} with the
exactly-summed `AC` coefficient — with the literal {1, sin, cos} channels
the giant A/C cancellation (docs/sinusoidal_basis_design.md, the #203
hazard) destroys the operator below ~1 kHz on this model.

What it shows (run it):

  1. dipole sanity: within a few percent of the stock solver and bspline
     at moderate and small electrical size;
  2. Roy's coupled-loop model: the loop/source current ratio comes out
     FLAT at ~0.44 from 50 kHz down to 5 Hz — the spurious loop EMF is
     structurally dead at every frequency;
  3. ...and the honest failure: below L/lambda ~ 1e-3 the input
     capacitance collapses ~200x. The final diagnostic prints why: the
     solved NODE potentials form perfect equipotential plateaus with
     exactly the drive-voltage jump at the gap, while the MIDPOINT
     potentials sit near zero — a checkerboard charge mode, invisible to
     node-only testing, supplied by the basis's intra-segment quadratic
     charge freedom.

Conclusion recorded in docs/nec2-loop-pathology.md: within the NEC-2
basis, phi must be controlled both at the nodes and inside the segments,
and N equations cannot do both — point matching controls the midpoints
(spurious loop EMF), node differencing controls the nodes (checkerboard).
The basis is the disease; the tent/interval (razor, NEC-5) and in-basis-
charge (bspline) routes dissolve both problems at once.

Usage:  python scripts/loop_pathology_half_razor.py
"""

import numpy as np
from momwire.sinusoidal import SinusoidalSolver

MU = 1.25663706127e-6
EPS = 8.8541878188e-12
C0 = 299792458.0
P_TAYLOR = 12

GX, GW = np.polynomial.legendre.leggauss(48)


def _moments(u, b, pmax):
    """M_p(u) = antiderivative of u^p / sqrt(u^2 + b^2), p = 0..pmax."""
    r = np.sqrt(u * u + b * b)
    M = [np.arcsinh(u / b), r.copy()]
    for p in range(2, pmax + 1):
        M.append((u ** (p - 1)) * r / p - (p - 1) * b * b / p * M[p - 2])
    return M


def _taylor_coeffs(kind, k, z0, pmax):
    """(1/p!) d^p/dz'^p of the shape at z' = z0. Kinds: const, sin, cos,
    cos1 (= cos - 1), dsin (= d/dz' sin), dcos (= d/dz' cos = d/dz' cos1)."""
    kz = k * z0
    out = []
    fac = 1.0
    for p in range(pmax + 1):
        if p:
            fac *= p
        cyc = p % 4
        if kind == "const":
            v = 1.0 if p == 0 else 0.0
        elif kind in ("sin",):
            v = (k**p) * (np.sin(kz), np.cos(kz), -np.sin(kz), -np.cos(kz))[cyc]
        elif kind in ("cos", "cos1"):
            v = (k**p) * (np.cos(kz), -np.sin(kz), -np.cos(kz), np.sin(kz))[cyc]
        elif kind == "dsin":
            v = (k ** (p + 1)) * (np.cos(kz), -np.sin(kz), -np.cos(kz), np.sin(kz))[cyc]
        elif kind == "dcos":
            v = (
                -(k ** (p + 1))
                * (np.sin(kz), np.cos(kz), -np.sin(kz), -np.cos(kz))[cyc]
            )
        else:
            raise ValueError(kind)
        out.append(v / fac)
    if kind == "cos1":
        out[0] = out[0] - 1.0
    return out


def shape_integrals(obs, cen, tan, H, k, a, kinds):
    """int shape(z') G_a(|obs - p(z')|) dz' per kind, machine-accurate.

    Near pairs: smooth part (e^{-jkr}-1)/r by Gauss-48 plus the 1/r_a part
    by exact Taylor moments about the observer's axial foot. Far pairs:
    plain Gauss-48 on the full integrand. `cos1` is evaluated as
    -2 sin^2(k z'/2) so the folded channel never cancels catastrophically.
    """
    rel = obs[:, None, :] - cen[None, :, :]
    z0 = np.einsum("mnd,nd->mn", rel, tan)
    rho2 = np.maximum((rel * rel).sum(-1) - z0 * z0, 0.0)
    b = np.sqrt(rho2 + a * a)
    u1, u2 = -H[None, :] - z0, H[None, :] - z0

    zq = H[:, None] * GX[None, :]
    pq = cen[:, None, :] + zq[..., None] * tan[:, None, :]
    d = obs[:, None, None, :] - pq[None, :, :, :]
    ra_q = np.sqrt((d * d).sum(-1) + a * a)
    Gq = np.exp(-1j * k * ra_q) / ra_q
    smooth_q = (np.exp(-1j * k * ra_q) - 1.0) / ra_q

    near = np.abs(k) * np.maximum(np.abs(u1), np.abs(u2)) < 1.0
    Mo2 = _moments(u2, b, P_TAYLOR)
    Mo1 = _moments(u1, b, P_TAYLOR)

    out = {}
    for kind in kinds:
        val_q = {
            "const": np.ones_like(zq),
            "sin": np.sin(k * zq),
            "cos": np.cos(k * zq),
            "cos1": -2.0 * np.sin(0.5 * k * zq) ** 2,
            "dsin": k * np.cos(k * zq),
            "dcos": -k * np.sin(k * zq),
        }[kind]
        far_val = (val_q[None, :, :] * Gq * GW[None, None, :]).sum(-1) * H[None, :]
        smooth_val = (val_q[None, :, :] * smooth_q * GW[None, None, :]).sum(-1) * H[
            None, :
        ]
        coeffs = _taylor_coeffs(kind, k, z0, P_TAYLOR)
        sing = np.zeros_like(smooth_val)
        for p in range(P_TAYLOR + 1):
            sing = sing + coeffs[p] * (Mo2[p] - Mo1[p])
        out[kind] = np.where(near, smooth_val + sing, far_val)
    return out


def _phi_tables(obs, cen, tan, H, k, a, omega):
    """Scalar potential of each folded shape at the given points: exact
    endpoint charges plus the line-charge integral (charge = -I'/j*omega)."""
    seg_l = cen - H[:, None] * tan
    seg_r = cen + H[:, None] * tan
    d2 = obs[:, None, :] - seg_r[None, :, :]
    d1 = obs[:, None, :] - seg_l[None, :, :]
    r2 = np.sqrt((d2 * d2).sum(-1) + a * a)
    r1 = np.sqrt((d1 * d1).sum(-1) + a * a)
    Ga2 = np.exp(-1j * k * r2) / r2
    Ga1 = np.exp(-1j * k * r1) / r1
    line = shape_integrals(obs, cen, tan, H, k, a, ("dsin", "dcos"))
    pref = 1.0 / (4 * np.pi * EPS * 1j * omega)
    e_sin2, e_sin1 = np.sin(k * H), np.sin(-k * H)
    e_c1 = -2.0 * np.sin(0.5 * k * H) ** 2  # cos(kH) - 1, exactly
    return {
        "const": pref * (Ga2 - Ga1),
        "sin": pref * (e_sin2 * Ga2 - e_sin1 * Ga1 - line["dsin"]),
        "cos1": pref * (e_c1 * Ga2 - e_c1 * Ga1 - line["dcos"]),
    }


def build_half_razor(s, want_phi_maps=False):
    """Half-razor matrix for a configured SinusoidalSolver: folded shape
    channels, -j*omega*A collocated at midpoints, phi as node differences.

    Returns (Gp, geom) — plus (Phi_nodes, Phi_mids, left, right) when
    `want_phi_maps` (the checkerboard diagnostic reads potentials off
    them)."""
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

    A_int = shape_integrals(cen, cen, tan, H, k, a, ("const", "sin", "cos1"))
    td = tan @ tan.T
    T_A = {
        nm: (-1j * omega * MU / (4 * np.pi)) * h[:, None] * td * A_int[nm]
        for nm in A_int
    }
    T_phi = _phi_tables(nodes, cen, tan, H, k, a, omega)

    sv = s._basis_coefs(geom, k)
    starts, jb, sig = sv["starts"], sv["jbasis"], sv["sigma"]
    n_idx = np.repeat(np.arange(n), starts[1:] - starts[:-1])
    # folded channels: the const coefficient is the EXACT A+C sum the
    # basis builder publishes; cos1 keeps C alone at its own (small) size.
    coef = {"const": sig * sv["AC"], "sin": sv["B"], "cos1": sig * sv["C"]}

    Gp = np.zeros((n, n), dtype=np.complex128)
    Phi_nodes = np.zeros((len(nodes), n), dtype=np.complex128)
    for nm in ("const", "sin", "cos1"):
        Mm = np.zeros((n, n), dtype=np.complex128)
        Mm[n_idx, jb] = coef[nm]
        Gp += (T_A[nm] - (T_phi[nm][right] - T_phi[nm][left])) @ Mm
        Phi_nodes += T_phi[nm] @ Mm
    if not want_phi_maps:
        return Gp, geom
    T_phi_m = _phi_tables(cen, cen, tan, H, k, a, omega)
    Phi_mids = np.zeros((n, n), dtype=np.complex128)
    for nm in ("const", "sin", "cos1"):
        Mm = np.zeros((n, n), dtype=np.complex128)
        Mm[n_idx, jb] = coef[nm]
        Phi_mids += T_phi_m[nm] @ Mm
    return Gp, geom, (Phi_nodes, Phi_mids, left, right)


def solve(s, V, want_phi_maps=False):
    built = build_half_razor(s, want_phi_maps)
    Gp, geom = built[0], built[1]
    rhs = np.zeros(geom["n_segs"], dtype=np.complex128)
    rhs[geom["feed_segs"][0]] = -V  # rows test int E.dl; the gap adds -V
    alpha = np.linalg.solve(Gp, rhs)
    return (alpha, geom) + built[2:]


def i_at_feed(s, geom, alpha):
    sv = s._basis_coefs(geom, s.k)
    st = sv["starts"]
    fed = geom["feed_segs"][0]
    ent = slice(st[fed], st[fed + 1])
    return np.sum((sv["sigma"][ent] * sv["AC"][ent]) * alpha[sv["jbasis"][ent]])


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
ROY_V = -404675.9j


def roy_solver(mhz):
    return SinusoidalSolver(
        wires=[np.array([p, q], float) for p, q, _ in ROY_WIRES],
        n_per_edge_per_wire=[[nn] for _, _, nn in ROY_WIRES],
        feeds=[(0, 270.0, 0j)],
        junctions=ROY_JUNCTIONS,
        wire_radius=0.005,
        wavelength=299.8 / mhz,
    )


def main():
    from momwire import BSplineSolver

    print("-- dipole sanity (10 m, 21 segs) --")
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
        alpha, geom = solve(s, 1.0 + 0j)
        zh = 1.0 / i_at_feed(s, geom, alpha)
        zb, _ = BSplineSolver(degree=2, **mkw).compute_impedance()
        print(
            f"  {mhz * 1e6:>10.0f} Hz  stock {z_stock:.4g}  "
            f"half-razor {zh:.4g}  bs2 {zb:.4g}"
        )

    print("-- Roy's coupled-loop model, frequency ladder --")
    for mhz in (0.05, 0.005, 0.0005, 0.00005, 0.000005):
        s6 = roy_solver(mhz)
        alpha, geom = solve(s6, ROY_V)
        i_src = i_at_feed(s6, geom, alpha)
        knots = [np.asarray(c) for c in s6.currents_at_knots(alpha)]
        loop = max(float(np.max(np.abs(0.5 * (c[:-1] + c[1:])))) for c in knots[1:])
        print(
            f"  {mhz * 1e6:>9.1f} Hz  I_src {abs(i_src):.4e} A"
            f"   max loop {loop:.4e} A   ratio {loop / abs(i_src):.4f}"
        )
    print("   (clean-lane truth: I_src proportional to f, ratio ~0.44-0.47;")
    print("    the FLAT ratio is the fix working; the I_src collapse below")
    print("    ~1 kHz is the checkerboard — see below)")

    print("-- the checkerboard, exhibited at 50 Hz --")
    s6 = roy_solver(0.00005)
    alpha, geom, (Phi_nodes, Phi_mids, left, right) = solve(
        s6, ROY_V, want_phi_maps=True
    )
    pn = Phi_nodes @ alpha
    pm = Phi_mids @ alpha
    fed = geom["feed_segs"][0]
    print("  segment | phi(left node) | phi(midpoint) | phi(right node) [Im, V]")
    for m in (0, 5, 12, fed, fed + 1, 20, 25, 30):
        print(
            f"   seg {m:2d}  {pn[left[m]].imag:+12.3e}  {pm[m].imag:+12.3e}"
            f"  {pn[right[m]].imag:+12.3e}"
        )
    print(
        "  node potentials: perfect plateaus with the exact drive jump at\n"
        "  the gap; midpoint potentials: near zero. The charge pattern that\n"
        "  does this is invisible to node-only testing — the basis's\n"
        "  intra-segment quadratic charge freedom pays for the plateaus\n"
        "  with ~200x too little net charge, so the input capacitance\n"
        "  collapses. Point matching and node differencing each control\n"
        "  half of phi; the NEC-2 basis needs both controlled at once."
    )


if __name__ == "__main__":
    main()
