"""The GUI's map and hold builders and its Copy link, server side (AK#2045).

The page builds an analysis as data (`lib/buildAnalysis.ts`, the same
``analyses.to_data`` form ``/analyses`` serves), asks ``/keep`` for its bare
``to_code`` expression (``expr``), and lists it in the tab by sending the
texts back with every ``/analyses`` (``built``), where they are read by
`analyses_text.read` (never run) and checked as a stranger's link analyses
are (`analyses_offer.link_refusal`). Copy link packs the listed link and
built analyses' expressions into one ``analyses=``. A catalog design's link
may carry ``analyses=`` too, which the page sends with ``/analyses``.

Also here, the fix carried from #2053: a link range can leave out the deck's
own SY value; the knob's default then moves inside the range, so the slider's
default and a held sweep's start lie inside the bounds they search.
"""

from __future__ import annotations

import json

import pytest

from antennaknobs import analyses as an
from antennaknobs import analyses_text as at
from antennaknobs import hold as hd
from antennaknobs.designs.dipoles.two_wire_doublet import Builder as Doublet
from antennaknobs.web import analyses_offer, decks, server

from fastapi.testclient import TestClient
from test_deck_link_analyses_2045 import (
    DOUBLET,
    DOUBLET_RANGES,
    SY_DIPOLE,
    _payload,
)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(server.app)


@pytest.fixture()
def fresh_decks(monkeypatch):
    """A clean deck store and limiter, restored afterwards (as
    test_deck_link_analyses_2045's)."""
    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


# What the page's builders send /keep (lib/buildAnalysis.ts): the doublet's
# three analyses on the deck's knobs, as a viewer builds them in the GUI.
MAP_DATA = {
    "an": "Analysis",
    "name": "resonance map",
    "sweep": [
        {"an": "Sweep", "knob": "sy_long_ft", "lo": 16, "hi": 36, "points": 41},
        {"an": "Sweep", "knob": "sy_short_ft", "lo": 1, "hi": 34, "points": 34},
    ],
    "views": [{"an": "Map"}],
    "references": {"an": "Ref", "x": [0]},
}


def _held(name: str, swept: str, lo, hi, points: int, held: str) -> dict:
    return {
        "an": "Analysis",
        "name": name,
        "sweep": {"an": "Sweep", "knob": swept, "lo": lo, "hi": hi, "points": points},
        "views": [{"an": "Rx"}, {"an": "Knobs"}],
        "hold": {"an": "Hold", "objective": "resonance", "adjust": [held]},
    }


LOW_DATA = _held("low-R branch", "sy_long_ft", 17.066, 32.5, 32, "sy_short_ft")
HIGH_DATA = _held("high-R branch", "sy_short_ft", 33.0, 3.5, 31, "sy_long_ft")


def _keep_expr(client, data, tab) -> str:
    r = client.post(
        "/keep", json={"origin": "chart", "form": "analysis", "spec": data, "tab": tab}
    )
    assert r.status_code == 200, r.text
    return r.json()["expr"]


def _open(client, payload) -> dict:
    r = client.post("/deck", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _analyses(client, req) -> dict:
    r = client.post("/analyses", json=req)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# /keep answers the bare expression a link carries
# ---------------------------------------------------------------------------


def test_keep_answers_the_bare_expression_and_it_reads_back(client):
    for a in Doublet().build_analyses():
        tab = {"geometry": "dipoles.two_wire_doublet"}
        expr = _keep_expr(client, an.to_data(a), tab)
        assert expr == an.to_code(a)
        assert "import" not in expr and not expr.lstrip().startswith("#")
        (back,) = at.read(expr)
        assert back == a


# ---------------------------------------------------------------------------
# /analyses lists what the page built (``built``)
# ---------------------------------------------------------------------------


def test_built_analyses_are_listed_and_run_on_a_deck(client, fresh_decks):
    sent = {**_payload(DOUBLET, "two_wire_doublet.nec"), "ranges": DOUBLET_RANGES}
    key = _open(client, sent)["key"]
    tab = {"geometry": key, "_deck": sent}
    exprs = [_keep_expr(client, d, tab) for d in (MAP_DATA, LOW_DATA, HIGH_DATA)]
    body = _analyses(client, {**tab, "built": exprs})
    assert body["built_refusal"] is None and body["analyses_refusal"] is None
    built = [e for e in body["analyses"] if e["origin"] == "built"]
    assert [e["name"] for e in built] == [
        "resonance map",
        "low-R branch",
        "high-R branch",
    ]
    m, low, high = (e["workbench"] for e in built)
    assert m["runs"] is True and m["kind"] == "map", m
    assert (m["x"]["param"], m["y"]["param"]) == ("sy_long_ft", "sy_short_ft")
    assert len(m["x"]["values"]) == 41 and len(m["y"]["values"]) == 34
    assert m["refs"]["x"] == [0]
    for w, held, swept in (
        (low, "sy_short_ft", "sy_long_ft"),
        (high, "sy_long_ft", "sy_short_ft"),
    ):
        assert w["runs"] is True, w
        assert w["param"] == swept and w["hold"]["knobs"] == [held]
        assert w["views"] == ["Rx", "Knobs"]
        # The link's ranges bound the hold.
        assert (
            w["hold"]["bounds"][held] == [15.0, 36.0]
            if held == "sy_long_ft"
            else [1.0, 34.0]
        )
        assert w["hold"]["spec"]["adjust"] == [held]
    # Each entry's spec is what /keep takes again (Copy as analysis, Copy link).
    assert _keep_expr(client, built[0]["spec"], tab) == exprs[0]
    # Sent no more, listed no more: the list is the page's, per request.
    assert not [e for e in _listed_plain(client, tab) if e["origin"] == "built"]


def _listed_plain(client, req) -> list[dict]:
    return _analyses(client, req)["analyses"]


def test_a_built_analysis_beside_a_same_named_one_is_renamed(client):
    expr = an.to_code(
        an.Analysis("convergence", an.Sweep("length_factor", 0.9, 1.1, points=3))
    )
    req = {"geometry": "dipoles.two_wire_doublet", "built": [expr]}
    names = [e["name"] for e in _listed_plain(client, req)]
    assert "convergence" in names and "built:convergence" in names


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ('__import__("os")', "refused: call of Name '__import__'"),
        ("an.Analysis('x', an.Sweep('long_ft', 1, 2)).__class__", "refused: Attribute"),
        ("[x for x in ()]", "refused: ListComp"),
        ("an.Metric('m', 1)", "a callable metric names a Python function"),
        ("an.Sweep('long_ft', 1, 2)", "Sweep at the top level"),
    ],
)
def test_a_built_text_that_does_not_read_is_named_and_the_rest_stand(
    client, text, words
):
    good = an.to_code(an.Analysis("ok", an.Sweep("long_ft", 20, 30, points=3)))
    body = _analyses(
        client, {"geometry": "dipoles.two_wire_doublet", "built": [text, good]}
    )
    assert "built analysis 1 was not read" in body["built_refusal"]
    assert words in body["built_refusal"], body["built_refusal"]
    built = [e["name"] for e in body["analyses"] if e["origin"] == "built"]
    assert built == ["ok"]


def test_a_built_analysis_naming_another_design_is_refused_by_name(client):
    text = (
        'an.Analysis("x", an.Sweep("long_ft", 20, 30, points=3), '
        'cross=an.Cross(states=(an.State("s", design="user.mine", long_ft=20),)))'
    )
    body = _analyses(client, {"geometry": "dipoles.two_wire_doublet", "built": [text]})
    (e,) = [e for e in body["analyses"] if e["origin"] == "built"]
    assert e["workbench"]["runs"] is False
    assert "names design 'user.mine'" in e["workbench"]["why"]
    text = an.to_code(an.Analysis("y", an.Sweep("nope", 1, 2, points=3)))
    body = _analyses(client, {"geometry": "dipoles.two_wire_doublet", "built": [text]})
    (e,) = [e for e in body["analyses"] if e["origin"] == "built"]
    assert (
        "moves 'nope', which no design it runs on has as a knob"
        in e["workbench"]["why"]
    )


def test_built_is_bounded_and_typed(client):
    g = "dipoles.two_wire_doublet"
    one = an.to_code(an.Analysis("ok", an.Sweep("long_ft", 20, 30, points=3)))
    body = _analyses(client, {"geometry": g, "built": [one] * (server.MAX_BUILT + 1)})
    assert f"over the {server.MAX_BUILT} a tab may hold" in body["built_refusal"]
    assert not [e for e in body["analyses"] if e["origin"] == "built"]
    big = "#" * (at.MAX_TEXT_CHARS + 1)
    body = _analyses(client, {"geometry": g, "built": [big]})
    assert f"over the {at.MAX_TEXT_CHARS} limit" in body["built_refusal"]
    for bad in ("an.Analysis()", [1], {"a": 1}):
        r = client.post("/analyses", json={"geometry": g, "built": bad})
        assert r.status_code == 422 and "built is a list" in r.json()["detail"]
    # None and empty are none.
    for none in (None, []):
        body = _analyses(client, {"geometry": g, "built": none})
        assert body["built_refusal"] is None


# ---------------------------------------------------------------------------
# A catalog design's link carries analyses= too
# ---------------------------------------------------------------------------


def test_a_catalog_design_link_carries_its_analyses(client):
    a = an.Analysis("short sweep", an.Sweep("short_ft", 5, 30, points=6))
    req = {"geometry": "dipoles.two_wire_doublet", "analyses": at.pack(at.write([a]))}
    body = _analyses(client, req)
    assert body["analyses_refusal"] is None
    (e,) = [e for e in body["analyses"] if e["origin"] == "link"]
    assert e["name"] == "short sweep" and e["workbench"]["runs"] is True
    assert e["workbench"]["param"] == "short_ft"
    # Text that does not read is refused by name; the design's own stand.
    body = _analyses(client, {**req, "analyses": at.pack('__import__("os")')})
    assert "refused: call of Name '__import__'" in body["analyses_refusal"]
    assert not [e for e in body["analyses"] if e["origin"] == "link"]
    assert [e for e in body["analyses"] if e["origin"] == "design"]
    r = client.post("/analyses", json={**req, "analyses": 5})
    assert r.status_code == 422 and "analyses must be a string" in r.json()["detail"]


def test_a_deck_lists_its_link_analyses_from_the_deck_never_the_request(
    client, fresh_decks
):
    sent = _payload(SY_DIPOLE, "d.nec")
    key = _open(client, sent)["key"]
    stray = at.pack(
        at.write([an.Analysis("stray", an.Sweep("sy_half", 4, 6, points=3))])
    )
    body = _analyses(client, {"geometry": key, "_deck": sent, "analyses": stray})
    assert not [e for e in body["analyses"] if e["origin"] == "link"]


# ---------------------------------------------------------------------------
# A range that leaves out the deck's own value (carried from #2053)
# ---------------------------------------------------------------------------


def test_a_range_outside_the_sy_value_moves_the_default_inside(client, fresh_decks):
    # SY half=5.1; the link's range is 6..8, so the default moves to 6.
    body = _open(client, {**_payload(SY_DIPOLE, "d.nec"), "ranges": "sy_half:6:8"})
    (half,) = [p for p in body["example"]["param_schema"] if p["name"] == "sy_half"]
    assert (half["min"], half["max"], half["default"]) == (6.0, 8.0, 6.0)
    body = _open(client, {**_payload(SY_DIPOLE, "d.nec"), "ranges": "sy_half:2:4.5"})
    (half,) = [p for p in body["example"]["param_schema"] if p["name"] == "sy_half"]
    assert half["default"] == 4.5
    # Inside, the deck's own value stands.
    body = _open(client, {**_payload(SY_DIPOLE, "d.nec"), "ranges": "sy_half:4:6"})
    (half,) = [p for p in body["example"]["param_schema"] if p["name"] == "sy_half"]
    assert half["default"] == 5.1


def test_inside_keeps_an_integer_whole():
    assert decks._inside(3, 4.5, 9.2) == 5
    assert decks._inside(12, 4.5, 9.2) == 9
    assert decks._inside(7, 4.5, 9.2) == 7
    # No whole number inside: left as it is, refused where it is used.
    assert decks._inside(3, 4.2, 4.8) == 3
    assert decks._inside(1.0, 2.0, 3.0) == 2.0 and decks._inside(9.0, 2.0, 3.0) == 3.0


def test_a_hold_starts_inside_its_bounds_when_the_deck_value_is_outside(
    client, fresh_decks
):
    # The doublet deck's SY L is 17.066 ft; a link range of 30..36 leaves it
    # out. The held sweep's cold start (the design's defaults) is then 30,
    # inside the range the hold searches, never 17.066.
    sent = {
        **_payload(DOUBLET, "two_wire_doublet.nec"),
        "ranges": "sy_long_ft:30:36,sy_short_ft:1:34",
    }
    key = _open(client, sent)["key"]
    req = {"geometry": key, "_deck": sent}
    h = an.to_data(an.Hold("resonance", adjust=("sy_long_ft",)))
    _h, free, defaults = server._held_setup(
        {**req, "sy_long_ft": 33.0, "sy_short_ft": 33.0}, "sy_short_ft", h
    )
    assert free == [{"name": "sy_long_ft", "min": 30.0, "max": 36.0}]
    assert defaults == {"sy_long_ft": 30.0}


def test_defaults_of_clamps_into_the_free_bounds():
    class B:
        a = 1.0
        b = 50.0
        c = 5.0

    free = [
        {"name": "a", "min": 2.0, "max": 3.0},
        {"name": "b", "min": 2.0, "max": 3.0},
        {"name": "c", "min": 2.0, "max": 9.0},
    ]
    assert hd.defaults_of(B(), free) == {"a": 2.0, "b": 3.0, "c": 5.0}


# ---------------------------------------------------------------------------
# The GUI flow end to end: build, Copy link, open the link
# ---------------------------------------------------------------------------


def test_built_analyses_copied_into_a_link_open_as_the_same_three(client, fresh_decks):
    """The acceptance's server half: the three analyses built in the GUI on
    the doublet deck, each turned into its expression by /keep, packed into
    one analyses= as Copy link packs them (`lib/buildAnalysis.ts`
    `analysesText`), and the link opened in a fresh page: /deck lists the
    same three, runnable, with the same workbench the built ones had."""
    sent = {**_payload(DOUBLET, "two_wire_doublet.nec"), "ranges": DOUBLET_RANGES}
    key = _open(client, sent)["key"]
    tab = {"geometry": key, "_deck": sent}
    exprs = [_keep_expr(client, d, tab) for d in (MAP_DATA, LOW_DATA, HIGH_DATA)]
    built = [
        e
        for e in _analyses(client, {**tab, "built": exprs})["analyses"]
        if e["origin"] == "built"
    ]
    # Copy link: the listed analyses' expressions, as one list.
    text = (
        "[\n"
        + "".join("    " + x.replace("\n", "\n    ") + ",\n" for x in exprs)
        + "]\n"
    )
    packed = at.pack(text)
    assert len(packed) <= 8000
    link_sent = {**sent, "analyses": packed}
    opened = _open(client, link_sent)
    assert opened["analyses"] == 3 and opened["analyses_refusal"] is None
    assert opened["key"] != key
    links = [
        e
        for e in _analyses(client, {"geometry": opened["key"], "_deck": link_sent})[
            "analyses"
        ]
        if e["origin"] == "link"
    ]
    assert [e["name"] for e in links] == [e["name"] for e in built]
    for a, b in zip(links, built, strict=True):
        assert a["workbench"] == b["workbench"], a["name"]
        assert a["spec"] == b["spec"]
    query = (
        f"?deck={sent['z']}&name={sent['name']}&analyses={packed}"
        f"&knobs=sy_long_ft:33:15:36,sy_short_ft:33:1:34"
        f"&analysis={json.dumps('resonance map')[1:-1].replace(' ', '%20')}&view=Map"
    )
    print(f"\ncopied link query: {len(query)} chars (analyses {len(packed)})")


def test_offer_link_names_its_origin():
    b = analyses_offer.builder_for(Doublet, {"geometry": "dipoles.two_wire_doublet"})
    a = an.Analysis("x", an.Sweep("long_ft", 20, 30, points=3))
    (e,) = analyses_offer.offer_link(
        b, {"geometry": "dipoles.two_wire_doublet"}, (a,), origin="built", taken={"x"}
    )
    assert e["origin"] == "built" and e["name"] == "built:x"
