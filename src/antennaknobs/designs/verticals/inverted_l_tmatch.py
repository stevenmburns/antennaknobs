r"""10 m inverted-L worked on the 12 m band through a T-network tuner —
the first design with a pure interior circuit node (series C, shunt L,
series C), exercising the MNA network core on the classic "wire antenna +
T-match" situation.

Geometry is inherited wholesale from `inverted_l`: the same 10 m
(28.57 MHz) bent, top-loaded vertical with four elevated radials. Operated
on 24.9 MHz that riser is electrically short and the feed is the textbook
tuner case — Z_ant ≈ 10.8 − 121.7j Ω (low R, big capacitive X), nowhere
near 50 Ω.

A **T-network** (the standard ham "T-tuner" topology, a high-pass tee)
fixes it with two series capacitors flanking a shunt inductor:

    source ──[ C1 series ]──┬──[ C2 series ]── feed
                            │
                     [ L shunt ]── common

The port spec drives a virtual `in` node, chains `TwoPort` capacitors
through a virtual midpoint `m`, and hangs a `Shunt` inductor off `m`. The
midpoint is a pure interior circuit node — no antenna segment, no TL,
nothing but lumped Group-2 branches meeting at a KCL row — which no other
design exercises. Stock values land ~50 Ω / SWR ≈ 1.0005 at 24.9 MHz.

Because the antenna is short (R ≈ 11 Ω) the match must ride a virtual
resistance of ~2 kΩ, so there is no symmetric-capacitor solution and the
loaded Q is high (~13) — the real-world "narrow retune on a short
antenna" behavior, visible here as a sharp SWR notch in a frequency sweep.

Degenerate slider endpoints (all legal since the MNA core, issue #285):
a 0 H shunt inductor hard-shorts the midpoint to common (input becomes
pure C1 reactance); a 0 F series capacitor is an OPEN — note this is the
opposite convention from the L-match's arms, where zero meant "element
absent": an absent series capacitor in a T-network is C → ∞ (a wire), not
C → 0. Setting `series_c2_pF = 0` disconnects the antenna entirely (the
source then sees only C1 + L), and `series_c1_pF = 0` open-circuits the
source itself.
"""

from types import MappingProxyType

from .inverted_l import Builder as InvertedL
from ...network import Driven, Network, PortOnWire, PortVirtual, Shunt, TwoPort


class Builder(InvertedL):
    default_params = MappingProxyType(
        {
            **InvertedL.default_params,
            # Antenna is cut for 10 m (inherited design_freq 28.57) but
            # operated on 12 m.
            "freq": 24.9,
            # T-network elements, tuned for ~50 Ω at 24.9 MHz on the stock
            # inverted-L (virtual resistance ~2 kΩ; see module docstring).
            "series_c1_pF": 20.47,  # source-side series capacitor
            "shunt_l_uH": 0.6458,  # shunt inductor at the tee midpoint
            "series_c2_pF": 254.5,  # antenna-side series capacitor
            # Coil quality factor (issue #298): adds R = ωL/Q in series with
            # the tee's shunt inductor. 0 = ideal coil (the historical
            # behavior); real air-wound coils run ~50–400. A T-network runs
            # high circulating current through this coil, so its loss is the
            # classic hidden tuner cost.
            "coil_q": 0.0,
            "ui_params": MappingProxyType(
                {
                    # Matched to 50 Ω, so the SWR readout shows ~1:1.
                    "target_z0": 50.0,
                    "default_view": "yz",
                    "series_c1_pF": {"min": 5.0, "max": 60.0},
                    "shunt_l_uH": {"min": 0.1, "max": 2.0},
                    "series_c2_pF": {"min": 50.0, "max": 500.0},
                    "coil_q": {"min": 0.0, "max": 400.0},
                }
            ),
        }
    )

    def build_wires(self):
        # Reuse the inverted-L geometry verbatim; rename the driven base gap
        # as the network's "feed" port and clear its inline excitation — the
        # T-network supplies the source at the virtual `in` node instead.
        wires = []
        for p0, p1, nseg, ev, *rest in super().build_wires():
            if ev is not None:
                wires.append((p0, p1, nseg, None, "feed"))
            else:
                wires.append((p0, p1, nseg, ev, *rest))
        return wires

    def build_network(self):
        return Network(
            ports={
                "feed": PortOnWire("feed"),
                "m": PortVirtual("m"),
                "in": PortVirtual("in"),
            },
            branches=[
                TwoPort(a="in", b="m", c=self.series_c1_pF * 1e-12),
                Shunt(
                    port="m",
                    l=self.shunt_l_uH * 1e-6,
                    ql=self.coil_q if self.coil_q > 0 else None,
                ),
                TwoPort(a="m", b="feed", c=self.series_c2_pF * 1e-12),
            ],
            sources=[Driven(port="in", voltage=1 + 0j)],
        )
