"""Dialect-detection tests for nec_import (#824): the NEC-5 edge-source
EX form must be recognised and refused precisely, never silently misread
as an NEC-2 center-gap feed."""

import pytest

from antennaknobs.nec_import import parse_nec


# --------------------------------------------------------------------------
# NEC-5 edge-source EX form (#824)
# --------------------------------------------------------------------------

_EDGE_DECK = """CM nec5 edge source
CE
GW 1 20 0 0 -2.5 0 0 2.5 .001
GE 0
EX 0 1 {seg} {i4} 1 0
FR 0 1 0 0 28.5 0
EN
"""


def test_nec5_edge_source_i4_refuses_precisely():
    """NEC-5 puts sources at segment ENDS: I4=2 selects end 2 (and is not a
    legal NEC-2 print-flag value, so it is unambiguous). The importer must
    refuse with the dialect named — never silently shift the feed half a
    segment to the NEC-2 center-gap reading (#824)."""
    with pytest.raises(ValueError, match="NEC-5 edge-source"):
        parse_nec(_EDGE_DECK.format(seg=10, i4=2))


def test_nec5_edge_source_negative_segment_refuses_precisely():
    """The I4=0 spelling: a NEGATIVE segment number selects end 1."""
    with pytest.raises(ValueError, match="NEC-5 edge-source"):
        parse_nec(_EDGE_DECK.format(seg=-10, i4=0))


def test_nec2_print_flag_i4_still_imports():
    """I4=1 is a legal NEC-2 print-control value (and only ambiguously the
    NEC-5 end-1 form) — it keeps its NEC-2 meaning: the feed imports as the
    ordinary center gap."""
    deck = parse_nec(_EDGE_DECK.format(seg=10, i4=1))
    assert len(deck.feeds) == 1
    assert deck.feeds[0].seg == 10
