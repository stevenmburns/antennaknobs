"""Server-side polar-chart cuts (issue #547).

The frontend's JS cut physics (computeCutDbi) is retired in favour of
`server._pattern_cuts`, so these tests pin the physics analytically (a
Hertzian dipole has closed-form gain), the request plumbing (/ws solve
attaches cuts; /cuts recomputes them statelessly), and the sample
parameterisation the polar charts assume (t = 2π·i/N_DIR).
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from starlette.testclient import TestClient

import antennaknobs.web.server as server
from antennaknobs.web.server import _mag2_at_directions, _pattern_cuts, app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _hertzian(dl=0.01, h=0.0, ground=False):
    """Solve-response stand-in: one z-directed segment of length dl at height
    h carrying 1 A. Free space: gain 1.5·sin²θ, peak 1.76 dBi; the norm is
    the closed form 3/(2·|I·dl|²)."""
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


def test_hertzian_azimuth_cut_at_horizon_is_flat_peak():
    cuts = _pattern_cuts(_hertzian(), az_elev_deg=0.0, elev_az_deg=0.0)
    az = np.asarray(cuts["azimuth"])
    assert np.allclose(az, 10 * math.log10(1.5), atol=1e-3)


def test_hertzian_elevation_cut_follows_sin2_theta():
    cuts = _pattern_cuts(_hertzian(), az_elev_deg=0.0, elev_az_deg=0.0)
    el = np.asarray(cuts["elevation"])
    n = cuts["n_dir"]
    # Sample i sits at t = 2π·i/n; the pattern is 1.5·cos²t (cos t = sin θ).
    for i in (10, 20, 40, 70):
        t = 2 * math.pi * i / n
        expect = 10 * math.log10(1.5 * math.cos(t) ** 2)
        assert el[i] == pytest.approx(expect, abs=1e-2)


def test_hertzian_elevation_cut_peaks_at_horizon_samples():
    cuts = _pattern_cuts(_hertzian(), az_elev_deg=0.0, elev_az_deg=0.0)
    el = np.asarray(cuts["elevation"])
    assert el[0] == pytest.approx(10 * math.log10(1.5), abs=1e-3)


def test_ground_floors_below_horizon_samples():
    cuts = _pattern_cuts(_hertzian(h=1.0, ground=True), 0.0, 0.0)
    el = np.asarray(cuts["elevation"])
    n = cuts["n_dir"]
    below = el[n // 2 + 1 : n - 1]  # t ∈ (180°, 360°) dips below the horizon
    assert np.all(below == cuts["floor_dbi"])
    above = el[1 : n // 2]
    assert np.all(above > cuts["floor_dbi"])


def test_pec_limit_vertical_dipole_gains_over_free_space():
    """Over a near-PEC ground (huge εr) a low vertical Hertzian dipole gains
    ~+6 dB at low elevation from the in-phase image — the classic result.
    Uses raw _mag2_at_directions so no norm assumptions intrude."""
    free = _hertzian(h=0.01)
    pec = _hertzian(h=0.01, ground=True)
    pec["ground_eps_r"] = 1e10
    pec["ground_eps_im"] = 0.0
    rhat = np.array([[math.cos(math.radians(5)), 0.0, math.sin(math.radians(5))]])
    m_free = _mag2_at_directions(free, rhat)[0]
    m_pec = _mag2_at_directions(pec, rhat)[0]
    assert 10 * math.log10(m_pec / m_free) == pytest.approx(6.0, abs=0.1)


def test_ground_reflection_survives_the_zenith_sample():
    """The elevation cut hits zenith exactly (i=45 → t=90°, where float
    cos(π/2) ≈ 6e-17), and there the h/v polarisation basis degenerates.
    A guard that only protects the division (s_safe) shrinks ĥ, v̂ to ~0 and
    silently drops the reflected wave at that one sample — a visible kink in
    the live chart. At normal incidence ρ_v = −ρ_h makes the reflection
    basis-independent, so the correct value is the closed-form two-ray
    result |e^{jkh} + ρ_h(0)·e^{−jkh}|²·dl² for a horizontal dipole."""
    dl, h = 0.01, 1.0
    out = _hertzian(dl=dl, h=h, ground=True)
    out["wires"][0]["knot_positions"] = [[0.0, 0.0, h], [dl, 0.0, h]]  # x-directed
    k = out["k_meas_m_inv"]
    root = np.sqrt(out["ground_eps_r"] + 1j * out["ground_eps_im"])
    rho_h = (1 - root) / (1 + root)
    expect = dl * dl * abs(np.exp(1j * k * h) + rho_h * np.exp(-1j * k * h)) ** 2

    t = 2 * np.pi * 45 / 180  # the elevation cut's zenith sample direction
    zen = np.array([[np.cos(t), 0.0, np.sin(t)]])
    m_zen = _mag2_at_directions(out, zen)[0]
    assert m_zen == pytest.approx(expect, rel=1e-9)
    # Continuity: a hair off the pole (s just above any guard) must agree.
    near = np.array([[np.sin(1e-8), 0.0, np.cos(1e-8)]])
    assert _mag2_at_directions(out, near)[0] == pytest.approx(m_zen, rel=1e-6)


def test_cuts_none_without_norm_or_wires():
    out = _hertzian()
    out["directivity_norm"] = 0.0
    assert _pattern_cuts(out, 0.0, 0.0) is None
    out = _hertzian()
    out["wires"] = []
    assert _pattern_cuts(out, 0.0, 0.0) is None


def test_directivity_norm_unchanged_by_refactor(client: TestClient):
    """The norm quadrature now routes through _mag2_at_directions; a live
    solve's directivity_norm must still be a sane O(1) scalar and the peak
    dBi from the attached cuts must be physically reasonable for an invvee
    over soil (a few dBi)."""
    with client.websocket_connect("/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "geometry": "dipoles.invvee",
                    "measurement_freq_mhz": 28.47,
                    "momwire_model": "bspline",
                    "az_elev_deg": 30.0,
                    "elev_az_deg": 0.0,
                }
            )
        )
        result = json.loads(ws.receive_text())
    assert result["directivity_norm"] > 0
    cuts = result["cuts"]
    assert cuts["az_elev_deg"] == 30.0 and cuts["elev_az_deg"] == 0.0
    assert len(cuts["azimuth"]) == cuts["n_dir"] == 180
    assert len(cuts["elevation"]) == 180
    peak = max(max(cuts["azimuth"]), max(cuts["elevation"]))
    assert 0.0 < peak < 15.0


def test_cuts_endpoint_matches_solve_attached_cuts(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "geometry": "dipoles.invvee",
                    "measurement_freq_mhz": 28.47,
                    "momwire_model": "bspline",
                    "az_elev_deg": 15.0,
                    "elev_az_deg": 45.0,
                }
            )
        )
        result = json.loads(ws.receive_text())

    r = client.post(
        "/cuts", json={"solve": result, "az_elev_deg": 15.0, "elev_az_deg": 45.0}
    )
    assert r.status_code == 200
    assert r.json() == result["cuts"]

    # Different angles produce a different trace.
    r2 = client.post(
        "/cuts", json={"solve": result, "az_elev_deg": 40.0, "elev_az_deg": 45.0}
    )
    assert r2.json()["azimuth"] != result["cuts"]["azimuth"]


def test_cuts_endpoint_rejects_garbage(client: TestClient):
    assert client.post("/cuts", json={}).status_code == 400
    assert client.post("/cuts", json={"solve": {"wires": []}}).status_code == 400


def test_solve_cache_stays_angle_independent(client: TestClient):
    """Two solves differing only in cut angles must both carry correct cuts
    (the second is a cache hit — cuts are attached per-request, after the
    cache)."""
    base = {
        "geometry": "dipoles.invvee",
        "measurement_freq_mhz": 28.47,
        "momwire_model": "bspline",
    }
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({**base, "az_elev_deg": 10.0}))
        r1 = json.loads(ws.receive_text())
        ws.send_text(json.dumps({**base, "az_elev_deg": 35.0}))
        r2 = json.loads(ws.receive_text())
    assert r1["cuts"]["az_elev_deg"] == 10.0
    assert r2["cuts"]["az_elev_deg"] == 35.0
    assert r1["cuts"]["azimuth"] != r2["cuts"]["azimuth"]
    # The angles are blocklisted from the cache key, so the second request
    # is a genuine hit — a cut-dial drag must not shred the solve cache.
    assert r2["cache_hit"] is True


def test_solve_cache_key_ignores_cut_angles():
    from antennaknobs.web.server import _canonical_solve_key

    a = {"geometry": "dipoles.invvee", "az_elev_deg": 10.0, "elev_az_deg": 0.0}
    b = {"geometry": "dipoles.invvee", "az_elev_deg": 35.0, "elev_az_deg": 90.0}
    assert _canonical_solve_key(a) == _canonical_solve_key(b)


def test_mag2_directions_shape_generic():
    out = _hertzian()
    r1 = _mag2_at_directions(out, np.array([[0.0, 1.0, 0.0]]))
    r2 = _mag2_at_directions(out, np.stack([np.eye(3), np.eye(3)[::-1]]))  # (2, 3, 3)
    assert r1.shape == (1,) and r2.shape == (2, 3)
    assert server._CUT_N_DIR == 180  # the cut-trace sample-count contract


# ---- solve_id cuts cache + ws cuts transport (issue #551) ----

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


def test_solve_id_cuts_match_full_body(client: TestClient):
    """A solve response carries solve_id, and the ~100-byte id-only /cuts
    request returns byte-identical cuts to the stateless full-body path."""
    result = _ws_solve(client)
    solve_id = result.get("solve_id")
    assert isinstance(solve_id, str) and solve_id

    full = client.post(
        "/cuts", json={"solve": result, "az_elev_deg": 22.0, "elev_az_deg": 5.0}
    )
    by_id = client.post(
        "/cuts", json={"solve_id": solve_id, "az_elev_deg": 22.0, "elev_az_deg": 5.0}
    )
    assert full.status_code == 200 and by_id.status_code == 200
    assert by_id.json() == full.json()


def test_cuts_unknown_solve_id_is_404(client: TestClient):
    r = client.post(
        "/cuts",
        json={"solve_id": "0" * 32, "az_elev_deg": 0.0, "elev_az_deg": 0.0},
    )
    assert r.status_code == 404


def test_cuts_source_repopulates_from_solve_cache_hit(client: TestClient):
    """Eviction of the cuts source must heal on the next solve of the same
    request — the solve-cache HIT path re-remembers, no re-solve needed."""
    result = _ws_solve(client)
    server._CUTS_SRC_CACHE.pop(result["solve_id"], None)
    miss = client.post(
        "/cuts",
        json={"solve_id": result["solve_id"], "az_elev_deg": 1.0, "elev_az_deg": 2.0},
    )
    assert miss.status_code == 404

    again = _ws_solve(client)  # same request → cache hit → source repopulated
    assert again["cache_hit"] is True and again["solve_id"] == result["solve_id"]
    healed = client.post(
        "/cuts",
        json={"solve_id": result["solve_id"], "az_elev_deg": 1.0, "elev_az_deg": 2.0},
    )
    assert healed.status_code == 200


def test_ws_cuts_channel_matches_http(client: TestClient):
    """Cuts requested over the /ws sidecar match the HTTP endpoint, and the
    solve mailbox is untouched (a later solve on the same socket still
    works)."""
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(_SOLVE_REQ))
        result = json.loads(ws.receive_text())
        ws.send_text(
            json.dumps(
                {
                    "_kind": "cuts",
                    "solve_id": result["solve_id"],
                    "az_elev_deg": 40.0,
                    "elev_az_deg": 10.0,
                }
            )
        )
        msg = json.loads(ws.receive_text())
        # The socket still solves after a cuts message.
        ws.send_text(json.dumps({**_SOLVE_REQ, "az_elev_deg": 20.0}))
        result2 = json.loads(ws.receive_text())

    assert msg["_kind"] == "cuts"
    assert msg["ok"] is True
    assert msg["solve_id"] == result["solve_id"]
    assert msg["az_elev_deg"] == 40.0 and msg["elev_az_deg"] == 10.0
    http = client.post(
        "/cuts", json={"solve": result, "az_elev_deg": 40.0, "elev_az_deg": 10.0}
    )
    assert msg["cuts"] == http.json()
    assert result2["cuts"]["az_elev_deg"] == 20.0


def test_ws_cuts_unknown_id_answers_ok_false(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "_kind": "cuts",
                    "solve_id": "f" * 32,
                    "az_elev_deg": 0.0,
                    "elev_az_deg": 0.0,
                }
            )
        )
        msg = json.loads(ws.receive_text())
    assert msg["_kind"] == "cuts" and msg["ok"] is False and "cuts" not in msg


def test_ws_cuts_junk_angles_answers_ok_false(client: TestClient):
    """Garbage angles must produce ok:false, not a torn-down socket."""
    result = _ws_solve(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "_kind": "cuts",
                    "solve_id": result["solve_id"],
                    "az_elev_deg": "garbage",
                    "elev_az_deg": None,
                }
            )
        )
        msg = json.loads(ws.receive_text())
        # Socket survives for real work.
        ws.send_text(json.dumps(_SOLVE_REQ))
        again = json.loads(ws.receive_text())
    assert msg["ok"] is False
    assert "wires" in again
