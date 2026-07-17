"""Issue #417: SY symbolic variables (4nec2 extension) — evaluate and
substitute.

SY was the single largest importer gap in the 2026-07-16 wild-corpus census
(642 of 1,082 rejections). Real-world usage this suite pins, all observed in
the corpus: spaces around `=` and inside expressions, trailing `'` comments
on the SY line, multi-assignment lines (`SY a=1, b=2`), case-insensitive
references, `^` for power, and 4nec2's BASIC-flavored function set with
trig in DEGREES (`sin(360*x)`, `atn`, `sqr` = square root).
"""

import math

import pytest

from antennaknobs.nec_import import parse_nec


def _deck(sy_lines, gw_fields="0 0 0 0 0 h 0.001"):
    sy = "\n".join(sy_lines)
    return f"""CE test
{sy}
GW 1 11 {gw_fields}
GE 0
EX 0 1 6 0 1.0 0.0
EN
"""


def _z_top(deck):
    return deck.wires[0].p2[2]


def test_simple_constant():
    deck = parse_nec(_deck(["SY h=12.5"]), name="t")
    assert _z_top(deck) == pytest.approx(12.5)


def test_spaces_and_case_insensitive():
    deck = parse_nec(
        _deck(["SY W0 = 0.005"], gw_fields="-w0/2 0 0 w0/2 0 0 W0"), name="t"
    )
    w = deck.wires[0]
    assert w.p1[0] == pytest.approx(-0.0025)
    assert w.p2[0] == pytest.approx(0.0025)
    assert w.radius == pytest.approx(0.005)


def test_arithmetic_with_references():
    deck = parse_nec(_deck(["SY a=2", "SY h=3*a/2 + 1"]), name="t")
    assert _z_top(deck) == pytest.approx(4.0)


def test_expression_in_card_field():
    deck = parse_nec(_deck(["SY ph=8"], gw_fields="0 0 0 0 0 3*ph/4 0.001"), name="t")
    assert _z_top(deck) == pytest.approx(6.0)


def test_caret_is_power():
    deck = parse_nec(_deck(["SY h=2^3"]), name="t")
    assert _z_top(deck) == pytest.approx(8.0)


def test_trig_in_degrees():
    deck = parse_nec(_deck(["SY h=10*sin(30)"]), name="t")
    assert _z_top(deck) == pytest.approx(5.0)


def test_basic_flavored_functions():
    deck = parse_nec(_deck(["SY h=sqr(9) + atn(1)/45 + int(1.9)"]), name="t")
    # sqr = square root (BASIC), atn = arctan in degrees, int truncates.
    assert _z_top(deck) == pytest.approx(3.0 + 1.0 + 1.0)


def test_pi_constant():
    deck = parse_nec(_deck(["SY h=pi"]), name="t")
    assert _z_top(deck) == pytest.approx(math.pi)


def test_multi_assignment_line():
    deck = parse_nec(_deck(["SY a=1.5, h=a+0.5"]), name="t")
    assert _z_top(deck) == pytest.approx(2.0)


def test_trailing_quote_comment():
    deck = parse_nec(_deck(["SY h=0.5*30/1000\t'radiator height, mm to m"]), name="t")
    assert _z_top(deck) == pytest.approx(0.015)


def test_paren_protected_commas_in_multi_assign():
    deck = parse_nec(_deck(["SY a=30, h=10*sin(a), w=a/30"]), name="t")
    assert _z_top(deck) == pytest.approx(5.0)


def test_unit_scale_symbols():
    """4nec2 predefines metric/imperial scale symbols: `SY r = 1.5 * mm`
    (xnec2c's sy_units_spaces fixture). A deck's own definition shadows."""
    deck = parse_nec(_deck(["SY h = 1.5 * mm"]), name="t")
    assert _z_top(deck) == pytest.approx(0.0015)
    shadowed = parse_nec(_deck(["SY mm=2", "SY h=3*mm"]), name="t")
    assert _z_top(shadowed) == pytest.approx(6.0)


def test_juxtaposed_units():
    """`SY X=135 ft` — implicit multiplication, unit names only (seen in
    the icecube/W2FMI-style decks)."""
    deck = parse_nec(_deck(["SY h=135 ft"]), name="t")
    assert _z_top(deck) == pytest.approx(135 * 0.3048)
    glued = parse_nec(_deck(["SY h=61ft"]), name="t")
    assert _z_top(glued) == pytest.approx(61 * 0.3048)
    # exponent letters are not units
    sci = parse_nec(_deck(["SY h=1.5e1"]), name="t")
    assert _z_top(sci) == pytest.approx(15.0)
    # electrical suffixes (`SY C=36.6pF`) — scale factors like the metric ones
    cap = parse_nec(_deck(["SY c=36.6pF", "SY h=c*1e9"]), name="t")
    assert _z_top(cap) == pytest.approx(36.6e-3)


def test_python_keyword_symbol_names():
    """`lambda` is the most idiomatic antenna symbol there is — and a Python
    keyword. xnec2c's own SY fixtures use it."""
    deck = parse_nec(_deck(["SY lambda=299.8/14.1", "SY h=lambda/4"]), name="t")
    assert _z_top(deck) == pytest.approx(299.8 / 14.1 / 4)


def test_undefined_symbol_is_clean_rejection():
    with pytest.raises(ValueError, match="undefined symbol"):
        parse_nec(_deck([""], gw_fields="0 0 0 0 0 nosuch 0.001"), name="t")


def test_bad_sy_expression_is_clean_rejection():
    # `import` is just an undefined symbol to the Pratt parser — Python
    # keywords have no special status in 4nec2's grammar (#424).
    with pytest.raises(ValueError, match="SY|undefined symbol"):
        parse_nec(_deck(["SY h=import os"]), name="t")


def test_sy_not_listed_as_ignored():
    deck = parse_nec(_deck(["SY h=1"]), name="t")
    assert "SY" not in deck.ignored


def test_plain_numbers_still_reject_garbage():
    with pytest.raises(ValueError, match="bad number|undefined symbol"):
        parse_nec(_deck([""], gw_fields="0 0 0 0 0 12..5 0.001"), name="t")
