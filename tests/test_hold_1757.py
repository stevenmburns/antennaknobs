"""Holds: the optimizer at every sweep point (AK#1757, sweep-framework step 6).

docs/design/sweep-framework-step6.md is the design note. The gates here:

1. THE SEAM. A held point's knobs and Z equal the workbench's optimizer run
   standalone at that x from the same start, bit for bit, through the
   production path the analysis run uses (``antennaknobs analyze`` and the
   workbench's ``/param_sweep``), never a fixture built here. Every point is
   recorded where the production path makes it (``hold.hold_point``), and
   the branch each point took (cold or warm; secant, warm Newton, seeded
   Newton) is COUNTED, so a gate that never reached a branch says so.
2. E8 and E9 run: every E9 point's X and every held E8 point's |Z - 50| are
   within the optimizer's own tolerance, and the warm-started knobs move
   smoothly.
3. A FORCED non-convergence (a ui_params range the root leaves) is drawn as
   gaps with reasons and the documented recovery, never as values.
4. A held chart kept as a study re-solves to the chart, bit for bit, through
   the chart keep and through pins.

Python tests here run on a big box, never the laptop (one runaway test
OOM-killed a session): each CLI run is tens of small solves.
"""

from __future__ import annotations

import itertools
import json
from collections import Counter
from types import MappingProxyType

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import hold as hd
from antennaknobs import studies
from antennaknobs.cli import (
    _GROUND_UNSET,
    cli,
    get_builder,
    make_engine_factory,
    resolve_ground,
)
from antennaknobs.web.analyses_offer import builder_for
from antennaknobs.web.examples import example_for
from antennaknobs.web.optimize import _ROOT_FTOL, optimize

INVVEE = "dipoles.invvee"
E8 = "match vs height"
E9 = "resonance vs angle"
N = 15


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    root = tmp_path / "studies"
    root.mkdir()
    monkeypatch.setenv("ANTENNAKNOBS_STUDIES_DIR", str(root))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_FILE", raising=False)
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path / "designs"))
    return root


def _record(monkeypatch, module, name):
    """Every call of ``module.name`` and what it returned. The list is only
    READ after the run: nothing loops over it while calling the spied
    function."""
    calls = []
    inner = getattr(module, name)

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        calls.append((args, kwargs, out))
        return out

    monkeypatch.setattr(module, name, wrapped)
    return calls


def _analyze(monkeypatch, capsys, tmp_path, name, *extra) -> tuple[dict, str]:
    runs = _record(monkeypatch, ar, "run")
    cli(["analyze", "--builder", INVVEE, "--analysis", name,
         "--fn", str(tmp_path / "chart.png"), *extra])  # fmt: skip
    out = capsys.readouterr().out
    return runs[-1][2], out


def _req(design=INVVEE, **knobs) -> dict:
    """A workbench solve request at the design's defaults (the keep tests'
    shape): every knob a field, the two frequencies, B-spline at N, free."""
    cls = example_for(design).builder_cls
    b = builder_for(cls, {"geometry": design, "variant": "default"})
    values = {
        k: v
        for k, v in an._params(b).items()
        if k not in ("ui_params", "nominal_nsegs", "freq", "design_freq")
    }
    return {
        "geometry": design,
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


def _standalone_cli_solve(ground_arg):
    """The CLI's knob solve, built here independently of `hold`: a fresh
    registry builder and engine factory, each request's knobs set on it and
    solved as ``sweep._solve_at`` solves a point."""
    b = get_builder(INVVEE)()
    factory = make_engine_factory("momwire", resolve_ground(ground_arg, type(b)))

    def solve(req):
        for k, v in req.items():
            setattr(b, k, v)
        z = complex(factory(b).impedance()[0])
        return {"z_in_re": z.real, "z_in_im": z.imag, "z0_ohms": 50.0}

    return solve


def _check_seam(points, standalone) -> Counter:
    """Each recorded point re-run standalone from its own start: ``==``.
    Returns the branch counts."""
    branches: Counter = Counter()
    for args, kwargs, (req, res) in points:
        x, knob, start, free, objective = args
        warm = kwargs["warm"]
        branches["warm" if warm else "cold"] += 1
        branches[res["method"]] += 1
        alone = optimize(
            {knob: x, **start},
            [dict(f) for f in free],
            objective,
            solve_fn=standalone,
            warm=warm,
            fallback=False,
        )
        assert req == {knob: x, **start}
        assert alone["params"] == res["params"]
        assert alone["metrics_after"]["z_in_re"] == res["metrics_after"]["z_in_re"]
        assert alone["metrics_after"]["z_in_im"] == res["metrics_after"]["z_in_im"]
        assert alone["method"] == res["method"]
    return branches


# ── 1. the seam ───────────────────────────────────────────────────────────


def test_e9_cli_points_are_the_optimizer_standalone_bit_equal(
    monkeypatch, capsys, tmp_path
):
    points = _record(monkeypatch, hd, "hold_point")
    cells = _record(monkeypatch, ar, "hold_cell")
    got, out = _analyze(monkeypatch, capsys, tmp_path, E9)
    # The held branch of the production run made the one curve, 25 points.
    assert len(cells) == 1 and len(points) == 25
    (pts,) = got["held"].values()
    assert [p.x for p in pts] == list(np.linspace(0, 60, 25))
    branches = _check_seam(points, _standalone_cli_solve(_GROUND_UNSET))
    # One cold start (the first point), then warm; the scalar secant all along.
    assert branches["cold"] == 1 and branches["warm"] == 24, branches
    assert branches["secant"] + branches["bracket-brent"] == 25, branches
    # The point a curve draws is the recorded optimum's own Z.
    for (_a, _k, (_req, res)), p in zip(points, pts, strict=True):
        m = res["metrics_after"]
        assert p.z == complex(m["z_in_re"], m["z_in_im"]) and p.params == res["params"]
    print("E9 seam branches:", dict(branches))


# 37 two-knob Newton points (~5 s): main-only. The PR lane keeps the hold seam
# through E9's CLI test and the workbench test below.
@pytest.mark.antenna_computation_check
def test_e8_cli_points_are_the_optimizer_standalone_bit_equal(
    monkeypatch, capsys, tmp_path
):
    points = _record(monkeypatch, hd, "hold_point")
    got, _out = _analyze(monkeypatch, capsys, tmp_path, E8, "--ground", "finite-fast")
    branches = _check_seam(points, _standalone_cli_solve("finite-fast"))
    # The two-knob Newton ran WARM, from the previous point, and the seeded
    # path ran for the cold starts: both branches were reached.
    assert branches["warm newton"] > 20, branches
    assert branches["cold"] >= 1, branches
    print("E8 seam branches:", dict(branches))


def test_workbench_points_are_the_optimizer_standalone_bit_equal(monkeypatch, client):
    from antennaknobs.web import server

    points = _record(monkeypatch, hd, "hold_point")
    streams = _record(monkeypatch, server, "_held_sweep_stream")
    plain = _record(monkeypatch, server, "_param_sweep_stream")
    entry = _entry(client, E9)
    w = entry["workbench"]
    req = _req()
    r = client.post(
        "/param_sweep",
        json={
            **req,
            "param": w["param"],
            "values": w["values"],
            "hold": w["hold"]["spec"],
        },
    )
    assert r.status_code == 200, r.text
    recs = _lines(r.text)
    # The held branch served it, not the plain sweep.
    assert len(streams) == 1 and len(plain) == 0 and len(points) == 25
    ex = example_for(INVVEE)

    def standalone(rq):
        return ex.momwire_solve(rq)

    branches: Counter = Counter()
    for (args, kwargs, (sent, res)), rec in zip(points, recs[:-1], strict=True):
        x, knob, start, free, objective = args
        branches["warm" if kwargs["warm"] else "cold"] += 1
        alone = optimize(
            {**kwargs["base"], knob: x, **start},
            [dict(f) for f in free],
            objective,
            solve_fn=standalone,
            warm=kwargs["warm"],
            fallback=False,
        )
        assert alone["params"] == res["params"] == rec["held"]
        z = alone["metrics_after"]
        assert (z["z_in_re"], z["z_in_im"]) == (rec["z_re"], rec["z_im"])
    assert branches == Counter({"cold": 1, "warm": 24}), branches
    # The start was the design's DEFAULTS, not the request's live knob.
    live = client.post(
        "/param_sweep",
        json={
            **_req(length_factor=1.1),
            "param": w["param"],
            "values": w["values"][:3],
            "hold": w["hold"]["spec"],
        },  # fmt: skip
    )
    assert [x["held"] for x in _lines(live.text)[:-1]] == [x["held"] for x in recs[:3]]


# ── 2. E8 and E9 ──────────────────────────────────────────────────────────


def test_e9_holds_x_at_zero_and_the_length_moves_smoothly(
    monkeypatch, capsys, tmp_path
):
    got, out = _analyze(monkeypatch, capsys, tmp_path, E9)
    (pts,) = got["held"].values()
    assert all(p.converged for p in pts), out
    worst = max(abs(p.z.imag) for p in pts)
    assert worst <= _ROOT_FTOL, worst
    lf = np.array([p.params["length_factor"] for p in pts])
    # Smooth: the resonant length rises with the droop, monotonically, in
    # steps far below the knob's 0.45-wide range, and without a kink.
    assert np.all(np.diff(lf) > 0)
    assert np.max(np.diff(lf)) < 0.01
    assert np.max(np.abs(np.diff(lf, 2))) < 0.002
    assert "25 of 25 points held, 0 gaps" in out
    print(f"E9: worst |X| {worst:.3g} ohm; lf {lf[0]:.5f} -> {lf[-1]:.5f}")


def test_e8_holds_the_match_where_it_converges_and_names_the_rest(
    monkeypatch, capsys, tmp_path
):
    got, out = _analyze(monkeypatch, capsys, tmp_path, E8, "--ground", "finite-fast")
    (pts,) = got["held"].values()
    held = [p for p in pts if p.converged]
    gaps = [p for p in pts if not p.converged]
    assert len(held) >= 34, out
    worst = max(abs(p.z - 50) for p in held)
    assert worst <= _ROOT_FTOL, worst
    # Every gap has its reason, and draws as NaN (never a value).
    (xs, zs) = got["curves"]["momwire"]
    for p in gaps:
        assert p.reason and f"gap at base = {p.x:g}: {p.reason}" in out
        assert np.isnan(zs[list(xs).index(p.x)])
    # Smooth where warm-started: neighbouring held points move the knobs by
    # a small fraction of their ranges (0.45 and 60 deg).
    for a, b in itertools.pairwise(pts):
        if a.converged and b.converged and not b.cold:
            assert abs(b.params["length_factor"] - a.params["length_factor"]) < 0.03
            assert abs(b.params["angle_deg"] - a.params["angle_deg"]) < 8.0
    print(f"E8: {len(held)}/{len(pts)} held, worst |Z-50| {worst:.3g} ohm; gaps "
          + "; ".join(f"{p.x:g}: {p.reason}" for p in gaps))  # fmt: skip


def test_e8_and_e9_run_in_the_workbench(client):
    for name, z0, tol in ((E9, None, _ROOT_FTOL), (E8, 50, _ROOT_FTOL)):
        w = _entry(client, name)["workbench"]
        assert w["runs"] is True and "Knobs" in w["views"]
        req = {**_req(), "ground": True, "ground_model": "fast"}
        r = client.post(
            "/param_sweep",
            json={
                **req,
                "param": w["param"],
                "values": w["values"],
                "hold": w["hold"]["spec"],
            },
        )
        assert r.status_code == 200, r.text
        recs = _lines(r.text)
        done = recs[-1]
        assert done["done"] is True
        ok = [x for x in recs[:-1] if x["converged"]]
        for x in ok:
            z = complex(x["z_re"], x["z_im"])
            assert (abs(z.imag) if z0 is None else abs(z - z0)) <= tol, x
        for x in recs[:-1]:
            if not x["converged"]:
                assert x["gap"] and "z_re" not in x
        assert done["held_points"] == len(ok) >= len(recs) - 3
        print(f"workbench {name}: {done['held_points']} held, {done['gaps']} gaps")


# ── 3. a forced non-convergence ───────────────────────────────────────────


@pytest.fixture
def tight(monkeypatch):
    """invvee with length_factor's range cut to 0.80..0.99: the resonant
    length (0.970 at 0 deg, 1.006 at 60 deg) leaves it near 50 deg."""
    cls = example_for(INVVEE).builder_cls
    ui = dict(cls.default_params["ui_params"])
    ui["length_factor"] = {"min": 0.8, "max": 0.99}
    params = dict(cls.default_params)
    params["ui_params"] = MappingProxyType(ui)
    monkeypatch.setattr(cls, "default_params", MappingProxyType(params))
    return cls


def test_a_root_outside_the_bounds_is_gaps_with_reasons_and_the_recovery(
    monkeypatch, capsys, tmp_path, tight
):
    csv = tmp_path / "e9.csv"
    got, out = _analyze(monkeypatch, capsys, tmp_path, E9, "--csv", str(csv))
    (pts,) = got["held"].values()
    gaps = [p for p in pts if not p.converged]
    assert gaps, out
    first = pts.index(gaps[0])
    # Every point past the exit is a gap, with its reason naming the bound.
    assert all(not p.converged for p in pts[first:])
    for p in gaps:
        assert "ui_params max 0.99" in p.reason, p.reason
        assert f"gap at angle_deg = {p.x:g}: " in out
    # The recovery: the first three failures warm-start from the last
    # CONVERGED point, then each remaining point cold-starts once.
    last = pts[first - 1].params
    for p in pts[first : first + hd.FAILS_BEFORE_COLD]:
        assert not p.cold and p.start == last
    for p in pts[first + hd.FAILS_BEFORE_COLD :]:
        default = {"length_factor": tight.default_params["length_factor"]}
        assert p.cold and p.start == default
        assert "cold start from the defaults (given up)" in out
    # Never a value: NaN on the curve, empty cells in the CSV.
    _xs, zs = got["curves"]["momwire"]
    assert np.all(np.isnan(np.asarray(zs[first:])))
    rows = csv.read_text().splitlines()
    assert rows[0] == "angle_deg,momwire R_ohm,momwire X_ohm,momwire length_factor"
    assert all(r.endswith(",,,") for r in rows[1 + first :]), rows
    print(f"forced: {len(gaps)} gaps from angle {gaps[0].x:g}; {gaps[0].reason}")


def test_the_workbench_draws_the_same_gaps_never_values(client, tight):
    w = _entry(client, E9)["workbench"]
    assert w["hold"]["bounds"] == {"length_factor": [0.8, 0.99]}
    r = client.post(
        "/param_sweep",
        json={
            **_req(),
            "param": w["param"],
            "values": w["values"],
            "hold": w["hold"]["spec"],
        },
    )
    recs = _lines(r.text)[:-1]
    gaps = [x for x in recs if not x["converged"]]
    assert gaps and all(
        "z_re" not in x and "ui_params max 0.99" in x["gap"] for x in gaps
    )
    assert _lines(r.text)[-1]["gaps"] == len(gaps)


def test_hold_line_recovers_when_the_root_comes_back():
    """The recovery rule on a synthetic X(x, k) = k - root(x), whose root
    leaves the box [0, 1] for four points and comes back: three warm
    failures from the last converged point, a cold start for the fourth,
    then a cold start that converges and resumes the warm chain."""
    roots = [0.5, 0.6, 1.5, 1.5, 1.5, 1.5, 0.7, 0.72]
    solves = []

    def solve(req):
        solves.append(req)
        x = int(req["x"])
        return {"z_in_re": 50.0, "z_in_im": req["k"] - roots[x], "z0_ohms": 50.0}

    pts = hd.hold_line(
        list(range(len(roots))),
        "x",
        [{"name": "k", "min": 0.0, "max": 1.0}],
        "resonance",
        solve_fn=solve,
        defaults={"k": 0.4},
    )
    assert [p.converged for p in pts] == [
        True,
        True,
        False,
        False,
        False,
        False,
        True,
        True,
    ]
    assert [p.cold for p in pts] == [
        True,
        False,
        False,
        False,
        False,
        True,
        True,
        False,
    ]
    assert pts[2].start == pts[3].start == pts[4].start == pts[1].params
    assert pts[5].start == pts[6].start == {"k": 0.4}
    assert pts[7].start == pts[6].params
    assert all("no resonance held" in p.reason for p in pts[2:6])


# ── 4. refusals by name ───────────────────────────────────────────────────


def test_what_v1_cannot_hold_is_refused_by_name(client):
    from antennaknobs.web import analyses_offer as ao

    b = get_builder(INVVEE)()
    h = an.Hold("resonance", adjust=("length_factor",))
    freq = an.Analysis("f", an.Sweep(an.FREQUENCY), hold=h)
    assert any("frequency sweep: not in v1" in g for g in ao.gaps(freq, b))
    swr = an.Analysis(
        "s", an.Sweep("angle_deg"), hold=an.Hold("swr", adjust=("length_factor",))
    )
    assert any(g.startswith("hold swr:") for g in ao.gaps(swr, b))
    # A held knob with no ui_params range is refused by name, not unbounded.
    bare = get_builder(INVVEE)()
    bare.ui_params = {}
    with pytest.raises(
        hd.HoldRefused, match="length_factor, which has no ui_params min/max"
    ):
        hd.free_of(h, bare)
    r = client.post(
        "/param_sweep",
        json={
            **_req(),
            "param": "angle_deg",
            "values": [0.0],
            "hold": an.to_data(an.Hold("swr", adjust=("length_factor",))),
        },  # fmt: skip
    )
    assert r.status_code == 422 and "hold swr" in r.json()["detail"]


# ── 5. keep: kept == pinned, bit-equal ───────────────────────────────────


def _entry(client, name, **req) -> dict:
    r = client.post("/analyses", json={"geometry": INVVEE, **req})
    (e,) = [e for e in r.json()["analyses"] if e["name"] == name]
    return e


def _held_curve(client, w, req) -> list[dict]:
    r = client.post(
        "/param_sweep",
        json={
            **req,
            "param": w["param"],
            "values": w["values"],
            "hold": w["hold"]["spec"],
        },
    )
    assert r.status_code == 200, r.text
    return _lines(r.text)[:-1]


def _run_study(monkeypatch, capsys, tmp_path, name) -> dict:
    runs = _record(monkeypatch, ar, "run")
    cli(["analyze", "--study", name, "--nominal-nsegs", str(N),
         "--fn", str(tmp_path / "chart.png")])  # fmt: skip
    capsys.readouterr()
    return runs[-1][2]


def _same(recs, pts) -> int:
    """Every held record equals the study's point at its x: Z and knobs."""
    at = {p.x: p for p in pts}
    n = 0
    for x in recs:
        p = at[x["value"]]
        assert p.converged and x["converged"]
        assert (p.z.real, p.z.imag) == (x["z_re"], x["z_im"])
        assert p.params == x["held"]
        n += 1
    return n


def test_a_kept_held_chart_reruns_bit_equal(
    monkeypatch, capsys, tmp_path, client, folder
):
    e = _entry(client, E9)
    w = e["workbench"]
    req = _req()
    recs = _held_curve(client, w, req)
    body = {"origin": "chart", "form": "study", "name": "held e9",
            "spec": e["spec"], "tab": req, "cells": [req]}  # fmt: skip
    r = client.post("/studies/save", json={**body, "path": "holds/e9"})
    assert r.status_code == 200, r.text
    (st,) = [s for s in studies.discover().studies if s.source == "holds/e9"]
    assert st.analysis.hold == an.Hold("resonance", adjust=("length_factor",))
    cells = _record(monkeypatch, ar, "hold_cell")
    got = _run_study(monkeypatch, capsys, tmp_path, "holds/e9:held e9")
    assert len(cells) == 1
    (pts,) = got["held"].values()
    assert _same(recs, pts) == 25


def test_held_pins_keep_their_hold_and_rerun_bit_equal(
    monkeypatch, capsys, tmp_path, client, folder
):
    w = _entry(client, E9)["workbench"]
    req = _req(base=9.0)
    recs = _held_curve(client, w, req)
    pin = {
        "req": {**req, "hold": w["hold"]["spec"]},
        "label": "",
        "x": {"kind": "knob", "name": "angle_deg"},
        "xs": [x["value"] for x in recs],
    }
    r = client.post(
        "/studies/save",
        json={
            "origin": "sweep pins",
            "name": "held pin",
            "pins": [pin],
            "path": "holds/pin",
        },
    )
    assert r.status_code == 200, r.text
    (st,) = [s for s in studies.discover().studies if s.source == "holds/pin"]
    assert st.analysis.hold is not None and an.Knobs() in st.analysis.views
    # The live length_factor is no part of the pin's state: the hold moves it.
    (state,) = an.states_of(st.analysis)
    assert dict(state.settings) == {"base": 9.0}
    got = _run_study(monkeypatch, capsys, tmp_path, "holds/pin:held pin")
    (pts,) = got["held"].values()
    assert _same(recs, pts) == 25
    # Pins drawn under different holds are refused by name.
    other = {
        **pin,
        "req": {**req, "hold": an.to_data(an.Hold("resonance", adjust=("base",)))},
    }
    r = client.post("/keep", json={"origin": "sweep pins", "pins": [pin, other]})
    assert r.status_code == 422 and "holds one way" in r.json()["detail"]


# ── 6. a hold composed with a MetricPlot (AK#1828) ────────────────────────
#
# M0AGP's study shape: resonance held with the length while a knob sweeps,
# and a far-field metric (the DX gain window) drawn against it, relative to a
# FIXED reference (a state that sets the swept knob, solved once at its own
# setting and never held). The metric is read at each point's OPTIMISED knobs.

BSPLINE = "momwire:bspline"
DX = an.ElevationWindow("DX gain", 2, 10, step=0.1)
ANGLES = (0.0, 20.0, 40.0)


def _held_dx(**kw) -> an.Analysis:
    return an.Analysis(
        **{
            "name": "held dx",
            "sweep": an.Sweep("angle_deg", values=ANGLES),
            "cross": an.Cross(
                states=(an.State("as built"), an.State("flat", angle_deg=0.0))
            ),
            "hold": an.Hold("resonance", adjust=("length_factor",)),
            "views": (an.MetricPlot(DX, relative_to="flat"), an.Knobs()),
            **kw,
        }
    )


def _offer_analyses(monkeypatch, analyses):
    monkeypatch.setattr(
        type(get_builder(INVVEE)()), "build_analyses", lambda self: list(analyses)
    )


def _bspline_builder_solve():
    """The CLI's solve at N, built here: a fresh builder and B-spline factory."""
    b = get_builder(INVVEE)()
    factory = make_engine_factory(BSPLINE, None, nominal_nsegs=N)

    def solve(req):
        for k, v in req.items():
            setattr(b, k, v)
        z = complex(factory(b).impedance()[0])
        return {"z_in_re": z.real, "z_in_im": z.imag, "z0_ohms": 50.0}

    return solve, b, factory


def _dx_at(**knobs) -> float:
    from antennaknobs import metrics as mx

    b = get_builder(INVVEE)()
    for k, v in knobs.items():
        setattr(b, k, v)
    eng = make_engine_factory(BSPLINE, None, nominal_nsegs=N)(b)
    return mx.evaluate(DX, mx.source_for(eng))


def _run_held_dx(monkeypatch, capsys, tmp_path, *extra) -> dict:
    runs = _record(monkeypatch, ar, "_run_metric_plots")
    cli(["analyze", "--builder", INVVEE, "--analysis", "held dx", "--engine", BSPLINE,
         "--nominal-nsegs", str(N), "--fn", str(tmp_path / "dx.png"), *extra])  # fmt: skip
    capsys.readouterr()
    return runs[-1][2][0]["DX gain"]


def test_a_held_metric_is_the_metric_at_the_standalone_optimum_bit_equal(
    monkeypatch, capsys, tmp_path
):
    _offer_analyses(monkeypatch, [_held_dx()])
    points = _record(monkeypatch, hd, "hold_point")
    cells = _record(monkeypatch, ar, "hold_cell")
    held_reads = _record(monkeypatch, ar, "_held_metric_values")
    per = _run_held_dx(monkeypatch, capsys, tmp_path)
    # Only the swept cell is held; the fixed reference is not.
    assert [c[0][0].label for c in cells] == ["as built"]
    assert len(held_reads) == 1 and len(points) == len(ANGLES)
    curve, ref = per["as built"], per["flat"]
    assert curve.xs == ANGLES and ref.fixed and curve.reference == "flat"
    solve, _b, _f = _bspline_builder_solve()
    for k, (args, kwargs, (_req, res)) in enumerate(points):
        x, knob, start, free, objective = args
        alone = optimize({knob: x, **start}, [dict(f) for f in free], objective,
                         solve_fn=solve, warm=kwargs["warm"], fallback=False)  # fmt: skip
        assert alone["params"] == res["params"]
        # The metric at the standalone optimum, solved afresh: ==.
        want = _dx_at(angle_deg=x, **alone["params"])
        assert curve.values[k] == want
        assert curve.relative[k] == want - ref.values[0]
    # The fixed reference is its own setting, never held: the defaults' length.
    assert ref.values == (_dx_at(angle_deg=0.0),)
    # Adversarial: the held metric is not the un-held one at the same x.
    assert curve.values[2] != _dx_at(angle_deg=40.0)


def test_a_gap_is_a_gap_in_the_metric_curve_too(monkeypatch, capsys, tmp_path, tight):
    _offer_analyses(
        monkeypatch, [_held_dx(sweep=an.Sweep("angle_deg", values=(0.0, 55.0, 60.0)))]
    )
    csv = tmp_path / "dx.csv"
    per = _run_held_dx(monkeypatch, capsys, tmp_path, "--csv", str(csv))
    curve = per["as built"]
    assert curve.values[0] is not None
    assert curve.values[1:] == (None, None) and curve.relative[1:] == (None, None)
    rows = csv.read_text().splitlines()
    head = rows[0].split(",")
    i = head.index("as built DX gain (dBi)")
    assert [r.split(",")[i] for r in rows[1:]] == [rows[1].split(",")[i], "", ""]


def test_a_held_metric_plot_csv_carries_the_held_knobs(monkeypatch, capsys, tmp_path):
    """With no impedance view (MetricPlot + Knobs, M0AGP's shape) the CSV
    still writes each held cell's R, X and held knob at every point, as it
    does beside an `Rx` chart: it wrote only the metric columns before."""
    import csv as csvmod

    _offer_analyses(monkeypatch, [_held_dx()])
    cells = _record(monkeypatch, ar, "hold_cell")
    out = tmp_path / "dx.csv"
    _run_held_dx(monkeypatch, capsys, tmp_path, "--csv", str(out))
    with out.open(newline="") as f:
        head, *rows = list(csvmod.reader(f))
    assert head == [
        "angle_deg",
        "as built R_ohm",
        "as built X_ohm",
        "as built length_factor",
        "as built DX gain (dBi)",
        "as built DX gain vs flat (dB)",
    ]
    (pts,) = [c[2] for c in cells]
    assert [float(r[0]) for r in rows] == list(ANGLES)
    for r, pt in zip(rows, pts, strict=True):
        assert pt.converged
        assert float(r[3]) == pt.params["length_factor"]
        assert complex(float(r[1]), float(r[2])) == pt.z
    # The fixed reference is never held: no knob columns of its own.
    assert not any(h.startswith("flat ") for h in head)


def test_workbench_held_metric_is_the_metric_at_the_standalone_optimum(
    monkeypatch, client
):
    from antennaknobs.web.adapter import capture_solved_metrics

    _offer_analyses(monkeypatch, [_held_dx()])
    e = _entry(client, "held dx")
    w = e["workbench"]
    assert w["views"] == ["Metric", "Knobs"] and w["metric"]["relative_to"] == "flat"
    built, flat = w["states"]
    assert flat["fixed"] is True and built["fixed"] is False
    points = _record(monkeypatch, hd, "hold_point")
    r = client.post(
        "/param_sweep",
        json={
            **_req(),
            "param": "angle_deg",
            "values": built["values"],
            "hold": w["hold"]["spec"],
            "metric": w["metric"]["spec"],
        },  # fmt: skip
    )
    assert r.status_code == 200, r.text
    recs = _lines(r.text)[:-1]
    ex = example_for(INVVEE)
    for (args, kwargs, (_sent, res)), rec in zip(points, recs, strict=True):
        x, knob, start, free, objective = args
        alone = optimize({**kwargs["base"], knob: x, **start}, [dict(f) for f in free],
                         objective, solve_fn=ex.momwire_solve, warm=kwargs["warm"],
                         fallback=False)  # fmt: skip
        assert rec["held"] == alone["params"]
        with capture_solved_metrics() as box:
            ex.momwire_solve({**kwargs["base"], knob: x, **alone["params"]})
        want, why = hd.metric_off(DX, box[-1].gain(), box[-1].freq)
        assert why is None and rec["metric"] == want
    assert len(points) == len(recs) == len(ANGLES)


def test_a_kept_held_metric_plot_chart_reruns_bit_equal(
    monkeypatch, capsys, tmp_path, client, folder
):
    _offer_analyses(monkeypatch, [_held_dx()])
    e = _entry(client, "held dx")
    w = e["workbench"]
    drawn = {}
    for st in w["states"]:
        req = {**_req(), **st["knobs"]}
        body = {**req, "param": st["param"], "values": st["values"],
                "metric": w["metric"]["spec"]}  # fmt: skip
        if not st["fixed"]:
            # The chart sends the hold with every curve but the fixed reference.
            body["hold"] = w["hold"]["spec"]
        r = client.post("/param_sweep", json=body)
        assert r.status_code == 200, r.text
        recs = _lines(r.text)[:-1]
        drawn[st["name"]] = (req, [x["metric"] for x in recs], recs)
    body = {"origin": "chart", "form": "study", "name": "kept held dx",
            "spec": e["spec"], "tab": _req(),
            "cells": [drawn["as built"][0], drawn["flat"][0]]}  # fmt: skip
    r = client.post("/studies/save", json={**body, "path": "holds/dx"})
    assert r.status_code == 200, r.text
    (st,) = [s for s in studies.discover().studies if s.source == "holds/dx"]
    assert st.analysis.hold is not None
    assert an.metric_plots(st.analysis) == (an.MetricPlot(DX, relative_to="flat"),)
    runs = _record(monkeypatch, ar, "_run_metric_plots")
    cli(["analyze", "--study", "holds/dx:kept held dx", "--nominal-nsegs", str(N),
         "--fn", str(tmp_path / "kept.png")])  # fmt: skip
    capsys.readouterr()
    per = runs[-1][2][0]["DX gain"]
    (built,) = [c for label, c in per.items() if label.endswith("as built")]
    (ref,) = [c for label, c in per.items() if label.endswith("flat")]
    assert built.xs == ANGLES
    assert list(built.values) == drawn["as built"][1]
    assert ref.fixed and list(ref.values) == drawn["flat"][1]
    assert list(built.relative) == [
        v - drawn["flat"][1][0] for v in drawn["as built"][1]
    ]
