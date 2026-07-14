"""40 m wide-band phased-driver wire Yagi (L. B. Cebik, W4RNL, "Wide-Band
40-Meter Yagis", Part 3).

A fixed wire beam hung between supports that covers ALL of 7.0-7.3 MHz with
50-ohm SWR under 1.5 -- where a conventional 2-element wire Yagi holds only
~2/3 of the band -- using no traps and no loading. The trick is a
PHASED-DRIVER CELL: two drivers close together (rear half 403", forward
half 379", 93" apart in Cebik's AWG #12 build), joined by a 250-ohm ladder
line with a SINGLE HALF TWIST. The transposition sets the rear driver's
current phase so the pair steers like a driver+reflector cell but with the
feedpoint R/X excursions of the two elements fighting each other instead of
adding -- that cancellation is where the bandwidth comes from. A single
director (half 377", 260" out) sharpens the forward lobe.

This is the 40 m answer to the same question `beams.owa_yagi` answers on
10 m -- hold a full band under SWR 1.5 without a matching network -- and the
two make the instructive contrast: the OWA parks a coupled RESONATOR next
to one driver, the wide-band Yagi PHASES two drivers against each other.
Cebik's wire-version table: gain climbing 5.92 -> 6.97 dBi across the band
with F/B 12.9-15.5 dB, SWR 1.42 / 1.11 / 1.48 at 7.0 / 7.15 / 7.3. This
model's feed Z tracks that table to a few ohms at all three marks and the
in-plane F/B lands 12.1 / 15.1 / 14.0 with the same mid-band peak; gain
reads ~1 dB over his column (6.8 -> 8.0), rising the same way. The
elements themselves are ladder line in the wire build -- two #12
conductors at ~1" spacing -- modelled here as the equivalent single fat
wire, sqrt(r*s) ~ 5.1 mm; thin single-wire elements shift the cell's
reactance balance visibly. The half twist IS the design: untwist the line
in the model and the feedpoint leaves the band (SWR ~20) while the
front-to-back collapses.

Geometry, in the framework's (x, y, z) convention:
  - y : the three elements run parallel to y at height `base`
  - x : the boom axis; beam fires +x (rear driver at x=0)
  - the 250-ohm phase line is an electrical element (a transposed `TL`
    branch), not geometry
Horizontally polarised.

    rear driver     =======x=======   x = 0       (port "rear")
                           | 250-ohm line, ONE half twist
    forward driver  ======[F]======   x ~ 0.056 wl (feed, 50-ohm line here)
    director        ======================   x ~ 0.157 wl
                                 beam --> +x
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, TL, WireSpec
from types import MappingProxyType


class Builder(AntennaBuilder):
    # (half-length, boom position) per element, in wavelengths at the
    # design frequency -- Cebik's Table 3 wire dimensions (403"/379"/377"
    # halves, 93" and 260" spacings at 7.15 MHz).
    REAR, FWD, DIR = 0, 1, 2
    TABLE = (
        (0.24414, 0.0),
        (0.22960, 0.05633),
        (0.22839, 0.15750),
    )

    default_params = MappingProxyType(
        {
            "design_freq": 7.15,
            "freq": 7.15,
            # Height of the wire beam above ground (hung between supports).
            "base": 15.0,
            # Phase line between the drivers: Cebik's 250-ohm #12 ladder
            # line with a single half twist, run across the driver spacing
            # ("just under 8 feet").
            "z0_phase": 250.0,
            # Overall scale knob.
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "xy",
                    "length_factor": {
                        "min": 0.95,
                        "max": 1.05,
                    },
                    "z0_phase": {
                        "min": 50.0,
                        "max": 600.0,
                        "step": 5.0,
                        "precision": 1,
                    },
                }
            ),
        }
    )

    def build_wire_material(self):
        # Cebik's wire elements are themselves LADDER LINE: two AWG #12
        # conductors (0.0808" dia) at ~1" spacing, shorted at the tips.
        # A two-conductor cage models as a single wire of equivalent
        # radius sqrt(r * s) ~ 5.1 mm -- the element fatness the Table 3
        # lengths (and the phased cell's reactance balance) assume.
        r = 0.0808 * 0.0254 / 2
        s = 1.0 * 0.0254
        return WireSpec(radius=(r * s) ** 0.5)

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength
        lf = self.length_factor

        tups = []
        for i, (half_frac, pos_frac) in enumerate(self.TABLE):
            half = half_frac * wavelength * lf
            x = pos_frac * wavelength
            z = self.base
            arm = self.segs_for(half - eps, quarter)
            L = (x, -half, z)
            C0 = (x, -eps, z)
            C1 = (x, eps, z)
            R = (x, half, z)
            if i == self.DIR:
                # Parasitic director: one unbroken wire.
                tups.append((L, R, 2 * arm + 1, None, None))
                continue
            # Both drivers carry a centre gap: the forward one is the feed,
            # the rear one takes the far end of the phase line.
            name = "feed" if i == self.FWD else "rear"
            tups.append((L, C0, arm, None, None))
            tups.append((C0, C1, 1, None, name))
            tups.append((C1, R, arm, None, None))
        return tups

    def build_network(self):
        wavelength = 299.792458 / self.design_freq
        drivers_apart = (self.TABLE[self.FWD][1] - self.TABLE[self.REAR][1]) * (
            wavelength
        )
        return Network(
            ports={"feed": PortOnWire("feed"), "rear": PortOnWire("rear")},
            branches=[
                # The single half twist: a TRANSPOSED 250-ohm line the
                # length of the driver spacing.
                TL(
                    a="feed",
                    b="rear",
                    z0=self.z0_phase,
                    length=drivers_apart,
                    transposed=True,
                ),
            ],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
