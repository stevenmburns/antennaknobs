"""Discone: a broadband vertical (disc + cone), modelled as a wire cage
(L. B. Cebik, W4RNL).

A horizontal DISC sits above the apex of a downward-opening CONE; the coax
feeds across the small gap between the disc centre and the cone apex. The cone
behaves like a fat, tapered monopole and the disc like its ground/counterpoise,
and because both are tapered the antenna stays usefully matched (~VSWR < 2-3)
over roughly a 4:1 frequency range starting a little above the frequency where
the cone slant height is a quarter wavelength. It radiates VERTICALLY
POLARISED and omnidirectionally in azimuth, like a vertical monopole but
WIDEBAND -- the standard scanner / VHF-UHF utility antenna.

This fills the "wideband vertical / frequency-independent omni" gap: the
catalog's verticals are resonant quarter-waves and its only other broadband
member, the t2fd, is a (lossy, terminated) horizontal dipole. We approximate
the solid disc and cone by a cage of radial WIRES (the usual NEC modelling
trick); the disc doubles as a self-contained counterpoise, so no ground card
is needed.

Geometry, in the framework's (x, y, z) convention:
  - z : vertical; the disc is the horizontal cage at the top, the cone hangs
        below it, fed across the apex gap -- VERTICALLY POLARISED
  - x, y : the disc radials and cone slant wires spread in azimuth

        disc:  ----o----o----o----   (horizontal radial cage)   z = base
                       \\ | /
                        \\|/  feed gap (apex)
                        /|\\
                       / | \\
        cone:         o  o  o         (downward radial cage)     z < base
"""

from antennaknobs import AntennaBuilder
import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the disc (and feedpoint) above ground.
            "base": 8.0,
            # Cone slant-wire length as a fraction of a wavelength at the design
            # frequency. ~1/4 wl sets the LOW-frequency corner; the antenna
            # works upward from there.
            "cone_frac": 0.27,
            # Half-angle of the cone from vertical, in degrees (~30 deg is the
            # classic ~60-degree-included discone cone).
            "cone_half_angle_deg": 30.0,
            # Disc radius as a fraction of the cone BASE radius -- the textbook
            # "disc diameter ~ 0.7 * cone base diameter" rule.
            "disc_ratio": 0.7,
            # Number of radial wires in each cage (disc and cone).
            "n_wires": 12,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    # Vertical radiator; the xz view reads the elevation.
                    "default_view": "xz",
                    # Broadband by design: let the GUI sweep run wide rather
                    # than band-locking to 10 m.
                    "cone_frac": {
                        "min": 0.2,
                        "max": 0.35,
                    },
                    "disc_ratio": {
                        "min": 0.5,
                        "max": 1.0,
                        "step": 0.01,
                        "precision": 3,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        cone = self.cone_frac * wavelength
        ang = math.radians(self.cone_half_angle_deg)
        cone_r = cone * math.sin(ang)  # cone base radius
        cone_h = cone * math.cos(ang)  # cone vertical drop
        disc_r = self.disc_ratio * cone_r  # disc radius (~0.7 * cone base r)
        m = int(self.n_wires)

        z_disc = self.base  # disc plane (cone apex just below)
        z_apex = self.base - 2 * eps  # cone apex
        z_cone_base = self.base - cone_h

        tups = []
        # Feed: a one-segment driven gap between the disc centre and the cone
        # apex (the coax point of a discone).
        tups.append(
            (
                (0.0, 0.0, z_disc),
                (0.0, 0.0, z_apex),
                self.segs_for(2 * eps, quarter),
                1 + 0j,
            )
        )

        for i in range(m):
            phi = 2 * math.pi / m * i
            c, s = math.cos(phi), math.sin(phi)
            # Disc radial: horizontal, out from the centre.
            tups.append(
                (
                    (0.0, 0.0, z_disc),
                    (disc_r * c, disc_r * s, z_disc),
                    self.segs_for(disc_r, quarter),
                    None,
                )
            )
            # Cone slant wire: down and out from the apex.
            tups.append(
                (
                    (0.0, 0.0, z_apex),
                    (cone_r * c, cone_r * s, z_cone_base),
                    self.segs_for(cone, quarter),
                    None,
                )
            )

        return tups
