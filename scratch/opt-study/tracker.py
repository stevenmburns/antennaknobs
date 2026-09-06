"""#1202 step 3 study: TRACKING a root while the user drags another knob.

The app's real case is not "optimise": it is "I am dragging knob A, hold X = 0
(or Z = Z0) with knob B". That is numerical CONTINUATION.

## The cost model, which is the whole point

A tick costs ONE solve no matter what -- the app must show Z at the new knob
position anyway. So the question is not solves per tick, it is EXTRA solves:
how often the tangent prediction is already within tolerance when that
unavoidable display solve lands. Zero extra solves means tracking is free.

The tangent comes from the implicit function theorem. Holding f(a, b) = 0 with
b as a moves: db/da = -(df/da)/(df/db). Both partials come from a Broyden
update on the corrector solves the tracker is already paying for -- no
dedicated Jacobian solves after the first tick.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import Deck

HERE = Path(__file__).resolve().parent
TOL_X = 1.0  # ohm
TOL_Z = 1.0  # ohm


def track_scalar(deck, drag_idx, hold_idx, a_path, b0, tol=TOL_X, max_corr=4):
    """Hold X = 0 with knob `hold_idx` while `drag_idx` walks `a_path`."""
    lo, hi = deck.box[hold_idx]

    def X(a, b):
        x = [0.0, 0.0]
        x[drag_idx], x[hold_idx] = a, b
        return deck.z(tuple(x)).imag

    rows = []
    b = b0
    a_prev = a_path[0]
    f_prev = X(a_prev, b)
    # Seed the two partials with one extra solve, once, at the start.
    hb = max((hi - lo) * 0.01, 1e-9)
    g_b = (X(a_prev, min(b + hb, hi)) - f_prev) / hb
    g_a = 0.0
    setup = 2
    for i, a in enumerate(a_path[1:], start=1):
        da = a - a_prev
        b_pred = b - (g_a / g_b) * da if g_b else b
        b_pred = min(max(b_pred, lo), hi)
        f = X(a, b_pred)  # the tick's DISPLAY solve
        corr = 0
        bb, ff = b_pred, f
        while abs(ff) > tol and corr < max_corr:
            step = -ff / g_b if g_b else 0.0
            bn = min(max(bb + step, lo), hi)
            if abs(bn - bb) < 1e-12:
                break
            fn = X(a, bn)
            corr += 1
            # Broyden on the held partial, from the corrector we just paid for.
            if bn != bb:
                g_b = (fn - ff) / (bn - bb)
            bb, ff = bn, fn
        # Broyden on the drag partial, across the tick.
        if da:
            g_a = (ff - f_prev - g_b * (bb - b)) / da
        rows.append(
            {
                "a": a,
                "b": bb,
                "X": ff,
                "corr": corr,
                "pred_ok": abs(f) <= tol,
                "pred_err": abs(f),
            }
        )
        a_prev, b, f_prev = a, bb, ff
    return rows, setup


def track_vector(deck3, drag, hold, a_path, x0, z0=50.0, tol=TOL_Z, max_corr=4):
    """Hold Z = Z0 with the two `hold` knobs while `drag` walks `a_path`.

    `deck3(params) -> complex Z`; knobs are named, so this works on a deck with
    a third knob to drag.
    """

    def F(vals):
        z = deck3(vals)
        return np.array([z.real - z0, z.imag])

    lo = np.array([hold[k][1][0] for k in range(len(hold))])
    hi = np.array([hold[k][1][1] for k in range(len(hold))])
    names_hold = [hold[k][0] for k in range(len(hold))]
    a_name, a_box = drag

    def at(a, b):
        d = {a_name: a}
        d.update(dict(zip(names_hold, b, strict=True)))
        return d

    b = np.array(x0, dtype=float)
    a_prev = a_path[0]
    Fp = F(at(a_prev, b))
    # One-off Jacobian: 2 solves for the held pair, 1 for the drag partial.
    J = np.zeros((2, 2))
    h = np.maximum((hi - lo) * 0.01, 1e-9)
    for j in range(2):
        bp = b.copy()
        bp[j] = min(max(bp[j] + h[j], lo[j]), hi[j])
        J[:, j] = (F(at(a_prev, bp)) - Fp) / (bp[j] - b[j])
    ha = (a_box[1] - a_box[0]) * 0.01
    Ja = (F(at(a_prev + ha, b)) - Fp) / ha
    setup = 4
    rows = []
    for a in a_path[1:]:
        da = a - a_prev
        try:
            db = np.linalg.solve(J, -Ja * da)
        except np.linalg.LinAlgError:
            db = np.zeros(2)
        b_pred = np.minimum(np.maximum(b + db, lo), hi)
        Fv = F(at(a, b_pred))  # the tick's DISPLAY solve
        pred_ok = float(np.linalg.norm(Fv)) <= tol
        pred_err = float(np.linalg.norm(Fv))
        bb, Ff = b_pred, Fv
        corr = 0
        while np.linalg.norm(Ff) > tol and corr < max_corr:
            try:
                step = np.linalg.solve(J, -Ff)
            except np.linalg.LinAlgError:
                break
            bn = np.minimum(np.maximum(bb + step, lo), hi)
            if np.linalg.norm(bn - bb) < 1e-12:
                break
            Fn = F(at(a, bn))
            corr += 1
            dx, dF = bn - bb, Fn - Ff
            if dx @ dx > 0:
                J = J + np.outer(dF - J @ dx, dx) / (dx @ dx)
            bb, Ff = bn, Fn
        if da:
            Ja = (Ff - Fp - J @ (bb - b)) / da
        rows.append(
            {
                "a": a,
                "b": list(map(float, bb)),
                "res": float(np.linalg.norm(Ff)),
                "corr": corr,
                "pred_ok": pred_ok,
                "pred_err": pred_err,
            }
        )
        a_prev, b, Fp = a, bb, Ff
    return rows, setup


def report(name, rows, setup):
    corr = [r["corr"] for r in rows]
    ok = sum(1 for r in rows if r["pred_ok"])
    print(f"\n### {name}   {len(rows)} ticks, setup {setup} solves")
    print(
        f"  prediction alone within tolerance : {ok}/{len(rows)} ticks "
        f"({100 * ok / len(rows):.0f} %)  -> ZERO extra solves"
    )
    print(
        f"  extra corrector solves per tick   : mean {np.mean(corr):.2f}, "
        f"max {max(corr)}, total {sum(corr)}"
    )
    print(
        f"  worst residual after correction   : "
        f"{max(r.get('X', r.get('res', 0)) and abs(r.get('X', r.get('res'))) for r in rows):.4f}"
    )
    print(
        f"  worst PREDICTION error            : {max(r['pred_err'] for r in rows):.3f}"
    )
    return {
        "ticks": len(rows),
        "setup": setup,
        "pred_ok": ok,
        "corr_mean": float(np.mean(corr)),
        "corr_total": int(sum(corr)),
        "rows": rows,
    }


if __name__ == "__main__":
    out = {}
    # --- moxon, scalar: drag tipspacer_factor, hold X = 0 with halfdriver
    d = Deck("moxon")  # knobs [halfdriver, tipspacer_factor]
    a_path = list(np.linspace(0.035, 0.125, 16))
    rows, setup = track_scalar(d, drag_idx=1, hold_idx=0, a_path=a_path, b0=2.4783)
    out["moxon_scalar"] = report(
        "moxon — drag tipspacer_factor, hold X = 0 with halfdriver", rows, setup
    )
    d.flush()

    # --- brv12, scalar: drag radial_factor, hold X = 0 with length_factor
    d2 = Deck("brv12")  # knobs [length_factor, radial_factor]
    a_path2 = list(np.linspace(0.12, 0.95, 14))
    rows2, setup2 = track_scalar(d2, drag_idx=1, hold_idx=0, a_path=a_path2, b0=0.9755)
    out["brv12_scalar"] = report(
        "brv12 — drag radial_factor, hold X = 0 with length_factor", rows2, setup2
    )
    d2.flush()
    (HERE / "tracker_results.json").write_text(json.dumps(out, indent=1))
    print("\nwrote tracker_results.json")
