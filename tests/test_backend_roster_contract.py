"""Contract: the frontend's backend roster tracks the server's registry.

The two halves of the backend roster live in different languages in different
places — ``_MOMWIRE_MODELS`` in ``web/adapter.py`` (the authority: what the
server will actually construct) and ``BACKEND_ORDER`` in
``web/frontend/src/lib/backends.ts`` (what the UI offers). Nothing structural keeps
them in sync, and the failure mode of drift is *silent absence*: when the
sinusoidal-Galerkin backend landed server-side (momwire#182 M6, PR #626),
every test in both repos stayed green while the UI simply had no tab to
click — found live, fixed in PR #627.

This test makes that drift a red test instead. It reads the TSX roster with a
regex rather than a TS parser on purpose: the roster is a literal string
array, and if its shape ever changes enough to break the regex, the test
fails loudly — which is the correct outcome for a contract check.

The full fix — serving the roster (labels, order, ground support, option
schemas) from /capabilities the way terrain presets already are — is tracked
in the issue referenced by PR #628; this test is the interim tripwire.
"""

import re
from pathlib import Path

# Import the server package first: importing adapter directly at collection
# time trips the adapter ↔ examples circular import (same order every other
# web test uses).
from antennaknobs.web import server as _server  # noqa: F401
from antennaknobs.web.adapter import _MOMWIRE_MODELS

_BACKENDS_TS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "antennaknobs"
    / "web"
    / "frontend"
    / "src"
    / "lib"
    / "backends.ts"
)

# Frontend entries that are deliberately not momwire models. PyNEC rides the
# separate `solver: "pynec"` request field, not `momwire_model`.
_NON_MOMWIRE_BACKENDS = {"pynec"}


def _frontend_roster() -> set[str]:
    src = _BACKENDS_TS.read_text()
    m = re.search(r"const BACKEND_ORDER: Backend\[\] = \[(?P<body>[^\]]*)\]", src, re.S)
    assert m, "BACKEND_ORDER literal not found in lib/backends.ts — update this contract test"
    entries = set(re.findall(r'"([a-z0-9-]+)"', m.group("body")))
    assert entries, "BACKEND_ORDER parsed empty — update this contract test"
    return entries


def test_every_server_backend_has_a_frontend_tab():
    """The direction that bit us: a solver registered in the adapter must be
    offered by the UI, or it is invisible to every user of the web app."""
    missing = set(_MOMWIRE_MODELS) - _frontend_roster()
    assert not missing, (
        f"server backends with no frontend tab: {sorted(missing)} — add them to "
        "BACKEND_ORDER / BACKEND_LABEL / BackendOptsMap in lib/backends.ts (see "
        "PR #627 for the full checklist of touch-points)"
    )


def test_every_frontend_tab_is_a_server_backend():
    """The reverse direction: a tab the server cannot construct would fall
    back to BSplineSolver silently (`_MOMWIRE_MODELS.get(model, BSplineSolver)`
    in the adapter) — the user would see the wrong solver's numbers."""
    stale = _frontend_roster() - _NON_MOMWIRE_BACKENDS - set(_MOMWIRE_MODELS)
    assert not stale, (
        f"frontend tabs with no server backend: {sorted(stale)} — remove them "
        "or register the solver in _MOMWIRE_MODELS"
    )
