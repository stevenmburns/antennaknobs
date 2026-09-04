"""The frontend's generated constraint fixture must match what we serve.

`src/__tests__/backendConstraintFixtures.ts` is generated from a live
`backend_roster()` and carries momwire's refusal prose verbatim, so the
frontend's tests can assert against the real payload rather than a paraphrase.
A generated file with no regeneration gate is just a copy, and copies drift.

THIS ONE ALREADY DID, SILENTLY. The momwire#888 pointer move (#1158) took
`bspline` from 1 constraint to 5 and `razor-2p` from 0 to 1, and every
frontend test stayed green — none of them asserts a count, and the roster's
own Python twin (`test_backend_roster_served_shape`) pins names, labels,
panels and the option schema but never the constraints. So the fixture sat
wrong for a whole PR with nothing to say so. That is the exact failure the
constraints seam exists to prevent, one layer down from momwire#888's own
version of it.

The comparison is on the FULL payload, prose included, not on counts: a count
would have caught this particular drift and would miss a reworded reason,
which is the drift that matters most here.
"""

from __future__ import annotations

import json
import pathlib

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web.adapter import backend_roster

FIXTURE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/antennaknobs/web/frontend/src/__tests__/backendConstraintFixtures.ts"
)

REGENERATE = (
    "Regenerate it — the command is in the fixture's own header comment — and "
    "commit the result with the change that moved the payload."
)


def _fixture() -> dict:
    """The TS module's JSON body.

    It is written as `export const NAME: Type =\\n<json>;` precisely so this
    can read it without a JS runtime; a hand-written TS literal would need a
    parser and would have been an argument for not gating it at all.
    """
    src = FIXTURE.read_text()
    marker = "export const SERVED_CONSTRAINTS"
    assert marker in src, f"{FIXTURE} no longer declares {marker}"
    body = src[src.index(marker) :]
    body = body[body.index("=") + 1 :].strip()
    assert body.endswith(";"), "fixture body is not the expected `= <json>;` shape"
    return json.loads(body[:-1])


def _live() -> dict:
    return {
        r["name"]: r["constraints"]
        for r in backend_roster(have_pynec=True, have_nec5=True)
    }


def test_the_fixture_is_not_empty_and_names_every_served_backend():
    """A fixture that failed to parse would make the comparison below vacuous
    — it would compare {} against {} only if the live side were empty too, so
    this pins both sides are real before anything is asserted about them."""
    fx, live = _fixture(), _live()
    assert fx, "fixture parsed as empty"
    assert live, "roster served nothing"
    assert set(fx) == set(live), (
        f"fixture names {sorted(set(fx) ^ set(live))} that the roster does not "
        f"(or vice versa). {REGENERATE}"
    )


@pytest.mark.parametrize("name", sorted(_live()))
def test_each_backend_row_matches_the_served_payload_exactly(name):
    """Whole rows, prose included — not counts.

    A count check would have caught the #888 drift and would sail past a
    reworded `reason`, which is the drift with real consequences: the prose is
    what a user reads when a control greys out, and momwire owns it.
    """
    fx, live = _fixture()[name], _live()[name]
    if live is None or fx is None:
        assert fx == live, (
            f"{name}: one side says 'cannot be asked' and the other does not. "
            f"{REGENERATE}"
        )
        return
    assert [c["reason"] for c in fx] == [c["reason"] for c in live], (
        f"{name}: refusal prose differs from what the server sends. {REGENERATE}"
    )
    assert fx == live, f"{name}: fixture differs from the served payload. {REGENERATE}"


def test_the_gate_would_notice_a_count_change_AND_a_reword():
    """Both drifts this file exists for, exercised rather than asserted.

    Mutating the fixture in memory and requiring the comparison to fail is the
    only way to know the comparison can fail at all — the failure mode being
    guarded against is a check that passes for the wrong reason.
    """
    live = _live()
    dropped = {k: (v[:-1] if v else v) for k, v in live.items()}
    assert dropped != live, "no backend has a row to drop — premise gone"

    reworded = {
        k: ([{**c, "reason": c["reason"] + " (edited)"} for c in v] if v else v)
        for k, v in live.items()
    }
    assert reworded != live
    # ...and a count check alone would NOT have seen the reword, which is why
    # the assertions above compare whole rows.
    assert {k: (len(v) if v else v) for k, v in reworded.items()} == {
        k: (len(v) if v else v) for k, v in live.items()
    }
