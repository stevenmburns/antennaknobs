"""AK#1828, sweep framework step 8 unit 3: the CALLABLE metric,
``an.Metric(name, fn, over="elevation"|"azimuth", step=, az=)``
(docs/design/sweep-framework-step8-metrics.md § 2).

- ``fn(cut: an.Cut) -> float`` is a NAMED MODULE-LEVEL function: a lambda, a
  nested function and a method are refused by name;
- ``to_code`` writes it by reference, ``module.qualname``, and `an.imports`
  gives the import; one that cannot be imported by name (a user design's or
  study's, loaded by path) is written by its bare name, and keep writes a
  comment saying to copy it;
- data never names a function into existence: `from_data` resolves one only
  through the functions the workbench served, and ``/param_sweep`` and
  ``/keep`` refuse any other by name;
- the hosted instance offers no callable metric but the catalog's;
- THE GATE: a callable written to equal ``ElevationWindow(2, 10, step=0.1,
  mean="power")`` gives ``==`` numbers on the same pattern, at a fixed
  azimuth, at ``PEAK_AZ`` and at ``MEAN_AZ``.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import keep
from antennaknobs import metrics as mx
from antennaknobs.cli import cli, get_builder, make_engine_factory, parse_ground
from antennaknobs.web import analyses_offer
from antennaknobs.web.analyses_offer import builder_for
from antennaknobs.web.examples import example_for

INVVEE = "dipoles.invvee"
ENGINE = "momwire:bspline"
N = 15
WINDOW = an.ElevationWindow("DX gain", 2, 10, step=0.1)


# The functions under test: module level, by name, as the rule wants.


def dx_gain(cut):
    """M0AGP's DX gain written by hand: the power mean of the cut, in dB."""
    lin = 10 ** (cut.gain_dbi / 10)
    return 10 * np.log10(lin.mean())


def dx_gain_filtered(cut):
    """The same, on a whole 0..90 cut, keeping 2..10 itself."""
    keep_ = (cut.el >= 2) & (cut.el <= 10)
    lin = 10 ** (cut.gain_dbi[keep_] / 10)
    return 10 * np.log10(lin.mean())


def vertical_share(cut):
    """The vertically polarised share of the power over the cut, in dB."""
    v = 10 ** (cut.gain_v_dbi / 10)
    t = 10 ** (cut.gain_dbi / 10)
    return 10 * np.log10(v.sum() / t.sum())


def ring_ratio(cut):
    """The azimuth ring's peak over its mean, in dB."""
    lin = 10 ** (cut.gain_dbi / 10)
    return 10 * np.log10(lin.max() / lin.mean())


class _Holder:
    @staticmethod
    def method(cut):
        return 0.0


def _outer():
    def inner(cut):
        return 0.0

    return inner


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


@pytest.fixture(scope="module")
def source():
    b = get_builder(INVVEE)()
    eng = make_engine_factory(ENGINE, parse_ground("finite"), nominal_nsegs=N)(b)
    return mx.source_for(eng)


def _dx(**kw) -> an.Metric:
    return an.Metric("DX gain", dx_gain, lo=2, hi=10, step=0.1, **kw)


# ── the function rule ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fn, words",
    [
        (lambda cut: 0.0, "fn is a lambda"),
        (_outer(), "defined inside another function or a class"),
        (_Holder.method, "defined inside another function or a class"),
        (len, "named module-level function"),
        ("dx_gain", "named module-level function"),
    ],
)
def test_only_a_named_module_level_function_is_a_metric(fn, words):
    with pytest.raises(TypeError, match=words):
        an.Metric("m", fn)


@pytest.mark.parametrize(
    "kw, words",
    [
        ({"over": "pattern"}, "not in v1"),
        ({"over": "azimuth"}, "needs el="),
        ({"over": "azimuth", "el": 10, "az": 30}, "an elevation cut's"),
        ({"over": "azimuth", "el": 90}, "the zenith"),
        ({"el": 10}, "an azimuth cut's elevation"),
        ({"lo": 2, "hi": 10, "step": 0.3}, "does not divide"),
        ({"az": 400}, "0 <= az < 360"),
    ],
)
def test_a_callable_that_cannot_cut_a_pattern_is_refused_by_name(kw, words):
    with pytest.raises((TypeError, ValueError), match=words):
        an.Metric("m", dx_gain, **kw)


def test_to_code_writes_the_function_by_reference_with_its_import():
    m = _dx(az=an.MEAN_AZ)
    ref = f"{__name__}.dx_gain"
    assert m.ref == ref
    code = an.to_code(m)
    assert code.startswith("an.Metric(") and f"{ref}," in code
    assert "lambda" not in code
    assert an.imports(m) == [f"import {__name__}"]
    # eval of the text, with the module the import names, is the value.
    top = __name__.split(".")[0]
    names = {"an": an, top: sys.modules[top]}
    assert eval(code, names) == m
    a = an.patterns(name="p", views=(an.PatternTable(metrics=(m,)),))
    text = an.code_with_imports(a)
    assert text.startswith(f"import {__name__}\n\n")
    assert eval(an.to_code(a), names) == a


def test_a_function_that_cannot_be_imported_by_name_is_written_bare():
    def mine(cut):
        return 0.0

    mine.__qualname__ = "mine"
    mine.__module__ = "antennaknobs._user_studies.feeds__m0agp"
    m = an.Metric("mine", mine)
    assert not an.importable(mine) and not an.is_catalog_function(mine)
    assert an.to_code(m) == 'an.Metric("mine", mine)'
    assert an.imports(m) == []
    a = an.patterns(name="p", views=(an.PatternTable(metrics=(m,)),))
    text = keep.render(a, form="study", origin="chart")
    assert "# The metric 'mine' calls mine() from " in text
    assert "copy the function into this file" in text
    assert 'an.Metric("mine", mine)' in text
    analysis = keep.render(a, form="analysis", origin="chart")
    assert "copy the function into this file" in analysis


def test_a_kept_importable_callable_is_written_with_its_import_and_execs():
    a = an.patterns(name="p", views=(an.PatternTable(metrics=(_dx(),)),))
    text = keep.render(a, form="study", origin="chart")
    assert f"import antennaknobs.analyses as an\nimport {__name__}\n" in text
    assert "copy the function" not in text
    ns: dict = {}
    exec(text, ns)
    assert ns["build_studies"]() == [a]


# ── data never names a function into existence ────────────────────────────


def test_from_data_resolves_only_a_served_function():
    m = _dx()
    data = an.to_data(m)
    assert data["fn"] == f"{__name__}.dx_gain"
    assert json.loads(json.dumps(data)) == data
    assert an.from_data(data, {m.ref: dx_gain}) == m
    with pytest.raises(ValueError, match="not a function this workbench served"):
        an.from_data(data)
    forged = {**data, "fn": "os.system"}
    with pytest.raises(ValueError, match="'os.system', which is not a function"):
        an.from_data(forged, {m.ref: dx_gain})
    # Equal by reference: the same function, whatever object holds it.
    assert an.Metric("DX gain", dx_gain, lo=2, hi=10, step=0.1) == m
    assert an.Metric("DX gain", dx_gain_filtered, lo=2, hi=10, step=0.1) != m


# ── THE GATE: a callable equal to the window is == on the same pattern ────


@pytest.mark.parametrize("az", [an.PEAK_AZ, an.MEAN_AZ, 0, 90, 37.5])
def test_a_callable_written_to_equal_the_window_is_equal(source, az):
    window = mx.evaluate(an.ElevationWindow("w", 2, 10, step=0.1, az=az), source)
    m = an.Metric("DX gain", dx_gain, lo=2, hi=10, step=0.1, az=az)
    cut = mx.cut_for(m, source)
    assert np.array_equal(cut.el, mx.angle_grid(2, 10, 0.1))
    assert mx.evaluate(m, source) == window
    # Adversarial: the gate can fail. A different window is not equal.
    other = an.Metric("DX gain", dx_gain, lo=2, hi=12, step=0.1, az=az)
    assert mx.evaluate(other, source) != window


def test_a_callable_over_the_whole_cut_filters_to_the_same_angles(source):
    """The note's own example cuts 0..90 and filters 2..10 in the function:
    the angles it keeps are exactly the window's (the grid is rounded to
    1e-9 degree), and the number agrees to rounding."""
    whole = an.Metric("DX", dx_gain_filtered, step=0.1, az=0)
    cut = mx.cut_for(whole, source)
    kept = cut.el[(cut.el >= 2) & (cut.el <= 10)]
    assert np.array_equal(kept, mx.angle_grid(2, 10, 0.1))
    window = mx.evaluate(an.ElevationWindow("w", 2, 10, step=0.1, az=0), source)
    assert mx.evaluate(whole, source) == pytest.approx(window, abs=1e-9)


# ── the Cut contract ──────────────────────────────────────────────────────


def test_the_cut_carries_angles_gains_frequency_and_its_fixed_angle(source):
    cut = mx.cut_for(an.Metric("v", vertical_share, step=1.0), source)
    assert cut.over == "elevation" and list(cut.el) == list(np.arange(0.0, 91.0))
    assert cut.freq_mhz == 28.47
    # PEAK_AZ resolved to the table's azimuth; MEAN_AZ cuts nothing.
    assert cut.fixed_deg == source.table()["azimuth_deg"]
    mean = mx.cut_for(an.Metric("v", vertical_share, az=an.MEAN_AZ), source)
    assert mean.fixed_deg is None
    total = 10 * np.log10(10 ** (cut.gain_v_dbi / 10) + 10 ** (cut.gain_h_dbi / 10))
    # Above the horizon (over ground the horizon is a null at the -300 dB
    # floor, where each part is floored on its own).
    assert np.allclose(total[1:], cut.gain_dbi[1:], atol=1e-9)
    with pytest.raises(AttributeError, match="cut.el"):
        _ = cut.az
    ring = mx.cut_for(an.Metric("r", ring_ratio, over="azimuth", el=15), source)
    assert ring.over == "azimuth" and list(ring.az) == list(np.arange(0.0, 360.0))
    assert ring.fixed_deg == 15.0
    # The invvee is broadside: the ring's peak is well over its mean.
    assert mx.evaluate(an.Metric("r", ring_ratio, over="azimuth", el=15), source) > 1


# ── the CLI ───────────────────────────────────────────────────────────────


def _offer(monkeypatch, analyses):
    monkeypatch.setattr(
        type(get_builder(INVVEE)()), "build_analyses", lambda self: list(analyses)
    )


def test_analyze_runs_a_callable_in_a_table_and_a_metric_plot(
    monkeypatch, capsys, tmp_path
):
    table = an.patterns(
        name="t", views=(an.PatternTable(metrics=(_dx(),)),), ground="finite"
    )
    plot = an.Analysis(
        "plot",
        an.Sweep("base", values=(7.0, 12.0)),
        views=(an.MetricPlot(_dx()),),
        ground="finite",
    )
    _offer(monkeypatch, [table, plot])
    pats = []
    inner = ar._run_patterns

    def rec(*a, **k):
        out = inner(*a, **k)
        pats.append(out)
        return out

    monkeypatch.setattr(ar, "_run_patterns", rec)
    cli(["analyze", "--builder", INVVEE, "--analysis", "t", "--engine", ENGINE,
         "--nominal-nsegs", str(N), "--fn", "/dev/null"])  # fmt: skip
    (cell,) = pats[-1]["patterns"].values()
    b = get_builder(INVVEE)()
    src = mx.source_for(
        make_engine_factory(ENGINE, parse_ground("finite"), nominal_nsegs=N)(b)
    )
    assert cell.values == {"DX gain": mx.evaluate(WINDOW, src)}
    capsys.readouterr()
    cli(["analyze", "--builder", INVVEE, "--analysis", "plot", "--code"])
    code = capsys.readouterr().out
    assert code.startswith(f"import {__name__}\n")
    cli(["analyze", "--builder", INVVEE, "--analysis", "plot", "--engine", ENGINE,
         "--nominal-nsegs", str(N), "--fn", str(tmp_path / "p.png")])  # fmt: skip
    assert "== DX gain (dBi) vs base" in capsys.readouterr().out


# ── the workbench, and the hosted instance ────────────────────────────────


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


def _plot() -> an.Analysis:
    return an.Analysis(
        "callable plot",
        an.Sweep("length_factor", values=(0.95, 1.0)),
        views=(an.MetricPlot(_dx()),),
    )


def test_the_local_workbench_serves_and_runs_a_callable(monkeypatch, client):
    monkeypatch.setattr(analyses_offer, "SERVED_FUNCTIONS", {})
    _offer(monkeypatch, [_plot()])
    r = client.post("/analyses", json=_req())
    (e,) = [x for x in r.json()["analyses"] if x["name"] == "callable plot"]
    w = e["workbench"]
    assert w["runs"] is True and w["views"] == ["Metric"]
    assert e["code"].startswith(f"import {__name__}\n")
    assert analyses_offer.SERVED_FUNCTIONS == {f"{__name__}.dx_gain": dx_gain}
    r = client.post("/param_sweep", json={**_req(), "param": "length_factor",
                                          "values": [1.0], "metric": w["metric"]["spec"]})  # fmt: skip
    assert r.status_code == 200, r.text
    rec = json.loads(r.text.splitlines()[0])
    b = get_builder(INVVEE)()
    b.length_factor = 1.0
    src = mx.source_for(make_engine_factory(ENGINE, None, nominal_nsegs=N)(b))
    assert rec["metric"] == mx.evaluate(WINDOW, src)
    # A function it never served is refused by name, never imported.
    forged = {**w["metric"]["spec"], "fn": "os.system"}
    r = client.post("/param_sweep", json={**_req(), "param": "length_factor",
                                          "values": [1.0], "metric": forged})  # fmt: skip
    assert r.status_code == 422 and "not a function this workbench served" in r.text
    # Keep reads it back through the same served functions.
    out = client.post("/keep", json={"origin": "chart", "form": "study",
                                     "spec": e["spec"], "tab": _req()}).json()  # fmt: skip
    assert f"import {__name__}" in out["code"]


def test_the_hosted_instance_offers_no_callable_but_the_catalogs(monkeypatch, client):
    from antennaknobs.web import server

    monkeypatch.setattr(analyses_offer, "SERVED_FUNCTIONS", {})
    monkeypatch.setattr(server, "_HOSTED", True)
    _offer(monkeypatch, [_plot()])
    r = client.post("/analyses", json=_req())
    (e,) = [x for x in r.json()["analyses"] if x["name"] == "callable plot"]
    assert e["workbench"]["runs"] is False
    assert "runs only on a local workbench" in e["workbench"]["why"]
    assert analyses_offer.SERVED_FUNCTIONS == {}
    # So its data cannot be run there either.
    r = client.post("/param_sweep", json={**_req(), "param": "length_factor",
                                          "values": [1.0],
                                          "metric": an.to_data(_dx())})  # fmt: skip
    assert r.status_code == 422

    # The catalog's own (ours) is offered hosted.
    def catalog_dx(cut):
        return dx_gain(cut)

    catalog_dx.__qualname__ = "catalog_dx"
    catalog_dx.__module__ = "antennaknobs.studies.fake"
    assert an.is_catalog_function(catalog_dx)
    a = an.Analysis(
        "catalog plot",
        an.Sweep("length_factor", values=(1.0,)),
        views=(an.MetricPlot(an.Metric("DX", catalog_dx, lo=2, hi=10, step=0.1)),),
    )
    w = analyses_offer.workbench(a, builder_for(example_for(INVVEE).builder_cls, _req()),
                                 _req(), hosted=True)  # fmt: skip
    assert w["runs"] is True
    assert analyses_offer.hosted_refusal(a) is None
