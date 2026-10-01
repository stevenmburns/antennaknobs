"""AK#1828, sweep framework step 8 unit 1: DECLARATIVE METRICS
(docs/design/sweep-framework-step8-metrics.md § 1).

- ``an.ElevationWindow``, ``an.GainAt``, ``an.TakeOff``, ``an.PeakGain`` and
  the pattern table's other columns are frozen spec values: they print back
  (``to_code``, ``eval`` is the value), go to data and back, and are refused
  by name when they cannot read a pattern;
- ``az=`` is a number, ``an.PEAK_AZ`` (the table's azimuth) or ``an.MEAN_AZ``
  (the power average over the azimuth ring);
- THE PIN: the pattern table re-expressed as metrics (`metrics.table_values`)
  is ``/pattern_metrics``' answer bit for bit, on the same design at the
  same density, and `far_field.engine_pattern_metrics`' on the same solve;
- each window's arithmetic is checked against an oracle computed straight
  off the engine's gain evaluator;
- ``PatternTable(metrics=...)`` prints a column per metric in ``analyze``,
  and a table-only pattern's ``--csv`` carries them at full precision.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import far_field
from antennaknobs import metrics as mx
from antennaknobs.cli import cli, get_builder, make_engine_factory, parse_ground
from antennaknobs.web.analyses_offer import builder_for
from antennaknobs.web.examples import example_for

INVVEE = "dipoles.invvee"
ENGINE = "momwire:bspline"
N = 15
DX = an.ElevationWindow("DX gain", 2, 10, step=0.1)


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


def _record(monkeypatch, module, name):
    calls = []
    inner = getattr(module, name)

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        calls.append((args, kwargs, out))
        return out

    monkeypatch.setattr(module, name, wrapped)
    return calls


def _engine(ground="finite", **knobs):
    b = get_builder(INVVEE)()
    for k, v in knobs.items():
        setattr(b, k, v)
    g = parse_ground(ground) if ground else None
    return make_engine_factory(ENGINE, g, nominal_nsegs=N)(b)


@pytest.fixture(scope="module")
def source():
    """One solved invvee over finite ground: every window below reads it."""
    return mx.source_for(_engine())


# ── the spec values ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "metric",
    [
        DX,
        an.ElevationWindow("low", 0, 5, mean="db", az=an.MEAN_AZ),
        an.ElevationWindow("max", 1, 30, step=0.5, mean="max", az=135.5),
        an.GainAt("g10", 10),
        an.GainAt("g10 mean", 10, az=an.MEAN_AZ),
        an.TakeOff(),
        an.TakeOff(az=90, step=0.5),
        an.PeakGain(az=an.MEAN_AZ),
        *an.TABLE_METRICS,
    ],
)
def test_a_metric_prints_back_and_round_trips_through_data(metric):
    assert eval(an.to_code(metric), {"an": an}) == metric
    assert an.from_data(an.to_data(metric)) == metric
    table = an.PatternTable(metrics=(metric,))
    assert eval(an.to_code(table), {"an": an}) == table
    assert an.from_data(an.to_data(table)) == table


def test_the_constants_print_by_name():
    assert an.to_code(an.GainAt("g", 5, az=an.MEAN_AZ)) == (
        'an.GainAt("g", 5, az=an.MEAN_AZ)'
    )
    assert an.to_code(DX) == 'an.ElevationWindow("DX gain", 2, 10, step=0.1)'
    # PEAK_AZ is the default, left out like every default.
    assert an.to_code(an.ElevationWindow("w", 2, 10, az=an.PEAK_AZ)) == (
        'an.ElevationWindow("w", 2, 10)'
    )


@pytest.mark.parametrize(
    "build, words",
    [
        (lambda: an.ElevationWindow("w", 10, 2), "lo 10 is above hi 2"),
        (lambda: an.ElevationWindow("w", 2, 10, step=0.3), "does not divide"),
        (lambda: an.ElevationWindow("w", 2, 10, step=0), "positive number"),
        (lambda: an.ElevationWindow("w", 2, 100), "hi is an elevation"),
        (lambda: an.ElevationWindow("w", 2, 10, mean="rms"), "mean is 'power'"),
        (lambda: an.ElevationWindow("w", 2, 10, az=360), "0 <= az < 360"),
        (lambda: an.ElevationWindow("w", 2, 10, az=True), "az is an azimuth"),
        (lambda: an.ElevationWindow("", 2, 10), "name is a non-empty string"),
        (lambda: an.GainAt("g", -1), "el is an elevation"),
        (lambda: an.AzMode("median"), "an.PEAK_AZ or an.MEAN_AZ"),
        (lambda: an.PatternTable(metrics=(DX, DX)), "two metrics are named"),
        (lambda: an.PatternTable(metrics=("DX",)), "metrics holds metrics"),
    ],
)
def test_a_metric_that_cannot_read_a_pattern_is_refused_by_name(build, words):
    with pytest.raises((TypeError, ValueError), match=words):
        build()


def test_the_table_metrics_are_the_tables_keys_in_its_order():
    assert [m.key for m in an.TABLE_METRICS] == [
        "peak_gain_dbi",
        "takeoff_deg",
        "azimuth_deg",
        "front_to_back_db",
        "az_beamwidth_deg",
        "el_beamwidth_deg",
        "rdf_db",
    ]
    # Away from PEAK_AZ, PeakGain and TakeOff read their own cut, not the
    # table's column.
    assert an.PeakGain().table_key == "peak_gain_dbi"
    assert an.PeakGain(az=0).table_key is None
    assert an.TakeOff(az=an.MEAN_AZ).table_key is None


# ── THE PIN: the table as metrics is /pattern_metrics, bit for bit ────────


def _req(**knobs) -> dict:
    cls = example_for(INVVEE).builder_cls
    b = builder_for(cls, {"geometry": INVVEE, "variant": "default"})
    values = {
        k: [dict(e) for e in v] if isinstance(v, tuple) else v
        for k, v in an._params(b).items()
        if k not in ("ui_params", "nominal_nsegs", "freq", "design_freq")
    }
    return {
        "geometry": INVVEE,
        "variant": "default",
        **values,
        **knobs,
        "design_freq_mhz": b.design_freq,
        "measurement_freq_mhz": b.freq,
        "solver": "momwire",
        "momwire_model": "bspline",
        "n_per_wire": N,
        "ground": False,
    }


@pytest.mark.parametrize("knobs", [{}, {"base": 12.0}])
def test_the_table_as_metrics_is_pattern_metrics_bit_for_bit(client, knobs):
    """The workbench compare table's numbers (``/pattern_metrics``, free
    space, where its request and the CLI's builder are the same antenna) and
    `metrics.table_values` on the CLI's engine for that design: ``==`` key
    for key. And `far_field.engine_pattern_metrics` on the same solve, the
    function the table's columns used to be read by directly."""
    r = client.post("/pattern_metrics", json=_req(**knobs))
    assert r.status_code == 200, r.text
    served = r.json()["metrics"]
    served.pop("measurement_freq_mhz")
    eng = _engine(ground=None, **knobs)
    got = mx.table_values(mx.source_for(eng))
    assert set(got) == set(served) == {m.key for m in an.TABLE_METRICS}
    assert got == served
    assert got == far_field.engine_pattern_metrics(eng, None)
    # Through `evaluate`, one metric at a time: the same numbers.
    src = mx.source_for(eng)
    assert {m.key: mx.evaluate(m, src) for m in an.TABLE_METRICS} == served


def test_a_grid_engines_table_is_compare_patterns_grid_measure():
    """An engine without a gain evaluator is read off its 1-degree grid, and
    its table is `far_field.pattern_metrics` on that grid, as
    `engine_pattern_metrics` reads it."""
    try:
        eng = make_engine_factory("pynec", parse_ground("finite"))(
            get_builder(INVVEE)()
        )
        ff = eng.far_field(**ar.PATTERN_GRID)
    except Exception as e:  # noqa: BLE001 — the engine is optional here
        pytest.skip(f"pynec unavailable: {e}")
    src = mx.source_for(eng, ff)
    assert isinstance(src, mx.GridSource)
    assert mx.table_values(src) == far_field.engine_pattern_metrics(eng, ff)
    # Whole degrees are read exactly off the grid; a finer step is refused
    # by name, never interpolated.
    g10 = mx.evaluate(an.GainAt("g", 10, az=0), src)
    assert g10 == np.asarray(ff.rings)[80][0]
    with pytest.raises(mx.MetricError, match="1-degree grid"):
        mx.evaluate(an.ElevationWindow("w", 2, 10, step=0.1, az=0), src)


# ── the arithmetic, against an oracle off the evaluator ───────────────────


def _oracle_cut(source, els, az):
    g = source._gain
    thetas = 90.0 - np.asarray(els, float)
    if az == an.MEAN_AZ:
        p = 10 ** (g(thetas, np.arange(360.0)) / 10)
        return 10 * np.log10(p.mean(axis=1))
    a = source.table()["azimuth_deg"] if az == an.PEAK_AZ else az
    return g(thetas, [a])[:, 0]


@pytest.mark.parametrize("az", [an.PEAK_AZ, an.MEAN_AZ, 0, 90, 37.5])
def test_an_elevation_window_is_the_power_mean_of_its_cut(source, az):
    els = 2 + 0.1 * np.arange(81)
    cut = _oracle_cut(source, els, az)
    want = 10 * np.log10(np.mean(10 ** (cut / 10)))
    got = mx.evaluate(an.ElevationWindow("w", 2, 10, step=0.1, az=az), source)
    assert got == pytest.approx(want, abs=1e-12)
    # The other means, the same cut.
    db = mx.evaluate(an.ElevationWindow("w", 2, 10, step=0.1, mean="db", az=az), source)
    top = mx.evaluate(
        an.ElevationWindow("w", 2, 10, step=0.1, mean="max", az=az), source
    )
    assert db == pytest.approx(float(np.mean(cut)), abs=1e-12)
    assert top == pytest.approx(float(np.max(cut)), abs=1e-12)
    # Adversarial: averaging dB is not averaging power (M0AGP's point), and
    # the power mean lies between the dB mean and the maximum.
    assert db < got < top


def test_the_azimuth_modes_read_different_cuts(source):
    """The invvee's lobes are broadside (azimuth 0 / 180), so a cut along
    the wire reads far less, and the azimuth average lies between."""
    peak = mx.evaluate(DX, source)
    along = mx.evaluate(an.ElevationWindow("w", 2, 10, step=0.1, az=90), source)
    mean = mx.evaluate(an.ElevationWindow("w", 2, 10, step=0.1, az=an.MEAN_AZ), source)
    assert source.table()["azimuth_deg"] == 0.0
    assert along < mean < peak
    assert peak - along > 5.0


def test_gain_at_take_off_and_peak_on_a_cut(source):
    els = np.arange(0.0, 91.0)
    cut = _oracle_cut(source, els, 0.0)
    i = int(np.flatnonzero(cut >= cut.max())[-1])
    assert mx.evaluate(an.PeakGain(az=0), source) == pytest.approx(cut[i], abs=1e-12)
    assert mx.evaluate(an.TakeOff(az=0), source) == els[i]
    assert mx.evaluate(an.GainAt("g", 30, az=0), source) == pytest.approx(
        cut[30], abs=1e-12
    )
    # At PEAK_AZ the table's own (refined) numbers, not the 1-degree cut's.
    assert mx.evaluate(an.TakeOff(), source) == source.table()["takeoff_deg"]


def test_the_polarised_gains_add_up_to_the_total(source):
    th, ph = np.array([0.0, 45.0, 80.0, 88.0]), np.array([0.0, 30.0, 90.0])
    v, h = source.polarized(th, ph)
    total = source.gain(th, ph)
    both = 10 * np.log10(10 ** (v / 10) + 10 ** (h / 10))
    assert np.allclose(both, total, atol=1e-9)
    # A horizontal dipole broadside at low angles is horizontally polarised.
    assert h[1, 0] > v[1, 0] + 10


# ── the CLI: a column per metric, and the table's CSV ─────────────────────


def _offer(monkeypatch, analyses):
    monkeypatch.setattr(
        type(get_builder(INVVEE)()), "build_analyses", lambda self: list(analyses)
    )


def test_analyze_prints_a_column_per_metric_and_csv_writes_them(
    monkeypatch, capsys, tmp_path
):
    mean = an.ElevationWindow("DX mean az", 2, 10, step=0.1, az=an.MEAN_AZ)
    a = an.patterns(
        name="dx",
        cross=an.Cross(states=(an.State("as built"), an.State("tall", base=12.0))),
        views=(an.PatternTable(metrics=(DX, mean)),),
        ground="finite",
    )
    _offer(monkeypatch, [a])
    runs = _record(monkeypatch, ar, "_run_patterns")
    values = _record(monkeypatch, mx, "values")
    out = tmp_path / "t.csv"
    cli(["analyze", "--builder", INVVEE, "--analysis", "dx", "--engine", ENGINE,
         "--nominal-nsegs", str(N), "--csv", str(out), "--fn", "/dev/null"])  # fmt: skip
    printed = capsys.readouterr().out
    assert "DX gain (dBi)" in printed and "DX mean az (dBi)" in printed
    got = runs[-1][2]["patterns"]
    assert len(values) == 2  # one read per cell, both metrics each
    # The values are the metric read off that cell's own engine.
    for st in ("as built", "tall"):
        knobs = {"base": 12.0} if st == "tall" else {}
        src = mx.source_for(_engine(**knobs))
        assert got[st].values == {
            "DX gain": mx.evaluate(DX, src),
            "DX mean az": mx.evaluate(mean, src),
        }
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0][0] == "cell" and rows[0][-2:] == [
        "DX gain (dBi)",
        "DX mean az (dBi)",
    ]
    for row in rows[1:]:
        cell = got[row[0]]
        assert float(row[-2]) == cell.values["DX gain"]
        assert float(row[-1]) == cell.values["DX mean az"]
        assert float(row[1]) == cell.metrics["peak_gain_dbi"]
    # Adversarial: the tall mast's low-angle gain is higher.
    assert got["tall"].values["DX gain"] > got["as built"].values["DX gain"] + 1


def test_a_metric_an_engine_cannot_read_refuses_its_cell_by_name(monkeypatch, capsys):
    a = an.patterns(name="fine", views=(an.PatternTable(metrics=(DX,)),))
    _offer(monkeypatch, [a])
    try:
        make_engine_factory("pynec", None)(get_builder(INVVEE)()).far_field(
            **ar.PATTERN_GRID
        )
    except Exception as e:  # noqa: BLE001 — the engine is optional here
        pytest.skip(f"pynec unavailable: {e}")
    with pytest.raises(SystemExit, match="every pattern was refused"):
        cli(["analyze", "--builder", INVVEE, "--analysis", "fine", "--engine",
             "pynec", "--fn", "/dev/null"])  # fmt: skip
    assert "1-degree grid" in capsys.readouterr().out


# ── NEC-5's exact RP grid ─────────────────────────────────────────────────


def test_nec5_reads_the_field_magnitudes_beside_the_total():
    from pathlib import Path

    from antennaknobs.engines.nec5 import NEC5Engine, _even_axis

    text = (
        Path(__file__).parent / "fixtures" / "nec5" / "invvee_dipole_pattern.out"
    ).read_text()
    rows = NEC5Engine._parse_radiation_fields(text)
    totals = NEC5Engine._parse_radiation_patterns(text)
    assert {k: v[0] for k, v in rows.items()} == totals
    assert rows[(0.0, 90.0)] == (2.14, 8.26520e-01, 2.18900e-14)
    # An RP grid from any evenly spaced angles, finest 0.01 degree.
    assert _even_axis([88.0, 87.9, 80.0, 87.95][:2] + [87.8], "theta") == (
        3,
        87.8,
        0.1,
    )
    assert _even_axis([30.0], "phi") == (1, 30.0, 1.0)
    with pytest.raises(ValueError, match="not evenly spaced"):
        _even_axis([1.0, 2.0, 4.0], "theta")
    with pytest.raises(ValueError, match="finer than 0.01"):
        _even_axis([1.0, 1.005], "theta")


def test_the_workbench_names_the_table_columns_it_leaves_to_analyze():
    """The chart's pattern table is the compare table's: a column the
    analysis's table names is said to be `analyze`'s, never dropped quietly."""
    from antennaknobs.web.analyses_offer import workbench

    b = get_builder(INVVEE)()
    a = an.patterns(name="t", views=(an.PatternTable(metrics=(DX,)),))
    w = workbench(a, b, {"geometry": INVVEE})
    assert w["runs"] is True
    assert w["note"] == (
        "left out: the table's metric columns 'DX gain' (`antennaknobs analyze` "
        "prints them)"
    )
    assert workbench(an.patterns(name="p"), b, {"geometry": INVVEE})["note"] is None
