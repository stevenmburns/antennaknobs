"""Side-by-side bowtie pair (1x2)."""

from ...builder import Array1x2Builder
from ..specialty import bowtie

from types import MappingProxyType


class Builder(Array1x2Builder):
    default_params = MappingProxyType(
        {
            "freq": 28.47,
            "angle_deg_top": 30.1137,
            "base": 7.0,
            "length_top": 5.53,
            "del_y": 4.0,
            "phase_lr": 0.0,
        }
    )

    def __init__(self, params=None):
        super().__init__(bowtie.Builder, params)
