"""Write the workbench map chart's fixture: dipoles.invvee's tuning map as
``antennaknobs analyze`` solves it, with contourpy's contour vertices on it
(docs/design/sweep-framework-map.md, unit 2).

The chart (``lib/mapGrid.ts``) is checked against this file: its marching
squares must put every contour vertex within 1e-9 of the axis span of
contourpy's (matplotlib's contour, which the CLI's map draws with), its
"(not reached)" rule must agree, and its best node must be the CLI's
``best_cell_line``.

The contours are the map's own ``Ref`` lines (X = 0, R = 50, R = 75) plus
an SWR = 2 threshold (``Ref.swr`` is drawn as the |Γ| contour, decision 13),
and one level the grid never reaches. ``tests/test_map_chart_fixture.py``
re-derives the contours from the fixture's own grid on every PR, and (main
only) re-solves the grid against the CLI.

    python scripts/map_chart_fixture.py   # rewrites the fixture in place
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "src/antennaknobs/web/frontend/src/__tests__/fixtures/invveeTuningMap.json"
)
DESIGN = "dipoles.invvee"
ANALYSIS = "tuning map"
GROUND = "finite:13,0.005"
Z0 = 50.0
#: The analysis's own Ref, its SWR threshold set (the design's map has none),
#: and an R the grid never reaches.
REFS = {"r": [50.0, 75.0, 5000.0], "x": [0.0], "swr": 2.0}


def cli_grid():
    """The CLI's grid: ``analyze`` run as a user runs it, its maps read back."""
    from antennaknobs import analysis_run as ar
    from antennaknobs.cli import cli

    runs = []
    inner = ar.run

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        runs.append(out)
        return out

    ar.run = wrapped
    try:
        with tempfile.TemporaryDirectory() as d:
            cli(["analyze", "--builder", DESIGN, "--analysis", ANALYSIS,
                 "--ground", GROUND, "--z0", f"{Z0:g}", "--fn", f"{d}/map.png"])  # fmt: skip
    finally:
        ar.run = inner
    ((_label, grid),) = runs[-1]["maps"].items()
    return grid


def contour_lines(xs, ys, field, level) -> list[list[list[float]]]:
    """contourpy's lines at ``level``, as matplotlib's ``contour`` makes them
    (its default ``mpl2014`` algorithm, corners masked)."""
    import contourpy
    import numpy as np

    gen = contourpy.contour_generator(
        np.asarray(xs, float),
        np.asarray(ys, float),
        np.asarray(field, float),
        name="mpl2014",
        corner_mask=True,
        line_type=contourpy.LineType.SeparateCode,
    )
    points, _codes = gen.lines(level)
    return [[[float(x), float(y)] for x, y in line] for line in points]


def contours(xs, ys, z) -> list[dict]:
    """Every contour the chart draws on this grid, by the CLI's own rule."""
    from antennaknobs import analyses as an
    from antennaknobs import analysis_run as ar

    refs = an.Ref(r=tuple(REFS["r"]), x=tuple(REFS["x"]), swr=REFS["swr"])
    out = []
    for quantity, level in ar.map_contours(refs, Z0):
        field = ar.map_contour_field(quantity, z, Z0)
        at = ar.swr_gamma(level) if quantity == "SWR" else level
        reached = ar.map_contour_reached(field, at)
        out.append(
            {
                "quantity": quantity,
                "level": level,
                "at": at,
                "reached": reached,
                "lines": contour_lines(xs, ys, field, at) if reached else [],
            }
        )
    return out


def build() -> dict:
    import numpy as np

    from antennaknobs import analysis_run as ar

    xs, ys, z = cli_grid()
    gamma = np.abs((z - Z0) / (z + Z0))
    j, i = np.unravel_index(np.nanargmin(gamma), gamma.shape)
    return {
        "design": DESIGN,
        "analysis": ANALYSIS,
        "ground": GROUND,
        "z0": Z0,
        "x": {"param": "length_factor", "values": [float(v) for v in xs]},
        "y": {"param": "angle_deg", "values": [float(v) for v in ys]},
        "re": [[float(v) for v in row] for row in z.real],
        "im": [[float(v) for v in row] for row in z.imag],
        "refs": REFS,
        "contours": contours(xs, ys, z),
        "best": {
            "i": int(i),
            "j": int(j),
            "line": ar.best_cell_line(
                "momwire", xs, ys, z, "length_factor", "angle_deg", Z0
            ).split(": ", 1)[1],
        },
    }


if __name__ == "__main__":
    data = build()
    FIXTURE.write_text(json.dumps(data, indent=None) + "\n")
    print(f"wrote {FIXTURE.relative_to(ROOT)}", file=sys.stderr)
