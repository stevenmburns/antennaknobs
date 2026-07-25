"""Web exposure of the faceted-terrain ground (issue #534, UI half).

Covers the request → engine mapping (levee/cliff presets, clamped inputs),
the response contract (`ground_terrain` + crest constants + applied label),
and the server cut physics' terrain branch — including the single-flat-facet
bit-identity gate that pins it to the plain finite ground.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from starlette.testclient import TestClient

from antennaknobs.terrain import Terrain
from antennaknobs.web.server import _EPS0, _pattern_cuts, app

# Imported after server: adapter and examples import each other cyclically,
# and only the examples-first entry order (which server triggers) resolves.
import antennaknobs.web.adapter as adapter  # noqa: E402
from antennaknobs.web.adapter import (  # noqa: E402
    _ground_for_engine,
    _pack_terrain,
    _pynec_ground_spec,
    _terrain_from_request,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _terrain_req(**terrain) -> dict:
    return {"ground": True, "ground_model": "terrain", "terrain": terrain}


# --- request -> engine mapping ---------------------------------------------


def test_ground_for_engine_builds_levee_by_default():
    spec = _ground_for_engine(_terrain_req(), 0.0)
    assert isinstance(spec, tuple) and spec[0] == "terrain"
    t = spec[1]
    assert isinstance(t, Terrain)
    assert len(t.sectors) == 2
    assert t.crest_medium == adapter._TERRAIN_LAND


def test_levee_params_flow_through():
    t = _terrain_from_request(
        _terrain_req(
            preset="levee",
            crest_width_m=4.0,
            slope_deg=30.0,
            drop_water_m=12.0,
            drop_land_m=6.0,
            water_azimuth_deg=90.0,
        )
    )
    water = t.sectors[0]
    assert (water.az0, water.az1) == (0.0, 180.0)  # water_azimuth ± 90
    crest = water.facets[0]
    assert crest.x1 == pytest.approx(2.0)  # half the crest width
    toe = water.facets[1]
    assert toe.z1 == pytest.approx(-12.0)
    run = toe.x1 - crest.x1
    assert math.degrees(math.atan2(12.0, run)) == pytest.approx(30.0)
    assert water.facets[2].eps_r == adapter._TERRAIN_WATER[0]


def test_cliff_preset_and_arc():
    t = _terrain_from_request(
        _terrain_req(preset="cliff", edge_m=8.0, drop_m=5.0, arc_deg=360.0)
    )
    assert len(t.sectors) == 1
    assert t.sectors[0].facets[0].x1 == pytest.approx(8.0)
    t2 = _terrain_from_request(
        _terrain_req(preset="cliff", edge_m=8.0, drop_m=5.0, arc_deg=120.0)
    )
    assert len(t2.sectors) == 2  # cliff sector + flat remainder


def test_garbage_terrain_params_clamp_to_defaults():
    t = _terrain_from_request(
        _terrain_req(
            preset="levee",
            crest_width_m="not-a-number",
            slope_deg=float("nan"),
            drop_water_m=-5.0,  # clamps to the positive floor
        )
    )
    assert isinstance(t, Terrain)  # constructors' invariants all hold
    assert t.sectors[0].facets[0].x1 == pytest.approx(1.5)  # default 3 m crest
    # Not a dict at all -> pure defaults.
    assert isinstance(
        _terrain_from_request({"ground": True, "terrain": "junk"}), Terrain
    )


def test_hillside_params_flow_through():
    t = _terrain_from_request(
        _terrain_req(
            preset="hillside",
            flat_width_m=30.0,
            up_slope_deg=25.0,
            down_slope_deg=8.0,
            downhill_azimuth_deg=180.0,
        )
    )
    down, up = t.sectors
    assert (down.az0, down.az1) == (90.0, 270.0)  # downhill_azimuth ± 90
    assert down.facets[0].x1 == pytest.approx(15.0)
    run = down.facets[-2].x1 - down.facets[0].x1
    assert math.degrees(math.atan2(150.0, run)) == pytest.approx(8.0)
    assert up.facets[-1].z1 > 0
    assert t.crest_medium == adapter._TERRAIN_LAND


def test_hillside_downhill_lifts_low_angles_over_flat():
    """The hillside's payoff at the cuts layer: toward the downhill side the
    low-angle field beats flat ground by several dB (the specular point
    walks down the slope, growing the effective height), while well above
    the slope band the bench governs and terrain equals flat exactly."""
    from antennaknobs.terrain import hillside_terrain

    t = hillside_terrain(flat_width=20.0, up_slope_deg=15.0, down_slope_deg=10.0)
    el = _pattern_cuts(_hertzian_over(t), 15.0, 0.0)["elevation"]
    el_flat = _pattern_cuts(_hertzian_over(None), 15.0, 0.0)["elevation"]
    assert el[2] > el_flat[2] + 3.0  # 4 deg toward the downhill side
    # 80 deg: the specular point sits on the flat bench -> identical values.
    assert el[40] == el_flat[40]


def test_terrain_marker_orientation_hint():
    """The chart-orientation marker: preset bearing + side labels, absent
    for the azimuth-symmetric full-circle cliff."""
    from antennaknobs.web.adapter import _terrain_marker

    m = _terrain_marker(_terrain_req(preset="hillside", downhill_azimuth_deg=45.0))
    assert m == {"bearing_deg": 45.0, "label": "downhill", "opposite": "uphill"}
    m = _terrain_marker(_terrain_req(preset="levee", water_azimuth_deg=-90.0))
    assert m == {"bearing_deg": -90.0, "label": "water", "opposite": "land"}
    assert _terrain_marker(_terrain_req(preset="cliff", arc_deg=360.0)) is None
    m = _terrain_marker(_terrain_req(preset="cliff", arc_deg=120.0, azimuth_deg=10.0))
    assert m == {"bearing_deg": 10.0, "label": "cliff", "opposite": "flat"}


def test_pynec_terrain_maps_to_crest_medium_sommerfeld():
    """The PyNEC terrain hybrid (issue #553): NEC has no facet model, but
    the #534 recipe solves currents over flat Sommerfeld at the crest
    medium anyway — which NEC does natively (GN 2). The facets ride the
    response's ground_terrain into the server's cut physics."""
    spec = _pynec_ground_spec(_terrain_req())
    assert spec == ("finite",) + adapter._TERRAIN_LAND


# --- server cut physics -----------------------------------------------------


def _hertzian_over(terrain: Terrain | None, *, h=6.1, dl=0.01, freq_mhz=21.2):
    """Vertical Hertzian dipole at height h; ground constants at the crest
    medium so the flat and terrain paths share identical inputs."""
    eps_r, sigma = adapter._TERRAIN_LAND
    omega = 2.0 * np.pi * freq_mhz * 1e6
    out = {
        "wires": [
            {
                "knot_positions": [[0.0, 0.0, h], [0.0, 0.0, h + dl]],
                "knot_currents_re": [1.0, 1.0],
                "knot_currents_im": [0.0, 0.0],
            }
        ],
        "measurement_freq_mhz": freq_mhz,
        "k_meas_m_inv": omega / 299_792_458.0,
        "ground": True,
        "ground_eps_r": eps_r,
        "ground_sigma": sigma,
        "ground_eps_im": -sigma / (omega * _EPS0),
        "directivity_norm": 3.0 / (2.0 * dl * dl),
    }
    if terrain is not None:
        out["ground_terrain"] = _pack_terrain(terrain)
    return out


def test_flat_terrain_cuts_bit_identical_to_finite_ground():
    """Gate 1 of #534, at the cuts layer: a single flat facet of the same
    medium must reproduce the plain finite-ground trace exactly."""
    from antennaknobs.terrain import flat_terrain

    flat = _pattern_cuts(_hertzian_over(None), 15.0, 30.0)
    terr = _pattern_cuts(
        _hertzian_over(flat_terrain(*adapter._TERRAIN_LAND)), 15.0, 30.0
    )
    assert terr["azimuth"] == flat["azimuth"]
    assert terr["elevation"] == flat["elevation"]


def test_levee_water_side_beats_land_side_at_lowest_angle():
    """Gate 3 of #534, at the cuts layer: the water side's greater drop
    (larger effective height) lifts the lowest-angle field. At higher
    elevations the two sides' lobe structures interleave (their nulls
    differ), so only the lowest sampled angle is a robust invariant.
    Elevation cut through the water bearing: 4 deg toward water (i=2) vs
    4 deg above the opposite horizon toward land (i=88)."""
    from antennaknobs.terrain import flat_terrain, levee_terrain

    t = levee_terrain(crest_width=3.0, slope_deg=20.0, drop_water=10.7, drop_land=7.6)
    el = _pattern_cuts(_hertzian_over(t), 15.0, 0.0)["elevation"]
    assert el[2] > el[88] + 1.0
    # And both sides differ from the flat crest-medium model — the facets
    # are actually in play, not just the crest Sommerfeld constants.
    el_flat = _pattern_cuts(
        _hertzian_over(flat_terrain(*adapter._TERRAIN_LAND)), 15.0, 0.0
    )["elevation"]
    assert abs(el[2] - el_flat[2]) > 1.0 and abs(el[88] - el_flat[88]) > 1.0


def test_terrain_zenith_sample_stays_finite_and_smooth():
    from antennaknobs.terrain import levee_terrain

    t = levee_terrain(crest_width=3.0, slope_deg=20.0, drop_water=10.7, drop_land=7.6)
    el = _pattern_cuts(_hertzian_over(t), 15.0, 0.0)["elevation"]
    # Vertical dipole: zenith is a null; neighbours bound it smoothly.
    assert el[45] <= min(el[44], el[46])


def test_norm_check_terrain_radiated_is_pec_facet_referenced():
    """Over terrain the P_in-referenced ratio is not an efficiency (the
    facet far field needn't integrate to the crest-referenced input power:
    measured 100.6% at 28.47 MHz / 38% at 21.2 MHz for the levee invvee,
    both confirmed against the engine's own far-field integral). The
    radiated fraction is instead referenced against the SAME facet
    geometry with perfect-reflector media — the restructuring cancels,
    isolating ground-media absorption — so it behaves like an efficiency
    again (measured 71.3% / 99.5% at the same two frequencies). The
    method tag drives the terrain-specific tooltip."""
    from antennaknobs.web.server import _norm_check

    for f in (28.47, 21.2):
        r = _norm_check(
            {
                "geometry": "dipoles.invvee",
                "measurement_freq_mhz": f,
                "momwire_model": "bspline",
                "ground": True,
                "ground_model": "terrain",
                "terrain": {"preset": "levee"},
            }
        )
        assert r["available"] and r["method"].startswith("grid_terrain_")
        # Bounded like an efficiency (small tolerance for quadrature and
        # interference cross-terms), and physically substantial.
        assert 0.2 < r["radiated_fraction"] <= 1.02, (f, r["radiated_fraction"])

    flat = _norm_check(
        {
            "geometry": "dipoles.invvee",
            "measurement_freq_mhz": 28.47,
            "momwire_model": "bspline",
            "ground": True,
            "ground_model": "sommerfeld",
        }
    )
    assert flat["method"].startswith("grid_") and not flat["method"].startswith(
        "grid_terrain"
    )
    # Flat finite ground stays a true efficiency: strictly below 1.
    assert 0.0 < flat["radiated_fraction"] < 1.0


# --- end-to-end -------------------------------------------------------------


def _solve_ws(client: TestClient, req: dict) -> dict:
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        return json.loads(ws.receive_text())


def test_ws_solve_with_terrain(client: TestClient):
    result = _solve_ws(
        client,
        {
            "geometry": "dipoles.invvee",
            "measurement_freq_mhz": 21.2,
            "momwire_model": "bspline",
            "ground": True,
            "ground_model": "terrain",
            "terrain": {"preset": "levee", "water_azimuth_deg": 0.0},
            "az_elev_deg": 15.0,
            "elev_az_deg": 0.0,
        },
    )
    assert "error" not in result
    assert result["ground_model_applied"] == "terrain"
    eps_r, sigma = adapter._TERRAIN_LAND
    assert result["ground_eps_r"] == eps_r and result["ground_sigma"] == sigma
    assert len(result["ground_terrain"]["sectors"]) == 2
    assert result["ground_terrain"]["marker"]["label"] == "water"
    assert len(result["cuts"]["elevation"]) == 180

    # /cuts stays stateless for terrain responses: new angles round-trip.
    r = client.post(
        "/cuts", json={"solve": result, "az_elev_deg": 25.0, "elev_az_deg": 90.0}
    )
    assert r.status_code == 200
    assert r.json()["azimuth"] != result["cuts"]["azimuth"]

    # Corrupt facet data -> a clean 400, not a 500.
    bad = dict(result)
    bad["ground_terrain"] = {"sectors": [{"az0": 0.0, "az1": 360.0, "facets": []}]}
    assert client.post("/cuts", json={"solve": bad}).status_code == 400


def test_pynec_terrain_solve_matches_momwire(client: TestClient):
    """End-to-end #553 hybrid: a PyNEC terrain solve carries the same
    response contract as momwire (applied label, crest constants, packed
    facets, cuts), and the two engines' terrain traces agree to engine
    tolerance — same facet physics over independently solved currents."""
    from antennaknobs.web import pynec_backend

    if not pynec_backend.HAVE_PYNEC:
        pytest.skip("pynec-accel not installed")

    base = {
        "geometry": "dipoles.invvee",
        "measurement_freq_mhz": 21.2,
        "ground": True,
        "ground_model": "terrain",
        "terrain": {"preset": "levee", "water_azimuth_deg": 0.0},
        "az_elev_deg": 15.0,
        "elev_az_deg": 0.0,
    }
    nec = _solve_ws(client, {**base, "solver": "pynec"})
    assert "error" not in nec
    assert nec["ground_model_applied"] == "terrain"
    eps_r, sigma = adapter._TERRAIN_LAND
    assert nec["ground_eps_r"] == eps_r and nec["ground_sigma"] == sigma
    assert len(nec["ground_terrain"]["sectors"]) == 2

    mom = _solve_ws(client, {**base, "solver": "momwire", "momwire_model": "bspline"})
    el_nec = np.asarray(nec["cuts"]["elevation"])
    el_mom = np.asarray(mom["cuts"]["elevation"])
    assert abs(el_nec.max() - el_mom.max()) < 1.0
    # The terrain asymmetry (water side up at the lowest angle) shows in
    # both engines' traces.
    assert el_nec[2] > el_nec[88] and el_mom[2] > el_mom[88]


def test_nec_export_falls_back_to_crest_medium():
    from antennaknobs.web.server import EXAMPLES

    deck = EXAMPLES["dipoles.invvee"].nec_export(
        {
            "geometry": "dipoles.invvee",
            "ground": True,
            "ground_model": "terrain",
            "terrain": {"preset": "levee"},
        }
    )
    gn = [ln for ln in deck.splitlines() if ln.startswith("GN")]
    assert gn and "1.300000E+01" in gn[0] and "5.000000E-03" in gn[0]
