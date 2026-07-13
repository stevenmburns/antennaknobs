"""2x2 phased stack of delta loops."""

from antennaknobs.builder import Array2x2Builder
from antennaknobs.designs.loops import delta_loop

from types import MappingProxyType


class Builder(Array2x2Builder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "length_factor_top": 1.1112,
            "angle_deg_top": 52.2022,
            "length_factor_bot": 1.1276,
            "angle_deg_bot": 52.7981,
            "base": 15.0,
            "del_y": 4.0,
            "del_z": 2.0,
            "phase_lr": 0.0,
            "phase_tb": 0.0,
            # Per-element shape (length_factor / angle_deg) as a top/bottom
            # matrix in cols 1-2; array spacing on row 3, feed phasing on row 4.
            "ui_params": MappingProxyType(
                {
                    "layout": {"columns": 3},
                    "length_factor_top": {"layout": {"row": 1, "col": 1}},
                    "angle_deg_top": {"layout": {"row": 1, "col": 2}},
                    "length_factor_bot": {"layout": {"row": 2, "col": 1}},
                    "angle_deg_bot": {"layout": {"row": 2, "col": 2}},
                    "base": {"layout": {"row": 3, "col": 1}},
                    "del_y": {"layout": {"row": 3, "col": 2}},
                    "del_z": {"layout": {"row": 3, "col": 3}},
                    "phase_lr": {"layout": {"row": 4, "col": 1}},
                    "phase_tb": {"layout": {"row": 4, "col": 2}},
                }
            ),
        }
    )

    def __init__(self, params=None):
        super().__init__(delta_loop.Builder, params)
