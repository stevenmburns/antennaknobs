"""AK#1757, sweep framework step 4: the frequency sweep as an analysis.

What is pinned here:

- ONE precedence for a frequency sweep's default range
  (`frequency_range.design_range`), at each rung: a file's own sweep, a
  design's ``sweep_range``, its ``meas_freq_range``, its band policy (band
  lock, then factors), the default window; and ``sweep --swr``, ``analyze``
  and ``/analyses`` all reach it;
- the ORACLE, with real solves on Dan's E4 deck: ``analyze --analysis "band
  SWR"`` computes the SWR of ``sweep --swr --range 14 14.35 --npoints 15`` at
  the same 15 frequencies, through the same solve (``sweep.swr_curve``);
- the E4 gap closed: ``sweep --swr`` with no range sweeps the deck's own
  14.0–14.35 MHz grid, not the ×0.8–×1.25 window; on a design with no range
  of its own the grid is exactly the old one;
- the 2:1 bandwidth readout: both crossings, a band running off an end of
  the sweep, none, two;
- ``analyze`` draws the Swr, S11 and Smith views as panels;
- ``/analyses`` serves a frequency analysis as the frequency sweep's range,
  views, scale and threshold.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import frequency_range as fr
from antennaknobs.cli import cli, get_builder

sw = importlib.import_module("antennaknobs.sweep")
cli_mod = importlib.import_module("antennaknobs.cli")

SSN = (
    Path(__file__).parent
    / "fixtures"
    / "ssn_numericparam_1716"
    / "snDipoleVarLenSegs.ssn"
)
E4_GRID = np.linspace(14.0, 14.35, 15)


# ── the precedence, rung by rung ───────────────────────────────────────────


def _params(freq=14.2, design_freq=None, **ui):
    p = {"freq": freq, "ui_params": ui}
    if design_freq is not None:
        p["design_freq"] = design_freq
    return p


def test_rung_1_a_files_own_sweep_with_its_grid():
    r = fr.design_range(
        _params(
            sweep_range={"lo": 14, "hi": 14.35, "step": 0.025, "source": "file"},
            meas_freq_range=(13, 15),
            sweep_policy={"band_locked": True},
        )
    )
    assert (r.lo, r.hi, r.level, r.spacing, r.step) == (14, 14.35, "file", "lin", 0.025)
    assert r.count() == 15


def test_rung_2_a_designs_sweep_range_outranks_its_dial_span():
    r = fr.design_range(
        _params(
            sweep_range={"lo": 7.0, "hi": 7.3, "spacing": "log", "points": 13},
            meas_freq_range=(6, 8),
        )
    )
    assert (r.lo, r.hi, r.level, r.spacing, r.points) == (7, 7.3, "design", "log", 13)


def test_rung_2_the_dial_span_states_a_range_but_no_grid():
    r = fr.design_range(
        _params(meas_freq_range=(400.0, 412.0), sweep_policy={"band_locked": True})
    )
    assert (r.lo, r.hi, r.level, r.spacing, r.step, r.points) == (
        400,
        412,
        "design",
        None,
        None,
        None,
    )
    # The CLI's own density where the design states none: 21 linear points.
    assert np.array_equal(r.grid(), np.linspace(400, 412, 21))


def test_rung_3_a_band_lock_is_the_band_holding_the_anchor():
    r = fr.design_range(_params(freq=14.1, sweep_policy={"band_locked": True}))
    assert (r.lo, r.hi, r.level) == (14.0, 14.35, "policy")
    # The design's own band table wins over the amateur set.
    r = fr.design_range(
        _params(
            freq=406.0,
            sweep_policy={"band_locked": True},
            bands=(("406", "406 MHz", 406.0, 400.0, 412.0),),
        )
    )
    assert (r.lo, r.hi) == (400.0, 412.0)
    # design_freq is the default anchor; meas_freq anchors on freq.
    r = fr.design_range(
        _params(freq=21.2, design_freq=14.2, sweep_policy={"band_locked": True})
    )
    assert (r.lo, r.hi) == (14.0, 14.35)
    r = fr.design_range(
        _params(
            freq=21.2,
            design_freq=14.2,
            sweep_policy={"anchor": "meas_freq", "band_locked": True},
        )
    )
    assert (r.lo, r.hi) == (21.0, 21.45)


def test_rung_3_policy_factors_off_every_band():
    r = fr.design_range(_params(freq=12.0, sweep_policy=("meas_freq", 0.95, 1.05)))
    assert (r.lo, r.hi, r.level) == (pytest.approx(11.4), pytest.approx(12.6), "policy")


def test_rung_4_the_default_window_is_the_clis_historical_one():
    r = fr.design_range(_params(freq=28.47))
    assert r.level == "default"
    # Exactly `sweep.resolve_range`'s rule, so the grid is the old grid.
    assert (r.lo, r.hi) == sw.resolve_range(28.47, None, None, None)
    assert np.array_equal(r.grid(), sw.gen_xs(28.47, None, None, None, 21))


@pytest.mark.parametrize(
    ("design", "want"),
    [
        (f"@{SSN}", ("file", 14.0, 14.35, 15)),
        ("verticals.elt_whip", ("design", 400.0, 412.0, 21)),
        ("dipoles.pota_invvee", ("policy", 14.0, 14.35, 21)),
        ("dipoles.invvee", ("default", 28.47 / 1.25, 28.47 * 1.25, 21)),
    ],
)
def test_catalog_designs_and_the_deck_at_their_rungs(design, want):
    r = fr.design_range(get_builder(design)()._params)
    assert (r.level, r.lo, r.hi, r.count()) == want


def test_examples_serves_the_declared_rungs_only(monkeypatch):
    """/examples' ``sweep_range`` is `declared`: a dial span is served as the
    range (log, the workbench's own spacing), a band policy is not."""
    # The adapter is imported through the registry, never first.
    importlib.import_module("antennaknobs.web.examples")
    from antennaknobs.web.adapter import _served_sweep_range

    assert _served_sweep_range(_params(meas_freq_range=(400.0, 412.0))) == {
        "lo": 400.0,
        "hi": 412.0,
        "spacing": "log",
        "source": "design",
    }
    assert _served_sweep_range(_params(sweep_policy={"band_locked": True})) is None


# ── one function, read by every tool ───────────────────────────────────────


@pytest.fixture
def no_solve(monkeypatch):
    """``sweep.swr_curve`` recording its grid and answering Z = 50 Ω."""
    grids = []

    def fake(builder, nm, xs, engine, z0):
        grids.append(np.asarray(xs))
        zs = np.full((len(xs), 1), 50 + 0j)
        rho = np.abs((zs - z0) / (zs + z0))
        return zs, (1 + rho) / (1 - rho)

    monkeypatch.setattr(sw, "swr_curve", fake)
    return grids


@pytest.fixture
def ranges(monkeypatch):
    """Record every `design_range` call's level."""
    seen = []
    inner = fr.design_range

    def wrapped(params):
        r = inner(params)
        seen.append(r.level)
        return r

    monkeypatch.setattr(fr, "design_range", wrapped)
    return seen


def test_sweep_analyze_and_the_workbench_all_read_design_range(
    no_solve, ranges, tmp_path
):
    cli(["sweep", "--builder", f"@{SSN}", "--swr", "--fn", str(tmp_path / "s.png")])
    assert ranges == ["file"]
    cli(["analyze", "--builder", f"@{SSN}", "--analysis", "band SWR",
         "--fn", str(tmp_path / "a.png")])  # fmt: skip
    assert ranges[1:] and set(ranges[1:]) == {"file"}
    n = len(ranges)
    _workbench(f"@{SSN}")
    assert ranges[n:] and set(ranges[n:]) == {"file"}
    # Both CLI paths swept the deck's own grid.
    assert all(np.array_equal(g, E4_GRID) for g in no_solve)


# ── the E4 gap: sweep --swr and the file's own sweep ──────────────────────────


def test_sweep_swr_with_no_range_sweeps_the_decks_own_grid(no_solve, tmp_path):
    cli(["sweep", "--builder", f"@{SSN}", "--swr", "--fn", str(tmp_path / "s.png")])
    (xs,) = no_solve
    assert np.array_equal(xs, E4_GRID)
    # Adversarial: the ×0.8–×1.25 window this used to fall back to is
    # 11.2–17.5 MHz in 21 points; none of it may survive.
    old = sw.gen_xs(14.0, None, None, None, 21)
    assert len(xs) != len(old) and xs[0] > old[0] and xs[-1] < old[-1]
    assert xs[0] == 14.0 and xs[-1] == 14.35


def test_npoints_alone_keeps_the_decks_span(no_solve, tmp_path):
    cli(["sweep", "--builder", f"@{SSN}", "--swr", "--npoints", "8",
         "--fn", str(tmp_path / "s.png")])  # fmt: skip
    assert np.array_equal(no_solve[0], np.linspace(14.0, 14.35, 8))


def test_center_or_fraction_is_the_relative_window_it_always_was(no_solve, tmp_path):
    cli(["sweep", "--builder", f"@{SSN}", "--swr", "--center", "14.2",
         "--fn", str(tmp_path / "s.png")])  # fmt: skip
    cli(["sweep", "--builder", f"@{SSN}", "--swr", "--fraction", "1.1",
         "--fn", str(tmp_path / "s.png")])  # fmt: skip
    assert np.array_equal(no_solve[0], sw.gen_xs(14.0, None, 14.2, None, 21))
    assert np.array_equal(no_solve[1], sw.gen_xs(14.0, None, None, 1.1, 21))


def test_a_design_with_no_range_of_its_own_sweeps_the_old_grid(no_solve, tmp_path):
    """dipoles.invvee declares no range and no policy: the grid is main's,
    bit for bit (the rendered chart was compared byte for byte when this
    landed)."""
    cli(["sweep", "--builder", "dipoles.invvee", "--swr",
         "--fn", str(tmp_path / "s.png")])  # fmt: skip
    b = get_builder("dipoles.invvee")()
    assert np.array_equal(no_solve[0], sw.gen_xs(b.freq, None, None, None, 21))


# ── the oracle ───────────────────────────────────────────────────────────────


def _recording(monkeypatch):
    calls = []
    inner = sw.swr_curve

    def wrapped(builder, nm, xs, engine, z0):
        zs, swr = inner(builder, nm, xs, engine, z0)
        calls.append((np.array(xs), np.array(swr)))
        return zs, swr

    monkeypatch.setattr(sw, "swr_curve", wrapped)
    return calls


def test_oracle_analyze_band_swr_is_sweep_swr_on_e4(monkeypatch, tmp_path, capsys):
    calls = _recording(monkeypatch)
    cli(["analyze", "--builder", f"@{SSN}", "--analysis", "band SWR",
         "--fn", str(tmp_path / "a.png")])  # fmt: skip
    cli(["sweep", "--builder", f"@{SSN}", "--swr", "--range", "14", "14.35",
         "--npoints", "15", "--fn", str(tmp_path / "s.png")])  # fmt: skip
    (xa, swr_a), (xs, swr_s) = calls
    assert np.array_equal(xa, E4_GRID) and np.array_equal(xs, E4_GRID)
    assert swr_a.shape == swr_s.shape == (15, 1)
    rel = np.max(np.abs(swr_a - swr_s) / np.abs(swr_s))
    assert rel <= 1e-12, rel
    out = capsys.readouterr().out
    assert "frequency 14..14.35 MHz, 15 points (the file's own range)" in out
    assert "2:1 BW" in out


# ── the bandwidth readout ────────────────────────────────────────────────────


def test_both_crossings_are_interpolated():
    xs = [1.0, 2.0, 3.0, 4.0]
    (b,) = ar.swr_bands(xs, [3.0, 1.0, 1.0, 3.0], 2.0)
    assert (b.lo, b.hi, b.open_lo, b.open_hi) == (1.5, 3.5, False, False)
    line = ar.bandwidth_line("c", xs, [3.0, 1.0, 1.0, 3.0], [b], 2.0, 2.5)
    assert line.startswith("c: 2:1 BW 2.000 MHz, 1.5..3.5 MHz;")
    assert "runs off" not in line


def test_a_band_running_off_an_end_says_so():
    xs = [14.0, 14.1, 14.2]
    swr = [1.2, 1.5, 3.0]
    (b,) = ar.swr_bands(xs, swr, 2.0)
    assert b.open_lo and not b.open_hi and b.lo == 14.0
    line = ar.bandwidth_line("c", xs, swr, [b], 2.0, 14.1)
    assert "BW ≥ " in line and "(runs off the low end of the sweep)" in line
    assert "the true minimum may lie past it" in line


def test_a_curve_that_never_crosses_says_none():
    xs = [14.0, 14.1, 14.2]
    swr = [3.0, 2.5, 2.0]  # AT the threshold is not below it
    assert ar.swr_bands(xs, swr, 2.0) == []
    line = ar.bandwidth_line("c", xs, swr, [], 2.0, 14.1)
    assert line.startswith("c: 2:1 BW none: SWR stays at or above 2:1 over 14..14.2")


def test_two_bands_report_the_one_holding_the_frequency():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    swr = [3.0, 1.0, 3.0, 1.0, 3.0]
    bands = ar.swr_bands(xs, swr, 2.0)
    assert len(bands) == 2
    line = ar.bandwidth_line("c", xs, swr, bands, 2.0, 4.0)
    assert "3.5..4.5 MHz" in line and "(1 of 2 bands below 2:1)" in line


def test_the_swr_scales():
    y = ar.swr_scale_y([1.0, 2.0, 3.0, np.inf, np.nan, 0.5], "reciprocal")
    assert np.allclose(y, [0, 0.5, 2 / 3, 1, 1, 0])
    y = ar.swr_scale_y([1.0, 2.0, 3.0, np.inf], "rho")
    assert np.allclose(y, [0, 1 / 3, 0.5, 1])


# ── analyze draws the views ──────────────────────────────────────────────────


@pytest.fixture
def figures(monkeypatch):
    """Every figure `save_or_show` writes: (fn, its axes' titles)."""
    import antennaknobs.core as core

    shots = []
    inner = core.save_or_show

    def wrapped(plt, fn):
        shots.append((fn, [ax.get_title() for ax in plt.gcf().axes]))
        return inner(plt, fn)

    monkeypatch.setattr(core, "save_or_show", wrapped)
    return shots


def _run(a, design, tmp_path, fn="a.png"):
    make = get_builder(design)

    def factory_for(engine, ground, density):
        return cli_mod.make_engine_factory(
            engine, cli_mod.resolve_ground(cli_mod._GROUND_UNSET, make)
        )

    return ar.run(
        a,
        make,
        factory_for=factory_for,
        ground_label_for=lambda spec: "free",
        session_engine="momwire",
        fn=str(tmp_path / fn),
    )


def test_e4_draws_swr_s11_and_smith_as_panels(monkeypatch, figures, tmp_path, capsys):
    a = an.band_swr(views=(an.Swr(scale="rho"), an.S11(), an.Smith(), an.Table()))
    cls = type(get_builder(f"@{SSN}")())
    monkeypatch.setattr(cls, "build_analyses", lambda self: [a], raising=False)
    out = _run(a, f"@{SSN}", tmp_path)
    ((fn, titles),) = figures
    assert fn == str(tmp_path / "a.png") and (tmp_path / "a.png").exists()
    assert titles == ["SWR (z0 = 50 Ω)", "S11 (z0 = 50 Ω)", "Smith (z0 = 50 Ω)"]
    text = capsys.readouterr().out
    assert "== frequency sweep: momwire ==" in text
    assert "SWR" in text and "2:1 BW" in text
    assert list(out["curves"]["momwire"][0]) == list(E4_GRID)


def test_band_swr_runs_on_a_catalog_design(monkeypatch, figures, tmp_path, capsys):
    a = an.band_swr(sweep=an.Sweep(an.FREQUENCY, 27.5, 29.5, points=9))
    _offer = [a]
    cls = type(get_builder("dipoles.invvee")())
    monkeypatch.setattr(cls, "build_analyses", lambda self: _offer)
    cli(["analyze", "--builder", "dipoles.invvee", "--analysis", "band SWR",
         "--nominal-nsegs", "8", "--fn", str(tmp_path / "a.png")])  # fmt: skip
    ((fn, titles),) = figures
    assert titles == ["SWR (z0 = 50 Ω)"]
    text = capsys.readouterr().out
    assert "frequency 27.5..29.5 MHz, 9 points (the analysis's own range)" in text
    assert "momwire: 2:1 BW" in text


def test_an_rx_view_beside_the_panels_writes_both(monkeypatch, figures, tmp_path):
    a = an.band_swr(
        sweep=an.Sweep(an.FREQUENCY, 14.0, 14.35, points=4), views=(an.Rx(), an.Smith())
    )
    _run(a, f"@{SSN}", tmp_path)
    assert [f for f, _ in figures] == [
        str(tmp_path / "a.png"),
        str(tmp_path / "a-views.png"),
    ]
    assert (tmp_path / "a-views.png").exists()


def test_the_list_no_longer_refuses_band_swr(capsys):
    cli(["analyze", "--builder", f"@{SSN}", "--list"])
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("band SWR"))
    assert "frequency (freq) 14..14.35 MHz (the file's own, 15 points)" in line
    assert "step 4" not in out


# ── the workbench: /analyses ────────────────────────────────────────────────


def _workbench(design, analyses=None, monkeypatch=None):
    """The frequency analyses' ``workbench`` entries, as /analyses serves
    them (a frequency entry reads nothing from the request)."""
    from antennaknobs.web.analyses_offer import workbench

    b = get_builder(design)()
    if analyses is not None:
        monkeypatch.setattr(type(b), "build_analyses", lambda self: analyses)
    return {
        a.name: workbench(a, b, {})
        for a in an.offered(b)
        if len(a.sweeps) == 1 and a.sweep.knob == an.FREQUENCY
    }


def test_e4_is_served_as_the_decks_own_range_and_the_views_scale():
    w = _workbench(f"@{SSN}")["band SWR"]
    assert w == {
        "runs": True,
        "kind": "frequency",
        "range": fr.design_range(get_builder(f"@{SSN}")()._params).as_spec(),
        "level": "file",
        "points": None,
        "views": ["Swr"],
        "swr": {"scale": "auto", "threshold": 2.0},
        "engines": None,
        "grounds": None,
        "note": None,
    }
    assert w["range"]["lo"] == 14.0 and w["range"]["hi"] == 14.35
    assert w["range"]["spacing"] == "lin" and w["range"]["source"] == "file"


@pytest.mark.parametrize(
    ("design", "level"),
    [("dipoles.invvee", "default"), ("dipoles.pota_invvee", "policy")],
)
def test_a_band_policy_is_the_sessions_to_place(design, level):
    w = _workbench(design)["band SWR"]
    assert w["runs"] is True and w["range"] is None and w["level"] == level


def test_a_view_the_workbench_lacks_is_left_out_by_name(monkeypatch):
    a = an.band_swr(
        name="e5ish",
        sweep=an.Sweep(an.FREQUENCY, 14.0, 14.35, points=8),
        views=(an.Swr(scale="rho"), an.Rx(), an.Table(), an.Smith()),
    )
    w = _workbench("dipoles.invvee", [a], monkeypatch)["e5ish"]
    assert w["views"] == ["Swr", "Smith"]
    assert w["swr"] == {"scale": "rho", "threshold": 2.0}
    assert w["range"] == {
        "lo": 14.0,
        "hi": 14.35,
        "spacing": "lin",
        "source": "design",
        "points": 8,
    }
    assert w["level"] == "analysis" and w["points"] == 8
    assert "left out: the Rx view of a frequency sweep" in w["note"]
    assert (
        "left out: the Table view: not in the workbench yet (sweep-framework step 5)"
        in w["note"]
    )


def test_no_drawable_view_or_explicit_frequencies_are_refused(monkeypatch):
    only_rx = an.band_swr(name="rx", views=(an.Rx(),))
    listed = an.band_swr(
        name="listed", sweep=an.Sweep(an.FREQUENCY, values=(14.0, 14.2))
    )
    got = _workbench("dipoles.invvee", [only_rx, listed], monkeypatch)
    assert got["rx"]["runs"] is False
    assert (
        "the Rx view of a frequency sweep: not in the workbench yet (sweep-framework step 5)"
        in got["rx"]["why"]
    )
    assert got["listed"]["runs"] is False
    assert (
        "explicit frequencies (give the Sweep lo, hi and points): not in the workbench yet (sweep-framework step 5)"
        in got["listed"]["why"]
    )


def test_rung_3_a_lock_off_every_band_keeps_its_own_anchor():
    # design_freq 13.0 sits in no amateur band: the lock falls back to the
    # policy's factors around design_freq, not the default window around freq.
    r = fr.design_range(
        _params(freq=14.2, design_freq=13.0, sweep_policy={"band_locked": True})
    )
    assert (r.lo, r.hi, r.level) == (
        pytest.approx(10.4),
        pytest.approx(16.25),
        "policy",
    )
