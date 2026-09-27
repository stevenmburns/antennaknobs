"""`sweep --only {r,x}`: one quantity of the R/X chart, on one y axis.

Every rectangular layout — the single-engine chart, `--panels`, `--overlay`,
the shared-axis multi-engine chart and the `nominal_nsegs` study — drops the
twin axis and the other quantity's lines, keeps R red / X blue (or the
engine's colour with R solid / X dashed), and callouts name only the drawn
quantity. The CLI refuses `--only` where there is no R/X chart, and a range
pin on the quantity it hides. Stub engines only; no solver runs.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

import antennaknobs as ant

sw = sys.modules["antennaknobs.sweep"]
cli_mod = sys.modules["antennaknobs.cli"]


class _Builder:
    def __init__(self):
        self.segs = 10
        self.length = 5.0
        self.nominal_nsegs = 21

    def build_network(self):
        return None


def _stub_engine(r_offset=0.0, x_offset=0.0):
    class _Engine:
        def __init__(self, builder):
            self.b = builder

        def impedance(self):
            n = float(self.b.nominal_nsegs) * float(self.b.length)
            return np.array([complex(72.0 + r_offset - 1.0 / n, x_offset - 8.0 / n)])

    return _Engine


ENGINES = {
    "a": _stub_engine(),
    "b": _stub_engine(r_offset=3.0, x_offset=-8.5),
}


@pytest.fixture
def capture(monkeypatch):
    import matplotlib.pyplot as plt

    got = {}
    monkeypatch.setattr(sw, "save_or_show", lambda _p, _f: got.update(fig=plt.gcf()))
    yield got
    plt.close("all")


def _data_lines(ax):
    """Curves, not the 2-point Z* hlines or 1-point marker squares."""
    return [ln for ln in ax.get_lines() if len(ln.get_xdata()) > 2]


def _box_texts(ax):
    return [t.get_text() for t in ax.texts if t.get_text()]


# --- single engine -----------------------------------------------------------


@pytest.mark.parametrize(
    "only,ylabel,color,part",
    [
        ("r", "resistance R (Ω)", "tab:red", np.real),
        ("x", "reactance X (Ω)", "tab:blue", np.imag),
    ],
)
def test_single_engine_draws_one_quantity_on_one_axis(
    capture, only, ylabel, color, part
):
    eng = _stub_engine()
    sw.sweep(_Builder(), "length", rng=(4, 6), npoints=5, engine=eng, only=only)
    (ax,) = capture["fig"].axes  # no twin
    assert ax.get_ylabel() == ylabel
    (line,) = ax.get_lines()
    assert line.get_color() == color
    b = _Builder()
    expected = []
    for x in line.get_xdata():
        b.length = x
        expected.append(part(eng(b).impedance()[0]))
    np.testing.assert_allclose(line.get_ydata(), expected)


def test_single_engine_callouts_name_only_the_drawn_quantity(capture):
    sw.sweep(
        _Builder(),
        "length",
        rng=(4, 6),
        npoints=5,
        engine=_stub_engine(),
        only="x",
        callouts=True,
        x_range=(-1.0, 0.0),
    )
    (ax,) = capture["fig"].axes
    assert ax.get_ylim() == (-1.0, 0.0)
    texts = _box_texts(ax)
    assert len(texts) == 2
    assert all("\nX " in t and "\nR " not in t for t in texts)


def test_single_engine_default_is_still_twin_axis(capture):
    sw.sweep(_Builder(), "length", rng=(4, 6), npoints=5, engine=_stub_engine())
    ax_r, ax_x = capture["fig"].axes
    assert ax_r.get_ylabel() == "resistance R (Ω)"
    assert ax_x.get_ylabel() == "reactance X (Ω)"


# --- panels ------------------------------------------------------------------


def test_panels_only_x_one_axis_per_engine(capture):
    sw.sweep(
        _Builder(),
        "length",
        rng=(2, 50),
        npoints=6,
        engine=ENGINES,
        panels=True,
        callouts=True,
        only="x",
    )
    axes = capture["fig"].axes
    assert len(axes) == 2  # one per engine, no twins
    for ax, name in zip(axes, ("a", "b"), strict=True):
        assert ax.get_ylabel() == "X (Ω)"
        assert ax.get_title().startswith(f"{name}:")
        (line,) = _data_lines(ax)
        assert line.get_label() == "X" and line.get_color() == "tab:blue"
        texts = _box_texts(ax)
        assert len(texts) == 2
        assert all("\nX " in t and "\nR " not in t for t in texts)


def test_panels_only_r(capture):
    sw.sweep(
        _Builder(),
        "length",
        rng=(2, 50),
        npoints=6,
        engine=ENGINES,
        panels=True,
        only="r",
    )
    axes = capture["fig"].axes
    assert [ax.get_ylabel() for ax in axes] == ["R (Ω)", "R (Ω)"]
    assert all([ln.get_label() for ln in _data_lines(ax)] == ["R"] for ax in axes)


def test_convergence_panels_only_x_draw_zstar_on_x(capture, monkeypatch, capsys):
    monkeypatch.setattr(sw, "_achieved_n", lambda eng, b: 2 * b.nominal_nsegs + 1)
    sw.sweep(
        _Builder(),
        "nominal_nsegs",
        rng=(8, 160),
        npoints=5,
        engine=ENGINES,
        only="x",
        callouts=True,
    )
    capsys.readouterr()
    axes = capture["fig"].axes
    assert len(axes) == 2
    for ax in axes:
        assert ax.get_ylabel() == "X (Ω)"
        assert ax.get_xscale() == "log"
        dotted = [ln for ln in ax.get_lines() if ln.get_linestyle() == ":"]
        assert [ln.get_color() for ln in dotted] == ["tab:blue"]
        assert all("\nX " in t for t in _box_texts(ax))


# --- overlay -----------------------------------------------------------------


def test_overlay_only_r_one_axis_all_engines(capture):
    sw.sweep(
        _Builder(),
        "length",
        rng=(2, 50),
        npoints=6,
        engine=ENGINES,
        overlay=True,
        callouts=True,
        only="r",
    )
    (ax,) = capture["fig"].axes
    assert ax.get_ylabel() == "R (Ω)"
    lines = _data_lines(ax)
    assert [ln.get_label() for ln in lines] == ["a R", "b R"]
    assert all(ln.get_linestyle() == "-" for ln in lines)
    assert len({ln.get_color() for ln in lines}) == 2
    legend = [t.get_text() for t in ax.get_legend().get_texts()]
    assert legend == ["a R", "b R"]
    texts = _box_texts(ax)
    assert len(texts) == 4  # one box per engine per end
    assert all("\nR " in t and " X " not in t for t in texts)
    # No dangling arrow-only annotations for the hidden X.
    assert len(ax.texts) == 4


def test_overlay_only_x_keeps_the_dashed_style(capture):
    sw.sweep(
        _Builder(),
        "length",
        rng=(2, 50),
        npoints=6,
        engine=ENGINES,
        overlay=True,
        callouts="all",
        only="x",
        x_range=(-10.0, 1.0),
    )
    (ax,) = capture["fig"].axes
    assert ax.get_ylabel() == "X (Ω)"
    assert ax.get_ylim() == (-10.0, 1.0)
    lines = _data_lines(ax)
    assert [ln.get_label() for ln in lines] == ["a X", "b X"]
    assert all(ln.get_linestyle() == "--" for ln in lines)
    texts = _box_texts(ax)
    # 2 engines x (2 end boxes + 4 inner points)
    assert len(texts) == 12
    assert all("X " in t and "R " not in t for t in texts)


# --- the shared-axis multi-engine chart -----------------------------------------


def test_multi_engine_shared_chart_only_x(capture):
    sw.sweep(_Builder(), "length", rng=(4, 6), npoints=3, engine=ENGINES, only="x")
    (ax,) = capture["fig"].axes
    assert ax.get_ylabel() == "reactance X (Ω)"
    lines = ax.get_lines()
    assert len(lines) == 2
    assert all(ln.get_linestyle() == "--" for ln in lines)
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ["a", "b"]


# --- CLI -----------------------------------------------------------------------


def _cli(extra):
    ant.cli(
        f"sweep --builder dipoles.invvee:dipole --param length_factor "
        f"{extra} --fn /dev/null".split()
    )


@pytest.mark.parametrize(
    "extra,match",
    [
        ("--only x --r-range 1 2", "--r-range pins the R axis"),
        ("--only r --x-range 1 2", "--x-range pins the X axis"),
        ("--only x --use_smithchart", "--use_smithchart"),
        ("--only r --swr", "--swr"),
        ("--only x --gain", "--gain"),
        ("--only x --patterns", "--patterns"),
    ],
)
def test_only_refusals(extra, match):
    with pytest.raises(SystemExit, match=match):
        _cli(extra)


def test_only_rejects_an_unknown_quantity(capsys):
    with pytest.raises(SystemExit) as exc:
        _cli("--only z")
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra,expected",
    [
        ("", None),
        ("--only x --x-range -5 5", "x"),
        ("--only r --r-range 60 80 --callouts", "r"),
        ("--engine momwire,momwire:razor-2p --only x", "x"),
        ("--engine momwire,momwire:razor-2p --overlay --only r", "r"),
        ("--engine momwire,momwire:razor-2p --panels --only x --callouts", "x"),
    ],
)
def test_cli_passes_only_through(monkeypatch, extra, expected):
    seen = {}
    monkeypatch.setattr(cli_mod, "sweep", lambda *a, **kw: seen.update(kw))
    _cli(extra)
    assert seen["only"] == expected


def test_cli_only_x_draws_one_axis_end_to_end(capture, monkeypatch):
    """The real CLI -> sweep wiring, with only the engine stubbed."""

    class _Engine:
        def __init__(self, builder):
            self.lf = float(builder.length_factor)

        def impedance(self):
            return np.array([complex(70.0 * self.lf, 100.0 * (self.lf - 1.0))])

    monkeypatch.setattr(cli_mod, "make_engine_factory", lambda *a, **kw: _Engine)
    _cli("--range 0.9 1.1 --npoints 3 --only x --callouts")
    (ax,) = capture["fig"].axes
    assert ax.get_ylabel() == "reactance X (Ω)"
    (line,) = ax.get_lines()
    np.testing.assert_allclose(line.get_xdata(), [0.9, 1.0, 1.1])
    np.testing.assert_allclose(line.get_ydata(), [-10.0, 0.0, 10.0], atol=1e-9)
    assert all("\nX " in t for t in _box_texts(ax))
