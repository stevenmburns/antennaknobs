"""Normal-mode helical vertical, continuous winding (L. B. Cebik, W4RNL).

One of the catalog's two helix variants (issue #630). This one models the
IDEAL circular winding: there is no facet-count parameter. The number of
chords per turn is derived from ``nominal_nsegs`` so that every chord comes
out at the design segment length (a quarter-wavelength divided by N) and
carries exactly one MoM segment. Refining ``nominal_nsegs`` therefore
refines the CURVE itself — chords shorten and multiply together — and a
convergence ladder converges to the true circular helix, with the
polygonal faceting error and the basis error shrinking as one. For a
winding whose facets are part of the geometry (a fixed ``pts_per_turn``
polygon, refined by subdividing segments along it), see ``faceted_helix``.

A vertical whip wound as a HELIX instead of a straight rod. When the helix
diameter and turn-to-turn pitch are both small compared with a wavelength the
antenna runs in its NORMAL mode: it radiates broadside to the helix axis just
like a short straight monopole (VERTICALLY POLARISED, omnidirectional in
azimuth), but the coiled conductor adds distributed inductance, so the whole
thing resonates at an axial height much SHORTER than a straight quarter-wave.
The price for the size reduction is a low radiation resistance and a narrow
bandwidth, both of which the model shows.

Like the framework's `vertical` / `inverted_l`, the helix works against a
small set of elevated quarter-wave RADIALS and is modelled in free space (no
ground card); a real ground-mounted install adds soil loss to the (already
low) feed resistance.

Geometry, in the framework's (x, y, z) convention:
  - z : helix axis, fed at the base against the radial counterpoise
  - x/y : the helix winds in the x-y plane at radius `radius_frac`*wl
  - the radials spread in the x-y plane at the base
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire
import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the radial counterpoise (and feedpoint) above ground.
            "base": 5.0,
            # Axial height of the helix as a fraction of a wavelength. Much
            # shorter than a straight 0.25 wl whip -- the winding makes up the
            # missing electrical length.
            "axial_frac": 0.18,
            # Helix radius as a fraction of a wavelength (small -> normal mode).
            "radius_frac": 0.012,
            # Number of turns. Together with the radius this sets the wound
            # wire length and hence the resonant frequency; tuned so X -> 0
            # at the default mesh density.
            "n_turns": 2.7,
            # Overall scale knob the optimiser tunes for resonance (X -> 0).
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    # Helically-loaded short whip -> low radiation resistance.
                    "target_z0": 50.0,
                    "default_view": "xz",
                    # Degenerate with length_factor (axial = axial_frac * wl *
                    # length_factor); pin it and keep length_factor as the knob.
                    "axial_frac": {"hidden": True},
                    "n_turns": {
                        "min": 2.0,
                        "max": 9.0,
                        "step": 0.05,
                        "precision": 2,
                    },
                    "length_factor": {
                        "min": 0.7,
                        "max": 1.3,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = self.design_wavelength
        quarter = 0.25 * wavelength

        radius = self.radius_frac * wavelength
        axial = self.axial_frac * wavelength * self.length_factor
        n_turns = self.n_turns

        z0 = self.base

        tups = []

        # Base feed: a driven gap at the foot, against the radials.
        tups.append(Wire((0.0, 0.0, z0), (0.0, 0.0, z0 + eps), ex=1 + 0j))

        # Helix: a space curve from the top of the feed gap upward. The chord
        # count comes from the design density (issue #630): the winding is cut
        # so each chord is one design-segment-length long, so auto_mesh
        # resolves every chord to exactly one segment and refining
        # nominal_nsegs refines the curve itself.
        wound = math.hypot(2.0 * math.pi * radius * n_turns, axial)
        n_pts = max(1, round(wound * self.nominal_nsegs / quarter))
        zbot = z0 + eps
        prev = (0.0, 0.0, zbot)
        for i in range(1, n_pts + 1):
            ang = 2.0 * math.pi * n_turns * i / n_pts
            x = radius * math.cos(ang) - radius  # start at angle 0 -> x=0
            y = radius * math.sin(ang)
            z = zbot + (axial * i / n_pts)
            cur = (x, y, z)
            tups.append(Wire(prev, cur))
            prev = cur

        # Elevated quarter-wave radials from the feedpoint (cf. vertical.py).
        # The radials refine with the mesh (issue #477), matching the ever-
        # finer helix chords they meet at the feed junction.
        n_radials = 4
        for j in range(n_radials):
            theta = 2 * math.pi / n_radials * j
            rx = quarter * math.cos(theta)
            ry = quarter * math.sin(theta)
            tups.append(Wire((0.0, 0.0, z0), (rx, ry, z0)))

        return tups
