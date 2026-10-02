"""Every NEC deck the workbench writes is ASCII.

A dropped-in deck's design name is its file name, and the NEC-2 / NEC-4 writer
put it verbatim on the deck's ``CM`` title. The engines then wrote the deck with
the platform's default encoding, which on Windows is cp1252: a file named
``40m λ-2 dipole.nec`` raised UnicodeEncodeError before nec2c or NEC-4.2 ran.
The audit (2026-10-01) exported every catalog design in all three dialects
(232 decks, all ASCII), so the free text on comment cards was the only leak.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from antennaknobs.card_text import card_text
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec5_export import catalog_header
from antennaknobs.nec_export import export_nec

ROOT = Path(__file__).resolve().parents[1]
NON_ASCII = re.compile(r"[^\x00-\x7f]")


@pytest.mark.parametrize(
    ("text", "ascii_"),
    [
        ("Dan – 40 m", "Dan - 40 m"),
        ("note — here", "note - here"),
        ("2 µH, 3 μH", "2 uH, 3 uH"),
        ("45° slope", "45 deg slope"),
        ("50 Ω and 50 Ω", "50 ohm and 50 ohm"),
        ("λ/2 dipole, ½-wave", "lambda/2 dipole, 1/2-wave"),
        ("Café åntenna", "Cafe antenna"),
        ("中", "?"),
        ("plain ascii", "plain ascii"),
    ],
)
def test_card_text_folds_to_ascii(text, ascii_):
    assert card_text(text) == ascii_


@pytest.fixture
def awkward_deck(tmp_path):
    """A latin-1 deck, as old EZNEC/4nec2 decks are, with non-ASCII comments,
    an SY comment, and a file name no cp1252 codec can write."""
    deck = (
        "CM Dan's dipole – 40 m, 45° slope, 2 µH coil\r\n"
        "CE\r\n"
        "SY L=10.1 '½-wave leg\r\n"
        "GW 1,21,0,-L,10,0,L,10,0.001\r\n"
        "GE 0\r\nEX 0,1,11,0,1,0\r\nFR 0,1,0,0,7.1\r\nEN\r\n"
    )
    path = tmp_path / "40m λ-2 – µdipole.nec"
    path.write_bytes(deck.encode("latin-1", errors="replace"))
    return path


@pytest.mark.parametrize("dialect", ["nec2", "nec42"])
def test_a_file_design_exports_an_ascii_deck(awkward_deck, dialect):
    deck = export_nec(builder_from_file(str(awkward_deck))(), dialect=dialect)
    assert not NON_ASCII.search(deck), [
        line for line in deck.splitlines() if NON_ASCII.search(line)
    ]
    # The name survives, folded, so the title still says which design it is.
    assert "lambda-2 - udipole" in deck.splitlines()[0]
    deck.encode("cp1252")


def test_the_nec5_header_is_ascii():
    header = catalog_header(
        "user.40m λ-2 dipole", "default", "average", 7.1, note="µ — x"
    )
    assert not NON_ASCII.search(header), header
    assert "lambda-2" in header


def test_every_engine_deck_write_names_its_encoding():
    """The engines hand decks to Windows console programs: a write that leans
    on the platform default is the bug this file is about."""
    calls = 0
    for path in sorted((ROOT / "src/antennaknobs/engines").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "write_text"
            ):
                calls += 1
                assert any(k.arg == "encoding" for k in node.keywords), (
                    f"{path.name}:{node.lineno}"
                )
    # The deck and printout writes of the NEC-2, NEC-4.2 and NEC-5 engines.
    assert calls >= 7
