import argparse
from types import MappingProxyType

import numpy as np
import pytest

import antennaknobs as ant
from antennaknobs import AntennaBuilder, Wire, WireSpec
from antennaknobs.cli import (
    MOMWIRE_BASES,
    parse_engine_spec,
    make_engine_factory,
    broadcast_pairs,
    deck_extended_kernel_flag,
    get_builder,
    _GROUND_UNSET,
)
from antennaknobs.engines import PyNECEngine, MomwireEngine
from momwire import SinusoidalSolver, BSplineSolver, RazorSolver

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
        ("razor", RazorSolver),
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
        "razor",
    }


def test_make_factory_binds_sinusoidal_galerkin():
    """The Galerkin-tested sinusoidal basis is selectable by name
    (momwire#182). Same basis as `momwire:sinusoidal`, variational testing —
    the pair is the instrument, so both must be addressable."""
    from momwire import SinusoidalGalerkinSolver

    factory = make_engine_factory("momwire:sinusoidal-galerkin", _GROUND_UNSET)
    assert factory.func is MomwireEngine
    assert factory.keywords == {"solver": SinusoidalGalerkinSolver}


def test_parse_variant_binds_kwargs_and_hands_back_a_fresh_dict():
    """A roster variant is a name bound to solver kwargs, and the kwargs are a
    fresh dict per parse so a caller mutating them cannot poison the roster.

    Written against `bspline-d1` because the variant it used to be written
    against is gone: `sinusoidal-galerkin-converged` bound
    `feed_model="point"`, which momwire#654 made the class default, so the
    name bound nothing the plain name did not already mean. The two claims
    here are about the VARIANT MECHANISM and outlive any one variant.
    """
    from momwire import BSplineSolver

    name, kw = parse_engine_spec("momwire:bspline-d1")
    assert name == "momwire"
    assert kw == {"solver": BSplineSolver, "solver_kwargs": {"degree": 1}}
    kw["solver_kwargs"]["degree"] = "mutated"
    assert parse_engine_spec("momwire:bspline-d1")[1]["solver_kwargs"] == {"degree": 1}


def test_make_factory_binds_a_variants_kwargs():
    from momwire import BSplineSolver

    factory = make_engine_factory("momwire:bspline-d1", _GROUND_UNSET)
    assert factory.func is MomwireEngine
    assert factory.keywords == {
        "solver": BSplineSolver,
        "solver_kwargs": {"degree": 1},
    }


def test_the_galerkin_name_is_the_point_gap_and_binds_nothing():
    """What replaced the `-converged` variant (momwire#654).

    The point gap is `SinusoidalGalerkinSolver`'s default now, so the plain
    name reaches it with no kwargs bound — one name, meaning the same thing
    through this CLI, both momwire portals and the library. Asserted on the
    CONSTRUCTED solver rather than on the roster table, because "binds
    nothing" is only the good news while the default is the thing worth
    getting.
    """
    from momwire import SinusoidalGalerkinSolver

    name, kw = parse_engine_spec("momwire:sinusoidal-galerkin")
    assert name == "momwire"
    assert kw == {"solver": SinusoidalGalerkinSolver}
    assert "solver_kwargs" not in kw
    assert (
        SinusoidalGalerkinSolver(
            wires=[np.array([(0.0, -0.25, 0.0), (0.0, 0.25, 0.0)])],
            nsegs=11,
            wavelength=1.0,
            wire_radius=5e-4,
        ).feed_model
        == "point"
    )


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


def test_make_factory_binds_razor():
    """Plain `momwire:razor` is the RazorSolver roster entry — the NEC-5
    formulation twin — with no solver_kwargs (the default converged
    Gauss-Legendre quadrature)."""
    factory = make_engine_factory("momwire:razor", _GROUND_UNSET)
    assert factory.func is MomwireEngine
    assert factory.keywords == {"solver": RazorSolver}


def test_parse_razor_nec5_variant_binds_quadrature_kwarg():
    """`momwire:razor-nec5` (momwire#316/#432) is the quadrature axis, not a
    different basis: same RazorSolver class as plain `razor`, with
    `nec5_quadrature=True` bound as solver kwargs — the interactive lane
    per the 2026-08-18 benchmark guidance, vs plain `razor`'s slower
    convergence/certification lane."""
    name, kw = parse_engine_spec("momwire:razor-nec5")
    assert name == "momwire"
    assert kw == {"solver": RazorSolver, "solver_kwargs": {"nec5_quadrature": True}}


def test_parse_razor_unchanged_by_nec5_variant():
    """Plain `razor` still binds no solver_kwargs (default GL quadrature)."""
    assert parse_engine_spec("momwire:razor") == (
        "momwire",
        {"solver": RazorSolver},
    )


def test_make_factory_binds_razor_nec5_variant():
    factory = make_engine_factory("momwire:razor-nec5", _GROUND_UNSET)
    assert factory.func is MomwireEngine
    assert factory.keywords == {
        "solver": RazorSolver,
        "solver_kwargs": {"nec5_quadrature": True},
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


# ---------------------------------------------------------------------------
# --extended-kernel (issue #849): NEC's EK card on the momwire CLI path, plus
# @file.nec decks honoring their own EK card. See engines/momwire.py's
# `_extended_kernel_refusal` for what refuses and why.
# ---------------------------------------------------------------------------

# Half-wave dipole with a/h ~ 0.24 (8 mm radius, ~33 mm segments) at 300 MHz —
# deliberately fat so the reduced and extended kernels visibly disagree, the
# same fixture shape as test_pynec_extended_kernel.py's PyNEC-side oracle.
_FAT_DIPOLE_FREQ_MHZ = 300.0
_FAT_DIPOLE_SPEC = WireSpec(radius=0.008)


def _fat_dipole_builder():
    class _B(AntennaBuilder):
        default_params = MappingProxyType({"freq": _FAT_DIPOLE_FREQ_MHZ})

        def build_wires(self):
            return [
                Wire(
                    (-0.25, 0.0, 0.0), (0.0, 0.0, 0.0), 7, None, None, _FAT_DIPOLE_SPEC
                ),
                Wire(
                    (0.0, 0.0, 0.0), (0.25, 0.0, 0.0), 8, 1 + 0j, None, _FAT_DIPOLE_SPEC
                ),
            ]

    return _B()


def test_make_factory_extended_kernel_binds_kwarg():
    factory = make_engine_factory("momwire", _GROUND_UNSET, extended_kernel=True)
    assert factory.func is MomwireEngine
    assert factory.keywords == {"extended_kernel": True}
    # Off by default: no kwarg at all, not extended_kernel=False (an EK-off
    # solve must keep passing exactly what it passed before this issue).
    assert make_engine_factory("momwire", _GROUND_UNSET) is MomwireEngine


@pytest.mark.parametrize(
    "flag,deck",
    [(True, False), (False, True), (True, True)],
)
def test_make_factory_extended_kernel_ors_flag_and_deck(flag, deck):
    """Either the explicit --extended-kernel flag or a deck's own EK card
    turns the kernel on — the combination rule is OR (issue #849)."""
    factory = make_engine_factory(
        "momwire", _GROUND_UNSET, extended_kernel=flag, deck_extended_kernel=deck
    )
    assert factory.keywords == {"extended_kernel": True}


def test_make_factory_extended_kernel_off_when_neither_set():
    factory = make_engine_factory(
        "momwire", _GROUND_UNSET, extended_kernel=False, deck_extended_kernel=False
    )
    assert factory is MomwireEngine


def test_make_factory_extended_kernel_moves_fat_wire_impedance_and_matches_direct():
    """Z must actually move with the flag, and match constructing
    MomwireEngine(extended_kernel=True) directly on the same design."""
    factory_off = make_engine_factory("momwire", _GROUND_UNSET)
    factory_on = make_engine_factory("momwire", _GROUND_UNSET, extended_kernel=True)
    z_off = factory_off(_fat_dipole_builder()).impedance()[0]
    z_on = factory_on(_fat_dipole_builder()).impedance()[0]
    assert abs(z_on - z_off) > 0.3  # the kernels must actually disagree here

    z_direct = MomwireEngine(_fat_dipole_builder(), extended_kernel=True).impedance()[0]
    assert z_on == z_direct


@needs_pynec
def test_make_factory_extended_kernel_rejected_for_non_momwire():
    """An explicit --extended-kernel is a momwire-only flag; a request to
    apply it on another engine is a clear user error, not a silent no-op
    (PyNEC's own EK support, issue #414, is a separate unexposed kwarg)."""
    with pytest.raises(argparse.ArgumentTypeError, match="momwire"):
        make_engine_factory("pynec", _GROUND_UNSET, extended_kernel=True)


@needs_pynec
def test_make_factory_deck_extended_kernel_silently_ignored_for_non_momwire():
    """A deck-only EK request (no explicit flag) on a non-momwire engine is
    left alone — unchanged from before issue #849, since PyNEC's EK support
    isn't wired to the deck by this issue."""
    factory = make_engine_factory("pynec", _GROUND_UNSET, deck_extended_kernel=True)
    assert factory is PyNECEngine


def test_make_factory_extended_kernel_serves_sinusoidal_galerkin():
    """momwire 0.27.0 un-refusal (issue #849): momwire#246 implemented NEC's
    extended kernel on the Galerkin fill (#287 lifted the last ground refusal,
    #299 fixed non-collinear decks), so the factory that used to raise
    NotImplementedError at construction now builds a working engine, and the
    kernel is honoured: the fat deck's EK answer differs measurably from the
    reduced one."""
    factory = make_engine_factory(
        "momwire:sinusoidal-galerkin", _GROUND_UNSET, extended_kernel=True
    )
    z_ek = factory(_fat_dipole_builder()).impedance()[0]
    reduced = make_engine_factory("momwire:sinusoidal-galerkin", _GROUND_UNSET)
    z_red = reduced(_fat_dipole_builder()).impedance()[0]
    assert abs(z_ek - z_red) / abs(z_red) >= 0.02, f"{z_ek} vs {z_red}"


def test_make_factory_extended_kernel_still_refuses_singular_enrichment():
    """The one EK refusal left (momwire#271): enrichment DOFs bypass the
    moment kernels the extended kernel corrects. Same NotImplementedError,
    same at-construction timing — this is the coverage the retired Galerkin
    refusal test used to provide for the engine's refusal path."""
    factory = make_engine_factory(
        "momwire:sinusoidal-galerkin", _GROUND_UNSET, extended_kernel=True
    )
    with pytest.raises(NotImplementedError, match="enrichment"):
        factory(_fat_dipole_builder(), solver_kwargs={"use_singular_enrichment": True})


def test_cli_extended_kernel_flag_runs():
    ant.cli(
        f"pattern --builder dipoles.invvee:dipole --engine momwire "
        f"--extended-kernel{O}".split()
    )


def test_cli_extended_kernel_galerkin_runs():
    """momwire 0.27.0 (issue #849): the exact invocation that used to be the
    CLI's documented clean-refusal case now just runs — the Galerkin fill
    serves the extended kernel on every ground, non-collinear invvee included
    (momwire#246/#287/#299). The cli() NotImplementedError→SystemExit handler
    this test used to cover keeps its coverage at the web layer
    (test_geometry_extended_kernel_enrichment_refusal_is_structured) and the
    factory layer (…still_refuses_singular_enrichment above); no basis name
    reachable from the CLI refuses EK anymore."""
    ant.cli(
        f"pattern --builder dipoles.invvee:dipole "
        f"--engine momwire:sinusoidal-galerkin --extended-kernel{O}".split()
    )


@needs_pynec
def test_cli_extended_kernel_flag_rejected_for_pynec():
    with pytest.raises(argparse.ArgumentTypeError):
        ant.cli(
            f"pattern --builder dipoles.invvee:dipole --engine pynec "
            f"--extended-kernel{O}".split()
        )


# --- @file.nec decks honoring their own EK card ---------------------------

_FAT_DIPOLE_DECK = """CE fat dipole
GW 1 15 -0.25 0 0 0.25 0 0 0.008
GE 0
{ek}FR 0 1 0 0 300.0
EX 0 1 8 0 1.0 0.0
EN
"""


def test_deck_extended_kernel_flag_absence_vs_explicit_off_vs_on(tmp_path):
    """NecDeck.extended_kernel semantics carried onto the synthesized @file
    builder: absence and `EK -1` both read as off, any other EK reads as on
    (issue #849's chosen, documented combination rule)."""
    on = tmp_path / "on.nec"
    on.write_text(_FAT_DIPOLE_DECK.format(ek="EK\n"))
    off = tmp_path / "off.nec"
    off.write_text(_FAT_DIPOLE_DECK.format(ek="EK -1\n"))
    absent = tmp_path / "absent.nec"
    absent.write_text(_FAT_DIPOLE_DECK.format(ek=""))

    assert deck_extended_kernel_flag(get_builder(f"@{on}")) is True
    assert deck_extended_kernel_flag(get_builder(f"@{off}")) is False
    assert deck_extended_kernel_flag(get_builder(f"@{absent}")) is False
    # An ordinary catalog design carries no such attribute at all.
    assert deck_extended_kernel_flag(get_builder("dipoles.invvee")) is False


def test_file_nec_deck_ek_card_honored_on_momwire_engine(tmp_path):
    """A `@file.nec` deck's own EK card turns the kernel on for the momwire
    engine with no --extended-kernel flag needed, and matches constructing
    MomwireEngine(extended_kernel=True) directly on the same geometry."""
    path = tmp_path / "fatdipole.nec"
    path.write_text(_FAT_DIPOLE_DECK.format(ek="EK\n"))

    builder_cls = get_builder(f"@{path}")
    factory = make_engine_factory(
        "momwire",
        _GROUND_UNSET,
        deck_extended_kernel=deck_extended_kernel_flag(builder_cls),
    )
    z_via_deck = factory(builder_cls()).impedance()[0]
    z_direct_on = MomwireEngine(builder_cls(), extended_kernel=True).impedance()[0]
    z_direct_off = MomwireEngine(builder_cls(), extended_kernel=False).impedance()[0]

    assert z_via_deck == z_direct_on
    assert abs(z_via_deck - z_direct_off) > 0.3


def test_cli_file_nec_deck_ek_card_runs_end_to_end(tmp_path):
    """Smoke-level: the CLI actually runs a momwire solve against an
    @file.nec deck carrying an EK card, with no --extended-kernel flag."""
    path = tmp_path / "fatdipole.nec"
    path.write_text(_FAT_DIPOLE_DECK.format(ek="EK\n"))
    ant.cli(f"pattern --builder @{path} --engine momwire{O}".split())
