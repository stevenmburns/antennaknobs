"""Issue #418: tolerant tokenization — 4nec2 `'` comments, fused mnemonics,
CM after CE.

Second-largest wild-corpus rejection class (~290 decks post-#417). Every
form pinned here was observed verbatim in the corpus: full-line `'` comments
(including commented-out cards like `'GW ...`), trailing `' comment` after
card fields (`GS 0 0 0.3048 ' All in ft.`), ARRL's fused mnemonics
(`GW1,8,...` / `GE1` / `GN1` / `EX5,1,...` — DIP.NEC's entire body), and CM
cards appearing after CE (icecube Catenary.nec).
"""

import pytest

from antennaknobs.nec_import import parse_nec


BASE = """CE test
GW 1 11 0 0 0 0 0 5 0.001
GE 0
EX 0 1 6 0 1.0 0.0
EN
"""


def test_full_line_quote_comments_skipped():
    deck = parse_nec(
        "CE t\n"
        "'\n"
        "' free-standing comment\n"
        "'GW 9 9 commented-out card, never parsed\n"
        "GW 1 11 0 0 0 0 0 5 0.001\n"
        "GE 0\n"
        "EX 0 1 6 0 1 0\n"
        "EN\n",
        name="t",
    )
    assert len(deck.wires) == 1
    assert deck.wires[0].tag == 1


def test_trailing_quote_comment_on_cards():
    deck = parse_nec(
        "CE t\n"
        "GW 1 11 0 0 0 0 0 5 0.001 'radiator, don't touch\n"
        "GS 0 0 0.3048 ' All in ft.\n"
        "GE 0 'no ground\n"
        "EX 0 1 6 0 1 0\n"
        "EN\n",
        name="t",
    )
    # GS scaled the 5 m wire by 0.3048
    assert deck.wires[0].p2[2] == pytest.approx(5 * 0.3048)


def test_cm_comment_text_keeps_apostrophes():
    deck = parse_nec("CM it's a dipole; don't strip this ' text\n" + BASE, name="t")
    assert "it's a dipole; don't strip this ' text" in deck.comments


def test_cm_after_ce_tolerated():
    deck = parse_nec(
        "CE t\nCM late comment, 4nec2 writes these\n"
        "GW 1 11 0 0 0 0 0 5 0.001\nGE 0\nEX 0 1 6 0 1 0\nEN\n",
        name="t",
    )
    assert len(deck.wires) == 1
    assert "late comment, 4nec2 writes these" in deck.comments


def test_fused_mnemonics_arrl_style():
    """ARRL DIP.NEC verbatim shape: mnemonic glued to the first field."""
    deck = parse_nec(
        "CM DIPOLE OVER IDEAL EARTH\n"
        "CE\n"
        "GW1,8,-1.,0.,1.,1.,0.,1.,.0001\n"
        "GE1\n"
        "GN1\n"
        "FR0,3,0,0,70.,5.\n"
        "EX5,1,4,0,1000.,0.\n"
        "EN\n",
        name="t",
    )
    assert len(deck.wires) == 1
    assert deck.wires[0].n_seg == 8
    assert deck.ground  # GE1 + GN1
    assert deck.feeds[0].seg == 4
    assert deck.freq_mhz == (70.0, 80.0)


def test_fused_negative_field():
    deck = parse_nec(
        "CE t\nGW1,11,0,0,0,0,0,5,.001\nGE0\nEX0,1,6,0,1.,0.\nEN\n", name="t"
    )
    assert deck.wires[0].p2[2] == pytest.approx(5.0)


def test_junk_mnemonics_still_reject():
    with pytest.raises(ValueError, match="mnemonic"):
        parse_nec("CE t\nFOO1 2 3\nEN\n", name="t")
    with pytest.raises(ValueError, match="unrecognised"):
        parse_nec("CE t\nQZ 1 2\nEN\n", name="t")


def test_glued_cm_is_a_comment():
    """NEC identifies cards by the first two columns: `cmRP ...` (however
    cased, no space) is a comment — wild decks use it to comment out cards."""
    deck = parse_nec(
        "CM head\nCE\ncmRP 0 19 37 1000 0 0 5 10\n"
        "GW 1 11 0 0 0 0 0 5 0.001\nGE 0\nEX 0 1 6 0 1 0\nEN\n",
        name="t",
    )
    assert len(deck.wires) == 1
    assert any(c.startswith("RP 0 19") for c in deck.comments)


def test_awg_gauge_radius():
    """4nec2's `#nn` AWG shorthand in a radius field: gauge 12 wire has
    diameter 0.127mm * 92^(24/39) ~ 2.053 mm."""
    deck = parse_nec(
        "CE t\nGW 1 11 0 0 0 0 0 5 #12\nGE 0\nEX 0 1 6 0 1 0\nEN\n",
        name="t",
    )
    assert deck.wires[0].radius == pytest.approx(0.5 * 0.127e-3 * 92.0 ** (24.0 / 39.0))
    with pytest.raises(ValueError, match="wire gauge"):
        parse_nec(
            "CE t\nGW 1 11 0 0 0 0 0 5 #junk\nGE 0\nEX 0 1 6 0 1 0\nEN\n",
            name="t",
        )


def test_quote_only_junk_no_longer_fatal():
    """The census's 'bad number' quote class: a quote glued to a field."""
    deck = parse_nec(
        "CE t\nGW 1 11 0 0 0 0 0 5 0.001'comment glued to the radius\n"
        "GE 0\nEX 0 1 6 0 1 0\nEN\n",
        name="t",
    )
    assert deck.wires[0].radius == pytest.approx(0.001)
