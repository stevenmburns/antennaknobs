"""GX/GR symmetry-cell resolution for LD cards (issue #946).

``GX``/``GR`` do not only replicate geometry — they declare the structure
symmetric, and NEC then builds the matrix on one *cell*: the structure as
it stood when the card fired. Anything entering the matrix can therefore
only be expressed cell-wide, and ``LOAD`` finishes by stamping the cell's
loading onto every copy (NEC-2 Fortran: ``NOP=N/NP`` then
``DO 3 I=1,NP ... ZARRAY(L1)=ZT``). So a load inside the cell lands on
every copy, and a load addressing a copy is overwritten by that pass and
has no effect at all.

Both rules were measured identically on nec2c and nec5cl; the gating
oracle is ``k9ay_orig.nec``, where nec2c answers 960.79 + 81.25j as
written and 490.79 + 81.25j if the load is applied to its named tag
alone — a 53 % error, the gap being exactly the deck's 470 Ω.

Symmetry survives a congruence of the whole structure and dies the moment
anything is added or transformed selectively, which is why the great
majority of real decks (any that add a feed wire or mast afterwards) are
untouched by any of this.
"""

import pathlib

import pytest

from antennaknobs.nec_import import parse_nec

EXAMPLES = pathlib.Path.home() / "antennas" / "xnec2c" / "examples"


def deck(geometry: str, extra: str = "LD 4 2 3 3 470. 0.") -> str:
    """Two 5-segment verticals, a driven tag 1, and one LD card."""
    return (
        "CM symmetry probe\nCE\n"
        "GW 1 5 0.5 0. 0. 0.5 0. 1. 0.001\n"
        f"{geometry}"
        "GE 0\n"
        "EX 0 1 3 0 1. 0.\n"
        f"{extra}\n"
        "FR 0 1 0 0 150.\n"
        "XQ\nEN\n"
    )


def loaded_tags(d):
    return sorted(d.wires[ld.wire].tag for ld in d.loads)


# --- the cell rule -------------------------------------------------------


def test_load_on_the_cell_reaches_every_copy():
    """GR 4-fold, cell = tag 1: a load on tag 1 loads all four legs — the
    same answer nec2c gives for four explicit per-tag LD cards."""
    d = parse_nec(deck("GR 1 4\n", extra="LD 4 1 3 3 470. 0."), network=True, name="gr")

    assert d.symmetry_cell == 5
    assert loaded_tags(d) == [1, 2, 3, 4]
    assert d.symmetry_dropped_loads == 0


@pytest.mark.parametrize("tag", [2, 3, 4])
def test_load_on_a_copy_is_discarded(tag):
    """Addressing a copy is not 'load that copy only' — NEC's replication
    pass overwrites it, so the card has no effect anywhere."""
    d = parse_nec(
        deck("GR 1 4\n", extra=f"LD 4 {tag} 3 3 470. 0."), network=True, name="gr"
    )

    assert d.loads == ()
    assert d.symmetry_dropped_loads == 1


def test_whole_structure_load_reaches_every_copy():
    """Tag 0 resolves through the cell, so the common real-world spelling
    behaves correctly."""
    d = parse_nec(deck("GR 1 4\n", extra="LD 4 0 3 3 470. 0."), network=True, name="gr")

    assert loaded_tags(d) == [1, 2, 3, 4]
    assert d.symmetry_dropped_loads == 0


def test_gx_cell_is_every_pre_card_wire():
    """The cell is the whole structure-so-far, not one wire: with two GW
    cards before GX, tag 2 is part of the CELL and replicates to tag 4.
    This is k9ay_orig's shape, and the 53 % error is exactly this."""
    d = parse_nec(
        deck("GW 2 5 1.5 0. 0. 1.5 0. 1. 0.001\nGX 2 100\n"), network=True, name="gx"
    )

    assert d.symmetry_cell == 10
    assert loaded_tags(d) == [2, 4]
    assert d.symmetry_dropped_loads == 0


# --- what preserves and what destroys the symmetry -----------------------


def test_a_later_gw_collapses_symmetry():
    """The common case, and the reason 30 of 34 corpus GX/GR decks never
    see the cell rule: a feed wire or mast added afterwards belongs to no
    copy, so NEC abandons symmetry and per-tag addressing resolves as
    written."""
    d = parse_nec(
        deck("GR 1 4\nGW 9 5 0. 0. 2. 0. 0. 3. 0.001\n"), network=True, name="gw"
    )

    assert d.symmetry_cell is None
    assert loaded_tags(d) == [2]  # tag 2 alone — no replication, no discard
    assert d.symmetry_dropped_loads == 0


@pytest.mark.parametrize(
    "card,keeps",
    [
        ("GM 0 0 0. 0. 0. 0. 0. 5. 0.\n", True),  # whole-structure translate
        ("GS 0 0 2.0\n", True),  # whole-structure scale
        ("GM 0 0 0. 0. 0. 0. 0. 5. 2.\n", False),  # restricted to tags >= 2
        ("GM 1 1 0. 0. 0. 0. 0. 5. 0.\n", False),  # replicating
        ("GS 2 4 2.0\n", False),  # xnec2c tag-ranged extension
    ],
)
def test_preserve_and_destroy_rules(card, keeps):
    d = parse_nec(deck(f"GR 1 4\n{card}"), network=True, name="x")
    assert (d.symmetry_cell is not None) is keeps


def test_a_later_replication_resets_the_cell():
    """GX after GR does not nest — the later card's cell is the whole
    structure as it then stood (measured: cell 20 / total 40)."""
    d = parse_nec(deck("GR 1 4\nGX 4 1\n"), network=True, name="x")

    assert d.symmetry_cell == 20
    assert sum(w.n_seg for w in d.wires) == 40


def test_no_replication_card_means_no_symmetry():
    d = parse_nec(deck("", extra="LD 4 1 3 3 470. 0."), network=True, name="plain")

    assert d.symmetry_cell is None
    assert loaded_tags(d) == [1]
    assert d.symmetry_dropped_loads == 0


# --- reporting -----------------------------------------------------------


def test_discarded_loads_are_reported_not_hidden():
    d = parse_nec(deck("GR 1 4\n", extra="LD 4 2 3 3 470. 0."), network=True, name="gr")
    note = d.skipped_note()

    assert note is not None
    assert "symmetry cell" in note
    assert "NEC discards" in note


def test_discarded_loads_are_not_an_inexpressible_network():
    """The discard is parity, not a limitation: routing it through
    ignored_detail would mark the deck partial-network and drop it from
    the benchmark's clean cohort, hiding future regressions on exactly
    these decks."""
    d = parse_nec(deck("GR 1 4\n", extra="LD 4 2 3 3 470. 0."), network=True, name="gr")

    assert [c for c, _ in d.ignored_detail if c in ("LD", "TL", "NT")] == []


# --- the live oracle -----------------------------------------------------


@pytest.mark.skipif(
    not (EXAMPLES / "k9ay_orig.nec").exists(), reason="xnec2c corpus not present"
)
def test_k9ay_orig_loads_the_driven_image():
    """nec2c answers 960.79 + 81.25j for this deck. The load is on tag 2,
    inside the GX cell, so it also lands on tag 4 — the driven wire —
    which is where the 470 Ω that separates 960.79 from 490.79 comes from.
    Before this fix PyNEC sat 0.0848 from nec2c here; after it, 0.0000.
    """
    d = parse_nec(
        (EXAMPLES / "k9ay_orig.nec").read_text(errors="replace"),
        name="k9ay_orig",
        network=True,
    )

    assert d.symmetry_cell == 13
    assert loaded_tags(d) == [2, 4]
    assert [d.wires[f.wire].tag for f in d.feeds] == [4], "driven wire is an image"
    assert {ld.r for ld in d.loads} == {470.0}


@pytest.mark.skipif(
    not (EXAMPLES / "1MHz_tower.nec").exists(), reason="xnec2c corpus not present"
)
def test_1mhz_tower_reroutes_without_changing_the_loaded_set():
    """A deck that writes one LD per leg: one lands in the cell and
    replicates to all four, the other three address images and are
    discarded. The net loaded set is what the author intended, so the
    deck's numbers do not move — a check that the rule fires without
    disturbing a deck it should not."""
    d = parse_nec(
        (EXAMPLES / "1MHz_tower.nec").read_text(errors="replace"),
        name="1MHz_tower",
        network=True,
    )

    assert d.symmetry_cell == 42
    assert d.symmetry_dropped_loads == 3
    assert len(d.loads) == 4
