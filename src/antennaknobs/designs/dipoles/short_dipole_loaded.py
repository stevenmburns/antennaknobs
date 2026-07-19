"""Center-loaded shortened dipole — the Load-branch showcase for issue #65.

A half-wave dipole shortened to `length_factor` × λ/2 has a small radiation
resistance plus a large capacitive reactance. Adding a series inductor at
the feed (a "loading coil") cancels the capacitive reactance and pulls
the input impedance toward resonance. Both Momwire's Sherman-Morrison rank-1
Y update and PyNEC's ld_card produce the same shift, which makes this the
natural cross-engine cross-check for the Load branch.

`inductance_uH` is whatever cancels the reactance of the unloaded short
dipole at `design_freq` — recompute it if you change `length_factor`.
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Load, Network, PortOnWire

from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.0,
            "freq": 28.0,
            # Total length as a fraction of λ/2. <1.0 shortens the dipole.
            "length_factor": 0.5,
            # Series inductor (µH) at the feed point. ~4.65 µH cancels the
            # ~−820 Ω capacitive reactance of the 0.5·λ/2 short dipole at
            # 28 MHz; both engines land within ±15 Ω of zero reactance.
            "inductance_uH": 4.65,
        }
    )

    def build_wires(self):
        wavelength = 299.792458 / self.design_freq
        half_arm = 0.25 * wavelength * self.length_factor
        # Single straight wire spanning the dipole, feed at the centre.
        # No `ev` — the Network supplies the source; `name` marks the
        # segment for PortOnWire resolution.
        return [
            (
                (0, -half_arm, 5),
                (0, half_arm, 5),
                self.segs_for(2 * half_arm, 0.25 * wavelength),
                None,
                "feed",
            )
        ]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed")},
            branches=[Load(port="feed", l=self.inductance_uH * 1e-6)],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
