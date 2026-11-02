"""The pattern charts' exact-pattern overlay is gated on a served capability.

`/capabilities` says, per backend, whether it can draw its own exact
far-field pattern (an RP-card run) as the dashed overlay. The client used to
test the backend's NAME against pynec and nec5, which left NEC-2 and NEC-4.2
without the overlay although both serve /pattern.
"""

from __future__ import annotations

import antennaknobs.web.server as server
from antennaknobs.web import adapter


def _roster():
    return adapter.backend_roster(
        have_pynec=True, have_nec5=True, have_nec2=True, have_nec42=True
    )


def test_every_engine_that_serves_pattern_offers_the_overlay():
    by_kind = {b["kind"]: b for b in _roster()}
    for kind in ("pynec", "nec5", "nec2", "nec42"):
        cap = by_kind[kind]["exact_pattern"]
        assert cap is not None, kind
        assert cap["label"] == by_kind[kind]["label"]
        assert "terrain" in cap["ground_refusals"]


def test_no_momwire_basis_offers_it():
    for b in _roster():
        if b["kind"] == "momwire":
            assert b["exact_pattern"] is None, b["name"]


def test_the_capability_matches_the_backends_that_serve_pattern():
    # Every external backend the server routes /pattern to has a pattern()
    # and is exactly the set the capability names, in both directions.
    serving = {
        name
        for name, (mod, _ok) in server._EXTERNAL_BACKENDS.items()
        if callable(getattr(mod, "pattern", None))
    }
    assert serving == set(adapter._EXACT_PATTERN_KINDS)


def test_the_frontend_fixture_carries_the_served_sentence():
    # backendFixtures.ts is hand-maintained (CLAUDE.md): pin its copy of the
    # terrain refusal to the served one so the two cannot drift.
    from pathlib import Path

    fixtures = (
        Path(__file__).resolve().parents[1]
        / "src/antennaknobs/web/frontend/src/__tests__/backendFixtures.ts"
    ).read_text(encoding="utf-8")
    assert f'"{adapter._EXACT_PATTERN_TERRAIN_REFUSAL}"' in fixtures
