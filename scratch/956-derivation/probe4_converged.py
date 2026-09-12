"""momwire#956 derivation, probe 4: the W fix against NEC-5 on refinement ladders.

probe2 read the crossing rod at one mesh (nn=42, rest_h 0.025): the shipped
residual +3.98 / +2.99 / +4.72 / +9.94 ohm at L = 0.15 / 0.30 / 0.60 / 1.20 m
became +2.77 / +0.61 / -0.08 / -0.26 with the W terms masked. The short rods
still carry NEC-5's first-order mesh error (the 931 study's Richardson figures
were 1.24 / 2.25 / 4.60 / 9.99), so both engines are laddered here the way
scratch/931-study did: uniform refinement r = 1, 2, 4 (rest_h / r, nn * r),
Richardson first order on NEC-5 (2 Z4 - Z2) and the plateau on momwire.

  rod   the crossing rod (931 RodBuilder), soil A, four lengths
  brv   the #956 deck itself (4 radials, hub 0.15 m), nominal_nsegs ladder
"""

import os
import sys

os.environ.setdefault("MOMWIRE_CROSSING_FORCE_DENSE", "1")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "4")
os.environ.setdefault(
    "NEC5_EXE", os.path.expanduser("~/antennas/NEC5-downloads/nec5-linux/nec5cl")
)

import argparse  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "956-oracle"))
sys.path.insert(0, str(HERE.parent / "931-study"))
sys.path.insert(0, str(HERE))

import probe2_impedance as P2  # noqa: E402  (installs the patches on import)
import probe_rod_ladder as ROD  # noqa: E402
from antennaknobs.engines.nec5 import NEC5Engine  # noqa: E402
from probe3_cross_block import build as build_brv  # noqa: E402

SOIL_A = (13.0, 0.005)
G = ("finite", *SOIL_A)


def fmt(z):
    return f"{z.real:9.3f}{z.imag:+9.3f}j"


def nsegs(b):
    text = NEC5Engine(b, ground=G).deck([b.freq])
    return sum(int(ln.split()[2]) for ln in text.splitlines() if ln.startswith("GW "))


def ladder(make, refines, label):
    print(f"\n{label}")
    print(
        f"  {'r':>2} {'segs':>5} {'NEC-5':>20} {'mw shipped':>20} {'dR':>8} {'dX':>8} {'mw fix W':>20} {'dR':>8} {'dX':>8}"
    )
    rows = {}
    for r in refines:
        b = make(r)
        zn = complex(NEC5Engine(b, ground=G).impedance()[0])
        z0 = P2.z_momwire(b, G)
        z1 = P2.z_momwire(b, G, w=True)
        rows[r] = (zn, z0, z1)
        print(
            f"  {r:2d} {nsegs(b):5d} {fmt(zn):>20} {fmt(z0):>20} {zn.real - z0.real:+8.3f} {zn.imag - z0.imag:+8.3f} "
            f"{fmt(z1):>20} {zn.real - z1.real:+8.3f} {zn.imag - z1.imag:+8.3f}"
        )
        sys.stdout.flush()
    r_hi, r_mid = refines[-1], refines[-2]
    zn_inf = (
        2 * rows[r_hi][0] - rows[r_mid][0]
    )  # first order, as the 931 ladder measured
    z0, z1 = rows[r_hi][1], rows[r_hi][2]
    print(
        f"  Richardson NEC-5 {fmt(zn_inf):>20}   vs shipped dR {zn_inf.real - z0.real:+8.3f} dX {zn_inf.imag - z0.imag:+8.3f}"
        f"   vs fix W dR {zn_inf.real - z1.real:+8.3f} dX {zn_inf.imag - z1.imag:+8.3f}"
    )
    return rows


def rod(args):
    for L in args.lengths:

        def make(r, L=L):
            ROD.REST_H = 0.025 / r
            return ROD.build("A", L, args.nn * r)

        ladder(
            make,
            args.refines,
            f"crossing rod L = {L} m, soil A (rest_h 0.025/r, nn {args.nn}*r)",
        )


def brv(args):
    def make(r):
        return build_brv(
            n_radials=args.n_radials, depth=args.depth, nominal_nsegs=args.nn * r
        )

    ladder(
        make,
        args.refines,
        f"buried_radial_vertical {args.n_radials} radials, hub {args.depth} m, soil A (nominal_nsegs {args.nn}*r)",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["rod", "brv"])
    ap.add_argument("--nn", type=int, default=42)
    ap.add_argument("--refines", type=int, nargs="+", default=[1, 2, 4])
    ap.add_argument(
        "--lengths", type=float, nargs="+", default=[0.15, 0.30, 0.60, 1.20]
    )
    ap.add_argument("--n-radials", type=int, default=4)
    ap.add_argument("--depth", type=float, default=0.15)
    a = ap.parse_args()
    {"rod": rod, "brv": brv}[a.mode](a)
