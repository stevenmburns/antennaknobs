"""2x2 phased stack of Yagi beams."""

from antennaknobs import Array2x2Builder
from antennaknobs.designs.beams import yagi

from types import MappingProxyType


class Builder(Array2x2Builder):
    default_params = MappingProxyType(
        {
            "freq": 28.47,
            "base": 7.0,
            "length_factor_top": 0.9866,
            "length_factor_bot": 0.9866,
            "angle_deg_top": 24.6372,
            "angle_deg_bot": 24.6372,
            "del_y": 4.0,
            "del_z": 2.0,
            "phase_lr": 0.0,
            "phase_tb": 0.0,
            "reflector_factor": 1.05,
            "boom_factor": 0.2,
            "n_directors": 2,
            # 3-column panel: the per-element shape (length_factor /
            # angle_deg) forms a top/bottom matrix in cols 1-2; the
            # shared Yagi element knobs (director count, reflector, boom) sit
            # on their own row, with array spacing and phasing beneath.
            "ui_params": MappingProxyType(
                {
                    "layout": {"columns": 3},
                    "length_factor_top": {"layout": {"row": 1, "col": 1}},
                    "angle_deg_top": {"layout": {"row": 1, "col": 2}},
                    "length_factor_bot": {"layout": {"row": 2, "col": 1}},
                    "angle_deg_bot": {"layout": {"row": 2, "col": 2}},
                    "n_directors": {"layout": {"row": 3, "col": 1}},
                    "reflector_factor": {"layout": {"row": 3, "col": 2}},
                    "boom_factor": {"layout": {"row": 3, "col": 3}},
                    "base": {"layout": {"row": 4, "col": 1}},
                    "del_y": {"layout": {"row": 4, "col": 2}},
                    "del_z": {"layout": {"row": 4, "col": 3}},
                    "phase_lr": {"layout": {"row": 5, "col": 1}},
                    "phase_tb": {"layout": {"row": 5, "col": 2}},
                }
            ),
        }
    )

    def __init__(self, params=None):
        super().__init__(yagi.Builder, params)
