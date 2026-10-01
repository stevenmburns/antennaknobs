"""AK#1828, sweep framework step 8 unit 2: ``an.MetricPlot(metric,
relative_to=)``, a metric against the swept x, one far-field cut per sweep
point (docs/design/sweep-framework-step8-metrics.md § 3).

- the spec: it prints back and round-trips through data; it is a swept view
  (refused on a pattern, a map); a ``relative_to`` that names no cell, or
  several on one axis, is refused by name when listed;
- the CLI: each point's value IS the metric read off that point's own
  engine (an oracle per point), a reference whose state sets the swept knob
  is FIXED (solved once, counted), each curve's difference is its value
  less its own reference's, paired per engine when the cross names
  several, and ``--csv`` carries the columns at full precision;
- the workbench: ``/analyses`` serves the Metric view, the metric's data
  and which cells are references (and fixed, with their one value);
  ``/param_sweep`` with ``metric`` reads it off each point's own solve;
- THE GATE: a MetricPlot chart solved through the workbench's own endpoints
  and kept as a study (``POST /studies/save``) reruns through ``analyze
  --study`` BIT-EQUAL: every point, the fixed reference, every difference.
"""

from __future__ import annotations

import csv
import json

import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import metrics as mx
from antennaknobs import studies
from antennaknobs.cli import cli, get_builder, make_engine_factory, parse_ground
from antennaknobs.web.analyses_offer import builder_for
from antennaknobs.web.examples import example_for

INVVEE = "dipoles.invvee"
BSPLINE = "momwire:bspline"
RAZOR = "momwire:razor-2p"
N = 15
DX = an.ElevationWindow("DX gain", 2, 10, step=0.1)
LF = (0.95, 1.0)


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """An empty studies folder with the trust gate ACTIVE."""
    root = tmp_path / "studies"
    root.mkdir()
    monkeypatch.setenv("ANTENNAKNOBS_STUDIES_DIR", str(root))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_FILE", raising=False)
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path / "designs"))
    return root


def _record(monkeypatch, module, name):
    calls = []
    inner = getattr(module, name)

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        calls.append((args, kwargs, out))
        return out

    monkeypatch.setattr(module, name, wrapped)
    return calls


def _offer(monkeypatch, analyses):
    monkeypatch.setattr(
        type(get_builder(INVVEE)()), "build_analyses", lambda self: list(analyses)
    )


def _dx_analysis(**kw) -> an.Analysis:
    """DX gain against length_factor, the as-built invvee and the dipole
    variant against a FIXED reference: its state sets the swept knob."""
    return an.Analysis(
        **{
            "name": "dx",
            "sweep": an.Sweep("length_factor", values=LF),
            "cross": an.Cross(
                states=(
                    an.State("as built"),
                    an.State("ref", length_factor=1.05),
                )
            ),
            "views": (an.MetricPlot(DX, relative_to="ref"),),
            **kw,
        }
    )


# ── the spec ──────────────────────────────────────────────────────────────


def test_a_metric_plot_prints_back_and_round_trips_through_data():
    a = _dx_analysis()
    assert eval(an.to_code(a), {"an": an}) == a
    assert an.from_data(an.to_data(a)) == a
    assert an.to_code(an.MetricPlot(DX)) == (
        'an.MetricPlot(an.ElevationWindow("DX gain", 2, 10, step=0.1))'
    )


def test_a_metric_plot_is_a_swept_view():
    with pytest.raises(ValueError, match="draws against a swept x"):
        an.patterns(name="p", views=(an.MetricPlot(DX),))
    with pytest.raises(TypeError, match="metric is a metric"):
        an.MetricPlot("DX gain")
    with pytest.raises(TypeError, match="relative_to names a cell"):
        an.MetricPlot(DX, relative_to="")
    pair = an.Analysis(
        "map", (an.Sweep("base"), an.Sweep("length_factor")), views=(an.MetricPlot(DX),)
    )
    assert "a two-sweep map" in ar.cli_gaps(pair)[0]
    ladder = an.convergence(views=(an.MetricPlot(DX),))
    assert "density ladder" in ar.cli_gaps(ladder)[0]


def test_a_reference_that_names_no_cell_or_several_is_refused_by_name():
    b = get_builder(INVVEE)()
    nothing = _dx_analysis(views=(an.MetricPlot(DX, relative_to="vertical"),))
    probs = an.problems(nothing, b)
    # Named nothing, so "ref" is no reference: its swept knob is refused too.
    assert len(probs) == 2
    assert "is relative to 'vertical', and no state, design or cell" in probs[1]
    assert "sets length_factor, which the analysis sweeps" in probs[0]
    both = an.Analysis(
        "two",
        an.Sweep("base", values=(5.0, 7.0)),
        cross=an.Cross(designs=(INVVEE, "dipoles.invvee_apex")),
        views=(an.MetricPlot(DX, relative_to="dipoles.invvee"),),
    )
    assert an.problems(both, b) == []
    # The fixed reference's state sets the swept knob, and is not refused
    # for it: a state that is no reference still is.
    assert an.problems(_dx_analysis(), b) == []
    plain = _dx_analysis(views=(an.MetricPlot(DX),))
    assert "sets length_factor, which the analysis sweeps" in an.problems(plain, b)[0]


# ── the CLI ───────────────────────────────────────────────────────────────


def _engine(engine=BSPLINE, ground=None, **knobs):
    b = get_builder(INVVEE)()
    for k, v in knobs.items():
        setattr(b, k, v)
    g = parse_ground(ground) if ground else None
    return make_engine_factory(engine, g, nominal_nsegs=N)(b)


def test_each_point_is_the_metric_off_its_own_engine_and_a_fixed_reference_once(
    monkeypatch, capsys, tmp_path
):
    _offer(monkeypatch, [_dx_analysis(ground="finite")])
    runs = _record(monkeypatch, ar, "_run_metric_plots")
    values = _record(monkeypatch, ar, "_metric_values")
    out = tmp_path / "dx.csv"
    cli(["analyze", "--builder", INVVEE, "--analysis", "dx", "--engine", BSPLINE,
         "--nominal-nsegs", str(N), "--csv", str(out),
         "--fn", str(tmp_path / "dx.png")])  # fmt: skip
    printed = capsys.readouterr().out
    assert "fixed reference, solved once" in printed
    (_args, _kw, (got, _cols)) = runs[-1]
    per = got["DX gain"]
    assert list(per) == ["as built", "ref"]
    # The reference solved ONCE (its own call, no x), the curve at each x.
    assert sorted(len(c[2][0]) for c in values) == [0, len(LF)]
    ref = per["ref"]
    assert ref.fixed and ref.xs == () and ref.reference == "ref"
    assert ref.values == (mx.evaluate(DX, mx.source_for(_engine(
        ground="finite", length_factor=1.05))),)  # fmt: skip
    curve = per["as built"]
    assert curve.xs == LF and curve.reference == "ref"
    for k, x in enumerate(LF):
        src = mx.source_for(_engine(ground="finite", length_factor=x))
        assert curve.values[k] == mx.evaluate(DX, src)
        assert curve.relative[k] == curve.values[k] - ref.values[0]
    # Adversarial: the lengths read different DX gains.
    assert curve.values[0] != curve.values[1]
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == [
        "length_factor",
        "as built DX gain (dBi)",
        "as built DX gain vs ref (dB)",
    ]
    assert [float(r[1]) for r in rows[1:]] == list(curve.values)
    assert [float(r[2]) for r in rows[1:]] == list(curve.relative)
    assert (tmp_path / "dx.png").is_file()


def test_each_curve_is_relative_to_the_reference_on_its_own_engine():
    a = _dx_analysis(
        cross=(
            an.Cross(
                states=(an.State("as built"), an.State("ref", length_factor=1.05))
            ),
            an.Cross(engines=(BSPLINE, RAZOR)),
        )
    )
    cells = ar.cells(a, BSPLINE)
    refs = ar.references(a, an.metric_plots(a)[0], cells)
    assert refs == {
        f"as built, {BSPLINE}": f"ref, {BSPLINE}",
        f"as built, {RAZOR}": f"ref, {RAZOR}",
        f"ref, {BSPLINE}": f"ref, {BSPLINE}",
        f"ref, {RAZOR}": f"ref, {RAZOR}",
    }


def test_a_metric_plot_beside_rx_solves_both_and_the_reference_stays_out_of_rx(
    monkeypatch, capsys, tmp_path
):
    _offer(
        monkeypatch,
        [_dx_analysis(views=(an.Rx(), an.MetricPlot(DX, relative_to="ref")))],
    )
    runs = _record(monkeypatch, ar, "run")
    cli(["analyze", "--builder", INVVEE, "--analysis", "dx", "--engine", BSPLINE,
         "--nominal-nsegs", str(N), "--fn", str(tmp_path / "rx.png")])  # fmt: skip
    capsys.readouterr()
    got = runs[-1][2]
    # R/X has no fixed reference (its state sets the swept knob): refused
    # there by name, drawn on the metric plot.
    assert list(got["curves"]) == ["as built"]
    assert set(got["metrics"]["DX gain"]) == {"as built", "ref"}
    assert (tmp_path / "rx-metrics.png").is_file()


# ── the workbench ─────────────────────────────────────────────────────────


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


def _lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _entry(client, name: str) -> dict:
    r = client.post("/analyses", json=_req())
    assert r.status_code == 200, r.text
    (e,) = [x for x in r.json()["analyses"] if x["name"] == name]
    return e


def test_analyses_serves_the_metric_view_and_the_reference(monkeypatch, client):
    _offer(monkeypatch, [_dx_analysis()])
    w = _entry(client, "dx")["workbench"]
    assert w["runs"] is True and w["kind"] == "knob"
    assert w["views"] == ["Metric"]
    assert w["metric"] == {
        "name": "DX gain",
        "unit": "dBi",
        "relative_to": "ref",
        "relative_unit": "dB",
        "spec": an.to_data(DX),
    }
    built, ref = w["states"]
    assert (built["reference"], built["fixed"], built["values"]) == (
        False,
        False,
        [0.95, 1.0],
    )
    assert (ref["reference"], ref["fixed"], ref["refused"]) == (True, True, None)
    assert (ref["param"], ref["values"]) == ("length_factor", [1.05])


def test_param_sweep_reads_the_metric_off_each_points_own_solve(client):
    r = client.post("/param_sweep", json={**_req(), "param": "length_factor",
                                          "values": list(LF), "metric": an.to_data(DX)})  # fmt: skip
    assert r.status_code == 200, r.text
    recs = _lines(r.text)[:-1]
    for rec, x in zip(recs, LF, strict=True):
        src = mx.source_for(_engine(length_factor=x))
        assert rec["metric"] == mx.evaluate(DX, src)
    # A request without one keeps its records' old shape.
    plain = _lines(client.post("/param_sweep", json={**_req(), "param": "length_factor",
                                                     "values": [1.0]}).text)  # fmt: skip
    assert "metric" not in plain[0] and "metric_error" not in plain[0]
    bad = client.post("/param_sweep", json={**_req(), "param": "length_factor",
                                            "values": [1.0], "metric": {"an": "Sweep"}})  # fmt: skip
    assert bad.status_code == 422 and "bad metric" in bad.json()["detail"]


# ── THE GATE: keeping a MetricPlot chart reruns it bit-equal ──────────────


def test_a_kept_metric_plot_chart_reruns_bit_equal(
    monkeypatch, capsys, tmp_path, client, folder
):
    """The chart as the workbench draws it: each cell's sweep through
    ``/param_sweep`` with the served metric, on the request the chart builds
    for that cell (the fixed reference at its one value); kept through
    ``POST /studies/save``; found; and run by ``analyze --study``. Every
    point, the reference and every difference: ``==``."""
    _offer(monkeypatch, [_dx_analysis()])
    e = _entry(client, "dx")
    w = e["workbench"]
    built_state, ref_state = w["states"]
    drawn = {}
    for st in (built_state, ref_state):
        req = {**_req(), **st["knobs"]}
        r = client.post("/param_sweep", json={**req, "param": st["param"],
                                              "values": st["values"],
                                              "metric": w["metric"]["spec"]})  # fmt: skip
        assert r.status_code == 200, r.text
        recs = _lines(r.text)[:-1]
        assert [x["value"] for x in recs] == st["values"]
        drawn[st["name"]] = (req, [x["metric"] for x in recs])
    body = {
        "origin": "chart",
        "form": "study",
        "name": "kept dx",
        "spec": e["spec"],
        "tab": _req(),
        "cells": [drawn["as built"][0], drawn["ref"][0]],
    }
    r = client.post("/studies/save", json={**body, "path": "kept"})
    assert r.status_code == 200, r.text
    (st,) = [s for s in studies.discover().studies if s.source == "kept"]
    assert an.metric_plots(st.analysis) == (an.MetricPlot(DX, relative_to="ref"),)

    runs = _record(monkeypatch, ar, "_run_metric_plots")
    cli(["analyze", "--study", "kept", "--nominal-nsegs", str(N),
         "--fn", str(tmp_path / "kept.png")])  # fmt: skip
    capsys.readouterr()
    per = runs[-1][2][0]["DX gain"]
    (built,) = [c for label, c in per.items() if label.endswith("as built")]
    (ref,) = [c for label, c in per.items() if label.endswith("ref")]
    assert built.xs == LF
    assert list(built.values) == drawn["as built"][1]
    assert ref.fixed and list(ref.values) == drawn["ref"][1]
    assert list(built.relative) == [
        v - drawn["ref"][1][0] for v in drawn["as built"][1]
    ]
