"""A second ground medium (the 11-05 EZNEC sitting).

EZNEC keeps a second medium beyond a boundary: a straight line at X =
coord, or a circle of radius coord (the header's byte 4, 'X' or 'R'). Its
NEC-2 export writes it as NEC-2's GD: 1 linear or 2 radial, eps_r, sigma,
the coordinate, and the height with its sign flipped. In NEC-2 it changes
only the far field, and EZNEC's NEC-5 engine deletes it. The import used to
refuse it.
"""

from __future__ import annotations

import pytest

from antennaknobs.ez_import import EzNotRepresentable, read_ez
from test_ez_import_1958 import DIPOLE, ez_file


def _two(boundary="X", height=-50.0):
    return ez_file(
        DIPOLE,
        ground="R",
        media=[(0.002, 13.0), (5.0, 81.0, 30.0, height)],
        boundary=boundary,
    )


@pytest.mark.parametrize(("boundary", "code"), [("X", "1"), ("R", "2")])
def test_the_second_medium_is_written_as_eznecs_gd(boundary, code):
    imp = read_ez(_two(boundary))
    gd = [l.split() for l in imp.nec_text.splitlines() if l.startswith("GD")]
    assert gd == [["GD", code, "0", "0", "0", "81.0", "5.0", "30.0", "50.0"]]
    assert any("second ground medium" in n and "far field" in n for n in imp.notes)


def test_it_does_not_move_the_impedance():
    """As EZNEC: medium 2 one metre or fifty down solves to the same Z."""
    from antennaknobs.engines import MomwireEngine
    from antennaknobs.file_designs import builder_from_text

    zs = []
    for h in (-1.0, -50.0):
        cls = builder_from_text("two.ez", _two(height=h).decode("latin-1"))
        zs.append(complex(MomwireEngine(cls(), ground=cls.file_ground).impedance()[0]))
    assert zs[0] == zs[1]


def test_under_nec5_it_is_left_out_as_eznec_deletes_it():
    imp = read_ez(_two(), reading="nec5")
    assert not [l for l in imp.nec_text.splitlines() if l.startswith("GD")]
    assert any("EZNEC's NEC-5 engine deletes it" in n for n in imp.notes)


def test_a_second_medium_under_the_mininec_analysis_stays_refused():
    raw = ez_file(
        DIPOLE,
        ground="R",
        analysis="M",
        media=[(0.002, 13.0), (5.0, 81.0, 30.0, -1.0)],
        boundary="X",
    )
    with pytest.raises(EzNotRepresentable, match="MININEC"):
        read_ez(raw)
