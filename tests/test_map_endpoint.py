"""The workbench's two-knob map, server side (docs/design/sweep-framework-map.md,
unit 1): ``/analyses`` offers a single-grid map with the CLI's own axes, and
``POST /map`` streams its grid, one record per node.

The oracle: ``/map`` on a map ``/analyses`` served equals ``antennaknobs
analyze``'s grid (`analysis_run.solve_map`) bit for bit, node by node, at a
ground named on BOTH sides (the note measured a 13 % mismatch when the CLI's
default ground and the request's differ), with the record count asserted so
the gate cannot pass on an empty stream. The full gate is dipoles.invvee's
own 825-node tuning map; a 3 × 2 map of the same design runs on every PR.
"""

from __future__ import annotations

import json
import socket
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs.cli import cli, get_builder
from antennaknobs.web import analyses_offer as ao
from antennaknobs.web import cost, server
from antennaknobs.web.analyses_offer import builder_for
from antennaknobs.web.examples import example_for

INVVEE = "dipoles.invvee"
CLI_GROUND = "finite:13,0.005"
# The same ground, as the workbench's request says it: Sommerfeld over the
# request's soil, whose default is 13 / 0.005.
REQ_GROUND = {"ground": True, "ground_model": "sommerfeld"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(server.app)


def _records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _invvee_cls():
    return type(get_builder(INVVEE)())


def _served(client, name: str, geometry: str = INVVEE) -> dict:
    r = client.post("/analyses", json={"geometry": geometry})
    assert r.status_code == 200, r.text
    (entry,) = [a for a in r.json()["analyses"] if a["name"] == name]
    return entry["workbench"]


def _req(**over) -> dict:
    """A workbench solve request at invvee's defaults: every knob, both
    frequencies, B-spline at the design's own density."""
    cls = example_for(INVVEE).builder_cls
    b = builder_for(cls, {"geometry": INVVEE, "variant": "default"})
    knobs = {
        k: v
        for k, v in an._params(b).items()
        if k not in ("ui_params", "nominal_nsegs", "freq", "design_freq")
    }
    return {
        "geometry": INVVEE,
        "variant": "default",
        **knobs,
        "design_freq_mhz": b.design_freq,
        "measurement_freq_mhz": b.freq,
        "solver": "momwire",
        "momwire_model": "bspline",
        "n_per_wire": b.nominal_nsegs,
        **over,
    }


def _map_body(w: dict, **over) -> dict:
    return {
        **_req(**REQ_GROUND),
        "x": {"param": w["x"]["param"], "values": w["x"]["values"]},
        "y": {"param": w["y"]["param"], "values": w["y"]["values"]},
        **over,
    }


def _cli_map(monkeypatch, tmp_path, name: str):
    runs: list = []
    inner = ar.run

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        runs.append(out)
        return out

    monkeypatch.setattr(ar, "run", wrapped)
    cli(["analyze", "--builder", INVVEE, "--analysis", name, "--ground", CLI_GROUND,
         "--fn", str(tmp_path / "map.png")])  # fmt: skip
    ((_label, grid),) = runs[-1]["maps"].items()
    return grid


def _oracle(monkeypatch, tmp_path, client, name: str) -> int:
    xs, ys, z = _cli_map(monkeypatch, tmp_path, name)
    w = _served(client, name)
    assert w["runs"] is True and w["kind"] == "map"
    # The served axes ARE the CLI's grid (`analysis_run.knob_xs`).
    assert w["x"]["values"] == [float(x) for x in xs]
    assert w["y"]["values"] == [float(y) for y in ys]
    r = client.post("/map", json=_map_body(w))
    assert r.status_code == 200, r.text
    *points, done = _records(r.text)
    n = len(xs) * len(ys)
    assert len(points) == n and done == {"done": True, "solver": "momwire", "points": n}
    got = np.full(z.shape, complex(np.nan, np.nan))
    for p in points:
        assert "error" not in p, p
        got[p["j"], p["i"]] = complex(p["z_re"], p["z_im"])
    # Bit for bit, every node (NaN never equals, so a missing node fails).
    assert np.array_equal(got.real, z.real) and np.array_equal(got.imag, z.imag)
    # y outer, x inner: the CLI's table order.
    assert [(p["j"], p["i"]) for p in points] == [
        (j, i) for j in range(len(ys)) for i in range(len(xs))
    ]
    return n


# ── the offer ──────────────────────────────────────────────────────────────


def test_invvees_tuning_map_is_offered_with_the_clis_axes(client):
    w = _served(client, "tuning map")
    b = get_builder(INVVEE)()
    sx, sy = ar.find(b, "tuning map").sweeps
    assert w["runs"] is True and w["kind"] == "map"
    assert w["x"] == {
        "param": "length_factor",
        "values": [float(x) for x in ar.knob_xs(sx, b, "length_factor")],
        "log": False,
        "lo": 0.9,
        "hi": 1.06,
        "points": 33,
        "spacing": "lin",
    }
    assert w["y"]["param"] == "angle_deg" and len(w["y"]["values"]) == 25
    assert (w["y"]["lo"], w["y"]["hi"]) == (0.0, 60.0)
    assert w["refs"] == {"r": [50.0, 75.0], "x": [0.0], "swr": None}
    assert w["views"] == ["Map"]
    assert w["engines"] is None and w["grounds"] is None
    assert w["note"] is None
    # A local workbench bounds neither the points nor the time.
    assert w["limit"] is None


def test_hosted_the_offer_carries_the_map_cap_and_budget(client, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    w = _served(client, "tuning map")
    assert w["limit"] == {"points": 1000, "seconds": 120}


LF = an.Sweep("length_factor", values=(0.95, 0.975, 1.0))
ANG = an.Sweep("angle_deg", values=(15.0, 30.0))


@pytest.mark.parametrize(
    ("analysis", "why"),
    [
        (
            an.Analysis(
                "m",
                (LF, ANG),
                views=(an.Map(),),
                cross=an.Cross(engines=("momwire:bspline", "nec5")),
            ),
            "a map with a cross over engines: the workbench draws one grid",
        ),
        (
            an.Analysis(
                "m", (an.Sweep(an.FREQUENCY, 27, 29, points=3), ANG), views=(an.Map(),)
            ),
            "a map with a frequency axis",
        ),
        (
            an.Analysis(
                "m", (LF, an.Sweep(an.DENSITY, values=(8, 12))), views=(an.Map(),)
            ),
            "a map axis or family over the density knob",
        ),
        (
            an.Analysis("m", (LF, ANG), views=(an.Table(),)),
            "the Table view of a map: the workbench draws the Map view",
        ),
    ],
)
def test_what_a_map_cannot_be_here_is_greyed_with_its_reason(
    monkeypatch, client, analysis, why
):
    monkeypatch.setattr(_invvee_cls(), "build_analyses", lambda self: [analysis])
    w = _served(client, "m")
    assert w["runs"] is False
    assert why in w["why"]


def test_a_maps_table_view_is_left_out_by_name(monkeypatch, client):
    a = an.Analysis("m", (LF, ANG), views=(an.Map(), an.Table()))
    monkeypatch.setattr(_invvee_cls(), "build_analyses", lambda self: [a])
    w = _served(client, "m")
    assert w["runs"] is True and w["views"] == ["Map"]
    assert w["note"].startswith("left out: the Table view of a map")
    assert ao.gaps(a) == []


def test_a_refs_swr_is_served(monkeypatch, client):
    a = an.Analysis("m", (LF, ANG), views=(an.Map(),), references=an.Ref(swr=2.0))
    monkeypatch.setattr(_invvee_cls(), "build_analyses", lambda self: [a])
    assert _served(client, "m")["refs"] == {"r": [], "x": [], "swr": 2.0}


# ── the oracle ─────────────────────────────────────────────────────────────


def test_a_small_map_is_the_clis_grid_bit_for_bit(monkeypatch, tmp_path, client):
    a = an.Analysis("small map", (LF, ANG), views=(an.Map(),))
    monkeypatch.setattr(_invvee_cls(), "build_analyses", lambda self: [a])
    assert _oracle(monkeypatch, tmp_path, client, "small map") == 6


@pytest.mark.antenna_computation_check
def test_invvees_tuning_map_is_the_clis_grid_bit_for_bit(monkeypatch, tmp_path, client):
    """The note's gate: all 825 nodes, ground named on both sides."""
    assert _oracle(monkeypatch, tmp_path, client, "tuning map") == 825


# ── the endpoint ───────────────────────────────────────────────────────────


def _stub(monkeypatch, delay: float = 0.0) -> list:
    calls: list = []

    def stub(req, cancel=None):
        calls.append((req["length_factor"], req["angle_deg"]))
        if delay:
            time.sleep(delay)
        return complex(req["length_factor"] * 50, req["angle_deg"]), None, None

    monkeypatch.setattr(server, "_solve_z_only", stub)
    return calls


AXES = {
    "x": {"param": "length_factor", "values": [0.9, 1.0, 1.1]},
    "y": {"param": "angle_deg", "values": [0, 30, 60]},
}


def test_nodes_stream_y_outer_and_resume_from_a_flat_index(client, monkeypatch):
    calls = _stub(monkeypatch)
    *points, done = _records(
        client.post("/map", json={**_req(), **AXES, "from": 5}).text
    )
    assert [(p["i"], p["j"]) for p in points] == [(2, 1), (0, 2), (1, 2), (2, 2)]
    assert calls == [(1.1, 30.0), (0.9, 60.0), (1.0, 60.0), (1.1, 60.0)]
    assert points[0]["z_re"] == 1.1 * 50 and points[0]["z_im"] == 30.0
    assert done == {"done": True, "solver": "momwire", "points": 9}


def test_a_failed_node_is_named_and_the_map_goes_on(client, monkeypatch):
    def flaky(req, cancel=None):
        if req["length_factor"] == 1.0:
            raise RuntimeError("degenerate")
        return complex(50, 0), None, None

    monkeypatch.setattr(server, "_solve_z_only", flaky)
    *points, done = _records(client.post("/map", json={**_req(), **AXES}).text)
    assert len(points) == 9 and done["done"] is True
    bad = [p for p in points if "error" in p]
    assert [(p["i"], p["j"]) for p in bad] == [(1, 0), (1, 1), (1, 2)]
    assert bad[0]["error"].startswith("RuntimeError: ")


@pytest.mark.parametrize(
    ("over", "words"),
    [
        ({"x": {"param": "n_per_wire", "values": [8, 12]}}, "the density is a ladder"),
        ({"x": {"param": "nope", "values": [1.0]}}, "x: "),
        ({"y": {"param": "length_factor", "values": [1.0]}}, "both length_factor"),
        ({"x": {"param": "length_factor", "values": []}}, "x: no values"),
        ({"from": 10}, "from: a node index in 0..9"),
        ({"from": -1}, "from: "),
        ({"y": None}, "y: {param, values}"),
    ],
)
def test_a_bad_map_is_a_422_before_any_solve(client, monkeypatch, over, words):
    calls = _stub(monkeypatch)
    r = client.post("/map", json={**_req(), **AXES, **over})
    assert r.status_code == 422, r.text
    assert words in r.json()["detail"]
    assert calls == []


def test_hosted_a_map_is_admitted_against_its_own_cap(client, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    calls = _stub(monkeypatch)
    # Over the sweep cap (500), inside the map's (1000): invvee's own map runs.
    big = {
        "x": {"param": "length_factor", "values": [0.9 + 0.005 * i for i in range(33)]},
        "y": {"param": "angle_deg", "values": [2.5 * j for j in range(25)]},
    }
    assert server._MAX_SWEEP_POINTS < 825 <= cost.MAX_MAP_POINTS == 1000
    r = client.post("/map", json={**_req(), **big})
    assert r.status_code == 200 and len(calls) == 825
    monkeypatch.setattr(cost, "MAX_MAP_POINTS", 824)
    r = client.post("/map", json={**_req(), **big})
    assert r.status_code == 413
    assert r.json()["detail"] == (
        "A map of 825 points is over the live limit of 824. Reduce the points "
        "on x or y."
    )


def test_hosted_the_budget_keeps_the_partial_map_and_says_so(client, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    monkeypatch.setattr(server, "_MAX_SWEEP_SECONDS", 0)
    calls = _stub(monkeypatch)
    *points, done = _records(client.post("/map", json={**_req(), **AXES}).text)
    assert len(calls) == 1 and [(p["i"], p["j"]) for p in points] == [(0, 0)]
    assert done == {
        "done": True,
        "solver": "momwire",
        "points": 9,
        "stopped": "time",
        "time_budget_s": 0,
    }


def test_map_points_carry_no_generation(client, monkeypatch):
    """A knob drag's live solve supersedes every turn of an older generation;
    a map's turns carry none, so dragging x or y never ends the map."""
    _stub(monkeypatch)
    seen: list = []
    inner = server._solve_turn

    def spy(req, session, kind, gen):
        seen.append((kind, gen))
        return inner(req, session, kind, gen)

    monkeypatch.setattr(server, "_solve_turn", spy)
    client.post("/map", json={**_req(), **AXES, "_session": "s", "_gen": 7})
    assert seen == [("map", None)] * 9


def test_a_client_that_goes_away_stops_the_map(monkeypatch):
    """Stop and closing the chart abort the fetch: the server stops at the
    next node, not at the end of the grid (a real socket: TestClient buffers
    the whole response, so it never disconnects mid-stream)."""
    import uvicorn

    calls = _stub(monkeypatch, delay=0.2)
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
        body = json.dumps(
            {
                **_req(),
                "x": {
                    "param": "length_factor",
                    "values": [0.9 + 0.01 * i for i in range(5)],
                },
                "y": {"param": "angle_deg", "values": [0, 10, 20, 30]},
            }
        ).encode()
        with socket.create_connection(("127.0.0.1", port), timeout=30) as conn:
            conn.sendall(
                b"POST /map HTTP/1.1\r\nHost: x\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
            got = b""
            while b'"i": 0' not in got:
                chunk = conn.recv(4096)
                assert chunk, got
                got += chunk
        # The whole grid would take 4 s; give the server that long to show
        # it stopped instead.
        time.sleep(4.0)
        assert 1 <= len(calls) <= 4, calls
    finally:
        srv.should_exit = True
        t.join(timeout=10)
