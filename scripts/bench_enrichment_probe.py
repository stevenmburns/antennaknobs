"""Singular-enrichment probe over the #521 junction-residue cluster (issue #565).

momwire #167 made the K≥3 singular-enrichment bases (T/X-junction bases,
``enrichment_min_k=3``) work over EVERY ground — PEC image, fast finite
(refl-coef), and Sommerfeld — via the image-reaction blocks. Before it,
``BSplineSolver(use_singular_enrichment=True, ground_z=...)`` raised
``NotImplementedError``; grounded studies of the junction cluster were locked
out. This tool is the direct probe that #521 asked for and could not run.

#521's no-mutual-limit residue cluster — **hentenna, hourglass, discone** and
their arrays — is the singular-enrichment target family: T-junctions (hentenna
feed↔loop), a degree-4 X-crossing (hourglass), an apex fan (discone), with the
sin↔bs2 disagreement concentrated in REACTANCE. #521 names junction-collocation
as the prime suspect but calls it "not yet demonstrated" for these
mid-structure junctions. Singular enrichment is a Galerkin correction at exactly
those junctions: on the free-space hentenna it flips R/X convergence from
O(1/N) to ~O(1/N^(d+1)) (momwire ``test_bspline_d2_hentenna_singular_enrichment``).

For each cluster design this solves the driving-point impedance (feed 0) up a
mesh ladder on THREE bases — sinusoidal, BSpline-d2 (Galerkin), and
**BSpline-d2 + singular enrichment** — over free space AND ground (PEC plus a
finite model at a chosen height). It then scores the discriminator:

  * the sin↔bs2 REACTANCE gap (the #521 disagreement) at the finest rung;
  * whether enrichment MOVES the bs2 value — toward sin (junction collocation
    corrupts bs2 too) or barely at all (bs2 already holds the Galerkin limit);
  * the fitted convergence rate p in Z(N)=Z_inf + C/N^p for bs2 and bs2+enr
    (the O(1/N^(d+1)) claim) via three-point Richardson on X.

Two confounds this tool is built to respect (issue #565 step 4):

  * ``enrichment_variant="auto"`` SUPPRESSES enrichment on several of these
    catalog designs (the auto tap-ratio gate decides the junction is already
    resolved and returns the plain-bs2 matrix bit-for-bit). The probe therefore
    defaults to ``raw`` — the honest "enrichment always on at K≥3" variant —
    with ``--variant`` to switch. A no-op result must mean "enrichment did
    nothing here", never "auto turned it off".
  * a design's FEED PLACEMENT gates how much a junction correction reaches the
    driving point. The catalog hentenna feeds mid-wire, far from its two K=3
    rails, so ``raw`` moves X by ~0.1 Ω at N=21 — versus ~5.6 Ω in the bare
    momwire test whose feed stub attaches AT the junction. That is a real
    geometry effect, not a bug; the report states the shift so it is not misread.

Δ/a discipline (issue #484): rungs past a design's thin-wire headroom
(``bench_delta_a_headroom.n_max``) are skipped and recorded for every basis —
below the floor the reduced kernel is ill-posed and both bases answer nonsense.
The cluster's thin-wire designs clear ~2600, so the default ladder is unclamped.

    python scripts/bench_enrichment_probe.py
    python scripts/bench_enrichment_probe.py --ladder 21 41 81 161 --grounds free pec
    python scripts/bench_enrichment_probe.py --only specialty.hentenna --variant stable
    python scripts/bench_enrichment_probe.py --height-wl 0.05 --grounds sommerfeld refl-coef
"""

from __future__ import annotations

# libgomp reads these once, before numpy/momwire load (mirrors bench_converge).
import os

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import resource  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_converge as bc  # noqa: E402 — load_design / total_nominal_segs
import bench_delta_a_headroom as dah  # noqa: E402 — Δ/a headroom clamp (#484)

# The #521 no-mutual-limit junction-residue cluster (issue #565): T-junctions
# (hentenna feed↔loop), a degree-4 X-crossing (hourglass), an apex fan
# (discone), and their arrays.
CLUSTER = (
    "specialty.hentenna",
    "arrays.hentenna_array",
    "specialty.hentenna_slant",
    "specialty.hourglass",
    "specialty.hourglass_slant",
    "arrays.hourglass_array",
    "broadband.discone",
)

# Geometric ladder (doubling), matching the momwire enrichment test's rungs so
# the three-point Richardson rate is directly comparable to its p≈2.74.
DEFAULT_LADDER = (21, 41, 81, 161)
DEFAULT_SEG_CAP = 6000
DEFAULT_MEM_GB = 8.0
# Average-ground medium (NEC "average": eps_r 13, sigma 0.005 S/m).
DEFAULT_EPS_R = 13.0
DEFAULT_SIGMA = 0.005
DEFAULT_HEIGHT_WL = 0.1  # lowest wire this many wavelengths above the plane
# sin, bs2 (Galerkin), bs2+enrichment.
ENGINES = ("sin", "bs2", "bs2enr")

C_LIGHT = 299_792_458.0


def structure_min_z(builder_cls, nseg: int) -> float:
    """Lowest z over every wire polyline at ``nominal_nsegs=nseg``. The ground
    plane is placed a fixed height below this so the whole structure sits above
    it (momwire rejects a plane cutting through a wire)."""
    from antennaknobs.geometry import flat_wires_to_polylines

    import numpy as np

    b = builder_cls()
    b.nominal_nsegs = nseg
    tr = flat_wires_to_polylines(b.build_wires())
    return min(float(np.asarray(p)[:, 2].min()) for p in tr["polylines"])


def ground_spec(kind: str, eps_r: float, sigma: float):
    """Map a scenario key to the MomwireEngine ``ground`` argument.
    ``sommerfeld`` -> true finite ground (NEC gn 2); ``refl-coef`` -> the
    reflection-coefficient approximation (NEC gn 0)."""
    if kind == "free":
        return None
    if kind == "pec":
        return "pec"
    if kind == "sommerfeld":
        return ("finite", eps_r, sigma)
    if kind == "refl-coef":
        return ("finite-fast", eps_r, sigma)
    raise ValueError(f"unknown ground scenario {kind!r}")


def solver_kwargs(engine: str, variant: str) -> tuple:
    """(momwire solver class, solver_kwargs) for an engine key."""
    from momwire import BSplineSolver, SinusoidalSolver

    if engine == "sin":
        return SinusoidalSolver, {}
    if engine == "bs2":
        return BSplineSolver, {"degree": 2}
    if engine == "bs2enr":
        return BSplineSolver, {
            "degree": 2,
            "use_singular_enrichment": True,
            "enrichment_variant": variant,
        }
    raise ValueError(f"unknown engine {engine!r}")


def solve(builder_cls, nseg, engine, ground_kind, *, variant, eps_r, sigma, height_wl):
    """Feed-0 driving-point Z for one (design, N, engine, ground). Places the
    ground plane ``height_wl`` wavelengths below the structure's lowest wire.
    Returns a complex, or raises (the caller records the failure)."""
    from antennaknobs.engines.momwire import MomwireEngine

    solver, kw = solver_kwargs(engine, variant)
    ground = ground_spec(ground_kind, eps_r, sigma)

    b = builder_cls()
    b.nominal_nsegs = nseg
    if ground is None:
        ground_z = 0.0
    else:
        wl = C_LIGHT / (b.freq * 1e6)
        ground_z = structure_min_z(builder_cls, nseg) - height_wl * wl

    eng = MomwireEngine(
        b, solver=solver, solver_kwargs=kw, ground=ground, ground_z=ground_z
    )
    return complex(eng.impedance()[0])


def richardson_p(series):
    """Three-point convergence rate p in Z(N)=Z_inf + C/N^p from the imaginary
    (reactance) parts of the last three rungs, using the same estimator as the
    momwire enrichment test:  p = log(|dX_12/dX_23|)/log(N2/N1).

    ``series`` is ``[(N, z), ...]`` ordered by increasing N. Returns None when
    there are fewer than three rungs or the differences sign-flip (the noise
    floor was reached — the rate estimate would be meaningless)."""
    pts = [(n, z) for n, z in series if z is not None]
    if len(pts) < 3:
        return None
    (n1, z1), (n2, z2), (_n3, z3) = pts[-3], pts[-2], pts[-1]
    d12, d23 = z1.imag - z2.imag, z2.imag - z3.imag
    if d12 == 0 or d23 == 0 or (d12 * d23) <= 0:
        return None
    return math.log(abs(d12 / d23)) / math.log(n2 / n1)


def aitken_x_inf(series):
    """Aitken Δ² extrapolation of the reactance limit X_inf from the last three
    rungs' X — but ONLY when the sequence is actually contracting toward a limit
    (|Δ_23| < |Δ_12|). A basis whose per-doubling steps are growing is not in an
    asymptotic regime; extrapolating it gives a number the true sequence blows
    straight through (the catalog hentenna's sin basis does exactly this — see
    the module docstring), so we refuse rather than print a mirage. Returns None
    on too few rungs, non-contraction, or a vanishing curvature denominator."""
    pts = [(n, z) for n, z in series if z is not None]
    if len(pts) < 3:
        return None
    x1, x2, x3 = pts[-3][1].imag, pts[-2][1].imag, pts[-1][1].imag
    d12, d23 = x2 - x1, x3 - x2
    if abs(d23) >= abs(d12):  # steps not shrinking → not asymptotic, don't extrapolate
        return None
    denom = d23 - d12
    if denom == 0:
        return None
    return x3 - d23**2 / denom


def last_step(series):
    """Reactance change across the final mesh doubling, |X(Nf) - X(prev)| — the
    honest "is this basis still moving?" number that needs no asymptotic
    assumption. A basis flat here has settled on this ladder; one still stepping
    (the sin basis on the junction cluster) has not, whatever a fit would say."""
    pts = [(n, z) for n, z in series if z is not None]
    if len(pts) < 2:
        return None
    return abs(pts[-1][1].imag - pts[-2][1].imag)


def probe_row(
    design, ladder, ground_kinds, seg_cap, *, variant, eps_r, sigma, height_wl
):
    """Solve one design across the ladder for every (ground, engine). Never
    raises — a dud rung is recorded as an error string in place of a value."""
    row = {"design": design, "variant": variant, "grounds": {}, "error": None}
    try:
        cls = bc.load_design(design)
    except Exception as e:  # noqa: BLE001 — one dud design must not sink the run
        row["error"] = f"load: {type(e).__name__}: {e}"
        return row
    try:
        headroom = dah.n_max(cls)
    except Exception:  # noqa: BLE001
        headroom = None
    row["headroom"] = headroom

    for gk in ground_kinds:
        gdata = {e: [] for e in ENGINES}
        skipped = {e: [] for e in ENGINES}
        for nseg in ladder:
            if headroom is not None and nseg > headroom:
                for e in ENGINES:
                    skipped[e].append([nseg, f"headroom {headroom}"])
                continue
            try:
                tot = bc.total_nominal_segs(cls, nseg)
            except Exception as e:  # noqa: BLE001
                tot = None
            if tot is not None and tot > seg_cap:
                for e in ENGINES:
                    skipped[e].append([nseg, f"seg-cap {tot}"])
                continue
            for e in ENGINES:
                try:
                    t0 = time.time()
                    z = solve(
                        cls,
                        nseg,
                        e,
                        gk,
                        variant=variant,
                        eps_r=eps_r,
                        sigma=sigma,
                        height_wl=height_wl,
                    )
                    gdata[e].append([nseg, z.real, z.imag, time.time() - t0, tot])
                except MemoryError:
                    skipped[e].append([nseg, "MemoryError"])
                except Exception as ex:  # noqa: BLE001
                    skipped[e].append([nseg, f"{type(ex).__name__}: {str(ex)[:80]}"])
        row["grounds"][gk] = {"series": gdata, "skipped": skipped}
    return row


def _series_z(series):
    """[(N, complex Z), ...] from a stored engine series."""
    return [(n, complex(re, im)) for n, re, im, *_ in series]


def score(row, ground_kind):
    """Reduce one (design, ground) to its discriminator summary, or a reason
    string if it cannot be scored.

    Returns a dict with, at the finest common rung:
      * gap_sin_bs2   — |X_sin - X_bs2|            (the #521 disagreement)
      * gap_sin_enr   — |X_sin - X_bs2enr|         (does enrichment close it?)
      * enr_shift     — |X_bs2enr - X_bs2|         (how far enrichment moved bs2)
      * z at the finest rung for each basis, and Richardson p for bs2 / bs2enr.
    """
    g = row["grounds"].get(ground_kind)
    if not g:
        return None, "no data"
    s = {e: _series_z(g["series"].get(e, [])) for e in ENGINES}
    if any(len(s[e]) < 1 for e in ENGINES):
        why = "; ".join(
            f"{e}: {g['skipped'][e][0][1] if g['skipped'].get(e) else 'none'}"
            for e in ENGINES
            if len(s[e]) < 1
        )
        return None, why
    common = sorted(
        set(n for n, _ in s["sin"])
        & set(n for n, _ in s["bs2"])
        & set(n for n, _ in s["bs2enr"])
    )
    if not common:
        return None, "no common rung"
    nf = common[-1]

    def z_at(e, n):
        return next(z for nn, z in s[e] if nn == n)

    zs, zb, ze = z_at("sin", nf), z_at("bs2", nf), z_at("bs2enr", nf)
    return {
        "nf": nf,
        "zs": zs,
        "zb": zb,
        "ze": ze,
        # gap BEFORE enrichment (sin↔bs2) and AFTER (sin↔bs2enr): if enrichment
        # collapsed the #521 disagreement, gap_after ≪ gap_before. Equal ⇒ the
        # correction never reached the driving point.
        "gap_before": abs(zs.imag - zb.imag),
        "gap_after": abs(zs.imag - ze.imag),
        "enr_shift": abs(ze.imag - zb.imag),
        "enr_shift_r": abs(ze.real - zb.real),
        # who is still moving on this ladder (no asymptotic assumption)
        "step_sin": last_step(s["sin"]),
        "step_bs2": last_step(s["bs2"]),
        # Galerkin convergence rate (the O(1/N^(d+1)) claim); extrapolated
        # Galerkin limit only when the enriched series is genuinely contracting.
        "p_bs2": richardson_p(s["bs2"]),
        "p_enr": richardson_p(s["bs2enr"]),
        "xinf_enr": aitken_x_inf(s["bs2enr"]),
    }, None


def print_report(rows, ladder, ground_kinds, variant):
    print(
        f"\nSINGULAR-ENRICHMENT PROBE (issue #565)  ladder={list(ladder)}  "
        f"variant={variant}  engines=sin/bs2/bs2enr"
    )
    print(
        "  gapB/gapA = |X_sin - X_bs2| BEFORE and |X_sin - X_bs2enr| AFTER\n"
        "  enrichment, at the finest common rung. gapA≈gapB ⇒ enrichment did not\n"
        "  collapse the #521 disagreement.  enr↦ = |X_bs2enr - X_bs2| (how far\n"
        "  the K≥3 junction correction moved the Galerkin driving-point X).\n"
        "  stepSin/stepBs2 = |ΔX| across the last mesh doubling — who is still\n"
        "  moving.  p_enr = enriched Galerkin rate; X∞ = its extrapolated limit\n"
        "  (blank when the series is not yet contracting)."
    )

    for gk in ground_kinds:
        print(f"\n{'=' * 104}\nGROUND: {gk}\n{'=' * 104}")
        hdr = (
            f"{'design':28} {'Nf':>4} {'X_sin':>7} {'X_bs2':>7} {'gapB':>6} "
            f"{'gapA':>6} {'enr↦':>7} {'stepSin':>8} {'stepBs2':>8} "
            f"{'p_enr':>6} {'X∞_enr':>7}"
        )
        print(hdr)
        print("-" * len(hdr))
        for row in rows:
            st, why = score(row, gk)
            if st is None:
                print(f"{row['design']:28} —  {str(why)[:50]}")
                continue

            def fnum(v, w=7, d=2):
                return f"{v:{w}.{d}f}" if v is not None else f"{'.':>{w}}"

            print(
                f"{row['design']:28} {st['nf']:>4} "
                f"{st['zs'].imag:7.2f} {st['zb'].imag:7.2f} "
                f"{st['gap_before']:6.2f} {st['gap_after']:6.2f} "
                f"{st['enr_shift']:7.3f} {fnum(st['step_sin'], 8, 3)} "
                f"{fnum(st['step_bs2'], 8, 3)} {fnum(st['p_enr'], 6)} "
                f"{fnum(st['xinf_enr'])}"
            )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ladder", type=int, nargs="+", default=list(DEFAULT_LADDER))
    ap.add_argument(
        "--grounds",
        nargs="+",
        default=["free", "pec", "sommerfeld"],
        choices=["free", "pec", "sommerfeld", "refl-coef"],
        help="ground scenarios (finite ones placed --height-wl below the structure)",
    )
    ap.add_argument("--only", nargs="+", help="restrict to these dotted designs")
    ap.add_argument(
        "--variant",
        default="raw",
        choices=["raw", "stable", "tikhonov", "auto"],
        help="enrichment variant (auto SUPPRESSES enrichment on several cluster "
        "designs — see module docstring; raw is the honest always-on default)",
    )
    ap.add_argument("--eps-r", type=float, default=DEFAULT_EPS_R)
    ap.add_argument("--sigma", type=float, default=DEFAULT_SIGMA)
    ap.add_argument("--height-wl", type=float, default=DEFAULT_HEIGHT_WL)
    ap.add_argument("--seg-cap", type=int, default=DEFAULT_SEG_CAP)
    ap.add_argument("--mem-limit-gb", type=float, default=DEFAULT_MEM_GB)
    ap.add_argument("--out", type=Path, help="also write raw rows as JSON lines")
    args = ap.parse_args(argv)

    cap = int(args.mem_limit_gb * 1e9)
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))

    designs = args.only or list(CLUSTER)
    ladder = sorted(set(args.ladder))
    print(
        f"designs: {', '.join(designs)}\n"
        f"grounds: {', '.join(args.grounds)}   ladder: {ladder}   "
        f"variant: {args.variant}\n"
        f"finite medium: eps_r={args.eps_r} sigma={args.sigma}   "
        f"height: {args.height_wl}λ above the plane"
    )

    rows = []
    out = args.out.open("w") if args.out else None
    for i, d in enumerate(designs, 1):
        print(f"\n[{i}/{len(designs)}] {d} ...", flush=True)
        row = probe_row(
            d,
            ladder,
            args.grounds,
            args.seg_cap,
            variant=args.variant,
            eps_r=args.eps_r,
            sigma=args.sigma,
            height_wl=args.height_wl,
        )
        rows.append(row)
        if out:
            out.write(json.dumps(row) + "\n")
            out.flush()
        # per-design progress line
        for gk in args.grounds:
            st, why = score(row, gk)
            if st is None:
                print(f"    {gk:11} — {str(why)[:60]}")
            else:
                sstep = st["step_sin"] if st["step_sin"] is not None else float("nan")
                print(
                    f"    {gk:11} Nf={st['nf']:<4} gapB={st['gap_before']:6.2f}Ω "
                    f"gapA={st['gap_after']:6.2f}Ω  enr↦{st['enr_shift']:6.3f}Ω  "
                    f"stepSin={sstep:5.2f}Ω"
                )
    if out:
        out.close()
    print_report(rows, ladder, args.grounds, args.variant)


if __name__ == "__main__":
    main()
