"""A SECOND fold, different deck and different mechanism (#1202).

`arrays.lumped_coupled_pair` holding X = 0 with `length_factor` while
`coupling_l_uH` is dragged. The lumped R+jwL bridging the two feed segments
makes X(length_factor) non-monotone; lowering L sinks that local maximum
through zero and the two roots ANNIHILATE:

    coupling_l_uH   local max of X over lf in [0.90, 0.945]   roots
        0.65             +12.61                          0.9016, 0.9225
        0.60              +6.83                          0.9087, 0.9240
        0.56              +2.69                          0.9150, 0.9248
        0.53              -0.13                          NONE     <- fold ~0.533
        0.50              -2.82                          NONE

The moxon fold (fold_probe.py) came from ELEMENT coupling; this one comes from
a LUMPED load. Two different mechanisms, so the guard is being calibrated
against something more than one deck's quirk.

Run at two drag resolutions to calibrate the guard: does "prediction error
rising for k ticks" survive a coarse drag, or must the test be a SLOPE?
"""

import warnings

import numpy as np
from antennaknobs.designs.arrays.lumped_coupled_pair import Builder
from antennaknobs.engines.momwire import MomwireEngine

warnings.filterwarnings("ignore")

_c = {}


def X(lf, L):
    k = (round(lf, 10), round(L, 10))
    if k in _c:
        return _c[k]
    b = Builder()
    b.length_factor = k[0]
    b.spacing_factor = 0.13
    b.coupling_l_uH = k[1]
    v = complex(MomwireEngine(b, ground=None).impedance()[0]).imag
    _c[k] = v
    return v


LO, HI = 0.880, 0.960
TOL = 1.0
FOLD = 0.533


def run(n_ticks, verbose=False):
    path = list(np.linspace(0.65, 0.48, n_ticks + 1))
    b = 0.9016
    a_prev = path[0]
    f_prev = X(b, a_prev)
    hb = 2e-4
    g_b = (X(b + hb, a_prev) - f_prev) / hb
    g_b0 = abs(g_b)
    g_a = 0.0
    rows = []
    for a in path[1:]:
        da = a - a_prev
        bp = min(max(b - (g_a / g_b) * da if g_b else b, LO), HI)
        f = X(bp, a)  # the tick's display solve; |f| is the PREDICTION error
        corr = 0
        bb, ff = bp, f
        while abs(ff) > TOL and corr < 4:
            bn = min(max(bb - ff / g_b if g_b else bb, LO), HI)
            if abs(bn - bb) < 1e-12:
                break
            fn = X(bn, a)
            corr += 1
            if bn != bb:
                g_b = (fn - ff) / (bn - bb)
            bb, ff = bn, fn
        if da:
            g_a = (ff - f_prev - g_b * (bb - b)) / da
        # What ONE refresh solve would report, had the guard asked for it.
        refreshed = (X(bb + hb, a) - ff) / hb
        rows.append(
            {
                "a": a,
                "b": bb,
                "X": ff,
                "pred_err": abs(f),
                "corr": corr,
                "g_b": g_b,
                "ratio": abs(refreshed) / g_b0,
                "speed": abs((bb - b) / da) if da else 0.0,
                "past_fold": a < FOLD,
            }
        )
        a_prev, b, f_prev = a, bb, ff
    return rows


def analyse(n, rows):
    pre = [r for r in rows if not r["past_fold"]]
    # Ticks of monotonically rising prediction error immediately before the fold.
    k = 0
    for i in range(len(pre) - 1, 0, -1):
        if pre[i]["pred_err"] > pre[i - 1]["pred_err"]:
            k += 1
        else:
            break
    first_bad = next(
        (i + 1 for i, r in enumerate(rows) if r["corr"] > 0 or abs(r["X"]) > TOL), None
    )
    print(f"\n### {n}-tick drag  (0.65 -> 0.48, fold at L ~ {FOLD})")
    print(f"  ticks before the fold                  : {len(pre)}")
    print(f"  consecutive RISING prediction error    : {k} ticks")
    print(f"  first tick to lose tolerance / correct : {first_bad}")
    if pre:
        print(
            "  prediction error over the last 5 pre-fold ticks: "
            + " -> ".join(f"{r['pred_err']:.3f}" for r in pre[-5:])
        )
        print(
            "  refreshed-partial ratio, same ticks            : "
            + " -> ".join(f"{r['ratio']:.3f}" for r in pre[-5:])
        )
    post = [r for r in rows if r["past_fold"]]
    if post:
        print(
            f"  after the fold: worst |X| {max(abs(r['X']) for r in post):.1f} ohm, "
            f"{sum(r['corr'] for r in post)} correctors over {len(post)} ticks, "
            f"min refreshed ratio {min(r['ratio'] for r in post):.3f}"
        )
    return k


if __name__ == "__main__":
    for n in (60, 15):
        analyse(n, run(n))
