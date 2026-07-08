import argparse

import pytest

import antennaknobs as ant
from antennaknobs.cli import (
    MOMWIRE_BASES,
    parse_engine_spec,
    make_engine_factory,
    broadcast_pairs,
    _GROUND_UNSET,
)
from antennaknobs.engines import PyNECEngine, MomwireEngine
from momwire import SinusoidalSolver, BSplineSolver

from conftest import needs_pynec


@needs_pynec
def test_parse_pynec_no_basis():
    assert parse_engine_spec("pynec") == ("pynec", {})


def test_parse_momwire_default():
    assert parse_engine_spec("momwire") == ("momwire", {})


@pytest.mark.parametrize(
    "basis,cls",
    [
        ("sinusoidal", SinusoidalSolver),
        ("bspline", BSplineSolver),
    ],
)
def test_parse_momwire_with_basis(basis, cls):
    name, kw = parse_engine_spec(f"momwire:{basis}")
    assert name == "momwire"
    assert kw == {"solver": cls}


def test_parse_unknown_engine_raises():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_engine_spec("bogus")


def test_parse_pynec_with_basis_raises():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_engine_spec("pynec:bspline")


def test_parse_momwire_unknown_basis_raises():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_engine_spec("momwire:not_a_basis")


@needs_pynec
def test_make_factory_returns_class_when_no_kwargs():
    assert make_engine_factory("pynec", _GROUND_UNSET) is PyNECEngine
    assert make_engine_factory("momwire", _GROUND_UNSET) is MomwireEngine


def test_make_factory_binds_solver():
    factory = make_engine_factory("momwire:sinusoidal", _GROUND_UNSET)
    assert factory.func is MomwireEngine
    assert factory.keywords == {"solver": SinusoidalSolver}


def test_make_factory_binds_ground_and_solver():
    factory = make_engine_factory("momwire:bspline", "pec")
    assert factory.func is MomwireEngine
    assert factory.keywords == {"solver": BSplineSolver, "ground": "pec"}


def test_momwire_bases_keys():
    assert set(MOMWIRE_BASES) == {
        "sinusoidal",
        "bspline",
        "hmatrix",
        "arrayblock",
    }


O = " --fn /dev/null"


@needs_pynec
def test_cli_compare_patterns_multi_engine():
    ant.cli(
        f"compare_patterns --builders dipoles.invvee:dipole --engines pynec momwire{O}".split()
    )


@needs_pynec
def test_cli_compare_patterns_single_engine_still_works():
    ant.cli(
        f"compare_patterns --builders dipoles.invvee:dipole dipoles.invvee --engines pynec{O}".split()
    )


def test_cli_compare_patterns_momwire_basis():
    ant.cli(
        f"compare_patterns --builders dipoles.invvee:dipole --engines momwire:bspline momwire:sinusoidal{O}".split()
    )


def test_broadcast_equal_length():
    assert broadcast_pairs(["a", "b", "c"], ["x", "y", "z"]) == [
        ("a", "x"),
        ("b", "y"),
        ("c", "z"),
    ]


def test_broadcast_single_engine():
    assert broadcast_pairs(["a", "b", "c"], ["x"]) == [
        ("a", "x"),
        ("b", "x"),
        ("c", "x"),
    ]


def test_broadcast_single_builder():
    assert broadcast_pairs(["a"], ["x", "y", "z"]) == [
        ("a", "x"),
        ("a", "y"),
        ("a", "z"),
    ]


def test_broadcast_mismatch_raises():
    with pytest.raises(argparse.ArgumentTypeError):
        broadcast_pairs(["a", "b"], ["x", "y", "z"])


@needs_pynec
def test_cli_compare_patterns_three_by_three_paired():
    ant.cli(
        f"compare_patterns --builders dipoles.invvee:dipole dipoles.invvee specialty.bowtie "
        f"--engines pynec momwire:bspline momwire:sinusoidal{O}".split()
    )


def test_cli_compare_patterns_three_builders_one_engine():
    ant.cli(
        f"compare_patterns --builders dipoles.invvee:dipole dipoles.invvee specialty.bowtie --engines momwire{O}".split()
    )


def test_cli_compare_patterns_mismatch_rejected():
    with pytest.raises(argparse.ArgumentTypeError):
        ant.cli(
            f"compare_patterns --builders dipoles.invvee:dipole dipoles.invvee --engines pynec momwire:bspline momwire:sinusoidal{O}".split()
        )


def test_cli_pattern_with_basis_spec():
    ant.cli(
        f"pattern --builder dipoles.invvee:dipole --engine momwire:sinusoidal{O}".split()
    )
