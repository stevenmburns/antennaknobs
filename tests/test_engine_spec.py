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
        "sinusoidal-galerkin",
        "bspline",
        "hmatrix",
        "arrayblock",
    }


def test_make_factory_binds_sinusoidal_galerkin():
    """The Galerkin-tested sinusoidal basis is selectable by name
    (momwire#182). Same basis as `momwire:sinusoidal`, variational testing —
    the pair is the instrument, so both must be addressable."""
    from momwire import SinusoidalGalerkinSolver

    factory = make_engine_factory("momwire:sinusoidal-galerkin", _GROUND_UNSET)
    assert factory.func is MomwireEngine
    assert factory.keywords == {"solver": SinusoidalGalerkinSolver}


def test_parse_converged_variant_binds_feed_model():
    """`momwire:sinusoidal-galerkin-converged` is the point-gap feed model as
    a roster variant (issue #640): same solver class, `feed_model="point"`
    bound as solver kwargs. The kwargs are a fresh dict per parse so a caller
    mutating them cannot poison the roster."""
    from momwire import SinusoidalGalerkinSolver

    name, kw = parse_engine_spec("momwire:sinusoidal-galerkin-converged")
    assert name == "momwire"
    assert kw == {
        "solver": SinusoidalGalerkinSolver,
        "solver_kwargs": {"feed_model": "point"},
    }
    kw["solver_kwargs"]["feed_model"] = "mutated"
    assert parse_engine_spec("momwire:sinusoidal-galerkin-converged")[1][
        "solver_kwargs"
    ] == {"feed_model": "point"}


def test_make_factory_binds_converged_variant():
    from momwire import SinusoidalGalerkinSolver

    factory = make_engine_factory(
        "momwire:sinusoidal-galerkin-converged", _GROUND_UNSET
    )
    assert factory.func is MomwireEngine
    assert factory.keywords == {
        "solver": SinusoidalGalerkinSolver,
        "solver_kwargs": {"feed_model": "point"},
    }


def test_no_converged_variant_for_plain_sinusoidal():
    """The point gap has no collocation RHS (momwire#212), so the roster must
    not offer a converged flavour of the point-matched solver."""
    with pytest.raises(argparse.ArgumentTypeError):
        parse_engine_spec("momwire:sinusoidal-converged")


def test_parse_bspline_d1_variant_binds_degree():
    """`momwire:bspline-d1` (issue #821) is the degree axis, not the
    feed-model axis: same BSplineSolver class as plain `bspline`, with
    degree=1 bound as solver kwargs — an intra-family d1-vs-d2 check
    reachable from the CLI."""
    name, kw = parse_engine_spec("momwire:bspline-d1")
    assert name == "momwire"
    assert kw == {"solver": BSplineSolver, "solver_kwargs": {"degree": 1}}


def test_parse_bspline_unchanged_by_d1_variant():
    """Plain `bspline` still binds no solver_kwargs (degree=2 default)."""
    assert parse_engine_spec("momwire:bspline") == (
        "momwire",
        {"solver": BSplineSolver},
    )


def test_make_factory_binds_bspline_d1_variant():
    factory = make_engine_factory("momwire:bspline-d1", _GROUND_UNSET)
    assert factory.func is MomwireEngine
    assert factory.keywords == {
        "solver": BSplineSolver,
        "solver_kwargs": {"degree": 1},
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


def test_cli_compare_patterns_bspline_d1_intra_family():
    """d1-vs-d2 convergence check from the command line (issue #821): same
    family, different degree, both reachable as engine specs."""
    ant.cli(
        f"compare_patterns --builders dipoles.invvee:dipole --engines momwire:bspline momwire:bspline-d1{O}".split()
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
