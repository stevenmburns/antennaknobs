"""Four delta loops in a broadside row (1x4)."""

from antennaknobs.builder import Array1x4Builder
from antennaknobs.designs.loops import delta_loop

from types import MappingProxyType


class Builder(Array1x4Builder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "length_factor_itop": 1.0912,
            "angle_deg_itop": 52.1965,
            "length_factor_otop": 1.0795,
            "angle_deg_otop": 51.0563,
            "base": 7.0,
            "del_y": 4.0,
            "del_z": 0.0,
            "phase_lr": 0.0,
            # Per-element shape (length_factor / angle_deg) as an
            # inner/outer matrix in cols 1-2; array spacing on row 3, feed
            # phasing on row 4.
            "ui_params": MappingProxyType(
                {
                    "layout": {"columns": 3},
                    "length_factor_itop": {"layout": {"row": 1, "col": 1}},
                    "angle_deg_itop": {"layout": {"row": 1, "col": 2}},
                    "length_factor_otop": {"layout": {"row": 2, "col": 1}},
                    "angle_deg_otop": {"layout": {"row": 2, "col": 2}},
                    "base": {"layout": {"row": 3, "col": 1}},
                    "del_y": {"layout": {"row": 3, "col": 2}},
                    "del_z": {"layout": {"row": 3, "col": 3}},
                    "phase_lr": {"layout": {"row": 4, "col": 1}},
                }
            ),
        }
    )

    def __init__(self, params=None):
        super().__init__(delta_loop.Builder, params)
