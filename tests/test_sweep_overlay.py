"""`sweep --overlay`: several engines on ONE twin-axis R/X chart.

R (solid) on the left axis and X (dashed) on the right, each shared by every
engine so the ranges are the union and the curves compare directly; one
colour and marker per engine; callouts per engine, staggered. Stub engines
only — no solver runs.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

import antennaknobs as ant

sw = sys.modules["antennaknobs.sweep"]


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
    "c": _stub_engine(r_offset=-1.0, x_offset=2.0),
}


@pytest.fixture
def capture(monkeypatch):
    import matplotlib.pyplot as plt

    got = {}
    monkeypatch.setattr(sw, "save_or_show", lambda _p, _f: got.update(fig=plt.gcf()))
    yield got
    plt.close("all")


def _lines(ax):
    """Data lines (not the legend-less Z* hlines, which are 2-point spans)."""
    return [ln for ln in ax.get_lines() if len(ln.get_xdata()) > 2]


def _span(lines, attr="get_ydata"):
    ys = np.concatenate([getattr(ln, attr)() for ln in lines])
    return ys.min(), ys.max()


def _general(**kw):
    sw.sweep(
        _Builder(),
        "length",
        rng=(2, 50),
        npoints=6,
        engine=ENGINES,
        log=True,
        overlay=True,
        **kw,
    )


def test_one_axes_pair_one_r_and_one_x_line_per_engine(capture):
    _general()
    axes = capture["fig"].axes
    assert len(axes) == 2  # the R axes and its X twin, nothing else
    ax_r, ax_x = axes
    assert ax_r.get_xscale() == "log"
    r_lines, x_lines = _lines(ax_r), _lines(ax_x)
    assert [ln.get_label() for ln in r_lines] == ["a R", "b R", "c R"]
    assert [ln.get_label() for ln in x_lines] == ["a X", "b X", "c X"]
    assert all(ln.get_linestyle() == "-" for ln in r_lines)
    assert all(ln.get_linestyle() == "--" for ln in x_lines)
    # One colour and one marker per engine, shared by its R and X lines.
    colors = [ln.get_color() for ln in r_lines]
    assert len(set(colors)) == 3
    assert colors == [ln.get_color() for ln in x_lines]
    assert len({ln.get_marker() for ln in r_lines}) == 3
    legend = [t.get_text() for t in ax_r.get_legend().get_texts()]
    assert legend == ["a R", "a X", "b R", "b X", "c R", "c X"]


def test_axis_ranges_are_the_union_across_engines(capture):
    _general()
    ax_r, ax_x = capture["fig"].axes
    lo, hi = _span(_lines(ax_r))
    assert ax_r.get_ylim()[0] <= lo and ax_r.get_ylim()[1] >= hi
    lo, hi = _span(_lines(ax_x))
    assert ax_x.get_ylim()[0] <= lo and ax_x.get_ylim()[1] >= hi


def test_explicit_ranges_still_override(capture):
    _general(r_range=(60.0, 80.0), x_range=(-10.0, 5.0))
    ax_r, ax_x = capture["fig"].axes
    assert ax_r.get_ylim() == (60.0, 80.0)
    assert ax_x.get_ylim() == (-10.0, 5.0)


def test_callouts_label_each_engines_ends_without_overlap(capture):
    _general(callouts=True)
    ax_r, ax_x = capture["fig"].axes
    boxes = [t for t in ax_r.texts if t.get_text()]
    heads = [t.get_text().split("\n")[0] for t in boxes]
    assert heads == [
        "a length=2",
        "b length=2",
        "c length=2",
        "a length=50",
        "b length=50",
        "c length=50",
    ]
    # One box per engine per end carries both values, with an arrow to the
    # X point on the X axis as well.
    assert all(" X " in t.get_text() for t in boxes)
    assert len(ax_x.texts) == 6
    # Each end's boxes form a column, spread so no two share a height.
    for end in (boxes[:3], boxes[3:]):
        ys = sorted(t.xyann[1] for t in end)
        assert min(np.diff(ys)) >= 0.08
        assert len({t.xyann[0] for t in end}) == 1


def test_convergence_overlay_draws_each_engines_zstar(capture, monkeypatch, capsys):
    monkeypatch.setattr(sw, "_achieved_n", lambda eng, b: 2 * b.nominal_nsegs + 1)
    sw.sweep(
        _Builder(),
        "nominal_nsegs",
        rng=(8, 160),
        npoints=5,
        engine=ENGINES,
        overlay=True,
        callouts=True,
    )
    capsys.readouterr()
    axes = capture["fig"].axes
    assert len(axes) == 2
    ax_r, ax_x = axes
    assert ax_r.get_xscale() == "log"
    assert len(_lines(ax_r)) == 3 and len(_lines(ax_x)) == 3
    # Z*: one dotted horizontal line per engine per axis, in its colour.
    for ax in (ax_r, ax_x):
        dotted = [ln for ln in ax.get_lines() if ln.get_linestyle() == ":"]
        assert [ln.get_color() for ln in dotted] == [
            ln.get_color() for ln in _lines(ax)
        ]
    assert len(ax_r.texts) == 6


@pytest.mark.parametrize(
    "extra,match",
    [
        ("--engine momwire,momwire:razor-2p --overlay --panels", "--panels"),
        ("--overlay", "two or more"),
        ("--engine momwire,momwire:razor-2p --overlay --use_smithchart", "smith"),
    ],
)
def test_overlay_refusals(extra, match):
    with pytest.raises(SystemExit, match=match):
        ant.cli(
            f"sweep --builder dipoles.invvee:dipole --param length_factor "
            f"{extra} --fn /dev/null".split()
        )


def test_multi_engine_callouts_accept_overlay_as_the_layout(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        sys.modules["antennaknobs.cli"],
        "sweep",
        lambda *a, **kw: seen.update(kw),
    )
    ant.cli(
        "sweep --builder dipoles.invvee:dipole --param length_factor "
        "--engine momwire,momwire:razor-2p --overlay --callouts".split()
    )
    assert seen["overlay"] is True and seen["panels"] is False
