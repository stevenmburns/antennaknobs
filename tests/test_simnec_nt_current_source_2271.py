"""A station chain on EZNEC's NEC-2 current-source idiom (AK#2271).

NEC-2 has no current-source EX card, so EZNEC spells one as an ``EX`` on a
one-segment wire parked far from the antenna, tied to the real feed segment
by a gyrator ``NT`` (Y11 = Y22 = 0, Y12 = j). ``nec_import`` reads that pair as
the current source it is, on the real segment (AK#1595). A SimNEC circuit
whose NEC block uses the idiom, behind a station chain, was refused: the
chain asked for a VOLTAGE source to replace, and the deck has a current one.

The chain now hangs on the segment the deck drives. The oracle is
independent of the import's chain code: the NEC block alone, written out as
a ``.nec`` and solved by the same engine on the same ground, then carried
through the line by the lossless line equation written here.

The fixture is synthetic (``fixtures/ssn_nt_current_source_2271``): a 7.1 MHz
dipole 12 m over Sommerfeld ground, the parked source wire 1800 m out, and a
lossless 15 m, 50 ohm, VF 0.66 line to a 50 ohm generator.
"""

from __future__ import annotations

import cmath
import math
from pathlib import Path

import pytest

from antennaknobs import network as N
from antennaknobs.cli import make_engine_factory
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import NEC_C_LIGHT_MHZ_M
from antennaknobs.plane import driven_at
from antennaknobs.schematic import lower, render_svg

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "ssn_nt_current_source_2271"
    / "dipole-nt-isrc-line.ssn"
)
TEXT = FIXTURE.read_text()

F_MHZ = 7.1
LINE_M, LINE_Z0, LINE_VF = 15.0, 50.0, 0.66
# The SimNEC chain tests' tolerance (test_simnec_station_2200.py).
REL = 1e-9
# A design read from NEC cards runs at NEC's speed of light, 299.8 m/us
# (`file_designs._make_builder`'s ``c_light_mhz_m``), the line included.
C_NEC = NEC_C_LIGHT_MHZ_M * 1e6

# The same circuit with the idiom removed: the EX directly on the feed
# segment, no parked wire, no NT.
_IDIOM = (
    "GW 2,1,1800.,1800.,1800.,1800.,1800.02,1800.,.002\n",
    "EX 0,2,1,0,0.,1.\nNT 2,1,1,6,0.,0.,0.,1.,0.,0.\n",
)
assert all(TEXT.count(s) == 1 for s in _IDIOM)
CONTROL = TEXT.replace(_IDIOM[0], "").replace(_IDIOM[1], "EX 0,1,6,0,1.,0.\n")


def _nec_block(text: str) -> str:
    start = text.index("NEC2  //")
    return text[text.index("\n", start) + 1 : text.index("NECEND")]


def _write(tmp_path, name: str, text: str) -> str:
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def _solve(cls, net=None) -> complex:
    b = cls()
    if net is not None:
        object.__setattr__(b, "build_network", lambda: net)
    (z,) = make_engine_factory("momwire", cls.file_ground)(b).impedance()
    return complex(z)


def _line(z_load: complex, c=C_NEC) -> complex:
    """Textbook lossless line: Z_in = Z0 (ZL + j Z0 t) / (Z0 + j ZL t),
    t = tan(beta l), beta = 2 pi f / (VF c)."""
    t = math.tan(2 * math.pi * F_MHZ * 1e6 * LINE_M / (LINE_VF * c))
    return LINE_Z0 * (z_load + 1j * LINE_Z0 * t) / (LINE_Z0 + 1j * z_load * t)


def _feed(net) -> str:
    (tl,) = [b for b in net.branches if isinstance(b, N.TL)]
    return tl.b


def test_it_opens_with_the_chain_on_the_segment_the_deck_drives(tmp_path):
    """The generator is the only source; the line runs from its block to the
    real segment the gyrator drove, and no gyrator or parked port is left."""
    net = builder_from_file(str(FIXTURE))().build_network()
    assert net.sources == [N.Driven(port="rig", voltage=1 + 0j)]
    feed = _feed(net)
    assert isinstance(net.ports[feed], N.PortOnWire)
    assert not [b for b in net.branches if isinstance(b, N.Admittance)]
    svg = render_svg(lower(net, title="AK#2271"))
    assert svg.lstrip().startswith("<svg")
    assert "15.00 m" in svg and "antenna" in svg


def test_the_generator_reads_the_deck_alone_through_the_line(tmp_path):
    """Z at the generator equals the NEC block's own driving-point impedance,
    solved with no SimNEC wrapper, carried through the line by hand."""
    cls = builder_from_file(str(FIXTURE))
    deck = builder_from_file(_write(tmp_path, "block.nec", _nec_block(TEXT)))
    assert deck.file_ground == cls.file_ground
    z_deck = _solve(deck)
    z_rig = _solve(cls)
    assert z_rig == pytest.approx(_line(z_deck), rel=REL)
    # Not the literal parked port: through the gyrator that reads
    # 1/(B^2 Z_deck), a fraction of an ohm here.
    assert abs(z_rig - _line(1 / z_deck)) > 10.0
    # The feed plane is the deck alone.
    net = cls().build_network()
    assert _solve(cls, driven_at(net, _feed(net))) == pytest.approx(z_deck, rel=REL)


def test_the_control_with_the_ex_on_the_feed_is_unchanged(tmp_path):
    """No NT: the EX on the feed segment, read as it always was (``feed``),
    meets the same oracle, and reads the same antenna as the idiom: the
    parked wire is a circuit node, not geometry, so the two meshes agree."""
    ctl = builder_from_file(_write(tmp_path, "ctl.ssn", CONTROL))
    net = ctl().build_network()
    assert net.sources == [N.Driven(port="rig", voltage=1 + 0j)]
    assert _feed(net) == "feed"
    z_deck = _solve(builder_from_file(_write(tmp_path, "ctl.nec", _nec_block(CONTROL))))
    assert _solve(ctl) == pytest.approx(_line(z_deck), rel=REL)
    idiom = _solve(builder_from_file(_write(tmp_path, "b.nec", _nec_block(TEXT))))
    assert idiom == pytest.approx(z_deck, rel=REL)


def test_two_parked_sources_are_refused_naming_the_idiom(tmp_path):
    """Two gyrated current sources are two feeds; the chain drives one."""
    two = TEXT.replace(
        _IDIOM[0], _IDIOM[0] + "GW 3,1,-1800.,1800.,1800.,-1800.,1800.02,1800.,.002\n"
    ).replace(_IDIOM[1], _IDIOM[1] + "EX 0,3,1,0,0.,1.\nNT 3,1,1,4,0.,0.,0.,1.,0.,0.\n")
    cls = builder_from_file(_write(tmp_path, "two.ssn", two))
    with pytest.raises(ValueError, match=r"has 2 sources") as e:
        cls().build_network()
    assert "current-source idiom" in str(e.value)
    assert "directly on the feed segment" in str(e.value)


def test_the_line_oracle_is_the_textbook_one():
    """Sanity on the hand formula: a matched load reads Z0, and a quarter
    wave inverts."""
    assert _line(LINE_Z0) == pytest.approx(LINE_Z0, rel=1e-12)
    beta = 2 * math.pi * F_MHZ * 1e6 / (LINE_VF * C_NEC)
    assert cmath.isclose(
        LINE_Z0 * 1j * math.tan(beta * LINE_M), _line(0.0), rel_tol=1e-12
    )
