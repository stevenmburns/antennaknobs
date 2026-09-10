"""Issue #1373 — the terrain far field with shadowing, exact tilted-mirror
reflections and UTD wedge diffraction, through the momwire engine.

Gate 1: a single flat facet with ``diffraction=True`` reproduces the plain
finite ground to round-off (no edges, nothing to shadow; the per-segment
image path recomputes the same physics), and the #534 specular path stays
bit-identical to it.

Gate 3: on M0AGP's 40 m, 45° hill with the mast mid-slope, the elevation
cuts are continuous at 1° resolution above the horizon roll-off — the
shadow and reflection boundaries that stepped by 6–15 dB under the
specular composer are patched by the diffracted field — and the uphill band
below the slope angle reads as a shadowed, diffracted field rather than
grazing cancellation.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from antennaknobs import merge_params
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.terrain import Facet, Sector, Terrain, flat_terrain
from momwire import BSplineSolver

F, H0 = 21.2, 6.1
SOIL = (13.0, 0.005)


def _engine(ground):
    p = merge_params(Builder.default_params, {"design_freq": F, "freq": F, "base": H0})
    return MomwireEngine(
        Builder(p), solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=ground
    )


def _grid(eng, n_phi=72, del_phi=5):
    """(elevations in degrees, gain in dBi on the (theta, phi) grid)."""
    ff = eng.far_field(n_theta=90, n_phi=n_phi, del_theta=1, del_phi=del_phi)
    return 90.0 - np.asarray(ff.thetas), np.asarray(ff.rings)


def test_flat_terrain_with_diffraction_reproduces_finite_ground():
    plain = _grid(_engine(("finite", *SOIL)))[1]
    specular = _grid(_engine(("terrain", flat_terrain(*SOIL))))[1]
    utd = Terrain(sectors=flat_terrain(*SOIL).sectors, diffraction=True)
    new = _grid(_engine(("terrain", utd)))[1]
    assert np.array_equal(plain, specular)  # #534's gate 1, still bit-identical
    assert np.max(np.abs(new - plain)) < 1e-8  # dB


def _mike_hill(H, slope_deg, f, n_facets=12):
    """Plateau uphill, slope, plain downhill; the mast f·H above the plain."""
    eps, sig = SOIL
    h_a, h_up = f * H, H - f * H
    tan_s = math.tan(math.radians(slope_deg))

    def ramp(dz):
        if abs(dz) < 1e-9:
            return ()
        run = abs(dz) / tan_s
        return tuple(
            Facet(run * (i + 1) / n_facets, dz * (i + 1) / n_facets, eps, sig)
            for i in range(n_facets)
        )

    down = (*ramp(-h_a), Facet(None, -h_a, eps, sig))
    up = (*ramp(+h_up), Facet(None, +h_up, eps, sig))
    return Terrain(
        sectors=(Sector(-90.0, 90.0, down), Sector(90.0, 270.0, up)), diffraction=True
    )


@pytest.mark.slow
def test_hillside_cuts_are_continuous_and_the_uphill_band_is_shadowed():
    """The specular composer steps by many dB where the specular point
    leaves a facet and where the direct ray meets the crest; with shadowing
    and diffraction those boundaries are patched. A real interference null
    (this vee's direct ray against three reflection paths at 17° downhill)
    still moves a few dB per degree, so the gate is relative: the UTD path
    steps no more than the specular one anywhere above the horizon
    roll-off, and never by more than 4 dB."""
    hill = _mike_hill(40.0, 45.0, 0.5)
    spec = Terrain(sectors=hill.sectors, diffraction=False)
    els, db_utd = _grid(_engine(("terrain", hill)), n_phi=4, del_phi=90)
    _, db_spec = _grid(_engine(("terrain", spec)), n_phi=4, del_phi=90)
    keep = els >= 5.0  # above the horizon roll-off, which is steep by itself
    for col in (0, 2):  # az 0 downhill, az 180 uphill
        step_utd = np.abs(np.diff(db_utd[keep, col])).max()
        step_spec = np.abs(np.diff(db_spec[keep, col])).max()
        assert step_utd <= step_spec + 1e-9, (col, step_utd, step_spec)
        assert step_utd < 4.0, (col, step_utd)
    # uphill below the slope angle is behind the crest: well below the same
    # elevations downhill
    band = (els >= 5.0) & (els <= 40.0)
    assert np.all(db_utd[band, 2] < db_utd[band, 0] - 6.0)
