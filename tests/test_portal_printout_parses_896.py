"""AK#896 — momwire's portal printout and our NEC-2 parser must agree.

The corpus census reads momwire's answers with
`antennaknobs.engines.nec2.NEC2Engine._parse_input_parameters`. That is a
contract between two packages and it is tested in neither: momwire tests that
its portal writes a column-exact NEC-2 printout, antennaknobs tests that the
parser reads a NEC-2 printout, and nothing tests that the one reads the other.

It is also a contract that has already been got wrong once in the obvious
direction. `nec5_corpus.py::_aip` — the scraper the census would naturally have
reused, since it reads the other engine's reports — requires a row of exactly
**12** tokens with the impedance at 7/8, which is NEC-5's layout. momwire writes
NEC-2's: **11** tokens, impedance at **6/7**. Measured while designing the
census, `_aip` reads **zero of 134** momwire printouts, silently: it returns an
empty list rather than raising, so a census built on it would have reported that
momwire solved nothing and called it a result.

So this pins the layout from both ends.
"""

from __future__ import annotations

import pytest

from antennaknobs.engines.nec2 import NEC2Engine

pytest.importorskip("momwire.portal")

# A centre-fed half-wave dipole in free space: the smallest deck that prints an
# ANTENNA INPUT PARAMETERS section, written in the dialect the corpus uses.
DECK = """CM test dipole
CE
GW 1 11 0 0 -2.5 0 0 2.5 0.001
GE 0
FR 0 1 0 0 30.0 0
EX 0 1 6 0 1.0 0.0
XQ
EN
"""


@pytest.fixture(scope="module")
def printout() -> str:
    from momwire.portal import run_deck

    out, _err = run_deck(DECK)
    return out


def test_the_portal_prints_an_input_parameters_section(printout):
    assert "ANTENNA INPUT PARAMETERS" in printout


def test_our_nec2_parser_reads_it(printout):
    freqs = NEC2Engine._parse_input_parameters(printout)
    assert len(freqs) == 1, "one FR point, one section"
    rows = freqs[0]
    assert len(rows) == 1, "one EX card, one source row"
    tag, seg, z = rows[0]
    assert (tag, seg) == (1, 6), "the driven segment, as the EX card names it"
    # A half-wave dipole near resonance: the value is not the point, the
    # PLAUSIBILITY is — a parser reading the wrong columns lands on the voltage
    # (1+0j) or the admittance (~1e-2), both of which this bracket excludes.
    assert 30.0 < z.real < 150.0, z
    assert abs(z.imag) < 200.0, z


def test_the_nec5_scraper_cannot_read_it(printout):
    """The trap, pinned so it cannot be walked into again.

    `_aip` returning [] rather than raising is what makes this dangerous: a
    census wired to it reports that momwire answered nothing, which reads as a
    finding rather than as a broken tool.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "nec5_corpus"))
    from nec5_corpus import _aip

    assert _aip(printout) == [], (
        "the NEC-5 scraper now reads NEC-2 printouts — if that is deliberate, "
        "the census can be simplified to one scraper; until then this failing "
        "means the two layouts have silently converged"
    )


def test_the_two_layouts_differ_as_recorded(printout):
    """11 tokens with Z at 6/7, not 12 with Z at 7/8 — the specific fact the
    census's parser choice rests on."""
    chunk = printout.split("ANTENNA INPUT PARAMETERS")[1]
    row = next(
        line
        for line in chunk.splitlines()
        if len(line.split()) >= 8 and line.split()[0].lstrip("-").isdigit()
    )
    toks = row.split()
    assert len(toks) == 11, f"NEC-2 layout is 11 tokens, got {len(toks)}: {toks}"
    z = complex(float(toks[6]), float(toks[7]))
    assert 30.0 < z.real < 150.0, f"impedance is not at tokens 6/7: {z}"
