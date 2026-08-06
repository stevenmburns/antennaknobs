"""Server side of adaptive sweep refinement (issue #744).

Two claims, both structural rather than numeric:

  - a refinement request must not kill the base sweep it is refining. It
    rides the same /sweep endpoint, so without its own lane kind
    lane.SAME_KIND_SUPERSEDES would cancel the in-flight base stream
    regardless of generation — the failure mode would be "refinement
    deletes the curve".
  - a refinement request re-issued for the same design and frequencies must
    perform ZERO engine solves. Counted at the engine, not inferred from
    latency.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import httpx2
from fastapi.testclient import TestClient

from antennaknobs.web import server
from antennaknobs.web.lane import PRIORITY, SAME_KIND_SUPERSEDES


class _Counter:
    """Counts engine sweep calls and the frequencies they were asked for."""

    def __init__(self) -> None:
        self.calls = 0
        self.freqs: list[float] = []


def _counting_example(counter: _Counter, dwell_s: float = 0.0):
    def momwire_sweep(req, freqs, cancel=None):
        counter.calls += 1
        counter.freqs.extend(freqs)
        if dwell_s:
            time.sleep(dwell_s)
        if cancel is not None:
            cancel.raise_if_cancelled()
        return [50.0] * len(freqs), [0.0] * len(freqs)

    return SimpleNamespace(
        multi_feed=False,
        count_basis=lambda req: 100,
        momwire_sweep=momwire_sweep,
    )


def _sweep_lines(resp):
    return [line for line in resp.text.splitlines() if line.strip()]


# ---- lane treatment --------------------------------------------------------


def test_refine_is_its_own_lane_kind_that_never_supersedes():
    # The two properties that make refinement safe to issue while a sweep is
    # in flight, pinned as data so a future edit to either table trips here.
    assert PRIORITY["sweep_refine"] > PRIORITY["sweep"]
    assert "sweep_refine" not in SAME_KIND_SUPERSEDES
    assert "sweep" in SAME_KIND_SUPERSEDES  # the trap this avoids


def test_refinement_does_not_cancel_an_in_flight_base_sweep(monkeypatch):
    counter = _Counter()
    first_point_done = threading.Event()
    release = threading.Event()

    fake = _counting_example(counter)
    inner = fake.momwire_sweep

    def gated_sweep(req, freqs, cancel=None):
        out = inner(req, freqs, cancel=cancel)
        if not req.get("_refine"):
            # Hold the base sweep's first chunk open until the refinement
            # request has been issued, so the two genuinely overlap.
            first_point_done.set()
            release.wait(5)
        return out

    fake.momwire_sweep = gated_sweep
    monkeypatch.setitem(server.EXAMPLES, "fake.refine", fake)

    base = {
        "geometry": "fake.refine",
        "_session": "tab-R",
        "_gen": 7,
        "freqs_mhz": [14.0, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7],
    }
    refine = {
        "geometry": "fake.refine",
        "_session": "tab-R",
        "_gen": 7,  # same generation: refinement of THIS design state
        "_refine": True,
        "freqs_mhz": [14.05, 14.15],
    }

    async def main():
        transport = httpx2.ASGITransport(app=server.app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://refine-test"
        ) as c:
            base_task = asyncio.create_task(c.post("/sweep", json=base))
            await asyncio.wait_for(asyncio.to_thread(first_point_done.wait), 5)
            refine_task = asyncio.create_task(c.post("/sweep", json=refine))
            await asyncio.sleep(0.05)  # let the refine turn queue behind
            release.set()
            return await asyncio.wait_for(asyncio.gather(base_task, refine_task), 10)

    base_resp, refine_resp = asyncio.run(asyncio.wait_for(main(), timeout=20))
    assert base_resp.status_code == 200 and refine_resp.status_code == 200
    # Every planned point of the base sweep survived — a same-kind
    # supersession would have truncated the stream here.
    assert len(_sweep_lines(base_resp)) == 8 + 1
    assert len(_sweep_lines(refine_resp)) == 2 + 1


def test_a_newer_generation_still_supersedes_refinement(monkeypatch):
    # Refinement opts out of same-kind supersession, NOT out of the
    # generation rule: a knob drag (a newer generation on the session) must
    # still cut an in-flight refinement off at its next chunk.
    counter = _Counter()
    refining = threading.Event()

    fake = _counting_example(counter)
    inner = fake.momwire_sweep

    def gated_sweep(req, freqs, cancel=None):
        if req.get("_refine"):
            refining.set()
            deadline = time.time() + 5
            while cancel is not None and not cancel.cancelled:
                if time.time() > deadline:
                    raise AssertionError("never preempted by the newer generation")
                time.sleep(0.005)
            cancel.raise_if_cancelled()
        return inner(req, freqs, cancel=cancel)

    fake.momwire_sweep = gated_sweep
    monkeypatch.setitem(server.EXAMPLES, "fake.refgen", fake)

    stale = {
        "geometry": "fake.refgen",
        "_session": "tab-S",
        "_gen": 3,
        "_refine": True,
        "freqs_mhz": [14.0, 14.1, 14.2, 14.3],
    }
    newer = {
        "geometry": "fake.refgen",
        "_session": "tab-S",
        "_gen": 9,
        "freqs_mhz": [21.0],
    }

    async def main():
        transport = httpx2.ASGITransport(app=server.app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://refine-test"
        ) as c:
            stale_task = asyncio.create_task(c.post("/sweep", json=stale))
            await asyncio.wait_for(asyncio.to_thread(refining.wait), 5)
            newer_resp = await c.post("/sweep", json=newer)
            return await asyncio.wait_for(stale_task, 10), newer_resp

    stale_resp, newer_resp = asyncio.run(asyncio.wait_for(main(), timeout=20))
    assert newer_resp.status_code == 200
    assert len(_sweep_lines(newer_resp)) == 1 + 1
    # The stale refinement was cut off: not all four points reached the wire.
    assert stale_resp.status_code == 200
    assert len(_sweep_lines(stale_resp)) < 4 + 1


# ---- per-frequency solve cache --------------------------------------------


def test_second_identical_refinement_solves_nothing(monkeypatch):
    counter = _Counter()
    monkeypatch.setitem(server.EXAMPLES, "fake.cache", _counting_example(counter))
    design = {"geometry": "fake.cache", "_session": "tab-C"}
    refine = {**design, "_refine": True, "freqs_mhz": [14.05, 14.15, 14.25]}
    with TestClient(server.app) as c:
        base = c.post("/sweep", json={**design, "freqs_mhz": [14.0, 14.1, 14.2]})
        assert base.status_code == 200
        first = c.post("/sweep", json=refine)
        assert first.status_code == 200
        solved_after_first = counter.calls
        assert counter.freqs.count(14.05) == 1

        second = c.post("/sweep", json=refine)

    assert second.status_code == 200
    # Same points on the wire, none of them recomputed.
    assert _sweep_lines(second) == _sweep_lines(first)
    assert counter.calls == solved_after_first
    assert counter.freqs.count(14.05) == 1


def test_refinement_reuses_the_base_sweep_points_it_overlaps(monkeypatch):
    # A refinement plan that happens to include a frequency the base sweep
    # already solved must not re-solve it: every sweep WRITES the cache.
    counter = _Counter()
    monkeypatch.setitem(server.EXAMPLES, "fake.overlap", _counting_example(counter))
    design = {"geometry": "fake.overlap", "_session": "tab-O"}
    with TestClient(server.app) as c:
        c.post("/sweep", json={**design, "freqs_mhz": [21.0, 21.1, 21.2]})
        before = counter.calls
        r = c.post(
            "/sweep",
            json={**design, "_refine": True, "freqs_mhz": [21.0, 21.05, 21.1]},
        )
    assert r.status_code == 200
    assert len(_sweep_lines(r)) == 3 + 1
    assert counter.freqs.count(21.0) == 1  # solved once, by the base sweep
    assert counter.freqs.count(21.05) == 1
    assert counter.calls == before + 1  # one chunk, for the one new freq


def test_a_base_sweep_never_reads_the_cache(monkeypatch):
    # Deliberate asymmetry (see _SWEEP_Z_CACHE): the primary curve is always
    # re-solved, so a stale entry can never survive in it.
    counter = _Counter()
    monkeypatch.setitem(server.EXAMPLES, "fake.fresh", _counting_example(counter))
    design = {"geometry": "fake.fresh", "_session": "tab-F", "freqs_mhz": [28.0]}
    with TestClient(server.app) as c:
        c.post("/sweep", json=design)
        c.post("/sweep", json=design)
    assert counter.freqs.count(28.0) == 2


def test_cache_key_ignores_metadata_but_not_physics():
    key = server._sweep_design_key
    base = {"geometry": "dipoles.invvee", "freqs_mhz": [14.0], "base": 7.0}
    # Which frequencies were asked for is the other half of the cache key,
    # never part of the design half.
    assert key(base) == key({**base, "freqs_mhz": [21.0, 21.1]})
    # Refinement/lane/cut metadata is blocklisted, so refinement lands on the
    # same entries a base sweep wrote.
    assert key(base) == key(
        {**base, "_refine": True, "_gen": 12, "_session": "x", "az_elev_deg": 40.0}
    )
    # Anything physical invalidates — including a field nobody enumerated.
    assert key(base) != key({**base, "base": 15.0})
    assert key(base) != key({**base, "future_physics_knob": 1})


def test_cache_is_lru_bounded(monkeypatch):
    monkeypatch.setattr(server, "_SWEEP_Z_CACHE_MAX", 4)
    monkeypatch.setattr(server, "_SWEEP_Z_CACHE", type(server._SWEEP_Z_CACHE)())
    for i in range(10):
        server._sweep_z_put("design", 14.0 + i, (50.0, 0.0, None, None))
    assert len(server._SWEEP_Z_CACHE) == 4
    # The four most recent survived; the oldest were evicted.
    assert server._sweep_z_get("design", 23.0) is not None
    assert server._sweep_z_get("design", 14.0) is None
    # Reading refreshes recency, so a re-read entry outlives newer arrivals.
    server._sweep_z_get("design", 20.0)
    for i in range(3):
        server._sweep_z_put("design", 30.0 + i, (50.0, 0.0, None, None))
    assert server._sweep_z_get("design", 20.0) is not None
    assert server._sweep_z_get("design", 21.0) is None


def test_cached_points_carry_the_per_feed_rows(monkeypatch):
    # Multi-feed sweeps ship per-feed Z alongside the primary; a cache round
    # trip must not silently drop them (the frontend indexes them
    # positionally against freqs_mhz).
    def momwire_sweep(req, freqs, cancel=None):
        n = len(freqs)
        return (
            [50.0] * n,
            [0.0] * n,
            [[50.0, 60.0]] * n,
            [[0.0, 1.0]] * n,
        )

    monkeypatch.setitem(
        server.EXAMPLES,
        "fake.multifeed",
        SimpleNamespace(
            multi_feed=True,
            count_basis=lambda req: 100,
            momwire_sweep=momwire_sweep,
        ),
    )
    design = {"geometry": "fake.multifeed", "_session": "tab-M"}
    with TestClient(server.app) as c:
        c.post("/sweep", json={**design, "freqs_mhz": [7.0]})
        cached = c.post("/sweep", json={**design, "_refine": True, "freqs_mhz": [7.0]})
    import json as _json

    record = _json.loads(_sweep_lines(cached)[0])
    assert record["feeds_z_re"] == [50.0, 60.0]
    assert record["feeds_z_im"] == [0.0, 1.0]
