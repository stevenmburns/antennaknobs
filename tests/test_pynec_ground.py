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


def test_momwire_folds_finite_fast_to_its_single_finite_model():
    assert _normalise_ground(("finite-fast", 10.0, 0.002)) == ("finite", 10.0, 0.002)


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
