"""AK#1816: the knob corners of `tests/test_buried_knob_corners_1131.py` with
the gap wire at one segment (the old auto count) and three (the fix), each
at nominal 21 (the pinned rung) and refined x2 / x4, momwire bs2.

    python scratch/1816-brv-gap/corners.py
"""

import warnings

from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import as_wire

SOIL_A = ("finite", 13.0, 0.005)
SOIL_B = ("finite", 20.0, 0.03)
SOIL_C = ("finite", 5.0, 0.001)
CORNERS = {
    "default": ({}, SOIL_A),
    "n_radials_min": ({"n_radials": 1}, SOIL_A),
    "depth_max": ({"depth": 0.5}, SOIL_A),
    "length_max": ({"length_factor": 1.2}, SOIL_A),
    "radial_max": ({"radial_factor": 1.5}, SOIL_A),
    "soil_B_dense": ({}, SOIL_B),
    "mild_sparse": (
        {"n_radials": 1, "depth": 0.05, "length_factor": 0.8, "radial_factor": 0.3},
        SOIL_C,
    ),
    "all_knobs_max_soil_B": (
        {"n_radials": 4, "depth": 0.5, "length_factor": 1.2, "radial_factor": 1.5},
        SOIL_B,
    ),
}


def solve(params, ground, gap, factor):
    class Gap(Builder):
        def build_wires(self):
            ws = [as_wire(t) for t in super().build_wires()]
            return [w._replace(n_seg=gap) if w.ex is not None else w for w in ws]

    b = Gap()
    for k, v in params.items():
        setattr(b, k, v)
    b.nominal_nsegs = b.nominal_nsegs * factor
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return complex(MomwireEngine(b, ground=ground, ground_z=0.0).impedance()[0])


for name, (params, ground) in CORNERS.items():
    row = []
    for factor in (1, 2, 4):
        for gap in (1, 3):
            row.append(f"x{factor} g{gap} {solve(params, ground, gap, factor):.4f}")
    print(name, " | ".join(row), flush=True)
