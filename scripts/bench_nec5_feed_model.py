"""Feed-model control study: NEC-5 edge sources vs center gaps (#872 phase 1).

NEC-5 places voltage sources at segment ENDS (knots) only — the Users
Manual's EX card offers no segment-center source, and a vanilla NEC-2
``EX 0 tag seg 0`` card is silently reinterpreted as a source at END 2 of
``seg``, half a segment away from where nec2c puts it. Measured live
(2026-08-12, this script's section A): the two spellings of one knot are
bit-identical, the NEC-2-style card lands exactly on the end-2 reading,
and nec2c's center feed sits between the two adjacent knots.

That half-segment shift is the O(Δ) systematic confounding every
NEC-5-vs-momwire comparison at fixed mesh, and — because the fed knot's
POSITION moves as a deck's mesh refines — it masquerades as slow O(1/N)
solver convergence in mesh ladders. This script separates the effects on
an asymmetrically fed straight wire (feed at L/4, where dZ/ds ≠ 0):

A. **EX semantics pins**: the knot-identity and NEC-2-reinterpretation
   table, plus nec2c's center-feed vote.
B. **Aligned vs walking ladders**: NEC-5 with the fed knot pinned exactly
   at L/4 every rung (NS = 4k, source end 2 of segment k) against NEC-5
   with the deck-natural knot that drifts toward L/4 (NS = 4k+2, knot at
   k/(4k+2)). The aligned-vs-walking gap is the pure feed-POSITION term;
   the aligned ladder's own march is the intrinsic knot-source
   feed-MODEL term. momwire engines (bs2, bs1, sing) and nec2c solve the
   identical aligned geometry (1-segment bridge wire, gap centered at
   L/4) as references.
C. **Center-equivalent recipe candidate**: a NEC-2-semantics deck feeds a
   segment CENTER — always midway between two knots — so the candidate
   correction for fixed-mesh census rows is the mean of the two
   adjacent-knot NEC-5 solves. Section C measures its residual against
   nec2c's true center feed at every walking rung.

Requires $NEC5_EXE and nec2c on PATH. Printouts go through the engine's
capture cache (End-User Reports, LLNL-CODE-746721), so re-runs are free.

Usage:
    python scripts/bench_nec5_feed_model.py [--out feed_model.json]
        [--rungs 5] [--nec5-capture-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bench_nec_corpus import run_nec2c

# Study geometry: a straight vertical wire in free space, fed at L/4 —
# asymmetric so dZ/ds != 0 at the feed and position errors are visible.
L = 5.2  # metres (~ half-wave at the study frequency)
FREQ = 27.0  # MHz
RADIUS = 1e-3
Z_BASE = 10.0


def wire_deck(ns: int, ex_line: str) -> str:
    return (
        "CM feed-model study wire\nCE\n"
        f"GW 1 {ns} 0. 0. {Z_BASE!r} 0. 0. {Z_BASE + L!r} {RADIUS!r}\n"
        "GE 0 0\n"
        f"{ex_line}\n"
        f"FR 0 1 0 0 {FREQ!r} 0.\nXQ 0\nEN\n"
    )


def bridge_deck(n: int) -> str:
    """The aligned reference geometry: 1-segment bridge wire of length
    L/n centered on L/4, arms meshed at the same pitch. nec2c's EX on the
    bridge segment gaps its center = exactly L/4."""
    d = L / n
    a, b = L / 4 - d / 2, L / 4 + d / 2
    n1, n2 = max(2, round(a / d)), max(2, round((L - b) / d))
    return (
        "CM aligned OCF bridge\nCE\n"
        f"GW 1 {n1} 0 0 {Z_BASE!r} 0 0 {Z_BASE + a!r} {RADIUS!r}\n"
        f"GW 2 1 0 0 {Z_BASE + a!r} 0 0 {Z_BASE + b!r} {RADIUS!r}\n"
        f"GW 3 {n2} 0 0 {Z_BASE + b!r} 0 0 {Z_BASE + L!r} {RADIUS!r}\n"
        "GE 0\nEX 0 2 1 0 1. 0.\n"
        f"FR 0 1 0 0 {FREQ!r} 0\nXQ\nEN\n"
    )


def make_nec5(capture_dir):
    """A NEC5Engine wrapping a throwaway builder — only run_deck is used."""
    from antennaknobs.builder import AntennaBuilder
    from antennaknobs.engines import NEC5Engine
    from antennaknobs.network import Wire

    class _Host(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wires(self):
            return [Wire((0, 0, Z_BASE), (0, 0, Z_BASE + L), n_seg=10, ex=1 + 0j)]

    return NEC5Engine(_Host(), capture_dir=capture_dir)


def make_momwire(solver_key: str, n: int):
    """MomwireEngine on the aligned bridge geometry at ladder pitch L/n.

    The builder declares the study RADIUS via `build_wire_material()` so
    momwire solves the same conductor the hand decks describe. The first
    run of this study omitted it, so every momwire reference row solved
    the adapter-default 0.5 mm wire against 1 mm decks — the ~15 Ω X
    "bridge idiom" split of momwire#300, which dissolved on the fix
    (radius moves X and barely touches R at an off-center feed).
    """
    from antennaknobs.builder import AntennaBuilder
    from antennaknobs.engines import MomwireEngine
    from antennaknobs.network import Wire, WireSpec
    from momwire import BSplineSolver, SinusoidalGalerkinSolver

    d = L / n
    a, b = L / 4 - d / 2, L / 4 + d / 2

    class _OCF(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wire_material(self):
            return WireSpec(radius=RADIUS)

        def build_wires(self):
            return [
                Wire((0, 0, Z_BASE), (0, 0, Z_BASE + a), n_seg=max(2, round(a / d))),
                Wire((0, 0, Z_BASE + a), (0, 0, Z_BASE + b), n_seg=1, ex=1 + 0j),
                Wire(
                    (0, 0, Z_BASE + b),
                    (0, 0, Z_BASE + L),
                    n_seg=max(2, round((L - b) / d)),
                ),
            ]

    if solver_key == "bs2":
        return MomwireEngine(_OCF(), solver=BSplineSolver, solver_kwargs={"degree": 2})
    if solver_key == "bs1":
        return MomwireEngine(_OCF(), solver=BSplineSolver, solver_kwargs={"degree": 1})
    if solver_key == "sing":
        return MomwireEngine(_OCF(), solver=SinusoidalGalerkinSolver)
    raise ValueError(solver_key)


def zc(z: complex) -> list[float]:
    return [z.real, z.imag]


def fmt(z: complex) -> str:
    return f"{z.real:9.3f}{z.imag:+10.3f}j"


def richardson(zs: list[complex]) -> dict:
    """Observed order and extrapolated limit from a Δ-halving ladder:
    p = log2 of successive-difference ratios (last pair), Z∞ from the
    geometric tail. Complex differences keep R and X together."""
    import math

    if len(zs) < 3:
        return {}
    d1, d2 = zs[-2] - zs[-3], zs[-1] - zs[-2]
    if abs(d2) == 0:
        return {"order": None, "zinf": zc(zs[-1])}
    r = abs(d1) / abs(d2)
    p = math.log2(r) if r > 0 else None
    zinf = zs[-1] + d2 / (r - 1) if r > 1 else zs[-1]
    return {"order": p, "zinf": zc(zinf)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None, help="write full JSON here")
    ap.add_argument(
        "--rungs", type=int, default=5, help="ladder rungs (k = 2, 4, ... 2^rungs)"
    )
    ap.add_argument(
        "--nec5-capture-dir",
        type=Path,
        default=Path.home() / ".antennaknobs" / "nec5-captures",
    )
    args = ap.parse_args(argv)

    from antennaknobs.engines.nec5 import find_nec5

    if find_nec5() is None:
        sys.exit("$NEC5_EXE does not resolve to an executable")
    eng = make_nec5(args.nec5_capture_dir)

    def nec5_z(ns, ex_line):
        return eng.run_deck(wire_deck(ns, ex_line))[0][0][2]

    def nec2c_z(deck):
        r = run_nec2c(Path("/tmp/feed_model.nec"), 120, deck_text=deck)
        if r.get("error"):
            sys.exit(f"nec2c: {r['error']}")
        return complex(*r["z"][0])

    results = {"geometry": {"L": L, "freq_mhz": FREQ, "radius": RADIUS}}

    # ---------------- A: EX semantics pins ----------------
    print("=" * 78)
    print("A. EX SEMANTICS (NS=8 wire, feed near L/4) — NEC-5 sources live at knots")
    print("=" * 78)
    cases = [
        ("EX 0 1 2 2 1. 0.", "end 2 of seg 2 -> knot 0.250L"),
        ("EX 0 1 3 1 1. 0.", "end 1 of seg 3 -> knot 0.250L (same point)"),
        ("EX 0 1 -3 0 1. 0.", "negative I3    -> end 1 of seg 3 = knot 0.250L"),
        ("EX 0 1 3 0 1. 0.", "vanilla NEC-2 card (nec2c: CENTER of seg 3)"),
        ("EX 0 1 3 2 1. 0.", "end 2 of seg 3 -> knot 0.375L"),
    ]
    a_rows = []
    for ex, note in cases:
        z = nec5_z(8, ex)
        a_rows.append({"ex": ex, "z": zc(z), "note": note})
        print(f"  NEC-5  {ex:<22} {fmt(z)}   {note}")
    z_center = nec2c_z(wire_deck(8, "EX 0 1 3 0 1. 0."))
    a_rows.append(
        {"ex": "nec2c EX 0 1 3 0", "z": zc(z_center), "note": "center 0.3125L"}
    )
    print(
        f"  nec2c  {'EX 0 1 3 0 1. 0.':<22} {fmt(z_center)}   center of seg 3 = 0.3125L"
    )
    results["ex_semantics"] = a_rows

    # ---------------- B: aligned vs walking ladders ----------------
    ks = [2 ** (i + 1) for i in range(args.rungs)]
    print("\n" + "=" * 78)
    print("B. LADDERS at feed = L/4 (aligned: NS=4k knot pinned; walking: NS=4k+2)")
    print("=" * 78)
    print(
        f"  {'pitch':>7} {'NEC-5 aligned':>21} {'NEC-5 walking':>21}"
        f" {'knot pos/L':>11} {'walk-align |dZ|':>16}"
    )
    b_rows = []
    aligned_series, walking_series = [], []
    for k in ks:
        za = nec5_z(4 * k, f"EX 0 1 {k} 2 1. 0.")
        zw = nec5_z(4 * k + 2, f"EX 0 1 {k} 2 1. 0.")
        aligned_series.append(za)
        walking_series.append(zw)
        b_rows.append(
            {
                "k": k,
                "ns_aligned": 4 * k,
                "ns_walking": 4 * k + 2,
                "z_aligned": zc(za),
                "z_walking": zc(zw),
                "walking_knot_frac": k / (4 * k + 2),
            }
        )
        print(
            f"  L/{4 * k:<5} {fmt(za):>21} {fmt(zw):>21}"
            f" {k / (4 * k + 2):>11.4f} {abs(zw - za):>15.2f}Ω"
        )
    rich = richardson(aligned_series)
    order = rich.get("order")
    order_s = f"{order:.2f}" if order else "n/a"
    print(
        f"  aligned Richardson: order ≈ {order_s}   Z∞ ≈ {fmt(complex(*rich['zinf']))}"
    )
    refs = {}
    for key in ("bs2", "bs1", "sing"):
        zs = []
        for k in ks:
            zs.append(make_momwire(key, 4 * k).impedance()[0])
        refs[key] = zs
        print(f"  {key:>5} aligned bridge:  " + "  ".join(fmt(z) for z in zs))
    nec2c_series = [nec2c_z(bridge_deck(4 * k)) for k in ks]
    print("  nec2c aligned bridge:  " + "  ".join(fmt(z) for z in nec2c_series))
    results["ladders"] = {
        "rungs": b_rows,
        "nec5_aligned_richardson": rich,
        "refs": {k: [zc(z) for z in v] for k, v in refs.items()},
        "nec2c_aligned": [zc(z) for z in nec2c_series],
    }

    # ---------------- C: center-equivalent recipe ----------------
    # NEC-2 semantics feed a segment CENTER = midway between two knots, so
    # the candidate fixed-mesh correction is the mean of the two adjacent
    # knot solves. Score it against nec2c's true center feed of the SAME
    # deck (EX 0 1 seg 0), per walking rung.
    print("\n" + "=" * 78)
    print("C. CENTER-EQUIVALENT RECIPE — mean(knot k, knot k+1) vs nec2c center feed")
    print("=" * 78)
    print(
        f"  {'NS':>5} {'raw knot |err|':>14} {'knot-mean |err|':>15}"
        f" {'knot-mean Z':>21} {'nec2c center Z':>21}"
    )
    c_rows = []
    for k in ks:
        ns = 4 * k + 2
        seg = k + 1  # feed segment: center at (k+0.5)/ns, knots k/ns, (k+1)/ns
        z_lo = nec5_z(ns, f"EX 0 1 {seg} 1 1. 0.")
        z_hi = nec5_z(ns, f"EX 0 1 {seg} 2 1. 0.")
        z_mean = (z_lo + z_hi) / 2
        z_ref = nec2c_z(wire_deck(ns, f"EX 0 1 {seg} 0 1. 0."))
        c_rows.append(
            {
                "ns": ns,
                "seg": seg,
                "z_knot_lo": zc(z_lo),
                "z_knot_hi": zc(z_hi),
                "z_knot_mean": zc(z_mean),
                "z_nec2c_center": zc(z_ref),
                "raw_err": abs(z_hi - z_ref),
                "mean_err": abs(z_mean - z_ref),
            }
        )
        print(
            f"  {ns:>5} {abs(z_hi - z_ref):>13.2f}Ω {abs(z_mean - z_ref):>14.2f}Ω"
            f" {fmt(z_mean):>21} {fmt(z_ref):>21}"
        )
    results["center_recipe"] = c_rows

    if args.out:
        args.out.write_text(json.dumps(results, indent=1))
        print(f"\nfull results -> {args.out}")


if __name__ == "__main__":
    main()
