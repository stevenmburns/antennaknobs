"""A self-tuning tuner measured at its tune frequency makes every match
objective degenerate, and the optimizer and the tracker refuse it (AK#1664).

There the driven port reads the tuner's target on every solve, so SWR,
resonance and match-to-Z0 are met whatever the knobs do: the optimizer would
descend a flat surface and the tracker's tangent would be zero. One band edge
away the tuner holds its parts, and the same request must still run.

The seam cases build a web example from the catalog skyloop with its L-match
swapped for the tuner, so the refusal is driven by what the real engine says
on the real solve response, not by a stub.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_l_tuner_tune_1646 import _skyloop

import antennaknobs.web.examples  # noqa: F401  registration order
from antennaknobs.designs.loops.skyloop_lmatch import Builder as FixedSkyloop
from antennaknobs.web import server
from antennaknobs.web.adapter import _make_example
from antennaknobs.web.optimize import DegenerateObjective, optimize, tuner_refusal
from antennaknobs.web.tracker import Tracker

F0 = 3.8  # the skyloop's design frequency, where the tuner tunes
FREE = [{"name": "length_factor", "min": 0.95, "max": 1.15}]


@pytest.fixture(scope="module")
def tuned():
    return _make_example("SkyloopTuned1664", type(_skyloop()))


def _req(meas):
    return {"measurement_freq_mhz": meas, "design_freq_mhz": F0}


def test_the_solve_says_when_the_tuner_holds_the_match(tuned):
    assert tuned.momwire_solve(_req(F0))["tuner_holds_match"] == {
        "name": "match",
        "f_mhz": F0,
    }
    assert tuned.momwire_solve(_req(1.03 * F0))["tuner_holds_match"] is None


def test_fixed_values_are_not_a_tuner():
    fixed = _make_example("SkyloopFixed1664", FixedSkyloop)
    assert fixed.momwire_solve(_req(F0))["tuner_holds_match"] is None


@pytest.mark.parametrize("objective", ["swr", "resonance", "match_z0"])
def test_the_optimizer_refuses_at_the_tune_frequency(tuned, objective):
    free = FREE + [{"name": "base", "min": 12.0, "max": 18.0}]
    free = free[: 2 if objective == "match_z0" else 1]
    calls = []

    def solve(r):
        calls.append(r)
        return tuned.momwire_solve(r)

    with pytest.raises(DegenerateObjective) as err:
        optimize(_req(F0), free, objective, solve_fn=solve)
    msg = str(err.value)
    assert "Tuner match" in msg and f"{F0:g} MHz" in msg
    for way_out in ("another frequency", "fixed part values", "something other"):
        assert way_out in msg
    assert len(calls) == 1, "refused on the first solve, before any search"


def test_one_band_edge_away_it_runs_and_the_objective_moves(tuned):
    seen = []
    res = optimize(
        _req(1.03 * F0),
        FREE,
        "swr",
        solve_fn=tuned.momwire_solve,
        max_evals=6,
        on_progress=lambda p: seen.append(p["objective"]),
    )
    assert res["objective_before"] > 1.01
    assert max(seen) - min(seen) > 1e-3


def test_the_tracker_refuses_at_the_tune_frequency(tuned):
    tr = Tracker(_req(F0), FREE, "resonance", solve_fn=tuned.momwire_solve)
    st = tr.start("base", 15.0)
    assert st["status"] == "refused"
    assert "Tuner match" in st["message"]
    assert tr.n_solves == 1
    # And it stays refused as the drag goes on.
    assert tr.tick(15.5)["status"] == "refused"


def test_the_tracker_enters_one_band_edge_away(tuned):
    tr = Tracker(_req(1.03 * F0), FREE, "resonance", solve_fn=tuned.momwire_solve)
    assert tr.start("base", 15.0)["status"] != "refused"


def test_no_field_no_refusal():
    assert tuner_refusal({}, "swr") is None
    assert tuner_refusal({"tuner_holds_match": None}, "swr") is None


def test_the_endpoint_says_it_in_words(tuned, monkeypatch):
    monkeypatch.setitem(server.EXAMPLES, "test.skyloop_tuned_1664", tuned)
    client = TestClient(server.app)
    body = {
        "geometry": "test.skyloop_tuned_1664",
        **_req(F0),
        "optimize": {"free": FREE, "objective": "swr"},
    }
    out = client.post("/optimize", json=body).json()
    assert out["error"].startswith("Tuner match retunes on every solve")
    stream = client.post(
        "/optimize", json=body, headers={"accept": "text/event-stream"}
    ).text
    assert "event: error" in stream and "Tuner match retunes" in stream
