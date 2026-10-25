"""Analyses a shared deck link carries (AK#2045, pieces 1-3).

``?deck=<z>&name=<file>&analyses=<z2>`` opens the deck with the link's
analyses listed in the chart's picker (``origin: "link"``). The analyses are
read by `analyses_text.read_link`, which parses the text and never runs it;
this file covers what the server does with them after that:

- ``POST /deck`` reads them beside the deck; refused ones do not refuse the
  deck (``analyses_refusal``);
- they are part of the opened deck's key, so two links with one deck and
  different analyses never share an entry in the (hosted, shared) store, and
  a deck opened WITHOUT analyses keeps the key it always had (old links);
- they ride the ``_deck`` payload every request carries, so an evicted deck
  comes back with them;
- before anything of a link analysis is built, every design it names must
  be the deck itself or a catalog design, and every knob it sets or moves a
  knob of a design it runs on (`analyses_offer.link_refusal`); nothing a link
  says can make the server read a file;
- the link's knob ranges (``knobs=``, sent to /deck as ``ranges``): read
  strictly and refused by name, part of the key (a link with none keeps its
  old key), folded into the deck's knobs' min/max so a hold on an SY knob
  runs, and carried through eviction;
- the acceptance: ``dipoles.two_wire_doublet`` as a NEC-5 deck with SY cards
  for L and M, its three analyses and the knobs' ranges, opened, listed, and
  the map and a held branch run.
"""

from __future__ import annotations

import base64
import builtins
import hashlib
import io
import json
import os
import zlib
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analyses_text as at
from antennaknobs import file_designs
from antennaknobs.designs.dipoles.two_wire_doublet import Builder as Doublet
from antennaknobs.web import analyses_offer, decks, server

DIPOLE = """CM opened-deck test dipole
CE
GW 1 11 0 -5.1 10 0 5.1 10 0.001
GE 0
EX 0 1 6 0 1 0
FR 0 1 0 0 14.0 0
EN
"""

# A 4nec2-style deck with one SY knob, so a link analysis has a knob to name.
SY_DIPOLE = """CM SY dipole
CE
SY half=5.1
GW 1 11 0 -half 10 0 half 10 0.001
GE 0
EX 0 1 6 0 1 0
FR 0 1 0 0 14.0 0
EN
"""

# dipoles.two_wire_doublet as `nec5_export` writes it (2 x 20 segments,
# #16 copper, the knot feed EX 0 2 1 1), with the two sides' lengths in feet
# as SY knobs L = long_ft and M = short_ft, the catalog design's own knobs and
# defaults. The deck opens them as sy_long_ft / sy_short_ft.
DOUBLET = """CM dipoles.two_wire_doublet as a NEC-5 deck, L and M as SY knobs (AK#2045)
CM NEC-5
CE
SY long_ft=17.066
SY short_ft=17.066
GW 1 20 0 -short_ft*0.3048 10 0 0 10 6.452E-04
GW 2 20 0 0 10 0 long_ft*0.3048 10 6.452E-04
GE 0 0
LD 5 0 0 0 5.8E+07 0. 0.
EX 0 2 1 1 1.0 0.0
FR 0 1 0 0 14.0 0
XQ 0
EN
"""


def _z(text: str) -> str:
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = c.compress(text.encode()) + c.flush()
    return base64.urlsafe_b64encode(packed).decode().rstrip("=")


def _payload(text=DIPOLE, name="dipole.nec", analyses=None) -> dict:
    out = {"name": name, "z": _z(text)}
    if analyses is not None:
        out["analyses"] = analyses if isinstance(analyses, str) else at.pack(analyses)
    return out


@pytest.fixture()
def client() -> TestClient:
    return TestClient(server.app)


@pytest.fixture()
def fresh_decks(monkeypatch):
    """A clean deck store and limiter, restored afterwards."""
    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


def _listed(client, key, deck_payload=None) -> list[dict]:
    req = {"geometry": key}
    if deck_payload is not None:
        req["_deck"] = deck_payload
    r = client.post("/analyses", json=req)
    assert r.status_code == 200, r.text
    return r.json()["analyses"]


def _links(entries) -> list[dict]:
    return [e for e in entries if e["origin"] == "link"]


SWEEP_HALF = 'an.Analysis("half sweep", an.Sweep("sy_half", 4.8, 5.4, points=4))'
SWEEP_HALF_WIDE = 'an.Analysis("half sweep", an.Sweep("sy_half", 4.0, 6.0, points=5))'


# ---------------------------------------------------------------------------
# The key: analyses are part of it, and a deck without them keeps its own
# ---------------------------------------------------------------------------


def _old_key(name: str, text: str, dialect: str | None = None) -> str:
    # deck_key as it was before AK#2045 (origin/main 287e7424), verbatim.
    tail = "" if dialect is None else f"\0{dialect}"
    h = hashlib.sha256(f"{name}\0{text}{tail}".encode("utf-8", "surrogatepass"))
    return f"deck.{h.hexdigest()[:12]}"


def test_a_deck_without_analyses_keeps_its_key():
    # Pinned literally (computed by the pre-#2045 code) and by formula: every
    # link shared before analyses existed names the same design.
    assert decks.deck_key("dipole.nec", DIPOLE) == "deck.51cef6474d59"
    assert decks.deck_key("dipole.nec", DIPOLE, "nec5") == "deck.3357c412c8b5"
    for dialect in (None, "nec2", "nec4", "nec5"):
        assert decks.deck_key("dipole.nec", DIPOLE, dialect) == _old_key(
            "dipole.nec", DIPOLE, dialect
        )
        assert decks.deck_key("dipole.nec", DIPOLE, dialect, None) == _old_key(
            "dipole.nec", DIPOLE, dialect
        )


def test_analyses_are_part_of_the_key():
    a, b = SWEEP_HALF, SWEEP_HALF_WIDE
    plain = decks.deck_key("d.nec", SY_DIPOLE)
    ka = decks.deck_key("d.nec", SY_DIPOLE, None, a)
    kb = decks.deck_key("d.nec", SY_DIPOLE, None, b)
    assert len({plain, ka, kb}) == 3
    # The dialect and the analyses are separate parts.
    assert decks.deck_key("d.nec", SY_DIPOLE, "nec5", a) != ka
    assert decks.deck_key("d.nec", SY_DIPOLE, "nec5", a) != decks.deck_key(
        "d.nec", SY_DIPOLE, "nec5"
    )


def test_open_without_analyses_answers_the_old_key(client, fresh_decks):
    r = client.post("/deck", json=_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["key"] == "deck.51cef6474d59"
    assert body["analyses"] == 0 and body["analyses_refusal"] is None
    # And /analyses on it lists no link analyses.
    assert _links(_listed(client, body["key"])) == []


def test_two_links_with_one_deck_do_not_collide(client, fresh_decks):
    ka = client.post(
        "/deck", json=_payload(SY_DIPOLE, "d.nec", at.pack(SWEEP_HALF))
    ).json()
    kb = client.post(
        "/deck", json=_payload(SY_DIPOLE, "d.nec", at.pack(SWEEP_HALF_WIDE))
    ).json()
    plain = client.post("/deck", json=_payload(SY_DIPOLE, "d.nec")).json()
    assert len({ka["key"], kb["key"], plain["key"]}) == 3
    assert ka["analyses"] == kb["analyses"] == 1
    va = _links(_listed(client, ka["key"]))[0]["workbench"]["values"]
    vb = _links(_listed(client, kb["key"]))[0]["workbench"]["values"]
    assert va == pytest.approx([4.8, 5.0, 5.2, 5.4])
    assert vb == pytest.approx([4.0, 4.5, 5.0, 5.5, 6.0])
    assert _links(_listed(client, plain["key"])) == []


# ---------------------------------------------------------------------------
# A refused analyses text: the deck opens, the refusal is named
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("analyses", "words"),
    [
        (at.pack('__import__("os")'), "refused: call of Name '__import__'"),
        (at.pack("[an.Analysis('x', an.Sweep(os.path, 1, 2))]"), "refused: Attribute"),
        ("!!not base64!!", "do not decode"),
        (at.pack("an.Analysis("), "does not parse"),
        ("A" * (at.MAX_PACKED_CHARS + 1), "over the"),
    ],
)
def test_refused_analyses_do_not_refuse_the_deck(client, fresh_decks, analyses, words):
    r = client.post("/deck", json=_payload(SY_DIPOLE, "d.nec", analyses))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["analyses"] == 0
    assert body["analyses_refusal"].startswith("the link's analyses were not read: ")
    assert words in body["analyses_refusal"]
    # Under the key the deck has with no analyses at all.
    assert body["key"] == decks.deck_key("d.nec", SY_DIPOLE)
    assert _links(_listed(client, body["key"])) == []


def test_analyses_that_are_not_a_string_are_refused_by_name(client, fresh_decks):
    r = client.post("/deck", json={**_payload(SY_DIPOLE, "d.nec"), "analyses": 3})
    assert r.status_code == 422
    assert "analyses must be a string" in r.json()["detail"]


# ---------------------------------------------------------------------------
# /analyses lists them; eviction brings them back from _deck
# ---------------------------------------------------------------------------


def test_analyses_lists_the_links_after_the_generic_ones(client, fresh_decks):
    text = f"[{SWEEP_HALF}, an.convergence()]"
    key = client.post("/deck", json=_payload(SY_DIPOLE, "d.nec", at.pack(text))).json()[
        "key"
    ]
    entries = _listed(client, key)
    origins = [e["origin"] for e in entries]
    first_link = origins.index("link")
    assert all(o == "generic" for o in origins[:first_link])
    links = _links(entries)
    assert [e["name"] for e in links] == ["half sweep", "link:convergence"]
    assert all(e["study"] is None for e in links)
    half = links[0]
    assert half["workbench"]["runs"] is True
    assert half["workbench"]["kind"] == "knob"
    assert half["workbench"]["param"] == "sy_half"
    assert half["code"].count("an.Sweep") == 1


def test_an_evicted_deck_comes_back_with_its_analyses(client, monkeypatch):
    st = replace(server._DECK_SETTINGS, max_open=1)
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(0))
    try:
        sent = _payload(SY_DIPOLE, "d.nec", at.pack(SWEEP_HALF))
        key = client.post("/deck", json=sent).json()["key"]
        # Another deck evicts it (max_open 1): store and registry both.
        client.post("/deck", json=_payload())
        assert key not in store and key not in server.EXAMPLES
        assert store.link_analyses(key) == ()
        # Without the payload: missing, by name.
        r = client.post("/analyses", json={"geometry": key})
        assert r.status_code == 409 and r.json()["deck_status"] == "missing"
        # The payload the page sends (the analyses ride in it): back, listed.
        links = _links(_listed(client, key, sent))
        assert [e["name"] for e in links] == ["half sweep"]
        assert key in store
        # A payload that dropped the analyses names another design: refused.
        store._decks.clear()
        store._links.clear()
        server.EXAMPLES.pop(key)
        bare = _payload(SY_DIPOLE, "d.nec")
        r = client.post("/analyses", json={"geometry": key, "_deck": bare})
        assert r.status_code == 400
    finally:
        for k in list(server.EXAMPLES):
            if decks.is_deck(k):
                del server.EXAMPLES[k]


# ---------------------------------------------------------------------------
# Safety: knob names and designs are checked before anything is built
# ---------------------------------------------------------------------------


def _open_with(client, text: str) -> list[dict]:
    body = client.post("/deck", json=_payload(SY_DIPOLE, "d.nec", at.pack(text))).json()
    assert body["analyses_refusal"] is None, body
    return _links(_listed(client, body["key"]))


@pytest.mark.parametrize(
    ("text", "words"),
    [
        # A state's knob the deck lacks.
        (
            'an.Analysis("s", an.Sweep("sy_half", 4.8, 5.4, points=3), '
            'cross=an.Cross(states=(an.State("x", build_wires=1),)))',
            "sets 'build_wires' in state 'x', and this deck has no knob 'build_wires'",
        ),
        # The same, inside a listed cell.
        (
            'an.Analysis("c", an.Sweep("sy_half", 4.8, 5.4, points=3), '
            'cross=an.Cross(cells=(an.Cell(an.State("y", label="z")),)))',
            "sets 'label' in state 'y', and this deck has no knob 'label'",
        ),
        # A swept knob nothing has.
        (
            'an.Analysis("w", an.Sweep("freq_scale_hack", 1, 2, points=3))',
            "moves 'freq_scale_hack', which no design it runs on has as a knob",
        ),
        # A held knob nothing has.
        (
            'an.Analysis("h", an.Sweep("sy_half", 4.8, 5.4, points=3), '
            'hold=an.Hold("resonance", adjust=("engine",)))',
            "moves 'engine', which no design it runs on has as a knob",
        ),
        # A state on a catalog design, naming a knob that design lacks.
        (
            'an.Analysis("k", an.Sweep("sy_half", 4.8, 5.4, points=3), '
            'cross=an.Cross(states=(an.State("q", design="dipoles.invvee", sy_half=1.0),)))',
            "sets 'sy_half' in state 'q', and 'dipoles.invvee' has no knob 'sy_half'",
        ),
    ],
)
def test_a_link_knob_the_design_lacks_is_refused_by_name(
    client, fresh_decks, monkeypatch, text, words
):
    # Nothing of the refused analysis is built: no setattr reaches a builder.
    calls = []
    real = analyses_offer.workbench

    def spy(a, *args, **kw):
        calls.append(a.name)
        return real(a, *args, **kw)

    monkeypatch.setattr(analyses_offer, "workbench", spy)
    (entry,) = _open_with(client, text)
    assert entry["workbench"]["runs"] is False
    assert words in entry["workbench"]["why"], entry["workbench"]["why"]
    assert entry["name"] not in calls  # (the generic ones are built, as ever)


def test_cell_builder_never_sets_a_knob_the_design_lacks():
    # The check also guards every analysis's state cell, not only a link's.
    st = an.State("x", build_wires=1)
    with pytest.raises(analyses_offer._Refusal, match="has no knob 'build_wires'"):
        analyses_offer._cell_builder(st, {"geometry": "dipoles.invvee"})


def test_a_link_design_must_be_the_deck_or_the_catalog(client, fresh_decks, tmp_path):
    other = client.post("/deck", json=_payload()).json()["key"]
    sweep = 'an.Sweep("sy_half", 4.8, 5.4, points=3)'
    secret = tmp_path / "secret.nec"
    secret.write_text(DIPOLE)
    # A path ending in the deck's own file name is a path, not the deck.
    (tmp_path / "d.nec").write_text(DIPOLE)
    refused = {
        "path": f"@{secret}",
        "path to a same-named file": f"@{tmp_path / 'd.nec'}",
        "user": "user.anything",
        "stranger's deck": other,
        "unknown": "nowhere.at_all",
    }
    lines = []
    for label, design in refused.items():
        lines.append(
            f'an.Analysis("{label} state", {sweep}, cross=an.Cross(states='
            f'(an.State("s", design={json.dumps(design)}),)))'
        )
        lines.append(
            f'an.Analysis("{label} designs", {sweep}, cross=an.Cross(designs='
            f"({json.dumps(design)}, )))"
        )
    lines.append(
        'an.Analysis("own by file name", an.Sweep("sy_half", 4.8, 5.4, points=3), '
        'cross=an.Cross(states=(an.State("s", design="@d.nec", sy_half=5.0),)))'
    )
    lines.append(
        'an.Analysis("catalog", an.Sweep("sy_half", 4.8, 5.4, points=3), '
        'cross=an.Cross(states=(an.State("s", design="dipoles.invvee"),)))'
    )
    entries = {e["name"]: e for e in _open_with(client, "[" + ", ".join(lines) + "]")}
    for label, design in refused.items():
        for shape in ("state", "designs"):
            w = entries[f"{label} {shape}"]["workbench"]
            assert w["runs"] is False
            assert f"names design {design!r}" in w["why"], w["why"]
            assert "only the opened deck itself or a catalog design" in w["why"]
    # The deck itself and a catalog design pass the check (whatever the
    # analysis then says of them is its own business).
    for name in ("own by file name", "catalog"):
        why = entries[name]["workbench"].get("why") or ""
        assert "names design" not in why


def test_no_link_value_makes_the_server_read_a_file(
    client, fresh_decks, monkeypatch, tmp_path
):
    secret = tmp_path / "secret.nec"
    secret.write_text(DIPOLE)
    s = str(secret)
    text = (
        "["
        f'an.Analysis("a", an.Sweep("sy_half", 4.8, 5.4, points=3), '
        f'cross=an.Cross(states=(an.State("s", design="@{s}"),))), '
        f'an.Analysis("b", an.Sweep("sy_half", 4.8, 5.4, points=3), '
        f'cross=an.Cross(designs=("@{s}", "user.x"))), '
        f'an.Analysis("c", an.Sweep("sy_half", 4.8, 5.4, points=3), '
        f'cross=an.Cross(cells=(an.Cell(an.State("s", design="@{s}")),))), '
        f'an.Optimize("d", an.State("start", design="@{s}"), '
        f'knobs=(an.Knob("sy_half", 4.0, 6.0),), bands=(an.Band(14.0),))'
        "]"
    )
    opened = []

    def watch(real):
        def wrapped(file, *args, **kw):
            opened.append(str(file))
            return real(file, *args, **kw)

        return wrapped

    monkeypatch.setattr(builtins, "open", watch(builtins.open))
    monkeypatch.setattr(io, "open", watch(io.open))
    monkeypatch.setattr(os, "open", watch(os.open))

    def no_file(*a, **k):
        raise AssertionError("a link reached the file importer")

    monkeypatch.setattr(file_designs, "builder_from_file", no_file)
    entries = _open_with(client, text)
    assert len(entries) == 4
    assert all(e["workbench"]["runs"] is False for e in entries)
    assert all("names design" in e["workbench"]["why"] for e in entries)
    assert not [p for p in opened if "secret" in p], opened


@pytest.mark.parametrize("hosted", [False, True], ids=["local", "hosted"])
def test_a_link_may_carry_a_kept_run_on_the_deck(
    client, fresh_decks, monkeypatch, hosted
):
    monkeypatch.setattr(server, "_HOSTED", hosted)
    # An an.Optimize on the deck itself (by its file name, as a kept band run
    # on a deck names it) reads, is listed, and is offered to jump to: no
    # hosted refusal is added for a link's.
    o = an.Optimize(
        "tune half",
        an.State("start", design="@d.nec", sy_half=5.0),
        knobs=(an.Knob("sy_half", 4.0, 6.0),),
        bands=(an.Band(14.0),),
    )
    assert at.read(at.write(o)) == (o,)
    (entry,) = _open_with(client, at.write(o))
    assert entry["name"] == "tune half" and entry["origin"] == "link"
    w = entry["workbench"]
    assert w["runs"] is True and w["kind"] == "optimize", w
    assert w["state"] == {"sy_half": 5.0}


# ---------------------------------------------------------------------------
# Knob ranges a link carries (knobs=, AK#2045): the deck's knobs take them
# ---------------------------------------------------------------------------


def test_a_deck_without_ranges_keeps_its_key():
    # No ranges, or an empty set, hashes as every older link did: pinned
    # literally (the pre-#2045 key) and beside analyses.
    assert decks.deck_key("dipole.nec", DIPOLE, None, None, None) == "deck.51cef6474d59"
    assert decks.deck_key("dipole.nec", DIPOLE, None, None, {}) == "deck.51cef6474d59"
    assert decks.deck_key("dipole.nec", DIPOLE, "nec5", None, {}) == "deck.3357c412c8b5"
    for dialect in (None, "nec2", "nec4", "nec5"):
        assert decks.deck_key("d.nec", SY_DIPOLE, dialect, SWEEP_HALF, {}) == (
            decks.deck_key("d.nec", SY_DIPOLE, dialect, SWEEP_HALF)
        )


def test_open_without_ranges_answers_the_old_key(client, fresh_decks):
    for extra in ({}, {"ranges": ""}, {"ranges": None}):
        body = client.post("/deck", json={**_payload(), **extra}).json()
        assert body["key"] == "deck.51cef6474d59", extra
        assert body["ranges_refusal"] is None


def test_ranges_are_part_of_the_key_in_one_spelling():
    a = {"sy_half": (4.0, 6.0)}
    plain = decks.deck_key("d.nec", SY_DIPOLE)
    ka = decks.deck_key("d.nec", SY_DIPOLE, None, None, a)
    kb = decks.deck_key("d.nec", SY_DIPOLE, None, None, {"sy_half": (4.0, 6.5)})
    assert len({plain, ka, kb}) == 3
    # The bounds' spelling is not part of it: 4 and 4.0 are one range.
    assert decks.deck_key("d.nec", SY_DIPOLE, None, None, {"sy_half": (4, 6)}) == ka
    r1, _ = decks.payload_ranges({"ranges": "sy_half:4:6"})
    r2, _ = decks.payload_ranges({"ranges": "sy_half:4.0:6.00"})
    assert decks.deck_key("d.nec", SY_DIPOLE, None, None, r1) == ka
    assert decks.deck_key("d.nec", SY_DIPOLE, None, None, r2) == ka
    # Ranges and analyses are separate parts.
    assert decks.deck_key("d.nec", SY_DIPOLE, None, SWEEP_HALF, a) not in {
        ka,
        decks.deck_key("d.nec", SY_DIPOLE, None, SWEEP_HALF),
    }


def test_two_links_with_different_ranges_do_not_collide(client, fresh_decks):
    def opened(ranges):
        body = client.post(
            "/deck", json={**_payload(SY_DIPOLE, "d.nec"), "ranges": ranges}
        ).json()
        assert body["ranges_refusal"] is None, body
        (half,) = [p for p in body["example"]["param_schema"] if p["name"] == "sy_half"]
        return body["key"], (half["min"], half["max"], half.get("auto_range"))

    ka, sa = opened("sy_half:4:6")
    kb, sb = opened("sy_half:3:8")
    plain = client.post("/deck", json=_payload(SY_DIPOLE, "d.nec")).json()
    assert len({ka, kb, plain["key"]}) == 3
    assert sa == (4.0, 6.0, False) and sb == (3.0, 8.0, False)
    # The deck opened without ranges keeps the import's own window.
    (half,) = [p for p in plain["example"]["param_schema"] if p["name"] == "sy_half"]
    assert half["auto_range"] is True


@pytest.mark.parametrize(
    ("ranges", "words"),
    [
        ("sy_half:4", "knob range 'sy_half:4' is not <knob>:<min>:<max>"),
        ("sy_half:4:6:8", "knob range 'sy_half:4:6:8' is not <knob>:<min>:<max>"),
        ("1x:4:6", "knob range '1x:4:6' is not <knob>:<min>:<max>"),
        ("sy.half:4:6", "knob range 'sy.half:4:6' is not <knob>:<min>:<max>"),
        ("sy_half:inf:6", "sy_half's range 'sy_half:inf:6' is not two finite numbers"),
        ("sy_half:4:nan", "is not two finite numbers"),
        ("sy_half:0x10:20", "is not two finite numbers"),
        ("sy_half:1_0:20", "is not two finite numbers"),
        ("sy_half:1e999:2e999", "is not two finite numbers"),
        ("sy_half:6:4", "sy_half's range 'sy_half:6:4' does not have min < max"),
        ("sy_half:4:4", "does not have min < max"),
        ("sy_half:4:6,sy_half:3:7", "sy_half is given a range twice"),
        (
            "__import__:1:2",
            "the link gives __import__ a range, and this deck has no knob",
        ),
        (
            "ui_params:1:2",
            "the link gives ui_params a range, and this deck has no knob",
        ),
        ("freq_scale:1:2", "this deck has no knob 'freq_scale'"),
    ],
)
def test_a_bad_range_is_refused_by_name_and_the_deck_opens(
    client, fresh_decks, ranges, words
):
    body = client.post(
        "/deck", json={**_payload(SY_DIPOLE, "d.nec"), "ranges": ranges}
    ).json()
    assert body["key"].startswith("deck."), body
    assert words in (body["ranges_refusal"] or ""), body["ranges_refusal"]
    (half,) = [p for p in body["example"]["param_schema"] if p["name"] == "sy_half"]
    # A refused entry gives no knob a range.
    if "twice" not in words:
        assert half["auto_range"] is True


def test_the_good_ranges_stand_beside_a_refused_one(client, fresh_decks):
    sent = {**_payload(SY_DIPOLE, "d.nec"), "ranges": "nope:1:2,sy_half:4:6,x:9:1"}
    body = client.post("/deck", json=sent).json()
    assert body["ranges_refusal"] == (
        "x's range 'x:9:1' does not have min < max; "
        "the link gives nope a range, and this deck has no knob 'nope'"
    )
    (half,) = [p for p in body["example"]["param_schema"] if p["name"] == "sy_half"]
    assert (half["min"], half["max"]) == (4.0, 6.0)
    # Opened again (already open: no re-parse), the refusal is named again.
    again = client.post("/deck", json=sent).json()
    assert again["key"] == body["key"]
    assert again["ranges_refusal"] == body["ranges_refusal"]


def test_ranges_are_bounded(client, fresh_decks):
    many = ",".join(f"k{i}:0:1" for i in range(decks.MAX_RANGES + 1))
    body = client.post(
        "/deck", json={**_payload(SY_DIPOLE, "d.nec"), "ranges": many}
    ).json()
    assert f"over the {decks.MAX_RANGES} a link may carry" in body["ranges_refusal"]
    long = "sy_half:4:" + "6" * decks.MAX_RANGES_CHARS
    body = client.post(
        "/deck", json={**_payload(SY_DIPOLE, "d.nec"), "ranges": long}
    ).json()
    assert (
        f"over the {decks.MAX_RANGES_CHARS} a link may carry" in body["ranges_refusal"]
    )
    assert body["key"] == decks.deck_key("d.nec", SY_DIPOLE)


def test_ranges_that_are_not_a_string_are_refused_by_name(client, fresh_decks):
    r = client.post(
        "/deck", json={**_payload(SY_DIPOLE, "d.nec"), "ranges": {"sy_half": [4, 6]}}
    )
    assert r.status_code == 422
    assert "ranges must be a string" in r.json()["detail"]


def test_an_evicted_deck_comes_back_with_its_ranges(client, monkeypatch):
    st = replace(server._DECK_SETTINGS, max_open=1)
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(0))
    try:
        sent = {**_payload(SY_DIPOLE, "d.nec"), "ranges": "sy_half:4:6,nope:1:2"}
        key = client.post("/deck", json=sent).json()["key"]
        client.post("/deck", json=_payload())
        assert key not in store and key not in server.EXAMPLES
        assert store.range_refusals(key) == ()
        # The page's payload carries the ranges: the deck comes back under the
        # same key, its knob bounded by them again.
        r = client.post("/geometry", json={"geometry": key, "_deck": sent})
        assert r.status_code == 200, r.text
        assert key in store
        b = analyses_offer.builder_for(
            server.EXAMPLES[key].builder_cls, {"geometry": key}
        )
        assert an._ui(an._params(b))["sy_half"]["min"] == 4.0
        assert store.range_refusals(key) == (
            "the link gives nope a range, and this deck has no knob 'nope'",
        )
        # A payload that dropped the ranges names another design: refused.
        store._decks.clear()
        server.EXAMPLES.pop(key)
        bare = _payload(SY_DIPOLE, "d.nec")
        r = client.post("/geometry", json={"geometry": key, "_deck": bare})
        assert r.status_code == 400
    finally:
        for k in list(server.EXAMPLES):
            if decks.is_deck(k):
                del server.EXAMPLES[k]


def test_without_ranges_the_doublet_deck_holds_are_refused(client, fresh_decks):
    # The gap the link's knobs= closes: a deck's SY knob has no range of its
    # own, so each held branch is listed, refused by name.
    sent = _payload(DOUBLET, "two_wire_doublet.nec", at.pack(_doublet_text()))
    key = client.post("/deck", json=sent).json()["key"]
    links = _links(_listed(client, key))
    for e, held in ((links[1], "sy_short_ft"), (links[2], "sy_long_ft")):
        w = e["workbench"]
        assert w["runs"] is False
        assert f"the hold adjusts {held}, which has no ui_params min/max" in w["why"]


# ---------------------------------------------------------------------------
# Acceptance: the two-wire doublet as a deck, with its three analyses
# ---------------------------------------------------------------------------


def _doublet_text() -> str:
    # The catalog design's three analyses as `write` prints them, on the
    # deck's knobs: an SY constant opens as sy_<name> (file_designs, AK#1705),
    # which is what a page building them on the deck would name.
    text = at.write(Doublet().build_analyses())
    return text.replace('"long_ft"', '"sy_long_ft"').replace(
        '"short_ft"', '"sy_short_ft"'
    )


#: The doublet link's knobs (AK#2045, ``knobs=``): each SY knob's value and
#: the catalog design's own range, which the deck's SY cards cannot say. The
#: values start the panel on the doublet (L = M = 33 ft); the ranges give
#: the two holds something to search.
DOUBLET_KNOBS = "sy_long_ft:33:15:36,sy_short_ft:33:1:34"
#: What the page sends /deck of it: the ranges alone (`lib/deepLink.ts`
#: `knobRanges`), never the values, which are the panel's.
DOUBLET_RANGES = "sy_long_ft:15:36,sy_short_ft:1:34"


def test_acceptance_two_wire_doublet_deck_link(client, fresh_decks):
    text = _doublet_text()
    packed = at.pack(text)
    sent = {
        **_payload(DOUBLET, "two_wire_doublet.nec", packed),
        "ranges": DOUBLET_RANGES,
    }
    # The link: ?deck=<z>&name=<file>&analyses=<z2>&knobs=<...> (base64url
    # needs no escaping, nor does the name; a knobs= colon and comma are
    # written bare, as the link writer writes them).
    link = (
        f"?deck={sent['z']}&name={sent['name']}&analyses={packed}&knobs={DOUBLET_KNOBS}"
    )
    assert len(link) < 2 * decks_max_share()
    print(
        f"\nlink: deck {len(sent['z'])} + analyses {len(packed)} + knobs "
        f"{len(DOUBLET_KNOBS)} chars, query {len(link)} chars"
    )
    body = client.post("/deck", json=sent).json()
    assert body["analyses"] == 3 and body["analyses_refusal"] is None
    assert body["ranges_refusal"] is None
    key = body["key"]
    schema = {p["name"]: p for p in body["example"]["param_schema"]}
    assert (schema["sy_long_ft"]["min"], schema["sy_long_ft"]["max"]) == (15.0, 36.0)
    assert (schema["sy_short_ft"]["min"], schema["sy_short_ft"]["max"]) == (1.0, 34.0)
    links = _links(_listed(client, key))
    assert [e["name"] for e in links] == [a.name for a in Doublet().build_analyses()]
    assert all(e["group"] == "Resonant splits" for e in links)
    # The two held branches run now: the link's ranges bound their holds.
    for e, held, swept in (
        (links[1], "sy_short_ft", "sy_long_ft"),
        (links[2], "sy_long_ft", "sy_short_ft"),
    ):
        w = e["workbench"]
        assert w["runs"] is True, w
        assert w["kind"] == "knob" and w["param"] == swept
        assert w["hold"]["knobs"] == [held]
        assert w["hold"]["bounds"][held] == list(
            (schema[held]["min"], schema[held]["max"])
        )
    resonance_map = links[0]["workbench"]
    assert resonance_map["runs"] is True and resonance_map["kind"] == "map"
    assert resonance_map["x"]["param"] == "sy_long_ft"
    assert resonance_map["y"]["param"] == "sy_short_ft"
    assert len(resonance_map["x"]["values"]) == 41
    assert len(resonance_map["y"]["values"]) == 34
    # Run the map through its own route (POST /map), as the chart does: the
    # axes exactly as /analyses served them, resumed at the grid's last
    # nodes so the test solves three of its 1394 (the route, not the size).
    n = 41 * 34
    r = client.post(
        "/map",
        json={
            "geometry": key,
            "_session": "acceptance",
            "_deck": sent,
            "x": {k: resonance_map["x"][k] for k in ("param", "values")},
            "y": {k: resonance_map["y"][k] for k in ("param", "values")},
            "from": n - 3,
        },
    )
    assert r.status_code == 200, r.text
    recs = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    nodes = [x for x in recs if "i" in x]
    assert recs[-1].get("done") is True, recs
    assert [(x["i"], x["j"]) for x in nodes] == [(38, 33), (39, 33), (40, 33)]
    assert all("error" not in x for x in nodes), nodes
    assert all(x["z_re"] > 0 for x in nodes)
    # Run the high-R branch's first point through its own route (POST
    # /param_sweep with the hold, as the chart does), with the panel at the
    # link's values: M = 33 ft, L held at resonance from the deck's own
    # value (a held curve starts from the design's defaults). The catalog
    # run gives L = 33.0 ft, about 5320 ohms there (AK#2045 acceptance).
    high = links[2]["workbench"]
    r = client.post(
        "/param_sweep",
        json={
            "geometry": key,
            "_session": "acceptance",
            "_deck": sent,
            "sy_long_ft": 33.0,
            "sy_short_ft": 33.0,
            "design_freq_mhz": 14.0,
            "measurement_freq_mhz": 14.0,
            "solver": "momwire",
            "momwire_model": "bspline",
            "ground": False,
            "param": high["param"],
            "values": high["values"][:1],
            "hold": high["hold"]["spec"],
        },
    )
    assert r.status_code == 200, r.text
    recs = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    (point,) = [x for x in recs if "value" in x]
    assert recs[-1].get("done") is True, recs
    assert point["converged"] is True, point
    assert point["value"] == 33.0
    assert 15.0 <= point["held"]["sy_long_ft"] <= 36.0
    print(
        f"high-R point: M = 33 ft, L = {point['held']['sy_long_ft']:.3f} ft, "
        f"Z = {point['z_re']:.1f}{point['z_im']:+.1f}j"
    )
    assert point["held"]["sy_long_ft"] == pytest.approx(33.0, abs=0.3)
    assert abs(point["z_im"]) < 5.0
    assert 4000 < point["z_re"] < 6500


def decks_max_share() -> int:
    # lib/decks.ts MAX_SHARE_CHARS: the deck's own cap in a shared link.
    return 8000
