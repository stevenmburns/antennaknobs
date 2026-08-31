"""Nested-path support for opt.py's --params: dotted names like
'bands.0.halfdriver_factor' walk Builder attrs, tuples, and dicts.
Without this, the multi-band hexbeam_5band couldn't be tuned through
the CLI."""

from __future__ import annotations

import pytest

from antennaknobs.designs.multiband.hexbeam_5band import Builder
from antennaknobs.opt import _get_path, _set_path, _parse_path


def test_parse_path_keeps_strings_and_promotes_ints():
    assert _parse_path("freq") == ["freq"]
    assert _parse_path("bands.0.halfdriver_factor") == ["bands", 0, "halfdriver_factor"]
    assert _parse_path("a.-1.b") == ["a", -1, "b"]


def test_get_path_walks_dict_and_tuple_and_attr():
    b = Builder()
    assert _get_path(b, "n_bands") == 5
    assert _get_path(b, "bands.0.freq") == 14.300
    assert _get_path(b, "bands.4.halfdriver_factor") == pytest.approx(1.071)


def test_set_path_does_not_leak_into_class_defaults():
    """Two separate Builder instances must not see each other's mutations
    — the class-level `bands` tuple is a shared reference, so the set
    helper has to rebuild the tuple functionally and write it back to
    only this instance."""
    b1 = Builder()
    b2 = Builder()
    _set_path(b1, "bands.0.halfdriver_factor", 1.234)
    assert _get_path(b1, "bands.0.halfdriver_factor") == 1.234
    # b2 must still see the class default — no leak through the shared
    # default_params tuple.
    assert _get_path(b2, "bands.0.halfdriver_factor") == pytest.approx(1.071)
    # And the class default itself stays put.
    assert Builder.default_params["bands"][0]["halfdriver_factor"] == pytest.approx(
        1.071
    )


def test_set_path_updates_top_level_attr():
    b = Builder()
    _set_path(b, "n_bands", 3)
    assert b.n_bands == 3


def test_set_path_then_get_path_roundtrip():
    b = Builder()
    _set_path(b, "bands.2.t0_factor", 0.111)
    assert _get_path(b, "bands.2.t0_factor") == 0.111
    # Other band entries unchanged.
    assert _get_path(b, "bands.0.t0_factor") == pytest.approx(0.1243)


def test_set_path_works_through_optimize_signature():
    """The actual call site in opt.objective uses _set_path for each
    independent_variable_name on every objective evaluation. Verify a
    typical dotted name round-trips."""
    b = Builder()
    names = ["bands.0.halfdriver_factor", "bands.0.t0_factor"]
    values = [1.05, 0.15]
    for v, nm in zip(values, names, strict=True):
        _set_path(b, nm, v)
    assert _get_path(b, names[0]) == 1.05
    assert _get_path(b, names[1]) == 0.15
