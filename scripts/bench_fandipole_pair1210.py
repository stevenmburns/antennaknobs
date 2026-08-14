"""Validation study: the catalog fan dipole, pair_12_10 variant.

Two questions, one design (`multiband.fandipole`, `pair_12_10`: 12m + 10m
elements on the shared cone feed, FREE SPACE so NEC-5's Michalski ground
offset stays out of the formulation comparison):

1. Cross-engine agreement + convergence character at both band centers —
   the three-oracle lanes (bs2 / bs1 / pynec / nec5) on a nominal_nsegs
   ladder, bydipole1-study style. The fan is a harder test than ByDipole1:
   two K=3 junctions, a 2 cm bridge feed wire, coupled parallel elements.

2. The feed-bridge (eps) artifact — the number that decides whether the
   partition-addressed node gap (momwire#315) matters for this design. The
   catalog geometry hard-codes eps = 0.01 m (bridge length 2 cm). We shrink
   eps by moving ONLY the two feed-junction points S/T toward each other
   (arms and spokes untouched), solve at fixed mesh, and extrapolate
   eps -> 0. The gap between the as-built eps = 0.01 answer and the limit
   IS the bridge-idiom cost a true partition feed would remove.

Usage:
  NEC5_EXE=... .venv/bin/python scripts/bench_fandipole_pair1210.py
  ... --no-nec5        # skip the licensed binary
Writes scratch/fandipole-pair1210-study.json and prints the tables.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scratch" / "fandipole-pair1210-study.json"

FREQS = {"12m": 24.97, "10m": 28.47}
LADDER = (11, 15, 21, 27, 35, 45)
EPS_LADDER = (0.02, 0.01, 0.005, 0.0025)
EPS_NOMINAL = 35
EPS_AS_BUILT = 0.01
BASE = 7.0


def _fan_builder_cls(feed_eps=None):
    """The pair_12_10 fan Builder, optionally with the feed bridge shrunk.

    Variant application: `Builder(params)` REPLACES default_params (the
    constructor merges FRAMEWORK_PARAMS with exactly what it is given), so
    the pair preset must be overlaid on the defaults by the caller.

    The eps override moves only the two feed-junction points S/T — the only
    wire endpoints on the x = 0 axis — from y = ±0.01 to y = ±feed_eps,
    after the stock geometry is built. Arms and spokes stay put, so the
    sweep isolates the bridge length from everything else (the slight
    riser-length change is second order: the riser is ~0.2 m, the move
    ≤ 1.75 cm along y).
    """
    from antennaknobs.designs.multiband.fandipole import Builder

    if feed_eps is None:
        return Builder

    def _snap(p):
        x, y, z = p
        if abs(x) < 1e-12 and abs(abs(y) - EPS_AS_BUILT) < 1e-12:
            return (x, math.copysign(feed_eps, y), z)
        return p

    class EpsFan(Builder):
        def build_wires(self):
            return [
                w._replace(p0=_snap(w.p0), p1=_snap(w.p1))
                for w in super().build_wires()
            ]

    return EpsFan


def _builder(freq, nominal, feed_eps=None):
    cls = _fan_builder_cls(feed_eps)
    params = {**cls.default_params, **cls.pair_12_10_params}
    b = cls(params)
    b.freq = freq
    b.nominal_nsegs = nominal
    return b


def _z_momwire(b, degree):
    from momwire import BSplineSolver

    from antennaknobs.engines.momwire import MomwireEngine

    eng = MomwireEngine(
        b, solver=BSplineSolver, solver_kwargs={"degree": degree}, ground=None
    )
    return eng.impedance()[0]


def _z_pynec(b):
    from antennaknobs.engines.pynec import PyNECEngine

    return PyNECEngine(b, ground=None).impedance()[0]


def _nec5_engine(b):
    from antennaknobs.engines.nec5 import NEC5Engine

    return NEC5Engine(
        b, ground=None, capture_dir=Path.home() / ".antennaknobs" / "nec5-captures"
    )


def _z_nec5(b):
    return _nec5_engine(b).impedance()[0]


def _ri(z):
    return [round(z.real, 4), round(z.imag, 4)]


LANES = {
    "bs2": lambda b: _z_momwire(b, 2),
    "bs1": lambda b: _z_momwire(b, 1),
    "pynec": lambda b: _z_pynec(b),
    "nec5": lambda b: _z_nec5(b),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-nec5", action="store_true")
    args = ap.parse_args()
    lanes = {k: v for k, v in LANES.items() if not (args.no_nec5 and k == "nec5")}

    data: dict = {"ladders": {}, "eps": {}}

    # ---- 1. cross-engine mesh ladders at both band centers
    for band, freq in FREQS.items():
        data["ladders"][band] = {}
        for lane, fn in lanes.items():
            rows = []
            for n in LADDER:
                z = fn(_builder(freq, n))
                rows.append([n, *_ri(z)])
                print(f"ladder {band} {lane} n={n}: {z:.3f}", flush=True)
            data["ladders"][band][lane] = rows

    # ---- 2. feed-bridge (eps) sensitivity at fixed mesh
    for band, freq in FREQS.items():
        data["eps"][band] = {}
        for lane, fn in lanes.items():
            rows = []
            for eps in EPS_LADDER:
                z = fn(_builder(freq, EPS_NOMINAL, feed_eps=eps))
                rows.append([eps, *_ri(z)])
                print(f"eps {band} {lane} eps={eps}: {z:.3f}", flush=True)
            data["eps"][band][lane] = rows

    OUT.write_text(json.dumps(data, indent=1))

    # ---- tables
    for band in FREQS:
        print(f"\n== ladder {band} ({FREQS[band]} MHz, free space) ==")
        keys = list(data["ladders"][band])
        print("  n  " + "".join(f"{k:>22}" for k in keys))
        for i, n in enumerate(LADDER):
            row = f"{n:4d} "
            for k in keys:
                r, x = data["ladders"][band][k][i][1:]
                row += f"{r:9.2f} {x:+9.2f}j  "
            print(row)

    for band in FREQS:
        print(f"\n== feed-bridge eps sweep {band} (nominal={EPS_NOMINAL}) ==")
        keys = list(data["eps"][band])
        print("  eps    " + "".join(f"{k:>22}" for k in keys))
        for i, eps in enumerate(EPS_LADDER):
            row = f"{eps:7.4f} "
            for k in keys:
                r, x = data["eps"][band][k][i][1:]
                row += f"{r:9.2f} {x:+9.2f}j  "
            print(row)
        # linear-in-eps extrapolation from the two smallest rungs, per lane
        for k in keys:
            (e1, r1, x1), (e0, r0, x0) = (
                data["eps"][band][k][-2],
                data["eps"][band][k][-1],
            )
            r_lim = r0 + (r0 - r1) * e0 / (e1 - e0)
            x_lim = x0 + (x0 - x1) * e0 / (e1 - e0)
            i_ab = EPS_LADDER.index(EPS_AS_BUILT)
            r_ab, x_ab = data["eps"][band][k][i_ab][1:]
            print(
                f"  {k}: eps->0 limit {r_lim:.2f}{x_lim:+.2f}j; "
                f"as-built artifact {r_ab - r_lim:+.2f}{x_ab - x_lim:+.2f}j"
            )


if __name__ == "__main__":
    main()
