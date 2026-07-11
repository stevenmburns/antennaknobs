"""2x2 phased stack of folded inverted-vees."""

from ... import Array2x2Builder
from ..dipoles import folded_invvee

from types import MappingProxyType


class Builder(Array2x2Builder):
    default_params = MappingProxyType(
        {
            "freq": 28.47,
            "base": 7.0,
            "length_factor_top": 0.9943,
            "length_factor_bot": 1.0038,
            "angle_deg_top": 41.5681,
            "angle_deg_bot": 41.5165,
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
        super().__init__(folded_invvee.Builder, params)
