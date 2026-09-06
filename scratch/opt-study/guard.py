"""The converged fold guard (#1202, last study step).

Latch on HOLDABILITY, demote on partial collapse, trigger from the corrector's
own Broyden update, re-acquire from pre-freeze history. Run on both decks at
both drag resolutions, against ground truth computed by scanning the held box.
"""

import warnings
from collections import deque

import numpy as np
from antennaknobs.designs.arrays.lumped_coupled_pair import Builder as CP
from antennaknobs.designs.beams.moxon import Builder as MX
from antennaknobs.engines.momwire import MomwireEngine

warnings.filterwarnings("ignore")

TOL = 1.0
MAX_CORR = 3
RATIO_LATCH = 0.25
_c = {}


def _z(kind, held, drag):
    k = (kind, round(held, 10), round(drag, 10))
    if k in _c:
        return _c[k]
    if kind == "cp":
        b = CP()
        b.length_factor = k[1]
        b.spacing_factor = 0.13
        b.coupling_l_uH = k[2]
        kw = dict(ground=None)
    else:
        b = MX()
        b.t0_factor = k[1]
        b.halfdriver = k[2]
        b.tipspacer_factor = 0.0906
        kw = dict(ground=None)
    v = complex(MomwireEngine(b, **kw).impedance()[0]).imag
    _c[k] = v
    return v


DECKS = {
    "coupled_pair": dict(
        kind="cp", lo=0.880, hi=0.960, b0=0.9087, a0=0.60, a1=0.495, fold=0.533
    ),
    "moxon": dict(
        kind="mx", lo=0.360, hi=0.460, b0=0.3971, a0=2.505, a1=2.487, fold=0.4925
    ),
}


_truth_cache = {}


def best_over_box(d, a, n=25):
    """Ground truth: the smallest |X| ANY held value can achieve at this drag.

    A plain coarse scan is not good enough -- at ~1000 ohm per unit of held
    knob, a 25-point grid over this box lands 2 ohm from a root it straddles
    and reports "unholdable" on a perfectly healthy tick. So: scan, then refine
    the bracket (or the argmin) to convergence.
    """
    key = (d["kind"], round(a, 10))
    if key in _truth_cache:
        return _truth_cache[key]
    ts = np.linspace(d["lo"], d["hi"], n)
    xs = [_z(d["kind"], t, a) for t in ts]
    sg = [i for i in range(len(xs) - 1) if xs[i] * xs[i + 1] < 0]
    if sg:
        best = 0.0  # a sign change means an exact root
    else:
        i = int(np.argmin([abs(v) for v in xs]))
        lo2 = ts[max(i - 1, 0)]
        hi2 = ts[min(i + 1, len(ts) - 1)]
        best = min(abs(_z(d["kind"], t, a)) for t in np.linspace(lo2, hi2, 21))
    _truth_cache[key] = best
    return best


def run(name, d, nt, trigger):
    def X(h, aa):
        return _z(d["kind"], h, aa)

    lo, hi = d["lo"], d["hi"]
    hb = (hi - lo) * 2e-3
    path = (
        list(np.linspace(d["a0"], d["a1"], nt + 1))
        + list(np.linspace(d["a1"], d["a0"], nt + 1))[1:]
    )
    b = d["b0"]
    a_prev = path[0]
    f_prev = X(b, a_prev)
    g_b = (X(b + hb, a_prev) - f_prev) / hb
    g_b0 = abs(g_b)
    g_a = 0.0
    hist = deque(maxlen=8)  # pre-freeze history: (drag, held)
    mode = "track"
    frozen = last_good = None
    corr_hist = []
    ev = {
        "demote": None,
        "latch": None,
        "reacq": None,
        "reacq_solves": 0,
        "reacq_b": None,
        "false": 0,
        "solves": 0,
    }
    truth_fail = None
    reversed_at = nt
    for i, a in enumerate(path[1:], 1):
        da = a - a_prev
        if truth_fail is None and best_over_box(d, a) > TOL:
            truth_fail = i
        if mode in ("frozen", "latched"):
            v = abs(X(frozen, a))
            ev["solves"] += 1
            if mode == "frozen" and v > TOL and ev["latch"] is None:
                ev["latch"] = i
                mode = "latched"
            # Re-acquire only on drag REVERSAL, seeded from pre-freeze history.
            if i > reversed_at and ev["reacq"] is None and hist:
                seed = hist[0][1]
                direction = np.sign(seed - frozen) or 1.0
                s = _secant(X, seed, a, lo, hi, direction * (hi - lo) * 0.02)
                ev["reacq_solves"] = s[1]
                ev["solves"] += s[1]
                if abs(X(seed, a)) is not None and abs(s[2]) <= TOL:
                    ev["reacq"] = i
                    ev["reacq_b"] = s[0]
                    b = s[0]
                    mode = "track"
                    g_b = (X(b + hb, a) - X(b, a)) / hb
                    ev["solves"] += 2
            a_prev = a
            continue
        bp = min(max(b - (g_a / g_b) * da if g_b else b, lo), hi)
        f = X(bp, a)
        ev["solves"] += 1
        pred_err = abs(f)
        corr = 0
        bb, ff = bp, f
        ratio = None
        while abs(ff) > TOL and corr < MAX_CORR:
            bn = min(max(bb - ff / g_b if g_b else bb, lo), hi)
            if abs(bn - bb) < 1e-12:
                break
            fn = X(bn, a)
            corr += 1
            ev["solves"] += 1
            if bn != bb:
                g_b = (fn - ff) / (bn - bb)
                ratio = abs(g_b) / g_b0  # candidate (c): free, from the corrector
            bb, ff = bn, fn
        corr_hist.append(corr)
        fired = trigger(pred_err, corr, corr_hist, ratio)
        if fired and ratio is None:
            ratio = abs((X(bb + hb, a) - ff) / hb) / g_b0
            ev["solves"] += 1
        # 2. DEMOTE on partial collapse -- stop stepping, do not declare dead.
        if fired and ratio is not None and ratio < RATIO_LATCH and mode == "track":
            if best_over_box(d, a) <= TOL:
                pass  # still holdable: demoting here is correct, not a false fire
            ev["demote"] = ev["demote"] or i
            frozen = last_good if last_good is not None else bb
            mode = "frozen"
            a_prev = a
            continue
        # 1. LATCH on holdability.
        if abs(ff) > TOL:
            if ev["latch"] is None:
                ev["latch"] = i
                frozen = last_good if last_good is not None else bb
                mode = "latched"
                a_prev = a
                continue
        else:
            last_good = bb
            hist.append((a, bb))
        if da:
            g_a = (ff - f_prev - g_b * (bb - b)) / da
        a_prev, b, f_prev = a, bb, ff
    ev["truth"] = truth_fail
    return ev


def _secant(X, seed, a, lo, hi, span):
    n = 0

    def p(v):
        return X(min(max(v, lo), hi), a)

    x0 = seed
    f0 = p(x0)
    n += 1
    x1 = min(max(seed + span, lo), hi)
    f1 = p(x1)
    n += 1
    for _ in range(10):
        if f1 == f0:
            break
        c = min(max(x1 - f1 * (x1 - x0) / (f1 - f0), lo), hi)
        if abs(c - x1) < 1e-7:
            break
        x0, f0 = x1, f1
        x1 = c
        f1 = p(c)
        n += 1
        if abs(f1) < 1e-4:
            break
    return x1, n, f1


TRIGGERS = {
    "(a) corr > running median": lambda e, c, ch, r: c > 0 and c > np.median(ch[-9:]),
    "(b) pred_err > 0.5*TOL": lambda e, c, ch, r: e > 0.5 * TOL,
    "(c) any corrector ran": lambda e, c, ch, r: c > 0,
}

if __name__ == "__main__":
    for tname, trig in TRIGGERS.items():
        print(f"\n=== trigger {tname} ===")
        print(
            f"  {'deck':14s}{'ticks':>6}{'demote':>8}{'latch':>7}{'truth':>7}"
            f"{'reacq':>7}{'r_solves':>9}  branch"
        )
        for name, d in DECKS.items():
            for nt in (60, 15):
                e = run(name, d, nt, trig)
                bb = f"{e['reacq_b']:.4f}" if e["reacq_b"] else "-"
                print(
                    f"  {name:14s}{nt:6d}{str(e['demote']):>8}{str(e['latch']):>7}"
                    f"{str(e['truth']):>7}{str(e['reacq']):>7}{e['reacq_solves']:>9}  {bb}"
                )
