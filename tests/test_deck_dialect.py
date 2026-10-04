"""An imported NEC deck says which dialect it was read in, and why, and the
reader can override it (Steve, 2026-10-04, for 0.96.0).

NEC-2 attaches a source or load at a segment CENTRE, NEC-5 at a segment END,
so the two readings of one deck put every source half a segment apart. The
importer detects NEC-5 from four tells (EZNEC's NEC-5 stamp, a bare
``CM NEC-5``, a ``GN`` ending ``NOFILE``, an ``EX`` in the segment-end form)
and otherwise reads NEC-2 -- silently, until now. A NEC-5 deck with none of
the tells was read half a segment off with nothing on screen saying so.
"""

from __future__ import annotations

import base64
import zlib

import pytest
from fastapi.testclient import TestClient

from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file, builder_from_text
from antennaknobs.nec_import import parse_nec
from antennaknobs.web import decks, server

DIPOLE = """CM dialect test dipole
CE
GW 1 11 0 -5.1 10 0 5.1 10 0.001
GE 0
EX 0 1 6 0 1 0
FR 0 1 0 0 14.0 0
EN
"""

STAMP = "CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.\n"


def _deck(text=DIPOLE, **kw):
    return parse_nec(text, name="d.nec", network=True, **kw)


# --------------------------------------------------------------------------
# what was chosen, and why
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (STAMP + DIPOLE, "EZNEC's stamp on line 1 says NEC-5 format"),
        ("CM NEC-5\n" + DIPOLE, "a CM NEC-5 card on line 1"),
        (
            DIPOLE.replace("GE 0", "GE 1\nGN 2 0 0 0 13 0.005 NOFILE"),
            "the GN card on line 5 ends in NOFILE, which NEC-4 and NEC-5 both "
            "write, and nothing else in the deck says which — choose Read as "
            "NEC-4 if it came from a NEC-4 program",
        ),
        (
            DIPOLE.replace("EX 0 1 6 0", "EX 0 1 -6 0"),
            "the EX card on line 5 is in NEC-5's segment-end form",
        ),
    ],
    ids=["stamp", "cm-nec5", "nofile", "ex-end"],
)
def test_each_tell_reads_nec5_and_names_itself(text, reason):
    d = _deck(text)
    assert (d.dialect, d.dialect_reason, d.dialect_chosen) == ("nec5", reason, None)
    assert d.nec5_dialect
    assert d.dialect_note() == (
        f"Read as NEC-5 (sources and loads at segment ends): {reason}."
    )


def test_no_marker_reads_nec2_and_says_so():
    d = _deck()
    assert (d.dialect, d.dialect_reason) == ("nec2", "no NEC-4 or NEC-5 marker found")
    assert d.dialect_note() == (
        "Read as NEC-2 (sources and loads at segment centres): no NEC-4 or NEC-5 marker found."
    )


def test_the_first_tell_is_the_reason():
    d = _deck("CM NEC-5\n" + DIPOLE.replace("EX 0 1 6 0", "EX 0 1 -6 0"))
    assert d.dialect_reason == "a CM NEC-5 card on line 1"


# --------------------------------------------------------------------------
# the override
# --------------------------------------------------------------------------
def test_forcing_nec5_moves_the_source_to_the_segment_end():
    auto, nec5 = _deck(), _deck(dialect="nec5")
    assert auto.feeds[0].edge == 0 and nec5.feeds[0].edge == 2
    assert nec5.dialect == "nec5" and nec5.dialect_chosen == "nec5"
    assert nec5.dialect_note() == (
        "Read as NEC-5 (sources and loads at segment ends), as chosen; "
        "detection reads it as NEC-2 (no NEC-4 or NEC-5 marker found)."
    )


def test_forcing_nec2_on_a_stamped_deck_reads_centres():
    d = _deck(STAMP + DIPOLE, dialect="nec2")
    assert d.dialect == "nec2" and not d.nec5_dialect and d.feeds[0].edge == 0
    assert d.dialect_detected == "nec5"
    assert "detection reads it as NEC-5 (EZNEC's stamp on line 1" in d.dialect_note()


def test_forcing_nec2_reads_a_nofile_gn_as_nec2():
    """NEC-4.2's own decks end GN with NOFILE (nec_export's nec4 dialect),
    so NOFILE is not NEC-5-only syntax: the choice reads it, GN 0 stays the
    reflection-coefficient ground."""
    d = _deck(
        DIPOLE.replace("GE 0", "GE 1\nGN 0 0 0 0 13 0.005 NOFILE"), dialect="nec2"
    )
    assert d.dialect == "nec2" and d.ground_method == "fast"


@pytest.mark.parametrize("ex", ["EX 0 1 -6 0 1 0", "EX 0 1 6 2 1 0", "EX 4 1 6 0 1 0"])
def test_forcing_nec2_refuses_nec5_only_ex_forms_by_name(ex):
    with pytest.raises(ValueError, match="cannot be read as NEC-2"):
        _deck(DIPOLE.replace("EX 0 1 6 0 1 0", ex), dialect="nec2")


def test_forcing_nec5_refuses_4nec2s_percentage_position():
    with pytest.raises(ValueError, match="4nec2's spelling"):
        _deck(DIPOLE.replace("EX 0 1 6 0", "EX 0 1 50% 0"), dialect="nec5")


def test_a_chosen_dialect_reads_an_uncaptured_eznec_writer():
    text = "CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-9 format.\n" + DIPOLE
    with pytest.raises(ValueError, match="no capture for"):
        _deck(text)
    d = _deck(text, dialect="nec5")
    assert d.dialect_detected is None
    assert "detection refuses it" in d.dialect_note()


def test_an_unknown_dialect_is_refused():
    with pytest.raises(ValueError, match="dialect must be"):
        _deck(dialect="nec7")


def test_forced_nec5_solves_a_different_impedance():
    def z(**kw):
        cls = builder_from_text("d.nec", DIPOLE, **kw)
        return complex(MomwireEngine(cls(), ground=None).impedance()[0])

    auto, nec2, nec5 = z(), z(dialect="nec2"), z(dialect="nec5")
    assert auto == nec2
    assert abs(nec5 - auto) > 1.0, (auto, nec5)


# --------------------------------------------------------------------------
# the note on file designs
# --------------------------------------------------------------------------
def _notes(cls):
    return dict(cls.default_params)["ui_params"]["notes"]


def test_a_folder_deck_says_what_it_was_read_as(tmp_path):
    p = tmp_path / "d.nec"
    p.write_text(STAMP + DIPOLE, encoding="utf-8")
    assert _notes(builder_from_file(str(p))).startswith(
        "Read as NEC-5 (sources and loads at segment ends): EZNEC's stamp on "
        "line 1 says NEC-5 format."
    )
    forced = builder_from_file(str(p), dialect="nec2")
    assert _notes(forced).startswith("Read as NEC-2 (sources and loads at segment")
    assert forced.file_deck_parsed.dialect == "nec2"


def test_an_ssn_refuses_a_chosen_dialect():
    with pytest.raises(ValueError, match="chosen for a .nec deck"):
        builder_from_text("c.ssn", "", dialect="nec5")


def test_sy_knobs_reparse_in_the_chosen_dialect():
    """The knobs re-parse the deck; reading it in another dialect than the
    import would drop them (the default reparse would not reproduce it)."""
    text = DIPOLE.replace(
        "GW 1 11 0 -5.1 10 0 5.1 10 0.001", "SY h=10\nGW 1 11 0 -5.1 h 0 5.1 h 0.001"
    )
    cls = builder_from_text("d.nec", text, dialect="nec5")
    assert cls.file_sy_knobs is not None
    assert cls.file_sy_knobs.deck.dialect == "nec5"


# --------------------------------------------------------------------------
# /deck and the link
# --------------------------------------------------------------------------
def _payload(text=DIPOLE, name="dipole.nec", **kw) -> dict:
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


def test_the_key_separates_dialects_and_auto_keeps_the_old_key():
    old = decks.deck_key("d.nec", DIPOLE)
    assert decks.deck_key("d.nec", DIPOLE, None) == old
    keys = {
        old,
        decks.deck_key("d.nec", DIPOLE, "nec2"),
        decks.deck_key("d.nec", DIPOLE, "nec5"),
    }
    assert len(keys) == 3


def test_deck_answers_what_it_read_and_carries_the_choice(client):
    auto = client.post("/deck", json=_payload()).json()
    assert auto["dialect"] == {
        "read_as": "nec2",
        "reason": "no NEC-4 or NEC-5 marker found",
        "detected": "nec2",
        "chosen": None,
    }
    assert auto["example"]["notes"].startswith("Read as NEC-2")
    nec5 = client.post("/deck", json=_payload(dialect="nec5")).json()
    assert nec5["key"] != auto["key"]
    assert nec5["dialect"]["read_as"] == "nec5" and nec5["dialect"]["chosen"] == "nec5"
    assert nec5["example"]["notes"].startswith("Read as NEC-5")
    same = client.post("/deck", json=_payload(dialect="auto")).json()
    assert same["key"] == auto["key"]


def test_a_request_carrying_the_choice_rebuilds_that_reading(client):
    key = client.post("/deck", json=_payload(dialect="nec5")).json()["key"]
    server._DECK_STORE._decks.clear()
    server.EXAMPLES.pop(key)
    # The auto payload is another design: refused as not this key.
    r = client.post("/geometry", json={"geometry": key, "_deck": _payload()})
    assert r.status_code == 400
    r = client.post(
        "/geometry", json={"geometry": key, "_deck": _payload(dialect="nec5")}
    )
    assert r.status_code == 200, r.text
    assert server.EXAMPLES[key].builder_cls.file_deck_parsed.dialect == "nec5"


def test_deck_refuses_by_name(client):
    bad = client.post("/deck", json=_payload(dialect="nec7"))
    assert bad.status_code == 422 and "dialect must be" in bad.json()["detail"]
    end = client.post(
        "/deck",
        json=_payload(DIPOLE.replace("EX 0 1 6 0", "EX 0 1 -6 0"), dialect="nec2"),
    )
    assert end.status_code == 422
    assert "cannot be read as NEC-2" in end.json()["detail"]


# --------------------------------------------------------------------------
# NEC-4(.2): segment centres, NEC-4's own cards
# --------------------------------------------------------------------------
# EZNEC's External NEC-4.2 slot, captured 2026-10-03 (momwire#1295): every
# deck NEC-4.2-stamped, solved on the licensed NEC-4.2 for these targets
# (scratch/eznec-capture/NEC42-SOLVE-NOTES-2026-10-03.md). Inlined: the
# captures are CRLF byte oracles under scratch/, not test fixtures.
NEC42_HEAD = """CM Dipole in free space
CM
CM EZNEC Pro/2+ v. 7.0.4  2026-10-03 07:53:56
CM
CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-4.2 format.
CE
"""
NEC42_CAPTURES = {
    # capture: (cards after CE, NEC-4.2's Z)
    "0223": (
        "GW 1,11,0.,-.25,0.,0.,.25,0.,.0005\nGE 0,-1\nFR 0,1,0,0,299.7925\n"
        "GN -1\nEX 6,1,6,0,1.414214,0.\nPQ 0\nRP 0,1,361,1000,90.,0.,0.,1.,0.\nEN\n",
        81.7499 + 46.0034j,
    ),
    "0224": (
        "GW 1,11,0.,-.25,0.,0.,.25,0.,.0005\nGE 0,-1\nFR 0,1,0,0,299.7925\n"
        "GN -1\nEX 0,1,6,0,1.414214,0.\nPQ 0\nRP 0,1,361,1000,90.,0.,0.,1.,0.\nEN\n",
        81.7499 + 46.0034j,
    ),
    "0228": (
        "GW 1,11,0.,-.25,10.,0.,.25,10.,.0005\nGE 0,-1\nFR 0,1,0,0,299.7925\n"
        "GN -1\nEX 0,1,6,0,1.414214,0.\nPQ 0\nRP 0,1,361,1000,90.,0.,0.,1.,0.\nEN\n",
        81.7499 + 46.0034j,
    ),
    "0230": (
        "GW 1,11,0.,-.25,10.,0.,.25,10.,.0005\nGE 1,-1\nFR 0,1,0,0,299.7925\n"
        "GN 1,0,0,0,0.,0.\nEX 0,1,6,0,1.414214,0.\nGD 2,0,0,0,13.,.005,0.,0.\n"
        "PQ 0\nRP 0,1,361,1000,75.,0.,0.,1.,0.\nEN\n",
        81.6310 + 44.9372j,
    ),
    "0231": (
        "GW 1,11,0.,-.25,10.,0.,.25,10.,.0005\nGE 1,-1\nFR 0,1,0,0,299.7925\n"
        "GN 2,0,0,0,13.,.005\nEX 0,1,6,0,1.414214,0.\nPQ 0\n"
        "RP 0,1,361,1000,75.,0.,0.,1.,0.\nEN\n",
        81.6784 + 45.4004j,
    ),
    "0232": (
        "GW 1,11,0.,-.25,10.,0.,.25,10.,.0005\nGE 1,-1\nFR 0,1,0,0,299.7925\n"
        "GN 3,0,0,0,13.,.005\nEX 0,1,6,0,1.414214,0.\nPQ 0\n"
        "RP 0,1,361,1000,75.,0.,0.,1.,0.\nEN\n",
        81.6784 + 45.4004j,
    ),
    # Buried 1 m in soil: mesh-unconverged at 11 segments, so no 5 % bar.
    "0239": (
        "GW 1,11,0.,-.25,-1.,0.,.25,-1.,.0005\nGE -1,-1\nFR 0,1,0,0,299.7925\n"
        "GN 3,0,0,0,13.,.005\nEX 6,1,6,0,1.414214,0.\nPQ 0\nXQ 0\nEN\n",
        149.7710 + 143.2080j,
    ),
}


def _nec42_z(text, **kw):
    from momwire import BSplineSolver

    cls = builder_from_text("cap.nec", text, **kw)
    eng = MomwireEngine(cls(), ground=cls.file_ground, solver=BSplineSolver)
    return cls, complex(eng.impedance()[0])


@pytest.mark.parametrize("cap", sorted(NEC42_CAPTURES))
def test_eznec_nec42_captures_read_as_nec4_and_solve_near_nec42(cap):
    cards, target = NEC42_CAPTURES[cap]
    cls, z = _nec42_z(NEC42_HEAD + cards)
    d = cls.file_deck_parsed
    assert (d.dialect, d.dialect_reason) == (
        "nec4",
        "EZNEC's stamp on line 5 says NEC-4.2 format",
    )
    assert _notes(cls).startswith(
        "Read as NEC-4 (sources and loads at segment centres): EZNEC's stamp"
    )
    assert all(f.edge == 0 for f in d.feeds)
    if cap != "0239":
        assert abs(z - target) / abs(target) < 0.05, (cap, z, target)
    else:
        assert z.real > 0  # solves; the 11-segment buried mesh is unconverged


def test_nec4_gn3_is_sommerfeld_where_nec2_reads_4nec2s_mininec():
    text = NEC42_HEAD + NEC42_CAPTURES["0232"][0]
    nec4 = _deck(text)
    assert nec4.ground_spec == ("finite", 13.0, 0.005)
    assert nec4.ground_method == "sommerfeld"
    # Forced NEC-2, the deck reads by NEC-2's (4nec2's) rules: GN 3 is the
    # MININEC-type ground. A decision, not a refusal: the cards are legal
    # NEC-2 (4nec2) cards.
    nec2 = _deck(text, dialect="nec2")
    assert nec2.dialect == "nec2" and nec2.ground_method == "mininec"
    ui = dict(builder_from_text("cap.nec", text).default_params)["ui_params"]
    assert ui["ground_card"] == "NEC-4 GN 3"


def test_nec4_reads_a_ground_table_file_name_and_says_it_did_not_read_it():
    text = DIPOLE.replace("GE 0", "GE 1\nGN 2 0 0 0 13 0.005 SOMEX10.NEC")
    with pytest.raises(ValueError, match="read the deck as NEC-4"):
        _deck(text)
    d = _deck(text, dialect="nec4")
    assert d.ground_spec == ("finite", 13.0, 0.005) and d.ground_file == "SOMEX10.NEC"
    assert d.dialect_note().endswith(
        "The GN card's ground table file SOMEX10.NEC is not read; the ground "
        "is computed from the GN card."
    )


def test_nec4_reads_nofile_as_no_file_and_not_as_nec5():
    stamped = NEC42_HEAD + DIPOLE.replace("GE 0", "GE 1\nGN 2 0 0 0 13 0.005 NOFILE")
    d = _deck(stamped)
    assert d.dialect == "nec4" and not d.nec5_dialect and d.ground_file is None
    # Without the stamp, NOFILE still declares NEC-5 under detection.
    assert (
        _deck(DIPOLE.replace("GE 0", "GE 1\nGN 2 0 0 0 13 0.005 NOFILE")).dialect
        == "nec5"
    )


def test_nec4_refuses_nec5s_segment_end_source():
    with pytest.raises(ValueError, match="cannot be read as NEC-4"):
        _deck(DIPOLE.replace("EX 0 1 6 0", "EX 0 1 -6 0"), dialect="nec4")


def test_nec4_ex6_is_a_current_source_at_the_centre():
    d = _deck(NEC42_HEAD + NEC42_CAPTURES["0223"][0])
    (f,) = d.feeds
    assert f.current and f.edge == 0 and f.seg == 6


@pytest.mark.parametrize("sommerfeld", [2, 3])
def test_nec42_export_round_trips_through_a_nec4_import(sommerfeld):
    from antennaknobs.nec_export import export_nec

    ground = ("finite", 13.0, 0.005)
    src = builder_from_text("d.nec", DIPOLE)
    z0 = complex(MomwireEngine(src(), ground=ground).impedance()[0])
    text = export_nec(src(), ground=ground, dialect="nec42", sommerfeld=sommerfeld)
    cls = builder_from_text("e.nec", text, dialect="nec4")
    assert cls.file_ground == ground
    z = complex(MomwireEngine(cls(), ground=cls.file_ground).impedance()[0])
    assert z == pytest.approx(z0, rel=1e-9)


def test_deck_takes_nec4(client):
    nec4 = client.post("/deck", json=_payload(dialect="nec4")).json()
    assert nec4["dialect"]["read_as"] == "nec4" and nec4["dialect"]["chosen"] == "nec4"
    assert nec4["key"] != client.post("/deck", json=_payload()).json()["key"]


@pytest.mark.parametrize("word", ["NEC-4", "NEC-4.2", "nec4.2"])
def test_cm_nec4_declares_nec4_and_prose_does_not(word):
    d = _deck(f"CM {word}\n" + DIPOLE)
    assert d.dialect == "nec4"
    assert d.dialect_reason == f"a CM {word} card on line 1"
    assert _deck("CM converted from a NEC-4.2 deck\n" + DIPOLE).dialect == "nec2"


@pytest.mark.parametrize("sommerfeld", [2, 3])
def test_nec42_export_round_trips_through_auto_detection(sommerfeld):
    """AK's own NEC-4.2 writer declares the deck, so detection reads its
    `GN ... NOFILE` as NEC-4's no-table-file, not as NEC-5's sentinel; before
    the declaration a GN 3 export came back as the MININEC-type ground."""
    from antennaknobs.nec_export import export_nec

    ground = ("finite", 13.0, 0.005)
    src = builder_from_text("d.nec", DIPOLE)
    z0 = complex(MomwireEngine(src(), ground=ground).impedance()[0])
    text = export_nec(src(), ground=ground, dialect="nec42", sommerfeld=sommerfeld)
    assert "CM NEC-4.2" in text.splitlines()
    cls = builder_from_text("e.nec", text)
    d = cls.file_deck_parsed
    assert d.dialect == "nec4" and not d.nec5_dialect
    assert _notes(cls).startswith(
        "Read as NEC-4 (sources and loads at segment centres): a CM NEC-4.2 card"
    )
    assert cls.file_ground == ground
    z = complex(MomwireEngine(cls(), ground=cls.file_ground).impedance()[0])
    assert z == pytest.approx(z0, rel=1e-9)


def test_the_nec2_export_carries_no_nec4_declaration():
    """The NEC-2 writer's output does not move (the NEC-5 deck is NEC5Engine's
    own writer, untouched)."""
    from antennaknobs.nec_export import export_nec

    src = builder_from_text("d.nec", DIPOLE)
    text = export_nec(src(), ground=("finite", 13.0, 0.005))
    assert "CM NEC-4.2" not in text.splitlines()
    assert builder_from_text("e.nec", text).file_deck_parsed.dialect == "nec2"


# --------------------------------------------------------------------------
# NOFILE rules out NEC-2 but does not say NEC-4 or NEC-5
# --------------------------------------------------------------------------
NOFILE = DIPOLE.replace("GE 0", "GE 1\nGN 2 0 0 0 13 0.005 NOFILE")


def test_a_nofile_only_deck_reads_wholly_as_nec5_and_says_it_was_a_default():
    d = _deck(NOFILE)
    assert d.dialect == "nec5" and d.nec5_dialect
    # The plain EX now reads the declared-NEC-5 way (end 2 of segment 6), as
    # loads and GN 0 already did: no more half-and-half reading.
    assert d.feeds[0].edge == 2
    assert d.dialect_note() == (
        "Read as NEC-5 (sources and loads at segment ends): the GN card on line "
        "5 ends in NOFILE, which NEC-4 and NEC-5 both write, and nothing else in "
        "the deck says which — choose Read as NEC-4 if it came from a NEC-4 "
        "program."
    )


def test_nofile_before_or_after_the_ex_reads_the_same():
    after = NOFILE.replace(
        "GN 2 0 0 0 13 0.005 NOFILE\nEX 0 1 6 0 1 0",
        "EX 0 1 6 0 1 0\nGN 2 0 0 0 13 0.005 NOFILE",
    )
    assert after != NOFILE
    assert _deck(after).feeds[0].edge == 2


@pytest.mark.parametrize(
    "marker",
    ["CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-4.2 format.\n", "CM NEC-4\n"],
    ids=["eznec-nec42-stamp", "cm-nec4"],
)
def test_nofile_with_a_nec4_marker_reads_as_nec4(marker):
    d = _deck(marker + NOFILE)
    assert d.dialect == "nec4" and not d.nec5_dialect and d.feeds[0].edge == 0
    assert d.ground_method == "sommerfeld"


def test_the_nofile_only_plain_ex_solves_as_the_declared_nec5_deck():
    def z(text):
        cls = builder_from_text("d.nec", text)
        return complex(MomwireEngine(cls(), ground=cls.file_ground).impedance()[0])

    now, declared, centre = (
        z(NOFILE),
        z("CM NEC-5\n" + NOFILE),
        z("CM NEC-4\n" + NOFILE),
    )
    assert now == declared
    assert abs(now - centre) > 1.0, (now, centre)


# --------------------------------------------------------------------------
# every export reads back in its own dialect under detection
# --------------------------------------------------------------------------
GROUND = ("finite", 13.0, 0.005)


def _z_of(cls, ground):
    return complex(MomwireEngine(cls(), ground=ground).impedance()[0])


def test_the_nec2_export_round_trips_under_detection():
    from antennaknobs.nec_export import export_nec

    src = builder_from_text("d.nec", DIPOLE)
    text = export_nec(src(), ground=GROUND)
    cls = builder_from_text("e.nec", text)
    assert cls.file_deck_parsed.dialect == "nec2"
    assert _z_of(cls, cls.file_ground) == pytest.approx(_z_of(src, GROUND), rel=1e-9)


def test_the_nec5_export_declares_itself_and_round_trips_under_detection():
    """NEC5Engine's deck carries CM NEC-5 (the export keeps it under its own
    header), so a source at end 1 (I4 = 1, ambiguous without a declaration)
    and a NOFILE ground both read back NEC-5's way."""
    from antennaknobs.nec5_export import export_nec5

    # 12 segments: the middle is a knot, end 2 of segment 6.
    deck12 = "CM NEC-5\n" + DIPOLE.replace(" 11 0 -5.1", " 12 0 -5.1").replace(
        "EX 0 1 6 0", "EX 0 1 6 2"
    )
    src = builder_from_text("d.nec", deck12)
    for ground, name in ((None, "free"), (GROUND, "somm13")):
        text = export_nec5(
            src(), ground=ground, design="d", rung="default", ground_name=name
        )
        assert "CM NEC-5" in text.splitlines()
        cls = builder_from_text("e.nec", text)
        d = cls.file_deck_parsed
        assert d.dialect == "nec5" and d.dialect_reason.startswith("a CM NEC-5 card")
        assert _z_of(cls, cls.file_ground) == pytest.approx(
            _z_of(src, ground), rel=1e-9
        )


# Dan's vertical dipole (AC6LA, AK scratch/dan-176-bump/som-dan.nec): GN 2 ...
# NOFILE is its only marker, and the licensed NEC-5 (x13) solved it to
# 87.321 - j2.6375 with the source at the END of segment 11 (20 segments, so
# 0.55 of the wire). Read half-and-half (the source at the segment centre, as
# before), razor-2p -- NEC-5's own formulation -- lands 1.65 ohm off; read
# wholly NEC-5 it lands within 0.01.
DAN_VERTICAL = """CM Dan AC6LA NE0 XYZ Dipole: vertical 20.4 m dipole, centre 12 m, 7.2 MHz
CE
GW 1 20 0 0 1.8 0 0 22.2 1.000000e-03
GE -1
GN 2 0 0 0 13.0 0.005 0 0 NOFILE
FR 0 1 0 0 7.2 1
EX 0 1 11 0 1.000000e+00
XQ
EN
"""


def test_a_nofile_only_nec5_deck_now_matches_nec5():
    from momwire import RazorSolver

    cls = builder_from_text("som-dan.nec", DAN_VERTICAL)
    assert cls.file_deck_parsed.feeds[0].edge == 2
    z = complex(
        MomwireEngine(
            cls(),
            ground=cls.file_ground,
            solver=RazorSolver,
            solver_kwargs={"nec5_quadrature": True},
        ).impedance()[0]
    )
    assert abs(z - (87.321 - 2.6375j)) < 0.1, z
