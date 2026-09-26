"""POST /param_sweep: the Z-vs-parameter view's backend
(docs/design/z-vs-param-view.md).

One streaming endpoint over the density (``n_per_wire``) or any numeric design
knob, solving each point on the request's own engine; ``/converge`` is its thin
alias. Plus the pure half in ``web/param_sweep.py``: which parameters sweep,
how values coerce, and the gap-fed density advisory.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import server
from antennaknobs.web.param_sweep import (
    DENSITY,
    ParamSweepError,
    gap_fed_advisory,
    gap_feed_wire,
    request_at,
    sweep_values,
)

DIPOLE = {
    "geometry": "dipoles.invvee",
    "variant": "dipole",
    "measurement_freq_mhz": 28.47,
    "design_freq_mhz": 28.47,
    "momwire_model": "bspline",
    "n_per_wire": 9,
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(server.app)


def _records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# --- the pure half -----------------------------------------------------------


def test_density_values_are_positive_integers():
    assert sweep_values(DIPOLE, DENSITY, [8, 11.6, 68]) == [8, 12, 68]
    with pytest.raises(ParamSweepError):
        sweep_values(DIPOLE, DENSITY, [0, 5])


def test_a_float_knob_keeps_its_values():
    assert sweep_values(DIPOLE, "length_factor", [0.9, 1]) == [0.9, 1.0]


def test_an_int_knob_rounds_to_integers():
    req = {"geometry": "beams.yagi"}
    assert sweep_values(req, "n_directors", [1, 2.4, 2.6]) == [1, 2, 3]


@pytest.mark.parametrize("param", ["nope", "freq", "design_freq", "", None])
def test_a_non_knob_is_refused_by_name(param):
    with pytest.raises(ParamSweepError) as e:
        sweep_values(DIPOLE, param, [1.0])
    if param == "nope":
        # The refusal lists what CAN be swept, density first.
        assert "sweepable: n_per_wire, " in str(e.value)
        assert "length_factor" in str(e.value)


@pytest.mark.parametrize("bad", [[float("nan")], ["x"], [True], "1,2"])
def test_non_numeric_values_are_refused(bad):
    with pytest.raises(ParamSweepError):
        sweep_values(DIPOLE, "length_factor", bad)


def test_request_at_overrides_one_field_and_nothing_else():
    out = request_at(DIPOLE, "length_factor", 1.01)
    assert out["length_factor"] == 1.01
    assert {k: v for k, v in out.items() if k != "length_factor"} == DIPOLE
    assert "length_factor" not in DIPOLE  # the base request is untouched


def test_the_catalog_dipole_is_gap_fed():
    # A 0.1 m feed wire against 0.33 m segments at N = 8 (λ/4 at 28.47 MHz
    # over 8).
    feed, segment = gap_feed_wire(DIPOLE, 8)
    assert feed == pytest.approx(0.1)
    assert segment == pytest.approx(0.25 * 299.792458 / 28.47 / 8, rel=1e-3)


def test_a_sweep_starting_fine_enough_is_not_gap_fed():
    # From N = 68 up every segment is under 0.04 m: the feed wire is
    # already meshed like its neighbours.
    assert gap_feed_wire(DIPOLE, 68) is None


def test_a_quad_fed_on_a_whole_side_is_not_gap_fed():
    assert gap_feed_wire({"geometry": "loops.quad"}, 8) is None


LADDER = [8, 12, 17, 24, 34, 48, 68]


@pytest.mark.parametrize(
    ("req", "solver", "fires"),
    [
        ({**DIPOLE, "momwire_model": "sinusoidal"}, "momwire", True),
        ({**DIPOLE, "solver": "nec2"}, "nec2", True),
        ({**DIPOLE, "solver": "pynec"}, "pynec", True),
        (DIPOLE, "momwire", False),  # B-spline: a point gap
        ({**DIPOLE, "solver": "nec5"}, "nec5", False),
        (
            {**DIPOLE, "model_options": {"feed_model": "segment"}},
            "momwire",
            True,
        ),
    ],
)
def test_gap_fed_advisory_needs_a_delta_gap_engine(req, solver, fires):
    note = gap_fed_advisory(req, DENSITY, LADDER, solver)
    assert (note is not None) is fires
    if fires:
        assert note["category"] == "DeltaGapFeedConvergence"
        assert "0.10 m feed wire, shorter than one segment at N = 8" in note["text"]


def test_gap_fed_advisory_is_for_density_sweeps_only():
    req = {**DIPOLE, "momwire_model": "sinusoidal"}
    assert gap_fed_advisory(req, "length_factor", [0.9, 1.0], "momwire") is None


def test_no_gap_advisory_on_a_quad():
    req = {"geometry": "loops.quad", "momwire_model": "sinusoidal"}
    assert gap_fed_advisory(req, DENSITY, LADDER, "momwire") is None


# --- the endpoint ------------------------------------------------------------


def test_a_knob_sweep_streams_one_record_per_value_then_done(client):
    values = [0.95, 1.0]
    r = client.post(
        "/param_sweep", json={**DIPOLE, "param": "length_factor", "values": values}
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    *points, done = _records(r.text)
    assert done == {"done": True, "solver": "momwire"}
    assert [p["value"] for p in points] == values
    assert all(p["param"] == "length_factor" for p in points)
    # The knob reached the geometry: a longer dipole has more reactance.
    assert points[1]["z_im"] > points[0]["z_im"] + 5


def test_each_point_overrides_only_the_swept_field(client, monkeypatch):
    """The measurement frequency and the engine stay the request's: the
    point request differs from the base in the swept field alone."""
    seen = []

    def fake(req, cancel=None):
        seen.append(dict(req))
        return complex(50, 0), None

    monkeypatch.setattr(server, "_solve_z_only", fake)
    base = {**DIPOLE, "solver": "momwire", "length_factor": 0.97}
    r = client.post(
        "/param_sweep", json={**base, "param": "length_factor", "values": [0.9, 1.1]}
    )
    assert r.status_code == 200
    assert [s["length_factor"] for s in seen] == [0.9, 1.1]
    for s in seen:
        assert {k: v for k, v in s.items() if k != "length_factor"} == {
            k: v for k, v in base.items() if k != "length_factor"
        }


def test_a_density_sweep_is_the_old_convergence_sweep(client):
    ns = [5, 7]
    new = _records(
        client.post(
            "/param_sweep", json={**DIPOLE, "param": DENSITY, "values": ns}
        ).text
    )
    old = _records(client.post("/converge", json={**DIPOLE, "n_values": ns}).text)
    # The alias keeps its record shape, and the numbers are the same solves.
    assert [o["n_per_wire"] for o in old[:-1]] == ns
    assert [(n["z_re"], n["z_im"]) for n in new[:-1]] == [
        (o["z_re"], o["z_im"]) for o in old[:-1]
    ]
    assert old[-1] == {"done": True, "solver": "momwire"}


def test_the_closing_record_carries_the_gap_fed_advisory(client):
    req = {**DIPOLE, "momwire_model": "sinusoidal", "param": DENSITY, "values": [8]}
    done = _records(client.post("/param_sweep", json=req).text)[-1]
    assert [a["category"] for a in done["advisories"]] == ["DeltaGapFeedConvergence"]


def test_an_unknown_param_is_422_before_any_solve(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("solved")

    monkeypatch.setattr(server, "_solve_z_only", boom)
    r = client.post("/param_sweep", json={**DIPOLE, "param": "nope", "values": [1]})
    assert r.status_code == 422
    assert "sweepable" in r.json()["detail"]


def test_empty_values_return_only_done(client):
    r = client.post(
        "/param_sweep", json={**DIPOLE, "param": "length_factor", "values": []}
    )
    assert _records(r.text) == [{"done": True, "solver": "momwire"}]


def test_a_failed_point_is_reported_and_the_sweep_goes_on(client, monkeypatch):
    def flaky(req, cancel=None):
        if req["length_factor"] == 0.9:
            raise RuntimeError("degenerate")
        return complex(60, 1), None

    monkeypatch.setattr(server, "_solve_z_only", flaky)
    recs = _records(
        client.post(
            "/param_sweep",
            json={**DIPOLE, "param": "length_factor", "values": [0.9, 1.0]},
        ).text
    )
    assert recs[0]["error"].startswith("RuntimeError: ")
    assert recs[0]["value"] == 0.9
    assert recs[1]["z_re"] == 60


def test_an_over_long_sweep_is_refused_when_hosted(client, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    values = [1.0] * (server._MAX_SWEEP_POINTS + 1)
    r = client.post(
        "/param_sweep", json={**DIPOLE, "param": "length_factor", "values": values}
    )
    assert r.status_code == 413
    assert "parameter sweep" in r.json()["detail"]


def test_a_client_that_goes_away_stops_the_sweep(monkeypatch):
    """The view's Stop aborts its fetch; the server must see the disconnect
    and stop solving, not run out the ladder. A real socket (TestClient
    buffers the whole response, so it can never disconnect mid-stream) and a
    slow stub engine: far fewer solves than points."""
    import socket
    import threading
    import time

    import uvicorn

    calls = []

    def slow(req, cancel=None):
        calls.append(req["length_factor"])
        time.sleep(0.2)
        return complex(50, 0), None

    monkeypatch.setattr(server, "_solve_z_only", slow)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(
        uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning")
    )
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    try:
        deadline = time.time() + 20
        while not srv.started and time.time() < deadline:
            time.sleep(0.05)
        values = [round(0.9 + 0.01 * i, 2) for i in range(20)]
        body = json.dumps(
            {**DIPOLE, "param": "length_factor", "values": values}
        ).encode()
        # A raw socket (stdlib only): send the POST, read until the first
        # record has arrived, then hang up — the browser's abort.
        with socket.create_connection(("127.0.0.1", port), timeout=30) as conn:
            conn.sendall(
                b"POST /param_sweep HTTP/1.1\r\nHost: x\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
            got = b""
            while b'"value": 0.9' not in got:
                chunk = conn.recv(4096)
                assert chunk, got
                got += chunk
        # The whole ladder would take 4 s; give the server that long to show
        # it stopped instead.
        time.sleep(4.0)
        assert 1 <= len(calls) <= 4, calls
    finally:
        srv.should_exit = True
        t.join(timeout=10)
