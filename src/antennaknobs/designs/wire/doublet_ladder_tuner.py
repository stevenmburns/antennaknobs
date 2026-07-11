"""88 ft doublet + 100 ft of 600 Ω open-wire line + lossy T-network tuner —
the "non-resonant wire and a matchbox" station, modelled from the rig
(issue #300).

The other half of the comparison with `dipoles.invvee_coax_station`: instead
of a resonant antenna on 50 Ω coax, a deliberately non-resonant flat doublet
(88 ft ≈ 26.8 m total, `design_freq` 5.593 MHz sizes it) feeds 100 ft of
`openwire-600` ladder line (issue #297) into a T-network — series C, shunt L,
series C, the `inverted_l_tmatch` topology — whose inductor has a finite
`coil_q` (issue #298). The source sits at the virtual **rig** node, so
impedance, SWR, gain, and the power budget (issue #299) are all referenced to
the transmitter.

Stock values match ~50 Ω at 7.1 MHz (40 m): the readout shows SWR ≈ 1 while
the budget itemizes where the watts actually go — with Q = 200 about 4 % in
the line and 4–5 % in the tuner coil, ~92 % radiated. Retune for 80 m
(3.8 MHz: C1 ≈ 44.6 pF, L ≈ 27.05 µH, C2 ≈ 6865 pF) and the same doublet is
electrically short: the line's SWR loss and the coil loss each climb to
~14 %, the honest cost of working a too-short wire. The classic folklore —
"open-wire line shrugs off SWR, the tuner coil is where multiband
flexibility is paid for" — falls out of the circuit solve as numbers.

T-network caveats inherited from `inverted_l_tmatch`: the degenerate slider
endpoints are physics (a 0 pF series cap is an open — `series_c1_pF = 0`
open-circuits the source, reported as Z = ∞), and T-match solutions are not
unique — bigger capacitors with a smaller L generally mean less circulating
current and lower coil loss.
"""

from types import MappingProxyType

from ...network import TL, Driven, Network, PortAtEdge, PortVirtual, Shunt, TwoPort
from ..dipoles.invvee import Builder as InvVee


class Builder(InvVee):
    default_params = MappingProxyType(
        {
            **InvVee.default_params,
            # 88 ft flat doublet: 0.25·λ(5.593 MHz)·1.0 = 13.41 m per side.
            "design_freq": 5.593,
            "freq": 7.1,
            "angle_deg": 0.0,
            "length_factor": 1.0,
            "base": 10.0,
            # Feedline: 100 ft of 600 Ω open-wire line.
            "line_len_m": 30.48,
            # T-network, tuned for ~50 Ω at 7.1 MHz on the stock doublet
            # (see the 80 m retune in the module docstring).
            "series_c1_pF": 74.16,
            "shunt_l_uH": 4.7007,
            "series_c2_pF": 1617.7,
            # Tuner coil Q (issue #298). Defaults LOSSY — the point of this
            # design is seeing the tuner cost; set 0 for the ideal coil.
            "coil_q": 200.0,
            "ui_params": MappingProxyType(
                {
                    **InvVee.default_params["ui_params"],
                    "target_z0": 50.0,
                    "angle_deg": {"hidden": True},
                    "line_len_m": {"min": 3.0, "max": 100.0, "unit": "m"},
                    # Ranges span the 40 m stock tune AND the 80 m retune.
                    "series_c1_pF": {"min": 5.0, "max": 500.0},
                    "shunt_l_uH": {"min": 0.5, "max": 40.0},
                    "series_c2_pF": {"min": 100.0, "max": 10000.0},
                    "coil_q": {"min": 0.0, "max": 400.0},
                }
            ),
        }
    )

    def build_wires(self):
        # Flat-doublet geometry from the inv-vee builder (angle 0); the
        # driven gap becomes the named "feed" port and loses its inline
        # excitation — the source lives at the virtual rig node.
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
                "feed": PortAtEdge("feed"),
                "li": PortVirtual("li"),  # line input (tuner output)
                "m": PortVirtual("m"),  # tee midpoint
                "rig": PortVirtual("rig"),
            },
            branches=[
                TL.from_cable("openwire-600", "li", "feed", self.line_len_m),
                TwoPort(a="rig", b="m", c=self.series_c1_pF * 1e-12),
                Shunt(
                    port="m",
                    l=self.shunt_l_uH * 1e-6,
                    ql=self.coil_q if self.coil_q > 0 else None,
                ),
                TwoPort(a="m", b="li", c=self.series_c2_pF * 1e-12),
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
