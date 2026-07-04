from ... import AntennaBuilder
import math

from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": 0.9719,
            "angle_deg": 31.6846,
            # length_factor span has to cover both the half-wave default
            # (~0.97) and the EDZ variant (~2.97, encoding a ~1.5λ
            # element). Auto-derive's ±50% window would clip at ~1.46.
            "ui_params": MappingProxyType(
                {
                    "length_factor": {
                        "min": 0.4,
                        "max": 3.2,
                    },
                }
            ),
        }
    )

    # Straight half-wave dipole: same V-dipole geometry as the default
    # invvee but with angle_deg=0, so the arms run flat (no droop).
    # length_factor=0.967 puts a free-space dipole at 28.47 MHz near
    # resonance (Z ≈ 66 + j1 Ω). Equivalent to the old top-level
    # dipole.py geometry, now reachable as the "dipole" variant on
    # dipoles.invvee.
    # Variants overlay default_params; each states only its length_factor /
    # angle_deg tuning (design_freq / freq / base come from default).
    dipole_params = MappingProxyType({"length_factor": 0.967, "angle_deg": 0.0})

    # Three-halves dipole: 1.484λ-long flat dipole, tuned to a near-
    # resonant length where Z_in collapses to ~95 Ω (real). Not the
    # classic Extended Double Zepp — that's the variant below — but
    # the value freq_based.extended_double_zepp.py defaulted to before
    # being folded into this Builder. Useful as a low-Z drop-in for a
    # 50–100 Ω feedline at 28.47 MHz without a tuner.
    #
    # length_factor parameterises driver_y as 0.25·λ·length_factor, so
    # this 0.7422·λ driver_y lands at length_factor = 0.7422 / 0.25 =
    # 2.9688 (giving 2 × 0.7422 = 1.4844λ total length).
    three_halves_params = MappingProxyType({"length_factor": 2.9688, "angle_deg": 0.0})

    # Classic Extended Double Zepp: 1.28λ total length (driver_y =
    # 0.64λ per leg → length_factor = 0.64 / 0.25 = 2.56). Tuned for
    # maximum broadside gain before pattern lobing splits; sits well
    # above ~1λ anti-resonance, so the input impedance is high and
    # very reactive (≈ 100 − j600 Ω at the design freq) and a matching
    # network is required.
    classic_edz_params = MappingProxyType({"length_factor": 2.56, "angle_deg": 0.0})

    def build_wires(self):
        eps = 0.05
        b = self.base

        wavelength = 299.792458 / self.design_freq

        driver_y = 0.25 * wavelength * self.length_factor

        angle = math.radians(self.angle_deg)
        z_sin = math.sin(angle)
        y_cos = math.cos(angle)

        def build_path(lst, ns, ex):
            return ((a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        def ry(p):
            return p[0], -p[1], p[2]

        n_seg0 = self.nominal_nsegs
        n_seg1 = max(3, self.nominal_nsegs // 7)

        """
                    
                A
                |
                |
                |
                |
                |
                |
                |
                S
                |
                T
                |
                |
                |
                |
                |
                |
                |
                D

    """

        S = (0, eps, b)
        A = (0, eps + (driver_y - eps) * y_cos, b - (driver_y - eps) * z_sin)

        D, T = ry(A), ry(S)

        tups = []

        tups.extend(build_path([S, A], n_seg0, None))
        tups.extend(build_path([D, T], n_seg0, None))
        tups.extend(build_path([T, S], n_seg1, 1 + 0j))

        return tups
