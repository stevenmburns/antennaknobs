"""momwire#931: ATTRIBUTE the connected-spelling residual.

The residual is real -- 3.1 % in R at 4 radials, 4.5 % at 12, converged on both
sides (#931's first comment). This asks what it is a function of.

Three questions, one deck family (antennaknobs `buried_radial_vertical`,
convention "connected": a rise from the buried hub through the interface to a
node, which is a documented geometry for both engines):

  1. how it scales with RADIAL COUNT and with SOIL;
  2. whether it tracks the far-field radiated-fraction gap -- if the impedance
     residual and the far-field residual move together across N and soil, that
     says both are one node-model difference rather than two coincidences;
  3. whether it goes to zero as the NODE moves away from the plane (the depth
     ladder), which is the measurement that separates a node-model difference
     from a bulk one.

METHOD. Both engines ladder through the SAME builder knob, `nominal_nsegs`
(segments per quarter-wave at the design frequency), so a rung is one geometry
meshed two ways rather than two geometries. That is deliberately not the old
probe's trick of multiplying GW counts while holding the feed wire fixed: this
refines the graded structure proportionally, so the grading RATIO is held while
the absolute density rises, which is what a mesh ladder is supposed to do.

A/B DISCIPLINE. Every rung prints its own segment count and NEC-5 card count.
Three arms in the previous unit silently did nothing (see #931's method note),
and the check that catches it is confirming the decks DIFFER before reading
their outputs. If the segment column does not move, the ladder is not a ladder
and the numbers below it mean nothing.

`design_eps_r`/`design_sigma` are set to the solve soil on each row, so the
mesh is sized for the medium it is solved in -- otherwise the buried wires are
under-resolved by |n| and the soil axis measures meshing rather than physics.

Usage:  probe_residual_attribution.py <mode> [args]
  cost                       one cell, timed, to size the rest
  scan  <soil> <n_radials>   the mesh ladder for one cell
  depth <soil> <n_radials>   the hub-depth ladder at a converged mesh
"""

import math
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

from antennaknobs.designs.verticals.buried_radial_vertical import (  # noqa: E402
    Builder,
)
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.nec5 import NEC5Engine  # noqa: E402

SOILS = {
    "A": (13.0, 0.005),
    "B": (10.0, 0.002),
    "C": (30.0, 0.02),
}
EPS0 = 8.8541878128e-12


def n_index(eps_r, sigma, f_hz):
    """|n|, the in-medium index -- the factor the below mesh must respect."""
    return abs(complex(eps_r, -sigma / (2 * math.pi * f_hz * EPS0))) ** 0.5


def builder(soil, n_rad, nn, depth=None):
    eps_r, sigma = SOILS[soil]
    b = Builder()
    b.n_radials = n_rad
    b.nominal_nsegs = nn
    b.design_eps_r = eps_r
    b.design_sigma = sigma
    if depth is not None:
        b.depth = depth
    return b


def deck_size(b, soil):
    """(momwire segment count, NEC-5 GW card count) -- the A/B evidence."""
    eng = NEC5Engine(b, ground=("finite", *SOILS[soil]))
    text = eng.deck([b.freq])
    gw = [ln for ln in text.splitlines() if ln.startswith("GW ")]
    segs = sum(int(ln.split()[2]) for ln in gw)
    return segs, len(gw)


def both(b, soil):
    g = ("finite", *SOILS[soil])
    t0 = time.time()
    zm = complex(MomwireEngine(b, ground=g).impedance()[0])
    t1 = time.time()
    zn = complex(NEC5Engine(b, ground=g).impedance()[0])
    return zm, zn, t1 - t0, time.time() - t1


def row(b, soil, tag):
    segs, ngw = deck_size(b, soil)
    zm, zn, tm, tn = both(b, soil)
    dR = 100.0 * (zn.real - zm.real) / zm.real
    print(
        f"  {tag:>10s}  segs {segs:5d} gw {ngw:3d}  "
        f"mw {zm.real:8.3f}{zm.imag:+8.3f}j  "
        f"n5 {zn.real:8.3f}{zn.imag:+8.3f}j  dR {dR:+6.2f} %"
        f"   [{tm:.0f}s / {tn:.0f}s]"
    )
    return zm, zn, dR, segs


# ---------------------------------------------------------------------------
# question (ii): does the far-field gap move with the impedance gap?
# ---------------------------------------------------------------------------


def radiated_pair(b, soil, n_theta=90, n_phi=360):
    """(momwire radiated fraction, NEC-5 radiated fraction), both in %.

    momwire's is `far_field.radiated_fraction` over its own hemisphere grid;
    NEC-5's is avg_gain * Omega / 4pi from an RP average-and-suppress run, each
    engine over the region it actually samples. Skylake measured on #569 that
    the difference in sampled solid angle is worth 0.004 pp on this deck class
    -- the horizon is a null over lossy soil -- so the two are comparable
    without a common-Omega correction.
    """
    from antennaknobs import far_field

    g = ("finite", *SOILS[soil])
    # momwire asserts 90 == del_theta * n_theta and 360 == del_phi * n_phi,
    # so the two must be passed together; 90x360 at unit steps is its own
    # default and the densest rung Skylake laddered on #569.
    ffm = MomwireEngine(b, ground=g).far_field(
        n_theta=n_theta,
        n_phi=n_phi,
        del_theta=90 // n_theta,
        del_phi=360 // n_phi,
    )
    fm = 100.0 * far_field.radiated_fraction(ffm)
    avg, omega = NEC5Engine(b, ground=g).average_power_gain(
        n_theta=n_theta, n_phi=n_phi
    )
    fn = 100.0 * avg * omega / (4.0 * math.pi)
    return fm, fn


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "cost"
    if mode == "cost":
        b = builder("A", 4, 21)
        print(f"|n| at soil A = {n_index(*SOILS['A'], 7.1e6):.2f}")
        print("cost probe: soil A, 4 radials")
        row(b, "A", "nn=21")
        return
    soil, n_rad = sys.argv[2], int(sys.argv[3])
    if mode == "scan":
        # 48 radials at nn=84 is ~10.6k segments and ~30 min of momwire; the
        # rung list is an argument so a heavy cell can stop at 42 and say so.
        rungs = (
            tuple(int(x) for x in sys.argv[4].split(","))
            if len(sys.argv) > 4
            else (21, 42, 84)
        )
        print(f"=== soil {soil} {SOILS[soil]}, {n_rad} radials ===")
        for nn in rungs:
            row(builder(soil, n_rad, nn), soil, f"nn={nn}")
    elif mode == "farfield":
        print(f"=== far field, soil {soil} {SOILS[soil]}, {n_rad} radials ===")
        b = builder(soil, n_rad, 42)
        segs, ngw = deck_size(b, soil)
        zm, zn, _, _ = both(b, soil)
        dR = 100.0 * (zn.real - zm.real) / zm.real
        fm, fn = radiated_pair(b, soil)
        print(
            f"  segs {segs:5d}  dR {dR:+6.2f} %   "
            f"radiated mw {fm:6.3f} %  n5 {fn:6.3f} %  "
            f"gap {fm - fn:+6.3f} pp"
        )
    elif mode == "rlen":
        # Does the residual live on the RADIALS? Depth moves both the rise
        # length and the radials' depth together, so it cannot separate them.
        # Radial LENGTH moves the screen alone, at a fixed rise.
        print(f"=== radial-length ladder, soil {soil}, {n_rad} radials, nn=42 ===")
        for rf in (0.3, 0.6, 1.2):
            b = builder(soil, n_rad, 42)
            b.radial_factor = rf
            row(b, soil, f"rf={rf}")
    elif mode == "depth":
        print(f"=== depth ladder, soil {soil}, {n_rad} radials, nn=42 ===")
        for d in (0.15, 0.3, 0.6, 1.2):
            row(builder(soil, n_rad, 42, depth=d), soil, f"d={d}")


if __name__ == "__main__":
    os.environ.setdefault("NEC5_EXE", "")
    main()


# ===========================================================================
# MEASURED 2026-09-06. Quoted in stevenmburns/momwire#931 comment 5560378585.
# Logs are .gitignore'd here, so the tables live with the script that made
# them. dZ = Z_nec5 - Z_momwire throughout.
#
# --- mesh ladder, soil A (13/0.005), 7.1 MHz -------------------------------
#   N=4    nn=21 segs  249  mw  75.848+40.452j  n5  77.805+44.468j  dR +2.58 %
#          nn=42 segs  475  mw  75.859+40.501j  n5  77.937+45.203j  dR +2.74 %
#          nn=84 segs  936  mw  75.866+40.535j  n5  78.006+45.578j  dR +2.82 %
#   N=12   nn=21 segs  681  mw  50.357+32.419j  n5  52.294+36.438j  dR +3.85 %
#          nn=42 segs 1331  mw  50.365+32.471j  n5  52.423+37.207j  dR +4.09 %
#          nn=84 segs 2656  mw  50.371+32.507j  n5  52.488+37.602j  dR +4.20 %
#   N=48   nn=21 segs 2625  mw  41.285+23.319j  n5  43.232+27.365j  dR +4.72 %
#          nn=42 segs 5183  mw  41.292+23.370j  n5  43.345+28.140j  dR +4.97 %
#
# momwire is converged by nn=21; NEC-5 is still first order. Richardson on the
# ratio: 2.90 % (N=4), 4.31 % (N=12).
#
# --- the finding: dZ is FLAT in radial count (soil A, nn=84; N=48 at nn=42) -
#     N      R_mw      dR      dX     dR/R
#      1   168.196   2.304   4.772   1.37 %
#      2   107.976   2.194   4.965   2.03 %
#      4    75.866   2.140   5.043   2.82 %
#     12    50.371   2.117   5.095   4.20 %
#     48    41.292   2.053   4.770   4.97 %
#
# dZ ~ 2.1 + 4.9j ohm while R falls 4x. The PERCENTAGE grows only because its
# denominator shrinks -- "3 % at 4 radials, 4.5 % at 12" is one number quoted
# against two different R.
#
# --- nor in radial LENGTH (nn=42, 4x span at fixed depth) ------------------
#   N=4   rf 0.3/0.6/1.2   dR 2.017 / 2.078 / 2.062   dX 4.719 / 4.702 / 4.699
#   N=12  rf 0.3/0.6/1.2   dR 1.995 / 2.058 / 2.038   dX 4.737 / 4.736 / 4.718
#
# --- but it scales with hub DEPTH (soil A, N=4, nn=42) ---------------------
#   depth 0.15  dR  2.078  dX  4.702   2.74 %      13.9 ohm/m of rise
#   depth 0.30  dR  4.497  dX  8.654   5.94 %      15.0
#   depth 0.60  dR 10.068  dX 14.444  13.03 %      16.8
#   depth 1.20  dR 23.562  dX 17.709  25.07 %      19.6
#
# So the depth ladder answers #931's question NEGATIVELY: the residual does
# not go to zero as the hub leaves the plane, it grows ~10x. Since the screen
# is irrelevant (above), what is left is the RISE.
#
# --- soil, nn=84 -----------------------------------------------------------
#   B (10/0.002)  dR 1.872 / 1.843   dX 4.466 / 4.482   (N=4 / N=12)
#   A (13/0.005)  dR 2.140 / 2.117   dX 5.043 / 5.095
#   C (30/0.02)   dR 2.176 / 2.140   dX 6.019 / 6.094
#
# --- far field, 90x360 both engines, nn=42 ---------------------------------
#   cell   dR/R     mw        n5        gap
#   B/4    2.36 %  15.091 %  14.130 %  +0.961 pp
#   A/4    2.74 %  16.997 %  15.773 %  +1.224 pp   <- reproduces #569's 1.2 pp
#   C/4    3.49 %  30.100 %  27.683 %  +2.417 pp
#   B/12   3.94 %  24.004 %  22.148 %  +1.856 pp
#   A/12   4.09 %  25.216 %  23.142 %  +2.074 pp
#   C/12   4.24 %  37.303 %  34.093 %  +3.210 pp
#
# Pearson r(dR, gap) = 0.84; r(dR, gap/fraction) = 0.93. But a series dR alone
# would move the fraction by R_mw/R_n5, and removing that leaves a radiated
# power deficit of 4.34 % +- 0.29 -- FLAT across N and soil, where dR/R itself
# spans 2.36-4.24 %. Related, not one quantity.
