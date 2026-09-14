"""antennaknobs#1295: a card whose trailing field wraps onto the next physical line.

`arrl/RHOM.NEC` (and two more decks in the 2026-09-08 census) wrap EVERY card's
last field onto a line of its own. The GW radius is the one that matters:

    GW  1 10   0.00000   0.00000  10.00000  17.30000  10.00000  10.00000
      0.01000

The importer read eight fields, found no radius and reported a tapered wire
("zero wire radius announces a tapered wire"), which is a mis-diagnosis. nec2c
rejects the deck outright (GEOMETRY DATA CARD ERROR); NEC-2 proper read it
column-formatted. A physical line that starts with a number is not a card, so it
now continues the card before it.
"""

from __future__ import annotations

from antennaknobs.nec_import import parse_nec, resolve_sy

# arrl/RHOM.NEC as it ships, every card wrapped.
RHOM = """\
CM NEC Input File for Rhombic
CE
GW  1 10   0.00000   0.00000  10.00000  17.30000  10.00000  10.00000
  0.01000
GW  2 10   0.00000   0.00000  10.00000  17.30000 -10.00000  10.00000
  0.01000
GW  3 10  17.30000  10.00000  10.00000  34.60000   0.00000  10.00000
  0.01000
GW  4 10  17.30000 -10.00000  10.00000  34.60000   0.00000  10.00000
  0.01000
GE  1
GN  1  0    0    0  0.00E+00  0.00E+00  0.00E+00  0.00E+00  0.00E+00
 0.00E+00
FR  0  1    0    0  3.00E+01  0.00E+00  0.00E+00  0.00E+00  0.00E+00
 0.00E+00
EX  0  1    1    0  1.00E+00  0.00E+00  0.00E+00  0.00E+00  0.00E+00
 0.00E+00
EX  0  2    1    0 -1.00E+00  0.00E+00  0.00E+00  0.00E+00  0.00E+00
 0.00E+00
LD  0  3   10   10  2.90E+02  0.00E+00  0.00E+00  0.00E+00  0.00E+00
 0.00E+00
LD  0  4   10   10  2.90E+02  0.00E+00  0.00E+00  0.00E+00  0.00E+00
 0.00E+00
RP  0 31   73 1001  0.00E+00  0.00E+00  3.00E+00  5.00E+00  0.00E+00
 0.00E+00
EN
"""


def _joined(text: str) -> str:
    """The same deck with each continuation joined by hand: the reference."""
    out: list[str] = []
    for line in text.splitlines():
        if line.strip() and line.strip()[0] in "0123456789+-." and out:
            out[-1] = out[-1] + " " + line.strip()
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def test_the_wrapped_deck_reads_every_wire_radius():
    deck = parse_nec(RHOM, name="RHOM.NEC")
    assert len(deck.wires) == 4
    assert {w.radius for w in deck.wires} == {0.01}


def test_the_wrapped_deck_parses_exactly_as_its_joined_twin():
    """Joining is the whole change: the wrapped deck and its hand-joined twin
    must be the same model, feeds and wires included."""
    wrapped = parse_nec(RHOM, name="RHOM.NEC")
    joined = parse_nec(_joined(RHOM), name="RHOM.NEC")
    assert wrapped.wires == joined.wires
    assert wrapped.feeds == joined.feeds
    assert [f.voltage for f in wrapped.feeds] == [1 + 0j, -1 + 0j]


def test_the_symbol_pass_writes_no_orphan_continuation_lines():
    out = resolve_sy(RHOM, name="RHOM.NEC")
    assert not [ln for ln in out.splitlines() if ln.strip()[:1] in set("0123456789+-.")]


def test_a_deck_whose_next_line_is_a_card_is_untouched():
    plain = _joined(RHOM)
    assert parse_nec(plain, name="plain") == parse_nec(_joined(plain), name="plain")
