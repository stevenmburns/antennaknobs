"""Slanted hentenna parameterised by top-rectangle perimeter + two
aspect ratios.

Tuning split:

  - `length_factor` — wire length around the TOP closed loop, in
    wavelengths (top wire + right-top vertical + middle wire +
    left-top vertical). The top rectangle's natural λ/2 resonance is
    the dominant mode.

  - `top_aspect` — height-over-width of the top rectangle. Larger =
    taller-and-narrower (higher Z); smaller = squat (lower Z).

  - `bot_aspect` — height-over-width of the bottom rectangle. The
    bottom is a parasitic loop that pulls the impedance and pattern
    around; tunes the match independently of the top.

  - `slant_deg` — corner droop angle (independent of the above).

Underlying geometry derived as:

    width                    = length_factor / (2·(1 + top_aspect))
    (top_height − mid_height) = top_aspect · width
    mid_height               = bot_aspect · width

Equivalently, the bottom rectangle's perimeter ends up being
2·width·(1 + bot_aspect) — fully determined by the three primary
knobs, no separate slider needed.

Wire layout (unchanged from the legacy implementation):

 C-------------AA-------------A
 |                            |
 |                            |
 D------------T--S------------B
 |                            |
 |                            |
 E-------------FF-------------F
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder, Transform, TransformStack


class Builder(AntennaBuilder):
    # Both variants below derive from the legacy hentenna_slant factors.
    # z50: top=0.4903, mid=0.1042, width=0.1577, slant=30°
    #   → length_factor = 2·(0.1577 + (0.4903 − 0.1042)) = 1.0876
    #     top_aspect    = (0.4903 − 0.1042) / 0.1577 = 2.449
    #     bot_aspect    = 0.1042 / 0.1577 = 0.661
    # z100: top=0.4357, mid=0.0880, width=0.2080, slant=30°
    #   → length_factor = 2·(0.2080 + (0.4357 − 0.0880)) = 1.1114
    #     top_aspect    = (0.4357 − 0.0880) / 0.2080 = 1.672
    #     bot_aspect    = 0.0880 / 0.2080 = 0.423
    z50_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 10.0,
            "length_factor": 1.0876,
            "top_aspect": 2.449,
            "bot_aspect": 0.661,
            "slant_deg": 30.0,
            # Resonance / Z / bottom-aspect are all primary tuning
            # knobs — auto step (~1% of default) is too coarse to
            # find a nice match. 0.001 → ~1000 ticks across the
            # explicit ranges.
            "ui_params": MappingProxyType(
                {
                    "top_aspect": {
                        "min": 0.5,
                        "max": 4.5,
                        "step": 0.001,
                        "precision": 4,
                    },
                    "bot_aspect": {
                        "min": 0.0,
                        "max": 2.0,
                        "step": 0.001,
                        "precision": 4,
                    },
                    "slant_deg": {
                        "min": 0.0,
                        "max": 45.0,
                        "step": 1.0,
                        "precision": 0,
                    },
                }
            ),
        }
    )

    # z100 (100 Ω feed) overlays default_params (= z50, the 50 Ω tuning);
    # it states only the shape factors that differ (slant_deg matches default).
    z100_params = MappingProxyType(
        {
            "length_factor": 1.1114,
            "top_aspect": 1.672,
            "bot_aspect": 0.423,
        }
    )

    default_params = z50_params

    def _shape_factors(self):
        """Recover the legacy (top_height_factor, mid_height_factor,
        width_factor) triple from the new parameterization. Inverse
        of the perimeter / aspect formulas in the module docstring.
        """
        width = self.length_factor / (2.0 * (1.0 + self.top_aspect))
        mid_height = self.bot_aspect * width
        top_height = (self.top_aspect + self.bot_aspect) * width
        return top_height, mid_height, width

    def build_wires(self):
        eps = 0.05
        b = self.base

        wavelength = 299.792458 / self.design_freq

        slant_radians = math.radians(self.slant_deg)
        slant_cos = math.cos(slant_radians)
        slant_sin = math.sin(slant_radians)

        top_height_factor, mid_height_factor, width_factor = self._shape_factors()

        def ry(p):
            return p[0], -p[1], p[2]

        n_seg0 = self.nominal_nsegs
        n_seg1 = max(3, self.nominal_nsegs // 7)

        S = (0, eps, wavelength * (mid_height_factor - top_height_factor))
        B = (
            0,
            wavelength * width_factor / 2 * slant_cos,
            wavelength * (mid_height_factor - top_height_factor)
            - wavelength * width_factor / 2 * slant_sin,
        )
        A = (
            0,
            wavelength * width_factor / 2 * slant_cos,
            -wavelength * width_factor / 2 * slant_sin,
        )
        AA = (0, 0, 0)

        F = (
            0,
            wavelength * width_factor / 2 * slant_cos,
            wavelength * (-top_height_factor)
            - wavelength * width_factor / 2 * slant_sin,
        )
        FF = (0, 0, wavelength * (-top_height_factor))

        C, D, T = ry(A), ry(B), ry(S)
        E = ry(F)

        st = TransformStack()
        st.push(Transform.translate(0, 0, b))

        def build_path(lst, ns, ex):
            return ((st.hit(a), st.hit(b), ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        tups = []

        tups.extend(build_path([B, A, AA, C, D], n_seg0, None))
        tups.extend(build_path([B, F, FF, E, D], n_seg0, None))
        tups.extend(build_path([S, B], n_seg0, None))
        tups.extend(build_path([D, T], n_seg0, None))
        tups.extend(build_path([T, S], n_seg1, 1 + 0j))

        return tups
