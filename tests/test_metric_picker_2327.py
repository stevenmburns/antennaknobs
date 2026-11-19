"""The chart's metric picker, the server's half (AK#2327).

An analysis declaring several MetricPlots is served with all of them
(`metrics`), the first being `metric`, and `/param_sweep` reads every one off
each point's ONE solve when asked for a list (`metrics`), so the chart draws
another pick without sweeping again. A single `metric` request is unchanged.
"""

from __future__ import annotations

import json

import momwire
import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import fill_report as fr
from antennaknobs.cli import get_builder

INVVEE = "dipoles.invvee"
DX = an.ElevationWindow("DX gain", 2, 10, step=0.1)
PEAK = an.PeakGain("peak gain")
LF = (0.95, 1.0)

HAVE_REPORT = fr.reads_fill_report(momwire.BSplineSolver)


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


def _records(client, req) -> list[dict]:
    r = client.post("/param_sweep", json=req)
    assert r.status_code == 200, r.text
    return [json.loads(line) for line in r.text.splitlines() if line][:-1]


def _offered(client, name) -> dict:
    r = client.post("/analyses", json={"geometry": INVVEE, "variant": "default"})
    assert r.status_code == 200, r.text
    (e,) = [x for x in r.json()["analyses"] if x["name"] == name]
    return e["workbench"]


def test_convergence_serves_all_four_and_leaves_the_note_to_the_chart(client):
    w = _offered(client, "convergence")
    assert [m["name"] for m in w["metrics"]] == [m.name for m in an.FILL_METRICS]
    assert w["metric"] == w["metrics"][0]
    assert w["views"].count("Metric") == 1
    assert w["note"] is None


def test_several_pattern_metrics_are_served_and_read_off_one_solve(monkeypatch, client):
    """Not only convergence: any analysis with several MetricPlots."""
    a = an.Analysis(
        "two gains",
        an.Sweep("length_factor", values=LF),
        views=(an.MetricPlot(DX), an.MetricPlot(PEAK)),
    )
    monkeypatch.setattr(type(get_builder(INVVEE)()), "build_analyses", lambda self: [a])
    w = _offered(client, "two gains")
    assert [m["name"] for m in w["metrics"]] == ["DX gain", "peak gain"]
    base = {"geometry": INVVEE, "param": "length_factor", "values": list(LF)}
    both = _records(client, {**base, "metrics": [m["spec"] for m in w["metrics"]]})
    one = {
        m["name"]: _records(client, {**base, "metric": m["spec"]}) for m in w["metrics"]
    }
    for k, rec in enumerate(both):
        assert "metric" not in rec
        assert rec["metric_errors"] == [None, None]
        assert rec["metrics"] == [
            one["DX gain"][k]["metric"],
            one["peak gain"][k]["metric"],
        ]
        assert (rec["z_re"], rec["z_im"]) == (
            one["DX gain"][k]["z_re"],
            one["DX gain"][k]["z_im"],
        )


def test_a_single_metric_request_keeps_its_shape(client):
    rec = _records(
        client,
        {
            "geometry": INVVEE,
            "param": "length_factor",
            "values": [1.0],
            "metric": an.to_data(DX),
        },
    )[0]
    assert "metric" in rec and "metrics" not in rec and "metric_errors" not in rec


def test_metrics_and_metric_together_are_refused(client):
    r = client.post(
        "/param_sweep",
        json={
            "geometry": INVVEE,
            "param": "length_factor",
            "values": [1.0],
            "metric": an.to_data(DX),
            "metrics": [an.to_data(PEAK)],
        },
    )
    assert r.status_code == 422


def test_a_fill_metric_in_the_list_off_the_ladder_is_refused(client):
    r = client.post(
        "/param_sweep",
        json={
            "geometry": INVVEE,
            "param": "length_factor",
            "values": [1.0],
            "metrics": [an.to_data(DX), an.to_data(an.FILL_TIME)],
        },
    )
    assert r.status_code == 422


def test_the_ladder_reads_all_four_each_with_its_own_reason(client):
    recs = _records(
        client,
        {
            "geometry": INVVEE,
            "solver": "momwire",
            "momwire_model": "bspline",
            "model_options": {"pair_reuse": False},
            "param": "n_per_wire",
            "values": [12, 17],
            "metrics": [an.to_data(m) for m in an.FILL_METRICS],
        },
    )
    for rec in recs:
        values, whys = rec["metrics"], rec["metric_errors"]
        assert len(values) == len(whys) == 4
        if HAVE_REPORT:
            # Reuse off: no compression, and why; the times stay.
            assert values[0] is None and whys[0] == "fill reuse is off for this solve"
            assert all(v is not None and v >= 0.0 for v in values[1:])
            assert whys[1:] == [None, None, None]
        else:
            # The recorded pointer: nothing to read, and every metric says so.
            assert values == [None] * 4
            assert whys == ["this engine does not report its fill"] * 4
