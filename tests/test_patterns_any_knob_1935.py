"""AK#1935: patterns across any knob, the "Sweep a knob" chart's pattern views.

Steve (2026-10-06): rather than special-casing "height patterns", let any knob
drive a family of patterns. The chart turns its knob and range into a step
cross, ``an.patterns(cross=an.Cross(step=an.Sweep(knob, lo, hi, points=n)))``,
and asks ``/pattern_cell`` once per value. This file is the server's half
(the chart's is frontend ``patternFamily*.test.ts*``):

- **keep**: "copy as analysis" of a family sends ``family`` in place of a
  picked analysis's ``spec``; the kept text is ``to_code`` of exactly that
  analysis, and ``eval`` of it is the value (the round trip); a ladder off
  the range's own grid (an integer knob's rounding) is kept as ``values=``;
  more than the cap is refused;
- **the frequency step** (patterns across the band): ``/analyses`` serves a
  family over `an.FREQUENCY` (it used to refuse ``freq`` as a knob), and a
  workbench cell at a step frequency is the CLI's cell at that frequency,
  bit for bit;
- **an opened deck**: any SY knob is a family's knob, with no height
  detection; a synthetic SY deck (third-party decks are never committed)
  keeps a family over its ``hgh`` cleanly, and its cells move the pattern.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import keep
from antennaknobs.cli import cli, get_builder
from antennaknobs.web import decks, server

INVVEE = "dipoles.invvee"
ENGINE = "momwire:bspline"


@pytest.fixture()
def client(monkeypatch):
    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(0))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield TestClient(server.app)
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


def _keep(client, family: dict, tab: dict, **kw):
    body = {"origin": "chart", "form": "analysis", "spec": None, "family": family}
    return client.post("/keep", json={**body, "tab": tab, **kw})


# ── keep: the round trip ─────────────────────────────────────────────────────


def test_a_family_is_kept_as_its_patterns_analysis_and_round_trips(client):
    fam = {"knob": "base", "lo": 5, "hi": 15, "points": 3, "spacing": "lin"}
    got = _keep(client, fam, {"geometry": INVVEE}, name="base patterns")
    assert got.status_code == 200, got.text
    out = got.json()
    want = an.patterns(
        name="base patterns",
        cross=an.Cross(step=an.Sweep("base", 5, 15, points=3)),
    )
    assert out["code"] == an.to_code(want) + "\n"
    value = eval(out["code"], {"an": an})
    assert value == want
    # The round trip: the text is the value's own, and its data reads back.
    assert an.to_code(value) + "\n" == out["code"]
    assert an.from_data(an.to_data(value)) == value
    # It is about the tab's design, and the chart's values are its own.
    assert out["problems"] == []
    assert ar.step_values(value.crosses[0].step, get_builder(INVVEE)()) == [5, 10, 15]


def test_a_log_family_writes_its_spacing_and_an_off_grid_ladder_its_values():
    log = {"knob": "base", "lo": 2, "hi": 18, "points": 3, "spacing": "log"}
    a = keep.analysis_from_family(log)
    assert a.crosses[0].step == an.Sweep("base", 2.0, 18.0, points=3, spacing="log")
    # The page's values ON the grid keep the range (geometric 2, 6, 18).
    a = keep.analysis_from_family({**log, "values": [2, 6.000000000001, 18]})
    assert a.crosses[0].step.values is None
    # OFF it (an int knob's lin ladder rounded to whole values): values=.
    rounded = {"knob": "n", "lo": 1, "hi": 4, "points": 4, "spacing": "lin"}
    a = keep.analysis_from_family({**rounded, "values": [1, 2, 3, 4]})
    assert a.crosses[0].step == an.Sweep("n", 1.0, 4.0, points=4)
    a = keep.analysis_from_family({**rounded, "points": 3, "values": [1, 2, 4]})
    assert a.crosses[0].step == an.Sweep("n", values=(1, 2, 4))
    # Whole numbers print as whole numbers, as Steve writes them.
    assert 'an.Sweep("n", values=(1, 2, 4))' in an.to_code(a)


@pytest.mark.parametrize(
    ("family", "words"),
    [
        ({"knob": "base", "lo": 5, "hi": 15, "points": 7}, "over the cap of 6"),
        ({"knob": "", "lo": 5, "hi": 15, "points": 3}, "family.knob"),
        ({"knob": "base", "lo": "5", "hi": 15, "points": 3}, "family.lo"),
        ({"knob": "base", "lo": 5, "hi": 15, "points": 3, "spacing": "geo"}, "spacing"),
        ({"knob": "base", "lo": -5, "hi": 15, "points": 3, "spacing": "log"}, "log"),
        ([1, 2], "family is"),
    ],
)
def test_a_family_the_keep_cannot_write_is_refused_by_name(client, family, words):
    r = _keep(client, family, {"geometry": INVVEE})
    assert r.status_code == 422
    assert words in r.json()["detail"]


def test_a_family_kept_as_a_study_names_the_tab_and_leaves_the_stepped_knob_out(client):
    fam = {"knob": "base", "lo": 5, "hi": 15, "points": 3, "spacing": "lin"}
    tab = {"geometry": INVVEE, "base": 9.0, "angle_deg": 40.0}
    a, form, _o, _n = keep.build(
        {"origin": "chart", "form": "study", "family": fam, "tab": tab}
    )
    assert form == "study"
    states = an.states_of(a)
    assert [s.design for s in states] == [INVVEE]
    # The tab's knobs where they differ, less the one the family steps.
    assert "angle_deg" in states[0].settings and "base" not in states[0].settings


# ── the frequency step: patterns across the band ─────────────────────────────


def _offer(monkeypatch, analyses):
    monkeypatch.setattr(
        type(get_builder(INVVEE)()), "build_analyses", lambda self: list(analyses)
    )


FREQ_FAMILY = an.patterns(
    name="across the band",
    cross=an.Cross(step=an.Sweep(an.FREQUENCY, 28.0, 29.7, points=3)),
    views=(an.PatternTable(),),
)


def test_a_frequency_family_is_served_as_the_measurement_frequency(monkeypatch, client):
    _offer(monkeypatch, [FREQ_FAMILY])
    r = client.post("/analyses", json={"geometry": INVVEE})
    (entry,) = [a for a in r.json()["analyses"] if a["name"] == "across the band"]
    w = entry["workbench"]
    assert w["runs"] is True and w["kind"] == "pattern", w
    assert w["axes"] == ["step"]
    assert w["step"] == {
        "knob": "freq",
        "values": [28.0, 28.85, 29.7],
        "labels": ["freq = 28", "freq = 28.85", "freq = 29.7"],
    }
    # The CLI labels its cells alike.
    labels = [c.label for c in ar.cells(FREQ_FAMILY, ENGINE, get_builder(INVVEE)())]
    assert labels == w["step"]["labels"]


def test_a_frequency_family_over_bad_values_is_refused_by_name(monkeypatch, client):
    bad = an.patterns(
        name="bad", cross=an.Cross(step=an.Sweep(an.FREQUENCY, values=(28.0, -1.0)))
    )
    _offer(monkeypatch, [bad])
    r = client.post("/analyses", json={"geometry": INVVEE})
    (entry,) = [a for a in r.json()["analyses"] if a["name"] == "bad"]
    assert entry["workbench"]["runs"] is False
    assert "a frequency is above zero" in entry["workbench"]["why"]


def _cell_body(**over) -> dict:
    return {
        "geometry": INVVEE,
        "base": 12.0,
        "length_factor": 0.9719,
        "angle_deg": 31.6846,
        "design_freq_mhz": 28.47,
        "measurement_freq_mhz": 28.47,
        "solver": "momwire",
        "momwire_model": "bspline",
        "n_per_wire": 15,
        "ground": False,
        "elev_az_deg": 0,
        "az_elev_deg": 10,
        **over,
    }


@pytest.mark.antenna_computation_check
def test_a_frequency_cell_is_the_clis_cell_at_that_frequency(
    monkeypatch, client, capsys
):
    """The chart's family cell (the session's request, ``freq`` and the
    measurement frequency set to the step's value, as buildRequestFor sets
    them) and the CLI's (``freq`` set on the cell's builder): one solve,
    bit-equal metrics. Adversarial: the design's own frequency is not it."""
    a = an.patterns(
        name="f",
        cross=an.Cross(step=an.Sweep(an.FREQUENCY, values=(29.5,))),
        views=(an.PatternTable(),),
    )
    _offer(monkeypatch, [a])
    runs = []
    inner = ar._run_patterns

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        runs.append(out)
        return out

    monkeypatch.setattr(ar, "_run_patterns", wrapped)
    cli(["analyze", "--builder", INVVEE, "--analysis", "f", "--engine", ENGINE,
         "--nominal-nsegs", "15", "--ground", "free", "--fn", "/dev/null"])  # fmt: skip
    capsys.readouterr()
    cli_cell = runs[-1]["patterns"]["freq = 29.5"]
    assert cli_cell.freq == 29.5
    # The CLI's builder carries the design's own knobs: the chart's request
    # is the session's at those defaults.
    b = get_builder(INVVEE)()
    defaults = {k: getattr(b, k) for k in ("base", "length_factor", "angle_deg")}
    body = _cell_body(**defaults, freq=29.5, measurement_freq_mhz=29.5)
    web = client.post("/pattern_cell", json=body).json()["metrics"]
    # Not vacuous: the CLI cell carries the compare table's numbers.
    assert {"peak_gain_dbi", "takeoff_deg"} <= set(cli_cell.metrics)
    assert {k: web[k] for k in cli_cell.metrics} == cli_cell.metrics
    own = client.post("/pattern_cell", json=_cell_body(**defaults)).json()["metrics"]
    assert own["peak_gain_dbi"] != web["peak_gain_dbi"]


def test_the_cli_summary_of_a_frequency_family_has_the_knob_familys_shape(
    monkeypatch, capsys
):
    """``analyze``'s header for a family over the frequency reads as a knob
    family's: the knob as the cells label it (``freq``, not the role's
    "frequency"), and no "at <design frequency> MHz" clause, which no cell of
    it is solved at. A knob family keeps the clause (its cells are)."""
    fam = an.patterns(
        name="f",
        cross=an.Cross(step=an.Sweep(an.FREQUENCY, values=(28.0, 29.5))),
        views=(an.PatternTable(),),
    )
    knob = an.patterns(
        name="k",
        cross=an.Cross(step=an.Sweep("base", values=(6.0, 8.0))),
        views=(an.PatternTable(),),
    )
    b = get_builder(INVVEE)()
    freq_line = ar.summary(fam, b)
    assert freq_line.startswith("pattern; 2 patterns (2 values of freq); ")
    assert "(freq)" not in freq_line
    knob_line = ar.summary(knob, b)
    assert (
        knob_line.startswith("pattern at ")
        and "MHz (freq); 2 patterns (2 values of base)" in knob_line
    )
    # The run prints it, and a line per value.
    _offer(monkeypatch, [fam])
    cli(["analyze", "--builder", INVVEE, "--analysis", "f", "--engine", ENGINE,
         "--nominal-nsegs", "15", "--ground", "free", "--fn", "/dev/null"])  # fmt: skip
    out = capsys.readouterr().out
    assert "analysis 'f': pattern; 2 patterns (2 values of freq)" in out
    assert "  freq = 28: 28 MHz" in out and "  freq = 29.5: 29.5 MHz" in out


# ── an opened deck: any SY knob ──────────────────────────────────────────────

# A synthetic 20 m dipole whose height is an SY symbol (the shape of Dan's
# Example3 `hgh`; his deck is third-party and is not committed).
SY_DECK = """CM synthetic dipole at an SY height (AK#1935)
CE
SY hgh = 10
SY half = 5.1
GW 1 21 0 -half hgh 0 half hgh .001
GE 1
GN 1
EX 0 1 11 0 1 0
FR 0 1 0 0 14.1
EN
"""


def _open(client) -> tuple[str, dict]:
    r = client.post("/deck", json={"name": "syn.nec", "text": SY_DECK})
    assert r.status_code == 200, r.text
    return r.json()["key"], r.json()["example"]


def test_an_opened_decks_sy_knob_is_a_family_knob_with_no_height_detection(client):
    key, ex = _open(client)
    (hgh,) = [p for p in ex["param_schema"] if p.get("name") == "sy_hgh"]
    # A plain float knob (the chart's sweepable kind), with no role.
    assert hgh["kind"] == "float" and hgh["default"] == 10
    fam = {"knob": "sy_hgh", "lo": 5, "hi": 15, "points": 3, "spacing": "lin"}
    out = _keep(client, fam, {"geometry": key}).json()
    assert 'an.Sweep("sy_hgh", 5, 15, points=3)' in out["code"]
    assert out["problems"] == []
    value = eval(out["code"], {"an": an})
    from antennaknobs.web.analyses_offer import builder_for

    b = builder_for(server.EXAMPLES[key].builder_cls, {"geometry": key})
    assert ar.step_values(value.crosses[0].step, b) == [5, 10, 15]


@pytest.mark.antenna_computation_check
def test_a_deck_family_cell_moves_the_pattern_with_its_sy_knob(client):
    """Each family cell is the session's request with ``sy_hgh`` set, as the
    chart sends it: a dipole twice as high over ground fires lower."""
    key, _ex = _open(client)
    base = {
        "geometry": key,
        "solver": "momwire",
        "momwire_model": "bspline",
        "n_per_wire": 15,
        "ground": True,
        "ground_model": "pec",
        "design_freq_mhz": 14.1,
        "measurement_freq_mhz": 14.1,
        "elev_az_deg": 90,
        "az_elev_deg": 10,
    }
    low = client.post("/pattern_cell", json={**base, "sy_hgh": 7.0}).json()
    high = client.post("/pattern_cell", json={**base, "sy_hgh": 14.0}).json()
    assert low["available"] and high["available"], (low, high)
    assert high["metrics"]["takeoff_deg"] < low["metrics"]["takeoff_deg"]
