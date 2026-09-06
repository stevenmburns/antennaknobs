"""Dragging back OUT of a fold: the un-latch rule (#1202).

Three measurements, each of which kills a candidate rule.

1. THE EXACT FOLD IS NOT WHERE THE USER'S EXPERIENCE CHANGES. Near a
   saddle-node the curve GRAZES zero, so the best achievable |X| grows
   continuously from 0 rather than jumping. On lumped_coupled_pair (fold at
   coupling_l_uH ~ 0.533):

        L      best |X| over the held knob   root?   holdable at 1 ohm?
      0.533        0.049                     yes     yes
      0.528        0.326                     NO      YES
      0.522        0.862                     NO      YES
      0.516        1.421                     NO      no

   So a guard that latches AT the fold stops ~15 ticks before the user would
   have noticed anything. Latch on holdability, not on the fold.

2. NO PASSIVE TEST AT THE FROZEN POINT CAN SEE THE BRANCH RETURN, because the
   residual and the partial are ANTI-CORRELATED there -- both measure the same
   tangency. At the frozen held value 0.9223, dragging back out:

        L      |X| at frozen   partial ratio   root exists?
      0.530       0.138            0.038         no
      0.540       0.788            0.099         YES     <- residual says yes,
      0.550       1.637            0.258         yes        partial says no
      0.570       3.033            0.657         yes     <- partial says yes,
                                                            residual says no

   Where the residual is small the partial is degenerate; where the partial has
   recovered the frozen knob is nowhere near the root. Candidate (b), a probe
   at the last-good value, cannot work at ANY probe rate.

3. RE-ACQUIRING FROM THE FROZEN POINT LANDS ON THE WRONG BRANCH. The user was
   holding the LOWER root (0.9016 at L = 0.65, tracked up to 0.9223 as L fell).
   The frozen point is nearer the UPPER root, so a secant from it silently
   switches branches:

        L      user's branch   from frozen 0.9223   from pre-freeze 0.9100
      0.560      0.9150          0.9249  wrong        0.9150  correct, 6 solves
      0.580      0.9117          0.9247  wrong        0.9117  correct, 5 solves
      0.600      0.9087          0.9242  wrong        0.9087  correct, 4 solves
      0.630      0.9043          0.9232  wrong        0.9043  correct, 5 solves

   Seeding from the held value a few ticks BEFORE the freeze -- where the two
   roots were still well separated -- plus the direction of travel, re-acquires
   the user's own branch every time in 4-6 solves.
"""

import warnings

import numpy as np
from fold_probe2 import HI, LO, X

warnings.filterwarnings("ignore")

FROZEN = 0.9223
PRE_FREEZE = 0.9100


def roots(L, lo=0.895, hi=0.950, n=111):
    ts = np.linspace(lo, hi, n)
    xs = [X(t, L) for t in ts]
    sg = [i for i in range(len(xs) - 1) if xs[i] * xs[i + 1] < 0]
    return [ts[i] - xs[i] * (ts[i + 1] - ts[i]) / (xs[i + 1] - xs[i]) for i in sg]


def secant_from(seed, L, span):
    n = [0]

    def P(v):
        n[0] += 1
        return X(min(max(v, LO), HI), L)

    a = seed
    fa = P(a)
    b = min(max(a + span, LO), HI)
    fb = P(b)
    for _ in range(12):
        if fb == fa:
            break
        c = min(max(b - fb * (b - a) / (fb - fa), LO), HI)
        if abs(c - b) < 1e-7:
            break
        a, fa = b, fb
        b, fb = c, P(c)
        if abs(fb) < 1e-4:
            break
    return b, n[0]


if __name__ == "__main__":
    print("1. holdability vs the exact fold")
    for L in (0.533, 0.528, 0.522, 0.516):
        ts = np.linspace(0.90, 0.945, 46)
        best = min(abs(X(t, L)) for t in ts)
        print(
            f"   L={L:.3f}  best |X|={best:6.3f}  root={'yes' if roots(L) else 'NO ':3s}"
        )
    print("\n2. residual vs partial at the frozen knob (anti-correlated)")
    hb = (HI - LO) * 2e-3
    g0 = abs((X(0.9087 + hb, 0.60) - X(0.9087, 0.60)) / hb)
    for L in (0.530, 0.540, 0.550, 0.570):
        v = abs(X(FROZEN, L))
        g = abs((X(FROZEN + hb, L) - X(FROZEN, L)) / hb) / g0
        print(
            f"   L={L:.3f}  |X|={v:6.3f}  ratio={g:.3f}  root={'yes' if roots(L) else 'NO'}"
        )
    print("\n3. which branch re-acquisition lands on")
    for L in (0.560, 0.580, 0.600, 0.630):
        r = roots(L)
        f, _ = secant_from(FROZEN, L, (HI - LO) * 0.02)
        p, np_ = secant_from(PRE_FREEZE, L, -(HI - LO) * 0.02)
        print(
            f"   L={L:.3f}  user={r[0]:.4f}  from-frozen={f:.4f}  "
            f"from-pre-freeze={p:.4f} ({np_} solves)"
        )
