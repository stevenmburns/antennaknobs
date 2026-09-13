"""AC6LA's QRZ report (2026-09-13) on a deck from the NEC-5 catalog corpus.

Two of his four points are this file's subject.

1. The GN card's NEC-5 ``NOFILE`` sentinel stopped the deck opening:
   "undefined symbol 'nofile'". antennaknobs writes that sentinel itself
   (NEC5Engine, the corpus tool), so a deck saved from a capture must open.
4. The two ground notices contradicted each other. The deck note said GN
   was "not applied" while the ground panel said the app used it. And the
   panel named the wrong model: NEC-5 has no reflection-coefficient ground,
   so a NEC-5 deck's GN 0 is Sommerfeld, not NEC-2's approximation.
"""

from __future__ import annotations

from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec

# dist/nec5_corpus/catalog-nec5/dipoles.invvee.default.somm13.nec, verbatim.
CATALOG_NEC5 = """CM antennaknobs catalog design dipoles.invvee (default mesh, somm13 ground)
CE
GW 1 20 0.000000E+00 5.000000E-02 7.000000E+00 0.000000E+00 2.184661E+00 5.682399E+00 5.000000E-04
GW 2 20 0.000000E+00 -2.184661E+00 5.682399E+00 0.000000E+00 -5.000000E-02 7.000000E+00 5.000000E-04
GW 3 2 0.000000E+00 -5.000000E-02 7.000000E+00 0.000000E+00 5.000000E-02 7.000000E+00 5.000000E-04
GE 1 0
GN 0 0 0 0 1.300000E+01 5.000000E-03 1.000000E+00 0.000000E+00 NOFILE
EX 0 3 1 2 1.000000E+00 0.000000E+00
FR 0 1 0 0 2.847000E+01 0.000000E+00
XQ 0
EN
"""

NEC2_GN0 = "GW 1 11 0 0 5 0 0 15 .001\nGE 1\nGN 0 0 0 0 13 .005\nEX 0 1 6 0 1 0\nEN\n"


def test_the_nofile_sentinel_opens_and_names_the_nec5_dialect():
    deck = parse_nec(CATALOG_NEC5, network=True)
    assert deck.nec5_dialect is True
    assert deck.ground_card == "GN 0"


def test_a_nec5_decks_gn0_is_sommerfeld():
    deck = parse_nec(CATALOG_NEC5, network=True)
    assert deck.ground_spec == ("finite", 13.0, 0.005)
    assert deck.ground_method == "sommerfeld"


def test_an_edge_source_alone_settles_the_dialect():
    """The same deck with NOFILE removed, the edit AC6LA made to open it: the
    EX at a segment END (I4 = 2) is NEC-5-only, so GN 0 still reads as
    Sommerfeld."""
    deck = parse_nec(CATALOG_NEC5.replace(" NOFILE", ""), network=True)
    assert deck.nec5_dialect is True
    assert deck.ground_method == "sommerfeld"


def test_a_nec2_decks_gn0_stays_reflection_coefficients():
    deck = parse_nec(NEC2_GN0)
    assert deck.nec5_dialect is False
    assert deck.ground_spec == ("finite-fast", 13.0, 0.005)
    assert deck.ground_method == "fast"


def test_the_folder_route_seeds_sommerfeld_and_names_the_nec5_card(tmp_path):
    p = tmp_path / "dipoles.invvee.default.somm13.nec"
    p.write_text(CATALOG_NEC5, encoding="utf-8")
    b = builder_from_file(str(p))
    ui = dict(b.default_params)["ui_params"]
    assert ui["ground_seed"] == "sommerfeld"
    assert ui["ground_card"] == "NEC-5 GN 0"
    assert b.file_ground == ("finite", 13.0, 0.005)


def test_the_note_no_longer_calls_the_ground_unapplied(tmp_path):
    p = tmp_path / "dipoles.invvee.default.somm13.nec"
    p.write_text(CATALOG_NEC5, encoding="utf-8")
    ui = dict(builder_from_file(str(p)).default_params)["ui_params"]
    assert ui["notes"] == (
        "Deck cards not applied: XQ (execute request) — the app's own settings "
        "are used instead."
    )


def test_a_nec2_folder_deck_keeps_the_default_label(tmp_path):
    p = tmp_path / "gn0.nec"
    p.write_text(NEC2_GN0, encoding="utf-8")
    ui = dict(builder_from_file(str(p)).default_params)["ui_params"]
    assert ui["ground_seed"] == "fast"
    assert "ground_card" not in ui


def test_examples_serves_the_card_the_panel_names(tmp_path, monkeypatch):
    """The card has to reach the browser, not only `ui_params`. The real-app
    drive on 2026-09-13 found /examples dropping it, so the panel fell back to
    "Sommerfeld (GN 2)" on a deck that says GN 0."""
    from fastapi.testclient import TestClient

    import antennaknobs.web.server as server

    (tmp_path / "dipoles.invvee.default.somm13.nec").write_text(
        CATALOG_NEC5, encoding="utf-8"
    )
    (tmp_path / "gn0.nec").write_text(NEC2_GN0, encoding="utf-8")
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    with TestClient(server.app) as c:
        examples = {e["name"]: e for e in c.get("/examples").json()["examples"]}
    nec5 = examples["user.dipoles.invvee.default.somm13"]
    assert nec5["ground_seed"] == "sommerfeld"
    assert nec5["ground_card"] == "NEC-5 GN 0"
    nec2 = examples["user.gn0"]
    assert nec2["ground_seed"] == "fast"
    assert nec2["ground_card"] is None
