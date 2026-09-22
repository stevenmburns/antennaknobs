"""Each per-feed row carries its drive's unit, "V" or "A" (AK#1657).

The readout printed ``feed 0 ∠0°``: a bare index, then a bare phase. AC6LA
read that as a drive of 0 A at 0°, because a number followed by an angle is how
a phasor is written. The index stays 0-based (it is the index into
``result.feeds``); what changes is that the drive gets its own labelled column,
with a magnitude and a unit wherever the lane knows which it is.

Every lane knows, and the unit comes from the SAME branch as the value, so one
lane's volts can never be labelled as another's amps: a network ``Driven`` is
volts and a ``DrivenCurrent`` amps; NEC-5's ``EX 4`` is amps; NEC-2's gyrator
phantom rows are read back as the current they force, so amps, and every other
row volts. A feed the lane has no drive for is padded with 1 V and NO unit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import antennaknobs.web.examples as examples
from antennaknobs.file_designs import builder_from_file
from antennaknobs.web.adapter import _make_example, _network_drives, _pack_feeds

CARDIOID = (
    Path(__file__).parent / "fixtures" / "eznec_gyrator_1595" / "Cardioidmodnec5.nec"
)


def _req(f, **over):
    return {"measurement_freq_mhz": f, "design_freq_mhz": f, "ground": True, **over}


def test_a_current_source_design_reports_amps():
    """The Cardioid's two EX 4 sources: 1.414 A at 0 and at -90 degrees."""
    cls = builder_from_file(str(CARDIOID))
    out = _make_example("Cardioidmodnec5", cls).momwire_solve(
        _req(cls().freq, ground_model="pec")
    )
    assert [r["drive_unit"] for r in out["feeds"]] == ["A", "A"]
    assert [complex(r["v_re"], r["v_im"]) for r in out["feeds"]] == [
        pytest.approx(1.414214),
        pytest.approx(-1.414214j),
    ]


def test_a_voltage_source_design_reports_volts():
    from antennaknobs.designs.verticals.four_square import Builder

    out = examples.example_for("verticals.four_square").momwire_solve(
        _req(Builder().freq, ground_model="pec")
    )
    assert len(out["feeds"]) == 4
    assert {r["drive_unit"] for r in out["feeds"]} == {"V"}


def test_the_network_drives_name_their_units():
    class _Eng:
        pass

    eng = _Eng()
    eng.builder = builder_from_file(str(CARDIOID))()
    assert _network_drives(eng) == [(1.414214 + 0j, "A"), (-1.414214j, "A")]


def test_a_padded_feed_claims_no_unit():
    rows = _pack_feeds([50 + 0j, 60 + 1j], [(2 + 0j, "A")])
    assert [r["drive_unit"] for r in rows] == ["A", None]
    assert (rows[1]["v_re"], rows[1]["v_im"]) == (1.0, 0.0)
