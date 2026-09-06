"""The converged guard on the TWO-KNOB (Z = Z0) tracker, through a fold (#1202).

Deck: beams.moxon, holding Z = 50 with (halfdriver, tipspacer_factor) while
`t0_factor` is dragged. Box widened to (2.35, 2.62) x (0.010, 0.200) so a box
edge cannot masquerade as a fold.

FIRST RESULT, AND IT IS A NEGATIVE ONE: there is no fold here. Tracked in BOTH
directions, det(J) never approaches zero and the conditioning stays benign --

    dragging t0 UP     det(J) 368k -> 467k, cond(J) 2.3 -> 5.2, then
                       tipspacer pins at its LOWER bound and the root is gone
    dragging t0 DOWN   det(J) 368k -> 316k, cond(J) 2.3 -> 1.9, then
                       tipspacer pins at its UPPER bound and the root is gone

So the two-component branch on this deck ends on a CONSTRAINT, not a
singularity: the Jacobian is healthy right up to the last good tick. The
scalar case's fold has no counterpart here, and the guard has to handle a
different branch-ending mode.

SECOND RESULT: THE SCALAR RULE DOES NOT TRANSFER UNCHANGED.

    demote stage ON        ticks  demote  latch  truth   reacq  solves
                              60       7      8     43     114      42
                              15       3      4     11      28       7

    demote stage OFF          60    None     43     43      78      10
                              15    None     11     11      20      10

The holdability latch alone is EXACT at both resolutions -- it fires on the
tick the objective genuinely becomes unholdable. The demote stage has to be
turned OFF here, for two reasons that compound: a two-component prediction
error on a healthy stretch routinely exceeds 0.5 x tolerance, so the scalar
trigger fires ~35 ticks early; and there is no fold to protect against anyway,
which was the demote's only job.

THIRD RESULT, and it corrects something already written down: the guard must be
armed only once a tangent EXISTS. On tick 1 the drag partial is still zero, so
the "prediction" is "do not move" and its error fires any threshold. The scalar
guard's ratio < 0.25 gate was suppressing that silently -- so the earlier note
that the ratio is "no longer load-bearing" was wrong in this one respect. With
the ratio retired the cold start has to be excluded explicitly.

Branch identity is trivially correct here: no fold means one branch, so the
wrong-branch hazard from the scalar case cannot arise. It is a fold problem,
not a tracking problem.

Ground truth exploits that. While the unconstrained root is inside the box the
best achievable |Z - Z0| is 0; once tipspacer is against a bound the constraint
is active on one variable, so the constrained optimum lies on that face and is
a 1-D minimisation over halfdriver -- scan and refine, ~30 solves, exact.
"""

import warnings

import numpy as np
from antennaknobs.designs.beams.moxon import Builder
from antennaknobs.engines.momwire import MomwireEngine

warnings.filterwarnings("ignore")

TOL = 1.0
MAX_CORR = 3
BOX = [(2.35, 2.62), (0.010, 0.200)]
H = np.array([(b[1] - b[0]) * 0.002 for b in BOX])
LOB = np.array([b[0] for b in BOX])
HIB = np.array([b[1] for b in BOX])
_c = {}


def Z(hd, tip, t0):
    k = (round(hd, 9), round(tip, 9), round(t0, 9))
    if k in _c:
        return _c[k]
    b = Builder()
    b.halfdriver, b.tipspacer_factor, b.t0_factor = k
    v = complex(MomwireEngine(b, ground=None).impedance()[0])
    _c[k] = v
    return v


def F(x, t0):
    z = Z(x[0], x[1], t0)
    return np.array([z.real - 50.0, z.imag])


def jac(x, t0, f):
    J = np.zeros((2, 2))
    for j in range(2):
        xp = np.array(x, float)
        step = H[j] if xp[j] + H[j] <= HIB[j] else -H[j]
        xp[j] = min(max(xp[j] + step, LOB[j]), HIB[j])
        d = xp[j] - x[j]
        J[:, j] = (F(xp, t0) - f) / (d if d else H[j])
    return J


_truth = {}


def truth(t0):
    """Smallest |Z - Z0| any held pair in the box can reach at this drag."""
    k = round(t0, 9)
    if k in _truth:
        return _truth[k]
    best = 1e9
    for tip in (LOB[1], HIB[1]):  # the two faces the root exits through
        hs = np.linspace(LOB[0], HIB[0], 25)
        vs = [np.linalg.norm(F([h, tip], t0)) for h in hs]
        i = int(np.argmin(vs))
        lo2, hi2 = hs[max(i - 1, 0)], hs[min(i + 1, 24)]
        best = min(
            best,
            min(np.linalg.norm(F([h, tip], t0)) for h in np.linspace(lo2, hi2, 15)),
        )
    # interior: a coarse grid, refined by one Newton polish from its argmin
    g = [
        (h, tp)
        for h in np.linspace(LOB[0], HIB[0], 7)
        for tp in np.linspace(LOB[1], HIB[1], 7)
    ]
    x = np.array(min(g, key=lambda p: np.linalg.norm(F(list(p), t0))), float)
    for _ in range(12):
        f = F(x, t0)
        best = min(best, float(np.linalg.norm(f)))
        if np.linalg.norm(f) < 1e-6:
            break
        try:
            s = np.linalg.solve(jac(x, t0, f), -f)
        except np.linalg.LinAlgError:
            break
        xn = np.minimum(np.maximum(x + s, LOB), HIB)
        if np.linalg.norm(xn - x) < 1e-9:
            break
        x = xn
    best = min(best, float(np.linalg.norm(F(x, t0))))
    _truth[k] = best
    return best


def run(nt, a0=0.3906, a1=0.4700, DEMOTE=True):
    path = list(np.linspace(a0, a1, nt + 1)) + list(np.linspace(a1, a0, nt + 1))[1:]
    x = np.array([2.4994, 0.1252])
    a_prev = path[0]
    f = F(x, a_prev)
    J = jac(x, a_prev, f)
    Ja = np.zeros(2)
    hist, last_good = [], None
    mode, frozen = "track", None
    ev = dict(demote=None, latch=None, truth=None, reacq=None, rs=0, rb=None, solves=0)
    for i, a in enumerate(path[1:], 1):
        da = a - a_prev
        if ev["truth"] is None and truth(a) > TOL:
            ev["truth"] = i
        if mode in ("frozen", "latched"):
            v = float(np.linalg.norm(F(frozen, a)))
            ev["solves"] += 1
            if mode == "frozen" and v > TOL and ev["latch"] is None:
                ev["latch"] = i
                mode = "latched"
            if i > nt and ev["reacq"] is None and hist and v <= TOL:
                seed = np.array(hist[0], float)
                xr, ns = newton_from(seed, a)
                ev["rs"] = ns
                ev["solves"] += ns
                if np.linalg.norm(F(xr, a)) <= TOL:
                    ev["reacq"] = i
                    ev["rb"] = tuple(xr)
                    x = xr
                    f = F(x, a)
                    J = jac(x, a, f)
                    ev["solves"] += 2
                    mode = "track"
            a_prev = a
            continue
        xp = np.minimum(np.maximum(x + Ja * da, LOB), HIB) if da else x.copy()
        fp = F(xp, a)
        ev["solves"] += 1
        pred_err = float(np.linalg.norm(fp))
        xx, ff, corr = xp, fp, 0
        while np.linalg.norm(ff) > TOL and corr < MAX_CORR:
            try:
                s = np.linalg.solve(J, -ff)
            except np.linalg.LinAlgError:
                break
            xn = np.minimum(np.maximum(xx + s, LOB), HIB)
            if np.linalg.norm(xn - xx) < 1e-12:
                break
            fn = F(xn, a)
            corr += 1
            ev["solves"] += 1
            dx, dF = xn - xx, fn - ff
            if dx @ dx > 0:
                J = J + np.outer(dF - J @ dx, dx) / (dx @ dx)
            xx, ff = xn, fn
        # ARM ONLY ONCE A TANGENT EXISTS. On tick 1 `Ja` is still zero, so the
        # "prediction" is just "do not move" and its error is meaningless -- it
        # fires the trigger every time. In the scalar guard the ratio < 0.25
        # gate was suppressing this silently; with the ratio retired it has to
        # be said out loud.
        armed = i > 2 and DEMOTE
        if armed and pred_err > 0.5 * TOL and mode == "track" and ev["demote"] is None:
            ev["demote"] = i
            frozen = last_good if last_good is not None else xx
            mode = "frozen"
            a_prev = a
            continue
        if np.linalg.norm(ff) > TOL:
            if ev["latch"] is None:
                ev["latch"] = i
                frozen = last_good if last_good is not None else xx
                mode = "latched"
                a_prev = a
                continue
        else:
            last_good = xx.copy()
            hist.insert(0, tuple(xx))
            hist[:] = hist[:8]
        if da:
            Ja = (xx - x) / da
        a_prev, x, f = a, xx, ff
    return ev


def newton_from(seed, t0, n=14):
    x = np.minimum(np.maximum(np.array(seed, float), LOB), HIB)
    ns = 0
    for _ in range(n):
        f = F(x, t0)
        ns += 1
        if np.linalg.norm(f) < 1e-4:
            break
        J = jac(x, t0, f)
        ns += 2
        try:
            s = np.linalg.solve(J, -f)
        except np.linalg.LinAlgError:
            break
        xn = np.minimum(np.maximum(x + s, LOB), HIB)
        if np.linalg.norm(xn - x) < 1e-10:
            break
        x = xn
    return x, ns


if __name__ == "__main__":
    print(
        f"  {'ticks':>6}{'demote':>8}{'latch':>7}{'truth':>7}{'reacq':>7}"
        f"{'solves':>8}  branch (halfdriver, tipspacer)"
    )
    for dem in (True, False):
        print(f"  --- demote stage {'ON' if dem else 'OFF'} ---")
        for nt in (60, 15):
            e = run(nt, DEMOTE=dem)
            rb = f"({e['rb'][0]:.4f}, {e['rb'][1]:.4f})" if e["rb"] else "-"
            print(
                f"  {nt:6d}{str(e['demote']):>8}{str(e['latch']):>7}{str(e['truth']):>7}"
                f"{str(e['reacq']):>7}{e['rs']:>8}  {rb}"
            )
