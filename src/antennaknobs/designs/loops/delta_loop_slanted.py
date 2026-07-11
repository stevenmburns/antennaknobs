"""Delta loop tilted out of the vertical plane by a slant_deg knob."""

from ... import AntennaBuilder
import math

from ... import Transform, TransformStack

from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": 1.0893,
            "angle_deg": 63.5181,
            "slant_deg": 15.0,
            # Cover the full variant family (slant0 through slant30 with
            # headroom): the auto ±50% window around the 15° default
            # (7.5–22.5°) strands both non-default variants.
            "ui_params": MappingProxyType({"slant_deg": {"min": 0.0, "max": 45.0}}),
        }
    )

    # Slant variants overlay default_params (only the tuning that differs);
    # default is the 15° slant.
    slant30_params = MappingProxyType(
        {"length_factor": 1.0850, "angle_deg": 66.4918, "slant_deg": 30}
    )
    slant0_params = MappingProxyType(
        {"length_factor": 1.0839, "angle_deg": 61.4669, "slant_deg": 0}
    )

    def build_wires(self):
        eps = 0.05
        b = self.base

        wavelength = 299.792458 / self.design_freq

        driver = wavelength * self.length_factor

        angle = math.radians(self.angle_deg)
        cos_theta = math.cos(angle)
        tan_theta = math.tan(angle)

        def build_path(lst, ns, ex):
            return ((a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        def ry(p):
            return p[0], -p[1], p[2]

        n_seg0 = self.nominal_nsegs
        n_seg1 = max(3, self.nominal_nsegs // 7)

        d = driver
        h = (cos_theta * (d - 2 * eps) + 2 * eps) / (2 * (cos_theta + 1))

        r"""
         B-----------------A
          \         theta /
           \             /
            \           /
             \         /
              \       /
               \     /
                T---S
    """

        S = (0, eps, b - (h - eps) * tan_theta)
        A = (0, h, b)

        B, T = ry(A), ry(S)

        st = TransformStack()
        st.push(Transform.translate(0, 0, b))
        st.push(Transform.rotX(-self.slant_deg))
        st.push(Transform.translate(0, 4, -b))

        SS, AA, BB, TT = st.hit(S), st.hit(A), st.hit(B), st.hit(T)

        SSS, AAA, BBB, TTT = ry(SS), ry(AA), ry(BB), ry(TT)

        tups = []

        tups.extend(build_path([SS, AA, BB, TT], n_seg0, None))
        tups.extend(build_path([TT, SS], n_seg1, 1 + 0j))

        tups.extend(build_path([SSS, AAA, BBB, TTT], n_seg0, None))
        tups.extend(build_path([SSS, TTT], n_seg1, 1 + 0j))

        return tups
