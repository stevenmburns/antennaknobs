"""The fill report's metrics on the density ladder (AK#2327).

How good the reuse is, and what the fill and factor cost, at each rung of
`an.convergence()`: one point per rung, each read off that rung's own solve.
A rung that cannot say (another engine, reuse off for the compression, a
momwire with no report) has no point, never a zero. The solve answers do not
move.
"""

from __future__ import annotations

import warnings

import momwire
import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server as server
from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import fill_report as fr
from antennaknobs.engines.momwire import MomwireEngine, clear_z_cache
from antennaknobs.web import adapter

HAVE_REPORT = fr.reads_fill_report(momwire.BSplineSolver)
SKIP_REASON = (
    "the installed momwire has no fill_report (momwire#2016): "
    "BSplineSolver.fill_report is missing"
)
needs_report = pytest.mark.skipif(not HAVE_REPORT, reason=SKIP_REASON)

YAGI = "beams.yagi"
# Rungs past the size reuse declines under in free space (N < 400), for the
# workbench's razor-2p; the engine-level ladder below is bspline's.
RUNGS = (81, 101)

# `antennaknobs.sweep` the module (the package also exports a `sweep` function).
sw = ar._sweep_module()


# --- the spec --------------------------------------------------------------


def test_the_four_metrics_and_their_units():
    assert [(m.name, m.unit) for m in an.FILL_METRICS] == [
        ("fill compression", "×"),
        ("fill time", "s"),
        ("factor time", "s"),
        ("fill share", "%"),
    ]
    with pytest.raises(ValueError, match="quantity is one of"):
        an.FillMetric("speedup")


def test_a_fill_metric_goes_to_data_and_code_and_back():
    for m in an.FILL_METRICS:
        assert an.from_data(an.to_data(m)) == m
        assert eval(an.to_code(an.MetricPlot(m)), {"an": an}) == an.MetricPlot(m)
    assert an.to_code(an.convergence()) == "an.convergence()"


def test_the_density_ladder_draws_them_and_nothing_else_does():
    a = an.convergence()
    plots = an.metric_plots(a)
    assert [p.metric for p in plots] == list(an.FILL_METRICS)
    assert all(ar._misfit(p, a) is None for p in plots)
    pattern = an.MetricPlot(an.PeakGain("gain"))
    assert ar._misfit(pattern, a) == ar._DENSITY_METRIC
    knob = an.knob("base")
    assert ar._misfit(an.MetricPlot(an.FILL_TIME), knob) == ar._FILL_OFF_DENSITY


# --- reading a report --------------------------------------------------------


def _report(**over):
    out = {
        "no_fill": False,
        "times": {"fill_s": 3.0, "factor_s": 1.0, "census_s": 0.5},
        "reuse": {
            "state": "served",
            "declined": None,
            "pairs": 100,
            "computed": 40,
            "near": 10,
        },
    }
    out.update(over)
    return out


@pytest.mark.parametrize(
    "quantity,value",
    [
        ("compression", 2.0),
        ("fill_time", 3.0),
        ("factor_time", 1.0),
        ("fill_share", 75.0),
    ],
)
def test_each_metric_off_a_served_report(quantity, value):
    assert fr.fill_metric_value(quantity, _report()) == (value, None)


def test_a_rung_that_cannot_say_has_no_value_and_says_why():
    assert fr.fill_metric_value("fill_time", None) == (
        None,
        "this engine does not report its fill",
    )
    off = _report(reuse=None)
    assert fr.fill_metric_value("compression", off) == (
        None,
        "fill reuse is off for this solve",
    )
    # Reuse off: the times stay.
    assert fr.fill_metric_value("fill_time", off) == (3.0, None)
    declined = _report(reuse={"state": "declined", "declined": "N < 400"})
    assert fr.fill_metric_value("compression", declined)[1] == (
        "fill reuse declined: N < 400"
    )
    assert fr.fill_metric_value("fill_share", _report(no_fill=True))[0] is None


# --- on a real ladder --------------------------------------------------------


def _factory(pair_reuse):
    def make(builder):
        return MomwireEngine(
            builder, solver=momwire.BSplineSolver, pair_reuse=pair_reuse
        )

    return make


def _ladder(pair_reuse, fills=None):
    builder = adapter.REGISTRY[YAGI].builder_cls()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sw._convergence_rows(
            builder, _factory(pair_reuse), RUNGS, "nominal_nsegs", fills=fills
        )


def test_reading_the_reports_leaves_the_ladder_unchanged():
    plain, _, _ = _ladder(True)
    fills: list = []
    read, _, _ = _ladder(True, fills)
    assert read == plain
    assert len(fills) == len(RUNGS)


@needs_report
def test_each_rung_equals_its_own_solvers_report():
    """The contract: the metric at a rung is momwire's `fill_report()` of
    that rung's solver."""
    builder = adapter.REGISTRY[YAGI].builder_cls()
    for n in RUNGS:
        builder.nominal_nsegs = n
        eng = _factory(True)(builder)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            eng.impedance()
        raw = eng._solved_cache[1][0].fill_report(wires=False)
        payload = eng.fill_report()
        reuse = raw["reuse"]
        assert reuse["state"] == "served", "this gate needs a served fill"
        compression, why = fr.fill_metric_value("compression", payload)
        assert why is None
        assert compression == reuse["pairs"] / (reuse["computed"] + reuse["near"])
        for quantity, key in (("fill_time", "fill_s"), ("factor_time", "factor_s")):
            assert fr.fill_metric_value(quantity, payload)[0] == raw["times"][key]


@needs_report
def test_reuse_off_drops_the_compression_and_keeps_the_times():
    fills: list = []
    _ladder(False, fills)
    for report in fills:
        assert fr.fill_metric_value("compression", report)[0] is None
        assert fr.fill_metric_value("fill_time", report)[0] > 0.0


# --- in the workbench ----------------------------------------------------------


def _records(client, metric, *, model="razor-2p", reuse=True, solver=None):
    req = {
        "geometry": YAGI,
        "param": "n_per_wire",
        "values": list(RUNGS),
        "metric": an.to_data(metric),
        "model_options": {"pair_reuse": reuse},
    }
    if solver is None:
        req.update(solver="momwire", momwire_model=model)
    else:
        req["solver"] = solver
    r = client.post("/param_sweep", json=req)
    assert r.status_code == 200, r.text
    import json

    return [json.loads(line) for line in r.text.splitlines()][:-1]


@needs_report
def test_the_density_sweep_carries_the_metric_per_rung():
    clear_z_cache()
    with TestClient(server.app) as client:
        recs = _records(client, an.FILL_COMPRESSION)
        times = _records(client, an.FILL_TIME, reuse=False)
        off = _records(client, an.FILL_COMPRESSION, reuse=False)
    assert all(rec["metric"] > 1.0 for rec in recs)
    assert all(rec["metric"] > 0.0 for rec in times)
    assert all(rec["metric_error"] == "fill reuse is off for this solve" for rec in off)


def test_another_engine_has_no_points():
    pytest.importorskip("PyNEC")
    with TestClient(server.app) as client:
        recs = _records(client, an.FILL_TIME, solver="pynec")
    assert recs and all("metric" not in rec for rec in recs)
    assert all(
        rec["metric_error"] == "this engine does not report its fill" for rec in recs
    )


def test_a_fill_metric_off_the_ladder_is_refused():
    with TestClient(server.app) as client:
        r = client.post(
            "/param_sweep",
            json={
                "geometry": YAGI,
                "solver": "momwire",
                "param": "base",
                "values": [7.0],
                "metric": an.to_data(an.FILL_TIME),
            },
        )
    assert r.status_code == 422
    assert "density ladder" in r.json()["detail"]


@pytest.mark.skipif(HAVE_REPORT, reason="this momwire reports its fill")
def test_at_the_recorded_pointer_every_rung_says_why():
    with TestClient(server.app) as client:
        recs = _records(client, an.FILL_TIME)
    assert all(
        rec["metric_error"] == "this engine does not report its fill" for rec in recs
    )
