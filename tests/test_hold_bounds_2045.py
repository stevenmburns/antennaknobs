"""AK#2045: a hold carries its own range for a held knob (``an.Hold.bounds``).

Steve's case (10-25): Mike's doublet opened as a NEC-5 deck, its two sides
SY knobs (``SY long_ft=33.12``, ``SY short_ft=4``). A deck's SY knob has no
``ui_params`` range of its own (the app shows an automatic window), so a
hold on it was refused, even after the user set the knob's range in its
Optimize menu. The hold builder now carries that range as ``bounds``:

- the bounds round-trip through ``to_code``, ``to_data`` / ``from_data`` and
  the never-executing link reader (`analyses_text`), and malformed ones are
  refused by name;
- `hold.free_of` searches them: on a knob with no range they are what make
  it searchable; on a knob with its own range they must lie within it;
- the held sweep runs end to end on the deck (``/deck`` then
  ``/param_sweep`` with the hold as data) and converges at every point.
"""

from __future__ import annotations

import base64
import json
import zlib

import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analyses_text as at
from antennaknobs import hold as hd
from antennaknobs.designs.dipoles.two_wire_doublet import Builder as Doublet
from antennaknobs.web import decks, server

#: Mike's doublet as a NEC-5 deck: the two sides of the knot feed as SY
#: knobs in feet (they open as sy_long_ft / sy_short_ft, auto ranges only).
#: 12.5 MHz puts resonance for long_ft 30..36 at short_ft 3.5..8.4 ft,
#: inside the 1..16 the hold searches.
MIKE_FREQ = 12.5
MIKE = f"""CM Mike's doublet, NEC-5, SY knobs (AK#2045 hold bounds)
CM NEC-5
CE
SY long_ft=33.12
SY short_ft=4
GW 1 20 0 -short_ft*0.3048 10 0 0 10 6.452E-04
GW 2 20 0 0 10 0 long_ft*0.3048 10 6.452E-04
GE 0 0
LD 5 0 0 0 5.8E+07 0. 0.
EX 0 2 1 1 1.0 0.0
FR 0 1 0 0 {MIKE_FREQ} 0
XQ 0
EN
"""

HELD = an.Hold("resonance", ("sy_short_ft",), bounds=(an.Knob("sy_short_ft", 1, 16),))
ANALYSIS = an.Analysis(
    "long_ft, short_ft held", sweep=an.Sweep("sy_long_ft", 30, 36, 4), hold=HELD
)


def _z(text: str) -> str:
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return (
        base64.urlsafe_b64encode(c.compress(text.encode()) + c.flush())
        .decode()
        .rstrip("=")
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(server.app)


@pytest.fixture()
def fresh_decks(monkeypatch):
    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


def _open_mike(client) -> tuple[str, dict]:
    sent = {"name": "mike_doublet.nec", "z": _z(MIKE)}
    r = client.post("/deck", json=sent)
    assert r.status_code == 200, r.text
    return r.json()["key"], sent


# ── the spec ────────────────────────────────────────────────────────────────


def test_bounds_round_trip_through_code_data_and_the_link_reader():
    assert HELD.bounds == (an.Knob("sy_short_ft", 1.0, 16.0),)
    code = an.to_code(ANALYSIS)
    assert 'bounds=(an.Knob("sy_short_ft", 1.0, 16.0),)' in code
    assert an.from_data(an.to_data(ANALYSIS)) == ANALYSIS
    assert an.to_data(HELD)["bounds"] == [
        {"an": "Knob", "name": "sy_short_ft", "min": 1.0, "max": 16.0}
    ]
    assert at.read(at.write((ANALYSIS,))) == (ANALYSIS,)
    assert at.read(at.unpack(at.pack(at.write((ANALYSIS,))))) == (ANALYSIS,)
    # No bounds: as before, and the code does not mention them.
    plain = an.Hold("resonance", ("sy_short_ft",))
    assert plain.bounds == () and "bounds" not in an.to_code(plain)


_HOLD = "an.Hold('resonance', adjust=('a',), bounds={})"


@pytest.mark.parametrize(
    ("bounds", "words"),
    [
        ("(('a', 1, 2),)", "bounds holds an.Knob(name, min, max) entries"),
        ("an.Knob('a', 1, 2)", "bounds takes a tuple of an.Knob, got one"),
        ("'a'", "Hold bounds takes a tuple, got the string 'a'"),
        ("(an.Knob('a', 2, 1),)", "Knob 'a': min is below max, got 2..1"),
        ("(an.Knob('a', 1, 1e999),)", "Knob 'a': max is a finite number"),
        ("(an.Knob('a', 1, float('inf')),)", "refused: call of Name 'float'"),
        ("(an.Knob('a', '1', 2),)", "Knob 'a': min is a finite number"),
        (
            "(an.Knob('b', 1, 2),)",
            "bounds name 'b', which the hold does not adjust (a)",
        ),
        ("(an.Knob('a', 1, 2), an.Knob('a', 3, 4))", "bounds give a knob twice"),
    ],
)
def test_malformed_bounds_are_refused_by_name(bounds, words):
    text = f"[an.Analysis('x', an.Sweep('k', 1, 2), hold={_HOLD.format(bounds)})]"
    with pytest.raises(at.AnalysesTextError) as e:
        at.read(text)
    assert words in str(e.value)


# ── free_of ─────────────────────────────────────────────────────────────────


def test_free_of_on_a_deck_sy_knob_searches_the_holds_bounds(client, fresh_decks):
    key, _ = _open_mike(client)
    builder = server.EXAMPLES[key].builder_cls()
    # Without bounds: refused by name, as before (the SY knob has no range).
    with pytest.raises(
        hd.HoldRefused, match="sy_short_ft, which has no ui_params min/max"
    ):
        hd.free_of(an.Hold("resonance", ("sy_short_ft",)), builder)
    free = hd.free_of(HELD, builder)
    assert free == [{"name": "sy_short_ft", "min": 1.0, "max": 16.0}]
    # The cold start is the deck's own value, inside the bounds; one outside
    # them starts from the nearer end.
    assert hd.defaults_of(builder, free) == {"sy_short_ft": 4.0}
    narrow = hd.free_of(
        an.Hold("resonance", ("sy_short_ft",), bounds=(an.Knob("sy_short_ft", 5, 9),)),
        builder,
    )
    assert hd.defaults_of(builder, narrow) == {"sy_short_ft": 5.0}


def test_bounds_outside_a_catalog_knobs_own_range_are_refused_by_name():
    b = Doublet()
    lo, hi = b.ui_params["short_ft"]["min"], b.ui_params["short_ft"]["max"]
    outside = an.Hold(
        "resonance", ("short_ft",), bounds=(an.Knob("short_ft", lo - 0.5, 20),)
    )
    with pytest.raises(hd.HoldRefused) as e:
        hd.free_of(outside, b)
    assert str(e.value) == (
        f"the hold searches short_ft over {lo - 0.5:g}..20, outside its own range "
        f"{lo:g}..{hi:g}: a hold's range for a knob lies within the knob's own"
    )
    inside = an.Hold(
        "resonance", ("short_ft",), bounds=(an.Knob("short_ft", lo + 1, 20),)
    )
    assert hd.free_of(inside, b) == [{"name": "short_ft", "min": lo + 1, "max": 20.0}]
    # A knob the bounds leave out keeps its own range.
    assert hd.free_of(an.Hold("resonance", ("short_ft",)), b) == [
        {"name": "short_ft", "min": float(lo), "max": float(hi)}
    ]


# ── end to end: the held sweep on Mike's deck ────────────────────────────────


def test_mike_deck_held_sweep_runs_and_converges(client, fresh_decks):
    key, sent = _open_mike(client)
    r = client.post(
        "/param_sweep",
        json={
            "geometry": key,
            "_session": "hold-bounds",
            "_deck": sent,
            "sy_long_ft": 33.12,
            "sy_short_ft": 4.0,
            "design_freq_mhz": MIKE_FREQ,
            "measurement_freq_mhz": MIKE_FREQ,
            "solver": "momwire",
            "momwire_model": "bspline",
            "ground": False,
            "param": "sy_long_ft",
            "values": [30.0, 32.0, 34.0, 36.0],
            "hold": an.to_data(HELD),
        },
    )
    assert r.status_code == 200, r.text
    recs = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    points = [x for x in recs if "value" in x]
    assert recs[-1].get("done") is True and recs[-1].get("gaps") == 0, recs[-1]
    assert [p["value"] for p in points] == [30.0, 32.0, 34.0, 36.0]
    for p in points:
        print(
            f"long_ft {p['value']:g}: short_ft {p['held']['sy_short_ft']:.3f}, "
            f"Z = {p['z_re']:.1f}{p['z_im']:+.4f}j"
        )
        assert p["converged"] is True, p
        assert 1.0 <= p["held"]["sy_short_ft"] <= 16.0
        assert abs(p["z_im"]) < hd.HOLD_TOL
    shorts = [p["held"]["sy_short_ft"] for p in points]
    # Resonance keeps the total length about constant: short falls as long grows.
    assert shorts == sorted(shorts, reverse=True)
    assert shorts[0] == pytest.approx(8.39, abs=0.05)
    assert shorts[-1] == pytest.approx(3.52, abs=0.05)


def test_the_deck_hold_without_bounds_is_a_422_by_name(client, fresh_decks):
    key, sent = _open_mike(client)
    r = client.post(
        "/param_sweep",
        json={
            "geometry": key,
            "_deck": sent,
            "param": "sy_long_ft",
            "values": [30.0],
            "hold": an.to_data(an.Hold("resonance", ("sy_short_ft",))),
        },
    )
    assert r.status_code == 422
    assert "sy_short_ft, which has no ui_params min/max" in r.json()["detail"]


def test_a_link_analysis_with_bounds_is_listed_runnable_on_the_deck(
    client, fresh_decks
):
    # The page's Copy link carries a built hold as its to_code text; the deck
    # opened with it lists the analysis as runnable, with the hold's bounds.
    sent = {
        "name": "mike_doublet.nec",
        "z": _z(MIKE),
        "analyses": at.pack(at.write((ANALYSIS,))),
    }
    body = client.post("/deck", json=sent).json()
    assert body["analyses"] == 1 and body["analyses_refusal"] is None
    r = client.post("/analyses", json={"geometry": body["key"], "_deck": sent})
    assert r.status_code == 200, r.text
    (entry,) = [e for e in r.json()["analyses"] if e["name"] == ANALYSIS.name]
    w = entry["workbench"]
    assert w["runs"] is True, w
    assert w["hold"]["bounds"] == {"sy_short_ft": [1.0, 16.0]}
    assert an.from_data(w["hold"]["spec"]) == HELD
