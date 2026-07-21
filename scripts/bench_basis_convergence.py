"""Basis-convergence census: sin vs BSpline-d2 over the catalog (issue #477).

Answers "which basis converges at the coarser mesh, and where can we even
tell?" Per design the driving-point impedance (feed 0) is solved up a mesh
ladder on both bases. A design has a MUTUAL LIMIT when the two bases agree
within ``--agree-tol`` at the finest common rung — the cross-validation that
makes a convergence claim meaningful (a single basis flat on its own ladder
can be flat at the wrong value; two different bases meeting is evidence of
the true limit). Against that limit the census reports each basis's error at
the coarsest rung and its conv@N, plus the designs where NO mutual limit
exists at the finest affordable mesh (the honest "we cannot yet say" list —
near-open feeds, folded/fan junctions, seg-capped giants).

2026-07-20 findings (see docs/status/2026-07-20-basis-convergence-census.md):
66/91 designs have a mutual limit; bs2 is within 2% of it at N=21 on 53/66
vs sin's 36/66, with conv@N advantages up to 15x on port-fed and junction-
heavy designs; the no-mutual class is dominated by folded/fan-junction
geometries where sin converges extremely slowly toward the value bs2 holds
from coarse meshes.

Memory discipline: RLIMIT_AS caps the process (an OOM becomes a recorded
MemoryError rung, not a dead machine) and ``--seg-cap`` skips rungs whose
nominal segment total is too large (recorded, not silently dropped).

    python scripts/bench_basis_convergence.py
    python scripts/bench_basis_convergence.py --ladder 21 61 161 --only wire.zepp
"""

from __future__ import annotations

import argparse
import json
import resource
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_converge as bc  # noqa: E402 — sibling script, reused ladder machinery

DEFAULT_LADDER = (21, 61, 161, 321)
DEFAULT_SEG_CAP = 4000
DEFAULT_MEM_GB = 6.0
ENGINES = ("sin", "bs2")
CONVERGE_TOL = 0.02
AGREE_TOL = 0.02


def census_row(design: str, ladder, seg_cap: int) -> dict:
    """Solve one design up the ladder on both bases; record (N, Z, t, segs)
    per rung and the skip reasons. Never raises — a dud rung is recorded."""
    row = {"design": design, "series": {}, "skipped": {}, "error": None}
    try:
        cls = bc.load_design(design)
    except Exception as e:  # noqa: BLE001 — one dud design must not sink the census
        row["error"] = f"load: {type(e).__name__}: {e}"
        return row
    for engine in ENGINES:
        series, skipped = [], []
        for nseg in ladder:
            try:
                tot = bc.total_nominal_segs(cls, nseg)
            except Exception as e:  # noqa: BLE001
                skipped.append([nseg, f"segs: {type(e).__name__}: {e}"])
                continue
            if tot > seg_cap:
                skipped.append([nseg, f"seg-cap {tot}"])
                continue
            try:
                t0 = time.time()
                res = bc.solve_design(cls, nseg, engine, "free")
                series.append(
                    [nseg, res["z"][0][0], res["z"][0][1], time.time() - t0, tot]
                )
            except MemoryError:
                skipped.append([nseg, "MemoryError"])
            except Exception as e:  # noqa: BLE001
                skipped.append([nseg, f"{type(e).__name__}: {str(e)[:80]}"])
        row["series"][engine] = series
        row["skipped"][engine] = skipped
    return row


def classify(row: dict, agree_tol: float = AGREE_TOL, tol: float = CONVERGE_TOL):
    """Reduce one census row to its claim summary.

    Returns ``("mutual", stats)``, ``("no_mutual", stats)``, or
    ``("incomplete", reason)``. ``stats`` for the mutual class carries the
    mutual limit ``zstar`` (mean of the two finest values), each basis's
    coarse-rung error and conv@N against it; the no-mutual class carries the
    two finest values and their disagreement.
    """
    if row.get("error"):
        return "incomplete", row["error"]
    s = {e: row["series"].get(e) or [] for e in ENGINES}
    if any(len(s[e]) < 2 for e in ENGINES):
        why = "; ".join(
            f"{e}: {row['skipped'][e][0][1] if row['skipped'].get(e) else 'few rungs'}"
            for e in ENGINES
        )
        return "incomplete", why
    common = sorted(set(n for n, *_ in s["sin"]) & set(n for n, *_ in s["bs2"]))
    if len(common) < 2:
        return "incomplete", "no common rungs"
    nf = common[-1]

    def z_at(e, n):
        return next(complex(re, im) for nn, re, im, *_ in s[e] if nn == n)

    zs_f, zb_f = z_at("sin", nf), z_at("bs2", nf)
    agree = abs(zs_f - zb_f) / abs(zb_f)
    stats = {"nf": nf, "zs_f": zs_f, "zb_f": zb_f, "agree": agree}
    if agree >= agree_tol:
        return "no_mutual", stats
    zstar = 0.5 * (zs_f + zb_f)

    def conv_at(e):
        return next(
            (n for n in common if abs(z_at(e, n) - zstar) / abs(zstar) <= tol), None
        )

    stats.update(
        zstar=zstar,
        conv={e: conv_at(e) for e in ENGINES},
        err_coarse={e: abs(z_at(e, common[0]) - zstar) / abs(zstar) for e in ENGINES},
        n_coarse=common[0],
    )
    return "mutual", stats


def print_report(rows, ladder, seg_cap, tol=CONVERGE_TOL, agree_tol=AGREE_TOL):
    mutual, no_mutual, incomplete = [], [], []
    for r in rows:
        kind, st = classify(r, agree_tol, tol)
        if kind == "mutual":
            mutual.append((r["design"], st))
        elif kind == "no_mutual":
            no_mutual.append((r["design"], st))
        else:
            incomplete.append((r["design"], st))

    print(
        f"\nBASIS-CONVERGENCE CENSUS (issue #477)  ladder={list(ladder)} "
        f"seg-cap={seg_cap}  engines={'/'.join(ENGINES)}  ground=free"
    )
    print(
        f"  mutual limit = sin and bs2 within {agree_tol:.0%} of each other at the "
        f"finest common rung; conv@N and coarse-rung errors are vs that limit"
    )
    print(
        f"\n{len(rows)} designs: {len(mutual)} mutual-limit, "
        f"{len(no_mutual)} no-mutual-limit, {len(incomplete)} incomplete"
    )
    flat = {e: sum(1 for _, d in mutual if d["err_coarse"][e] <= tol) for e in ENGINES}
    for e in ENGINES:
        print(
            f"  {e}: within {tol:.0%} of the mutual limit at N={ladder[0]} on "
            f"{flat[e]}/{len(mutual)}"
        )

    hdr = (
        f"\n{'design':34} {'Z* (feed0)':>18} {'agree':>6} "
        f"{'e21 sin':>8} {'e21 bs2':>8} {'cv sin':>7} {'cv bs2':>7}"
    )
    print(hdr)
    print("-" * len(hdr))
    for name, d in sorted(mutual, key=lambda t: -t[1]["err_coarse"]["sin"]):
        z = d["zstar"]
        cv = {e: str(d["conv"][e]) if d["conv"][e] else f">{d['nf']}" for e in ENGINES}
        print(
            f"{name:34} {z.real:8.1f}{z.imag:+8.1f}j {d['agree'] * 100:5.1f}% "
            f"{d['err_coarse']['sin'] * 100:7.1f}% "
            f"{d['err_coarse']['bs2'] * 100:7.1f}% {cv['sin']:>7} {cv['bs2']:>7}"
        )

    ratios = [
        d["conv"]["sin"] / d["conv"]["bs2"]
        for _, d in mutual
        if d["conv"]["sin"] and d["conv"]["bs2"]
    ]
    if ratios:
        print(
            f"\nconv@N ratio sin/bs2: median {statistics.median(ratios):.1f}x, "
            f"max {max(ratios):.1f}x, =1 on {sum(1 for r in ratios if r == 1)}"
            f"/{len(ratios)}"
        )

    print("\nNO MUTUAL LIMIT at the finest affordable rung (cannot score either):")
    for name, d in sorted(no_mutual, key=lambda t: -t[1]["agree"]):
        print(
            f"  {name:34} sin {d['zs_f']:.1f} vs bs2 {d['zb_f']:.1f} "
            f"({d['agree'] * 100:.1f}% apart at N={d['nf']})"
        )
    if incomplete:
        print("\nINCOMPLETE:")
        for name, why in incomplete:
            print(f"  {name:34} {str(why)[:90]}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ladder", type=int, nargs="+", default=list(DEFAULT_LADDER))
    ap.add_argument("--seg-cap", type=int, default=DEFAULT_SEG_CAP)
    ap.add_argument("--mem-limit-gb", type=float, default=DEFAULT_MEM_GB)
    ap.add_argument("--out", type=Path, help="also write raw rows as JSON lines")
    ap.add_argument("--only", nargs="+", help="restrict to these dotted designs")
    args = ap.parse_args(argv)

    cap = int(args.mem_limit_gb * 1e9)
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))

    from antennaknobs.cli import list_builtin_designs

    designs = args.only or list_builtin_designs()
    rows = []
    out = args.out.open("w") if args.out else None
    for i, d in enumerate(designs, 1):
        print(f"[{i}/{len(designs)}] {d} ...", flush=True)
        row = census_row(d, args.ladder, args.seg_cap)
        rows.append(row)
        if out:
            out.write(json.dumps(row) + "\n")
            out.flush()
    if out:
        out.close()
    print_report(rows, args.ladder, args.seg_cap)


if __name__ == "__main__":
    main()
