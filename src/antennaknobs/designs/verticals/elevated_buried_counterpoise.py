"""Elevated-feed vertical over a buried radial screen — the antenna whose
counterpoise is capacitive, not galvanic (momwire#553, the buried serve).

The radiator's foot stands clear of the ground, so no conductor touches or
crosses the interface; the buried screen underneath is DETACHED, and works
by improving the ground the radiator sees rather than by carrying conducted
return current. That combination — every wire wholly on one side of the
interface — is momwire's buried serve proper, and it is exactly the deck
momwire#553 gated its integration unit on (an elevated monopole over a
detached buried radial, no ground contact anywhere).

    z = base+height  T        radiator, ~lambda/4
                     |
    z = base         F        elevated feed, `base` clear of the surface
    z = 0       ===========   air/soil interface — NOTHING touches it
    z = -depth      -H-       buried hub; `n_radials` radials fan out
                   /   \\      horizontally at `depth`, free at their tips

Contrast `buried_radial_vertical`, which BONDS the radials to the radiator
at z = 0 and therefore needs the much narrower crossing serve. Nothing here
crosses, so the scope is wide: the radials may be tilted, may be any count,
and the deck carries no crossing junction at all. What it costs is the
conducted return path — the screen couples through the soil, so the
driving-point impedance is a good deal more sensitive to `base` and to the
soil constants than a bonded screen would be.

GEOMETRY CONVENTIONS. The radiator lives entirely at z >= `base` > 0 and
the screen entirely at z = -`depth` < 0; the only thing the serve insists
on is that neither reaches the plane. The radials share a buried hub at
(0, 0, -depth), which is an ordinary wholly-below junction, and their tips
are free.

FEED. The house eps-gap idiom at the radiator's foot, as `raised_vertical`
and `vertical` spell it. There is no crossing junction to protect here, so
nothing about the feed is unusual.

REQUIRES A FINITE GROUND, and momwire. The buried screen only exists under
a Sommerfeld half-space, which antennaknobs chooses at SOLVE time, not in
the design: pass ``--ground finite:13,0.005`` (or another eps_r/sigma
pair). Under ``free`` the screen is a floating wire in the air; under
``pec`` it is shorted to a perfect plane above it. The NEC-5 and PyNEC
engine wrappers both refuse a wire below z = 0 outright, so this is a
momwire-only design, and the mixed-medium fill makes it a slow one.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 7.1,
            "design_freq": 7.1,
            # Radiator height as a fraction of the design quarter-wave.
            "length_factor": 1.0,
            # Feed height above the surface. Small enough to be a real
            # installation (the radiator's foot on an insulator on a post),
            # large enough that no basis function reaches the plane.
            "base": 0.5,
            # Buried screen, as in `buried_radial_vertical`.
            "n_radials": 4,
            "radial_factor": 1.0,
            "depth": 0.15,
            "ui_params": MappingProxyType(
                {
                    # Radial 0 runs along +x, so x-z shows one radial at full
                    # length under the radiator with both clearances visible.
                    "default_view": "xz",
                    # Unlike the bonded design there is no degree-2 node to
                    # avoid, so a single radial is a legal (and instructive)
                    # screen — it is momwire#553's own serve-gate deck.
                    "n_radials": {"min": 1, "max": 4, "step": 1},
                    "base": {"min": 0.2, "max": 3.0, "unit": "m"},
                    "depth": {"min": 0.05, "max": 0.5, "unit": "m"},
                    "length_factor": {"min": 0.8, "max": 1.2},
                    "radial_factor": {"min": 0.3, "max": 1.5},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05

        height = 0.25 * self.design_wavelength * self.length_factor
        radial = height * self.radial_factor
        base = self.base
        depth = self.depth
        n_radials = max(1, round(self.n_radials))

        hub = (0.0, 0.0, -depth)

        tups = []
        # Driven gap at the radiator foot; the radiator stacks on top of it.
        tups.append(Wire((0.0, 0.0, base), (0.0, 0.0, base + eps), ex=1 + 0j))
        tups.append(Wire((0.0, 0.0, base + eps), (0.0, 0.0, base + height)))

        for i in range(n_radials):
            theta = 2 * math.pi / n_radials * i
            c, s = math.cos(theta), math.sin(theta)
            # Exact zeros on axis, so every radial lands on the SAME hub node.
            x = radial * (0.0 if abs(c) < 1e-15 else c)
            y = radial * (0.0 if abs(s) < 1e-15 else s)

            tups.append(Wire((x, y, -depth), hub))

        return tups
