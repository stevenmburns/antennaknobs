"""2x2 phased stack of bowtie dipoles."""

from antennaknobs import Array2x2Builder
from antennaknobs.designs.specialty import bowtie

from types import MappingProxyType


class Builder(Array2x2Builder):
    default_params = MappingProxyType(
        {
            "freq": 28.47,
            "angle_deg_top": 33.3449,
            "angle_deg_bot": 27.1124,
            "base": 7.0,
            "length_top": 5.79,
            "length_bot": 5.70,
            "del_y": 4.0,
            "del_z": 2.0,
            "phase_lr": 0.0,
            "phase_tb": 0.0,
            # droop-angle / length as a top/bottom matrix in cols 1-2 (the 2x2
            # sibling, bowtiearray2x4, adds inner/outer columns); array
            # spacing on row 3, feed phasing on row 4.
            "ui_params": MappingProxyType(
                {
                    "layout": {"columns": 3},
                    "angle_deg_top": {"layout": {"row": 1, "col": 1}},
                    "length_top": {"layout": {"row": 1, "col": 2}},
                    "angle_deg_bot": {"layout": {"row": 2, "col": 1}},
                    "length_bot": {"layout": {"row": 2, "col": 2}},
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
        super().__init__(bowtie.Builder, params)
