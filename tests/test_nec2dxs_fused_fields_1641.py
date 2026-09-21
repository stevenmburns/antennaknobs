"""NEC2Engine reads a 4nec2 ``nec2dxs`` printout, whose negative values fuse
with the field before them (AK#1641).

nec2dxs prints ANTENNA INPUT PARAMETERS in fixed-width ``E12.5`` fields, and a
negative value's minus sign takes the one separating space:
``7.18272E+01-8.10563E+00`` is a resistance and a reactance, not one token. The
row was read by splitting on whitespace and counting 11 tokens, which nec2c's
spaced columns always satisfied and which read none of the 861 input-parameter
blocks in the 1,010 real 4nec2 printouts under ``scratch/4nec2-capture/``. With
the 80-column deck fix (#1628) the binary accepts our deck, so this is where
AC6LA's NEC-2 slot failed next.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

from antennaknobs.engines.nec2 import _AIP_HEADER, NEC2Engine, NEC2Error

# Verbatim from scratch/4nec2-capture/0001_20260818-095814/post/out__3vertical.out:
# a negative voltage fused onto the segment number (row 2), two fused pairs in
# one row, and three sources.
THREE_SOURCES = """\
                                          - - - ANTENNA INPUT PARAMETERS - - -

   TAG   SEG.    VOLTAGE (VOLTS)         CURRENT (AMPS)         IMPEDANCE (OHMS)        ADMITTANCE (MHOS)      POWER
   NO.   NO.    REAL        IMAG.       REAL        IMAG.       REAL        IMAG.       REAL        IMAG.     (WATTS)
  9901    76 0.00000E+00 1.00000E+00-1.65197E+02 1.19221E+02 2.87254E-03-3.98029E-03 1.19221E+02 1.65197E+02 5.96106E+01
  9902    77-2.00000E+00 0.00000E+00-1.07494E+02-1.73139E+02 5.17646E-03-8.33760E-03 5.37471E+01 8.65693E+01 1.07494E+02
  9903    78 0.00000E+00-1.00000E+00 5.29363E+01-2.26454E+01 6.83106E-03-1.59684E-02 2.26454E+01 5.29363E+01 1.13227E+01

"""

# The row for our dipoles.invvee deck (which nec2c solves to 48.532 - j8.1039):
# TAG, SEG and the impedance are what the Windows box's nec2dxs11k.exe printed;
# the other fields are computed from that impedance at 1 V and written in the
# same E12.5 layout, which is what fuses the reactance to the resistance.
INVVEE_ROW = (
    "     3    41 1.00000E+00 0.00000E+00 2.00459E-02 3.34721E-03"
    " 4.85323E+01-8.10377E+00 2.00459E-02 3.34721E-03 1.00230E-02"
)


def test_fused_fields_are_read_as_the_numbers_they_are():
    (rows,) = NEC2Engine._parse_input_parameters(THREE_SOURCES)
    assert [(t, s) for t, s, _z in rows] == [(9901, 76), (9902, 77), (9903, 78)]
    assert [z for _t, _s, z in rows] == [
        pytest.approx(2.87254e-03 - 3.98029e-03j),
        pytest.approx(5.17646e-03 - 8.33760e-03j),
        pytest.approx(6.83106e-03 - 1.59684e-02j),
    ]


def test_the_feed_voltages_come_from_the_same_rows():
    assert NEC2Engine._parse_feed_voltages(THREE_SOURCES) == [
        pytest.approx(1j),
        pytest.approx(-2.0),
        pytest.approx(-1j),
    ]


def test_the_row_the_windows_binary_printed_for_our_deck():
    text = THREE_SOURCES.split("  9901")[0] + INVVEE_ROW + "\n\n"
    (((tag, seg, z),),) = NEC2Engine._parse_input_parameters(text)
    assert (tag, seg) == (3, 41)
    assert z == pytest.approx(48.5323 - 8.10377j)


def test_the_headers_are_not_rows():
    """The two header lines each split to exactly 11 tokens, so the old count
    test admitted them and rejected the data."""
    header_only = THREE_SOURCES.split("  9901")[0]
    with pytest.raises(NEC2Error, match="unparseable"):
        NEC2Engine._parse_input_parameters(header_only)


CAPTURES = sorted(
    glob.glob(
        str(Path(__file__).parents[1] / "scratch" / "4nec2-capture" / "**" / "*.out"),
        recursive=True,
    )
)


@pytest.mark.skipif(not CAPTURES, reason="the 4nec2 captures are not in this tree")
def test_every_real_4nec2_printout_reads_and_every_row_is_v_over_i():
    """Every input-parameter block in the tracked 4nec2 printouts parses, and
    every row it yields satisfies Z = V/I to the printout's six figures, which
    is what says the numbers landed in the right columns."""
    blocks = rows = 0
    for path in CAPTURES:
        text = Path(path).read_text(errors="replace")
        if _AIP_HEADER not in text:
            continue
        NEC2Engine._parse_input_parameters(text)
        blocks += 1
        for chunk in text.split(_AIP_HEADER)[1:]:
            for _tag, _seg, n in NEC2Engine._aip_rows(chunk):
                v, i, z = complex(n[0], n[1]), complex(n[2], n[3]), complex(n[4], n[5])
                if abs(i) > 0:
                    assert abs(z - v / i) <= 1e-5 * abs(z), (path, n)
                rows += 1
    assert blocks == 861 and rows == 3504
