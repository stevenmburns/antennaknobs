"""Run every method on every deck/start, count distinct solves, emit the table."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import methods as M
from harness import Deck

HERE = Path(__file__).resolve().parent

TOL_Z = 1.0  # ohm, |Z - Z0|
TOL_X = 1.0  # ohm, |X|
BUDGET = 80  # distinct solves; the shipped NM budget for two knobs

STARTS = {
    "moxon": {
        "tuned": (2.4454699666515394, 0.047061074343758946),
        "far": (2.41, 0.115),
    },
    "brv12": {"tuned": (1.0, 0.6), "far": (0.89, 0.12)},
}


def row(name, tr, deck, case, tol):
    n = tr.first_within(tol, deck.z0, case)
    best, bx = tr.best(deck.z0, case)
    return {
        "method": name,
        "solves": n,
        "reached": n is not None,
        "used": tr.n,
        "best": best,
        "best_x": list(bx),
        "path": [list(p) for p in tr.path()],
    }


def main():
    kinds = sys.argv[1:] or ["moxon", "brv12"]
    out = {}
    for kind in kinds:
        d = Deck(kind)
        out[kind] = {
            "knobs": d.knobs,
            "box": d.box,
            "z0": d.z0,
            "starts": {},
            "cases": {},
        }
        for sname, x0 in STARTS[kind].items():
            out[kind]["starts"][sname] = list(x0)
            # ---- case 1: two knobs -> Z0
            r1 = []
            r1.append(
                row(
                    "Nelder-Mead",
                    M.run_nm(d, x0, "match_z0", BUDGET),
                    d,
                    "match_z0",
                    TOL_Z,
                )
            )
            r1.append(
                row(
                    "NM + seed (#1176)",
                    M.run_nm(d, x0, "match_z0", BUDGET, seed=True),
                    d,
                    "match_z0",
                    TOL_Z,
                )
            )
            r1.append(
                row(
                    "Newton (FD Jacobian)",
                    M.run_newton2(d, x0, BUDGET),
                    d,
                    "match_z0",
                    TOL_Z,
                )
            )
            r1.append(
                row(
                    "Broyden",
                    M.run_newton2(d, x0, BUDGET, broyden=True),
                    d,
                    "match_z0",
                    TOL_Z,
                )
            )
            r1.append(
                row("seed + Broyden", M.run_hybrid(d, x0, BUDGET), d, "match_z0", TOL_Z)
            )
            out[kind]["cases"].setdefault("two_knob", {})[sname] = r1
            # ---- case 2: knob 0 only -> X = 0
            r2 = []
            r2.append(
                row(
                    "Nelder-Mead",
                    M.run_nm(d, x0, "resonance", BUDGET),
                    d,
                    "resonance",
                    TOL_X,
                )
            )
            r2.append(row("secant", M.run_secant(d, x0, BUDGET), d, "resonance", TOL_X))
            r2.append(
                row(
                    "bracket + Brent", M.run_brent(d, x0, BUDGET), d, "resonance", TOL_X
                )
            )
            r2.append(
                row(
                    "Newton (FD deriv)",
                    M.run_newton1(d, x0, BUDGET),
                    d,
                    "resonance",
                    TOL_X,
                )
            )
            out[kind]["cases"].setdefault("one_knob", {})[sname] = r2
            d.flush()
        d.flush()
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    # ---- print
    for kind, K in out.items():
        for case, label, tol in (
            ("one_knob", "ONE KNOB -> X = 0 (|X| <= %.1f)" % TOL_X, TOL_X),
            ("two_knob", "TWO KNOBS -> Z0 (|Z-Z0| <= %.1f)" % TOL_Z, TOL_Z),
        ):
            print(f"\n### {kind}  {label}   budget {BUDGET} distinct solves")
            print(f"{'method':22s} {'tuned start':>18s} {'far start':>18s}")
            names = [r["method"] for r in K["cases"][case]["tuned"]]
            for i, nm in enumerate(names):
                cells = []
                for s in ("tuned", "far"):
                    r = K["cases"][case][s][i]
                    cells.append(
                        f"{r['solves']:d} solves"
                        if r["reached"]
                        else f"FAIL (best {r['best']:.2f})"
                    )
                print(f"{nm:22s} {cells[0]:>18s} {cells[1]:>18s}")


if __name__ == "__main__":
    main()
