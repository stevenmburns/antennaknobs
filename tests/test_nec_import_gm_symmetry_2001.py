""".nec import: the symmetric cell across an in-place, renumbering ``GM``
(the importer's half of momwire#2001).

``GM ITGI 0 ...`` moves the block from ITS on in place AND adds ITGI to its
nonzero tags (AK#2124). NEC's MOVE keeps a ``GX``/``GR`` symmetry only when it
neither replicates nor restricts: ``NRPT == 0`` and the block starting at the
first segment. The importer decided the second half by looking ITS up again
AFTER the card ran, by which time the block had been renumbered, so a deck
that rotated a structure and then moved all of it with a tag increment was
refused ("GM card: no wire has tag 1"). The block starts at the first wire
exactly when that wire carried ITS before the card, which is how momwire's
reader decides it since momwire#2001 (nec2c 1.17 and NEC-4.2 renumber the same
way).

Every deck here is synthetic. The momwire comparison runs only where the
installed momwire's NEC-2 reader renumbers, probed on a deck rather than read
off a version.
"""

from __future__ import annotations

import pytest

from antennaknobs.nec_import import parse_nec


def deck(geometry: str, ex: str = "EX 0 6 3 0 1. 0.") -> str:
    """A 5-segment vertical tagged 1, the geometry under test, one source."""
    return (
        "CM gm symmetry probe\nCE\n"
        "GW 1 5 0.5 0. 0. 0.5 0. 1. 0.001\n"
        f"{geometry}"
        "GE 0\n"
        f"{ex}\n"
        "FR 0 1 0 0 150.\n"
        "XQ\nEN\n"
    )


def tags(d):
    return [w.tag for w in d.wires]


# GR 1 4 makes tags 1..4; GM 5 0 ... ITS 1 then moves all four 1 m up and
# renumbers them 6..9. A whole-structure congruence: the cell survives.
WHOLE_MOVE = "GR 1 4\nGM 5 0 0. 0. 0. 0. 0. 1. 1.\n"


def test_a_renumbering_move_of_the_whole_structure_keeps_the_cell():
    d = parse_nec(deck(WHOLE_MOVE), network=True, name="x")
    assert tags(d) == [6, 7, 8, 9]
    assert d.symmetry_cell == 5


def test_the_new_tag_answers_and_the_old_one_is_refused():
    parse_nec(deck(WHOLE_MOVE, "EX 0 9 3 0 1. 0."), network=True, name="x")
    with pytest.raises(ValueError, match="no wire has tag 1"):
        parse_nec(deck(WHOLE_MOVE, "EX 0 1 3 0 1. 0."), network=True, name="x")


def test_its_past_the_first_wire_moves_only_its_block_and_drops_the_cell():
    """ITS 3: wires ahead of it keep their tags; the move is selective, so the
    symmetry ends."""
    d = parse_nec(
        deck("GR 1 4\nGM 5 0 0. 0. 0. 0. 0. 1. 3.\n", "EX 0 1 3 0 1. 0."),
        network=True,
        name="x",
    )
    assert tags(d) == [1, 2, 8, 9]
    assert d.symmetry_cell is None
    with pytest.raises(ValueError, match="no wire has tag 3"):
        parse_nec(
            deck("GR 1 4\nGM 5 0 0. 0. 0. 0. 0. 1. 3.\n", "EX 0 3 3 0 1. 0."),
            network=True,
            name="x",
        )


def test_tag_zero_stays_zero_and_its_zero_is_the_whole_structure():
    text = (
        "CM\nCE\nGW 0 5 0.5 0. 0. 0.5 0. 1. 0.001\nGR 0 4\n"
        "GM 5 0 0. 0. 0. 0. 0. 1. 0.\nGE 0\nEX 0 0 3 0 1. 0.\n"
        "FR 0 1 0 0 150.\nXQ\nEN\n"
    )
    d = parse_nec(text, network=True, name="x")
    assert tags(d) == [0, 0, 0, 0]
    assert d.symmetry_cell == 5


def test_a_replicating_gm_keeps_the_old_tags_and_drops_the_cell():
    """NRPT > 0 is unchanged: copies take the increment, the originals keep
    their tags, and replication ends the symmetry."""
    d = parse_nec(
        deck("GR 1 4\nGM 4 1 0. 0. 0. 0. 0. 1. 1.\n", "EX 0 1 3 0 1. 0."),
        network=True,
        name="x",
    )
    assert tags(d) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert d.symmetry_cell is None


def test_a_move_with_no_symmetry_to_keep_still_renumbers():
    d = parse_nec(
        deck(
            "GW 2 5 1.5 0. 0. 1.5 0. 1. 0.001\nGM 10 0 0. 0. 0. 0. 0. 1. 2.\n",
            "EX 0 12 3 0 1. 0.",
        ),
        network=True,
        name="x",
    )
    assert tags(d) == [1, 12]
    assert d.symmetry_cell is None


# --- against momwire's reader --------------------------------------------------

CASES = {
    "whole move": WHOLE_MOVE,
    "its 3": "GR 1 4\nGM 5 0 0. 0. 0. 0. 0. 1. 3.\n",
    "replicating": "GR 1 4\nGM 4 1 0. 0. 0. 0. 0. 1. 1.\n",
    "no symmetry": "GW 2 5 1.5 0. 0. 1.5 0. 1. 0.001\nGM 10 0 0. 0. 0. 0. 0. 1. 2.\n",
}


def _momwire_structure(text):
    from momwire.deck._cards import parse_card
    from momwire.deck._nec2 import _GEOMETRY_CARDS
    from momwire.deck._nec2_geometry import build_geometry

    cards = []
    for line in text.splitlines():
        card = parse_card(line)
        if card is not None and card.mnemonic in _GEOMETRY_CARDS:
            cards.append(card)
    return build_geometry(cards)


def _momwire_renumbers() -> bool:
    try:
        s = _momwire_structure(deck("GM 5 0 0. 0. 0. 0. 0. 1. 1.\n"))
    except Exception:  # noqa: BLE001 — a reader that refuses the deck predates the rule
        return False
    return [w.tag for w in s.wires] == [6]


@pytest.mark.skipif(
    not _momwire_renumbers(),
    reason="the installed momwire's NEC-2 reader predates momwire#2001's renumbering",
)
@pytest.mark.parametrize("case", list(CASES))
def test_tags_and_cell_match_momwires_reader(case):
    # The source by absolute segment, so it lands whatever the tags became.
    text = deck(CASES[case], "EX 0 0 3 0 1. 0.")
    ours = parse_nec(text, network=True, name="x")
    theirs = _momwire_structure(text)
    assert tags(ours) == [w.tag for w in theirs.wires]
    assert (ours.symmetry_cell is None) is (theirs.symmetry is None)
