"""The 2026-09-08 parse-census quartet (#1272, #1273, #1274, #1275): four
dialect forms the wild corpus writes that the importer rejected, each ported
from the NEC-5 corpus translator (scripts/nec5_corpus) where they were first
fixed against the same decks.

Every acceptance is paired with a behaviour assertion (the value the field
resolves to, the sentence a refusal carries, the note a truncation leaves),
so deleting the fix fails the test rather than merely changing a count.
"""

import math

import pytest

from antennaknobs.nec_import import parse_nec, resolve_sy

AWG12_M = 0.5 * 0.127e-3 * 92.0 ** ((36.0 - 12) / 39.0)


def _deck(*cards: str) -> str:
    return "CE\n" + "\n".join(cards) + "\nGE 0\nEX 0 1 3 0 1 0\nEN\n"


# --- #1272a: AWG gauge with a unit tail -----------------------------------


def test_gauge_per_unit_is_the_radius_in_that_unit():
    # A deck in feet (GS 0 0 0.3048 at the end) writes its radius in feet too.
    deck = _deck("GW 1 5 0 0 0 0 0 31.915 #12/ft")
    d = parse_nec(deck)
    assert d.wires[0].radius == pytest.approx(AWG12_M / 0.3048)


def test_gauge_per_inch():
    d = parse_nec(_deck("GW 1 5 0 0 0 0 0 10 #14/in"))
    awg14 = 0.5 * 0.127e-3 * 92.0 ** ((36.0 - 14) / 39.0)
    assert d.wires[0].radius == pytest.approx(awg14 / 0.0254)


def test_bare_gauge_still_metres():
    d = parse_nec(_deck("GW 1 5 0 0 0 0 0 10 #12"))
    assert d.wires[0].radius == pytest.approx(AWG12_M)


def test_gauge_inside_sy_expression():
    deck = "CE\nSY D = #12/in\nGW 1 5 0 0 0 0 0 10 D\nGE 0\nEX 0 1 3 0 1 0\nEN\n"
    d = parse_nec(deck)
    assert d.wires[0].radius == pytest.approx(AWG12_M / 0.0254)
    # resolve_sy materialises the same number for nec2c.
    resolved = resolve_sy(deck)
    gw = next(ln for ln in resolved.splitlines() if ln.startswith("GW"))
    assert float(gw.split()[-1]) == pytest.approx(AWG12_M / 0.0254)


def test_bad_gauge_still_refused_by_name():
    with pytest.raises(ValueError, match="bad wire gauge"):
        parse_nec(_deck("GW 1 5 0 0 0 0 0 10 #xx"))


# --- #1272b: CE glued to its text ------------------------------------------


def test_ce_glued_to_comment_text_is_the_ce_card():
    deck = "CMTHE PATCH MODEL\nCEFOR THIS RUN  *** KA=2.9 ***\nGW 1 5 0 0 0 0 0 10 .001\nGE 0\nEX 0 1 3 0 1 0\nEN\n"
    d = parse_nec(deck)
    assert len(d.wires) == 1
    assert list(d.comments) == ["THE PATCH MODEL"]
    # resolve_sy keeps the CE as a bare card, text and all.
    assert "CE" in resolve_sy(deck).splitlines()[1]


# --- #1273: expressions with spaces inside parentheses / tab fields --------


def test_gm_expression_with_spaces_inside_parentheses():
    deck = (
        "CE\nSY dHelix=200\nSY dCplLoop=40\nSY clSep=10\nSY clZ=50\n"
        "GW 1 5 0 0 0 0 0 1 .001\n"
        "GM 0 0 0 0 0 (dHelix/2 - dCplLoop/2 - clSep)/1000 0 clZ/1000 1\n"
        "GE 0\nEX 0 1 3 0 1 0\nEN\n"
    )
    d = parse_nec(deck)
    # (100 - 20 - 10)/1000 = 0.07 m along x, 0.05 m along z.
    assert d.wires[0].p1[0] == pytest.approx(0.07)
    assert d.wires[0].p1[2] == pytest.approx(0.05)


def test_tab_delimited_expression_with_spaced_operators():
    deck = (
        "CE\nSY Fz=0.030886\n"
        "GW\t1\t5\t0\t0\t0\t0\t0\t1\t.001\n"
        "GM\t0\t0\t0\t0\t0\t0.023475\t0\tFz + 0.24529\t1\n"
        "GE 0\nEX 0 1 3 0 1 0\nEN\n"
    )
    d = parse_nec(deck)
    assert d.wires[0].p1[0] == pytest.approx(0.023475)
    assert d.wires[0].p1[2] == pytest.approx(0.030886 + 0.24529)


def test_mixed_tab_and_space_deck_keeps_plain_numbers_apart():
    # A tab field that holds several space-separated plain numbers is still
    # several fields (the ElevatRad / G5RV shape).
    deck = "CE\nGW 1 4\t0.0 0.0 0.01778\t0.0 0.0 0.5\t0.0012941\nGE 0\nEX 0 1 2 0 1 0\nEN\n"
    d = parse_nec(deck)
    assert d.wires[0].p2[2] == pytest.approx(0.5)
    assert d.wires[0].radius == pytest.approx(0.0012941)


# --- #1274: a GN card naming a Sommerfeld ground file ----------------------


def test_gn_ground_file_is_refused_by_name_not_as_a_syntax_error():
    deck = _deck("GW 1 5 0 0 1 0 0 11 .001", "GN 2 0 0 0 10. 0.01 SOMEX10.NEC")
    with pytest.raises(ValueError, match="Sommerfeld ground file \\(SOMEX10.NEC\\)"):
        parse_nec(deck)


def test_gn_without_a_file_still_imports():
    d = parse_nec(_deck("GW 1 5 0 0 1 0 0 11 .001", "GN 2 0 0 0 10. 0.01"))
    assert d.ground is True


# --- #1275: NX ends the first structure ------------------------------------


def test_nx_imports_the_first_structure_and_says_so():
    deck = (
        "CE first\nGW 1 5 0 0 0 0 0 10 .001\nGE 0\nEX 0 1 3 0 1 0\nRP 0 1 1 1000 0 0 0 0\n"
        "NX\nCM second antenna\nCE\nGW 7 9 0 0 0 0 0 20 .002\nGE 0\nEX 0 7 5 0 1 0\nEN\n"
    )
    d = parse_nec(deck)
    assert len(d.wires) == 1 and d.wires[0].n_seg == 5
    assert "NX" in d.ignored
    assert "only the first structure" in (d.skipped_note() or "")


def test_deck_without_nx_carries_no_nx_note():
    d = parse_nec(_deck("GW 1 5 0 0 0 0 0 10 .001"))
    assert "NX" not in d.ignored
    assert math.isfinite(d.wires[0].radius)
