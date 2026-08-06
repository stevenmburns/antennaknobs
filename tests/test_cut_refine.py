"""Non-uniform pattern-cut sampling (issue #744).

The /cuts endpoint (HTTP and the /ws sidecar) accepts an explicit angle
list per cut so adaptive refinement can densify a multi-lobed pattern where
the polar trace corners. What has to hold:

  - the dBi at an explicit angle equals the dBi the uniform grid gives at
    that same angle — refinement adds samples, it never changes physics;
  - the parameterisation travels back with the data, because a non-uniform
    trace's angle is no longer derivable from its index;
  - a uniform request is byte-identical to what it was before this feature,
    so pre-#744 clients keep working;
  - the cuts-source cache stays angle-independent, so extra angles against a
    live solve_id cost one far-field evaluation and no solve.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from starlette.testclient import TestClient

import antennaknobs.web.server as server
from antennaknobs.web.server import _pattern_cuts, app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _hertzian(h: float = 2.0, ground: bool = True) -> dict:
    """One z-directed segment at height h — a lobed elevation pattern once
    the ground image interferes, which is exactly what refinement is for."""
    dl = 0.01
    out = {
        "wires": [
            {
                "knot_positions": [[0.0, 0.0, h], [0.0, 0.0, h + dl]],
                "knot_currents_re": [1.0, 1.0],
                "knot_currents_im": [0.0, 0.0],
            }
        ],
        "k_meas_m_inv": 0.44,
        "ground": ground,
        "ground_eps_r": 13.0,
        "ground_eps_im": -1.0,
        "directivity_norm": 3.0 / (2.0 * dl * dl),
    }
    return out


_SOLVE_REQ = {
    "geometry": "dipoles.invvee",
    "measurement_freq_mhz": 28.47,
    "momwire_model": "bspline",
    "az_elev_deg": 15.0,
    "elev_az_deg": 45.0,
}


def _ws_solve(client: TestClient, req=_SOLVE_REQ) -> dict:
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        return json.loads(ws.receive_text())


# ---- physics: extra angles are extra SAMPLES, not different physics -------


def test_explicit_angles_agree_with_the_uniform_grid():
    out = _hertzian()
    uniform = _pattern_cuts(out, 15.0, 0.0)
    n = uniform["n_dir"]
    # Every 10th uniform angle, requested explicitly.
    picked = [(360.0 * i) / n for i in range(0, n, 10)]
    explicit = _pattern_cuts(
        out, 15.0, 0.0, az_angles_deg=picked, elev_angles_deg=picked
    )
    assert explicit["az_angles_deg"] == pytest.approx(picked)
    for j, i in enumerate(range(0, n, 10)):
        assert explicit["azimuth"][j] == pytest.approx(uniform["azimuth"][i], abs=1e-3)
        assert explicit["elevation"][j] == pytest.approx(
            uniform["elevation"][i], abs=1e-3
        )


def test_a_uniform_request_is_unchanged_by_this_feature():
    out = _hertzian()
    cuts = _pattern_cuts(out, 15.0, 0.0)
    # The angle arrays stay ABSENT: "absent means t = 2π·i/n" is the contract
    # every pre-#744 client draws on.
    assert "az_angles_deg" not in cuts
    assert "elev_angles_deg" not in cuts
    assert len(cuts["azimuth"]) == len(cuts["elevation"]) == cuts["n_dir"] == 180


def test_the_two_cuts_may_carry_different_sample_counts():
    out = _hertzian()
    cuts = _pattern_cuts(
        out,
        15.0,
        0.0,
        az_angles_deg=[0.0, 90.0, 180.0, 270.0],
        elev_angles_deg=[0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0],
    )
    assert len(cuts["azimuth"]) == 4
    assert len(cuts["elevation"]) == 8
    # n_dir keeps reporting the uniform base resolution; a refined trace's
    # own length governs.
    assert cuts["n_dir"] == 180


def test_angles_are_wrapped_deduped_and_sorted():
    out = _hertzian()
    cuts = _pattern_cuts(
        out, 15.0, 0.0, az_angles_deg=[270.0, -90.0, 10.0, 370.0, 10.0]
    )
    # -90 wraps onto 270 and 370 onto 10; both duplicates collapse. The chart
    # strokes these in order, so an unsorted list would draw a chord across
    # the pattern.
    assert cuts["az_angles_deg"] == pytest.approx([10.0, 270.0])
    assert cuts["az_angles_deg"] == sorted(cuts["az_angles_deg"])


def test_below_horizon_samples_still_clamp_to_the_floor():
    out = _hertzian(ground=True)
    cuts = _pattern_cuts(out, 15.0, 0.0, elev_angles_deg=[10.0, 190.0, 270.0, 350.0])
    floor = cuts["floor_dbi"]
    # t in (180, 360) dips below the horizon on the elevation circle.
    assert cuts["elevation"][0] > floor
    assert cuts["elevation"][2] == floor


def test_a_refined_elevation_cut_draws_closer_to_the_true_pattern():
    # The acceptance shape for cuts: same chart geometry, denser sampling,
    # strictly smaller worst display-space error. Measured with the chart's
    # own radial map (dBi -> fraction of plot radius, -20 dBi at the origin).
    out = _hertzian(h=8.0, ground=True)  # many lobes: ~1.1 lambda up

    def deviation(angles_deg, dbi):
        floor, top = -20.0, max(10.0, np.ceil(max(dbi) + 1.0))
        frac = np.clip((np.asarray(dbi) - floor) / (top - floor), 0.0, 1.0) * 0.5
        t = np.radians(angles_deg)
        p = np.stack([frac * np.cos(t), frac * np.sin(t)], axis=-1)
        prev, nxt = np.roll(p, 1, axis=0), np.roll(p, -1, axis=0)
        chord = nxt - prev
        a = p - prev
        length = np.hypot(chord[:, 0], chord[:, 1])
        cross = np.abs(a[:, 0] * chord[:, 1] - a[:, 1] * chord[:, 0])
        return float(np.max(np.where(length > 0, cross / np.maximum(length, 1e-15), 0)))

    coarse_angles = [(360.0 * i) / 180 for i in range(180)]
    coarse = _pattern_cuts(out, 15.0, 0.0)["elevation"]
    fine_angles = [(360.0 * i) / 720 for i in range(720)]
    fine = _pattern_cuts(out, 15.0, 0.0, elev_angles_deg=fine_angles)["elevation"]
    assert deviation(fine_angles, fine) < deviation(coarse_angles, coarse)


# ---- request plumbing -----------------------------------------------------


def test_http_cuts_accepts_explicit_angles_by_solve_id(client: TestClient):
    result = _ws_solve(client)
    angles = [0.0, 12.5, 90.0, 181.25, 300.0]
    r = client.post(
        "/cuts",
        json={
            "solve_id": result["solve_id"],
            "az_elev_deg": 15.0,
            "elev_az_deg": 45.0,
            "elev_angles_deg": angles,
        },
    )
    assert r.status_code == 200
    cuts = r.json()
    assert cuts["elev_angles_deg"] == pytest.approx(angles)
    assert len(cuts["elevation"]) == len(angles)
    # The azimuth cut was not refined, so it stays uniform and unannotated.
    assert "az_angles_deg" not in cuts
    assert len(cuts["azimuth"]) == 180


def test_http_cuts_accepts_explicit_angles_in_the_full_body_path(client: TestClient):
    result = _ws_solve(client)
    angles = [0.0, 45.0, 90.0]
    by_id = client.post(
        "/cuts",
        json={
            "solve_id": result["solve_id"],
            "az_elev_deg": 15.0,
            "elev_az_deg": 45.0,
            "az_angles_deg": angles,
        },
    )
    full = client.post(
        "/cuts",
        json={
            "solve": result,
            "az_elev_deg": 15.0,
            "elev_az_deg": 45.0,
            "az_angles_deg": angles,
        },
    )
    # The stateless backstop must answer identically — a pin whose server
    # session died still refines.
    assert by_id.status_code == 200 and full.status_code == 200
    assert by_id.json() == full.json()


def test_non_finite_angles_are_rejected():
    # NaN/inf can't ride JSON at all, so they're pinned at the validator
    # rather than over the wire — but a hand-rolled client could still hand
    # them to _pattern_cuts.
    for bad in ([float("nan")], [float("inf")], [1.0, float("-inf")]):
        with pytest.raises(ValueError):
            server._cut_angles(bad)


@pytest.mark.parametrize(
    "angles",
    ["not-a-list", [1.0, "x"], [True], list(range(721))],
)
def test_junk_angle_lists_are_a_400(client: TestClient, angles):
    result = _ws_solve(client)
    r = client.post(
        "/cuts",
        json={
            "solve_id": result["solve_id"],
            "az_elev_deg": 15.0,
            "elev_az_deg": 45.0,
            "az_angles_deg": angles,
        },
    )
    assert r.status_code == 400


def test_an_empty_angle_list_falls_back_to_the_uniform_circle(client: TestClient):
    out = _hertzian()
    cuts = _pattern_cuts(out, 15.0, 0.0, az_angles_deg=[])
    assert len(cuts["azimuth"]) == 180


def test_ws_cuts_channel_carries_explicit_angles(client: TestClient):
    angles = [0.0, 30.0, 60.0, 200.0]
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(_SOLVE_REQ))
        result = json.loads(ws.receive_text())
        ws.send_text(
            json.dumps(
                {
                    "_kind": "cuts",
                    "solve_id": result["solve_id"],
                    "az_elev_deg": 15.0,
                    "elev_az_deg": 45.0,
                    "az_angles_deg": angles,
                }
            )
        )
        msg = json.loads(ws.receive_text())
    assert msg["ok"] is True
    assert msg["refined"] is True
    assert msg["cuts"]["az_angles_deg"] == pytest.approx(angles)
    http = client.post(
        "/cuts",
        json={
            "solve_id": result["solve_id"],
            "az_elev_deg": 15.0,
            "elev_az_deg": 45.0,
            "az_angles_deg": angles,
        },
    )
    assert msg["cuts"] == http.json()


def test_ws_refinement_and_a_dial_request_do_not_squash_each_other(
    client: TestClient,
):
    # Latest-wins per solve is right for dial drags, but a refinement asks
    # for a different thing at the same angles; sharing a slot would lose it
    # every time the user is still moving.
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(_SOLVE_REQ))
        result = json.loads(ws.receive_text())
        base = {
            "_kind": "cuts",
            "solve_id": result["solve_id"],
            "az_elev_deg": 15.0,
            "elev_az_deg": 45.0,
        }
        ws.send_text(json.dumps(base))
        ws.send_text(json.dumps({**base, "az_angles_deg": [0.0, 90.0, 180.0]}))
        replies = [json.loads(ws.receive_text()) for _ in range(2)]
    by_refined = {r["refined"]: r for r in replies}
    assert set(by_refined) == {False, True}
    assert len(by_refined[False]["cuts"]["azimuth"]) == 180
    assert len(by_refined[True]["cuts"]["azimuth"]) == 3


def test_the_cuts_source_cache_stays_angle_independent(client: TestClient):
    # Refinement never re-solves: extra angles run against the cached moment
    # set, which is why cut refinement takes no lane turn.
    result = _ws_solve(client)
    solve_id = result["solve_id"]
    before = len(server._CUTS_SRC_CACHE)
    for angles in ([0.0, 1.0], [2.0, 3.0, 4.0], [5.0]):
        r = client.post(
            "/cuts",
            json={
                "solve_id": solve_id,
                "az_elev_deg": 15.0,
                "elev_az_deg": 45.0,
                "az_angles_deg": angles,
            },
        )
        assert r.status_code == 200
        assert len(r.json()["azimuth"]) == len(angles)
    assert len(server._CUTS_SRC_CACHE) == before
