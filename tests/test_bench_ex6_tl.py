"""EX 6 R_BIG subtraction vs. a TL/NT on the driven segment (issue #456).

The EX 6 current-source emulation (issue #442) drives ``V = I·R_BIG`` behind
an ``LD 4`` series ``R_BIG`` and ``bench_deck`` recovers the load impedance by
subtracting ``R_BIG`` from nec2c's reported feed impedance. That subtraction is
only valid when the series R lands *inside* the readout. On the EZNEC-coax
family (DipTL/CardTL/4SQTL) the EX 6 feed shares its segment with a ``TL``: the
line carries the feed current, so nec2c's reported V/I is already the true
driving-point impedance and the R_BIG term never appears. Subtracting there
manufactured a ~−R_BIG resistance (≈ −19,980 Ω references, ΔΓ ≈ 1.3–1.6 with
both engines agreeing against each other). ``feeds_sharing_tl_nt`` identifies
those feeds so the caller skips the subtraction.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bench_nec_corpus import feeds_sharing_tl_nt  # noqa: E402

from antennaknobs.nec_import import parse_nec  # noqa: E402

_DIPOLE = "GW 1 11 0 -5 10 0 5 10 0.001\n"  # 11 segs → feedable middle seg 6


def _deck(cards: str):
    return parse_nec(_DIPOLE + "GE\n" + cards + "EN\n", name="t", network=True)


def test_tl_on_driven_segment_is_flagged():
    """DipTL topology in miniature: TL endpoint anchored on the EX 6 feed's
    own segment → the subtraction must be skipped."""
    deck = _deck("GW 2 1 0 5 10 0 6 10 0.001\nTL 1 6 2 1 50 1.0\nEX 6 1 6 0 1 0\n")
    assert feeds_sharing_tl_nt(deck) == [0]


def test_tl_elsewhere_is_not_flagged():
    """A TL that does not touch the feed's segment leaves the standard
    subtraction in force."""
    deck = _deck("GW 2 3 0 5 10 0 6 10 0.001\nTL 2 1 2 3 50 1.0\nEX 6 1 6 0 1 0\n")
    assert feeds_sharing_tl_nt(deck) == []


def test_nt_on_driven_segment_is_flagged():
    """The same steal-the-readout hazard exists for an NT two-port anchored on
    the driven segment, not just a TL."""
    deck = _deck(
        "GW 2 1 0 5 10 0 6 10 0.001\n"
        "NT 1 6 2 1 0 -0.02 0 0.02 0 -0.02 0\nEX 6 1 6 0 1 0\n"
    )
    assert feeds_sharing_tl_nt(deck) == [0]


def test_multi_feed_flags_only_the_shared_one():
    """Row order follows deck.feeds; only the feed whose segment carries the
    TL is flagged, so the other feed keeps its R_BIG subtraction."""
    deck = _deck(
        "GW 2 11 3 -5 10 3 5 10 0.001\nGW 3 1 0 5 10 0 6 10 0.001\n"
        "TL 1 6 3 1 50 1.0\n"
        "EX 6 2 6 0 1 0\n"  # feed 0: no TL on its segment
        "EX 6 1 6 0 1 0\n"  # feed 1: shares its segment with the TL
    )
    assert feeds_sharing_tl_nt(deck) == [1]


def test_helper_is_source_kind_agnostic():
    """The helper keys off geometry (feed segment vs. TL/NT endpoint), not the
    excitation kind — an EX 0 voltage feed on a TL segment is reported too. The
    caller still gates the actual subtraction on ``feed.current``."""
    deck = _deck("GW 2 1 0 5 10 0 6 10 0.001\nTL 1 6 2 1 50 1.0\nEX 0 1 6 0 1 0\n")
    assert deck.feeds[0].current is False
    assert feeds_sharing_tl_nt(deck) == [0]
