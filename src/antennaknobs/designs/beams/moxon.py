"""Moxon rectangle — a 2-element beam with folded-back element tips."""

from antennaknobs import AntennaBuilder
from types import MappingProxyType


class Builder(AntennaBuilder):
    # Variants overlay default_params; each states only the driver geometry
    # that differs (freq, base, aspect_ratio come from default).
    original_params = MappingProxyType(
        {
            "halfdriver": (147.25 / 2 + 22 + 3 / 16) * 0.0254,
            "tipspacer_factor": (4 + 1 / 16) / (53 + 11 / 16),
            "t0_factor": (22 + 3 / 16) / (53 + 11 / 16),
        }
    )

    default_params = MappingProxyType(
        {
            "freq": 28.57,
            # Geometry is hand-tuned in absolute metres; design_freq only
            # anchors auto_mesh's density scale (nominal_nsegs per
            # quarter-wave), so it is hidden from the UI.
            "design_freq": 28.57,
            "base": 7.0,
            "halfdriver": 2.4597430629596713,
            "aspect_ratio": 0.3646010186757216,
            "tipspacer_factor": 0.07729647745945359,
            "t0_factor": 0.4078045966770739,
            "ui_params": MappingProxyType({"design_freq": {"hidden": True}}),
        }
    )

    opt_params = MappingProxyType(
        {
            "halfdriver": 2.4454699666515394,
            "tipspacer_factor": 0.047061074343758946,
            "t0_factor": 0.42268888502818136,
        }
    )

    def build_wires(self):
        eps = 0.05
        base = self.base

        # short = aspect_ratio*long
        # halfdriver = long/2 + short*t0_factor
        # halfdriver = long/2 + aspect_ratio*long*t0_factor
        # 2*halfdriver = long + 2*aspect_ratio*long*t0_factor
        # 2*halfdriver = long*(1 + 2*aspect_ratio*t0_factor)
        # long = 2*halfdriver/(1 + 2*aspect_ratio*t0_factor)

        long = 2 * self.halfdriver / (1 + 2 * self.aspect_ratio * self.t0_factor)
        short = self.aspect_ratio * long

        tipspacer = short * self.tipspacer_factor
        t0 = short * self.t0_factor

        def rx(p):
            return -p[0], p[1], p[2]

        def ry(p):
            return p[0], -p[1], p[2]

        """
    D----------C   B-----A
    |                    |
    |                    |
    |                    |
    |                    |
    |                    |
    |                    |
    |                    S
    |                    |
    |                    T
    |                    |
    |                    |
    |                    |
    |                    |
    |                    |
    |                    |
    E----------F   G-----H
	"""

        S = (short / 2, eps, base)
        A = (S[0], long / 2, base)
        B = (A[0] - t0, A[1], base)
        C = (B[0] - tipspacer, B[1], base)
        D = rx(A)
        E, F, G, H, T = ry(D), ry(C), ry(B), ry(A), ry(S)

        # Uniform-density mesh (issue #522): giving each wire the full
        # nominal count put 6.7x-over-dense segments on the short folded
        # tails — exactly the facing conductors across the critical tip
        # gap — and the sin/PyNEC family walked off the Galerkin value at
        # fine mesh (39.2-21.2j vs 43.6-16.3j at N=321). At uniform
        # design density sin lands on bs2 to 0.1% there.
        def path(lst):
            return [(a, b, None, None) for a, b in zip(lst[:-1], lst[1:])]

        tups = []
        tups.extend(path([S, A, B]))
        tups.extend(path([C, D, E, F]))
        tups.extend(path([G, H, T]))
        tups.append((T, S, None, 1 + 0j))

        return tups
