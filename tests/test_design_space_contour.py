"""Unit tests for the two-knob design-space contour map.

Exercises the plumbing of ``scripts/design_space_contour.py`` — the SWR/dB
conversions the contour labels rest on, the ground-spec parser, the sweep-range
defaulting, the network-only fast-path detector, and the conditioning report —
plus one small end-to-end sweep on each path (network-only and full-solve) to
pin that they agree with a direct engine solve.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

# The script lives in scripts/, not on the package path — load it by file.
_PATH = Path(__file__).resolve().parent.parent / "scripts" / "design_space_contour.py"
_spec = importlib.util.spec_from_file_location("design_space_contour", _PATH)
dsc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dsc)


@pytest.mark.parametrize("swr", [1.01, 1.5, 2.0, 3.0, 10.0])
def test_swr_db_roundtrip(swr):
    assert dsc.db_to_swr(dsc.swr_to_db(swr)) == pytest.approx(swr, rel=1e-9)


def test_swr_levels_are_monotone_in_db():
    """The contour labels are only correct if the dB levels sort the same way
    the SWR values do — a mislabelled contour is worse than no label."""
    dbs = [dsc.swr_to_db(s) for s in dsc.SWR_LEVELS]
    assert dbs == sorted(dbs, reverse=True)  # SWR_LEVELS runs high -> low
    assert all(d < 0 for d in dbs)
    assert dsc.swr_to_db(2.0) == pytest.approx(-9.542, abs=1e-3)


def test_parse_ground():
    assert dsc.parse_ground("free") is None
    assert dsc.parse_ground("pec") == "pec"
    assert dsc.parse_ground("finite:13:0.005") == ("finite", 13.0, 0.005)
    assert dsc.parse_ground("finite-fast:5:0.001") == ("finite-fast", 5.0, 0.001)


@pytest.mark.parametrize("spec", ["dirt", "finite", "finite:13", "finite:a:b"])
def test_parse_ground_rejects_junk(spec):
    with pytest.raises(SystemExit):
        dsc.parse_ground(spec)


def test_axis_range_prefers_the_designs_own_ui_slider():
    """A design's ui_params min/max is its author's statement of which values
    are meaningful; the ±25% fallback is a guess. Prefer the statement."""
    from antennaknobs.designs.dipoles.invvee import Builder

    b = Builder()
    assert dsc.axis_range(b, "angle_deg", None) == (0.0, 60.0)
    assert dsc.axis_range(b, "length_factor", None) == (0.8, 1.25)
    # An explicit --range always wins.
    assert dsc.axis_range(b, "angle_deg", [10, 20]) == (10.0, 20.0)


def test_axis_range_falls_back_to_a_window_around_the_default():
    """base carries no min/max in ui_params... unless the design added one."""
    from antennaknobs.designs.verticals.vertical import Builder

    b = Builder()
    lo, hi = dsc.axis_range(b, "freq", None)
    assert lo < float(b.freq) < hi


def test_network_only_detects_network_knobs():
    """The stub-matched vertical's two knobs are pure circuit values: no wire
    moves, so the geometry solve can be hoisted out of the grid loop."""
    from antennaknobs.cli import get_builder

    factory = get_builder("verticals.stub_matched_vertical")
    xs, ys = np.linspace(0.05, 0.45, 3), np.linspace(0.05, 0.45, 3)
    assert dsc.network_only(factory, ["line_wl", "stub_wl"], xs, ys)


def test_network_only_rejects_geometry_knobs():
    """Both invvee knobs move wires. Misreading them as network-only would
    hoist the geometry solve and map a single fixed antenna instead."""
    from antennaknobs.cli import get_builder

    factory = get_builder("dipoles.invvee")
    xs, ys = np.linspace(0.9, 1.1, 3), np.linspace(10.0, 50.0, 3)
    assert not dsc.network_only(factory, ["length_factor", "angle_deg"], xs, ys)


def test_network_only_rejects_a_mixed_pair():
    """One network knob and one geometry knob is still a geometry sweep. The
    four-corner comparison is what catches this."""
    from antennaknobs.cli import get_builder

    factory = get_builder("verticals.stub_matched_vertical")
    xs, ys = np.linspace(0.05, 0.45, 3), np.linspace(9.0, 11.0, 3)
    assert not dsc.network_only(factory, ["line_wl", "base"], xs, ys)


def test_fast_path_matches_a_direct_solve():
    """The hoisted-geometry path must reproduce what the ordinary engine
    returns — it is an optimization, not a different model."""
    from antennaknobs.cli import get_builder
    from antennaknobs.engines.momwire import MomwireEngine

    factory = get_builder("verticals.stub_matched_vertical")
    names = ["line_wl", "stub_wl"]
    xs, ys = np.linspace(0.10, 0.40, 3), np.linspace(0.10, 0.40, 3)
    Z = dsc.sweep(factory, names, xs, ys, None, verbose=False)

    for j, x in enumerate(xs):
        for i, y in enumerate(ys):
            b = factory()
            b.line_wl, b.stub_wl = float(x), float(y)
            assert Z[i, j] == pytest.approx(
                MomwireEngine(b).impedance()[0], rel=1e-9, abs=1e-9
            )


def test_fast_path_finds_the_documented_match():
    """The design docstring names (0.406, 0.1408) as a solved 50 Ω match; a
    grid straddling it must show it as such."""
    from antennaknobs.cli import get_builder

    factory = get_builder("verticals.stub_matched_vertical")
    xs, ys = np.array([0.400, 0.406, 0.412]), np.array([0.135, 0.1408, 0.146])
    Z = dsc.sweep(factory, ["line_wl", "stub_wl"], xs, ys, None, verbose=False)
    assert Z[1, 1].real == pytest.approx(50.0, abs=1.0)
    assert Z[1, 1].imag == pytest.approx(0.0, abs=2.0)


def test_full_solve_path_tracks_geometry():
    """A geometry sweep must actually vary with geometry — the regression this
    guards is the fast path firing when it should not, which would return the
    same impedance at every point."""
    from antennaknobs.cli import get_builder

    factory = get_builder("dipoles.invvee")
    xs, ys = np.array([0.90, 1.05]), np.array([10.0, 45.0])
    Z = dsc.sweep(factory, ["length_factor", "angle_deg"], xs, ys, None, verbose=False)
    assert len(set(np.round(Z.ravel(), 6))) == 4
    # Longer wire -> more inductive at fixed droop.
    assert Z[0, 1].imag > Z[0, 0].imag


def test_conditioning_flags_the_loose_axis():
    """A synthetic valley that is narrow in x and spans the whole y range: the
    report exists to say 'your optimizer's y is not determined'."""
    xs = np.linspace(0.0, 1.0, 51)
    ys = np.linspace(0.0, 1.0, 51)
    # |Γ| depends on x only, so every y is equally good. The x curvature has to
    # be steep enough that the SWR<2 band is genuinely narrow — a shallow bowl
    # is legitimately "loose in both", which is not what this test is about.
    gdb = -40 + 4000 * (xs[None, :] - 0.5) ** 2 + 0 * ys[:, None]
    cond = dsc.conditioning(xs, ys, gdb)
    x_span, x_frac = cond["x"]
    y_span, y_frac = cond["y"]
    assert x_frac < 0.5  # pinned
    assert y_frac == pytest.approx(1.0)  # entirely undetermined
    assert math.isclose(y_span, 1.0, abs_tol=1e-9)


def test_conditioning_on_a_round_basin_pins_both():
    xs = ys = np.linspace(-1.0, 1.0, 41)
    gdb = -40 + 600 * (xs[None, :] ** 2 + ys[:, None] ** 2)
    cond = dsc.conditioning(xs, ys, gdb)
    assert cond["x"][1] < 0.5
    assert cond["y"][1] < 0.5
    assert cond["x"][0] == pytest.approx(cond["y"][0], rel=0.15)
