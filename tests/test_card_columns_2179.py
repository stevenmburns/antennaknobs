"""Every NEC card the .ez and .maa imports write fits 80 columns (AK#2179).

Real NEC reads a fixed card width and drops the rest of the card silently,
which changes or zeroes a number: Fortran NEC-2 (AC6LA's nec2dxs11k.exe,
AK#1628) at 80 columns, NEC-4.2 at 120, nec2c at 132, NEC-5 at 200 to 255
(measured, black box). `nec_export` already kept its own cards inside
`CARD_COLUMNS`; the imports spelt their reals at full precision.
"""

from __future__ import annotations

import pytest

from antennaknobs.ez_import import read_ez
from antennaknobs.nec_export import CARD_COLUMNS, fit_card
from test_ez_import_1958 import ez_file


def test_a_card_that_fits_keeps_every_digit():
    card = "GW 1 21 0 -5.123456789012345 10 0 5 10 0.0021"
    assert fit_card(card) == card


def test_the_longest_field_goes_first_and_short_coordinates_stay_exact():
    card = "GW 4 11 -5.955815e-08 -2.183449e-07 3.047983 -20.1168 -3.306241e-07 3.047983 0.00102621"
    out = fit_card(card)
    assert len(out) <= CARD_COLUMNS
    f = out.split()
    assert f[:3] == ["GW", "4", "11"]
    # The coordinates that were already short are untouched.
    assert (f[5], f[6], f[8]) == ("3.047983", "-20.1168", "3.047983")
    for a, b in zip(card.split()[3:], f[3:], strict=True):
        assert float(b) == pytest.approx(float(a), rel=1e-4)


def test_integer_fields_and_comments_are_never_touched():
    tags = "NT 12345678 999 12345678 999 " + " ".join(["1.234567890123456"] * 6)
    out = fit_card(tags)
    assert out.split()[1:5] == ["12345678", "999", "12345678", "999"]
    long_comment = "CM " + "x" * 200
    assert fit_card(long_comment) == long_comment


def test_a_card_that_cannot_fit_is_refused_not_truncated():
    with pytest.raises(ValueError, match="cannot be written inside"):
        fit_card("GW 1 1 " + " ".join(["-1.234567e-123"] * 7))


def test_an_ez_with_full_precision_coordinates_writes_80_column_cards():
    wire = (1 / 3, -5.15 / 7, 10 / 3, 2 / 7, 5.15 / 3, 10 / 7, 0.002 / 3, 21)
    imp = read_ez(ez_file([wire]))
    cards = [
        line for line in imp.nec_text.splitlines() if not line.startswith(("CM", "CE"))
    ]
    assert max(len(c) for c in cards) <= CARD_COLUMNS
    gw = next(c for c in cards if c.startswith("GW"))
    # An .ez holds singles, so 1/3 is good to about 7 figures in the file
    # itself; spelt at full double precision it took 17, which is why such a
    # card ran past 80 columns.
    assert float(gw.split()[3]) == pytest.approx(1 / 3, rel=1e-6)
