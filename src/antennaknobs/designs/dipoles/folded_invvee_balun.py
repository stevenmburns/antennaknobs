"""Folded inverted-V fed through a 4:1 balun and real coax — the
`Transformer` showcase (issue #301).

The stock folded inv-vee presents ~218 Ω at its feed (the folded geometry's
step-up, pulled below the ideal 4×73 by droop and tuning). A 4:1 balun
(`Transformer` with `balun_n` = 0.5, so Z_line = n²·Z_feed ≈ 55 Ω) steps
that down onto `line_len_m` of 50 Ω cable, and the source sits at the
virtual **rig** node — the full chain the back of a real folded dipole
carries.

The balun is lossy the way a real ferrite one is: `lmag_uH` is the
magnetizing inductance shunting its line side and `qlmag` its Q (core
loss). At 28 MHz the magnetizing reactance dwarfs 50 Ω and the balun is
nearly free; drag the measurement frequency down and the classic low-band
insertion-loss rolloff appears as the balun's `(mag)` row in the power
budget. Winding resistance is available via the network's `r` if you want
it; the geometry knobs are the stock folded-invvee ones.
"""

from types import MappingProxyType

from antennaknobs.network import (
    CABLES,
    TL,
    Driven,
    Instance,
    Network,
    PortOnWire,
    PortVirtual,
)
from antennaknobs.station import balun
from antennaknobs.designs.dipoles.folded_invvee import Builder as FoldedInvVee


class Builder(FoldedInvVee):
    default_params = MappingProxyType(
        {
            **FoldedInvVee.default_params,
            "cable": "RG-8X",
            "line_len_m": 30.48,  # 100 ft
            # 4:1 balun: line-side voltage is half the feed-side voltage.
            "balun_n": 0.5,
            "lmag_uH": 10.0,
            "qlmag": 100.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "cable": {"enum_options": tuple(sorted(CABLES))},
                    "line_len_m": {"min": 3.0, "max": 100.0, "unit": "m"},
                    # 100 ft of coax rotates the sweep trace around the
                    # Smith chart several times over the default ±20/25 %
                    # window — lock the sweep to the band being measured.
                    "sweep_policy": {"anchor": "meas_freq", "band_locked": True},
                    "balun_n": {"min": 0.25, "max": 1.0},
                    "lmag_uH": {"min": 1.0, "max": 50.0},
                    "qlmag": {"min": 0.0, "max": 400.0},
                }
            ),
        }
    )

    def build_wires(self):
        # Stock folded inv-vee geometry; the driven gap becomes the named
        # "feed" port (the source lives at the virtual rig node).
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
                "bal": PortVirtual("bal"),  # balun line-side terminals
                "rig": PortVirtual("rig"),
            },
            branches=[
                TL.from_cable(self.cable, "rig", "bal", self.line_len_m),
                Instance(
                    "balun",
                    balun(
                        n=self.balun_n,
                        lmag_uH=self.lmag_uH,
                        qlmag=self.qlmag if self.qlmag > 0 else None,
                    ),
                    line="bal",
                    ant="feed",
                ),
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
