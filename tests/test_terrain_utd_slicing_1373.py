"""Issue #1373 — the diffracted composer evaluated on slices of its grid.

`terrain_utd_power` is written over a separable (theta, phi) grid, because the
profile a ray has to clear is a property of the azimuth. The web layer's cuts
path holds the opposite thing: an unstructured direction set, made more
unstructured by #744's refinement, which replaces either polar circle's uniform
parameterisation with an explicit non-uniform angle list.

The bridge between them is this property — a call restricted to ONE azimuth
column returns exactly that column of the full grid — which lets the cuts path
group its directions by azimuth and evaluate each group with the azimuth it
belongs to. Nothing is interpolated and nothing is evaluated at an azimuth it
does not belong to; the only cost is one call per distinct azimuth.

It is not a property to assume. The composer chunks columns to bound memory,
and `sector_for` / `back_idx` / the front-back sector pairing are all computed
over the WHOLE phi array, so a one-column call takes a visibly different route
through the function than the column does inside a wide one. Hence a test that
measures rather than reasons: it spies on the composer's real arguments from a
real engine run, so nothing here can disagree with the engine for any reason
other than the one under test.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs import merge_params
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines import momwire as M
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.terrain import hillside_terrain, levee_terrain
from momwire import BSplineSolver

F, H0 = 21.2, 6.1
SOIL, WATER = (13.0, 0.005), (80.0, 1e-3)

CASES = {
    # Two media and two drops: front/back sector pairs that differ by azimuth,
    # which is what makes the per-column route non-trivial.
    "levee": levee_terrain(
        crest_width=3.0,
        slope_deg=20.0,
        drop_water=10.67,
        drop_land=7.6,
        water=WATER,
        land=SOIL,
        water_azimuth=0.0,
    ),
    # A slope steep enough to shadow the sky, so the diffraction terms carry
    # real weight rather than rounding.
    "hillside-45": hillside_terrain(
        flat_width=20.0, up_slope_deg=45.0, down_slope_deg=20.0
    ),
}


def _engine(terrain):
    p = merge_params(Builder.default_params, {"design_freq": F, "freq": F, "base": H0})
    return MomwireEngine(
        Builder(p),
        solver=BSplineSolver,
        solver_kwargs={"degree": 2},
        ground=("terrain", terrain),
    )


def _column(x, j, n_phi):
    """Argument `x` restricted to azimuth column j, chosen BY SHAPE.

    Deliberately not by parameter name: the point is that whatever the caller
    passes per-azimuth gets sliced, so a new per-azimuth argument is covered
    the day it is added rather than the day someone remembers to list it here.
    """
    if not isinstance(x, np.ndarray):
        return x
    if x.ndim >= 2 and x.shape[1] == n_phi:
        return x[:, j : j + 1]
    if x.ndim == 1 and x.shape[0] == n_phi:
        return x[j : j + 1]
    return x


@pytest.mark.parametrize("name", sorted(CASES))
def test_one_azimuth_at_a_time_is_bit_identical_to_the_whole_grid(name, monkeypatch):
    terrain = CASES[name]
    assert terrain.diffraction, "the default carries this; a False here tests nothing"

    seen: list[tuple] = []
    real = M.terrain_utd_power

    def spy(*args):
        out = real(*args)
        seen.append((args, out))
        return out

    monkeypatch.setattr(M, "terrain_utd_power", spy)
    _engine(terrain).far_field(n_theta=18, n_phi=12, del_theta=5, del_phi=30)

    assert len(seen) == 1, f"expected one composer call for one grid, got {len(seen)}"
    args, full = seen[-1]
    n_phi = full.shape[1]
    assert n_phi > 1, "a one-column grid would make the comparison vacuous"

    sliced = np.stack(
        [real(*[_column(a, j, n_phi) for a in args])[:, 0] for j in range(n_phi)],
        axis=1,
    )
    assert sliced.shape == full.shape
    assert np.array_equal(sliced, full), (
        f"max|d| = {np.abs(sliced - full).max():.3e} at "
        f"{np.unravel_index(np.abs(sliced - full).argmax(), full.shape)}"
    )
