"""AK#2297: a knob the import made whole-number can be read as a decimal knob,
and back, from its menu (G8HUL, groups.io).

The importer reads a whole-valued SY symbol (a ``.ssn`` dcl constant) that
only integer card fields read as a whole-number knob (`classify_sy`,
`classify_dcl`, AK#2295). That is a guess; ``decimal_knobs`` overrules it:
those knobs are read with ``integer=False`` (`file_designs._read_as_decimal`),
so the knob value reaches the deck unrounded, exactly as an SY card holding
that value would. What is pinned here:

- a move of a switched knob builds the hand-edited deck's wires (``.nec`` and
  ``.ssn``), and the same move unswitched does not -- the knob feeds
  ``n*2``, so rounding the knob and rounding the count part ways;
- switching back is the import as before;
- a name that is no knob, or a knob that already takes decimals, is refused
  by name, at the importer and at ``POST /deck``;
- the choice splits the deck key, and a request carrying it rebuilds it;
- the served schema marks the switchable knobs (``whole_numbers``), and a
  catalog design's own int params carry no mark.
"""

from __future__ import annotations

import base64
import zlib

import pytest
from fastapi.testclient import TestClient
from test_ssn_parser_2204 import DIPOLE, _ssn

from antennaknobs.file_designs import builder_from_text
from antennaknobs.nec_import import parse_nec
from antennaknobs.web import decks, server

# ``n`` reaches only GW's segment field, through ``n*2``: a whole-number knob
# as imported. ``span`` is a length.
DECK = """CM synthetic
CE
SY span=6.5
SY n=7
GW 1 n*2 0 0 9 span 0 9 1.e-3
GE 0
EX 0 1 1 0 1 0
GN -1
FR 0 1 0 0 14.2 0
EN
"""


def _hand_edit(value: float) -> list:
    return parse_nec(
        DECK.replace("SY n=7", f"SY n={value!r}"), network=True
    ).wire_tuples(specs=True)


def _moved(cls, **values) -> list:
    return cls(dict(cls.default_params, **values)).build_wires()


def test_a_switched_knob_moves_as_the_hand_edited_deck():
    whole = builder_from_text("t.nec", DECK)
    decimal = builder_from_text("t.nec", DECK, decimal_knobs=("sy_n",))
    assert whole.default_params["sy_n"] == 7
    assert isinstance(whole.default_params["sy_n"], int)
    assert isinstance(decimal.default_params["sy_n"], float)
    # 7.4 * 2 = 14.8 segments -> 15; the whole-number knob rounds 7.4 to 7
    # first -> 14. The hand-edited deck is the decimal reading.
    assert _moved(decimal, sy_n=7.4) == _hand_edit(7.4)
    assert _moved(whole, sy_n=7.4) != _hand_edit(7.4)
    # At its default the switched design is the file as imported.
    assert decimal().build_wires() == whole().build_wires()


def test_switching_back_restores_the_whole_number_knob():
    back = builder_from_text("t.nec", DECK, decimal_knobs=())
    assert isinstance(back.default_params["sy_n"], int)
    assert back.default_params["ui_params"]["sy_n"]["whole_numbers"] is True
    assert _moved(back, sy_n=7.4) == _hand_edit(7.0)
    switched = builder_from_text("t.nec", DECK, decimal_knobs=("sy_n",))
    assert switched.default_params["ui_params"]["sy_n"]["whole_numbers"] is False
    # A knob the import never made whole-number is not switchable.
    assert "whole_numbers" not in switched.default_params["ui_params"]["sy_span"]


@pytest.mark.parametrize(
    ("name", "said"),
    [
        ("sy_nope", "this deck has no knob 'sy_nope'"),
        ("sy_span", "sy_span in decimals, and it already takes them"),
    ],
)
def test_a_name_that_is_no_whole_number_knob_is_refused_by_name(name, said):
    with pytest.raises(ValueError, match=said):
        builder_from_text("t.nec", DECK, decimal_knobs=(name,))


def test_a_file_without_knobs_refuses_any_name():
    frozen = DECK.replace("SY n=7\n", "").replace("n*2", "14")
    frozen = frozen.replace("SY span=6.5\n", "").replace("span", "6.5")
    with pytest.raises(ValueError, match="has no knob 'sy_n'"):
        builder_from_text("t.nec", frozen, decimal_knobs=("sy_n",))


def _circuit(jam: str = "") -> str:
    return (
        _ssn("dcl n = 7;")
        .replace(DIPOLE, "GW 1,n*2,0,0,0,0,0,10.2,.001")
        .replace("$GW_1.JamSegments(21);", jam)
        .replace("EX 0 1 11 0 1 0", "EX 0 1 1 0 1 0")
    )


def test_the_ssn_reader_honours_the_switch():
    text = _circuit()
    whole = builder_from_text("t.ssn", text)
    decimal = builder_from_text("t.ssn", text, decimal_knobs=("dcl_n",))
    assert whole.default_params["ui_params"]["dcl_n"]["whole_numbers"] is True
    assert decimal.default_params["ui_params"]["dcl_n"]["whole_numbers"] is False
    hand = builder_from_text("t.ssn", text.replace("dcl n = 7;", "dcl n = 7.4;"))
    assert _moved(decimal, dcl_n=7.4) == hand().build_wires()
    assert _moved(whole, dcl_n=7.4) != hand().build_wires()
    with pytest.raises(ValueError, match="has no knob 'sy_n'"):
        builder_from_text("t.ssn", text, decimal_knobs=("sy_n",))


def test_a_switched_jamsegments_count_is_read_as_a_hand_edit_is():
    """SimNEC's JamSegments takes a whole count and the reader refuses a
    fraction by name (`_DclCards.jam_counts`): a switched knob meets that
    refusal exactly where a hand-edited dcl value does."""
    text = _circuit("$GW_1.JamSegments(n*2);")
    decimal = builder_from_text("t.ssn", text, decimal_knobs=("dcl_n",))
    hand = builder_from_text("t.ssn", text.replace("dcl n = 7;", "dcl n = 7.5;"))
    assert _moved(decimal, dcl_n=7.5) == hand().build_wires()
    with pytest.raises(ValueError, match="asks for 14.8 segments"):
        _moved(decimal, dcl_n=7.4)


# --------------------------------------------------------------------------
# the deck payload
# --------------------------------------------------------------------------
def _payload(text=DECK, name="t.nec", **kw) -> dict:
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = c.compress(text.encode()) + c.flush()
    return {
        "name": name,
        "z": base64.urlsafe_b64encode(packed).decode().rstrip("="),
        **kw,
    }


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


def test_the_choice_splits_the_key_and_none_keeps_the_old_one():
    old = decks.deck_key("t.nec", DECK)
    assert decks.deck_key("t.nec", DECK, decimal_knobs=()) == old
    assert decks.deck_key("t.nec", DECK, decimal_knobs=("sy_n",)) != old
    assert decks.payload_decimal_knobs({"decimal_knobs": ["sy_n", "sy_a", "sy_n"]}) == (
        "sy_a",
        "sy_n",
    )
    assert decks.payload_decimal_knobs({}) == ()


@pytest.mark.parametrize("raw", ["sy_n", [1], [""], {"sy_n": True}])
def test_a_malformed_list_is_refused_by_name(raw):
    with pytest.raises(decks.DeckError, match="decimal_knobs must be a list"):
        decks.payload_decimal_knobs({"decimal_knobs": raw})


def _knob(entry: dict, name: str) -> dict:
    (spec,) = [p for p in entry["param_schema"] if p.get("name") == name]
    return spec


def test_deck_serves_the_switch_and_rebuilds_it(client):
    whole = client.post("/deck", json=_payload()).json()
    decimal = client.post("/deck", json=_payload(decimal_knobs=["sy_n"])).json()
    assert decimal["key"] != whole["key"]
    n, n_dec = _knob(whole["example"], "sy_n"), _knob(decimal["example"], "sy_n")
    assert (n["kind"], n["whole_numbers"], n["step"]) == ("int", True, 1.0)
    assert n_dec["kind"] == "float" and n_dec["whole_numbers"] is False
    assert n_dec["step"] < 1.0
    assert _knob(whole["example"], "sy_span")["whole_numbers"] is None
    # An evicted deck comes back as the reading its payload carries.
    key = decimal["key"]
    server._DECK_STORE._decks.clear()
    server.EXAMPLES.pop(key)
    r = client.post("/geometry", json={"geometry": key, "_deck": _payload()})
    assert r.status_code == 400
    r = client.post(
        "/geometry",
        json={"geometry": key, "_deck": _payload(decimal_knobs=["sy_n"])},
    )
    assert r.status_code == 200, r.text
    assert isinstance(server.EXAMPLES[key].builder_cls.default_params["sy_n"], float)


@pytest.mark.parametrize(
    ("names", "said"),
    [
        (["sy_nope"], "this deck has no knob 'sy_nope'"),
        (["sy_span"], "sy_span in decimals, and it already takes them"),
    ],
)
def test_deck_refuses_a_bad_name_by_name(client, names, said):
    r = client.post("/deck", json=_payload(decimal_knobs=names))
    assert r.status_code == 422 and said in r.json()["detail"]


def test_a_catalog_int_param_is_not_switchable(client):
    entries = client.get("/examples").json()["examples"]
    ints = [
        p
        for e in entries
        for p in e["param_schema"]
        if p.get("kind") == "int" and "params" not in p
    ]
    assert ints, "no catalog design has an int param to check"
    assert all(p["whole_numbers"] is None for p in ints)
