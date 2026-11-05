"""An .ez's NEC deck carries every load in one run of LD cards (AK#2177).

NEC-4.2 and nec2c (black box) start a new run of loads at an LD card that
follows any other card (FR, GN, GD, EX, XQ, RP, NE, NH, TL, NT), and the new
run throws away every load read before it; PT, PQ and CM do not break a run.
The import used to write lumped loads, then lines, then wire conductivity
(LD 5), so a deck it exported and a user ran in real NEC lost its lumped
loads. Every LD card now comes in one run, directly after GE.
"""

from __future__ import annotations

from antennaknobs.ez_import import read_ez
from test_ez_import_1958 import PAIR, ez_file

_NO_BREAK = ("LD", "PT", "PQ", "CM", "CE")


def surviving_loads(nec_text: str) -> int:
    """The LD cards NEC keeps under the run rule above: the last run's."""
    kept = 0
    in_run = False
    for line in nec_text.splitlines():
        card = line.split()[0] if line.split() else ""
        if card == "LD":
            if not in_run:
                kept = 0
                in_run = True
            kept += 1
        elif card in ("GE",) or card not in _NO_BREAK:
            in_run = False
    return kept


def _deck():
    raw = ez_file(
        PAIR,
        loads=({"wire": 1, "pct": 25.0, "z": (5.0, 10.0)},),
        lines=((1, 50.0, 2, 50.0, 75.0, 6.0, 0.66),),
        wrho=1.72e-8,
    )
    return read_ez(raw)


def test_loads_lines_and_wire_loss_write_one_run_after_ge():
    text = _deck().nec_text
    cards = [
        l.split()[0]
        for l in text.splitlines()
        if l and l.split()[0] not in ("CM", "CE")
    ]
    ld = [i for i, c in enumerate(cards) if c == "LD"]
    assert ld, text
    assert cards[ld[0] - 1] == "GE"
    assert all(c == "LD" for c in cards[ld[0] : ld[-1] + 1]), text
    assert "TL" in cards and cards.index("TL") > ld[-1]
    # NEC keeps every one of them.
    assert surviving_loads(text) == len(ld)


def test_the_rule_this_checks_drops_a_split_run():
    """The checker itself: a TL between two LD runs keeps only the second."""
    split = "GE 0\nLD 4 1 5 5 5 10 0\nTL 1 11 2 11 75 6 0 0\nLD 5 0 0 0 5.8e7\nEN\n"
    assert surviving_loads(split) == 1
    assert surviving_loads("GE 0\nLD 4 1 5 5 5 10 0\nLD 5 0 0 0 5.8e7\nEN\n") == 2
