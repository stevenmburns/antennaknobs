"""Mutual-limit / Richardson convergence of the single-wire center-fed doublet
feedpoint (free space, 7.1 MHz), on BSpline d=2 and Sinusoidal.

The delta-gap feedpoint is mesh-sensitive: both bases climb monotonically with
nominal_nsegs and Richardson/Neville-extrapolate to the SAME value (<0.05 ohm
apart) -> that mutual limit is the "correct" converged feedpoint.

Result:  Z_converged ~= 192.9 + j589.8 ohm.
(SimNEC/momwire at default meshes undershoot: ~28 seg -> 181+j573,
 ~76 seg -> 188+j583. That is why a single default-mesh solve is not the truth.)

Run:  python scratch/simnec/convergence.py
"""

from antennaknobs.designs.wire.doublet_ladder_tuner import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import Driven, Network, PortOnWire, Wire
from momwire import BSplineSolver, SinusoidalSolver

YT = 13.400300629701409


class DipoleOnly(Builder):
    def build_wires(self):
        return [Wire((0, -YT, 10.0), (0, YT, 10.0), n_seg=None, name="feed")]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed")},
            branches=[],
            sources=[Driven(port="feed")],
        )


def zfeed(solver, kw, nominal):
    b = DipoleOnly(dict(Builder.default_params))
    b.nominal_nsegs = nominal
    return complex(
        MomwireEngine(b, solver=solver, ground=None, solver_kwargs=kw).impedance()[0]
    )


def neville(hs, ys):
    """Polynomial extrapolation of ys(hs) to h=0."""
    T = list(ys)
    n = len(ys)
    for k in range(1, n):
        T = [
            ((0 - hs[i + k]) * T[i] - (0 - hs[i]) * T[i + 1]) / (hs[i] - hs[i + k])
            for i in range(n - k)
        ]
    return T[0]


if __name__ == "__main__":
    ladder = [21, 61, 161, 321, 641]
    finest = {}
    for name, solver, kw in (
        ("bs2", BSplineSolver, {"degree": 2}),
        ("sin", SinusoidalSolver, None),
    ):
        print(f"=== {name} ===")
        zs = []
        for nseg in ladder:
            z = zfeed(solver, kw, nseg)
            zs.append(z)
            print(f"   nominal_nsegs={nseg:4d}   Z = {z.real:8.3f} {z.imag:+8.3f} j")
        hs = [1.0 / n for n in ladder]
        zr = neville(hs[-4:], [z.real for z in zs[-4:]])
        zx = neville(hs[-4:], [z.imag for z in zs[-4:]])
        finest[name] = (zs[-1], complex(zr, zx))
        print(f"   Neville -> h=0 : {zr:8.3f} {zx:+8.3f} j\n")
    a, b = finest["bs2"][1], finest["sin"][1]
    print(
        f"CONVERGED (both bases agree to {abs(a - b):.3f} ohm): "
        f"{(a.real + b.real) / 2:.1f} {(a.imag + b.imag) / 2:+.1f} j"
    )
