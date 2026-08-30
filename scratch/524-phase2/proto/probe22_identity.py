"""A-2 session 5, probe 22 — GATE 1: the by-parts identities' NODE rows on
designed kernels at rho = a (DERIVATION-NEAR-INTERFACE.md §4, ledger 22).

Two exact 1-D identities, both sides from the SAME designed tables, with
log-graded quadrature toward the node so the continuum content is resolved
(finite at rho = a — the §3 radius rule):

  V:  int int f_m f_n dzpV  ==  int int f'_m f'_n V
                                - SUM_E  sig  f_m(E) int f'_n V(E,.)
                                - SUM_E' sig' f_n(E') int f'_m V(.,E')
                                + SUM SUM sig sig' f_m(E) f_n(E') V(E,E')
  W:  int int f_m f_n dzpW  ==  SUM_E' sig' f_n(E') int f_m W(.,E')
                                - int int f_m f'_n W

x1 crossing-deck scales: above arm h_a = 2/3 (15 segs on [0,10]), below
arm h_b = 0.5 (4 segs on [-2,0]), a = 1e-3. Test bases (above): node tent
(sig = -1 at z=0) + interior tent; source bases (below): node tent
(sig' = +1 at z'=0) + interior tent. Interior x interior = the floor;
GATE = node rows close to that floor class.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe22_identity.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from numpy.polynomial.legendre import leggauss

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import corner_tables as ct  # noqa: E402

WL7 = 42.83100850350743
K_P = 2.0 * np.pi / WL7
OMEGA = 2.0 * np.pi * 7.0e6
EPS0 = 8.8541878128e-12
EPS_T = 13.0 - 1j * 0.005 / (OMEGA * EPS0)
A = 1e-3
H_A = 10.0 / 15.0
H_B = 0.5
RTOL = 1e-9

GX8, GW8 = leggauss(8)


def graded_panels(lo, hi, grade_at_lo, a=A):
    """Panel edges on [lo, hi]; log-graded from the `lo` end (scale a,
    doubling) if grade_at_lo, else uniform-ish coarse panels."""
    if not grade_at_lo:
        return np.linspace(lo, hi, 7)
    edges = [lo]
    step = a
    while edges[-1] + step < hi:
        edges.append(edges[-1] + step)
        step *= 2.0
    edges.append(hi)
    return np.array(edges)


def quad_nodes(edges):
    mid = 0.5 * (edges[:-1] + edges[1:])
    half = 0.5 * (edges[1:] - edges[:-1])
    x = (mid[:, None] + half[:, None] * GX8[None, :]).ravel()
    w = (half[:, None] * GW8[None, :]).ravel()
    return x, w


# --- bases: (value fn, deriv fn, support, end value at the node, sigma) ----
def tent(peak, h):
    lo, hi = peak - h, peak + h

    def f(x):
        return np.clip(1.0 - np.abs(x - peak) / h, 0.0, None)

    def fd(x):
        return np.where(
            (x >= lo) & (x < peak),
            1.0 / h,
            np.where((x >= peak) & (x <= hi), -1.0 / h, 0.0),
        )

    return f, fd


BASES_ABOVE = {
    # node tent: support [0, H_A], f(0) = 1, near end at the node -> sigma -1
    "nodeA": dict(
        f=lambda z: np.clip(1.0 - z / H_A, 0.0, None),
        fd=lambda z: np.where((z >= 0) & (z <= H_A), -1.0 / H_A, 0.0),
        lo=0.0,
        hi=H_A,
        f_node=1.0,
        sig=-1.0,
        graded=True,
    ),
    "intA": dict(
        f=tent(2.0 * H_A, H_A)[0],
        fd=tent(2.0 * H_A, H_A)[1],
        lo=H_A,
        hi=3.0 * H_A,
        f_node=0.0,
        sig=0.0,
        graded=False,
    ),
}
BASES_BELOW = {
    # node tent: support [-H_B, 0], f(0) = 1, far end at the node -> sigma +1
    "nodeB": dict(
        f=lambda z: np.clip(1.0 + z / H_B, 0.0, None),
        fd=lambda z: np.where((z >= -H_B) & (z <= 0), 1.0 / H_B, 0.0),
        lo=-H_B,
        hi=0.0,
        f_node=1.0,
        sig=+1.0,
        graded=True,
    ),
    "intB": dict(
        f=tent(-1.0, H_B)[0],
        fd=tent(-1.0, H_B)[1],
        lo=-1.5,
        hi=-0.5,
        f_node=0.0,
        sig=0.0,
        graded=False,
    ),
}


def tab(z, zp):
    """Designed tables at rho = a on the (z, zp) grid; returns dict of
    (nz, nzp) arrays."""
    zg, zpg = np.meshgrid(z, zp, indexing="ij")
    return ct.designed_tables(EPS_T, K_P, A, zg, zpg, rtol=RTOL)


def main():
    t_start = time.time()
    out = {}
    # quadrature per axis
    qa = {}
    for name, b in BASES_ABOVE.items():
        x, w = quad_nodes(graded_panels(b["lo"], b["hi"], b["graded"]))
        qa[name] = (x, w, b)
    qb = {}
    for name, b in BASES_BELOW.items():
        x, w = quad_nodes(graded_panels(-b["hi"], -b["lo"], b["graded"]))
        # below axis: graded toward z' = 0 -> build on |z'| then negate
        xq = -x
        qb[name] = (xq, w, b)

    corner = ct.six_point(EPS_T, K_P, A, 0.0, 0.0, rtol=RTOL)
    iV, iW, idzpV, idzpW = 1, 2, 4, 5  # noqa: F841 — kept: names the quantity the probe computed, read when inspecting

    res = {}
    for na, (za, wa, ba) in qa.items():
        for nb, (zb, wb, bb) in qb.items():
            t0 = time.time()
            T = tab(za, zb)
            fa, fda = ba["f"](za), ba["fd"](za)
            fb, fdb = bb["f"](zb), bb["fd"](zb)

            lhs_V = (fa * wa) @ T["dzpV"] @ (fb * wb)
            rhs_V = (fda * wa) @ T["V"] @ (fdb * wb)
            lhs_W = (fa * wa) @ T["dzpW"] @ (fb * wb)
            rhs_W = -((fa * wa) @ T["W"] @ (fdb * wb))

            # end terms (only the node ends carry basis value)
            if ba["sig"] != 0.0:
                e = ct.designed_tables(EPS_T, K_P, A, np.zeros_like(zb), zb, rtol=RTOL)
                rhs_V += -ba["sig"] * ba["f_node"] * np.dot(fdb * wb, e["V"])
            if bb["sig"] != 0.0:
                e = ct.designed_tables(EPS_T, K_P, A, za, np.zeros_like(za), rtol=RTOL)
                rhs_V += -bb["sig"] * bb["f_node"] * np.dot(fda * wa, e["V"])
                rhs_W += bb["sig"] * bb["f_node"] * np.dot(fa * wa, e["W"])
            if ba["sig"] != 0.0 and bb["sig"] != 0.0:
                rhs_V += (
                    ba["sig"]
                    * bb["sig"]
                    * ba["f_node"]
                    * bb["f_node"]
                    * complex(corner[iV])
                )

            res[f"{na}x{nb}"] = dict(
                lhs_V=lhs_V,
                rhs_V=rhs_V,
                lhs_W=lhs_W,
                rhs_W=rhs_W,
                secs=time.time() - t0,
            )
            print(
                f"{na} x {nb}: V lhs {lhs_V:.6e} rhs {rhs_V:.6e} | "
                f"W lhs {lhs_W:.6e} rhs {rhs_W:.6e}  "
                f"({res[f'{na}x{nb}']['secs']:.0f}s)",
                flush=True,
            )

    scale_V = max(abs(r["lhs_V"]) for r in res.values())
    scale_W = max(abs(r["lhs_W"]) for r in res.values())
    print(f"\nscales: V {scale_V:.4e}, W {scale_W:.4e}")
    for key, r in res.items():
        dv = abs(r["lhs_V"] - r["rhs_V"]) / scale_V
        dw = abs(r["lhs_W"] - r["rhs_W"]) / scale_W
        out[key] = dict(V_rel=f"{dv:.3e}", W_rel=f"{dw:.3e}")
        print(f"  {key:>12}:  V {dv:.3e}   W {dw:.3e}")

    (HERE.parent / "results" / "probe22-identity.json").write_text(
        json.dumps(out, indent=1)
    )
    print(f"\nsaved results/probe22-identity.json ({time.time() - t_start:.0f}s total)")


if __name__ == "__main__":
    main()
