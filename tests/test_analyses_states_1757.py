"""AK#1757, sweep framework step 7 unit 2: STATES, a cross over named knob
settings (``an.State``), in the spec, the CLI and the workbench's
``/analyses``.

The contract (docs/design/sweep-framework-step7.md, "States", ruling 2):

- a state is knob overrides over the design's DEFAULTS, so a state cell is
  the same design solved with those knobs set directly: checked bit-equal
  against ``antennaknobs sweep --set`` (the same solve path, the knobs set
  by hand);
- it multiplies with the other cross kinds under the cap of 6;
- a state naming its design is that design's cell; beside a ``designs=``
  cross that is refused by name, and an unnamed state multiplies with it;
- every setting the run would silently undo or never make is refused by
  name: a knob the design lacks, the swept knob, the family's knob, a held
  knob, the density knob, and two states alike;
- ``to_code`` prints states back and ``eval`` of that text is the value.
"""

from __future__ import annotations

import csv
import dataclasses
import importlib
import itertools
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import studies
from antennaknobs.cli import cli, get_builder

sw = importlib.import_module("antennaknobs.sweep")

INVVEE = "dipoles.invvee"
APEX = "dipoles.invvee_apex"
DOUBLET = "wire.doublet_ladder_tuner"
REL = 1e-9


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


def _invvee():
    return get_builder(INVVEE)()


def _offer(monkeypatch, analyses):
    monkeypatch.setattr(type(_invvee()), "build_analyses", lambda self: list(analyses))


def _capture_run(monkeypatch):
    got = []
    inner = ar.run

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        got.append(out)
        return out

    monkeypatch.setattr(ar, "run", wrapped)
    return got


def _record(monkeypatch, module, name):
    calls = []
    inner = getattr(module, name)

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        calls.append((args, kwargs, out))
        return out

    monkeypatch.setattr(module, name, wrapped)
    return calls


def _lf(**kw) -> an.Analysis:
    """A small knob sweep, crossed over ``kw``'s states."""
    return an.Analysis(
        kw.pop("name", "lf"),
        an.Sweep("length_factor", 0.95, 1.0, points=3),
        cross=kw.pop("cross", ()),
        **kw,
    )


# ── the value ────────────────────────────────────────────────────────────


def test_a_state_keeps_its_knobs_in_the_order_written():
    st = an.State("tall, narrow", base=12.0, angle_deg=20)
    assert st.name == "tall, narrow" and st.design is None
    assert st.knobs == (("base", 12.0), ("angle_deg", 20))
    assert st.settings == {"base": 12.0, "angle_deg": 20}
    assert st.label == "tall, narrow"
    apex = an.State("tall", design=APEX, base=12.0)
    assert apex.label == f"{APEX}, tall"
    # Frozen and hashable, as every spec value is.
    assert len({st, an.State("tall, narrow", base=12.0, angle_deg=20)}) == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        st.name = "x"


@pytest.mark.parametrize(
    ("make", "err", "words"),
    [
        (lambda: an.State(""), TypeError, "name is a non-empty string"),
        (lambda: an.State("x", design=""), TypeError, "design is a registry name"),
        # A tuple is a group knob's value since unit 4; an empty one, or one
        # mixing entries and plain values, is no value at all.
        (lambda: an.State("x", base=[]), TypeError, "base takes a number"),
        (lambda: an.State("x", base=[{"f": 1}, 2]), TypeError, "base takes a number"),
        (lambda: an.State("x", base=float("nan")), TypeError, "base takes a number"),
        (lambda: an.State("x", ui_params={}), ValueError, "ui_params is not a knob"),
        (
            lambda: an.Cross(states=("tall",)),
            TypeError,
            "states holds an.State values",
        ),
        (
            lambda: an.Cross(states=(an.State("a"),), designs=(INVVEE,)),
            ValueError,
            "give exactly one of engines, grounds, planes, designs, states, cells or step",
        ),
    ],
)
def test_a_malformed_state_is_refused_when_built(make, err, words):
    with pytest.raises(err, match=words):
        make()


def test_states_print_back_as_code_and_eval_to_the_same_value():
    a = an.band_swr(
        name="heights",
        cross=(
            an.Cross(
                states=(
                    an.State("as built"),
                    an.State("low", base=5.0),
                    an.State("apex, tall", design=APEX, base=12, angle_deg=20.5),
                    an.State("flagged", note="x", flat=True),
                )
            ),
            an.Cross(engines=("momwire:bspline",)),
        ),
    )
    code = an.to_code(a)
    assert 'an.State("as built")' in code
    assert 'an.State("low", base=5.0)' in code
    assert an.to_code(an.State("apex, tall", design=APEX, base=12, angle_deg=20.5)) == (
        f'an.State("apex, tall", design="{APEX}", base=12, angle_deg=20.5)'
    )
    back = eval(code, {"an": an})
    assert back == a
    # The knobs' order and types survive: 12 stays an int, 5.0 a float.
    (st,) = [s for s in an.states_of(back) if s.name == "apex, tall"]
    assert st.knobs == (("base", 12), ("angle_deg", 20.5))
    assert type(st.settings["base"]) is int


# ── refused when listed, each by name ────────────────────────────────────


def test_every_setting_a_run_would_undo_or_never_make_is_refused_by_name():
    b = _invvee()
    cases = {
        "missing": (
            _lf(cross=an.Cross(states=(an.State("typo", hieght=3.0),))),
            "REFUSED: state 'typo' sets hieght, and this design has no knob 'hieght'",
        ),
        "swept by role": (
            an.Analysis(
                "h",
                an.Sweep("base", 2, 20, points=3),
                cross=an.Cross(states=(an.State("tall", base=12.0),)),
            ),
            "REFUSED: state 'tall' sets base, which the analysis sweeps; a knob "
            "is swept or set by a state, not both",
        ),
        "swept frequency": (
            an.band_swr(cross=an.Cross(states=(an.State("f", freq=28.0),))),
            "REFUSED: state 'f' sets freq, which the analysis sweeps; a knob is "
            "swept or set by a state, not both",
        ),
        "stepped": (
            _lf(
                cross=(
                    an.Cross(step=an.Sweep("angle_deg", values=(0, 30))),
                    an.Cross(states=(an.State("droop", angle_deg=45),)),
                )
            ),
            "REFUSED: state 'droop' sets angle_deg, which the family steps; a "
            "knob is stepped or set by a state, not both",
        ),
        "held": (
            an.Analysis(
                "held",
                an.Sweep("base", 2, 20, points=3),
                hold=an.Hold("resonance", adjust=("length_factor",)),
                views=(an.Rx(), an.Knobs()),
                cross=an.Cross(states=(an.State("long", length_factor=1.0),)),
            ),
            "REFUSED: state 'long' sets length_factor, which the hold adjusts "
            "at every point; a knob is held or set by a state, not both",
        ),
        "density ladder": (
            an.convergence(
                cross=an.Cross(states=(an.State("fine", nominal_nsegs=41),))
            ),
            "REFUSED: state 'fine' sets nominal_nsegs, the density knob: the "
            "ladder sweeps it; a state is one setting of the other knobs",
        ),
        "density off the ladder": (
            an.band_swr(cross=an.Cross(states=(an.State("fine", nominal_nsegs=41),))),
            "REFUSED: state 'fine' sets nominal_nsegs, the density knob: the "
            "engine holds a sweep at its own density, so the setting would be "
            "undone at every solve",
        ),
        "twice": (
            _lf(cross=an.Cross(states=(an.State("a", base=5.0), an.State("a")))),
            "REFUSED: the cross over states names 'a' twice",
        ),
        "named and crossed": (
            _lf(
                cross=(
                    an.Cross(designs=(INVVEE, APEX)),
                    an.Cross(states=(an.State("tall", design=APEX, base=12.0),)),
                )
            ),
            f"REFUSED: the states '{APEX}, tall' name their design, and the "
            "analysis also crosses designs=, which would multiply them again; "
            "give every state its design= and drop the designs cross, or drop "
            "design= and let the cross carry the designs",
        ),
    }
    for case, (a, want) in cases.items():
        assert an.problems(a, b) == [want], case
    # A problem lists the analysis as not runnable in the CLI too.
    lines = "\n".join(ar.list_lines(b))
    assert "height states" in lines


def test_one_name_on_two_designs_is_two_states():
    # A state is found by its label (design, name): "as built" on each of
    # two designs is two curves, not a name used twice.
    a = _lf(
        cross=an.Cross(
            states=(
                an.State("as built", design=INVVEE),
                an.State("as built", design=APEX),
            )
        )
    )
    assert an.problems(a, _invvee()) == []


def test_states_multiply_with_the_other_kinds_under_the_cap():
    b = _invvee()
    three = an.Cross(
        states=(
            an.State("as built"),
            an.State("low", base=5.0),
            an.State("tall", base=12.0),
        )
    )
    six = _lf(cross=(three, an.Cross(engines=("momwire:bspline", "momwire:razor-2p"))))
    assert six.curves == 6 and an.problems(six, b) == []
    nine = _lf(
        cross=(three, an.Cross(grounds=("free", "finite:13,0.005", "finite:5,0.001")))
    )
    assert an.problems(nine, b) == [
        "REFUSED: 3 states x 3 grounds = 9 curves, over the cap of 6"
    ]
    assert "3 states" in ar.summary(six, b)


def test_cells_label_by_state_name_and_by_design_where_a_state_names_one():
    b = _invvee()
    a = _lf(
        cross=(
            an.Cross(
                states=(
                    an.State("as built"),
                    an.State("apex, tall", design=APEX, base=12.0),
                )
            ),
            an.Cross(engines=("momwire:bspline", "nec2")),
        )
    )
    got = ar.cells(a, "momwire", b)
    assert [c.label for c in got] == [
        "as built, momwire:bspline",
        "as built, nec2",
        f"{APEX}, apex, tall, momwire:bspline",
        f"{APEX}, apex, tall, nec2",
    ]
    assert [c.design for c in got] == [None, None, APEX, APEX]
    assert got[2].state == an.State("apex, tall", design=APEX, base=12.0)
    # An unnamed state multiplies with a designs cross: set on each design.
    crossed = _lf(
        cross=(
            an.Cross(designs=(INVVEE, APEX)),
            an.Cross(states=(an.State("low", base=5.0), an.State("tall", base=12.0))),
        )
    )
    got = ar.cells(crossed, "momwire", b)
    assert [(c.label, c.design, c.state.name) for c in got] == [
        (f"{INVVEE}, low", INVVEE, "low"),
        (f"{INVVEE}, tall", INVVEE, "tall"),
        (f"{APEX}, low", APEX, "low"),
        (f"{APEX}, tall", APEX, "tall"),
    ]
    assert an.problems(crossed, b) == []


# ── studies: states name designs ──────────────────────────────────────────


def _collect(fn, host=None):
    return studies._collect("t.states", fn, None, host=host)


def test_a_study_may_name_its_designs_by_its_states():
    a = _lf(
        name="apex vs vee, tall",
        cross=an.Cross(
            states=(
                an.State("vee, tall", design=INVVEE, base=12.0),
                an.State("apex, tall", design=APEX, base=12.0),
            )
        ),
    )
    found, blocked = _collect(lambda: [a])
    assert blocked == [] and [s.designs for s in found] == [(INVVEE, APEX)]
    assert found[0].includes(APEX) and found[0].includes(INVVEE)
    assert not found[0].includes("dipoles.fan_dipole")


def test_a_module_study_refuses_a_state_with_no_design_by_name():
    a = _lf(
        name="loose",
        cross=an.Cross(
            states=(an.State("apex", design=APEX), an.State("tall", base=12.0))
        ),
    )
    found, blocked = _collect(lambda: [a])
    assert found == []
    (b,) = blocked
    assert b.name == "loose"
    assert b.reason == (
        "REFUSED: the states 'tall' name no design, and a study has no 'this "
        "design' to set them on; give each its design=, or cross designs=(...) "
        "to set them on every design"
    )
    # Beside a designs cross, the unnamed state is set on every design.
    ok = _lf(
        name="ok",
        cross=(
            an.Cross(designs=(INVVEE, APEX)),
            an.Cross(states=(an.State("t", base=12.0),)),
        ),
    )
    found, blocked = _collect(lambda: [ok])
    assert blocked == [] and found[0].designs == (INVVEE, APEX)


def test_a_method_study_sets_its_unnamed_states_on_its_own_design():
    a = _lf(
        name="vs apex",
        cross=an.Cross(
            states=(an.State("mine, tall", base=12.0), an.State("apex", design=APEX))
        ),
    )
    found, blocked = _collect(lambda: [a], host=INVVEE)
    assert blocked == []
    (st,) = found
    assert st.designs == (INVVEE, APEX) and st.includes(INVVEE)
    assert not st.includes(APEX)  # a method study is its own tab's only


# ── the CLI: a state cell IS the design with those knobs set ─────────────


def test_each_state_curve_is_bit_equal_to_the_sweep_with_those_knobs_set(
    monkeypatch, capsys, tmp_path
):
    states = (
        an.State("as built"),
        an.State("flat, low", angle_deg=0, base=5.0),
        an.State("droop", angle_deg=60),
    )
    a = _lf(name="st", cross=an.Cross(states=states), views=(an.Rx(), an.Table()))
    _offer(monkeypatch, [a])
    runs = _capture_run(monkeypatch)
    overlay = _record(monkeypatch, sw, "_rx_overlay")
    cli(["analyze", "--builder", INVVEE, "--analysis", "st", "--ground", "finite-fast",
         "--engine", "momwire:bspline", "--fn", str(tmp_path / "a.png")])  # fmt: skip
    out = capsys.readouterr().out
    got = runs[0]["curves"]
    labels = ["as built", "flat, low", "droop"]
    assert list(got) == labels
    assert [row[0] for row in overlay[0][0][0]] == labels  # the legend
    for label in labels:
        assert f"== length_factor sweep: {label} ==" in out
    calls = _record(monkeypatch, sw, "_solve_at")
    for st in states:
        calls.clear()
        sets = [f"{k}={v}" for k, v in st.knobs]
        cli(["sweep", "--builder", INVVEE, "--param", "length_factor",
             "--range", "0.95", "1.0", "--npoints", "3", "--ground", "finite-fast",
             "--engine", "momwire:bspline",
             *(["--set", *sets] if sets else []),
             "--fn", str(tmp_path / "s.png")])  # fmt: skip
        capsys.readouterr()
        (want,) = [c for c in calls if len(c[0][2])]
        assert list(want[0][2]) == got[st.name][0]
        # Bit-equal: the same builder state reaches the same solve.
        assert got[st.name][1] == [z[0] for z in want[2]], st.name
    # Adversarial: the three settings are three different antennas.
    r_mid = [got[label][1][1].real for label in labels]
    assert min(abs(x - y) for x, y in itertools.pairwise(r_mid)) > 1.0, r_mid


def test_a_state_sets_over_the_defaults_not_over_an_earlier_cells_knobs(
    monkeypatch, capsys, tmp_path
):
    """Each state cell is a fresh builder: "as built" after "low" is the
    design's own 7 m, not 5 m left over (a shared builder would pass the
    per-state check above only in written order)."""
    states = (an.State("low", base=5.0), an.State("as built"))
    a = _lf(name="order", cross=an.Cross(states=states))
    _offer(monkeypatch, [a])
    runs = _capture_run(monkeypatch)
    cli(["analyze", "--builder", INVVEE, "--analysis", "order", "--ground",
         "finite-fast", "--engine", "momwire:bspline",
         "--fn", str(tmp_path / "o.png")])  # fmt: skip
    capsys.readouterr()
    solo = an.Analysis("solo", a.sweep)
    _offer(monkeypatch, [solo])
    cli(["analyze", "--builder", INVVEE, "--analysis", "solo", "--ground",
         "finite-fast", "--engine", "momwire:bspline",
         "--fn", str(tmp_path / "p.png")])  # fmt: skip
    capsys.readouterr()
    (solo_z,) = [z for _, z in runs[1]["curves"].values()]
    assert runs[0]["curves"]["as built"][1] == solo_z
    assert runs[0]["curves"]["low"][1] != solo_z


def test_a_state_on_a_design_that_lacks_its_knob_is_a_named_refused_cell(
    monkeypatch, capsys, tmp_path
):
    """An unnamed state beside a designs cross is set on each design; the
    one lacking its knob (the vee has no feed line) is refused by name, and
    the other runs."""
    a = _lf(
        name="lack",
        cross=(
            an.Cross(designs=(INVVEE, DOUBLET)),
            an.Cross(states=(an.State("long line", line_len_m=20.0),)),
        ),
    )
    assert an.problems(a, _invvee()) == []  # per cell, not per analysis
    _offer(monkeypatch, [a])
    runs = _capture_run(monkeypatch)
    cli(["analyze", "--builder", INVVEE, "--analysis", "lack", "--ground", "free",
         "--engine", "momwire:bspline", "--fn", str(tmp_path / "l.png")])  # fmt: skip
    out = capsys.readouterr().out
    why = "state 'long line' sets line_len_m, and this design has no knob 'line_len_m'"
    assert runs[0]["refused"] == {f"{INVVEE}, long line": why}
    assert f"{INVVEE}, long line: refused: {why}" in out
    assert list(runs[0]["curves"]) == [f"{DOUBLET}, long line"]


def test_analyze_csv_writes_a_column_group_per_state(monkeypatch, tmp_path):
    a = an.band_swr(
        name="csv states",
        sweep=an.Sweep(an.FREQUENCY, 28.0, 29.0, points=3),
        cross=an.Cross(states=(an.State("as built"), an.State("tall", base=12.0))),
        ground="finite-fast",
    )
    _offer(monkeypatch, [a])
    out = tmp_path / "s.csv"
    cli(["analyze", "--builder", INVVEE, "--analysis", "csv states",
         "--engine", "momwire:bspline", "--csv", str(out), "--fn", "/dev/null"])  # fmt: skip
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == [
        "MHz",
        "as built R_ohm",
        "as built X_ohm",
        "as built SWR",
        "tall R_ohm",
        "tall X_ohm",
        "tall SWR",
    ]
    assert [float(r[0]) for r in rows[1:]] == [28.0, 28.5, 29.0]
    # Over ground the height moves the feed impedance.
    assert all(float(r[1]) != float(r[4]) for r in rows[1:])


def test_analyze_code_prints_the_states_back(capsys):
    cli(["analyze", "--builder", INVVEE, "--analysis", "height states", "--code"])
    code = capsys.readouterr().out
    assert 'an.State("low mast", base=5.0)' in code
    a = eval(code, {"an": an})
    assert [s.name for s in an.states_of(a)] == ["as built", "low mast", "tall mast"]


def test_the_catalog_height_states_analysis_lists_runnable():
    b = _invvee()
    (a,) = [x for x in an.offered(b) if x.name == "height states"]
    assert an.problems(a, b) == [] and ar.cli_gaps(a, b) == []
    assert "3 curves (3 states)" in ar.summary(a, b)


# ── the workbench: /analyses serves each state as the CLI's cell ──────────


def _served(client, req, name) -> dict:
    r = client.post("/analyses", json=req)
    assert r.status_code == 200, r.text
    (entry,) = [x for x in r.json()["analyses"] if x["name"] == name]
    return entry["workbench"]


def _records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _defaults(client, geometry) -> dict:
    (ex,) = [
        e for e in client.get("/examples").json()["examples"] if e["name"] == geometry
    ]
    return {
        p["name"]: p["default"]
        for p in ex["param_schema"]
        if "default" in p and "params" not in p
    }


def test_the_catalog_height_states_serve_one_cell_per_state(client):
    w = _served(client, {"geometry": INVVEE}, "height states")
    assert w["runs"] is True and w["kind"] == "frequency"
    assert w["axes"] == ["states"] and w["grounds"] == ["finite-fast"]
    got = [(s["name"], s["design"], s["knobs"], s["label"]) for s in w["states"]]
    assert got == [
        ("as built", None, {}, "as built"),
        ("low mast", None, {"base": 5.0}, "low mast"),
        ("tall mast", None, {"base": 12.0}, "tall mast"),
    ]
    (a,) = [x for x in an.offered(_invvee()) if x.name == "height states"]
    for s in w["states"]:
        assert s["refused"] is None and s["on"] is None
        # Exactly the grid `analyze` sweeps on that cell's builder.
        cell = _invvee()
        for k, v in s["knobs"].items():
            setattr(cell, k, v)
        assert s["freqs"] == [float(x) for x in ar.frequency_xs(a.sweep, cell)]
        assert len(s["freqs"]) == 26


def test_a_state_is_set_over_the_defaults_not_the_tabs_live_knobs(monkeypatch, client):
    """The tab has dragged the measurement frequency to 14 MHz (and the mast
    to 3 m). The design's own band is the default window around ``freq``, so
    a band follows whatever ``freq`` the builder holds: the served "as
    built" state stays on the design's own 28.47 MHz band, the grid
    ``analyze`` sweeps, not one around the live 14."""
    states = an.band_swr(name="states", cross=an.Cross(states=(an.State("as built"),)))
    _offer(monkeypatch, [states])
    req = {"geometry": INVVEE, "freq": 14.0, "base": 3.0}
    (s,) = _served(client, req, "states")["states"]
    fresh = _invvee()
    assert s["freqs"] == [float(x) for x in ar.frequency_xs(states.sweep, fresh)]
    assert min(s["freqs"]) > 20.0, s["freqs"]
    live = _invvee()
    live.freq = 14.0
    assert max(ar.frequency_xs(states.sweep, live)) < 20.0  # what live would be


def test_served_states_name_their_refusals_and_their_designs(monkeypatch, client):
    crossed = _lf(
        name="crossed",
        cross=(
            an.Cross(designs=(INVVEE, DOUBLET)),
            an.Cross(states=(an.State("long line", line_len_m=20.0),)),
        ),
    )
    named = _lf(
        name="named",
        cross=an.Cross(states=(an.State("apex, tall", design=APEX, base=12.0),)),
    )
    _offer(monkeypatch, [crossed, named])
    w = _served(client, {"geometry": INVVEE}, "crossed")
    assert w["axes"] == ["designs", "states"]
    (s,) = w["states"]
    assert s["refused"] is None and s["freqs"] is None and s["values"] is None
    assert [(o["name"], o["refused"]) for o in s["on"]] == [
        (
            INVVEE,
            "state 'long line' sets line_len_m, and this design has no knob "
            "'line_len_m'",
        ),
        (DOUBLET, None),
    ]
    w = _served(client, {"geometry": INVVEE}, "named")
    (s,) = w["states"]
    assert (s["design"], s["label"], s["refused"]) == (
        APEX,
        f"{APEX}, apex, tall",
        None,
    )
    assert s["param"] == "length_factor" and len(s["values"]) == 3


def test_a_served_state_cell_is_the_clis_curve_for_that_state(
    monkeypatch, client, capsys, tmp_path
):
    states = (an.State("as built"), an.State("tall", base=12.0, angle_deg=45))
    a = _lf(name="st", cross=an.Cross(states=states))
    _offer(monkeypatch, [a])
    w = _served(client, {"geometry": INVVEE}, "st")
    runs = _capture_run(monkeypatch)
    cli(["analyze", "--builder", INVVEE, "--analysis", "st", "--ground", "free",
         "--engine", "momwire:bspline", "--nominal-nsegs", "15",
         "--fn", str(tmp_path / "w.png")])  # fmt: skip
    capsys.readouterr()
    worst = 0.0
    for s in w["states"]:
        xs, want = runs[0]["curves"][s["label"]]
        assert s["values"] == [float(x) for x in xs]
        # The chart's state cell: the design's defaults, the state's knobs.
        body = {
            "geometry": INVVEE,
            **_defaults(client, INVVEE),
            **s["knobs"],
            "design_freq_mhz": 28.47,
            "measurement_freq_mhz": 28.47,
            "solver": "momwire",
            "momwire_model": "bspline",
            "n_per_wire": 15,
            "ground": False,
            "param": s["param"],
            "values": s["values"],
        }
        recs = _records(client.post("/param_sweep", json=body).text)[:-1]
        got = [complex(r["z_re"], r["z_im"]) for r in recs]
        worst = max(worst, float(np.max(np.abs(np.subtract(got, want)) / np.abs(want))))
    assert worst <= REL, worst


def test_a_served_state_cell_is_the_clis_curve_over_finite_fast(
    monkeypatch, client, capsys, tmp_path
):
    """AK#1825: the free-space gate above, over ``finite-fast``. The two
    paths build one ground (refl-coef, 13 / 0.005), so they agree as they do
    in free space. The issue's 51.531−10.776j vs 51.540−10.759j is the tall
    mast at N=15 on refl-coef vs SOMMERFELD (measured 2026-10-04): a request
    with the ground on and no ``ground_model`` gets the built-in method,
    Sommerfeld since AK#1856, so the cell has to name "fast" — which the
    chart's ground slot does (``groundSpecHeld`` matches the method)."""
    states = (an.State("as built"), an.State("tall", base=12.0))
    a = _lf(name="st", cross=an.Cross(states=states))
    _offer(monkeypatch, [a])
    w = _served(client, {"geometry": INVVEE}, "st")
    runs = _capture_run(monkeypatch)
    cli(["analyze", "--builder", INVVEE, "--analysis", "st",
         "--ground", "finite-fast", "--engine", "momwire:bspline",
         "--nominal-nsegs", "15", "--fn", str(tmp_path / "w.png")])  # fmt: skip
    capsys.readouterr()
    worst = 0.0
    for s in w["states"]:
        xs, want = runs[0]["curves"][s["label"]]
        body = {
            "geometry": INVVEE,
            **_defaults(client, INVVEE),
            **s["knobs"],
            "design_freq_mhz": 28.47,
            "measurement_freq_mhz": 28.47,
            "solver": "momwire",
            "momwire_model": "bspline",
            "n_per_wire": 15,
            "ground": True,
            "ground_model": "fast",
            "param": s["param"],
            "values": s["values"],
        }
        recs = _records(client.post("/param_sweep", json=body).text)[:-1]
        got = [complex(r["z_re"], r["z_im"]) for r in recs]
        worst = max(worst, float(np.max(np.abs(np.subtract(got, want)) / np.abs(want))))
        # The other method is a different answer, not a rounding of this one.
        body["ground_model"] = "sommerfeld"
        recs = _records(client.post("/param_sweep", json=body).text)[:-1]
        somm = [complex(r["z_re"], r["z_im"]) for r in recs]
        assert np.max(np.abs(np.subtract(somm, want))) > 1e-3
    assert worst <= REL, worst


def _docs_states_blocks() -> list[str]:
    page = (
        Path(__file__).resolve().parents[1] / "site/src/content/docs/reference/cli.md"
    )
    text = page.read_text(encoding="utf-8")
    section = text[text.index("### States") : text.index("### Maps")]
    return section.split("```python\n")[1:]


def test_the_docs_states_examples_are_the_catalogs_and_a_runnable_study():
    """The CLI reference's States section: its first block is the catalog's
    ``height states`` as ``--code`` prints it, and its study example is
    found, crossing the two designs its states name."""
    blocks = [b.split("```")[0] for b in _docs_states_blocks()]
    (a,) = [x for x in an.offered(_invvee()) if x.name == "height states"]
    assert blocks[0].strip() == an.to_code(a)
    ns = {"an": an}
    exec(blocks[1], ns)
    found, blocked = _collect(ns["build_studies"])
    assert blocked == []
    (st,) = found
    assert st.designs == (INVVEE, APEX)
    assert [c.label for c in ar.cells(st.analysis, "momwire", _invvee())] == [
        f"{INVVEE}, bridge",
        f"{APEX}, apex",
    ]
