"""#956 Phase B step 1: what the rise deck's cross block actually IS.

Before pricing a block against an oracle, size it. Prints the deck's segment
census, the above/below split, the crossing junction, and the cross-pair
count — the cost driver for an independent double-quadrature assembly.
"""

import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")

from antennaknobs.designs.verticals.buried_radial_vertical import (  # noqa: E402
    Builder,
)
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402

SOIL_A = (13.0, 0.005)
C0 = 299792458.0


def deck(n_radials=4, nominal_nsegs=None, depth=None):
    b = Builder()
    b.n_radials = n_radials
    b.design_eps_r, b.design_sigma = SOIL_A
    if nominal_nsegs is not None:
        b.nominal_nsegs = nominal_nsegs
    if depth is not None:
        b.depth = depth
    return b


def solver_of(b):
    """The momwire solver the AK engine would build, un-solved."""
    eng = MomwireEngine(b, ground=("finite", *SOIL_A))
    return eng._make_solver(wavelength=C0 / (b.freq * 1e6))


def main():
    b = deck()
    print(f"freq {b.freq:.3f} MHz   depth {b.depth} m   n_radials {b.n_radials}")
    s = solver_of(b)
    print(f"solver {type(s).__name__}  degree {getattr(s, 'degree', '-')}")
    geom = s._build_geometry()
    below = s._below_segments(geom)
    n = geom["n_segs_total"]
    a_idx = np.nonzero(~below)[0]
    b_idx = np.nonzero(below)[0]
    h = np.asarray(geom["seg_h"] if "seg_h" in geom else geom["h_per_seg"])
    print(f"segments {n}: above {len(a_idx)}, below {len(b_idx)}")
    print(f"cross pairs (a x b)  {len(a_idx) * len(b_idx)}  (x2 directions)")
    print(f"segment length: min {h.min():.6f}  max {h.max():.6f}  m")
    seg_l = np.asarray(geom["seg_l"])
    seg_r = np.asarray(geom["seg_r"])
    c = 0.5 * (seg_l + seg_r)
    print(
        f"z range: [{min(seg_l[:, 2].min(), seg_r[:, 2].min()):.4f}, "
        f"{max(seg_l[:, 2].max(), seg_r[:, 2].max()):.4f}] m"
    )
    d = np.linalg.norm(c[a_idx][:, None, :] - c[b_idx][None, :, :], axis=-1)
    print(f"closest above/below centre pair {d.min():.6f} m")
    print(f"crossing junctions: {s._crossing_junctions()}")
    print(f"wire radius {s.wire_radius if hasattr(s, 'wire_radius') else '-'}")
    # the below segments nearest the plane, which is what the rise contributes
    zb = c[b_idx][:, 2]
    print(f"below segment depths: min {zb.max():.6f}  max {zb.min():.6f}  m")
    nrise = int(
        np.count_nonzero(np.abs(c[b_idx][:, 0]) + np.abs(c[b_idx][:, 1]) < 1e-9)
    )
    print(f"below segments on the rise axis (x=y=0): {nrise}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
