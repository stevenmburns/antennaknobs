"""momwire#931, closing measurement: the bare rod, laddered in length.

The study found the residual is a constant series dZ, invisible to radial
count (1..48) and radial length (4x span), that scales with hub depth. Depth
moves TWO things at once -- the rise length and the radials' depth -- so it
cannot on its own say the rise is where the residual lives.

This removes the screen entirely. The deck is `buried_radial_vertical`'s
connected spelling with the radials deleted: the graded rise from the hub up
to the node, the driven gap at the node, and the radiator above it. Everything
but the screen is what the #931 decks had, so dZ here is directly comparable to
the N sweep -- it is that sweep's N -> 0 end.

The question is the INTERCEPT. Fit dZ against rod length:

  * proportional through the origin  -> the difference is DISTRIBUTED along
    the conductor in the lossy medium, and the node is exonerated;
  * a non-zero intercept             -> there IS a node term, and the
    intercept is its size.

Both engines are laddered as in the rest of the study: momwire to its plateau
(it converges by nn=21 on this class), NEC-5 with its first-order mesh error
quoted from the last step.

A/B DISCIPLINE: every row prints its segment and GW-card counts. If the rod
length changes and the deck does not, the ladder is not a ladder.
"""

import math
import sys
import warnings

warnings.filterwarnings("ignore")

from antennaknobs.designs.verticals.buried_radial_vertical import (  # noqa: E402
    Builder,
)
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.nec5 import NEC5Engine  # noqa: E402
from antennaknobs.wire_catalog import Wire, graded_wire  # noqa: E402

SOILS = {"A": (13.0, 0.005), "B": (10.0, 0.002)}


REST_H = 0.025  # far-panel size on the rod; overridden from argv


class RodBuilder(Builder):
    """`buried_radial_vertical` connected, with the screen removed.

    Deliberately a SUBCLASS rather than a fresh design: the rise grading, the
    feed gap and the radiator grading are then bit-for-bit the ones the #931
    decks used, and the only difference between this and an N-radial deck is
    the radials. That is what makes dZ comparable across the two.
    """

    def build_wires(self):
        eps = 0.05
        height = 0.25 * self.design_wavelength * self.length_factor
        node = (0.0, 0.0, 0.0)
        hub = (0.0, 0.0, -self.depth)
        # `rest_h` is PINNED so that lengthening the rod adds panels rather
        # than stretching them. Without it the rise's far panels grow with the
        # rod -- measured 25 mm at L=0.15 up to 240 mm at L=2.4, i.e. the
        # ladder varied mesh fineness and length together and its dZ column
        # was reading both. The node grading (h_node, growth) is untouched, so
        # the node is resolved identically at every length and the only thing
        # that moves is how much conductor there is.
        tups = [
            graded_wire(hub, node, toward="p1", rest_h=REST_H),
            Wire(node, (0.0, 0.0, eps), ex=1 + 0j),
            graded_wire(
                (0.0, 0.0, eps),
                (0.0, 0.0, height),
                toward="p0",
                rest_h=0.25 * self.design_wavelength / self.nominal_nsegs,
            ),
        ]
        return tups


def build(soil, length, nn=42):
    eps_r, sigma = SOILS[soil]
    b = RodBuilder()
    b.nominal_nsegs = nn
    b.design_eps_r = eps_r
    b.design_sigma = sigma
    b.depth = length
    return b


def row(soil, length, nn=42):
    g = ("finite", *SOILS[soil])
    b = build(soil, length, nn)
    text = NEC5Engine(b, ground=g).deck([b.freq])
    gw = [ln for ln in text.splitlines() if ln.startswith("GW ")]
    segs = sum(int(ln.split()[2]) for ln in gw)
    zm = complex(MomwireEngine(b, ground=g).impedance()[0])
    zn = complex(NEC5Engine(b, ground=g).impedance()[0])
    dr, dx = zn.real - zm.real, zn.imag - zm.imag
    print(
        f"  L={length:5.2f} m  segs {segs:4d} gw {len(gw):2d}  "
        f"mw {zm.real:8.3f}{zm.imag:+8.3f}j  n5 {zn.real:8.3f}{zn.imag:+8.3f}j  "
        f"dR {dr:7.3f}  dX {dx:7.3f}"
    )
    return length, dr, dx


def fit(rows, label):
    """Least squares dR = a + b*L, and the same forced through the origin."""
    n = len(rows)
    x = [r[0] for r in rows]
    for j, name in ((1, "dR"), (2, "dX")):
        y = [r[j] for r in rows]
        sx, sy = sum(x), sum(y)
        sxx = sum(v * v for v in x)
        sxy = sum(a * b for a, b in zip(x, y, strict=True))
        den = n * sxx - sx * sx
        b_ = (n * sxy - sx * sy) / den
        a_ = (sy - b_ * sx) / n
        b0 = sxy / sxx  # through the origin
        resid = math.sqrt(
            sum((v - (a_ + b_ * u)) ** 2 for u, v in zip(x, y, strict=True)) / n
        )
        r0 = math.sqrt(sum((v - b0 * u) ** 2 for u, v in zip(x, y, strict=True)) / n)
        print(
            f"  {label} {name}:  free fit  {a_:+7.3f} + {b_:6.3f}/m  "
            f"(rms {resid:.3f})   through-origin  {b0:6.3f}/m  (rms {r0:.3f})"
        )


def farfield_rows(soil, lengths):
    """The radiated-power deficit on the rod decks (#931 question (ii)).

    Same construction as the screened decks: each engine over the region it
    samples, on a 90x360 hemisphere grid. `excess` is the part NOT explained
    by a series dR -- a series resistance alone moves the fraction by exactly
    R_mw/R_n5, and the screened decks left a 4.34 % +- 0.29 remainder after
    that was removed, flat across radial count and soil.
    """
    import math as _m

    from antennaknobs import far_field

    g = ("finite", *SOILS[soil])
    print(f"\n=== rod far field, soil {soil} ===")
    for L in lengths:
        b = build(soil, L)
        zm = complex(MomwireEngine(b, ground=g).impedance()[0])
        zn = complex(NEC5Engine(b, ground=g).impedance()[0])
        ffm = MomwireEngine(b, ground=g).far_field(
            n_theta=90, n_phi=360, del_theta=1, del_phi=1
        )
        fm = 100.0 * far_field.radiated_fraction(ffm)
        avg, omega = NEC5Engine(b, ground=g).average_power_gain(n_theta=90, n_phi=360)
        fn = 100.0 * avg * omega / (4.0 * _m.pi)
        pred = fm / (zn.real / zm.real)
        print(
            f"  L={L:5.2f} m  mw {fm:6.3f} %  n5 {fn:6.3f} %  gap {fm - fn:+6.3f} pp"
            f"   excess {pred - fn:+6.3f} pp = {100 * (pred - fn) / fm:5.2f} % of frac"
        )


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "A"
    if len(sys.argv) > 2:
        REST_H = float(sys.argv[2])
        globals()["REST_H"] = REST_H
    print(f"(rod far-panel rest_h = {REST_H * 1000:.1f} mm)")
    lengths = (0.15, 0.3, 0.6, 1.2, 2.4) if which == "A" else (0.15, 0.6, 2.4)
    print(f"=== bare rod, soil {which} {SOILS[which]}, nn=42 ===")
    rows = [row(which, L) for L in lengths]
    print()
    fit(rows, f"soil {which}")
    farfield_rows(which, lengths)


# ===========================================================================
# MEASURED 2026-09-06. Quoted in stevenmburns/momwire#931 comment 5560502861.
#
# dR by rod length, soil A, at three far-panel sizes -- the mesh ladder is
# what says which points are converged:
#
#     L        25 mm   12.5 mm   6.2 mm   last step
#   0.15 m     3.984    2.166     1.096     1.070    <- NOT converged
#   0.30 m     2.985    2.454     2.147     0.307
#   0.60 m     4.724    4.574     4.486     0.088
#   1.20 m     9.942    9.913     9.883     0.030
#   2.40 m    22.481   22.483    22.484     0.001    <- converged
#
# Fits at 6.2 mm: free -0.879 + 9.567/m (rms 0.476); through the origin
# 9.035/m (rms 0.751). Soil B: free +0.263 + 7.601/m, origin 7.735/m.
#
# THE SLOPE IS STABLE, THE INTERCEPT IS NOT. Across the three meshes the
# through-origin slope reads 9.151 -> 9.079 -> 9.035 while the intercept
# marches +0.716 -> -0.288 -> -0.879, past zero and to a value with no
# physical reading. It is set by the two shortest rods, which are the ones
# still moving -- and BOTH engines move there (momwire 0.39 ohm/step, NEC-5
# 1.46 at L=0.15). So: no evidence of a node term, not a proven zero.
#
# Local slope 8.995 ohm/m over 0.6->1.2 and 10.501 over 1.2->2.4: slightly
# SUPERLINEAR, matching the screened deck's depth ladder (~d^1.1), which
# means a straight-line intercept was never a clean node term anyway.
#
# Far field, soil A, 6.2 mm:
#   L        mw        n5       gap        excess (beyond a series dR)
#   0.15   1.788 %   1.732 %   +0.057 pp    3.00 % of fraction
#   0.30   3.119 %   2.943 %   +0.176 pp    5.08 %
#   0.60   5.468 %   4.866 %   +0.602 pp    9.12 %
#   1.20   9.788 %   7.583 %   +2.205 pp   16.12 %
#   2.40  18.135 %   9.967 %   +8.168 pp   26.25 %
#
# The excess is NOT the flat 4.34 % the screened decks showed -- it grows with
# rod length. That is the confirmation, not a contradiction: those decks all
# had a 0.15 m rise, so a term proportional to rise length looks constant
# there. Vary the rise and it varies.
#
# CAVEAT the tables cannot carry: the rod is not the N -> 0 end of the radial
# sweep. Deleting the screen deletes the return path and R goes 75 -> 655 ohm,
# so this is a different antenna and its dZ is not comparable to the screened
# decks' 2.1 + 4.9j. What it buys is a 16x range in rise length with nothing
# else moving, which the depth ladder could not give.
