"""Half-razor prototype: NEC-2 basis, phi tested by end-difference.

The dissection (pathology_dissect.py + the stub/radius ladder) pinned the
sin lane's loop residual to the TESTING side: point matching samples E at
segment midpoints, so the loop sum of tested equations is a midpoint-rule
quadrature of the closed integral of grad phi — whose error is O(local phi
scale) wherever the junction basis makes phi vary on the segment scale,
and which rides 1/omega. The clean schemes never quadrature that integral:
pulse differences phi across segment ends, razor/NEC-5 integrate E dl.

Smallest change, prototyped here OUTSIDE momwire: keep the NEC-2 3-term
basis and its junction conditions (seg_view straight from the solver),
keep midpoint collocation for the smooth -j*omega*A part, but test the
scalar potential as an exact end-difference phi(r) - phi(l), with phi
evaluated once per unique NODE POSITION (a scalar field value — shared by
every segment meeting there), so any closed-loop sum telescopes by
construction.

Row m tests the E.dl integral over segment m:
    sum_n [ -j*omega*h_m*(t_m . t_n)*(mu/4pi)*Int_shape(mid_m, n)
            - (phi_shape(node_r(m), n) - phi_shape(node_l(m), n)) ]
phi of a shape I on segment n (reduced kernel, radius a):
    (1/(4pi*eps*j*omega)) * [ I(+H)G_a(R2) - I(-H)G_a(R1)
                              - int I'(z') G_a dz' ]

Checks:
  1. sanity: a plain dipole's Z vs the stock sinusoidal solver;
  2. the loop-circulation functional under the new rows (expect the phi
     part gone — telescoping — leaving only the small omega-side term);
  3. Roy's model at 500 Hz: source and loop currents vs the clean lanes;
  4. the 1/f ratio sweep, stock vs half-razor.

Run: .venv/bin/python scratch/qrz-lfa-thread/half_razor_proto.py
"""

import numpy as np
from momwire.sinusoidal import SinusoidalSolver

MU = 1.25663706127e-6
EPS = 8.8541878188e-12
C0 = 299792458.0

GX48, GW48 = np.polynomial.legendre.leggauss(48)


def _g_a(r2, a):
    """Regularized reduced-kernel Green's fn e^{-jkr_a}/r_a, r_a=sqrt(r2+a2)."""
    return r2, a


def build_half_razor(s):
    """Assemble the half-razor matrix for a configured SinusoidalSolver.

    Returns (Gp, geom, nodes) where Gp[m, j] tests basis j's E.dl integral
    over segment m, and nodes maps segment ends to unique node ids.
    """
    geom = s._build_geometry()
    k = s.k
    omega = C0 * k
    n = geom["n_segs"]
    a = s._uniform_radius
    cen = geom["seg_centers"]
    tan = geom["seg_tangents"]
    h = geom["seg_h"]
    seg_l = cen - 0.5 * h[:, None] * tan
    seg_r = cen + 0.5 * h[:, None] * tan

    # unique node table (1e-9 snap, the solver's own junction tolerance)
    node_pos = []
    node_of = {}

    def node_id(p):
        key = tuple(np.round(p / 1e-9).astype(np.int64))
        if key not in node_of:
            node_of[key] = len(node_pos)
            node_pos.append(p)
        return node_of[key]

    left_node = np.array([node_id(p) for p in seg_l])
    right_node = np.array([node_id(p) for p in seg_r])
    nodes = np.array(node_pos)

    H = 0.5 * h  # source half-lengths

    # quadrature points per source segment, z' in [-H, +H]
    zq = H[:, None] * GX48[None, :]  # (n, q)
    pq = cen[:, None, :] + zq[..., None] * tan[:, None, :]  # (n, q, 3)

    shp = {
        "const": (np.ones_like(zq), np.zeros_like(zq), 1.0, 1.0),
        "sin": (np.sin(k * zq), k * np.cos(k * zq), np.sin(k * H), np.sin(-k * H)),
        "cos": (np.cos(k * zq), -k * np.sin(k * zq), np.cos(k * H), np.cos(-k * H)),
    }
    # (I(z'), I'(z'), I(+H), I(-H)) per shape; end values broadcast per seg
    shp = {
        name: (v, d, np.broadcast_to(e2, H.shape), np.broadcast_to(e1, H.shape))
        for name, (v, d, e2, e1) in shp.items()
    }

    def g_at(obs, src_pts):
        """G_a table: obs (M,3) x src_pts (n,q,3) -> (M,n,q)."""
        d = obs[:, None, None, :] - src_pts[None, :, :, :]
        r2 = (d * d).sum(-1)
        ra = np.sqrt(r2 + a * a)
        return np.exp(-1j * k * ra) / ra

    # ---- A part: Int shape * G_a at segment midpoints ----------------------
    Gq_mid = g_at(cen, pq)  # (n_obs, n_src, q)
    # singularity extraction for the self/near 1/r spike: subtract shape(z0)/ra
    # where z0 = axial coordinate of the observer in the source frame,
    # and add back the arcsinh closed form times shape(z0).
    rel = cen[:, None, :] - cen[None, :, :]
    z0 = np.einsum("mnd,nd->mn", rel, tan)  # obs axial coord in src frame
    rho2 = (rel * rel).sum(-1) - z0 * z0
    rho2 = np.maximum(rho2, 0.0)
    rho_a = np.sqrt(rho2 + a * a)
    u2 = (H[None, :] - z0) / rho_a
    u1 = (-H[None, :] - z0) / rho_a
    int_inv = np.arcsinh(u2) - np.arcsinh(u1)  # closed form of int 1/r_a

    A_int = {}
    for name, (val, _d, _e2, _e1) in shp.items():
        # shape value at the observer's axial foot, clamped into the segment
        zc = np.clip(z0, -H[None, :], H[None, :])
        if name == "const":
            f0 = np.ones_like(z0)
        elif name == "sin":
            f0 = np.sin(k * zc)
        else:
            f0 = np.cos(k * zc)
        ra_q = np.sqrt(
            ((cen[:, None, None, :] - pq[None, :, :, :]) ** 2).sum(-1) + a * a
        )
        reg = val[None, :, :] * Gq_mid - f0[..., None] / ra_q
        A_int[name] = (reg * GW48[None, None, :]).sum(-1) * H[None, :] + f0 * int_inv

    td = tan @ tan.T  # (m, n)
    T_A = {
        name: (-1j * omega * MU / (4 * np.pi)) * h[:, None] * td * A_int[name]
        for name in A_int
    }

    # ---- phi part: potential at unique nodes -------------------------------
    d_end2 = nodes[:, None, :] - seg_r[None, :, :]
    d_end1 = nodes[:, None, :] - seg_l[None, :, :]
    Ga2 = np.exp(-1j * k * np.sqrt((d_end2**2).sum(-1) + a * a)) / np.sqrt(
        (d_end2**2).sum(-1) + a * a
    )
    Ga1 = np.exp(-1j * k * np.sqrt((d_end1**2).sum(-1) + a * a)) / np.sqrt(
        (d_end1**2).sum(-1) + a * a
    )
    Gq_nod = g_at(nodes, pq)  # (n_nodes, n_src, q)

    reln = nodes[:, None, :] - cen[None, :, :]
    z0n = np.einsum("mnd,nd->mn", reln, tan)
    rho2n = (reln * reln).sum(-1) - z0n * z0n
    rho2n = np.maximum(rho2n, 0.0)
    rho_an = np.sqrt(rho2n + a * a)
    int_inv_n = np.arcsinh((H[None, :] - z0n) / rho_an) - np.arcsinh(
        (-H[None, :] - z0n) / rho_an
    )

    pref_phi = 1.0 / (4 * np.pi * EPS * 1j * omega)
    T_phi = {}
    for name, (val, dv, e2, e1) in shp.items():
        if name == "const":
            line = 0.0  # I' = 0: endpoint charges only
        else:
            zcn = np.clip(z0n, -H[None, :], H[None, :])
            f0n = (k * np.cos(k * zcn)) if name == "sin" else (-k * np.sin(k * zcn))
            ra_qn = np.sqrt(
                ((nodes[:, None, None, :] - pq[None, :, :, :]) ** 2).sum(-1) + a * a
            )
            regn = dv[None, :, :] * Gq_nod - f0n[..., None] / ra_qn
            line = (regn * GW48[None, None, :]).sum(-1) * H[None, :] + f0n * int_inv_n
        T_phi[name] = pref_phi * (e2[None, :] * Ga2 - e1[None, :] * Ga1 - line)

    # ---- assemble G' -------------------------------------------------------
    sv = s._basis_coefs(geom, k)
    starts, jb = sv["starts"], sv["jbasis"]
    sig = sv["sigma"]
    n_idx = np.repeat(np.arange(n), starts[1:] - starts[:-1])
    coef = {"const": sig * sv["A"], "sin": sv["B"], "cos": sig * sv["C"]}

    Gp = np.zeros((n, n), dtype=np.complex128)
    for name in ("const", "sin", "cos"):
        M = np.zeros((n, n), dtype=np.complex128)
        M[n_idx, jb] = coef[name]
        rowfield = T_A[name] - (T_phi[name][right_node] - T_phi[name][left_node])
        Gp += rowfield @ M
    return Gp, geom, (left_node, right_node)


def solve_half_razor(s, V):
    """Solve with a delta-gap V on the solver's configured feed segment."""
    Gp, geom, _ = build_half_razor(s)
    fed = geom["feed_segs"][0]
    rhs = np.zeros(geom["n_segs"], dtype=np.complex128)
    rhs[fed] = -V  # tested quantity is int E.dl; the gap contributes -V
    alpha = np.linalg.solve(Gp, rhs)
    return alpha, Gp, geom


def knot_currents(s, alpha):
    return [np.asarray(c) for c in s.currents_at_knots(alpha)]


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    WLR = 299.8 / 0.0005
    RADIUS = 0.005

    # ---- 1. sanity: dipole impedance vs stock solver at 15 MHz ------------
    L, nseg = 10.0, 21
    wl15 = 299.8 / 15.0
    mk = dict(
        wires=[np.array([[0, 0, 0], [0, L, 0]], float)],
        n_per_edge_per_wire=[[nseg]],
        feeds=[(0, L / 2, 1.0 + 0j)],
        wire_radius=0.001,
        wavelength=wl15,
    )
    s = SinusoidalSolver(**mk)
    z_stock, _ = s.compute_impedance()
    alpha, Gp, geom = solve_half_razor(s, 1.0 + 0j)
    fed = geom["feed_segs"][0]
    sv = s._basis_coefs(geom, s.k)
    # current at the fed segment centre from the basis view
    st = sv["starts"]
    ent = slice(st[fed], st[fed + 1])
    i_fed = np.sum(
        (sv["sigma"][ent] * sv["A"][ent] + sv["sigma"][ent] * sv["C"][ent])
        * alpha[sv["jbasis"][ent]]
    )
    print(f"dipole 15 MHz: stock Z {z_stock:.2f}  half-razor Z {1.0 / i_fed:.2f}")

    # ---- 2 + 3. Roy's model ----------------------------------------------
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

    def roy_solver(mhz, k_ref=1):
        return SinusoidalSolver(
            wires=[np.array([p0, p1], float) for p0, p1, _ in W],
            n_per_edge_per_wire=[[nn * k_ref] for _, _, nn in W],
            feeds=[(0, 280.0 - 10.0 / k_ref, 0j)],
            junctions=J6,
            wire_radius=RADIUS,
            wavelength=299.8 / mhz,
        )

    for mhz in (0.05, 0.0005, 0.000005):
        s6 = roy_solver(mhz)
        alpha, Gp, geom = solve_half_razor(s6, V)
        knots = knot_currents(s6, alpha)
        i_src = None
        # source current = current at the fed segment centre
        sv = s6._basis_coefs(geom, s6.k)
        st = sv["starts"]
        fed = geom["feed_segs"][0]
        ent = slice(st[fed], st[fed + 1])
        i_src = np.sum(
            (sv["sigma"][ent] * sv["A"][ent] + sv["sigma"][ent] * sv["C"][ent])
            * alpha[sv["jbasis"][ent]]
        )
        loop = max(float(np.max(np.abs(0.5 * (c[:-1] + c[1:])))) for c in knots[1:])
        print(
            f"Roy {mhz * 1e6:>9.1f} Hz  half-razor: I_src {abs(i_src):.4e} A"
            f"   max loop {loop:.4e} A   ratio {loop / abs(i_src):.4f}"
        )
