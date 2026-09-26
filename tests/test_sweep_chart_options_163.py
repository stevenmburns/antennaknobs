"""SimNEC-style chart options for `sweep` (AC6LA, QRZ 1003328 #163).

Dan's convergence charts put R (red, left axis) and X (blue, right axis) on
independent ranges against a log segment-count axis, with a value box at the
first and last points, one panel per engine. These tests pin the options that
reproduce them — `--log`, `--r-range` / `--x-range`, `--callouts`, `--panels`,
`--set`, and the convergence chart's twin axes — against a stub engine, so
each runs in well under a second and no solver is involved.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

import antennaknobs as ant
from antennaknobs.sweep import gen_xs

sw = sys.modules["antennaknobs.sweep"]


class _Builder:
    """Just enough builder for `sweep()`: two knobs, one int, one float."""

    def __init__(self):
        self.segs = 10
        self.length = 5.0
        self.nominal_nsegs = 21

    def build_network(self):
        return None


def _stub_engine(offset=0.0):
    class _Engine:
        def __init__(self, builder):
            self.b = builder

        def impedance(self):
            n = float(getattr(self.b, "segs", 10))
            x = float(self.b.nominal_nsegs) if hasattr(self.b, "nominal_nsegs") else n
            return np.array([complex(72.0 + offset - 1.0 / n - 1.0 / x, -8.0 / x)])

    return _Engine


@pytest.fixture
def capture(monkeypatch):
    """The figure each sweep draws, instead of saving it."""
    import matplotlib.pyplot as plt

    got = {}

    def fake_save_or_show(_plt, _fn):
        got["fig"] = plt.gcf()

    monkeypatch.setattr(sw, "save_or_show", fake_save_or_show)
    yield got
    plt.close("all")


# --- gen_xs ------------------------------------------------------------------


def test_linear_spacing_is_unchanged():
    xs = gen_xs(10, (10, 500), None, None, 20)
    assert np.allclose(np.diff(xs), (500 - 10) / 19)


def test_log_spacing_is_geometric_for_a_float_knob():
    xs = gen_xs(10.0, (10, 500), None, None, 20, log=True)
    assert len(xs) == 20
    assert xs[0] == pytest.approx(10) and xs[-1] == pytest.approx(500)
    ratios = xs[1:] / xs[:-1]
    assert np.allclose(ratios, ratios[0])


def test_log_spacing_rounds_an_int_knob_and_drops_duplicates():
    xs = gen_xs(10, (1, 30), None, None, 20, log=True)
    assert all(isinstance(x, (int, np.integer)) for x in xs)
    assert list(xs) == sorted(set(xs))
    # 20 geometric points over 1..30 collide at the coarse end once rounded.
    assert len(xs) < 20
    assert xs[0] == 1 and xs[-1] == 30


def test_log_spacing_refuses_a_range_through_zero():
    with pytest.raises(ValueError, match="above zero"):
        gen_xs(1.0, (0, 10), None, None, 5, log=True)


# --- the general --param chart ----------------------------------------------


def test_single_engine_default_chart_has_no_new_decoration(capture):
    sw.sweep(_Builder(), "length", rng=(4, 6), npoints=5, engine=_stub_engine())
    ax_r, ax_x = capture["fig"].axes
    assert ax_r.get_xscale() == "linear"
    assert not ax_r.texts and not ax_x.texts


def test_single_engine_log_ranges_and_callouts(capture):
    sw.sweep(
        _Builder(),
        "segs",
        rng=(10, 500),
        npoints=20,
        engine=_stub_engine(),
        log=True,
        r_range=(71.0, 72.5),
        x_range=(-1.0, 1.0),
        callouts=True,
    )
    ax_r, ax_x = capture["fig"].axes
    assert ax_r.get_xscale() == "log"
    assert ax_r.get_ylim() == (71.0, 72.5)
    assert ax_x.get_ylim() == (-1.0, 1.0)
    # A value box on R and on X at each end.
    assert len(ax_r.texts) == 2 and len(ax_x.texts) == 2
    first, last = (t.get_text() for t in ax_r.texts)
    assert first.startswith("segs=10\nR ") and last.startswith("segs=500\nR ")
    # int knob: the plotted points are integers.
    xs = ax_r.get_lines()[0].get_xdata()
    assert all(float(x).is_integer() for x in xs)


def test_markers_get_callouts_in_markers_mode(capture):
    sw.sweep(
        _Builder(),
        "length",
        rng=(4, 6),
        npoints=3,
        markers=[4.5],
        engine=_stub_engine(),
        callouts="markers",
    )
    ax_r, ax_x = capture["fig"].axes
    labels = [t.get_text().split("\n")[0] for t in ax_r.texts]
    assert labels == ["length=4", "length=6", "length=4.5"]


def test_multi_engine_panels_are_twin_axis_one_per_engine(capture):
    engines = {"a": _stub_engine(), "b": _stub_engine(offset=1.0)}
    sw.sweep(
        _Builder(),
        "segs",
        rng=(10, 500),
        npoints=6,
        engine=engines,
        log=True,
        panels=True,
        callouts=True,
    )
    axes = capture["fig"].axes
    # Two panels, each with its twin: R axes first, then their X twins.
    assert len(axes) == 4
    for ax_r in axes[:2]:
        assert ax_r.get_xscale() == "log"
        assert ax_r.get_ylabel() == "R (Ω)"
        assert len(ax_r.texts) == 2
    for ax_x in axes[2:]:
        assert ax_x.get_ylabel() == "X (Ω)"
    assert [ax.get_title().split(":")[0] for ax in axes[:2]] == ["a", "b"]
    # Each panel auto-ranges on its own: engine b's R sits 1 Ω higher.
    assert axes[1].get_ylim()[0] > axes[0].get_ylim()[0]


def test_multi_engine_default_chart_is_unchanged(capture):
    engines = {"a": _stub_engine(), "b": _stub_engine(offset=1.0)}
    sw.sweep(_Builder(), "length", rng=(4, 6), npoints=3, engine=engines)
    (ax,) = capture["fig"].axes
    assert ax.get_ylabel() == "R solid / X dashed (Ω)"


# --- the convergence chart --------------------------------------------------


def test_convergence_chart_is_twin_axis_per_engine(capture, monkeypatch, capsys):
    monkeypatch.setattr(sw, "_achieved_n", lambda eng, b: 2 * b.nominal_nsegs + 1)
    engines = {"a": _stub_engine(), "b": _stub_engine(offset=1.0)}
    sw.sweep(
        _Builder(),
        "nominal_nsegs",
        rng=(10, 500),
        npoints=5,
        engine=engines,
        callouts=True,
        x_range=(-2.0, 0.5),
    )
    capsys.readouterr()
    axes = capture["fig"].axes
    assert len(axes) == 4
    for ax_r, ax_x in zip(axes[:2], axes[2:], strict=True):
        assert ax_r.get_xscale() == "log"
        assert ax_r.get_ylabel() == "R (Ω)" and ax_x.get_ylabel() == "X (Ω)"
        assert ax_x.get_ylim() == (-2.0, 0.5)
        texts = [t.get_text().split("\n")[0] for t in ax_r.texts]
        assert texts == ["N=21", "N=1001"]


def test_bare_callouts_label_only_the_ends_and_all_labels_every_point(capture):
    kw = dict(rng=(4, 6), npoints=5, markers=[4.5], engine=_stub_engine())
    sw.sweep(_Builder(), "length", callouts=True, **kw)
    assert len(capture["fig"].axes[0].texts) == 2
    sw.sweep(_Builder(), "length", callouts="all", **kw)
    # every sweep point, plus the marker
    assert len(capture["fig"].axes[0].texts) == 6


@pytest.mark.parametrize("mode", [True, "markers"])
def test_markers_that_are_the_ladder_get_only_end_callouts(
    capture, monkeypatch, capsys, mode
):
    """Steve's geometric ladders are `--markers` given alone: then they ARE
    the rungs, and a 20-rung study must not get 20 value boxes."""
    monkeypatch.setattr(sw, "_achieved_n", lambda eng, b: 2 * b.nominal_nsegs + 1)
    ladder = [int(round(x)) for x in np.geomspace(10, 500, 20)]
    engines = {"a": _stub_engine(), "b": _stub_engine(offset=1.0)}
    # npoints=None: as the CLI passes it when --npoints is not given.
    sw.sweep(
        _Builder(),
        "nominal_nsegs",
        npoints=None,
        markers=ladder,
        engine=engines,
        callouts=mode,
    )
    capsys.readouterr()
    axes = capture["fig"].axes
    assert len(axes) == 4
    for ax in axes:
        assert len(ax.texts) == 2
    assert [t.get_text().split("\n")[0] for t in axes[0].texts] == ["N=21", "N=1001"]


@pytest.mark.parametrize(
    "flags,expected",
    [("", None), ("--callouts", "ends"), ("--callouts all", "all")],
)
def test_cli_callouts_flag_values(monkeypatch, flags, expected):
    cli_mod = sys.modules["antennaknobs.cli"]
    seen = {}
    monkeypatch.setattr(cli_mod, "sweep", lambda *a, **kw: seen.update(kw))
    ant.cli(
        f"sweep --builder dipoles.invvee:dipole --param length_factor {flags}".split()
    )
    assert seen["callouts"] == expected


def test_cli_callouts_refuses_an_unknown_mode():
    with pytest.raises(SystemExit):
        ant.cli("sweep --param length_factor --callouts some".split())


# --- CLI: refusals ---------------------------------------------------------


@pytest.mark.parametrize(
    "extra,match",
    [
        ("--callouts --use_smithchart", "--use_smithchart"),
        ("--r-range 1 2 --swr", "--swr"),
        ("--log --gain", "--gain"),
        ("--engine momwire,momwire:razor-2p --callouts", "--panels"),
    ],
)
def test_chart_flags_refuse_where_they_draw_nothing(extra, match):
    with pytest.raises(SystemExit, match=match):
        ant.cli(
            f"sweep --builder dipoles.invvee:dipole --param length_factor "
            f"{extra} --fn /dev/null".split()
        )
