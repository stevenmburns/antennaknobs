"""`sweep --set NAME=VALUE` (AC6LA, QRZ 1003328 #163): a catalog design's
knobs set from the command line, so its convergence can be studied at 14 MHz
without copying the design. Pure argument handling; nothing is solved."""

from __future__ import annotations

import pytest

from antennaknobs.cli import _with_params, get_builder


def test_set_overrides_knobs_with_the_knobs_own_types():
    make = _with_params(
        get_builder("dipoles.invvee:dipole"),
        ["freq=14", "design_freq=14", "nominal_nsegs=40"],
    )
    b = make()
    assert b.freq == 14.0 and isinstance(b.freq, float)
    assert b.nominal_nsegs == 40 and isinstance(b.nominal_nsegs, int)
    # Every instance, not just the first.
    assert make().freq == 14.0


@pytest.mark.parametrize(
    "item,match",
    [
        ("nope=1", "no knob 'nope'"),
        ("freq", "NAME=VALUE"),
        ("nominal_nsegs=4.5", "integer"),
    ],
)
def test_set_refuses_by_name(item, match):
    with pytest.raises(SystemExit, match=match):
        _with_params(get_builder("dipoles.invvee:dipole"), [item])
