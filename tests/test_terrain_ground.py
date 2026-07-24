"""Faceted-terrain far-field ground (issue #534).

The three acceptance gates from the issue, plus the terrain type system:

1. Flat-profile limit reproduces ("finite", eps, sigma) bit-identically —
   impedance and the full far-field grid.
2. Single-cliff limit tracks nec2c's classic GN+GD cliff ground (via the
   #535 harness deck authoring) to a small constant offset.
3. The levee scenario shows the physics: crest-pinned impedance, water/land
   azimuth asymmetry, low-angle lobes at the full effective height, and
   agreement of all models at crest-governed high elevations.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import numpy as np
import pytest

from antennaknobs import merge_params
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.terrain import (
    Facet,
    Sector,
    Terrain,
    cliff_terrain,
    flat_terrain,
    levee_terrain,
    specular_cut,
)
from momwire import BSplineSolver

needs_nec2c = pytest.mark.skipif(
    shutil.which("nec2c") is None, reason="nec2c not on PATH"
)

# The motivating QTH (issues #534/#535).
F, H0 = 21.2, 6.1
SOIL, WATER = (13.0, 0.005), (80.0, 0.005)
QTH = dict(crest_width=3.0, slope_deg=20.0, drop_water=10.67, drop_land=7.62)


def _engine(ground):
    p = merge_params(Builder.default_params, {"design_freq": F, "freq": F, "base": H0})
    return MomwireEngine(
        Builder(p), solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=ground
    )


def _grid(eng):
    ff = eng.far_field(n_theta=90, n_phi=72, del_theta=1, del_phi=5)
    return 90.0 - np.asarray(ff.thetas), np.asarray(ff.rings)


def _at(el, cut, angle):
    return float(cut[int(np.argmin(np.abs(el - angle)))])


# ---------------------------------------------------------------------------
# type system
# ---------------------------------------------------------------------------


def test_terrain_rejects_gap_and_overlap():
    s = (Facet(None, 0.0, 13.0, 0.005),)
    with pytest.raises(ValueError, match="tile 360"):
        Terrain(sectors=(Sector(0, 180, s),))
    with pytest.raises(ValueError, match="tile 360|overlap"):
        Terrain(sectors=(Sector(0, 270, s), Sector(180, 270, s)))


def test_terrain_rejects_mismatched_crest_media():
    with pytest.raises(ValueError, match="crest medium"):
        Terrain(
            sectors=(
                Sector(0, 180, (Facet(None, 0.0, 13.0, 0.005),)),
                Sector(180, 360, (Facet(None, 0.0, 80.0, 0.005),)),
            )
        )


def test_sector_rejects_finite_last_facet_and_bad_order():
    with pytest.raises(ValueError, match="infinite"):
        Sector(0, 360, (Facet(5.0, 0.0, 13.0, 0.005),))
    with pytest.raises(ValueError, match="increase"):
        Sector(
            0,
            360,
            (
                Facet(5.0, 0.0, 13.0, 0.005),
                Facet(2.0, -1.0, 13.0, 0.005),
                Facet(None, -1.0, 13.0, 0.005),
            ),
        )


def test_sector_for_wraps_azimuth():
    t = levee_terrain(**QTH, water_azimuth=0.0)
    # Water sector spans -90..90: phi 0 and 350 are water (index 0),
    # phi 180 is land (index 1).
    assert list(t.sector_for([0.0, 350.0, 180.0, 90.0])) == [0, 0, 1, 1]
    assert t.crest_medium == SOIL


# ---------------------------------------------------------------------------
# specular geometry
# ---------------------------------------------------------------------------


def test_specular_cut_band_structure_matches_qth_geometry():
    """Facet selection reproduces the #535 validity-band angles: crest facet
    above ~76 deg elevation, water plain below ~28.6, slope between."""
    t = levee_terrain(**QTH)
    water = t.sectors[0]

    def one(psi_deg):
        theta = np.radians([90.0 - psi_deg])
        z_f, beta, eps, sig = specular_cut(water, theta, H0)
        return float(z_f[0]), float(beta[0]), float(eps[0])

    z, b, e = one(80.0)  # crest band
    assert z == 0.0 and b == 0.0 and e == SOIL[0]
    z, b, e = one(50.0)  # slope band
    assert -10.67 < z < 0.0 and b == pytest.approx(np.radians(20.0)) and e == SOIL[0]
    z, b, e = one(20.0)  # water plain
    assert z == pytest.approx(-10.67) and b == 0.0 and e == WATER[0]


def test_specular_cut_zenith_hits_the_crest():
    t = levee_terrain(**QTH)
    z_f, beta, eps, _ = specular_cut(t.sectors[0], np.array([0.0]), H0)
    assert z_f[0] == 0.0 and beta[0] == 0.0 and eps[0] == SOIL[0]


# ---------------------------------------------------------------------------
# gate 1: flat limit, bit-identical
# ---------------------------------------------------------------------------


def test_flat_terrain_reproduces_finite_ground_bit_identically():
    e_fin = _engine(("finite", *SOIL))
    e_ter = _engine(("terrain", flat_terrain(*SOIL)))
    assert complex(e_fin.impedance()[0]) == complex(e_ter.impedance()[0])
    _, g_fin = _grid(e_fin)
    _, g_ter = _grid(e_ter)
    assert np.array_equal(g_fin, g_ter)


# ---------------------------------------------------------------------------
# gate 2: single cliff vs nec2c GN+GD (via the #535 harness)
# ---------------------------------------------------------------------------


@needs_nec2c
def test_cliff_terrain_tracks_nec2c_gd_cliff():
    lb_path = Path(__file__).parent.parent / "scripts" / "bench_levee_bracket.py"
    spec = importlib.util.spec_from_file_location("lb", lb_path)
    lb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lb)

    deck = lb.author_cliff_deck(
        "dipoles.invvee", F, H0, ("finite", *SOIL), (*WATER, 1.5, 10.67), 2
    )
    el_n, g_n = lb.cliff_elevation_cut(lb.run_nec2c_pattern(deck), phi=0.0)

    t = cliff_terrain(edge=1.5, drop=10.67, inner=SOIL, outer=WATER)
    el_t, grid = _grid(_engine(("terrain", t)))
    g_t = grid[:, 0]  # phi = 0, over the cliff

    # Measured 2026-07-24: constant -0.11 dB across 3..60 deg (the medium-1
    # refl-coef vs Sommerfeld offset). Gate generously at 0.5 dB.
    for a in (3, 5, 8, 10, 15, 20, 30, 45, 60):
        d = _at(el_t, g_t, a) - _at(el_n, g_n, a)
        assert abs(d) < 0.5, f"terrain vs nec2c cliff at {a} deg: {d:+.2f} dB"


# ---------------------------------------------------------------------------
# gate 3: the levee scenario
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def levee():
    e_ter = _engine(("terrain", levee_terrain(**QTH)))
    e_crest = _engine(("finite", *SOIL))
    z_ter = complex(e_ter.impedance()[0])
    z_crest = complex(e_crest.impedance()[0])
    el, grid = _grid(e_ter)
    _, g_crest = _grid(e_crest)
    return z_ter, z_crest, el, grid, g_crest


def test_levee_impedance_is_the_crest_sommerfeld_impedance(levee):
    z_ter, z_crest, *_ = levee
    assert z_ter == z_crest


def test_levee_azimuth_asymmetry_water_beats_land_low(levee):
    el, grid = levee[2], levee[3]
    water, land = grid[:, 0], grid[:, 36]  # phi 0 / 180
    assert _at(el, water, 5) > _at(el, land, 5) + 0.5
    assert _at(el, water, 10) > _at(el, land, 10) + 0.5


def test_levee_low_angle_rides_the_full_effective_height(levee):
    """Below the water-side toe angle the terrain pattern must track the
    flat model at h_eff = 16.77 m over water — within ~1.5 dB (same-azimuth
    cut; the residual is the slope-facet transition tail)."""
    el, grid = levee[2], levee[3]
    p = merge_params(
        Builder.default_params, {"design_freq": F, "freq": F, "base": H0 + 10.67}
    )
    eng = MomwireEngine(
        Builder(p),
        solver=BSplineSolver,
        solver_kwargs={"degree": 2},
        ground=("finite", *WATER),
    )
    el_e, g_eff = _grid(eng)
    for a in (5, 8, 10):
        d = _at(el, grid[:, 0], a) - _at(el_e, g_eff[:, 0], a)
        assert abs(d) < 1.5, f"terrain vs h_eff flat model at {a} deg: {d:+.2f} dB"


def test_levee_high_angles_are_crest_governed(levee):
    """Above the crest threshold (~76 deg) every azimuth reflects off the
    crest facet: terrain == flat crest model, both sides equal."""
    el, grid, g_crest = levee[2], levee[3], levee[4]
    for a in (80, 85):
        w = _at(el, grid[:, 0], a)
        ln = _at(el, grid[:, 36], a)
        c = _at(el, g_crest[:, 0], a)
        assert w == pytest.approx(ln, abs=1e-9)
        assert w == pytest.approx(c, abs=1e-9)
