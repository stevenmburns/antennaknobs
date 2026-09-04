"""The frontend's generated option-spec and kwarg fixtures match what we serve.

Same argument as `test_frontend_constraint_fixture.py` beside it, and the same
evidence: a generated file with no regeneration gate is a copy, and the
constraint fixture next door had already gone stale silently through a pointer
move while every frontend test stayed green.

Two fixtures are pinned here.

`optionSpecFixtures.ts` mirrors `model_option_specs()` — the catalogue a
generic renderer draws from. A stale bound here is worse than a stale
constraint: the UI would offer a value the hosted sanitiser then rejects, so
the control looks available and fails on solve.

The kwarg tuples in `backendFixtures.ts` mirror `_BackendSpec.model_kwargs`,
which the server measures BY CONSTRUCTION. If the fixture drifted, the
frontend's offered-vs-sent tests would be reasoning about a backend surface
that does not exist.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web.adapter import backend_roster, model_option_specs

FRONTEND = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/antennaknobs/web/frontend/src/__tests__"
)
SPEC_FIXTURE = FRONTEND / "optionSpecFixtures.ts"
ROSTER_FIXTURE = FRONTEND / "backendFixtures.ts"

REGENERATE = "Regenerate it — the command is in the fixture's header comment."


def _json_after(src: str, marker: str) -> object:
    assert marker in src, f"fixture no longer declares {marker}"
    body = src[src.index(marker) :]
    body = body[body.index("=") + 1 :].strip()
    assert body.endswith(";"), "fixture body is not the expected `= <json>;` shape"
    return json.loads(body[:-1])


def test_the_option_spec_fixture_matches_the_served_catalogue():
    fx = _json_after(SPEC_FIXTURE.read_text(), "export const SERVED_OPTION_SPECS")
    live = model_option_specs()
    assert fx, "fixture parsed as empty — the comparison below would be vacuous"
    assert live
    assert set(fx) == set(live), (
        f"fixture and server disagree on WHICH options exist: "
        f"{sorted(set(fx) ^ set(live))}. {REGENERATE}"
    )
    assert fx == live, f"option spec fixture is stale. {REGENERATE}"


@pytest.mark.parametrize("key", sorted(model_option_specs()))
def test_each_served_bound_reaches_the_fixture_unchanged(key):
    """Per-key so a failure names the knob.

    Bounds specifically, because a widened one in the fixture would let a
    frontend test assert a control the hosted sanitiser rejects — the UI
    offering a value the server refuses is the failure with a user on the
    other end of it.
    """
    fx = _json_after(SPEC_FIXTURE.read_text(), "export const SERVED_OPTION_SPECS")
    assert fx[key] == model_option_specs()[key], f"{key} is stale. {REGENERATE}"


def _ts_tuple(src: str, name: str) -> list[str]:
    m = re.search(rf"const {name} = (\[[^\]]*\]);", src)
    assert m, f"{name} not found in {ROSTER_FIXTURE}"
    return json.loads(m.group(1))


def test_the_kwarg_tuples_match_what_the_server_measured():
    """The families share tuples on both sides, so this checks the SHARING as
    well as the contents — three separate literals would be the drift."""
    src = ROSTER_FIXTURE.read_text()
    live = {
        r["name"]: r["model_kwargs"]
        for r in backend_roster(have_pynec=True, have_nec5=True)
    }
    assert (
        _ts_tuple(src, "SIN_KWARGS")
        == live["sinusoidal"]
        == live["sinusoidal-galerkin"]
    )
    assert (
        _ts_tuple(src, "BSPLINE_KWARGS")
        == live["bspline"]
        == live["hmatrix"]
        == live["arrayblock"]
    )
    assert _ts_tuple(src, "RAZOR_KWARGS") == live["razor-2p"]


def test_the_two_facts_the_offered_vs_sent_rule_depends_on_are_still_true():
    """The frontend's rule-2 tests assert `feed_model` stays unoffered on
    bspline and `degree` on razor-2p. Both rest on server facts that live
    here, so if either changed, those tests would be asserting the absence of
    a control for a reason that had evaporated — passing, and meaningless.
    """
    live = {r["name"]: r for r in backend_roster(have_pynec=True, have_nec5=True)}
    assert "feed_model" in live["bspline"]["model_kwargs"]
    assert live["bspline"]["axes"]["feed_model"] == ["segment-gap"]
    assert "degree" in live["razor-2p"]["model_kwargs"]
    assert live["razor-2p"]["axes"]["basis"] == ["tent"]
