"""AntennaBuilder.auto_mesh — the design-density meshing contract.

The rulebook (issues #521/#522, deliberately per-wire with no
interactions): a ``None`` count means "mesh me at the design density"
— ``nominal_nsegs`` segments per quarter-wavelength at ``design_freq``
— and an integer count is taken verbatim (the legacy path; allowed,
not recommended). ``design_freq`` anchors the scale, never the
measurement ``freq``, so sweeping frequency can never remesh geometry.
"""

from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder

C = 299.792458


class _Design(AntennaBuilder):
    default_params = MappingProxyType({"freq": 21.0, "design_freq": 29.9792458})


class _NoDesignFreq(AntennaBuilder):
    default_params = MappingProxyType({"freq": 21.0})


def _wire(length, ns, ex=None):
    return ((0.0, 0.0, 0.0), (length, 0.0, 0.0), ns, ex)


def test_none_counts_mesh_at_quarter_wave_density():
    # design_freq chosen so lambda/4 = 2.5 m exactly.
    b = _Design()
    b.nominal_nsegs = 20  # -> segment length 0.125 m
    out = b.auto_mesh([_wire(2.5, None), _wire(1.25, None), _wire(0.05, None)])
    assert [t[2] for t in out] == [20, 10, 1]  # 0.05 m floors at 1


def test_integer_counts_taken_verbatim_and_extras_preserved():
    b = _Design()
    b.nominal_nsegs = 20
    tagged = ((0.0, 0.0, 0.0), (1.25, 0.0, 0.0), None, 1 + 0j, "feed")
    out = b.auto_mesh([_wire(2.5, 7), tagged])
    assert out[0][2] == 7  # legacy explicit count untouched
    assert out[1][2] == 10  # None resolved at the same density
    assert out[1][3] == 1 + 0j and out[1][4] == "feed"  # payload intact


def test_all_explicit_is_a_pure_passthrough_without_design_freq():
    b = _NoDesignFreq()
    b.nominal_nsegs = 20
    tups = [_wire(2.5, 7), _wire(1.0, 3)]
    assert b.auto_mesh(tups) == tups  # no design_freq needed, no change


def test_none_count_without_design_freq_raises():
    b = _NoDesignFreq()
    b.nominal_nsegs = 20
    with pytest.raises(ValueError, match="design_freq"):
        b.auto_mesh([_wire(2.5, None)])


def test_measurement_freq_does_not_affect_the_mesh():
    """Sweeping freq must never remesh the antenna — density is anchored
    to design_freq only."""
    b = _Design()
    b.nominal_nsegs = 20
    ref = [t[2] for t in b.auto_mesh([_wire(2.5, None), _wire(0.7, None)])]
    b.freq = 3.5
    assert [t[2] for t in b.auto_mesh([_wire(2.5, None), _wire(0.7, None)])] == ref


def test_density_is_the_same_across_designs():
    """N means one physical density everywhere: two designs at the same
    design_freq give the same segment length to same-length wires."""

    class Other(AntennaBuilder):
        default_params = MappingProxyType({"freq": 7.0, "design_freq": 29.9792458})

    a, o = _Design(), Other()
    a.nominal_nsegs = o.nominal_nsegs = 15
    wa = a.auto_mesh([_wire(1.9, None)])
    wo = o.auto_mesh([_wire(1.9, None)])
    assert wa[0][2] == wo[0][2]
