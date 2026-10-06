"""The map's contours, CLI side, and the workbench chart's fixture
(docs/design/sweep-framework-map.md, unit 2 and decision 13).

``Ref.swr`` is drawn on a map as the contour of |Γ| at that SWR, in the CLI
and the workbench together. The chart's fixture
(``scripts/map_chart_fixture.py``) is the CLI's grid of invvee's tuning map
with contourpy's vertices on it; the vitest checks the chart against it, and
this file keeps the fixture honest: its contours are contourpy's on its own
grid (every PR), and its grid is the CLI's (main only: 825 solves).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs.cli import cli, get_builder

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "map_chart_fixture.py"


def _script():
    spec = importlib.util.spec_from_file_location("map_chart_fixture", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def fx() -> dict:
    return json.loads(_script().FIXTURE.read_text())


def _grid(fx):
    return (
        np.array(fx["x"]["values"]),
        np.array(fx["y"]["values"]),
        np.array(fx["re"]) + 1j * np.array(fx["im"]),
    )


# ── the CLI's rule ─────────────────────────────────────────────────────────


def test_an_swr_threshold_is_a_contour_of_gamma():
    assert ar.map_contours(an.Ref(swr=2.0), 50) == [
        ("X", 0.0),
        ("R", 50.0),
        ("SWR", 2.0),
    ]
    assert ar.map_contours(an.Ref(r=(50,), swr=1.5), 50) == [("R", 50.0), ("SWR", 1.5)]
    assert ar.swr_gamma(2.0) == pytest.approx(1 / 3)
    z = np.array([[50 + 0j, 100 + 0j]])
    assert np.allclose(ar.map_contour_field("SWR", z, 50.0), [[0.0, 1 / 3]])


def test_the_cli_draws_the_swr_contour_and_names_one_not_reached(monkeypatch, tmp_path):
    import matplotlib.pyplot as plt
    from matplotlib.axes import Axes

    drawn, legends = [], []
    inner_contour = Axes.contour

    def contour(self, *args, **kwargs):
        drawn.append((args, kwargs))
        return inner_contour(self, *args, **kwargs)

    inner_fig = ar._map_figure

    def figure(*args, **kwargs):
        inner_fig(*args, **kwargs)
        legends.extend(
            t.get_text()
            for ax in plt.gcf().axes
            if ax.get_legend() is not None
            for t in ax.get_legend().get_texts()
        )

    monkeypatch.setattr(Axes, "contour", contour)
    monkeypatch.setattr(ar, "_map_figure", figure)
    lf = an.Sweep("length_factor", values=(0.95, 0.975, 1.0))
    ang = an.Sweep("angle_deg", values=(15.0, 30.0, 45.0))
    maps = [
        an.Analysis(
            "swr map", (lf, ang), views=(an.Map(),), references=an.Ref(swr=2.0)
        ),
        an.Analysis(
            "tight map", (lf, ang), views=(an.Map(),), references=an.Ref(swr=1.0001)
        ),
    ]
    cls = type(get_builder("dipoles.invvee")())
    monkeypatch.setattr(cls, "build_analyses", lambda self: maps)
    runs = []
    inner_run = ar.run

    def run(*args, **kwargs):
        out = inner_run(*args, **kwargs)
        runs.append(out)
        return out

    monkeypatch.setattr(ar, "run", run)
    cli(["analyze", "--builder", "dipoles.invvee", "--analysis", "swr map",
         "--ground", "finite:13,0.005", "--fn", str(tmp_path / "a.png")])  # fmt: skip
    xs, ys, z = runs[-1]["maps"]["momwire"]
    gamma = np.abs((z - 50) / (z + 50))
    swr_drawn = [
        (args, kw) for args, kw in drawn if kw["levels"] == [pytest.approx(1 / 3)]
    ]
    assert len(swr_drawn) == 1
    (cx, cy, field), kw = swr_drawn[0]
    assert np.array_equal(field, gamma) and kw["linestyles"] == [":"]
    assert "SWR = 2 (|Γ| = 0.333)" in legends
    legends.clear()
    cli(["analyze", "--builder", "dipoles.invvee", "--analysis", "tight map",
         "--ground", "finite:13,0.005", "--fn", str(tmp_path / "b.png")])  # fmt: skip
    assert "SWR = 1.0001 (|Γ| = 5e-05) (not reached)" in legends


# ── the fixture ────────────────────────────────────────────────────────────


def test_the_fixtures_contours_are_contourpys_on_its_own_grid(fx):
    xs, ys, z = _grid(fx)
    assert z.shape == (25, 33)
    assert fx["contours"] == _script().contours(xs, ys, z)
    by = {(c["quantity"], c["level"]): c for c in fx["contours"]}
    # The map's own lines, the threshold, and the one level never reached.
    assert set(by) == {
        ("X", 0.0),
        ("R", 50.0),
        ("R", 75.0),
        ("R", 5000.0),
        ("SWR", 2.0),
    }
    assert by[("R", 5000.0)]["reached"] is False and by[("R", 5000.0)]["lines"] == []
    assert all(c["lines"] for k, c in by.items() if k != ("R", 5000.0))


def test_the_fixtures_best_node_is_best_cell_lines(fx):
    xs, ys, z = _grid(fx)
    line = ar.best_cell_line("momwire", xs, ys, z, "length_factor", "angle_deg", 50.0)
    assert line == f"momwire: {fx['best']['line']}"
    assert fx["best"]["line"].startswith(
        "least |Γ| 0.0235 (SWR 1.05) at length_factor 0.975"
    )


@pytest.mark.antenna_computation_check
def test_the_fixtures_grid_is_the_clis(fx):
    xs, ys, z = _script().cli_grid()
    fxs, fys, fz = _grid(fx)
    assert np.array_equal(xs, fxs) and np.array_equal(ys, fys)
    assert np.array_equal(z.real, fz.real) and np.array_equal(z.imag, fz.imag)
