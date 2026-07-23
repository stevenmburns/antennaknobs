"""Quarter-wave vertical over ground."""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire

import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 28.57,
            # Geometry is hand-tuned in absolute metres; design_freq only
            # anchors auto_mesh's density scale (nominal_nsegs per
            # quarter-wave), so it is hidden from the UI.
            "design_freq": 28.57,
            "length": 2.619,
            "base": 0.5,
            # Auto-view rule picks xy (x/y are the two largest spans
            # since the three radials spread in x/y), but the radiator
            # itself is vertical — yz reads the elevation profile
            # naturally.
            "ui_params": MappingProxyType(
                {
                    "default_view": "yz",
                    "design_freq": {"hidden": True},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05

        z = self.length
        base = self.base

        n_radials = 3
        # Radials refine with the mesh (issue #477): hard-coding the count let
        # coarse radial segments meet fine riser segments at the feed junction
        # on refined meshes, dragging PyNEC/sin off BSpline's converged value.
        # Radials run the full self.length (not a quarter-wave): self.length is
        # already the ~quarter-wave radiator length, so the radials match the
        # radiator and form an equal-length elevated counterpoise.

        tups = []
        # Driven gap at the riser foot; the riser stacks on top of it.
        tups.append(Wire((0, 0, base), (0, 0, base + eps), ex=1 + 0j))
        tups.append(Wire((0, 0, base + eps), (0, 0, base + z)))

        for i in range(n_radials):
            theta = 2 * math.pi / n_radials * i

            x, y = self.length * math.cos(theta), self.length * math.sin(theta)

            tups.append(Wire((0, 0, base), (x, y, base)))

        return tups
