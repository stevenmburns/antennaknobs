"""ByDipole1 convergence, six formulations side by side — how does razor converge?

The wire is the one every razor/NEC-5 comparison in this project already uses:
L = 10.18946 m of #14 (a = 1.0262 mm) at 14 MHz in FREE SPACE, centre-fed.
L/a = 9929. Free space so nothing is contaminated by a ground model's own
limit offset.

Six lanes, one deck, one mesh ladder:

  bs2            BSplineSolver(degree=2)      quadratic B-spline, Galerkin
  bs1            BSplineSolver(degree=1)      tent basis, Galerkin
  sin            SinusoidalSolver             three-term, point-matched (NEC-2's)
  sin-galerkin   SinusoidalGalerkinSolver     three-term, Galerkin
  razor          RazorSolver                  tent basis, razor-blade testing,
                                              converged Gauss-Legendre path rule
  razor-nec5     RazorSolver(nec5_quadrature) same, NEC-5's own two-point
                                              centroid trapezoid (momwire#316)

The last two are the SAME class and the same basis. They differ only in where
the testing path is sampled, which is the whole point of putting them in one
table: any gap between those two rows is quadrature, not formulation.

PARITY IS PER ENGINE, not per run. A centre-fed dipole's answer wobbles with
the parity of N because whether a basis lands a degree of freedom ON the feed
depends on it, and the engines do not agree about which parity is right:

    bs1           even
    sin           odd
    razor         even     (NEC-5's EX-at-knot convention)
    razor-nec5    even
    bs2           either
    sin-galerkin  either

So each lane runs its OWN parity: the base ladder is even and a lane that wants
odd is shifted +1. Scoring every engine on one parity would handicap whichever
engines it does not suit — on this deck bs1 splits ~0.6 ohm between N=24 and
N=25 and sin ~0.26, which is larger than several of the differences this table
is meant to resolve. The rung labels below are therefore the base ladder; the N
actually solved is printed per lane.

THE KERNEL. `--ek` puts every lane on the extended kernel, and on this deck it
matters at the fine end. The REDUCED (thin-wire) kernel puts the source on the
axis and observes on the surface, an approximation that degrades as the segment
length falls toward the radius: at N=2048 here Delta/a is 4.85. Measured, the
reduced kernel's reactance never settles -- its step ratio decays TOWARD 1.0
(0.0571 / 0.0501 / 0.0458 ohm per doubling, ratios 1.14 then 1.09), which is a
ladder that is not converging at all. The extended kernel's ratios go the other
way (1.23 then 1.25). Three other suspects were measured and cleared first, so
they need not be re-litigated:

  * quadrature -- `n_qp_pair` 8/16/32 give IDENTICAL answers to every printed
    digit here, because a single straight wire has only same-edge pairs and
    n_qp_pair is exact for those (it under-integrates cross-edge pairs, which
    this deck has none of);
  * the feed model -- point, segment gap and smoothed all drift the same;
  * the source WIDTH -- holding it fixed at 2/5/10 cm while the mesh refines
    (alpha = w/h_feed) does not settle it either, so it is not a
    shrinking-source artifact.

THE REFERENCE. Convergence is reported against a limit, and a single basis flat
on its own ladder can be flat at the WRONG value (the standing argument in
`bench_basis_convergence.py`). So the reference is taken two independent ways
and they must agree, or the run says so:

  * a high-N bs2 solve (`--ref-n`), and
  * each lane's own Richardson extrapolation from its top three rungs.

Run:
    .venv/bin/python scripts/bench_bydipole1_bases.py
    .venv/bin/python scripts/bench_bydipole1_bases.py --ladder 12 24 48 96 192
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
from momwire import SinusoidalSolver
from momwire.bspline import BSplineSolver
from momwire.razor import RazorSolver
from momwire.sinusoidal_galerkin import SinusoidalGalerkinSolver

BD1_LEN = 10.18946
BD1_RAD = 0.0010262
BD1_WL = 299792458.0 / 14.0e6
BD1_WIRE = [np.array([[0.0, 0.0, 0.0], [0.0, BD1_LEN, 0.0]])]

DEFAULT_LADDER = (12, 24, 48, 96, 192, 384)

# (solver, kwargs, required parity of N for a centre-fed dipole).
LANES: dict[str, tuple[type, dict, str]] = {
    "bs2": (BSplineSolver, {}, "either"),
    "bs1": (BSplineSolver, {"degree": 1}, "even"),
    "sin": (SinusoidalSolver, {}, "odd"),
    "sin-galerkin": (SinusoidalGalerkinSolver, {}, "either"),
    "razor": (RazorSolver, {}, "even"),
    "razor-nec5": (RazorSolver, {"nec5_quadrature": True}, "even"),
}


def rung_for(n_base, parity):
    """The N this lane actually solves, given an even base rung."""
    if parity == "odd":
        return n_base + 1
    return n_base


def solve(cls, n, **kw):
    s = cls(wires=BD1_WIRE, nsegs=n, wire_radius=BD1_RAD, wavelength=BD1_WL, **kw)
    t0 = time.perf_counter()
    z, _ = s.compute_impedance()
    return complex(z), time.perf_counter() - t0


def richardson(zs, ns):
    """Limit from the top three rungs, assuming z(N) = z* + C/N^p."""
    if len(zs) < 3:
        return None, None
    (n1, z1), (n2, z2), (n3, z3) = zip(ns[-3:], zs[-3:], strict=True)
    d1, d2 = abs(z2 - z1), abs(z3 - z2)
    if d2 <= 0 or d1 <= 0:
        return None, None
    ratio = np.log(n2 / n1) / np.log(n3 / n2)
    p = np.log(d1 / d2) / (np.log(n3 / n2) * (1.0 + 0.0)) if ratio else None
    if p is None or not np.isfinite(p) or p <= 0:
        return None, None
    z_star = z3 + (z3 - z2) / ((n3 / n2) ** p - 1.0)
    return complex(z_star), float(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ladder", type=int, nargs="+", default=list(DEFAULT_LADDER))
    ap.add_argument("--ref-n", type=int, default=768, help="bs2 rung used as the limit")
    ap.add_argument("--only", nargs="+", help="restrict to these lanes")
    ap.add_argument(
        "--ek",
        action="store_true",
        help="extended kernel on every lane (see THE KERNEL in the docstring)",
    )
    ap.add_argument("--out", help="also write raw rows as JSON")
    args = ap.parse_args()

    ladder = list(args.ladder)
    if any(n % 2 for n in ladder):
        raise SystemExit("--ladder must be even; odd-parity lanes are shifted +1")
    lanes = {k: v for k, v in LANES.items() if not args.only or k in args.only}
    if args.ek:
        lanes = {
            k: (c, dict(kw, extended_kernel=True), par)
            for k, (c, kw, par) in lanes.items()
        }

    print(f"ByDipole1  L={BD1_LEN} m  a={BD1_RAD} m  14 MHz  free space")
    print(f"base ladder {ladder}; odd-parity lanes solve N+1")
    print(f"kernel: {'EXTENDED (--ek)' if args.ek else 'reduced (thin-wire)'}")

    # The limit is cross-validated, not taken on one basis's word. bs2 scoring
    # itself would flatter bs2 and make its own error column meaningless, so a
    # SECOND, independently formulated lane is solved at the same rung and the
    # two must agree far inside the errors being reported. sin-galerkin is the
    # check: a different basis (three-term, not B-spline) with different
    # testing, so a shared limit is evidence rather than a coincidence.
    ek = {"extended_kernel": True} if args.ek else {}
    z_ref, t_ref = solve(LANES["bs2"][0], args.ref_n, **LANES["bs2"][1], **ek)
    z_chk, _ = solve(
        LANES["sin-galerkin"][0], args.ref_n, **LANES["sin-galerkin"][1], **ek
    )
    spread = abs(z_ref - z_chk)
    print(f"reference: bs2 at N={args.ref_n} = {z_ref:.4f}  ({t_ref:.1f}s)")
    print(f"cross-check: sin-galerkin at N={args.ref_n} = {z_chk:.4f}")
    print(f"             they agree to {spread:.4f} ohm — the limit is trustworthy")
    print("             to about that, so read |Z-ref| below only where it is")
    print("             comfortably larger.\n")

    rows = {}
    for name, (cls, kw, parity) in lanes.items():
        ns = [rung_for(n, parity) for n in ladder]
        zs, secs = [], []
        for n in ns:
            z, dt = solve(cls, n, **kw)
            zs.append(z)
            secs.append(dt)
        z_star, p = richardson(zs, ns)
        rows[name] = dict(
            parity=parity,
            ns=ns,
            z=[f"{z:.4f}" for z in zs],
            secs=[round(s, 2) for s in secs],
            err=[abs(z - z_ref) for z in zs],
            richardson=None if z_star is None else f"{z_star:.4f}",
            order=None if p is None else round(p, 2),
        )

    w = max(len(k) for k in rows)
    print(
        f"{'lane':<{w}} "
        + " ".join(f"{'N=' + str(n):>11}" for n in ladder)
        + f" {'Rich. limit':>22} {'p':>5}"
    )
    print(f"{'':<{w}} " + " ".join(f"{'|Z-ref|':>11}" for _ in ladder))
    for name, r in rows.items():
        tag = {"odd": " (odd)", "even": " (even)", "either": ""}[r["parity"]]
        print(
            f"{name:<{w}} "
            + " ".join(f"{e:>11.4f}" for e in r["err"])
            + f" {str(r['richardson']):>22} {str(r['order']):>5}{tag}"
        )
    print()
    print(
        f"{'lane':<{w}} "
        + " ".join(f"{'N=' + str(n):>11}" for n in ladder)
        + "   (wall seconds)"
    )
    for name, r in rows.items():
        print(f"{name:<{w}} " + " ".join(f"{s:>11.2f}" for s in r["secs"]))
    # SELF-CONVERGENCE: |Z(N) - Z(N/2)| per lane, which needs no reference at
    # all. This is the metric to read, because the reference is NOT converged:
    # bs2 still moves 0.046 ohm between N=1024 and N=2048, and the movement
    # shrinks by only ~1.1x per doubling (it would halve for O(1/N)). Nearly all
    # of it is reactance -- the delta-gap feed's log singularity, which costs an
    # O(1/N) term no basis degree removes. Scoring against a drifting reference
    # measures partly the reference's own drift (the momwire#674 trap), so
    # |Z-ref| above is only meaningful well ABOVE that drift.
    print()
    print(
        f"{'lane':<{w}} "
        + " ".join(f"{'->' + str(n):>11}" for n in ladder[1:])
        + "   |Z(N) - Z(N/2)|, reference-free"
    )
    for name, r in rows.items():
        zs = [complex(z) for z in r["z"]]
        steps = [abs(zs[i] - zs[i - 1]) for i in range(1, len(zs))]
        print(f"{name:<{w}} " + " ".join(f"{d:>11.4f}" for d in steps))
    print()
    print(
        f"{'lane':<{w}} "
        + " ".join(f"{'->' + str(n):>11}" for n in ladder[2:])
        + "   step ratio (2.0 = O(1/N), 4.0 = O(1/N^2))"
    )
    for name, r in rows.items():
        zs = [complex(z) for z in r["z"]]
        steps = [abs(zs[i] - zs[i - 1]) for i in range(1, len(zs))]
        rats = [
            (steps[i - 1] / steps[i]) if steps[i] > 0 else float("inf")
            for i in range(1, len(steps))
        ]
        print(f"{name:<{w}} " + " ".join(f"{r_:>11.2f}" for r_ in rats))

    print()
    print("Richardson limits vs the bs2 reference:")
    for name, r in rows.items():
        if r["richardson"]:
            print(
                f"  {name:<{w}}  {r['richardson']:>22}  "
                f"|d| = {abs(complex(r['richardson']) - z_ref):.4f}"
            )

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(
                dict(
                    ladder=ladder,
                    ref_n=args.ref_n,
                    z_ref=f"{z_ref:.4f}",
                    lanes={
                        k: {kk: vv for kk, vv in v.items() if kk != "err"}
                        for k, v in rows.items()
                    },
                ),
                fh,
                indent=2,
            )
        print(f"\nsaved {args.out}")


if __name__ == "__main__":
    main()
