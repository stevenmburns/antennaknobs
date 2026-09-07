"""momwire#931, the last open measurement: the SHORT rods, laddered on their
own until each engine stops moving.

The rod ladder (probe_rod_ladder.py) left one thing open: the intercept of dR
against rod length is set by the two shortest rods, and at L = 0.15 m BOTH
engines were still moving (momwire 0.39 ohm per far-panel halving, NEC-5
1.46). That probe halved only the rod's far panels; the node grading
(h_node = 12.5 mm, growth 4) and the radiator mesh (nominal_nsegs = 42) were
held, so the short rods' residual mesh error was wherever those were coarse.

Here EVERYTHING is refined by one factor s: h_node, the rod's far panels and
the radiator's nominal_nsegs all scale together, so the grading RATIOS hold
across the ladder (the #931 method). Each engine is read at its own plateau
and Richardson-extrapolated with its own observed order; dR is then the
difference of two converged numbers rather than of two moving ones.

A/B DISCIPLINE: every row prints its segment count. If s changes and the
count does not, the ladder is not a ladder.

Usage: python probe_rod_short_ladder.py [soil] [lengths...]
"""

import math
import sys
import warnings

warnings.filterwarnings("ignore")

from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.nec5 import NEC5Engine  # noqa: E402
from antennaknobs.wire_catalog import Wire, graded_wire  # noqa: E402
from probe_rod_ladder import SOILS, RodBuilder  # noqa: E402

BASE_REST_H = 0.0062  # the finest rung the rod ladder reached
BASE_H_NODE = 0.0125  # graded_wire's default
BASE_NN = 42


class ScaledRod(RodBuilder):
    scale = 1

    def build_wires(self):
        s = self.scale
        eps = 0.05
        height = 0.25 * self.design_wavelength * self.length_factor
        node = (0.0, 0.0, 0.0)
        hub = (0.0, 0.0, -self.depth)
        return [
            graded_wire(
                hub, node, toward="p1", h_node=BASE_H_NODE / s, rest_h=BASE_REST_H / s
            ),
            Wire(node, (0.0, 0.0, eps), ex=1 + 0j),
            graded_wire(
                (0.0, 0.0, eps),
                (0.0, 0.0, height),
                toward="p0",
                h_node=BASE_H_NODE / s,
                rest_h=0.25 * self.design_wavelength / self.nominal_nsegs,
            ),
        ]


def build(soil, length, s):
    eps_r, sigma = SOILS[soil]
    b = ScaledRod()
    b.scale = s
    b.nominal_nsegs = BASE_NN * s
    b.design_eps_r = eps_r
    b.design_sigma = sigma
    b.depth = length
    return b


def solve(soil, length, s):
    g = ("finite", *SOILS[soil])
    b = build(soil, length, s)
    text = NEC5Engine(b, ground=g).deck([b.freq])
    segs = sum(int(ln.split()[2]) for ln in text.splitlines() if ln.startswith("GW "))
    zm = complex(MomwireEngine(b, ground=g).impedance()[0])
    zn = complex(NEC5Engine(b, ground=g).impedance()[0])
    return segs, zm, zn


def richardson(z1, z2, z4):
    """Observed order from three rungs (h, h/2, h/4) and the extrapolant from
    the finest pair. Returns (order, extrapolated) per component, or None
    when the steps do not shrink (no order to read)."""
    out = []
    for f in (lambda z: z.real, lambda z: z.imag):
        d1, d2 = f(z2) - f(z1), f(z4) - f(z2)
        if d2 == 0 or d1 == 0 or (d1 / d2) <= 1:
            out.append((None, f(z4)))
            continue
        p = math.log(abs(d1 / d2), 2)
        out.append((p, f(z4) + d2 / (2**p - 1)))
    return out


if __name__ == "__main__":
    soil = sys.argv[1] if len(sys.argv) > 1 else "A"
    lengths = [float(x) for x in sys.argv[2:]] or [0.15, 0.30, 0.60]
    scales = (1, 2, 4)
    print(f"=== short rods, soil {soil} {SOILS[soil]}: everything refined by s ===")
    summary = []
    for L in lengths:
        rows = []
        for s in scales:
            segs, zm, zn = solve(soil, L, s)
            rows.append((s, segs, zm, zn))
            print(
                f"  L={L:4.2f}  s={s}  segs {segs:5d}  "
                f"mw {zm.real:9.4f}{zm.imag:+9.4f}j  "
                f"n5 {zn.real:9.4f}{zn.imag:+9.4f}j  "
                f"dR {zn.real - zm.real:7.3f}  dX {zn.imag - zm.imag:7.3f}"
            )
            sys.stdout.flush()
        zms = [r[2] for r in rows]
        zns = [r[3] for r in rows]
        (pm_r, mr), (pm_x, mx) = richardson(*zms)
        (pn_r, nr), (pn_x, nx) = richardson(*zns)

        def fmt(p):
            return "  -- " if p is None else f"{p:5.2f}"

        print(
            f"    momwire order R {fmt(pm_r)} X {fmt(pm_x)} -> {mr:9.4f}{mx:+9.4f}j ;"
            f"  NEC-5 order R {fmt(pn_r)} X {fmt(pn_x)} -> {nr:9.4f}{nx:+9.4f}j ;"
            f"  converged dR {nr - mr:7.3f}  dX {nx - mx:7.3f}"
        )
        summary.append((L, nr - mr, nx - mx))
    print("\nconverged dR / dX by rod length:")
    for L, dr, dx in summary:
        print(f"  L={L:4.2f}  dR {dr:7.3f}  dX {dx:7.3f}  dR/L {dr / L:6.2f} ohm/m")
    if len(summary) >= 2:
        x = [r[0] for r in summary]
        y = [r[1] for r in summary]
        n = len(x)
        sx, sy, sxx, sxy = (
            sum(x),
            sum(y),
            sum(v * v for v in x),
            sum(a * b for a, b in zip(x, y, strict=True)),
        )
        b_ = (n * sxy - sx * sy) / (n * sxx - sx * sx)
        a_ = (sy - b_ * sx) / n
        print(
            f"  free fit on converged dR: {a_:+7.3f} + {b_:6.3f}/m ; through-origin {sxy / sxx:6.3f}/m"
        )


# ===========================================================================
# MEASURED 2026-09-07 (laptop, momwire c616fa367c, nec5cl laptop build).
# Quoted in stevenmburns/momwire#931's closing comment.
#
# s=1 reproduces probe_rod_ladder.py's 6.2 mm rung to the digit (soil A,
# L=0.15: dR 1.096) -- the A/B evidence that this ladder starts where that
# one ended. Under UNIFORM refinement both engines then move by hundredths
# of an ohm per rung, not the 1.46 ohm/step NEC-5 showed when only the far
# panels were halved: that drift was the grading RATIOS changing, the very
# hazard the #931 method note names.
#
# Converged (Richardson on each engine's own observed order) dR / dX, ohm:
#
#   soil A (13/0.005)          soil B (10/0.002)
#   L      dR      dX  dR/L    L      dR      dX  dR/L
#   0.15  1.239   0.594  8.3   0.15  -0.615  0.666  -4.1
#   0.30  2.254   4.345  7.5   0.30   1.441  3.741   4.8
#   0.60  4.595   8.629  7.7   0.60   3.802  7.624   6.3
#   1.20  9.992  13.757  8.3
#
# Soil A: free fit +0.069 + 7.507/m over 0.15-0.60 (through-origin 7.66);
# the 1.2 m point sits above the line (8.3 ohm/m), the superlinear tail the
# long-rod ladder already saw. Soil B: the shortest rod comes out NEGATIVE
# (NEC-5 below momwire in R), and the curve steepens with length.
#
# READING: there is no positive length-independent term. On soil A the
# converged curve passes through the origin to 0.07 ohm; on soil B it passes
# through zero near L ~ 0.2 m and is negative below that. A linear-fit
# "intercept" is therefore not a node term on either soil -- the relation
# is a curve (sub-linear onset, superlinear tail), and dX has a threshold
# onset (~0.6 ohm at 0.15 m on both soils, 3.7-4.3 at 0.30 m). Whatever the
# two conventions do differently along a buried conductor, it is not a
# lumped element at the crossing node.
