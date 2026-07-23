"""Normal-mode helical vertical (L. B. Cebik, W4RNL).

A vertical whip wound as a HELIX instead of a straight rod. When the helix
diameter and turn-to-turn pitch are both small compared with a wavelength the
antenna runs in its NORMAL mode: it radiates broadside to the helix axis just
like a short straight monopole (VERTICALLY POLARISED, omnidirectional in
azimuth), but the coiled conductor adds distributed inductance, so the whole
thing resonates at an axial height much SHORTER than a straight quarter-wave.
That is the classic "helically-loaded short vertical" -- the rubber-duck and
the loaded mobile whip live here. The price for the size reduction is a low
radiation resistance and a narrow bandwidth, both of which the model shows.

This fills two gaps at once. Geometrically it is the catalog's first genuinely
THREE-DIMENSIONAL, non-planar radiator: every other design lies in a plane or a
few parallel planes, whereas the helix is a space curve, so it exercises the
engines' 3D segment geometry and the dense chain of short skewed segments a
coil discretises into. Electrically it is distributed inductive loading, the
continuous cousin of the lumped-coil loaded verticals.

Like the framework's `vertical` / `inverted_l`, the helix works against a small
set of elevated quarter-wave RADIALS and is modelled in free space (no ground
card); a real ground-mounted install adds soil loss to the (already low) feed
resistance.

Geometry, in the framework's (x, y, z) convention:
  - z : helix axis, fed at the base against the radial counterpoise
  - x/y : the helix winds in the x-y plane at radius `radius_frac`*wl
  - the radials spread in the x-y plane at the base

         __                       turns of the helix wind up the z axis,
        /  \\        each turn discretised into `pts_per_turn` short chords
       |    |
        \\__/
         ||
       \\ || /       elevated radials
        \\||/
         F           base feed
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
            # (~2.7 turns gives a near-resonant ~15 ohm at this height/radius).
            "n_turns": 2.7,
            # Chords per turn used to discretise the circular winding.
            "pts_per_turn": 12,
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
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        radius = self.radius_frac * wavelength
        axial = self.axial_frac * wavelength * self.length_factor
        n_turns = self.n_turns
        ppt = int(self.pts_per_turn)

        z0 = self.base

        tups = []

        # Base feed: a one-segment driven gap at the foot, against the radials.
        tups.append(Wire((0.0, 0.0, z0), (0.0, 0.0, z0 + eps), n_seg=1, ex=1 + 0j))

        # Helix: a space curve from the top of the feed gap upward. Each chord
        # is a straight segment between successive points on the winding; the
        # chords are short, so one MoM segment each is plenty.
        n_pts = int(round(n_turns * ppt))
        zbot = z0 + eps
        prev = (0.0, 0.0, zbot)
        for i in range(1, n_pts + 1):
            t = i / ppt  # turns completed
            ang = 2.0 * math.pi * t
            x = radius * math.cos(ang) - radius  # start at angle 0 -> x=0
            y = radius * math.sin(ang)
            z = zbot + (axial * i / n_pts)
            cur = (x, y, z)
            tups.append(Wire(prev, cur, n_seg=1))
            prev = cur

        # Elevated quarter-wave radials from the feedpoint (cf. vertical.py).
        n_seg_radials = 5
        n_radials = 4
        for j in range(n_radials):
            theta = 2 * math.pi / n_radials * j
            rx = quarter * math.cos(theta)
            ry = quarter * math.sin(theta)
            tups.append(Wire((0.0, 0.0, z0), (rx, ry, z0), n_seg=n_seg_radials))

        return tups
