"""Side-by-side hentenna pair (1x2)."""

from ...builder import Array1x2Builder
from ..specialty import hentenna

from types import MappingProxyType


class Builder(Array1x2Builder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "top_height_factor_top": 0.4551,
            "mid_height_factor_top": 0.0943,
            "width_factor_top": 0.1880,
            "base": 10.0,
            "del_y": 4.0,
            "phase_lr": 0.0,
        }
    )

    def __init__(self, params=None):
        super().__init__(hentenna.Builder, params)
