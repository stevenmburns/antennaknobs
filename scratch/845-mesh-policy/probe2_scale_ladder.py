"""momwire#845 part 2 — the segment count razor-2p needs for a stated
tolerance, and the per-solver scale that follows. Measured, not re-derived.

#845's diagnosis proposes a solver-aware `nominal_nsegs` scale and offers
"roughly 4x bspline's segment count" as the rule it would encode. That figure
is read off a comparison of razor at **2 ohm** against bspline d2 at **0.1
ohm** — different tolerances on the two sides of the ratio. A scale has to be
quoted at EQUAL accuracy or it is not a scale, so this probe measures, for each
solver and each of #845's own deck families, the smallest ladder rung whose
|dZ| against a converged reference falls under 1.0 ohm and under 0.3 ohm. The
ratio of those two rungs IS the candidate scale.

Re-deriving from the issue's published ladder already suggests the answer moves
a long way: razor reads 1.00 ohm at N=241 and 0.38 at N=481, while bspline d2
reads 0.73 at N=15 and 0.13 at N=61, which is a ratio nearer 12-17x than 4x. If
that survives direct measurement then a scale at equal accuracy is not
shippable — probe1 found catalog decks already at 5536 segments at 4x, and 16x
on those is six figures — and the honest remedy is #845's option (b), the
construction-time advisory. Either way the number wanted here is the one a
policy would be written against, so it is worth one cheap ladder to stop
guessing.

THE RULE, in one line: a |dZ| is only meaningful to the extent its reference
has settled -- a row whose reference moved by more than a THIRD of the
tolerance being tested is an artifact of the reference, not a measurement.

Reference choice. Both solvers are scored against **bspline d2 at the finest
rung**, not against each own's finest: the question is distance from the
converged answer, and #845 already establishes bspline d2 as the converged one
(it moves < 0.3 ohm from N=15 to 61 where razor moves 19). Scoring each solver
against its own tail would credit razor for being self-consistent while wrong.
The reference rung is reported so its own convergence is visible rather than
assumed: the report prints how far the reference itself moved on its last rung
and flags any tolerance row that the reference cannot resolve. That guard earned
its place immediately -- the first run of this probe used a lambda/8 deck where
bspline d2 was still moving 0.51 ohm at N=961, and it produced a clean-looking
"4.0x" that was purely an artifact of the unconverged reference.

Decks are #845's own four, so the numbers are comparable with the issue:

  free_dipole    20 m centre-fed dipole, free space
  pec_contact    10.70 m (lambda/4) base-fed monopole standing in a PEC plane
  somm_contact   the same monopole at soil A (13, 0.005), Sommerfeld ground
  somm_845       #845's exact Sommerfeld row: 10 m, radius 1 mm, fed 4.3333 m
                 up from the base, which is where its published ladder was run

RESULTS, 2026-09-03, momwire 9eda56f, ladder 5..961, reference bspline d2 at
N=961 (which moved <= 0.045 ohm on its own last rung on all three decks, so it
resolves both bars).

                             1.0 ohm            0.3 ohm
    deck                razor / bspl  scale  razor / bspl  scale
    free_dipole            241 /  15  16.1x    961 /  61  15.8x
    somm_contact            61 /   9   6.8x    241 /  31   7.8x
    somm_845               481 /  15  32.1x   >961 / 121    n/a

**The equal-tolerance scale is 7-16x on a clean deck, not 4x.** #845's "roughly
4x" compares razor at 2 ohm against bspline d2 at 0.1 ohm; quoted at equal
accuracy the ratio is 6.8-7.8x on a base-fed quarter-wave over soil A and
15.8-16.1x on the free-space half-wave dipole. It is also remarkably stable in
the tolerance -- both decks give nearly the same scale at 1 ohm and at 0.3 ohm
-- which is what a first-order-vs-higher-order pair should do over this range,
and it means a single scale factor IS a well-posed thing to ask for. The
problem is that it is 7-16x rather than 4x, and probe1 shows the catalog cannot
absorb that.

**`somm_845` is the wrong deck to write a rule from, and it is the deck the
issue's ladder uses.** Its razor series is NOT MONOTONE: |dZ| reads 42.5 at
N=5, 11.4 at N=9, then back up to 22.3 at N=15 before resuming its first-order
descent. The feed sits at arclength 4.3333 on a 10 m wire, so where it lands
inside a segment changes with N, and that quantization adds an error component
that does not decay with the mesh. The deck is therefore the catalog's
worst-behaved by a factor of 4 (32x scale vs 6.8x for the same ground and
length, base-fed) and its ladder measures feed placement as much as mesh. Any
rule derived from it overstates what the far mesh owes.

Provenance: with the wire built 10 -> 0 this probe reproduces #845's published
ladder to the digit -- razor N=31 gives 107.802 - 81.488j against the issue's
107.80 - 81.49j, and bspline d2 at N=61 gives 103.355 - 73.765j against the
issue's stated reference 103.35 - 73.76j. The |dZ| columns differ from the
issue's only because it scored against bspline at N=61 (itself 0.32 ohm out)
where this scores against N=961.

Run: .venv/bin/python scratch/845-mesh-policy/probe2_scale_ladder.py --deck free_dipole
     .venv/bin/python scratch/845-mesh-policy/probe2_scale_ladder.py --all --json out.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from momwire import BSplineSolver, RazorSolver

C0 = 299792458.0
FREQ_MHZ = 7.0
WL = C0 / (FREQ_MHZ * 1e6)

# Soil A, the (eps_r, sigma) pair #845's ladder and momwire's own Sommerfeld
# tests both use. `ground_eps` takes the tuple directly.
SOIL_A = (13.0, 0.005)

TOLERANCES = (1.0, 0.3)


def _wire(p0, p1):
    return [np.array([list(p0), list(p1)], dtype=float)]


DECKS = {
    # 20 m centre-fed dipole in free space: #845's "free-space dipole 20 m".
    "free_dipole": {
        "wires": _wire((0.0, 0.0, -10.0), (0.0, 0.0, 10.0)),
        "radius": 1.0e-3,
        "kwargs": {},
        "feed_arclength": 10.0,
        "note": "20 m centre-fed dipole, free space",
    },
    # Base-fed QUARTER-WAVE monopole in a PEC plane. lambda/4 at WL7 is
    # 10.70 m; momwire's own contact captures use 5.35 m, which is lambda/8 --
    # a short capacitive deck (Z ~ 6 - 440j) where a 1 ohm bar is 0.2 % of |Z|
    # rather than 1 %, and where bspline d2 itself had not settled by N=961.
    # Part 2 asks about a quarter-wave, so this is one.
    "pec_contact": {
        "wires": _wire((0.0, 0.0, 0.0), (0.0, 0.0, 10.70)),
        "radius": 1.0e-3,
        "kwargs": {"ground_z": 0.0},
        "feed_arclength": 0.0,
        "note": "10.70 m (lambda/4) base-fed monopole, PEC plane",
    },
    "somm_contact": {
        "wires": _wire((0.0, 0.0, 0.0), (0.0, 0.0, 10.70)),
        "radius": 1.0e-3,
        "kwargs": {
            "ground_z": 0.0,
            "ground_eps": SOIL_A,
            "ground_model": "sommerfeld",
        },
        "feed_arclength": 0.0,
        "note": "10.70 m (lambda/4) base-fed monopole, Sommerfeld soil A",
    },
    # #845's published row, feed included: the one deck whose numbers can be
    # compared rung-for-rung with the issue.
    #
    # The wire runs 10 -> 0, TOP anchor first, which is not cosmetic. Feed
    # arclength is measured from the first anchor, so 4.3333 lands at z =
    # 5.667 here and at z = 4.333 on a 0 -> 10 wire. momwire's own
    # `tests/test_crossing_serve_524.py:212` records the consequence: "an
    # improvised feed at 10 - 4.333 is silently ~50 ohm wrong". Building it
    # 0 -> 10 reproduced that exactly -- Z came back 65.8 - 49.9j at N=15
    # against the issue's 114.75 - 92.50j -- which is the tell that a ladder
    # disagreeing with a published one is a geometry bug first and a physics
    # finding second.
    "somm_845": {
        "wires": _wire((0.0, 0.0, 10.0), (0.0, 0.0, 0.0)),
        "radius": 1.0e-3,
        "kwargs": {
            "ground_z": 0.0,
            "ground_eps": SOIL_A,
            "ground_model": "sommerfeld",
        },
        "feed_arclength": 4.3333,
        "note": "#845's deck: 10 m monopole, soil A, fed 4.3333 m up",
    },
}

SOLVERS = {
    "razor-2p": (RazorSolver, {"nec5_quadrature": True}),
    "bspline-d2": (BSplineSolver, {"degree": 2}),
}


def solve(deck_name, solver_name, n):
    """One (deck, solver, N) impedance, with wall time. Returns (z, seconds)."""
    d = DECKS[deck_name]
    cls, extra = SOLVERS[solver_name]
    t0 = time.perf_counter()
    z, _ = cls(
        wires=d["wires"],
        n_per_edge_per_wire=[n],
        wire_radius=d["radius"],
        wavelength=WL,
        feed_arclength=d["feed_arclength"],
        **d["kwargs"],
        **extra,
    ).compute_impedance()
    return complex(z), time.perf_counter() - t0


def smallest_rung(series, ref, tol):
    """Smallest N in `series` whose |Z - ref| <= tol, and every FINER rung in
    the series also does.

    The trailing condition is the point. A first-order sequence can clip a
    tolerance once on the way down and bounce back out, and reporting that rung
    as "the mesh that meets 1 ohm" overstates the solver by a factor of two or
    more. Requiring the tail to stay inside makes the answer the mesh a policy
    could actually promise.
    """
    ok = [(n, abs(z - ref) <= tol) for n, z in series]
    for i, (n, good) in enumerate(ok):
        if good and all(g for _, g in ok[i:]):
            return n
    return None


def run_deck(deck_name, ladder, *, ref_solver="bspline-d2"):
    rows = {}
    for s in SOLVERS:
        series, times = [], {}
        for n in ladder:
            z, secs = solve(deck_name, s, n)
            series.append((n, z))
            times[n] = secs
            print(
                f"  {deck_name:13} {s:11} N={n:>5}  "
                f"Z = {z.real:9.3f} {z.imag:+9.3f}j   {secs:7.3f} s",
                flush=True,
            )
        rows[s] = {"series": series, "times": times}

    ref_n, ref_z = rows[ref_solver]["series"][-1]
    prev_n, prev_z = rows[ref_solver]["series"][-2]
    out = {
        "deck": deck_name,
        "note": DECKS[deck_name]["note"],
        "ladder": list(ladder),
        "ref_solver": ref_solver,
        "ref_n": ref_n,
        "ref_z": [ref_z.real, ref_z.imag],
        # The reference's own last step: if this is not small the whole table
        # is measured against something that had not settled.
        "ref_self_move": abs(ref_z - prev_z),
        "ref_prev_n": prev_n,
        "solvers": {},
    }
    for s, d in rows.items():
        ser = d["series"]
        out["solvers"][s] = {
            "dz": {str(n): abs(z - ref_z) for n, z in ser},
            "z": {str(n): [z.real, z.imag] for n, z in ser},
            "dR": {str(n): z.real - ref_z.real for n, z in ser},
            "dX": {str(n): z.imag - ref_z.imag for n, z in ser},
            "times": {str(n): d["times"][n] for n, _ in ser},
            "n_for": {str(t): smallest_rung(ser, ref_z, t) for t in TOLERANCES},
        }
    return out


def print_report(res):
    print(f"\n### {res['deck']} — {res['note']}")
    print(
        f"reference: {res['ref_solver']} at N={res['ref_n']} = "
        f"{res['ref_z'][0]:.3f} {res['ref_z'][1]:+.3f}j "
        f"(moved {res['ref_self_move']:.3f} ohm from N={res['ref_prev_n']})"
    )
    hdr = f"{'N':>6} | " + " | ".join(
        f"{s:>28}" for s in ("razor-2p |dZ| dR/dX", "bspline-d2 |dZ| dR/dX")
    )
    print(hdr)
    print("-" * len(hdr))
    for n in res["ladder"]:
        cells = []
        for s in ("razor-2p", "bspline-d2"):
            d = res["solvers"][s]
            cells.append(
                f"{d['dz'][str(n)]:8.3f}  "
                f"{d['dR'][str(n)]:+7.2f}/{d['dX'][str(n)]:+7.2f}"
            )
        print(f"{n:>6} | " + " | ".join(f"{c:>28}" for c in cells))

    print(f"\n{'tolerance':>10} | {'razor-2p N':>11} | {'bspline-d2 N':>13} | scale")
    for t in TOLERANCES:
        r = res["solvers"]["razor-2p"]["n_for"][str(t)]
        b = res["solvers"]["bspline-d2"]["n_for"][str(t)]
        scale = f"{r / b:.1f}x" if (r and b) else "n/a"
        rs = str(r) if r else f">{res['ladder'][-1]}"
        bs = str(b) if b else f">{res['ladder'][-1]}"
        # The reference's own last step bounds what any |dZ| here can resolve.
        # If it is not well under the tolerance, the row is an artifact of an
        # unconverged reference and must not be read as a scale.
        flag = "" if res["ref_self_move"] <= t / 3.0 else "  <-- REFERENCE NOT SETTLED"
        print(f"{t:>10} | {rs:>11} | {bs:>13} | {scale}{flag}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck", action="append", choices=sorted(DECKS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument(
        "--ladder",
        default="15,31,61,121,241,481",
        help="comma-separated N rungs (default: #845's own ladder)",
    )
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)

    decks = sorted(DECKS) if args.all else (args.deck or ["free_dipole"])
    ladder = tuple(int(x) for x in args.ladder.split(","))

    results = []
    for d in decks:
        print(f"\n=== {d} ===", flush=True)
        results.append(run_deck(d, ladder))
    for r in results:
        print_report(r)

    if args.json:
        args.json.write_text(json.dumps(results, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
