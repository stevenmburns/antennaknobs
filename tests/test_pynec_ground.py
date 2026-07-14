"""PyNEC finite-ground handling.

("finite", eps_r, sigma) must select NEC's Sommerfeld-Norton ground (IPERF 2)
and ("finite-fast", eps_r, sigma) the reflection-coefficient approximation
(IPERF 0). The numerical test pins the two apart at a height where they
genuinely diverge, guarding against both specs silently mapping to the same
gn_card again (the pre-fix behaviour: "finite" emitted IPERF 0).
"""

import argparse

import pytest

pytest.importorskip("PyNEC")

from antennaknobs import resolve_variant_params  # noqa: E402
from antennaknobs.cli import parse_ground  # noqa: E402
from antennaknobs.designs.dipoles.invvee import Builder as InvVee  # noqa: E402
from antennaknobs.engines import PyNECEngine  # noqa: E402
from antennaknobs.engines.momwire import _normalise_ground  # noqa: E402


def _flat_dipole(height_m):
    params = dict(resolve_variant_params(InvVee, "dipole"))
    params["base"] = height_m
    return InvVee(params)


def test_parse_ground_finite_variants():
    assert parse_ground("finite") == ("finite", 10.0, 0.002)
    assert parse_ground("finite:13,0.005") == ("finite", 13.0, 0.005)
    assert parse_ground("finite-fast") == ("finite-fast", 10.0, 0.002)
    assert parse_ground("finite-fast:13,0.005") == ("finite-fast", 13.0, 0.005)
    with pytest.raises(argparse.ArgumentTypeError):
        parse_ground("finite-slow")


def test_momwire_preserves_the_finite_variant():
    """Since momwire 0.6.0 the two finite specs mean different physics
    (true Sommerfeld vs reflection-coefficient), so normalisation must
    keep the variant instead of folding to a single model."""
    assert _normalise_ground(("finite-fast", 10.0, 0.002)) == (
        "finite-fast",
        10.0,
        0.002,
    )
    assert _normalise_ground(("finite", 10.0, 0.002)) == ("finite", 10.0, 0.002)


def test_sommerfeld_and_reflection_coefficient_diverge_when_low():
    # At 0.05λ height the Sommerfeld and reflection-coefficient grounds
    # disagree on R by ~15 Ω (they agree within ~1 Ω above ~0.2λ, so a low
    # antenna is what tells them apart).
    lam = 299.792458 / 28.47
    height = 0.05 * lam
    z_somm = PyNECEngine(
        _flat_dipole(height), ground=("finite", 10.0, 0.002)
    ).impedance()[0]
    z_fast = PyNECEngine(
        _flat_dipole(height), ground=("finite-fast", 10.0, 0.002)
    ).impedance()[0]
    z_pec = PyNECEngine(_flat_dipole(height), ground="pec").impedance()[0]
    assert abs(z_somm - z_fast) > 5.0
    # and neither finite model is the PEC image in disguise
    assert abs(z_somm - z_pec) > 5.0
    assert abs(z_fast - z_pec) > 5.0


class _GroundedMonopole:
    """Minimal grounded quarter-wave monopole: bottom end at exactly z=0."""

    def __new__(cls):
        from types import MappingProxyType

        from antennaknobs import AntennaBuilder

        class Mono(AntennaBuilder):
            default_params = MappingProxyType({"freq": 28.57, "design_freq": 28.57})

            def build_wires(self):
                h = 0.25 * 299.792458 / 28.57
                return [
                    ((0.0, 0.0, 0.0), (0.0, 0.0, 0.3), 1, 1 + 0j),
                    ((0.0, 0.0, 0.3), (0.0, 0.0, h), 15, None),
                ]

        return Mono()


def test_ge_flag_connects_z0_wire_ends_to_pec_ground():
    """A wire ending at exactly z=0 over a ground plane must be CONNECTED to
    it (NEC GE flag 1: touching segments' currents interpolate onto their
    images). A bottom-fed grounded quarter-wave then reads the textbook
    monopole ~36 +j21; with the old unconditional GE flag 0 the same feed
    saw an insulated free end and thousands of ohms capacitive."""
    z = PyNECEngine(_GroundedMonopole(), ground="pec").impedance()[0]
    assert 25.0 < z.real < 55.0
    assert -20.0 < z.imag < 60.0


def test_ge_flag_stays_zero_when_nothing_touches_ground():
    """Elevated geometry keeps GE flag 0 (no behaviour change for the whole
    existing catalog), and free space never sets it even with a z=0 end."""
    eng = PyNECEngine(_flat_dipole(10.0), ground="pec")
    assert eng._ge_flag() == 0
    eng_free = PyNECEngine(_GroundedMonopole(), ground=None)
    assert eng_free._ge_flag() == 0
    eng_gnd = PyNECEngine(_GroundedMonopole(), ground="pec")
    assert eng_gnd._ge_flag() == 1
