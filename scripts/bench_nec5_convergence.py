"""Convergence-character census: NEC-5 vs the momwire bases (#872 phase 2).

Per design in a stratified catalog sample (the motivating hentenna, loops,
multi-junction fans, folded elements, yagis, near-open feeds), solve the
driving-point impedance up a Δ-halving mesh ladder on three engines —
nec5, bs2, sin — and reduce each series by Richardson: observed order p,
extrapolated Z∞, and the coarsest rung already census-grade against Z∞.

Feed-model framing (phase 1, docs/status/2026-08-12-nec5-feed-model-*):
NEC-5's knot source is the same feed class as bs1's tent basis — both
declare segment_parity="even" and the standard coercion pins the feed to
the same physical point at every rung — so nec5 rides the ladder as just
another engine, no special corrections. Its expected order is ~1 (the
knot-source march), which is exactly why census-grade NEC-5 numbers are
extrapolated pairs; this census measures the order and the practical
(N, 2N) pair per design family.

Products (the #872 phase-2 acceptance items):
  (a) do the Z∞'s agree within formulation bars — pairwise ΔΓ between
      engines' extrapolated limits, with the |Γ|-bounded metric of the
      corpus census (Z₀ = 50);
  (b) what NS single-mesh NEC-5 needs for census-grade answers, and what
      the (N, 2N) extrapolation pair buys.

Requires $NEC5_EXE. NEC-5 printouts ride the capture cache.

    python scripts/bench_nec5_convergence.py --out phase2.json
    python scripts/bench_nec5_convergence.py --only specialty.hentenna --ladder 21 41
"""

from __future__ import annotations

import argparse
import json
import math
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_converge as bc  # noqa: E402 — sibling: ladder + engine dispatch
import bench_delta_a_headroom as dah  # noqa: E402 — Δ/a clamp (#484 discipline)

Z0 = 50.0
ENGINES = ("nec5", "bs2", "sin")
DEFAULT_LADDER = (21, 41, 81, 161)
DEFAULT_SEG_CAP = 4000
DEFAULT_MEM_GB = 6.0
AGREE_TOL = 0.02  # ΔΓ bar for "same physics" (matches the basis census)
GRADE_TOL = 0.01  # ΔΓ bar for "census-grade single-mesh read"

# Stratified per #872 phase 2: hentenna (the motivator), loops,
# multi-junction fans + folded elements (#484-sensitive), yagis/bent
# beams, the bridge-feed idiom (momwire#300 exposure: invvee), an OCF
# asymmetric feed (the phase-1 geometry class), curtains, close-parallel
# stubs, a loaded short dipole and a high-|X| loop (near-open feeds).
SAMPLE = (
    "specialty.hentenna",
    "loops.quad",
    "loops.delta_loop",
    "loops.bisquare",
    "multiband.fandipole",
    "dipoles.folded_invvee",
    "beams.yagi",
    "beams.moxon",
    "dipoles.invvee",
    "dipoles.ocf_dipole",
    "verticals.bruce",
    "verticals.jpole",
    "dipoles.short_dipole_loaded",
)


def _gamma(z: complex) -> complex:
    return (z - Z0) / (z + Z0)


def dgamma(a: complex, b: complex) -> float:
    return abs(_gamma(a) - _gamma(b))


def richardson(series):
    """Reduce a [(N, Z), ...] ladder (N ascending, len >= 3): observed
    order p from the last three rungs (actual N ratios), Z∞ from the
    geometric tail, and the (N, 2N)-style pair extrapolation from the two
    finest rungs at that order. Returns {} when the series is too short
    or non-contracting (p undefined)."""
    if len(series) < 3:
        return {}
    (n1, z1), (n2, z2), (n3, z3) = series[-3:]
    d1, d2 = z2 - z1, z3 - z2
    if abs(d2) == 0 or abs(d1) == 0:
        return {"order": None, "zinf": z3}
    r_step = n3 / n2  # Δ shrink factor of the last step
    ratio = abs(d1) / abs(d2)
    if ratio <= 1.0:
        return {"order": None, "zinf": z3, "non_contracting": True}
    p = math.log(ratio) / math.log(r_step)
    zinf = z3 + d2 / (ratio - 1)
    return {"order": p, "zinf": zinf}


def census_row(design: str, ladder, seg_cap: int) -> dict:
    """One design, all engines, whole ladder. Never raises."""
    row = {"design": design, "series": {}, "skipped": {}, "error": None}
    try:
        cls = bc.load_design(design)
    except Exception as e:  # noqa: BLE001 — a dud design must not sink the census
        row["error"] = f"load: {type(e).__name__}: {e}"
        return row
    try:
        row["headroom"] = dah.n_max(cls)
    except Exception:  # noqa: BLE001
        row["headroom"] = None
    for engine in ENGINES:
        series, skipped = [], []
        for nseg in ladder:
            if row["headroom"] is not None and nseg > row["headroom"]:
                skipped.append([nseg, f"headroom {row['headroom']}"])
                continue
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


def analyze(row: dict) -> dict:
    """Per-engine Richardson + the phase-2 products for one design."""
    out = {"engines": {}, "agreement": {}}
    zinfs = {}
    for e in ENGINES:
        series = [
            (n, complex(zr, zi)) for n, zr, zi, _t, _s in row["series"].get(e, [])
        ]
        rich = richardson(series)
        ana = {}
        if rich:
            zinf = rich["zinf"]
            zinfs[e] = zinf
            ana = {
                "order": rich.get("order"),
                "zinf": [zinf.real, zinf.imag],
                "non_contracting": rich.get("non_contracting", False),
                # coarsest rung already census-grade vs the engine's own limit
                "grade_n": next(
                    (n for n, z in series if dgamma(z, zinf) < GRADE_TOL), None
                ),
                # what the two-COARSEST-rung pair extrapolation would have
                # reported, scored against the full-ladder limit: the
                # practical (N, 2N) recipe's error at minimum cost
                "pair_err": (
                    dgamma(
                        series[1][1]
                        + (series[1][1] - series[0][1])
                        / ((series[1][0] / series[0][0]) ** rich["order"] - 1),
                        zinf,
                    )
                    if rich.get("order")
                    else None
                ),
            }
        out["engines"][e] = ana
    for a, b in (("nec5", "bs2"), ("nec5", "sin"), ("bs2", "sin")):
        if a in zinfs and b in zinfs:
            out["agreement"][f"{a}-{b}"] = dgamma(zinfs[a], zinfs[b])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="+", default=None, help="subset of SAMPLE designs")
    ap.add_argument("--ladder", nargs="+", type=int, default=list(DEFAULT_LADDER))
    ap.add_argument("--seg-cap", type=int, default=DEFAULT_SEG_CAP)
    ap.add_argument("--mem-gb", type=float, default=DEFAULT_MEM_GB)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    from antennaknobs.engines.nec5 import find_nec5

    if find_nec5() is None:
        sys.exit("$NEC5_EXE does not resolve to an executable")
    mem = int(args.mem_gb * 2**30)
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))

    designs = args.only or list(SAMPLE)
    ladder = sorted(args.ladder)
    rows = []
    for i, d in enumerate(designs, 1):
        print(f"[{i}/{len(designs)}] {d} ...", flush=True)
        row = census_row(d, ladder, args.seg_cap)
        row["analysis"] = analyze(row)
        rows.append(row)

    # ---------------- report ----------------
    print("\n" + "=" * 100)
    print(
        f"CONVERGENCE CHARACTER (ladder {ladder}; feed-0 Z; "
        f"order & Z∞ by Richardson on the finest 3 rungs)"
    )
    print("=" * 100)
    hdr = f"{'design':<28}" + "".join(
        f"{e + ' p':>9}{e + ' Z∞':>22}{'grade@N':>9}" for e in ENGINES
    )
    print(hdr)
    print("-" * len(hdr))
    for row in rows:
        if row.get("error"):
            print(f"{row['design']:<28} {row['error']}")
            continue
        cells = ""
        for e in ENGINES:
            ana = row["analysis"]["engines"].get(e) or {}
            if not ana:
                cells += f"{'—':>9}{'(short series)':>22}{'—':>9}"
                continue
            p = ana.get("order")
            z = ana.get("zinf")
            cells += (
                f"{p:>9.2f}" if p else f"{'n/a':>9}"
            ) + f"{z[0]:>11.1f}{z[1]:>+9.1f}j{str(ana.get('grade_n') or '—'):>9}"
        print(f"{row['design']:<28}{cells}")

    print("\n" + "=" * 72)
    print(f"Z∞ AGREEMENT (pairwise ΔΓ between extrapolated limits; bar {AGREE_TOL})")
    print("=" * 72)
    print(f"{'design':<28}{'nec5-bs2':>12}{'nec5-sin':>12}{'bs2-sin':>12}  verdict")
    for row in rows:
        agr = row.get("analysis", {}).get("agreement", {})
        if not agr:
            continue
        cells = "".join(
            f"{agr.get(k, float('nan')):>12.4f}"
            for k in ("nec5-bs2", "nec5-sin", "bs2-sin")
        )
        worst = max(agr.values())
        verdict = "AGREE" if worst < AGREE_TOL else f"SPLIT ({worst:.3f})"
        print(f"{row['design']:<28}{cells}  {verdict}")

    if args.out:
        args.out.write_text(
            json.dumps(
                {"ladder": ladder, "engines": list(ENGINES), "rows": rows},
                indent=1,
                default=lambda z: [z.real, z.imag],
            )
        )
        print(f"\nfull results -> {args.out}")


if __name__ == "__main__":
    main()
