"""Hex beam — a W-folded 2-element beam on a hexagonal spreader footprint."""

from antennaknobs import AntennaBuilder
import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 28.47,
            # Geometry is hand-tuned in absolute metres; design_freq only
            # anchors auto_mesh's density scale (nominal_nsegs per
            # quarter-wave), so it is hidden from the UI.
            "design_freq": 28.47,
            "base": 7.0,
            "halfdriver": 2.82,
            "tipspacer_factor": 0.1312,
            "t0_factor": 0.1243,
            # The opt variant's tip spacer (0.208) sits above the auto ±50%
            # window around the default (≤0.197).
            "ui_params": MappingProxyType(
                {
                    "tipspacer_factor": {"min": 0.065, "max": 0.25},
                    "design_freq": {"hidden": True},
                }
            ),
        }
    )

    # Overlays default_params; base comes from default.
    opt_params = MappingProxyType(
        {
            "freq": 28.57,
            "halfdriver": 2.782539354535098,
            "tipspacer_factor": 0.20803460322922357,
            "t0_factor": 0.07058920808116927,
        }
    )

    def build_wires(self):
        eps = 0.05

        # 2*radius = self.halfdriver + t0_factor*radius + tipspacer_factor*radius
        # 2*radius - t0_factor*radius - tipspacer_factor*radius = self.halfdriver
        radius = self.halfdriver / (2 - self.t0_factor - self.tipspacer_factor)

        tipspacer = radius * self.tipspacer_factor
        t0 = radius * self.t0_factor
        t1 = radius - tipspacer - t0

        sin30 = 1 / 2
        cos30 = math.sqrt(3) / 2
        # x is the beam direction

        def build_path(lst, ns, ex):
            return ((a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        def rx(p):
            return -p[0], p[1], p[2]

        def ry(p):
            return p[0], -p[1], p[2]

        A = (radius * cos30, radius * sin30, 0)
        B = (A[0] - t1 * cos30, A[1] + t1 * sin30, 0)
        D = (0, radius, 0)
        C = (D[0] + t0 * cos30, D[1] - t0 * sin30, 0)
        E = rx(A)
        F = ry(E)
        G = ry(D)
        H = ry(C)
        II = ry(B)
        J = ry(A)

        S = (eps * cos30, eps * sin30, 0)
        T = ry(S)

        # Uniform-density mesh (issue #521 class): every wire — arms, the
        # short tip spacers (whose old hard-coded 5 segments left a graded
        # junction that worsened with N), and the feed gap — meshes at the
        # design density (nominal_nsegs per design_freq quarter-wave).
        tups = []
        tups.extend(build_path([S, A, B], None, None))
        tups.extend(build_path([C, D], None, None))
        tups.extend(build_path([D, E, F, G], None, None))
        tups.extend(build_path([G, H], None, None))
        tups.extend(build_path([II, J, T], None, None))
        tups.append((T, S, None, 1 + 0j))
        tups = self.auto_mesh(tups)

        new_tups = []
        for xoff, yoff, zoff in [(0, 0, self.base)]:
            new_tups.extend(
                [
                    (
                        (x0 + xoff, y0 + yoff, z0 + zoff),
                        (x1 + xoff, y1 + yoff, z1 + zoff),
                        ns,
                        ex,
                    )
                    for ((x0, y0, z0), (x1, y1, z1), ns, ex) in tups
                ]
            )

        return new_tups
