"""Side-by-side hourglass pair (1x2)."""

from ...builder import Array1x2Builder
from ..specialty import hourglass

from types import MappingProxyType


class Builder(Array1x2Builder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "height_factor_top": 0.7777,
            "width_factor_top": 0.7653,
            "waist_factor_top": 0.6071,
            "base": 10.0,
            "del_y": 4.0,
            "phase_lr": 0.0,
        }
    )

    def __init__(self, params=None):
        super().__init__(hourglass.Builder, params)
