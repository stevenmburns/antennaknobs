"""Side-by-side delta-loop pair (1x2)."""

from ...builder import Array1x2Builder
from ..loops import delta_loop

from types import MappingProxyType


class Builder(Array1x2Builder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "length_factor_top": 1.0664,
            "angle_deg_top": 61.2377,
            "base": 7.0,
            "del_y": 4.0,
            "phase_lr": 0.0,
        }
    )

    # Alternate element spacings (the loop tuning was re-optimised per del_y).
    # These were formerly suffixed `_dz2`; the del_z=2 they carried was an inert
    # rigid lift on this single-row 1x2 array (see Array1x2Builder) and has been
    # removed, so the variants are named by their distinguishing del_y.
    # Element-spacing variants overlay default_params; each states only its
    # top-leg tuning and del_y (design_freq / freq / base / phase_lr default).
    dy35_params = MappingProxyType(
        {"length_factor_top": 1.0843, "angle_deg_top": 65.0422, "del_y": 3.5}
    )
    dy45_params = MappingProxyType(
        {"length_factor_top": 1.0801, "angle_deg_top": 63.2603, "del_y": 4.5}
    )
    dy3_params = MappingProxyType(
        {"length_factor_top": 1.0801, "angle_deg_top": 63.2603, "del_y": 3}
    )

    def __init__(self, params=None):
        super().__init__(delta_loop.Builder, params)
