"""Yagi-Uda whose driven element is fed across a real gap between its arm ends.

The stock ``beams.yagi`` feeds the driver through a 0.1 m bridge wire that
carries a delta gap. Here the bridge is gone: the two driver arms stop
``gap`` metres apart and the source sits across their facing ENDS — two
`PortAtEnd` junction ports joined by a 1:1 `FloatingBalun`, the same
construction as ``dipoles.invvee_endport`` (see its docstring for why: the
gap is geometry, so it holds still as the mesh refines). Reflector and
directors are the stock design's, untouched.

With ``gap`` = 0.1 m (the default, the stock bridge length) the arms are the
stock arms exactly, so stock vs this design is the bridge metal and nothing
else. That metal is not small: the driver is ``gap`` shorter without it, and
the feed reactance moves by tens of ohms at 10 m. Pattern and F/B move far
less, since the parasitic elements set them.

Engine support is `PortAtEnd`'s: momwire's junction-port backends only.
"""

import math
from types import MappingProxyType

from antennaknobs.designs.beams.yagi import Builder as Yagi
from antennaknobs.network import (
    Driven,
    FloatingBalun,
    Network,
    PortAtEnd,
    PortVirtual,
    Wire,
)


class Builder(Yagi):
    default_params = MappingProxyType(
        {
            **Yagi.default_params,
            # Gap between the two driver-arm ends at the feed, metres.
            "gap": 0.1,
            "ui_params": MappingProxyType(
                {"gap": {"min": 0.005, "max": 0.3, "step": 0.005}}
            ),
        }
    )

    def build_wires(self):
        # The stock list is [S-A, B-U, U-C, D-T, T-S (bridge, fed), directors...]:
        # keep the parasitic elements, rebuild the driver arms from the gap.
        stock = super().build_wires()
        driver_y = 0.25 * self.design_wavelength * self.length_factor
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
            stock[1],
            stock[2],
            Wire(ry(tip), ry(root), name="left"),
            *stock[5:],
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
