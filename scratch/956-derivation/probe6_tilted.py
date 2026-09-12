"""momwire#956 derivation, probe 6: the GENERAL spelling on tilted members.

probe5 showed the transverse mask closes the vertical x vertical block against
momwire's own transmitted-grid field form. The momwire#936 lean sweep then
showed the mask is not the whole story on a LEANING test member (drift grew
0.70 -> 1.20 pp). Re-deriving for an arbitrary test tangent t = (tx, ty, tz):

    E^V  = C1 [ k^2 V zhat  -  grad W  +  grad(-dz'V) ]        (vertical source)
    E^Hx = C1 [ U xhat  +  dxW zhat   +  grad(dxV) ]           (horizontal source)

so, tested along the wire and by parts on both sides, the EXACT sandwich is

    s_u                                     (as shipped)
  + (F tz)_A  k^2 V  (F tz)_B               (k^2 V ALONE -- no dzW)
  + (F tz)_A   W   ((1 - tz^2) F')_B        (source TRANSVERSE charge)
  +   F'_A     W    (F tz)_B                (FULL test charge)
  - F'_A V F'_B                             (as shipped)
  + BT + SQ + CORNER                        (as shipped)
  + SW  on the source ends x (1 - tz'^2)    (the W end of the source by-parts)
  + TW  on the TEST ends: -c1 sigma f_m(E) INT f_n tz' W(E, .)   (NEW)

On a VERTICAL test the pair (k^2V - dzW) equals (k^2V + s_w2 + TW) by parts, so
the shipped s_zz and the mask fix coincide there and every vertical-radiator
number stands. On a leaning test they differ by
-tz(1-tz)(2+tz) INT f_m dzW f_n + tz^2 tx INT f_m dxW f_n.

This probe builds a NON-crossing deck with a TILTED above wire and a TILTED
below wire (plus an off-axis horizontal control), where the solver's own cross
quadrant is the transmitted-grid field form, and compares against it:

    exact   = the branch's `cross_complete_block` (general spelling)
    mask    = probe2's mask-only patch (transverse mask on s_w2 + SW)

Expected: exact agrees to the grid's accuracy (~1e-5) on every block; mask
departs on the tilted x tilted block.
"""

import os
import sys

os.environ.setdefault("MOMWIRE_CROSSING_FORCE_DENSE", "1")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "4")

import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "956-oracle"))
sys.path.insert(0, str(HERE))

import probe2_impedance as P2  # noqa: E402  (installs the mask-only patches)
from momwire import BSplineSolver  # noqa: E402
from momwire import _crossing_fill as CF  # noqa: E402

C0 = 299792458.0
FREQ = 7.1e6
SOIL_A = (13.0, 0.005)


def tilted_deck(lean_above_deg=30.0, lean_below_deg=25.0):
    """Wires either side of the plane, none ending in it, no junction. The
    above and the on-axis below wire LEAN; the third is a horizontal control."""
    a = np.radians(lean_above_deg)
    b = np.radians(lean_below_deg)
    above = np.array([(0.0, 0.0, 0.25), (1.0 * np.sin(a), 0.0, 0.25 + 1.0 * np.cos(a))])
    below = np.array(
        [(-1.0 * np.sin(b), 0.0, -0.15 - 1.0 * np.cos(b)), (0.0, 0.0, -0.15)]
    )
    below_off = np.array([(3.0, 0.0, -0.30), (4.0, 0.0, -0.30)])
    return BSplineSolver(
        wires=[above, below, below_off],
        n_per_edge_per_wire=[[9], [9], [9]],
        feeds=[(0, 0.5, 1 + 0j)],
        wavelength=C0 / FREQ,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )


def rel(x, y):
    return float(np.abs(x - y).max() / max(np.abs(y).max(), 1e-300))


def main():
    for la, lb in ((0.0, 0.0), (30.0, 0.0), (0.0, 25.0), (30.0, 25.0), (60.0, 45.0)):
        s = tilted_deck(la, lb)
        geom = s._build_geometry()
        supp_seg, polys, *_ = s._build_basis_polynomials(geom)
        below = s._below_segments(geom)
        a_idx = np.nonzero(~below)[0]
        b_idx = np.nonzero(below)[0]
        Z = s._compute_Z_operator(geom, supp_seg, polys)  # the grid route
        ctx = s._crossing_context(geom, supp_seg, polys)
        A = CF.axis_data(ctx, a_idx)
        B = CF.axis_data(ctx, b_idx)
        P2.FIX["W"] = False
        exact = CF.cross_complete_block(ctx, A, B, corner=True)
        P2.FIX["W"] = True
        mask = CF.cross_complete_block(ctx, A, B, corner=True)
        P2.FIX["W"] = False
        live_a = np.flatnonzero(np.abs(A["F"]).sum(axis=1) > 0)
        live_b = np.flatnonzero(np.abs(B["F"]).sum(axis=1) > 0)
        ff = -Z[np.ix_(live_a, live_b)]
        ex = exact[np.ix_(live_a, live_b)]
        mk = mask[np.ix_(live_a, live_b)]
        tilted_b = np.array(
            [bool(np.all(B["nodes"][np.abs(B["F"][n]) > 0, 0] <= 1e-9)) for n in live_b]
        )
        print(f"\nlean above {la:4.0f} deg, lean below {lb:4.0f} deg")
        for label, msk in (
            ("tilted/axis below wire", tilted_b),
            ("horizontal control", ~tilted_b),
        ):
            cols = np.flatnonzero(msk)
            print(
                f"   {label:24s}: exact vs grid {rel(ex[:, cols], ff[:, cols]):.3e}   "
                f"mask-only vs grid {rel(mk[:, cols], ff[:, cols]):.3e}   |ff| max {np.abs(ff[:, cols]).max():.3e}"
            )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
