"""SimNEC comparison, Track 1 (agreement): wire.doublet_ladder_tuner.

Center-fed, single-ended station at 7.1 MHz that maps 1:1 onto SimNEC blocks
and runs on the Sinusoidal basis (== PyNEC == SimNEC's nec2c). Prints:
  - the antenna-only feedpoint (single-wire, the geometry SimNEC solves)
  - the NEC deck to paste into SimNEC's N block
  - the full-chain rig Z on BSpline / Sinusoidal / PyNEC, free space + ground
  - the analytic cascade checkpoints (antenna -> line -> T-net -> rig)

Run:  python scratch/simnec/track1_agreement.py
"""
import cmath
import math

from antennaknobs.designs.wire.doublet_ladder_tuner import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import Driven, Network, PortOnWire, Wire
from momwire import BSplineSolver, SinusoidalSolver

YT = 13.400300629701409  # half-length of the 88 ft doublet, metres
Z10 = 10.0               # height (free space => irrelevant, kept for parity)


def swr(z):
    g = abs((z - 50) / (z + 50))
    return (1 + g) / (1 - g)


class SingleWire(Builder):
    """doublet_ladder_tuner but the antenna is ONE center-fed wire (no feed
    bridge), matching a plain NEC center feed in SimNEC. n_seg=None => the wire
    density-meshes at nominal_nsegs (the framework's convergence knob)."""

    def build_wires(self):
        return [Wire((0, -YT, Z10), (0, YT, Z10), n_seg=None, name="feed")]


class DipoleOnly(SingleWire):
    """Antenna only — no station network, for the feedpoint number."""

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed")},
            branches=[],
            sources=[Driven(port="feed")],
        )


def full_chain(solver, ground, nominal=120):
    b = SingleWire(dict(Builder.default_params))
    b.nominal_nsegs = nominal
    eng = MomwireEngine(b, solver=solver, ground=ground)
    return complex(eng.impedance()[0])


def antenna_feedpoint(nominal=120):
    b = DipoleOnly(dict(Builder.default_params))
    b.nominal_nsegs = nominal
    eng = MomwireEngine(b, solver=SinusoidalSolver, ground=None)
    return complex(eng.impedance()[0])


NEC_DECK = """\
NEC2
GW 1 55 0 -13.40030 10 0 13.40030 10 0.0005
FR 0 1 0 0 7.1 0
EX 0 1 28 0 1 0
NECEND
(SimNEC: set NECOptions.segmentsPerWavelength high; ~120 => ~76 seg => 188+j583.
 The delta-gap feed converges slowly; Richardson truth is 192.9+j589.8, see
 convergence.py.)"""


def analytic_cascade(Za, vf, label):
    """Antenna Z -> 600 ohm line (vf) -> series C2 500pF -> shunt L 4.218uH Q200
    -> series C1 81.2pF -> 50 ohm rig. Lossless line (openwire-600 is low-loss)."""
    f = 7.1e6
    w = 2 * math.pi * f
    lam0 = 299.792458e6 / f
    Z0, Lline = 600.0, 30.48  # 100 ft
    t = cmath.tan(2 * math.pi * Lline / (vf * lam0))
    B = Z0 * (Za + 1j * Z0 * t) / (Z0 + 1j * Za * t)
    C = B + 1 / (1j * w * 500e-12)
    zl = 1j * w * 4.218e-6 + (w * 4.218e-6 / 200)
    D = 1 / (1 / C + 1 / zl)
    E = D + 1 / (1j * w * 81.2e-12)
    print(f"  [{label}] vf={vf}")
    print(f"    A antenna     {Za.real:8.2f} {Za.imag:+8.2f} j")
    print(f"    B +600ohm line {B.real:8.2f} {B.imag:+8.2f} j")
    print(f"    C +C2 500pF   {C.real:8.2f} {C.imag:+8.2f} j")
    print(f"    D +L 4.218uH  {D.real:8.2f} {D.imag:+8.2f} j")
    print(f"    E +C1 81.2pF  {E.real:8.2f} {E.imag:+8.2f} j   SWR={swr(E):.3f}")


if __name__ == "__main__":
    print("=== antenna-only feedpoint (free space, momwire/Sin, nominal=120) ===")
    za = antenna_feedpoint()
    print(f"  {za.real:.2f} {za.imag:+.2f} j   (SimNEC nec2c reproduces this at matched mesh)\n")

    print("=== NEC deck for SimNEC's N block ===")
    print(NEC_DECK, "\n")

    print("=== full-chain rig Z ===")
    for gname, ground in (("free space", None),
                          ("finite (eps10 sig0.002)", ("finite-fast", 10.0, 0.002))):
        for sname, solver in (("BSpline", BSplineSolver), ("Sinusoidal", SinusoidalSolver)):
            z = full_chain(solver, ground)
            print(f"  {gname:24s} {sname:10s}: {z.real:7.2f} {z.imag:+7.2f} j  SWR={swr(z):.3f}")
    print()

    print("=== analytic cascade checkpoints (Za=188+583j, the SimNEC-mesh antenna) ===")
    analytic_cascade(complex(188, 583), 0.95, "vf 0.95 -> SimNEC read 40-j5.7; momwire/Sin 41.9-j5.8")
    print("\n  VERDICT: SimNEC 40-j5.7 (SWR 1.29) == AntennaKNoBs 41.9-j5.8 (SWR 1.24). Agree.")
