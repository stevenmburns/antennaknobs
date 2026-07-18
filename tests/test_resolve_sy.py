"""Issue #439: ``resolve_sy`` — materialize 4nec2-dialect decks as plain
NEC-2 text so a reference engine that knows nothing of the dialect (vanilla
nec2c) can read them.

The contract under test: the resolved text is (a) dialect-free — no SY
cards, no ``'`` comments, no ``#AWG`` gauges, no fused mnemonics, every
field a plain decimal — and (b) semantically identical, i.e. ``parse_nec``
extracts the same wires/feeds/frequency from original and resolved text.
"""

import math

import pytest

from antennaknobs.nec_import import parse_nec, resolve_sy


def _tokens(resolved):
    return [line.split() for line in resolved.strip().splitlines()]


def _assert_plain(resolved):
    """Every non-comment field must be a number Python's float() accepts."""
    for toks in _tokens(resolved):
        assert toks[0].isalpha() and len(toks[0]) == 2 and toks[0].isupper()
        if toks[0] in ("CM", "CE"):
            continue
        assert toks[0] != "SY", "SY card leaked into resolved text"
        for t in toks[1:]:
            float(t)  # raises on anything exotic


def _assert_same_deck(original, resolved):
    a = parse_nec(original, name="orig")
    b = parse_nec(resolved, name="resolved")
    assert len(a.wires) == len(b.wires)
    for wa, wb in zip(a.wires, b.wires):
        assert wa.n_seg == wb.n_seg
        assert wa.p1 == pytest.approx(wb.p1)
        assert wa.p2 == pytest.approx(wb.p2)
        assert wa.radius == pytest.approx(wb.radius)
    assert [(f.wire, f.seg) for f in a.feeds] == [(f.wire, f.seg) for f in b.feeds]
    assert a.freq_mhz == pytest.approx(b.freq_mhz)


SY_DECK = """CE 4nec2-style deck
SY h=12.5, len=2*h  'total height
GW 1 11 0 0 0 0 0 len #14
GE 0
EX 0 1 6 0 1.0 0.0
FR 0 1 0 0 14.1 0
EN
"""


def test_sy_substitution_round_trip():
    resolved = resolve_sy(SY_DECK, name="t")
    _assert_plain(resolved)
    _assert_same_deck(SY_DECK, resolved)
    gw = next(t for t in _tokens(resolved) if t[0] == "GW")
    assert float(gw[8]) == pytest.approx(25.0)  # len = 2*h
    # AWG 14 radius in metres
    assert float(gw[9]) == pytest.approx(0.5 * 0.127e-3 * 92 ** (22 / 39))


def test_plain_numbers_kept_verbatim():
    deck = "CE\nGW 1 11 0 0 0 0 0 1.E+01 1.0e-3\nGE 0\nEX 0 1 6 0 1. 0.\nEN\n"
    resolved = resolve_sy(deck, name="t")
    gw = next(t for t in _tokens(resolved) if t[0] == "GW")
    # untouched fields keep their original spelling, exponent style and all
    assert gw[8] == "1.E+01" and gw[9] == "1.0e-3"


def test_comment_conventions_dropped():
    deck = (
        "CM a comment\nCE\n"
        "'GW 9 9 this whole card is commented out\n"
        "GW 1 11 0 0 0 0 0 10 0.001 'eol comment\n"
        "cmRP 0 1 1 1000 0 0 0 0\n"
        "GE 0\nEX 0 1 6 0 1 0\nEN\ntrailing junk after EN\n"
    )
    resolved = resolve_sy(deck, name="t")
    _assert_plain(resolved)
    lines = resolved.strip().splitlines()
    assert lines[0] == "CM a comment" and lines[1] == "CE"
    assert not any("junk" in ln or "commented" in ln for ln in lines)
    assert sum(ln.startswith("GW") for ln in lines) == 1
    assert lines[-1] == "EN"


def test_fused_mnemonic_and_commas_normalized():
    deck = "CE\nGW1,11,0,0,0,0,0,10,.001\nGE0\nEX0,1,6,0,1,0\nEN\n"
    resolved = resolve_sy(deck, name="t")
    _assert_plain(resolved)
    _assert_same_deck(deck, resolved)


def test_ce_inserted_when_missing():
    deck = "CM only a CM, no CE\nGW 1 3 0 0 0 0 0 1 .001\nGE 0\nEN\n"
    lines = resolve_sy(deck, name="t").strip().splitlines()
    assert lines[0].startswith("CM") and lines[1] == "CE"
    assert lines[2].startswith("GW")


def test_no_comments_no_ce_invented():
    deck = "GW 1 3 0 0 0 0 0 1 .001\nGE 0\nEN\n"
    lines = resolve_sy(deck, name="t").strip().splitlines()
    assert lines[0].startswith("GW")


def test_sy_reassignment_mid_deck():
    deck = (
        "CE\nSY h=1\nGW 1 3 0 0 0 0 0 h .001\n"
        "SY h=2\nGW 2 3 1 0 0 1 0 h .001\nGE 0\nEN\n"
    )
    resolved = resolve_sy(deck, name="t")
    gws = [t for t in _tokens(resolved) if t[0] == "GW"]
    assert float(gws[0][8]) == 1 and float(gws[1][8]) == 2


def test_fortran_d_exponent_reformatted():
    deck = "CE\nGW 1 3 0 0 0 0 0 1.0D+01 .001\nGE 0\nEN\n"
    gw = next(t for t in _tokens(resolve_sy(deck, name="t")) if t[0] == "GW")
    assert "D" not in gw[8] and float(gw[8]) == 10


def test_unsupported_cards_pass_through_resolved():
    # parse_nec refuses SP; resolve_sy is lexical and must not
    deck = "CE\nSY s=0.1\nGW 1 3 0 0 0 0 0 1 .001\nSP 0 0 s 0 0 0\nGE 0\nEN\n"
    sp = next(t for t in _tokens(resolve_sy(deck, name="t")) if t[0] == "SP")
    assert float(sp[3]) == pytest.approx(0.1)


def test_degrees_trig_and_units():
    deck = "CE\nSY a=sin(30)\nGW 1 3 0 0 0 0 0 90ft a\nGE 0\nEN\n"
    gw = next(t for t in _tokens(resolve_sy(deck, name="t")) if t[0] == "GW")
    assert float(gw[8]) == pytest.approx(90 * 0.3048)  # juxtaposed unit
    assert float(gw[9]) == pytest.approx(math.sin(math.radians(30)))


def test_integral_values_emit_as_integers():
    deck = "CE\nSY n=3+8\nGW 1 n 0 0 0 0 0 1 .001\nGE 0\nEN\n"
    gw = next(t for t in _tokens(resolve_sy(deck, name="t")) if t[0] == "GW")
    assert gw[2] == "11"


def test_bad_expression_raises_with_location():
    with pytest.raises(ValueError, match="line 2"):
        resolve_sy("CE\nSY h=nosuchfn(3)\nEN\n", name="t")


def test_filename_fields_kept_verbatim():
    # GN's Sommerfeld-grid and WG's output filenames are strings, not
    # expressions — they must survive untouched, not raise
    deck = (
        "CE\nGW 1 3 0 0 0 -2 0 0 .01\nGE -1\n"
        "GN 2 0 0 0 10. 0.01 SOMEX10.NEC\nWG radials-vg\nEN\n"
    )
    resolved = resolve_sy(deck, name="t")
    assert "SOMEX10.NEC" in resolved and "radials-vg" in resolved
