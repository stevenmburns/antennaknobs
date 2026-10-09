"""Keepable multi-band optimize runs and multi-band holds (AK#1906).

The gates: ``an.Optimize`` and ``an.Hold(bands=...)`` round-trip through
``to_code`` and ``to_data``; a run kept with ``optimize --bands --keep`` is a
trusted study that ``analyze --study`` lists, re-runs to the same per-band
SWR, and ``--apply`` loads with its stored knobs exactly; a band hold on the
two-band fan matches an independent band optimization at each of three sweep
points. UR0GT's deck (a third-party file, never committed) is the slow
lane's, skipped without it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import antennaknobs as ant
from antennaknobs import analyses as an
from antennaknobs import hold
from antennaknobs.web import optimize_bands as ob

FAN = "multiband.twoband_fan_dipole:current_physical"


def _ev(code: str):
    return eval(code, {"an": an})


def _optimize(**kw) -> an.Optimize:
    fields = {
        "name": "fan 26.6/29.3",
        "start": an.State(
            "start", "multiband.twoband_fan_dipole", variant="current_physical"
        ),
        "knobs": (
            an.Knob("bands.0.length", 5.2, 5.8),
            an.Knob("bands.1.length", 4.8, 5.3),
        ),
        "bands": (an.Band(26.6), an.Band(29.3)),
        "engine": "momwire",
        "result": an.Result(
            (("bands.0.length", 5.5), ("bands.1.length", 5.05)),
            (
                an.BandResult(26.6, (60.0, -20.0), (55.0, 1.0), 1.6, 1.1),
                an.BandResult(29.3, None, (52.0, -3.0), None, 1.08),
            ),
        ),
        **kw,
    }
    return an.Optimize(**fields)


# ── the values ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        _optimize(),
        _optimize(
            mode="sequential",
            bands=(
                an.Band(26.6, knobs=("bands.0.length",)),
                an.Band(29.3, knobs=("bands.1.length",)),
            ),
        ),
        _optimize(result=None, group="Tuning", mean_weight=0.2, max_evals=80),
        _optimize(
            mode="root",
            bands=(an.Band(26.6, "resonance"), an.Band(29.3, "resonance")),
            result=None,
        ),
        an.Hold(
            "swr",
            adjust=("bands.0.length", "bands.1.length"),
            bands=(an.Band(26.6), an.Band(29.3, z0=75.0)),
            mean_weight=0.3,
        ),
        an.Hold(
            "resonance",
            adjust=("bands.0.length", "bands.1.length"),
            bands=(an.Band(26.6), an.Band(29.3)),
            warm_start=False,
        ),
    ],
    ids=["kept", "sequential", "grouped", "root", "band hold", "root hold"],
)
def test_round_trips_through_code_and_data(value):
    code = an.to_code(value)
    assert _ev(code) == value, code
    assert an.from_data(an.to_data(value)) == value


def test_an_analysis_with_a_band_hold_round_trips():
    a = an.Analysis(
        "the fan held across its bands",
        an.Sweep("base", 5, 9, points=3),
        hold=an.Hold("swr", adjust=("bands.0.length",), bands=(an.Band(26.6),)),
        views=(an.Swr(), an.Knobs()),
    )
    assert _ev(an.to_code(a)) == a
    assert an.from_data(an.to_data(a)) == a


def test_a_hold_written_before_bands_still_reads():
    h = an.Hold("resonance", adjust=("length_factor",))
    data = an.to_data(h)
    for k in ("bands", "mean_weight"):
        del data[k]
    assert an.from_data(data) == h
    assert "bands" not in an.to_code(h)


def test_the_spec_constants_are_the_optimizers():
    assert an.BANDS_MEAN_WEIGHT == ob.DEFAULT_MEAN_WEIGHT
    assert an.MAX_BANDS == ob.MAX_BANDS
    assert an.BAND_MODES == ob.MODES
    assert set(an.BAND_OBJECTIVES) == set(ob.BAND_OBJECTIVES)


@pytest.mark.parametrize(
    "kw, words",
    [
        ({"mode": "root", "result": None}, "as many equations as knobs"),
        (
            {"bands": (an.Band(26.6), an.Band(29.3, "resonance")), "result": None},
            "one unit",
        ),
        ({"mode": "sequential", "result": None}, "each band's own knobs"),
        (
            {"result": an.Result((("bands.1.length", 5.0), ("bands.0.length", 5.5)))},
            "the result's knobs are the run's",
        ),
        ({"mean_weight": 1.5}, "within 0..1"),
        ({"start": an.State("start")}, "naming its design"),
        ({"bands": (an.Band(26.6), an.Band(26.6))}, "listed twice"),
    ],
)
def test_an_optimize_refuses_by_name(kw, words):
    with pytest.raises((TypeError, ValueError), match=words):
        _optimize(**kw)


@pytest.mark.parametrize(
    "kw, words",
    [
        (
            {
                "objective": "resonance",
                "adjust": ("a",),
                "bands": (an.Band(1.0), an.Band(2.0)),
            },
            "2 equations",
        ),
        (
            {
                "objective": "swr",
                "adjust": ("a",),
                "bands": (an.Band(1.0, "resonance"),),
            },
            "one objective across its bands",
        ),
    ],
)
def test_a_band_hold_refuses_by_name(kw, words):
    with pytest.raises(ValueError, match=words):
        an.Hold(**kw)


def test_swr_is_holdable_across_bands_only():
    from antennaknobs.analysis_run import cli_gaps

    one = an.Analysis(
        "x", an.Sweep("base", 5, 9, points=3), hold=an.Hold("swr", adjust=("s",))
    )
    many = an.Analysis(
        "x",
        an.Sweep("base", 5, 9, points=3),
        hold=an.Hold("swr", adjust=("s",), bands=(an.Band(26.6),)),
    )
    assert any("SWR is a minimisation" in g for g in cli_gaps(one))
    assert cli_gaps(many) == []


# ── kept, listed, re-run, applied ────────────────────────────────────────────


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


_FAN_RUN = [
    "optimize",
    "--builder",
    FAN,
    "--engine",
    "momwire",
    "--bands",
    "26.6:res,29.3:res",
    "--mode",
    "root",
    "--params",
    "bands.0.length",
    "bands.1.length",
    "--bound",
    "bands.0.length=5.2:5.8",
    "--bound",
    "bands.1.length=4.8:5.3",
]


def _swrs(out: str) -> list[float]:
    """The SWR after column of `band_opt.report_lines`' table: the first
    ``before>after`` pair of each band row (the second is the residual)."""
    rows = [ln for ln in out.splitlines() if re.match(r"^\s+\d+\s+\d", ln)]
    return [float(re.search(r"\d+\.\d+>(\d+\.\d+)", ln).group(1)) for ln in rows]


def test_a_kept_run_is_a_trusted_study_that_reruns_and_applies(folder, capsys):
    ant.cli([*_FAN_RUN, "--keep", "fan/two", "--keep-name", "fan pair"])
    out = capsys.readouterr().out
    assert "kept as the study 'fan/two:fan pair'" in out
    kept = _swrs(out)
    assert len(kept) == 2
    text = (folder / "fan" / "two.py").read_text()
    assert "an.Optimize(" in text and "Saved trusted" in text

    from antennaknobs import studies

    study = studies.find("fan/two:fan pair")
    o = study.analysis
    assert an.is_optimize(o) and o.result is not None
    assert o.mode == "root" and o.bands[0].objective == "resonance"
    assert study.includes("multiband.twoband_fan_dipole")
    assert [b.swr_after for b in o.result.bands] == pytest.approx(kept, abs=1e-3)

    ant.cli(["analyze", "--list-studies"])
    assert "fan/two:fan pair" in capsys.readouterr().out

    # Re-run: the same search from the same start, so the same answer.
    ant.cli(["analyze", "--study", "fan/two:fan pair"])
    out = capsys.readouterr().out
    assert _swrs(out) == pytest.approx(kept, abs=1e-3)
    assert "against the stored result" in out

    # --apply: no search, the stored knobs exactly, each band read there.
    ant.cli(["analyze", "--study", "fan/two:fan pair", "--apply"])
    out = capsys.readouterr().out
    got = dict(re.findall(r"^(bands\.\d\.length) = (\S+)$", out, re.M))
    assert {k: float(v) for k, v in got.items()} == o.result.values
    assert "evals" not in out  # nothing searched


def test_override_engine_reruns_a_kept_run_on_another_engine(
    folder, capsys, monkeypatch
):
    """A kept run's engine wins over --engine, so a re-run repeats it;
    --override-engine is the explicit way onto another (#1921). A spy on the
    engine seam proves which engine each --apply actually built."""
    import importlib

    cli = importlib.import_module("antennaknobs.cli")  # the module, not ant.cli
    ant.cli([*_FAN_RUN, "--keep", "fan/two", "--keep-name", "fan pair"])
    capsys.readouterr()
    built = []
    real = cli.make_engine_factory

    def spy(spec, *a, **k):
        built.append(spec)
        return real(spec, *a, **k)

    monkeypatch.setattr(cli, "make_engine_factory", spy)
    study = ["analyze", "--study", "fan/two:fan pair", "--apply"]

    ant.cli([*study, "--engine", "momwire:sinusoidal"])
    assert built == ["momwire"]  # the kept engine, not --engine
    assert "overriding" not in capsys.readouterr().out

    built.clear()
    ant.cli([*study, "--override-engine", "momwire:sinusoidal"])
    assert built == ["momwire:sinusoidal"]
    out = capsys.readouterr().out
    assert "# engine momwire:sinusoidal, overriding the kept run's momwire" in out
    assert "against the stored result" in out


def test_override_engine_needs_a_kept_run():
    with pytest.raises(SystemExit, match="--override-engine re-runs a kept"):
        ant.cli(
            [
                "analyze",
                "--builder",
                "dipoles.invvee",
                "--study",
                "dipoles.apex_feed_on_invvee:feed spelling (E7)",
                "--override-engine",
                "momwire:sinusoidal",
            ]
        )


def test_apply_reproduces_the_stored_knobs_exactly():
    from antennaknobs import optimize_study as ost
    from antennaknobs.cli import get_builder, make_engine_factory

    o = _optimize()
    b = ost.prepared(o, get_builder)
    got = ost.apply(o, b, make_engine_factory("momwire", None))
    assert got["params"] == o.result.values
    for k, v in o.result.values.items():
        assert ost._get_path(b, k) == v  # set exactly, not re-derived
    assert [r["freq_mhz"] for r in got["bands"]] == [26.6, 29.3]


@pytest.mark.parametrize("knob", ["name", "design", "variant"])
def test_a_start_with_a_knob_named_as_a_state_argument_is_refused(monkeypatch, knob):
    """A design knob spelled ``name``/``design``/``variant`` cannot be a
    State keyword (#1921): refused by name, as keep's states are, not a
    TypeError from the State call."""
    from antennaknobs import optimize_study as ost

    built, fresh = object(), object()
    monkeypatch.setattr(an, "_params", lambda b: {knob: 2.0 if b is built else 1.0})
    monkeypatch.setattr(an, "density_knob", lambda b: "nsegs")
    with pytest.raises(ValueError, match=rf"the knob '{knob}' cannot be written"):
        ost.start_state("fan_dipole", built, fresh)


def test_analyze_apply_needs_a_kept_run():
    with pytest.raises(SystemExit, match="not an an.Optimize"):
        ant.cli(
            [
                "analyze",
                "--builder",
                "dipoles.invvee",
                "--study",
                "dipoles.apex_feed_on_invvee:feed spelling (E7)",
                "--apply",
            ]
        )


# ── a band hold ──────────────────────────────────────────────────────────────


def _fan_builder():
    from antennaknobs.cli import get_builder

    return get_builder(FAN)()


# 6-11 s of fan solves: out of the PR lane (#1921).
@pytest.mark.antenna_computation_check
def test_a_band_hold_matches_independent_band_runs_at_three_points():
    """Each held point (warm-started from the last, as a hold runs) agrees
    with a band run of its own from the design's defaults, to the root
    form's tolerance."""
    from antennaknobs import band_opt
    from antennaknobs.cli import make_engine_factory

    h = an.Hold(
        "resonance",
        adjust=("bands.0.length", "bands.1.length"),
        bands=(an.Band(26.6), an.Band(29.3)),
    )
    factory = make_engine_factory("momwire", None)
    xs = [6.0, 7.0, 8.0]
    b = _fan_builder()
    free = hold.band_free_of(h, b)
    defaults = hold.band_defaults_of(b, free)
    held = hold.hold_bands_line(
        xs,
        "base",
        free,
        h,
        sweep_fn=band_opt.builder_sweep_fn(b, factory, 50.0),
        defaults=defaults,
    )
    assert [pt.cold for pt in held] == [True, False, False]
    for i, (x, pt) in enumerate(zip(xs, held, strict=True)):
        solo = ob.optimize_bands(
            {"base": x, **defaults},
            free,
            hold.bands_of(h),
            sweep_fn=band_opt.builder_sweep_fn(_fan_builder(), factory, 50.0),
            mode="root",
        )
        assert solo["root_status"] == "root", solo
        assert pt.converged, pt.reason
        if i == 0:
            # Cold from the defaults, as the solo run starts: the same call,
            # so the same answer, exactly.
            assert pt.params == solo["params"]
        for k, v in solo["params"].items():
            assert pt.params[k] == pytest.approx(v, abs=2e-3)
        assert [r["swr"] for r in pt.bands] == pytest.approx(
            [r["swr"] for r in solo["bands_after"]], abs=5e-3
        )


def test_a_root_the_band_hold_cannot_reach_is_a_gap():
    res = {
        "root_status": "no root in the box",
        "at_bound": [{"name": "k", "bound": "max"}],
    }
    why = hold._band_gap_reason(res, "root")
    assert why.startswith("no root held across the bands (no root in the box)")
    assert "k at its max" in why
    assert hold._band_gap_reason({"root_status": "root"}, "root") is None
    assert "no band near a match" in hold._band_gap_reason(
        {"far_from_match": True, "worst_swr_after": 300.0}, "minimax"
    )


def test_analyze_runs_a_band_hold_and_draws_per_band_swr(monkeypatch, capsys, tmp_path):
    """The CLI's run: a curve per band, its SWR along the sweep, and the
    knobs that hold it."""
    from antennaknobs import analysis_run as ar
    from antennaknobs.designs.multiband.twoband_fan_dipole import Builder

    a = an.Analysis(
        "fan held",
        an.Sweep("base", 6, 8, points=3),
        hold=an.Hold(
            "resonance",
            adjust=("bands.0.length", "bands.1.length"),
            bands=(an.Band(26.6), an.Band(29.3)),
        ),
        views=(an.Swr(), an.Table(), an.Knobs()),
    )
    monkeypatch.setattr(Builder, "build_analyses", lambda self: (a,))
    ant.cli(
        [
            "analyze",
            "--builder",
            FAN,
            "--analysis",
            "fan held",
            "--fn",
            str(tmp_path / "h.png"),
        ]
    )
    out = capsys.readouterr().out
    assert "held resonance across 26.6/29.3 MHz (root)" in out
    assert "3 of 3 points held" in out, out
    assert "SWR 26.6" in out and "SWR 29.3" in out
    assert (tmp_path / "h.png").exists()
    assert "hold resonance on bands.0.length, bands.1.length across 26.6/29.3 MHz" in (
        ar.summary(a, Builder())
    )


# ── UR0GT (third-party deck, never committed) ────────────────────────────────

_UR0GT = Path(
    os.environ.get(
        "AK_UR0GT_DECK", str(Path.home() / "revpin" / "UR0GT_SY_vert_inv_L.nec")
    )
)


@pytest.mark.heavy_mesh
@pytest.mark.skipif(not _UR0GT.is_file(), reason=f"UR0GT's deck not at {_UR0GT}")
def test_a_kept_ur0gt_run_reruns_to_the_same_per_band_swr(folder, capsys):
    """UR0GT's 160/80/40 m vertical, kept and run again. sy_cap1 rails at
    the top of any range (the optimizer wants it shorted), so its range is
    pinned."""
    run = [
        "optimize",
        "--builder",
        f"@{_UR0GT}",
        "--bands",
        "1.83,3.7,7.1",
        "--params",
        "sy_w5hgt",
        "sy_w6len",
        "sy_cap1",
        "sy_cap2",
        "--bound",
        "sy_w5hgt=8:16",
        "--bound",
        "sy_w6len=45:75",
        "--bound",
        "sy_cap1=100:1000",
        "--bound",
        "sy_cap2=10:150",
    ]
    ant.cli([*run, "--keep", "ur0gt/three"])
    out = capsys.readouterr().out
    kept = _swrs(out)
    name = re.search(r"kept as the study '([^']+)'", out).group(1)
    ant.cli(["analyze", "--study", name])
    assert _swrs(capsys.readouterr().out) == pytest.approx(kept, abs=0.02)


# ── the workbench: keep, list, jump ──────────────────────────────────────────


def _rec(freq, swr, z0=50.0):
    return {
        "freq_mhz": freq,
        "objective": "swr",
        "feed": 0,
        "z0_ohms": z0,
        "z_re": 40.0 + swr,
        "z_im": -3.0,
        "swr": swr,
        "residual": None,
        "value": swr,
    }


def _run_body(tab, free, params, before, *, path=None, name="kept pair"):
    body = {
        "origin": "optimize",
        "form": "study",
        "name": name,
        "tab": tab,
        "free": free,
        "bands": [{"freq": 26.6}, {"freq": 29.3}],
        "mean_weight": 0.4,
        "result": {
            "objective": "bands",
            "params": params,
            "params_before": before,
            "bands_before": [_rec(26.6, 2.5), _rec(29.3, 3.0)],
            "bands_after": [_rec(26.6, 1.2), _rec(29.3, 1.3)],
            "mean_weight": 0.4,
        },
    }
    if path is not None:
        body["path"] = path
    return body


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from antennaknobs.web import server

    return TestClient(server.app)


def test_the_workbench_keeps_a_band_run_and_lists_it(folder, client):
    tab = {"geometry": "multiband.twoband_fan_dipole", "variant": "current_physical"}
    free = [
        {"name": "bands.0.length", "min": 5.2, "max": 5.8},
        {"name": "bands.1.length", "min": 4.8, "max": 5.3},
    ]
    params = {"bands.0.length": 5.51, "bands.1.length": 5.04}
    before = {"bands.0.length": 5.6, "bands.1.length": 5.0}
    r = client.post(
        "/studies/save", json=_run_body(tab, free, params, before, path="fan/kept")
    )
    assert r.status_code == 200, r.text
    from antennaknobs import studies

    o = studies.find("fan/kept:kept pair").analysis
    assert an.is_optimize(o)
    assert o.design == "multiband.twoband_fan_dipole:current_physical"
    assert o.mean_weight == 0.4 and o.engine == "momwire:bspline"
    # The run's start: the moved knobs back where the run began.
    from antennaknobs import optimize_study as ost
    from antennaknobs.cli import get_builder

    b = ost.prepared(o, get_builder)
    assert [ost._get_path(b, k) for k in before] == list(before.values())
    assert o.result.values == params
    assert [r.swr_after for r in o.result.bands] == [1.2, 1.3]

    req = {**tab, "measurement_freq_mhz": 28.0, "design_freq_mhz": 28.0}
    got = client.post("/analyses", json=req).json()["analyses"]
    (entry,) = [a for a in got if a["study"] and a["study"]["name"] == "kept pair"]
    w = entry["workbench"]
    assert w["kind"] == "optimize" and w["runs"] is True
    assert w["free"] == free
    assert [bd["freq"] for bd in w["bands"]] == [26.6, 29.3]
    assert w["result"]["knobs"] == params
    assert entry["summary"].startswith("optimize bands.0.length, bands.1.length")
    assert entry["group"] == "General"
    # Another variant's tab lists it, and says why it cannot jump there.
    other = client.post("/analyses", json={**req, "variant": "default"}).json()
    (entry,) = [
        a for a in other["analyses"] if a["study"] and a["study"]["name"] == "kept pair"
    ]
    assert entry["workbench"] == {
        "runs": False,
        "why": "kept on the current_physical variant: switch to it to jump to this run",
    }


@pytest.fixture
def fresh_decks(monkeypatch):
    from antennaknobs.web import decks, server

    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


DECK = """CM synthetic two-band fan dipole with SY knobs (AK#1906)
CE
SY L1 = 10.2
SY L2 = 6.6
GW 1 1 0 -.01 10 0 .01 10 .001
GW 2 9 0 .01 10 0 L1/2 10 .001
GW 3 9 0 -.01 10 0 -L1/2 10 .001
GW 4 7 0 .01 10 0 L2/2 9 .001
GW 5 7 0 -.01 10 0 -L2/2 9 .001
GE 0
EX 0 1 1 0 1 0
FR 0 1 0 0 14.1
EN
"""


def test_a_deck_run_is_kept_by_its_file_name_and_listed_on_the_deck(
    folder, client, fresh_decks
):
    key = client.post("/deck", json={"name": "syn.nec", "text": DECK}).json()["key"]
    free = [
        {"name": "sy_l1", "min": 8.0, "max": 12.0},
        {"name": "sy_l2", "min": 5.0, "max": 8.0},
    ]
    body = _run_body(
        {"geometry": key},
        free,
        {"sy_l1": 10.6, "sy_l2": 6.9},
        {"sy_l1": 10.2, "sy_l2": 6.6},
    )
    copy = client.post("/keep", json=body).json()
    assert '"@syn.nec"' in copy["code"], copy["code"]
    assert "named by its file name" in copy["code"]
    assert copy["problems"] == [] and copy["study_refusal"] is None
    r = client.post("/studies/save", json={**body, "path": "decks/syn"})
    assert r.status_code == 200, r.text
    got = client.post("/analyses", json={"geometry": key}).json()["analyses"]
    (entry,) = [a for a in got if a["study"] and a["study"]["name"] == "kept pair"]
    assert entry["workbench"]["runs"] is True, entry["workbench"]
    assert entry["workbench"]["result"]["knobs"] == {"sy_l1": 10.6, "sy_l2": 6.9}


def test_a_band_run_keep_is_refused_by_name(client):
    body = _run_body({"geometry": "multiband.twoband_fan_dipole"}, [], {}, {})
    r = client.post("/keep", json=body)
    assert r.status_code == 422
    assert "free is the run's knobs" in r.json()["detail"]


def test_a_band_hold_is_listed_for_the_command_line(client, monkeypatch):
    from antennaknobs.designs.multiband.twoband_fan_dipole import Builder

    a = an.Analysis(
        "fan held",
        an.Sweep("base", 6, 8, points=3),
        hold=an.Hold("swr", adjust=("bands.0.length",), bands=(an.Band(26.6),)),
        views=(an.Swr(), an.Knobs()),
    )
    monkeypatch.setattr(Builder, "build_analyses", lambda self: (a,))
    got = client.post(
        "/analyses", json={"geometry": "multiband.twoband_fan_dipole"}
    ).json()["analyses"]
    (entry,) = [e for e in got if e["name"] == "fan held"]
    assert entry["workbench"]["runs"] is False
    assert "a hold across several bands" in entry["workbench"]["why"]
