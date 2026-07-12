"""Smoke tests for the in-house Smith chart that replaced scikit-rf (#332).

These run headless (conftest forces the Agg backend) and pin two things:
the chart background actually rasterizes, and the CLI smith-sweep path no
longer imports skrf.
"""

import sys

import numpy as np
import matplotlib.pyplot as plt

import antennaknobs as ant
from antennaknobs.smith_chart import (
    MAJOR_GRID,
    MINOR_GRID,
    draw_smith_chart,
    plot_reflection,
)


def test_smith_background_builds_and_rasterizes():
    fig, ax = plt.subplots()
    draw_smith_chart(ax, z0=50)
    # One boundary circle, plus per grid value one resistance circle and a
    # ±reactance arc pair.
    expected_patches = 1 + 3 * (len(MAJOR_GRID) + len(MINOR_GRID))
    assert len(ax.patches) == expected_patches
    fig.canvas.draw()
    plt.close(fig)


def test_plot_reflection_traces_and_markers():
    fig, ax = plt.subplots()
    draw_smith_chart(ax)
    z = np.array([25 + 10j, 50 + 0j, 80 - 30j])
    gamma = (z - 50) / (z + 50)
    assert np.all(np.abs(gamma) < 1)  # passive loads stay inside the rim
    (line,) = plot_reflection(ax, gamma, color="C0")
    (dots,) = plot_reflection(ax, gamma[:1], marker="s", linestyle="None")
    assert line.get_xydata().shape == (3, 2)
    assert dots.get_marker() == "s"
    fig.canvas.draw()
    plt.close(fig)


def test_cli_smith_sweep_runs_without_skrf():
    # The full CLI path: sweep + smith mode on the always-available momwire
    # engine. Must render (to /dev/null) without ever touching skrf.
    ant.cli(
        "sweep --builder dipoles.invvee:dipole --npoints 3 --engine momwire"
        " --ground free --use_smithchart --z0=50 --fn /dev/null".split()
    )
    assert "skrf" not in sys.modules
