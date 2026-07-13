"""Lumped-coupled dipole pair — the TwoPort-branch showcase for issue #65.

Two parallel half-wave dipoles a fraction of a wavelength apart. Only the
front one is fed; the rear one is a parasite reachable *only* through a lumped
series R+jωL element bridging the two feed segments (a `TwoPort` branch). By
tuning that coupling impedance you steer current onto the parasite with a
chosen magnitude and phase, turning the pair into a small end-fire beam —
the lumped analogue of a reactance-loaded parasitic element.

This is the smallest geometry that exercises a `TwoPort` as a genuine 2-port
between two distinct antenna segments (not a self-load on one segment, which
is what `Load` covers). It is the cross-engine cross-check for issue #65
piece (B): MomwireEngine and PyNECEngine both reduce the branch through the
shared `NetworkReducer` stamp, and PyNECEngine with ``native_nt=True`` instead
bakes a real NEC2 `nt_card` and solves it simultaneously with the MoM currents
— an independent oracle, exactly as `build_tls()` → native `tl_card` is the
oracle for the TL branch. All three agree on impedance and far field.

`coupling_r_ohm` / `coupling_l_uH` set the bridge impedance; large R (≳1 kΩ)
opens the branch and recovers the isolated driven dipole (the base case the
cross-check pins first).
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, TwoPort

from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.0,
            "freq": 28.0,
            # Dipole half-arm as a fraction of λ/4 (1.0 = resonant half-wave).
            "length_factor": 0.95,
            # Front-to-rear spacing as a fraction of λ.
            "spacing_factor": 0.13,
            # Lumped series R+jωL bridging the two feed segments.
            "coupling_r_ohm": 20.0,
            "coupling_l_uH": 0.10,
            # Height above the origin plane (kept out of any ground image).
            "base": 7.0,
        }
    )

    def build_wires(self):
        wavelength = 299.792458 / self.design_freq
        half_arm = 0.25 * wavelength * self.length_factor
        spacing = self.spacing_factor * wavelength
        z = self.base
        tups = []
        for x, name in ((0.0, "front"), (-spacing, "rear")):
            # One straight wire per dipole, feed edge at the centre. No `ev` —
            # the Network supplies the source (front) and the coupling terminal
            # (rear); `name` marks each centre segment for PortOnWire lookup.
            tups.append(((x, -half_arm, z), (x, half_arm, z), 21, None, name))
        return tups

    def build_network(self):
        return Network(
            ports={
                "front": PortOnWire("front"),
                "rear": PortOnWire("rear"),
            },
            branches=[
                TwoPort(
                    a="front",
                    b="rear",
                    r=self.coupling_r_ohm,
                    l=self.coupling_l_uH * 1e-6,
                ),
            ],
            sources=[Driven(port="front", voltage=1 + 0j)],
        )
