"""The per-engine default density is ONE table, and both front ends read it.

antennaknobs#1543. Before it there were two tables and they disagreed: the web
roster carried `default_n_per_wire` (razor-2p 40, nec5 20) and the CLI carried
nothing at all, so `--engine momwire:razor-2p` ran at the Builder framework
default while the app's razor tab was documented at 40 and — because a slot
preserved its N across an engine swap — actually served 15.

What is gated here:

- every web roster entry's served default comes from `antennaknobs.density`,
  so a new roster entry cannot ship with a number of its own;
- the CLI resolves each `--engine` spelling to a row in the same table,
  including the two spellings that are not roster names;
- the values themselves, as literals — a pin computed from the table would
  pass whatever the table said;
- the one invariant between the flat and per-degree halves: the degree the
  solver defaults to must agree with the flat entry, or an engine swap and a
  degree change would disagree about the stock mesh.
"""

from __future__ import annotations

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import (
    ENGINE_CLASSES,
    MOMWIRE_BASES,
    MOMWIRE_BASIS_VARIANTS,
    engine_density,
)
from antennaknobs.density import (
    DEFAULT_NSEGS,
    NSEGS_BY_DEGREE,
    default_nsegs,
    nsegs_by_degree,
)
from antennaknobs.web.adapter import backend_roster, model_option_specs


def _roster():
    return backend_roster(have_pynec=True, have_nec5=True, have_nec2=True)


# --------------------------------------------------------------------------
# The table itself
# --------------------------------------------------------------------------


def test_the_values():
    """The decided numbers, written out (#1543, 2026-09-16).

    razor-2p and nec5 share 40 so an A/B between momwire's formulation twin
    and the licensed binary is not also an A/B on the mesh; nec5 moved from
    20 to get there. bspline is per degree and its flat entry is the degree-2
    value.
    """
    assert dict(DEFAULT_NSEGS) == {
        "sinusoidal": 30,
        "sinusoidal-galerkin": 30,
        "bspline": 15,
        "pulse": 30,
        "hmatrix": 30,
        "arrayblock": 21,
        "razor-2p": 40,
        "pynec": 21,
        "nec5": 40,
        "nec2": 21,
    }
    assert {k: dict(v) for k, v in NSEGS_BY_DEGREE.items()} == {
        "bspline": {1: 20, 2: 15, 3: 12},
    }


def test_the_solvers_default_degree_agrees_with_the_flat_entry():
    """The invariant that keeps a swap and a degree change consistent.

    `defaultOptsFor` sets a fresh slot's degree to the SERVED spec default and
    its N to the flat entry; a later degree change reads the per-degree row.
    If the two disagreed at that degree, touching the degree tab and putting
    it back would leave a different mesh than the swap produced.
    """
    d = int(model_option_specs()["degree"]["default"])
    for name, by_degree in NSEGS_BY_DEGREE.items():
        assert by_degree[d] == DEFAULT_NSEGS[name], name


def test_an_engine_with_no_entry_has_no_opinion():
    """None, never 0 and never the framework default: the caller decides what
    "no opinion" means, and the CLI and the roster decide it differently."""
    assert default_nsegs("not-an-engine") is None
    assert nsegs_by_degree("not-an-engine") is None


def test_a_degree_the_engine_has_no_row_for_falls_back_to_the_flat_entry():
    """An engine that merely ACCEPTS a degree keeps one density across it —
    hmatrix and arrayblock are the live cases."""
    assert default_nsegs("bspline", degree=1) == 20
    assert default_nsegs("bspline", degree=9) == 15
    assert default_nsegs("hmatrix", degree=1) == 30
    assert default_nsegs("arrayblock", degree=3) == 21


def test_the_per_degree_map_is_handed_out_fresh():
    """It crosses the wire and reaches a CLI resolver; a shared mapping would
    let one caller edit the table for every other."""
    first = nsegs_by_degree("bspline")
    first[2] = "mutated"
    assert nsegs_by_degree("bspline") == {1: 20, 2: 15, 3: 12}


# --------------------------------------------------------------------------
# The web roster reads it
# --------------------------------------------------------------------------


@pytest.mark.parametrize("entry", _roster(), ids=lambda e: e["name"])
def test_every_roster_entry_is_reachable_through_the_table(entry):
    """Per-entry so a failure names the backend. A roster entry with no row
    raises at roster-build time rather than serving `undefined` to the knob."""
    assert entry["default_n_per_wire"] == default_nsegs(entry["name"])
    assert entry["default_n_per_wire_by_degree"] == (
        None
        if nsegs_by_degree(entry["name"]) is None
        else {str(d): n for d, n in nsegs_by_degree(entry["name"]).items()}
    )


def test_the_roster_carries_no_density_literal_of_its_own():
    """The point of the unit: `_BackendSpec` has no `default_n_per_wire`
    FIELD to set, so a new entry cannot carry a private number."""
    from antennaknobs.web.adapter import _BackendSpec

    assert "default_n_per_wire" not in _BackendSpec.__dataclass_fields__
    assert "default_n_per_wire_by_degree" not in _BackendSpec.__dataclass_fields__


# --------------------------------------------------------------------------
# The CLI reads it
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec, expected",
    [
        # The two first-order engines, at the one number.
        ("momwire:razor-2p", 40),
        ("momwire:razor-nec5", 40),  # deprecated spelling, same engine
        ("nec5", 40),
        # bspline per degree, through both spellings of the degree.
        ("momwire:bspline", 15),
        ("momwire:bspline-d1", 20),
        # The rest.
        ("momwire:sinusoidal", 30),
        ("momwire:sinusoidal-galerkin", 30),
        ("momwire:hmatrix", 30),
        ("momwire:arrayblock", 21),
        ("pynec", 21),
        ("nec2", 21),
    ],
)
def test_cli_engine_specs_resolve_to_the_table(spec, expected):
    assert engine_density(spec) == expected


def test_a_bare_momwire_keeps_the_framework_default():
    """`momwire` is the CLI's DEFAULT engine, so a density on it would re-mesh
    every command line that names no engine at all — the catalog runs and the
    status pages with them. Naming the basis is what asks for the basis's
    density."""
    assert engine_density("momwire") is None
    assert AntennaBuilder.FRAMEWORK_PARAMS["nominal_nsegs"] == 21


def test_every_cli_basis_name_has_a_row():
    """No CLI-orderable basis may be missing from the table: a missing row is
    silent — the engine just runs at 21 — which is the defect #1543 is."""
    for basis in list(MOMWIRE_BASES) + list(MOMWIRE_BASIS_VARIANTS):
        assert engine_density(f"momwire:{basis}") is not None, basis
    for name in ENGINE_CLASSES:
        if name != "momwire":
            assert engine_density(name) is not None, name
