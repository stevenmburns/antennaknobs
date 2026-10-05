"""AK#1893: on the web, a NEC-2 deck's own EK card is a deck default.

The CLI has honoured the card since #849 (`cli.deck_extended_kernel_flag`).
The web took only #1891's NEC-4/NEC-5 dialect default, so an opened NEC-2
deck with EK solved EK-off. Now the card resolves through the same
`extended_kernel_default` path: the slot's toggle shows it on, a request
that does not say solves EK-on, and an explicit off is honoured.

Counted at the momwire solver CONSTRUCTOR, reached through `/deck` and then
`/pattern_cell`, never through an engine the test builds itself.
"""

from __future__ import annotations

import pytest
from momwire import RazorSolver
from test_ek_by_dialect_1891 import (
    _cell,
    _ek_constructions,
    _payload,
    _text,
    client,  # noqa: F401 — the fixture, used by name below
)


@pytest.mark.parametrize(
    ("ek", "model_options", "want"),
    [
        ("EK\n", None, True),
        ("EK\n", {"extended_kernel": True}, True),
        ("EK\n", {"extended_kernel": False}, False),
        ("EK -1\n", None, False),
        ("", None, False),
    ],
    ids=["ek-card", "ek-card-on", "ek-card-switched-off", "ek-minus-1", "no-card"],
)
def test_an_opened_nec2_deck_takes_its_ek_card_as_the_default(
    ek,
    model_options,
    want,
    client,  # noqa: F811 — the imported fixture
    monkeypatch,
):
    opened = client.post("/deck", json=_payload(_text("nec2", ek=ek))).json()
    assert opened["dialect"]["read_as"] == "nec2"
    assert opened["example"]["extended_kernel_default"] is (ek == "EK\n")
    seen = _ek_constructions(monkeypatch, RazorSolver)
    kw = {} if model_options is None else {"model_options": model_options}
    _cell(client, opened["key"], **kw)
    assert seen and set(seen) == {want}, seen


def test_a_nec2_ek_card_on_a_refusing_tab_falls_back_and_says_so(
    client,  # noqa: F811 — the imported fixture
):
    # A default, not a request, on the web: the pulse basis cannot serve the
    # extended kernel, so the card's kernel falls back with the advisory.
    opened = client.post("/deck", json=_payload(_text("nec2", ek="EK\n"))).json()
    out = _cell(client, opened["key"], momwire_model="pulse", n_per_wire=41)
    notes = [
        a for a in out.get("advisories") or () if a["category"] == "ExtendedKernel"
    ]
    assert len(notes) == 1, out.get("advisories")
