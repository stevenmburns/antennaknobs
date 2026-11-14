"""The sector (block-circulant) route on the symmetric ELT whips, gated
against the dense solve.

`verticals.elt_whip:sym4` (C4v) and `:hex6` (C6v) exist for symmetry studies;
`test_elt_whip_sym4.py` / `test_elt_whip_hex6.py` hold their GEOMETRY to the
group. This file holds the SOLVE: with the `rotational_symmetry` checkbox on,
the route must actually run (the solver's sector map has the design's order:
4 or 6, not a weaker subgroup and not None) and must move no number against
the dense route on the same engine. That is an algebraic identity between
two routes through one matrix, so the bar is the house sector-route
tolerance (`test_rotational_symmetry_sector_route_1029.py`, 1e-9), not a
convergence one.

Per-PR cost: the plane is cut to `SMALL_RADIUS` at the design's own pitch.
That keeps the outline round and the group intact (the size ladder of
2026-11-12 used the same cut), at ~1.1k segments instead of ~4.2k. The full
designs run under `heavy_mesh` (excluded from CI; run manually).

Skips on the capability, never on a version: a momwire whose class does not
declare the "sector" strategy offers no checkbox to test.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.cli import resolve_class
from antennaknobs.web.adapter import (
    _BACKENDS_BY_NAME,
    _build_builder,
    _make_momwire_engine,
    _offers_rotational_symmetry,
)

RTOL = 1e-9
FREQS = np.array([400.0, 406.0, 412.0])
SMALL_RADIUS = 0.5  # m; the design's own plane is 1.2192 m
ORDER = {"sym4": 4, "hex6": 6}


def _offers(backend):
    return _offers_rotational_symmetry(_BACKENDS_BY_NAME[backend])


def _engine(variant, backend, *, rotational_symmetry, plane_radius=None):
    req = {
        "geometry": "verticals.elt_whip",
        "variant": variant,
        "solver": "momwire",
        "momwire_model": backend,
        "ground": False,
        "model_options": {"rotational_symmetry": rotational_symmetry},
    }
    if backend == "bspline":
        req["model_options"]["degree"] = 1
    if plane_radius is not None:
        req["plane_radius"] = plane_radius
    builder = _build_builder(resolve_class("verticals.elt_whip"), req)
    builder.freq = float(FREQS[1])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _make_momwire_engine(req, builder)


def _sweep(eng):
    """Z over FREQS, and the sector order of every solver the sweep built
    (None on the dense route), read off the solvers themselves: the elt_whip's
    posts are a network, so its Z goes through the multiport Y and no excited
    solve is cached for a test to inspect."""
    built = []
    construct = eng._construct_solver

    def recording(**kw):
        sim = construct(**kw)
        built.append(sim)
        return sim

    eng._construct_solver = recording
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        z = np.asarray(eng.impedance_sweep(FREQS)).ravel()
    orders = {
        None if s._rotational_map is None else s._rotational_map.n_sectors
        for s in built
    }
    return z, orders


def _gate(variant, backend, plane_radius):
    if not _offers(backend):
        pytest.skip(f"momwire's {backend} class does not declare the sector route")
    dense = _engine(
        variant, backend, rotational_symmetry=False, plane_radius=plane_radius
    )
    sector = _engine(
        variant, backend, rotational_symmetry=True, plane_radius=plane_radius
    )

    z_dense, dense_orders = _sweep(dense)
    z_sector, sector_orders = _sweep(sector)
    # The route ran, at the design's full order, in every solver the sweep
    # built: a green agreement from two dense solves would measure nothing.
    assert dense_orders == {None}
    assert sector_orders == {ORDER[variant]}

    assert z_dense.shape == z_sector.shape == FREQS.shape
    assert np.all(np.abs(z_dense) > 1.0)  # a real feed impedance, not a stub
    worst = float(np.max(np.abs(z_sector - z_dense) / np.abs(z_dense)))
    assert worst < RTOL, (z_dense, z_sector, worst)


@pytest.mark.parametrize("variant", ["sym4", "hex6"])
@pytest.mark.parametrize("backend", ["sinusoidal", "bspline"])
def test_sector_route_agrees_with_dense_on_the_cut_plane(variant, backend):
    _gate(variant, backend, SMALL_RADIUS)


@pytest.mark.heavy_mesh
@pytest.mark.parametrize("variant", ["sym4", "hex6"])
def test_sector_route_agrees_with_dense_on_the_full_design(variant):
    # ~4.2k segments; the dense sinusoidal fill is ~280 MB and seconds per
    # frequency, which is why this sits outside CI.
    _gate(variant, "sinusoidal", None)
