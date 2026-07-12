"""Inverted-V fed through real coax — the classic "resonant antenna on
50 Ω line" station, modelled from the rig (issue #300).

Geometry is the stock `dipoles.invvee` (28.47 MHz half-wave V, ~32° droop)
with the apex raised to 10 m so the station pair (see below) compares at the
same height.
What changes is the reference plane: the source moves to a virtual **rig**
port and reaches the feedpoint through `line_len_m` of a real cable from
the `CABLES` catalog (`TL.from_cable`, issue #297) — so the impedance, SWR,
gain, and power budget the workbench reports are what the *transmitter*
sees, not the feedpoint.

On the design frequency the V is near 50 Ω and the line runs close to
matched: the budget shows roughly the cable's matched loss (~1.6 dB ≈ 31 %
for 100 ft of RG-8X at 28 MHz — coax at 10 m is not cheap) and nothing
else. Drag the measurement frequency off resonance and the SWR-multiplied
line loss appears by itself — it emerges from the MNA circuit solve, not
from a formula. Swap
the `cable` preset (dropdown) to compare RG-58 against LMR-400, or pick
the 450/600 Ω lines to see why open-wire feeders shrug off SWR that would
cook coax.

The natural comparison partner is `wire.doublet_ladder_tuner` — the same
question answered the other way (non-resonant doublet + low-loss line +
lossy tuner).
"""

from types import MappingProxyType

from ...network import CABLES, TL, Driven, Network, PortOnWire, PortVirtual
from .invvee import Builder as InvVee


class Builder(InvVee):
    default_params = MappingProxyType(
        {
            **InvVee.default_params,
            "cable": "RG-8X",
            "line_len_m": 30.48,  # 100 ft
            # Apex at 10 m, matching wire.doublet_ladder_tuner, so the
            # station pair compares at the same height.
            "base": 10.0,
            "ui_params": MappingProxyType(
                {
                    **InvVee.default_params["ui_params"],
                    "target_z0": 50.0,
                    "cable": {"enum_options": tuple(sorted(CABLES))},
                    "line_len_m": {"min": 3.0, "max": 100.0, "unit": "m"},
                    # 100 ft of coax rotates the sweep trace around the
                    # Smith chart several times over the default ±20/25 %
                    # window — lock the sweep to the band being measured.
                    "sweep_policy": {"anchor": "meas_freq", "band_locked": True},
                }
            ),
        }
    )

    def build_wires(self):
        # Stock inv-vee geometry; the driven gap becomes the named "feed"
        # port and loses its inline excitation — the source lives at the
        # virtual rig end of the line instead.
        wires = []
        for p0, p1, nseg, ev, *rest in super().build_wires():
            if ev is not None:
                wires.append((p0, p1, nseg, None, "feed"))
            else:
                wires.append((p0, p1, nseg, ev, *rest))
        return wires

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
            branches=[
                TL.from_cable(self.cable, "rig", "feed", self.line_len_m),
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
