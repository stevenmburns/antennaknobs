"""Issue #1373 — ray geometry and wedge diffraction for the faceted terrain.

Module-level gates, independent of any antenna:

* a flat profile has no edges and shadows nothing;
* a subdivided straight ramp diffracts nothing (collinear breaks are n = 1);
* the tilted-mirror reflection reproduces the horizontal-mirror specular
  point on horizontal facets and images the source across the plane on a
  tilted one;
* the UTD coefficient at a shadow boundary hands over exactly half the field
  the boundary switches off, and the total is continuous through it (the
  knife-edge limit);
* the perfectly conducting limit of the Luebbers form is Kouyoumjian–Pathak.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from antennaknobs.terrain import Facet, Sector, flat_terrain
from antennaknobs.terrain_utd import (
    diffractions,
    direct_visible,
    fresnel_grazing,
    reflections,
    transition,
    wedge_coefficients,
    wedges,
)

FREQ = 7.1
K = 2 * math.pi * FREQ * 1e6 / 299_792_458.0
OMEGA = 2 * math.pi * FREQ * 1e6
SOIL = (13.0, 0.005)


def _sector(facets):
    return Sector(az0=-90.0, az1=90.0, facets=tuple(facets))


def _ramp(H, slope_deg, n_facets, eps=13.0, sig=0.005):
    run = H / math.tan(math.radians(slope_deg))
    fs = [
        Facet(run * (i + 1) / n_facets, H * (i + 1) / n_facets, eps, sig)
        for i in range(n_facets)
    ]
    fs.append(Facet(None, H, eps, sig))
    return _sector(fs)


def test_flat_profile_has_no_edges_and_no_shadow():
    sec = flat_terrain(*SOIL).sectors[0]
    assert wedges(sec) == []
    psi = np.radians(np.linspace(0.5, 89.5, 179))
    assert direct_visible(sec, psi, 10.0).all()
    refl = reflections(sec, psi, 10.0)
    assert len(refl) == 1 and refl[0].mask.all()
    # horizontal mirror: image straight below, cos of incidence = sin(psi)
    assert np.allclose(refl[0].image, [0.0, -10.0])
    assert np.allclose(refl[0].cos_ti, np.sin(psi))


def test_subdivided_ramp_makes_one_edge_at_the_crest_only():
    sec = _ramp(40.0, 45.0, 12)  # 12 collinear breaks then the plateau
    ws = wedges(sec)
    assert len(ws) == 1
    (crest,) = ws
    assert np.allclose(crest.p, [40.0, 40.0])
    # 0-face runs back down the slope, n-face is the plateau: exterior 225°
    assert crest.n == pytest.approx(1.25)


def test_uphill_direct_ray_is_shadowed_below_the_slope_angle():
    sec = _ramp(40.0, 45.0, 12)
    h = 5.0  # source 5 m up the mast; the slope starts at the mast foot
    psi = np.radians(np.array([10.0, 30.0, 44.0, 46.0, 60.0]))
    vis = direct_visible(sec, psi, h)
    # a ray from (0, 5) at 44° clears the slope? z(x)=5+x tan44 vs slope x:
    # at x=40: 5+38.6=43.6 > 40 -> clear. At 30°: 5+23.1 < 40 -> blocked.
    assert vis.tolist() == [False, False, True, True, True]


def test_tilted_mirror_images_the_source_across_the_facet():
    # a single 45° facet falling away from the mast foot, plain far away
    sec = _sector([Facet(1000.0, -1000.0, *SOIL), Facet(None, -1000.0, *SOIL)])
    h = 10.0
    psi = np.radians(np.linspace(-44.0, 89.0, 134))  # below-horizontal too
    refl = [
        r
        for r in reflections(sec, psi, h)
        if len(r.planes) == 1 and math.isfinite(r.plane.length)
    ]
    assert len(refl) == 1
    r = refl[0]
    # image of (0, 10) across the line z = -x is (-10, 0)
    assert np.allclose(r.image, [-10.0, 0.0])
    # a reflected ray leaves the facet upward for psi > -45° (w . n > 0 with
    # n = (1, 1)/sqrt2), but its specular point is on THIS facet (x >= 0)
    # only for directions below the horizontal: from the image (-10, 0) an
    # upward ray meets the line z = -x at x < 0, behind the mast. The slope
    # ahead of a mast feeds the sky below the horizontal; the sky above it
    # is fed by the slope behind (the two-sided cut, next test).
    assert r.mask.tolist() == (psi <= 1e-9).tolist()
    # local incidence: cos from the facet normal = sin(psi + 45°)
    assert np.allclose(r.cos_ti, np.sin(psi + math.pi / 4), atol=1e-12)


def test_shadow_boundary_is_continuous_and_the_diffracted_field_jumps_by_the_direct_field():
    """Knife-edge limit: a plateau ending in a sheer drop. Across the cliff
    edge's shadow boundary the direct field switches off; the diffracted
    field jumps by exactly that amount in the opposite sense, so the total
    is continuous. (The total is not ½ there: the other three UTD terms
    carry the plateau's reflected field, which is legitimately nonzero.)"""
    sec = _sector(
        [
            Facet(30.0, 0.0, *SOIL),
            Facet(30.0 + 1e-3, -200.0, *SOIL),
            Facet(None, -200.0, *SOIL),
        ]
    )
    h = 20.0
    psi_sb = -math.atan2(h, 30.0)  # source (0, 20), edge (30, 0)
    d = np.radians(0.02)
    psi = psi_sb + np.array([20.0, 1.0, 0.2, -0.2, -1.0, -20.0]) * d
    diff = [
        x for x in diffractions(sec, psi, h, K, OMEGA) if abs(x.wedge.n - 1.5) < 1e-3
    ]
    assert len(diff) == 1
    dd = diff[0]
    S = np.array([0.0, h])
    E = dd.wedge.p
    w = np.stack([np.cos(psi), np.sin(psi)], -1)
    direct = np.exp(1j * K * (w @ S))
    diffr = dd.D_soft * np.exp(1j * K * (w @ E))
    vis = psi > psi_sb
    total = np.where(vis, direct, 0) + diffr
    # continuous through the boundary
    assert abs(total[2] - total[3]) < 0.01
    # the diffracted field's jump is the direct field it replaces
    assert abs((diffr[3] - diffr[2]) - direct[2]) < 0.02
    # and far from the boundary the diffracted term is smaller than the
    # direct one it no longer has to patch
    assert abs(diffr[0]) < 0.7 and abs(diffr[-1]) < 0.7


def test_two_sided_cut_reflects_off_the_facet_behind_the_mast():
    """A mast mid-slope: in the downhill cut the slope AHEAD reflects only
    below the horizontal, while the slope BEHIND (the uphill sector,
    mirrored) is the tilted mirror that throws radiation into the downhill
    sky above the horizontal."""
    from antennaknobs.terrain_utd import build_cut

    H, S_deg = 40.0, 45.0
    run = H / math.tan(math.radians(S_deg))
    # mast half way up: 20 m of slope ahead (falling), 20 m behind (rising)
    down = _sector([Facet(run / 2, -H / 2, *SOIL), Facet(None, -H / 2, *SOIL)])
    up = _sector([Facet(run / 2, +H / 2, *SOIL), Facet(None, +H / 2, *SOIL)])
    cut = build_cut(down, up)
    assert cut.xb.min() < 0 < cut.xb.max()
    h = 5.0
    psi = np.radians(np.linspace(1.0, 89.0, 89))
    refl = [r for r in reflections(cut, psi, h) if len(r.planes) == 1]
    ahead = [r for r in refl if r.plane.t[0] > 0 and math.isfinite(r.plane.length)]
    behind = [r for r in refl if r.plane.t[0] < 0 and math.isfinite(r.plane.length)]
    assert ahead == []  # the falling slope ahead reflects nothing upward
    assert len(behind) == 1
    b = behind[0]
    # image of (0, 5) across the line z = -x (rising behind: z = -x for x<0)
    assert np.allclose(b.image, [-5.0, 0.0])
    # it serves the downhill sky above the horizontal for the directions
    # whose specular point is on the 20 m of slope behind the mast
    assert b.mask.any()
    # the crest behind the mast is a wedge on the back side
    backs = [w for w in cut.wedges if w.sense == -1]
    assert len(backs) == 1 and backs[0].n == pytest.approx(1.25)


def test_pec_limit_is_kouyoumjian_pathak():
    n, k, L = 1.5, K, 25.0
    phi = np.radians(np.linspace(5, 260, 52))
    phi_p = math.radians(40.0)
    # a huge conductivity makes R_h -> -1 and R_v -> +1
    pec = 1.0 - 1j * 1e9
    Ds, Dh = wedge_coefficients(k, L, n, phi, phi_p, pec, pec)
    R_h, R_v = fresnel_grazing(np.radians(30.0), pec)
    assert R_h == pytest.approx(-1.0, abs=1e-3)
    assert R_v == pytest.approx(1.0, abs=1e-3)
    # soft and hard differ only through the reflection terms
    assert not np.allclose(Ds, Dh)
    assert np.all(np.isfinite(Ds)) and np.all(np.isfinite(Dh))


def test_transition_function_limits():
    X = np.array([1e-6, 1e-3, 0.1, 1.0, 10.0, 100.0])
    F = transition(X)
    assert abs(F[-1] - 1.0) < 0.01
    small = math.sqrt(math.pi * 1e-6) * np.exp(1j * math.pi / 4)
    assert abs(F[0] - small) / abs(small) < 0.01
