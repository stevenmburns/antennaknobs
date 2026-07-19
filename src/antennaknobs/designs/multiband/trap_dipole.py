"""Dual-band trap dipole — Load(parallel=True) showcase for issue #65.

A trap dipole inserts a parallel-LC tank in series with each arm of the
dipole. At the trap's resonant frequency the tank is high-Z (effectively
open) so the segment's current is interrupted — only the inner arms
radiate, behaving as a shorter dipole. Well below trap resonance the tank
looks inductive, electrically lengthening the outer arms and letting the
whole antenna act as a loaded dipole at the low band.

The trap is a `Load(parallel=True)` on a single segment of a continuous
wire. MomwireEngine modifies the segment's MoM Z-diagonal via Sherman-Morrison;
PyNECEngine emits `ld_card type 1` (parallel RLC). The wires on either
side of the trap segment share an endpoint and junction continuously
through the trap segment — the trap impedance is *in series with* the
segment's current path, not a discrete circuit element bridging a gap.

(An earlier draft used `TwoPort` across stub wires separated by a small
geometric gap. That was the wrong primitive: with the named ports at the
tip of each polyline where the open-end BC forces basis-function current
toward zero, modifying admittance there had no effect on the antenna.
Load on a mid-wire segment is the right idiom — see NEC2's ld_card.)

Default params place the trap at 28 MHz and pick a half-arm length so the
loaded full dipole comes near resonance at 14 MHz. Trap L and C can be
tuned independently; defaults are LC-resonant at design_freq.
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Load, Network, PortOnWire

import math
from types import MappingProxyType


def _resonant_C_pF(L_uH: float, freq_mhz: float) -> float:
    """C in pF such that ω² LC = 1 at `freq_mhz`."""
    omega = 2 * math.pi * freq_mhz * 1e6
    return 1.0 / (omega**2 * L_uH * 1e-6) * 1e12


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # Inner dipole self-resonates at design_freq when the trap is
            # open; the trap is also tuned here by default.
            "design_freq": 28.0,
            "freq": 28.0,
            # Inner half-arm length as a fraction of λ_design/4. 1.0 = exactly
            # resonant inner dipole when the trap is open.
            "length_factor": 1.0,
            # Outer half-arm physical length beyond the trap (m). The total
            # half-arm = inner + trap_seg + outer; the full-length antenna
            # sets the low-band tuning when the trap is loading inductively.
            "outer_arm_m": 1.3,
            # Trap parallel-LC values, independent. Default C is whatever
            # makes the trap resonate at design_freq with the default L.
            "trap_L_uH": 5.0,
            "trap_C_pF": _resonant_C_pF(L_uH=5.0, freq_mhz=28.0),
            # Antenna height above ground (m).
            "base": 5.0,
            # Length (m) of the single-segment "trap wire" whose middle
            # segment is the named Load port. Should be much shorter than λ
            # so radiation from the trap segment itself is negligible.
            "trap_seg_m": 0.05,
        }
    )

    def build_wires(self):
        wavelength = 299.792458 / self.design_freq
        inner_arm = 0.25 * wavelength * self.length_factor
        z = self.base
        trap_seg = self.trap_seg_m
        outer = self.outer_arm_m

        # Layout (x-axis only, all wires at y=0, height=z):
        #
        #  ←─ outer_l ─→ ← trap_l ─→ ←──── inner ────→ ← trap_r ─→ ←─ outer_r ─→
        #  -X_outer_tip                                                  +X_outer_tip
        #            -X_trap_outer  -X_trap_inner   +X_trap_inner   +X_trap_outer
        #
        # Wires share vertices at every "│" → momwire junctions them continuously.
        # The named single-segment "trap_l" and "trap_r" wires sit *inside*
        # the wire chain, so their basis-function current carries the actual
        # arm current. Loading them with parallel-LC interrupts that current
        # at trap resonance, exactly as a physical trap would.

        # Each arm: outer_main + trap_seg + inner_half (joining at center feed).
        x_trap_inner_l = -inner_arm
        x_trap_outer_l = x_trap_inner_l - trap_seg
        x_outer_tip_l = x_trap_outer_l - outer

        x_trap_inner_r = inner_arm
        x_trap_outer_r = x_trap_inner_r + trap_seg
        x_outer_tip_r = x_trap_outer_r + outer

        def p(x):
            return (x, 0.0, z)

        # Catalog-norm meshing: nominal_nsegs per quarter-wave via segs_for,
        # so the convergence slider reaches this design like every other.
        quarter = 0.25 * wavelength
        n_outer = self.segs_for(outer, quarter)
        # Single continuous inner wire spanning −X_inner → +X_inner so the
        # named "feed" middle segment lands exactly at the geometric centre
        # (x = 0). Splitting the inner span at the origin would put `feed`
        # on the middle of *one half*, offsetting the feed point by
        # X_inner/2 — a real asymmetry that broke the symmetric design.
        # Engine parity coercion bumps to odd/even as needed.
        n_inner = self.segs_for(2 * inner_arm, quarter)

        return [
            # Left arm, outer → trap.
            (p(x_outer_tip_l), p(x_trap_outer_l), n_outer, None),
            (
                p(x_trap_outer_l),
                p(x_trap_inner_l),
                self.segs_for(trap_seg, quarter),
                None,
                "trap_l",
            ),
            # Inner span — one wire, feed at middle = origin.
            (p(x_trap_inner_l), p(x_trap_inner_r), n_inner, None, "feed"),
            # Right arm, trap → outer.
            (
                p(x_trap_inner_r),
                p(x_trap_outer_r),
                self.segs_for(trap_seg, quarter),
                None,
                "trap_r",
            ),
            (p(x_trap_outer_r), p(x_outer_tip_r), n_outer, None),
        ]

    def build_network(self):
        L = self.trap_L_uH * 1e-6
        C = self.trap_C_pF * 1e-12
        return Network(
            ports={
                "feed": PortOnWire("feed"),
                "trap_l": PortOnWire("trap_l"),
                "trap_r": PortOnWire("trap_r"),
            },
            branches=[
                # Parallel-LC trap: Z = jωL / (1 − ω²LC); diverges at ω₀
                # and acts inductively below. Series-in-line with the
                # segment's current via ld_card-equivalent stamping.
                Load(port="trap_l", l=L, c=C, parallel=True),
                Load(port="trap_r", l=L, c=C, parallel=True),
            ],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
