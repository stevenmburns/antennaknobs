"""2x2 phased stack of Moxon rectangles."""

from antennaknobs import Array2x2Builder
from antennaknobs.designs.beams import moxon

from types import MappingProxyType


class Builder(Array2x2Builder):
    default_params = MappingProxyType(
        {
            "freq": 28.47,
            "base": 7.0,
            "del_y": 4.0,
            "del_z": 2.0,
            "phase_lr": 0.0,
            "phase_tb": 0.0,
            "halfdriver_top": 2.4515,
            "halfdriver_bot": 2.4487,
            "aspect_ratio_top": 0.3646010186757216,
            "aspect_ratio_bot": 0.3646010186757216,
            "tipspacer_factor_top": 0.07729647745945359,
            "tipspacer_factor_bot": 0.07729647745945359,
            "t0_factor_top": 0.4078045966770739,
            "t0_factor_bot": 0.4078045966770739,
            # Auto-view picks yz (y/z dominate from the 2x2 stacking),
            # but moxon-family geometry reads in xy — keep the array
            # consistent with the single moxon's view.
            #
            # Lay the panel out as two element columns: col 1 = the top
            # element, col 2 = the bottom element; each row is one shape
            # family (halfdriver / aspect_ratio / tipspacer / t0). The moxon
            # param names are long, so a 2-wide grid keeps every label
            # readable (a 4-wide family-per-column grid truncates them).
            # Array spacing and feed phasing get their own rows beneath.
            "ui_params": MappingProxyType(
                {
                    "default_view": "xy",
                    "layout": {"columns": 2},
                    "halfdriver_top": {"layout": {"row": 1, "col": 1}},
                    "halfdriver_bot": {"layout": {"row": 1, "col": 2}},
                    "aspect_ratio_top": {"layout": {"row": 2, "col": 1}},
                    "aspect_ratio_bot": {"layout": {"row": 2, "col": 2}},
                    "tipspacer_factor_top": {"layout": {"row": 3, "col": 1}},
                    "tipspacer_factor_bot": {"layout": {"row": 3, "col": 2}},
                    "t0_factor_top": {"layout": {"row": 4, "col": 1}},
                    "t0_factor_bot": {"layout": {"row": 4, "col": 2}},
                    "del_y": {"layout": {"row": 5, "col": 1}},
                    "del_z": {"layout": {"row": 5, "col": 2}},
                    "phase_lr": {"layout": {"row": 6, "col": 1}},
                    "phase_tb": {"layout": {"row": 6, "col": 2}},
                    "base": {"layout": {"row": 7, "col": 1}},
                }
            ),
        }
    )

    def __init__(self, params=None):
        super().__init__(moxon.Builder, params)
