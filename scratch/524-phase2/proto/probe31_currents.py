"""A-2 session 6, probe 31 — momwire-complete's junction currents vs the
engine's (adjudicator 1, current level).

probe30 measured the engine side from the phase-0 captures: I(0+) stable
~ 1.14-0.03j (= its contact-mono base), I(0-) ANTIPHASE and diverging
~ sqrt(n) (KCL deficit 1.55 -> 2.23 A x1 -> x8), slope ratio sweeping
THROUGH the AGARD value without settling. The engine's junction is two
independent contact ends, not an AGARD junction.

This probe prints the same observables for the probe27 complete+split
solve (cached blocks, g1 + g2): I(0-), I(0+), one-sided slopes, the
AGARD ratio, the feed current, and the current profile on both arms.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe31_currents.py [level ...]
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
from probe1_baseline import seeded  # noqa: E402
from probe2_crossing import node_rows  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402
from probe19_graded_mpb import crossing_graded  # noqa: E402
from probe27_complete import cross_complete, self_complete_hook  # noqa: E402

A_WIRE = 0.001
ct.install(wire_radius=A_WIRE)

# engine junction numbers from probe30 (x5 rung, converged Z; x8 for trend)
ENGINE = {
    "I0_plus_x5": 1.1418 - 0.0254j,
    "I0_minus_x5": -0.8246 + 0.2747j,
    "I0_plus_x8": 1.1297 - 0.0243j,
    "I0_minus_x8": -1.0686 + 0.3412j,
}


def eval_rows(s, geom, z_targets):
    """Rows r such that r @ sol = I(z) for points on either arm.

    z < 0 -> below wire (wire 0), z > 0 -> above wire (wire 1).
    """
    supp_seg, polys, _kcl, _wk, _wbg = s._build_basis_polynomials(geom)
    n_basis = supp_seg.shape[0]
    n0 = int(geom["seg_offsets"][1])
    h = geom["h_per_seg"]
    # segment z-ranges: wire 0 runs -2 -> 0 over segs 0..n0-1; wire 1 runs
    # 0 -> 10 over segs n0..
    z_lo = np.empty(len(h))
    z = -2.0
    for i in range(n0):
        z_lo[i] = z
        z += h[i]
    z = 0.0
    for i in range(n0, len(h)):
        z_lo[i] = z
        z += h[i]
    rows = []
    for zt in z_targets:
        if zt < 0:
            segs = range(n0)
        else:
            segs = range(n0, len(h))
        seg = None
        for i in segs:
            if z_lo[i] - 1e-12 <= zt <= z_lo[i] + h[i] + 1e-12:
                seg = i
                break
        assert seg is not None, zt
        u = zt - z_lo[seg]
        r = np.zeros(n_basis)
        for m in range(n_basis):
            for wing in range(supp_seg.shape[1]):
                a = polys[m, wing]
                if not np.any(a):
                    continue
                if int(supp_seg[m, wing]) == seg:
                    r[m] += sum(a[p] * u**p for p in range(len(a)))
        rows.append(r)
    return np.array(rows)


def cfmt(z):
    return f"{z.real:+.4f}{z.imag:+.4f}j"


def main():
    levels = [int(x) for x in sys.argv[1:]] or [1, 2]
    out = {}
    for lv in levels:
        s = seeded(crossing_graded(lv))
        geom = s._build_geometry()
        below = s._below_segments(geom)
        b_seg = np.sort(np.nonzero(below)[0])
        a_seg = np.sort(np.nonzero(~below)[0])
        nb, na = node_indices(s, geom)

        t_A, _corner = cross_complete(s, lv)
        d_self = self_complete_hook(s, geom)

        def corr_hook(Zp, add=d_self):
            return Zp + add

        # stash the production solution vector
        sol_box = {}
        orig_true = BSplineSolver._solve_with_kcl

        def stashing(self, Z, v, kcl_A, overwrite=False):
            r = orig_true(self, Z, v, kcl_A, overwrite=False)
            sol_box["sol"] = np.array(r, copy=True)
            sol_box["v"] = np.array(v, copy=True)
            return r

        BSplineSolver._solve_with_kcl = stashing
        try:
            t0 = time.time()
            st = capture(
                seeded(crossing_graded(lv)),
                t_ab=t_A,
                a_seg=a_seg,
                b_seg=b_seg,
                z_hook=corr_hook,
            )
        finally:
            BSplineSolver._solve_with_kcl = orig_true
        sol = sol_box["sol"]
        z_in = st["z_in"]
        print(
            f"\n== g{lv}: complete+split Z = {z_in:.4f} "
            f"({time.time() - t0:.0f}s), n_basis = {sol.shape[0]}, "
            f"nb={nb} na={na}"
        )

        row_v, der_a, der_b = node_rows(s, geom)
        I0m, I0p = complex(sol[nb]), complex(sol[na])
        Ipm = complex(der_b @ sol)
        Ipp = complex(der_a @ sol)
        eps_t, _em, _kp, _km, _c2, _am = s._buried_medium()
        agard = 1.0 / eps_t

        # feed current for normalization (feed at z = 4.3333 on the above arm)
        zf = 4.3333333333
        r_feed = eval_rows(s, geom, [zf])
        I_feed = complex(r_feed[0] @ sol)

        print(f"  I(feed {zf:.2f} m) = {cfmt(I_feed)}  |.| = {abs(I_feed):.4f}")
        print(f"  I(0-) = {cfmt(I0m)}   I(0+) = {cfmt(I0p)}")
        print(f"  continuity I(0+)/I(0-) = {cfmt(I0p / I0m)}")
        print(f"  KCL deficit = {cfmt(I0p - I0m)}  |.| = {abs(I0p - I0m):.2e}")
        print(f"  I'(0-) = {cfmt(Ipm)}   I'(0+) = {cfmt(Ipp)}")
        sr = Ipp / Ipm
        print(
            f"  slope ratio I'+/I'- = {cfmt(sr)}  |.| = {abs(sr):.5f}"
            f"   AGARD 1/eps_t = {cfmt(agard)}  |.| = {abs(agard):.5f}"
        )
        print(
            f"  normalized I(0)/I(feed) = {cfmt(I0p / I_feed)}  "
            f"|.| = {abs(I0p / I_feed):.4f}   [engine x5: "
            f"I(0+)/1A = {cfmt(ENGINE['I0_plus_x5'])}]"
        )

        # profile on both arms
        z_prof = [
            -1.9,
            -1.5,
            -1.0,
            -0.5,
            -0.25,
            -0.1,
            -0.05,
            0.05,
            0.1,
            0.25,
            0.5,
            1.0,
            2.0,
            4.3333333333,
            6.0,
            8.0,
            9.5,
        ]
        rows = eval_rows(s, geom, z_prof)
        prof = rows @ sol
        print("  profile (z [m], I norm to feed):")
        for zt, I in zip(z_prof, prof, strict=True):
            In = I / I_feed
            print(
                f"    z = {zt:+8.3f}   I = {cfmt(In)}   |I| = {abs(In):.4f}"
                f"   phase {np.degrees(np.angle(In)):+7.2f}"
            )

        out[f"g{lv}"] = dict(
            z_in=f"{z_in:.4f}",
            I_feed=str(I_feed),
            I0_minus=str(I0m),
            I0_plus=str(I0p),
            dI_minus=str(Ipm),
            dI_plus=str(Ipp),
            slope_ratio=str(sr),
            agard=str(complex(agard)),
            kcl_deficit=str(I0p - I0m),
            profile={
                f"{zt:+.4f}": str(complex(I / I_feed))
                for zt, I in zip(z_prof, prof, strict=True)
            },
        )

    fp = HERE.parent / "results" / "probe31-currents.json"
    fp.write_text(json.dumps(out, indent=1))
    print(f"\nsaved {fp}")


if __name__ == "__main__":
    main()
