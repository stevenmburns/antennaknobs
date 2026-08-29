"""Ground ladders, part (a): the Sommerfeld height sweep (#872 phase 3).

Maps the reactance-split curve the pinned 0.048 λ point sampled
(`test_live_low_height_sommerfeld_documented_gap`: NEC-5 ~7 Ω in X from
the mutually-agreeing NEC-2 lineage, resistances matching): a 5 m dipole
at 28.5 MHz over ("finite", 13, 0.005), height 0.02–1.0 λ, solved by

  - nec5   — Richardson (N, 2N) = (40, 80) pair per the phase-2 recipe
             (order ~1 knot-source march), with the raw NS=20 read also
             recorded so the pinned point's mesh contribution is visible;
  - bs2    — N=81 (census-grade at coarse mesh for a plain dipole);
  - sin    — N=81;
  - pynec  — N=81 (nec2++, needs pynec-accel >= 1.7.6 for gn 2 near
             ground, issue #448);
  - nec2c  — NS=81 hand deck, GN 2 Sommerfeld.

Feed positions are exact everywhere (center knot / center gap of a
symmetric dipole). The question: where does NEC-5 depart the NEC-2
lineage, how fast — and how much of the documented 7 Ω was really the
unextrapolated knot-source march.

Part (b) — the momwire#291 contact-geometry extensions (radius ladder,
slant contact, 3-wire star) — is deliberately NOT here yet: a faithful
base-fed ground-contact spelling per engine is exactly where feed-model
artifacts breed (see the momwire#300 bridge lesson), so it gets its own
carefully-oracled instrument.

    python scripts/bench_nec5_ground.py --out ground_a.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_nec_corpus import run_nec2c

FREQ = 28.5  # MHz
LAM = 299.792458 / FREQ
HALF = 2.5  # dipole half-length (m)
RADIUS = 0.0005
GROUND = ("finite", 13.0, 0.005)
HEIGHTS_LAMBDA = (0.02, 0.03, 0.048, 0.07, 0.10, 0.15, 0.22, 0.30, 0.50, 0.75, 1.0)


def make_builder(h_m: float, n: int):
    from antennaknobs.builder import AntennaBuilder
    from antennaknobs.network import Wire

    class LowDipole(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wires(self):
            return [Wire((0, -HALF, h_m), (0, HALF, h_m), n_seg=n, ex=1 + 0j)]

    return LowDipole()


def nec2c_z(h_m: float, n: int, timeout: float):
    deck = (
        "CM height sweep\nCE\n"
        f"GW 1 {n} 0. {-HALF!r} {h_m!r} 0. {HALF!r} {h_m!r} {RADIUS!r}\n"
        "GE 1\nGN 2 0 0 0 13. .005\n"
        f"EX 0 1 {n // 2 + 1} 0 1. 0.\n"
        f"FR 0 1 0 0 {FREQ!r} 0\nXQ\nEN\n"
    )
    r = run_nec2c(Path("/tmp/ground_a.nec"), timeout, deck_text=deck)
    if r.get("error"):
        return {"error": r["error"]}
    return {"z": complex(*r["z"][0])}


def solve(engine: str, h_m: float, n: int, capture_dir):
    from antennaknobs.engines import MomwireEngine, NEC5Engine
    from momwire import BSplineSolver, SinusoidalSolver

    b = make_builder(h_m, n)
    if engine == "nec5":
        eng = NEC5Engine(b, ground=GROUND, capture_dir=capture_dir)
    elif engine == "bs2":
        eng = MomwireEngine(
            b, solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=GROUND
        )
    elif engine == "sin":
        eng = MomwireEngine(b, solver=SinusoidalSolver, ground=GROUND)
    elif engine == "pynec":
        from antennaknobs.engines.pynec import PyNECEngine

        eng = PyNECEngine(b, ground=GROUND)
    else:
        raise ValueError(engine)
    return eng.impedance()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument(
        "--nec5-capture-dir",
        type=Path,
        default=Path.home() / ".antennaknobs" / "nec5-captures",
    )
    args = ap.parse_args(argv)

    from antennaknobs.engines.nec5 import find_nec5

    if find_nec5() is None:
        sys.exit("$NEC5_EXE does not resolve to an executable")

    rows = []
    for i, hl in enumerate(HEIGHTS_LAMBDA, 1):
        h_m = hl * LAM
        print(f"[{i}/{len(HEIGHTS_LAMBDA)}] h = {hl} lambda = {h_m:.3f} m", flush=True)
        row = {"h_lambda": hl, "h_m": h_m, "engines": {}, "errors": {}}
        for key, fn in [
            ("nec5_raw20", lambda: solve("nec5", h_m, 20, args.nec5_capture_dir)),
            ("nec5_40", lambda: solve("nec5", h_m, 40, args.nec5_capture_dir)),
            ("nec5_80", lambda: solve("nec5", h_m, 80, args.nec5_capture_dir)),
            ("bs2", lambda: solve("bs2", h_m, 81, None)),
            ("sin", lambda: solve("sin", h_m, 81, None)),
            ("pynec", lambda: solve("pynec", h_m, 81, None)),
        ]:
            try:
                t0 = time.time()
                z = fn()
                row["engines"][key] = [z.real, z.imag, time.time() - t0]
            except Exception as e:  # noqa: BLE001 — record, keep sweeping
                row["errors"][key] = f"{type(e).__name__}: {str(e)[:100]}"
        nc = nec2c_z(h_m, 81, args.timeout)
        if "error" in nc:
            row["errors"]["nec2c"] = nc["error"]
        else:
            row["engines"]["nec2c"] = [nc["z"].real, nc["z"].imag, None]
        e = row["engines"]
        if "nec5_40" in e and "nec5_80" in e:
            # Order-1 pair extrapolation (phase-1 recipe): Z∞ ≈ 2 Z(2N) − Z(N).
            zi = [2 * e["nec5_80"][k] - e["nec5_40"][k] for k in (0, 1)]
            row["engines"]["nec5_extrap"] = [zi[0], zi[1], None]
        rows.append(row)

    print("\n" + "=" * 108)
    print(
        "SOMMERFELD HEIGHT SWEEP — 5 m dipole @ 28.5 MHz over (finite, 13, 0.005)\n"
        "X-split columns are vs nec5_extrap; the raw NS=20 column shows what the "
        "pinned 0.048-lambda test actually sampled"
    )
    print("=" * 108)
    print(
        f"{'h/lam':>6} {'nec5 raw20':>19} {'nec5 extrap':>19} {'nec2c':>19}"
        f" {'bs2':>19} {'dX n5-n2c':>10} {'dX n5-bs2':>10}"
    )
    for row in rows:
        e = row["engines"]

        def f(k):
            if k not in e:
                return f"{'—':>19}"
            return f"{e[k][0]:>9.2f}{e[k][1]:>+9.2f}j"

        dx1 = (
            f"{e['nec5_extrap'][1] - e['nec2c'][1]:>10.2f}"
            if "nec5_extrap" in e and "nec2c" in e
            else f"{'—':>10}"
        )
        dx2 = (
            f"{e['nec5_extrap'][1] - e['bs2'][1]:>10.2f}"
            if "nec5_extrap" in e and "bs2" in e
            else f"{'—':>10}"
        )
        print(
            f"{row['h_lambda']:>6} {f('nec5_raw20')} {f('nec5_extrap')}"
            f" {f('nec2c')} {f('bs2')} {dx1} {dx2}"
        )
        if row["errors"]:
            print(f"       errors: {row['errors']}")

    if args.out:
        args.out.write_text(json.dumps(rows, indent=1))
        print(f"\nfull results -> {args.out}")


if __name__ == "__main__":
    main()
