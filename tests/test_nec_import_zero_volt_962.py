"""momwire#962, antennaknobs half: a zero-volt EX is driven at 1 V, as NEC drives it.

Four wild-corpus decks returned z = [inf, 0] from momwire with no exception:
both Moxon copies, necpp patch_999 and patch_999_2. All four drive their EX at
zero volts (`EX 0 1 18 1 0`, `EX 0 143 1 0 0 0 ...`), and they reach momwire
through THIS importer, which took `complex(F1, F2)` literally, so no port was
driven. NEC does not read it that way. Measured 2026-09-14 on a dipole:
nec2c 1.3.1 and SimNEC's ae6ty build both print V = 1.0 and the 1 V impedance
for `EX 0 1 6 0 0. 0.` and for the five-field `EX 0 1 6 1 0`. momwire's own deck
readers got the same default in momwire#1072.
"""

from __future__ import annotations

import pytest

from antennaknobs.nec_import import parse_nec

DIPOLE = (
    "CM zero-volt probe\nCE\n"
    "GW 1 11 0. 0. -2.5 0. 0. 2.5 0.001\n"
    "GE 0\n"
    "{ex}\n"
    "FR 0 1 0 0 30. 0.\nXQ 0\nEN\n"
)


@pytest.mark.parametrize(
    "ex",
    ["EX 0 1 6 0 0. 0.", "EX 0 1 6 1 0", "EX 0 1 6 0"],
    ids=["explicit-zero", "moxon-five-fields", "voltage-absent"],
)
def test_a_zero_volt_source_imports_at_one_volt(ex):
    (feed,) = parse_nec(DIPOLE.format(ex=ex)).feeds
    assert feed.voltage == 1 + 0j


def test_a_written_voltage_is_kept_as_written():
    (feed,) = parse_nec(DIPOLE.format(ex="EX 0 1 6 0 2. -1.")).feeds
    assert feed.voltage == 2 - 1j
