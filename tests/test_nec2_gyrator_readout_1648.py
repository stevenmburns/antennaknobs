"""NEC2Engine reports the antenna's impedance on a design with a current
source, not the reciprocal it reads behind its own gyrator (AK#1648).

NEC-2 has no current-source card, so `export_nec` (AK#1597) writes each
`DrivenCurrent` as the gyrator idiom: an `EX 0` of V = j*I on a phantom
segment, and `NT phantom real 0. 0. 0. 1. 0. 0.` to the real segment. The
printout's ANTENNA INPUT PARAMETERS rows are then the PHANTOM's, and behind a
gyrator of Y12 = Y21 = jB that is 1/(B^2 Z) of the antenna: AC6LA's
`Cardioidmodnec2.nec` read 0.0215 + j0.0113 on the NEC-2 lane (QRZ post #120).

No heuristic is involved, unlike the import side (AK#1595, AK#1644): the engine
reads the gyrators out of the deck it ran, and a row on a phantom port is
mapped back exactly. Z = 1/(B^2 Z_row), and the drive value is the current,
I = -jB V.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from antennaknobs.engines import nec2 as m
from antennaknobs.engines.nec2 import NEC2Engine
from antennaknobs.file_designs import builder_from_file

CARDIOID = (
    Path(__file__).parent / "fixtures" / "eznec_gyrator_1595" / "Cardioidmodnec2.nec"
)


def _engine(exe=sys.executable):
    cls = builder_from_file(str(CARDIOID))
    # Construction never runs the binary; any executable stands in for it.
    return NEC2Engine(cls(), ground=cls.file_ground, nec2_exe=exe)


def _aip_row(tag, seg, v, i):
    z, y = v / i, i / v
    f = lambda x: f"{x:12.5E}"  # noqa: E731 - nec2dxs's own E12.5 layout
    return (
        f"{tag:6d}{seg:6d}"
        + "".join(
            f(x)
            for x in (v.real, v.imag, i.real, i.imag, z.real, z.imag, y.real, y.imag)
        )
        + f(0.5 * (v * i.conjugate()).real)
    )


def test_the_engine_finds_the_gyrators_it_wrote():
    eng = _engine()
    phantoms = m._gyrator_phantoms(eng.deck(eng.builder.freq))
    # Two current sources on one phantom wire, after the 12 real segments.
    assert phantoms == {(3, 13): 1.0, (3, 14): 1.0}


def test_a_design_without_current_sources_has_no_phantoms():
    from antennaknobs.designs.dipoles.invvee import Builder

    eng = NEC2Engine(Builder(), nec2_exe=sys.executable)
    assert m._gyrator_phantoms(eng.deck(eng.builder.freq)) == {}


def test_a_phantom_row_reads_as_the_antenna_behind_it(monkeypatch):
    """A printout whose rows are the phantoms' (V = j*I on each, as the writer
    drives them) comes back as the antenna's impedance and forced current."""
    eng = _engine()
    antenna = (36.5 - 19.2j, 67.7 + 20.0j)
    forced = (1.414214 + 0j, -1.414214j)
    rows = []
    for (tag, seg), z_ant, i_ant in zip(
        ((3, 13), (3, 14)), antenna, forced, strict=True
    ):
        v = 1j * i_ant  # the phantom's EMF, as `_gyrator_cards` writes it
        rows.append(_aip_row(tag, seg, v, v * z_ant))  # I_phantom = V / (1/Z_ant)
    printout = (
        "                                          - - - ANTENNA INPUT PARAMETERS - - -\n\n"
        "   TAG   SEG.    VOLTAGE (VOLTS)         CURRENT (AMPS)         IMPEDANCE (OHMS)\n"
        "   NO.   NO.    REAL        IMAG.       REAL        IMAG.       REAL        IMAG.\n"
        + "\n".join(rows)
        + "\n\n"
    )
    monkeypatch.setattr(eng, "_run", lambda deck: printout)
    assert eng.impedance() == [pytest.approx(z, rel=1e-4) for z in antenna]
    deck = eng.deck(eng.builder.freq)
    drives = eng._drives(printout, deck)
    assert [v for v, _ in drives] == [pytest.approx(i, rel=1e-5) for i in forced]
    # A forced current is in amps (AK#1657).
    assert [u for _, u in drives] == ["A"] * len(forced)


@pytest.mark.skipif(shutil.which("nec2c") is None, reason="nec2c not on PATH")
def test_a_real_nec2_agrees_with_pynec_on_the_cardioid():
    """nec2c and nec2++ are one formulation: a few tenths of a percent."""
    pynec = pytest.importorskip("PyNEC")  # noqa: F841 - presence check
    from antennaknobs.engines.pynec import PyNECEngine

    eng = _engine(shutil.which("nec2c"))
    cls = builder_from_file(str(CARDIOID))
    ref = PyNECEngine(cls(), ground=cls.file_ground).impedance()
    zs = eng.impedance()
    assert zs == [pytest.approx(complex(z), rel=1e-2) for z in ref]
    assert abs(zs[0]) > 10.0  # it read 0.0215 + j0.0113
