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
AXES_FIXTURE = FRONTEND / "axesFixtures.ts"

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
    # The sinusoidal pair no longer shares one tuple: the Galerkin member
    # exposes `feed_model` and the point-matched one must not, because it
    # REFUSES the point gap (momwire#212). They did share one, and that is
    # exactly what would have sent a point gap to the solver that raises.
    assert _ts_tuple(src, "SIN_KWARGS") == live["sinusoidal"]
    assert _ts_tuple(src, "SIN_GALERKIN_KWARGS") == live["sinusoidal-galerkin"]
    assert (
        _ts_tuple(src, "BSPLINE_KWARGS")
        == live["bspline"]
        == live["hmatrix"]
        == live["arrayblock"]
    )
    assert _ts_tuple(src, "RAZOR_KWARGS") == live["razor-2p"]


def test_the_accepted_but_unexposed_knobs_stay_unexposed():
    """The frontend's rule-2 tests assert `feed_model` never renders on
    bspline and `degree` never on razor-2p. Both now rest on EXPOSURE, so if
    either were exposed those tests would be asserting an absence for a reason
    that had evaporated — passing, and meaningless."""
    live = {r["name"]: r for r in backend_roster(have_pynec=True, have_nec5=True)}
    # `bspline` USED to be here: it accepted `feed_model` and did not expose
    # it. That was never a decision — the row mis-declared the axis as
    # single-valued while the constructor defaulted to the other value
    # (momwire#891). It is exposed now, so the surviving cases are razor's.
    assert "feed_model" in live["bspline"]["model_kwargs"]
    assert live["bspline"]["axes"]["feed_model"] == ["point-gap", "segment-gap"]
    assert "degree" not in live["razor-2p"]["model_kwargs"]
    assert live["razor-2p"]["axes"]["basis"] == ["tent"]
    # ...and the sinusoidal case, which is the one that was actually a bug.
    assert "feed_model" not in live["sinusoidal"]["model_kwargs"]
    assert "feed_model" in live["sinusoidal-galerkin"]["model_kwargs"]


def test_the_served_slot_seeds_and_aliases_reach_the_frontend_fixture():
    """The last two engine-name facts to leave the client (#1006 G2-6).

    `DEFAULT_SLOT_SEEDS` was three product decisions written as three engine
    names, and `normalizeBackend` carried an inline `"triangular" -> "bspline"`
    rewrite. Both are served now, so both need the same regeneration gate as
    the catalogue beside them — a generated copy nothing compares to its
    source is a hand-written copy with a misleading header.
    """
    import json
    import re

    from antennaknobs.web.adapter import backend_aliases, default_slots

    src = ROSTER_FIXTURE.read_text()
    m = re.search(r"SERVED_SLOT_SEEDS: ServedSlotSeed\[\] = (\[.*?\]);", src, re.S)
    assert m, "SERVED_SLOT_SEEDS not found in the fixture"
    assert json.loads(m.group(1)) == default_slots(), REGENERATE

    m = re.search(r"SERVED_ALIASES: Record<string, string> = (\{[^}]*\});", src)
    assert m, "SERVED_ALIASES not found in the fixture"
    assert json.loads(m.group(1)) == backend_aliases(), REGENERATE


def test_the_seeds_name_backends_the_roster_actually_serves():
    """A seed naming an absent backend is tolerated by the client (it falls
    back to the roster head, #429) — but a seed naming one that NEVER exists
    is a typo that would silently downgrade a slot forever."""
    from antennaknobs.web.adapter import default_slots

    served = {r["name"] for r in backend_roster(have_pynec=True, have_nec5=True)}
    for seed in default_slots():
        assert seed["backend"] in served, seed
    assert [s["slot"] for s in default_slots()] == ["A", "B", "C"]


def test_every_alias_target_is_a_real_backend_and_no_alias_shadows_one():
    """An alias pointing at nothing silently resolves to null; an alias whose
    KEY is a live backend name would rewrite a working name."""
    from antennaknobs.web.adapter import backend_aliases

    served = {r["name"] for r in backend_roster(have_pynec=True, have_nec5=True)}
    for old, new in backend_aliases().items():
        assert new in served, (old, new)
        assert old not in served, f"{old} is a live backend name, not a retired one"


def test_the_axes_fixture_matches_the_served_axes():
    """The gate `axesFixtures.ts` was created to need, and did not have.

    That file exists BECAUSE a fixture drifted: the roster fixture built every
    entry's axes by spreading one shared literal, so fixing the b-spline
    family silently gave `sinusoidal` a feed-model choice it does not have,
    and every gate passed because they compared kwarg tuples and constraints
    and never axes. Generating the axes removed the inheritance — and then the
    generated file shipped with a header claiming a Python-side pin that did
    not exist. The one fixture created in response to drift was the one
    fixture that could drift unwatched.

    Caught in review by grepping for the reference the header promised. Worth
    remembering: a comment asserting that a gate exists is not a gate, and it
    reads exactly like one.
    """
    fx = _json_after(AXES_FIXTURE.read_text(), "export const SERVED_AXES")
    live = {
        r["name"]: r["axes"] for r in backend_roster(have_pynec=True, have_nec5=True)
    }
    assert fx, "fixture parsed as empty — the comparison would be vacuous"
    assert set(fx) == set(live), (
        f"fixture and server disagree on WHICH backends exist: "
        f"{sorted(set(fx) ^ set(live))}. {REGENERATE}"
    )
    assert fx == live, f"the axes fixture is stale. {REGENERATE}"


@pytest.mark.parametrize(
    "name",
    sorted(
        r["name"] for r in backend_roster(have_pynec=True, have_nec5=True) if r["axes"]
    ),
)
def test_each_backend_axes_block_matches(name):
    """Per-backend so a failure names the tab, and because the drift this
    guards against was a SINGLE entry silently inheriting another's values —
    a whole-object comparison reports that as one enormous diff."""
    fx = _json_after(AXES_FIXTURE.read_text(), "export const SERVED_AXES")
    live = {
        r["name"]: r["axes"] for r in backend_roster(have_pynec=True, have_nec5=True)
    }
    assert fx[name] == live[name], f"{name} axes are stale. {REGENERATE}"


def test_the_single_valued_axes_are_the_ones_that_can_silently_widen():
    """The specific shape of the drift, asserted directly.

    A spread widens a single-valued axis into whatever the base declares, and
    single-valued is exactly the state that carries meaning here: it is what
    makes an axis the tab's IDENTITY rather than a control. `sinusoidal`'s
    feed model is the case that actually broke.
    """
    fx = _json_after(AXES_FIXTURE.read_text(), "export const SERVED_AXES")
    assert fx["sinusoidal"]["feed_model"] == ["segment-gap"]
    assert fx["razor-2p"]["basis"] == ["tent"]
    # ...and the family that legitimately has two, so this is not just
    # "everything is single-valued".
    assert fx["bspline"]["feed_model"] == ["point-gap", "segment-gap"]
