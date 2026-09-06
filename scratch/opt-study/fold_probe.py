"""A genuine FOLD in the tracked variable (#1202 step 3, the named caveat).

On beams.moxon at tipspacer_factor 0.0906, X(t0_factor) has a local maximum.
Lower `halfdriver` and that maximum sinks through zero, so the two roots of
X = 0 in t0 MERGE AND ANNIHILATE -- a saddle-node. Measured:

    halfdriver   max X over t0     roots of X = 0
      2.505         +7.49          0.3971, 0.4291
      2.500         +4.56          0.3999, 0.4240
      2.494         +1.06          0.4049, 0.4161
      2.491         -0.67          NONE          <- fold at ~2.4925

This drags halfdriver down through that fold while tracking t0 to hold X = 0,
and prints the held partial each tick.

WHAT IT SHOWS. The partial does NOT warn: it stays frozen at its drag-start
value of 649.85 all the way to the cliff, because Broyden only updates it when
a corrector solve runs and ticks 2-15 need none. The tracker flies on a stale
linearisation and then thrashes -- t0 flung to the box bound with X = -27,
partial recovery, back to the bound.

What IS free and does warn, both visible below:
  * |db/da| ramps monotonically  0.53 -> 1.24  over 13 ticks (the square-root
    approach to a saddle-node), and
  * the prediction residual climbs monotonically 0.327 -> 0.982 while still
    inside a 1 ohm tolerance.
One refresh of the partial at tick 16 reads 88.35 against 649.85 -- a 7.4x
collapse -- so a single solve confirms the fold the moment either signal fires.
"""

import warnings

import numpy as np
from antennaknobs.designs.beams.moxon import Builder
from antennaknobs.engines.momwire import MomwireEngine

warnings.filterwarnings("ignore")

_c = {}


def X(t0, hd):
    """X at (t0_factor, halfdriver), memoised on the exact pair."""
    k = (round(t0, 10), round(hd, 10))
    if k in _c:
        return _c[k]
    b = Builder()
    b.t0_factor = k[0]
    b.halfdriver = k[1]
    b.tipspacer_factor = 0.0906
    v = complex(MomwireEngine(b, ground=None).impedance()[0]).imag
    _c[k] = v
    return v


LO, HI = 0.360, 0.460
TOL = 1.0

b = 0.3971
path = list(np.linspace(2.505, 2.485, 21))
a_prev = path[0]
f_prev = X(b, a_prev)
hb = 1e-3
g_b = (X(b + hb, a_prev) - f_prev) / hb
g_b0 = abs(g_b)
g_a = 0.0
print(f"  held partial dX/dt0 at the start: {g_b:.2f}  (the fold is where this -> 0)")
print("\n  tick  halfdriver   t0      X      dX/dt0   ratio   |db/da|   corr")
for tick, a in enumerate(path[1:], start=2):
    da = a - a_prev
    bp = min(max(b - (g_a / g_b) * da if g_b else b, LO), HI)
    f = X(bp, a)
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
    speed = abs((bb - b) / da) if da else 0.0
    print(
        f"  {tick:4d}  {a:9.4f}  {bb:.4f}  {ff:7.3f}  {g_b:8.2f}  "
        f"{abs(g_b) / g_b0:6.3f}  {speed:8.2f}   {corr}"
    )
    a_prev, b, f_prev = a, bb, ff
