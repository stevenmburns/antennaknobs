"""Inverted-vee (or flat dipole) fed across a real gap between its arm ends.

The stock ``dipoles.invvee`` feeds through a 0.1 m bridge wire that carries
a delta gap; ``dipoles.invvee_apex`` closes the arms to one point and inserts
a series gap there. This design is the third model, and the one a real
centre insulator is: the two arms stop ``gap`` metres apart, nothing joins
them, and the feedline lands on the two wire ENDS. Each end is a
`PortAtEnd` (momwire's junction port, the attachment `wire.sterba_bl`'s
balanced risers use), and a 1:1 `FloatingBalun` puts the source across the
pair, so the reported impedance is the differential one between the ends.

Why it exists (momwire#1408 / #1396 study, 2026-10-09): the gap width here
is GEOMETRY — the user draws it — so it does not shrink as the mesh is
refined, which is what makes every delta-gap and gap-wire feed drift on a
fat wire. On a d/λ 0.0085 dipole with segments down to 0.57 radii the
gap-wire feeds collapsed toward 13 Ω while this one stayed within 4 Ω of its
coarse-mesh value. The width is physics, not a nuisance: with no metal in
the gap the antenna is ``gap`` shorter, and at 10 m a 0.1 m gap moves X by
tens of ohms against the bridge model of the same arms.

Same knobs as the stock invvee plus ``gap``. Arm geometry matches the stock
design with ``gap`` = 0.1 m (its bridge length), so stock vs this design at
the defaults is the bridge metal and nothing else. ``angle_deg`` = 0 is a
flat dipole.

Engine support is `PortAtEnd`'s: momwire's junction-port backends only;
NEC-2-shaped engines refuse the port by name.
"""

import math
from types import MappingProxyType

from antennaknobs.designs.dipoles.invvee import Builder as InvVee
from antennaknobs.network import (
    Driven,
    FloatingBalun,
    Network,
    PortAtEnd,
    PortVirtual,
    Wire,
)


class Builder(InvVee):
    default_params = MappingProxyType(
        {
            **{k: v for k, v in InvVee.default_params.items() if k != "ui_params"},
            # Gap between the two arm ends at the feed, metres.
            "gap": 0.1,
            "ui_params": MappingProxyType(
                {
                    **InvVee.default_params["ui_params"],
                    "gap": {"min": 0.005, "max": 0.3, "step": 0.005},
                }
            ),
        }
    )

    def build_wires(self):
        wavelength = self.design_wavelength
        driver_y = 0.25 * wavelength * self.length_factor
        angle = math.radians(self.angle_deg)
        b = self.base
        g = 0.5 * self.gap

        root = (0.0, g, b)
        tip = (
            0.0,
            g + (driver_y - g) * math.cos(angle),
            b - (driver_y - g) * math.sin(angle),
        )

        def ry(p):
            return p[0], -p[1], p[2]

        return [
            Wire(root, tip, name="right"),
            Wire(ry(tip), ry(root), name="left"),
        ]

    def build_network(self):
        return Network(
            ports={
                "feed": PortVirtual("feed"),
                "end_r": PortAtEnd("right", end="p0"),
                "end_l": PortAtEnd("left", end="p1"),
            },
            branches=[FloatingBalun(primary="feed", a="end_r", b="end_l", n=1.0)],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
