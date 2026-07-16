"""Single-lane solve scheduler (issue #382): lane, cost model, endpoints.

Lane semantics are tested event-driven on a private event loop (no solver,
no sleeps); the endpoint tests run the real FastAPI app against a fake
instant "example" so the whole file stays far under the time budget.

Concurrent-request tests drive the ASGI app in-loop (httpx2 AsyncClient +
ASGITransport, concurrent tasks in one event loop) — the same shape uvicorn
gives every request in production. They deliberately avoid TestClient for
concurrency: its cross-thread blocking portal deadlocks when two streaming
responses contend (one portal task vanishes without resolving its caller's
future) — a test-harness artifact, not server behavior. TestClient stays
for the plain sequential cases.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import httpx2
import momwire
import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import cost, server
from antennaknobs.web.lane import (
    LaneRegistry,
    SolveLane,
    Superseded,
    cancel_on_disconnect,
)

# ---------------------------------------------------------------------------
# SolveLane semantics
# ---------------------------------------------------------------------------


class FakeToken:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise momwire.SolveAborted()


def _lane() -> SolveLane:
    return SolveLane(token_factory=FakeToken)


def test_lane_never_grants_two_turns_at_once():
    async def main():
        lane = _lane()
        active = 0
        peak = 0

        async def job(kind, gen):
            nonlocal active, peak
            async with lane.turn(kind, gen):
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0)  # yield while "computing"
                await asyncio.sleep(0)
                active -= 1

        await asyncio.gather(
            job("sweep", 1),
            job("converge", 1),
            job("norm_check", 1),
            job("live", 1),
            job("sweep", 2),
            return_exceptions=True,  # some are superseded — irrelevant here
        )
        assert peak == 1
        assert lane.idle

    asyncio.run(main())


def test_live_outranks_queued_batches():
    async def main():
        lane = _lane()
        order: list[str] = []
        release = asyncio.Event()

        async def holder():
            async with lane.turn("pattern_metrics"):
                await release.wait()

        async def job(kind):
            async with lane.turn(kind):
                order.append(kind)

        h = asyncio.create_task(holder())
        await asyncio.sleep(0)  # holder takes the lane
        jobs = [
            asyncio.create_task(job("sweep")),
            asyncio.create_task(job("converge")),
            asyncio.create_task(job("live")),
            asyncio.create_task(job("norm_check")),
        ]
        await asyncio.sleep(0)  # everyone queues
        release.set()
        await asyncio.gather(h, *jobs)
        assert order[0] == "live"
        assert order[1] == "norm_check"
        assert set(order[2:]) == {"sweep", "converge"}

    asyncio.run(main())


def test_newer_generation_cancels_the_running_turn():
    async def main():
        lane = _lane()
        preempted = asyncio.Event()
        seen: dict = {}

        async def old_batch():
            async with lane.turn("sweep", 5) as token:
                seen["token"] = token
                await preempted.wait()

        t = asyncio.create_task(old_batch())
        await asyncio.sleep(0)
        assert seen["token"].cancelled is False

        async def newer_live():
            async with lane.turn("live", 6):
                pass

        live = asyncio.create_task(newer_live())
        await asyncio.sleep(0)
        # The knob drag preempts the running chunk right away…
        assert seen["token"].cancelled is True
        preempted.set()  # …and the solver would raise SolveAborted about now
        await asyncio.gather(t, live)

    asyncio.run(main())


def test_newer_generation_supersedes_queued_and_stale_arrivals():
    async def main():
        lane = _lane()
        release = asyncio.Event()

        async def holder():
            async with lane.turn("live", 5):
                await release.wait()

        h = asyncio.create_task(holder())
        await asyncio.sleep(0)

        async def queued_old_batch():
            async with lane.turn("sweep", 5):
                pass

        q = asyncio.create_task(queued_old_batch())
        await asyncio.sleep(0)

        async def newer_live():
            async with lane.turn("live", 7):
                pass

        n = asyncio.create_task(newer_live())
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(q, n, return_exceptions=True)
        assert isinstance(results[0], Superseded)  # queued gen-5 batch died
        assert results[1] is None
        # A gen older than the lane's is stale on arrival.
        with pytest.raises(Superseded):
            async with lane.turn("sweep", 3):
                pass
        await h

    asyncio.run(main())


def test_same_kind_supersedes_but_pattern_metrics_coexists():
    async def main():
        lane = _lane()
        release = asyncio.Event()

        async def holder():
            async with lane.turn("live"):
                await release.wait()

        h = asyncio.create_task(holder())
        await asyncio.sleep(0)

        async def queued(kind):
            async with lane.turn(kind):
                pass

        old_sweep = asyncio.create_task(queued("sweep"))
        pm1 = asyncio.create_task(queued("pattern_metrics"))
        pm2 = asyncio.create_task(queued("pattern_metrics"))
        await asyncio.sleep(0)
        new_sweep = asyncio.create_task(queued("sweep"))
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(
            old_sweep, pm1, pm2, new_sweep, return_exceptions=True
        )
        assert isinstance(results[0], Superseded)  # re-issued sweep wins
        assert results[1] is None  # compare-table rows are all legitimate
        assert results[2] is None
        assert results[3] is None
        await h

    asyncio.run(main())


def test_advance_preempts_without_taking_a_turn():
    async def main():
        registry = LaneRegistry(token_factory=FakeToken)
        preempted = asyncio.Event()
        seen: dict = {}

        async def old_chunk():
            async with registry.turn("tab-1", "sweep", 5) as token:
                seen["token"] = token
                await preempted.wait()

        t = asyncio.create_task(old_chunk())
        await asyncio.sleep(0)
        # The /ws reader path: newer intent lands, no turn is taken yet.
        registry.advance("tab-1", 6)
        assert seen["token"].cancelled is True
        registry.advance("ghost-session", 9)  # unknown session: no-op
        preempted.set()
        await t

    asyncio.run(main())


def test_registry_isolates_sessions_and_reaps_idle_lanes():
    async def main():
        registry = LaneRegistry(token_factory=FakeToken)
        both = asyncio.Barrier(2)

        async def job(session):
            async with registry.turn(session, "sweep"):
                # Different sessions (and sessionless requests) may compute
                # concurrently — reaching the barrier proves no shared lane.
                await asyncio.wait_for(both.wait(), timeout=1)

        await asyncio.gather(job("tab-1"), job("tab-2"))
        assert len(registry) == 0  # idle lanes reaped on turn exit
        await asyncio.gather(job(None), job(None))
        assert len(registry) == 0

    asyncio.run(main())


def test_cancel_on_disconnect_trips_the_token():
    async def main():
        token = FakeToken()
        gone = False

        async def is_disconnected():
            return gone

        request = SimpleNamespace(is_disconnected=is_disconnected)
        async with cancel_on_disconnect(request, token, interval=0.005):
            assert token.cancelled is False
            gone = True
            await asyncio.sleep(0.03)
            assert token.cancelled is True

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Cost model: the run/warn/refuse mapping
# ---------------------------------------------------------------------------


def _example(n_basis):
    return SimpleNamespace(count_basis=lambda req: n_basis)


@pytest.mark.parametrize(
    ("req", "kw", "verdict"),
    [
        # Local instances are unlocked: no refuse, whatever the size.
        ({}, dict(hosted=False, example=_example(10**6)), "warn"),
        # Hosted matrix caps, per engine class.
        ({}, dict(hosted=True, example=_example(cost.MAX_BASIS + 1)), "refuse"),
        (
            {"momwire_model": "hmatrix"},
            dict(hosted=True, example=_example(cost.MAX_BASIS + 1)),
            "warn",  # compressed engines get cap headroom, but a b-spline-
            # family solver on a benchmark mesh is still a poor match
        ),
        (
            {"momwire_model": "hmatrix"},
            dict(hosted=True, example=_example(cost.MAX_BASIS_COMPRESSED + 1)),
            "refuse",  # …but not unlimited
        ),
        (
            {},
            dict(
                hosted=True, use_pynec=True, example=_example(cost.MAX_BASIS_PYNEC + 1)
            ),
            "refuse",
        ),
        # Batch size multiplies cost: hosted point cap, any kind.
        (
            {},
            dict(hosted=True, example=_example(100), points=cost.MAX_SWEEP_POINTS + 1),
            "refuse",
        ),
        # Poor-match combo on a benchmark mesh: warn — dense b-spline family…
        ({}, dict(hosted=False, example=_example(cost.WARN_MIN_BASIS + 1)), "warn"),
        (
            {"momwire_model": "arrayblock"},
            dict(hosted=False, example=_example(cost.WARN_MIN_BASIS + 1)),
            "warn",
        ),
        # …but sinusoidal and PyNEC are the recommended combos: run.
        (
            {"momwire_model": "sinusoidal"},
            dict(hosted=False, example=_example(cost.WARN_MIN_BASIS + 1)),
            "run",
        ),
        (
            {},
            dict(
                hosted=False, use_pynec=True, example=_example(cost.WARN_MIN_BASIS + 1)
            ),
            "run",
        ),
        # Small mesh: run; unknown size: run (the solve surfaces real errors).
        ({}, dict(hosted=True, example=_example(100)), "run"),
        ({}, dict(hosted=True, example=None), "run"),
        ({}, dict(hosted=True, example=_example(None)), "run"),
    ],
)
def test_admission_mapping(req, kw, verdict):
    kw.setdefault("use_pynec", False)
    kw.setdefault("kind", "sweep")
    assert cost.admit(req, **kw).verdict == verdict


def test_admission_reasons_name_the_lever():
    over = cost.admit(
        {}, kind="live", use_pynec=False, hosted=True, example=_example(10**5)
    )
    assert "segments / wire" in over.reason
    warned = cost.admit(
        {}, kind="sweep", use_pynec=False, hosted=False, example=_example(5000)
    )
    assert "Sinusoidal" in warned.reason and warned.est_basis == 5000


# ---------------------------------------------------------------------------
# Endpoints: the lane + admission wired into the real app
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    return TestClient(server.app)


class _Meter:
    """Concurrency meter shared by the fake compute functions."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def __enter__(self):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        return self

    def __exit__(self, *exc):
        with self.lock:
            self.active -= 1


def _fake_example(meter: _Meter, n_basis: int = 100, dwell_s: float = 0.02):
    """A minimal stand-in for an AntennaExample: instant fake physics with a
    concurrency meter, honouring the cancel token like momwire does."""

    def momwire_sweep(req, freqs, cancel=None):
        with meter:
            time.sleep(dwell_s)
        if cancel is not None:
            cancel.raise_if_cancelled()
        return [50.0] * len(freqs), [0.0] * len(freqs)

    def momwire_solve(req, cancel=None):
        with meter:
            time.sleep(dwell_s)
        if cancel is not None:
            cancel.raise_if_cancelled()
        return {"z_in_re": 50.0, "z_in_im": 0.0}

    return SimpleNamespace(
        multi_feed=False,
        count_basis=lambda req: n_basis,
        momwire_sweep=momwire_sweep,
        momwire_solve=momwire_solve,
    )


def _sweep_lines(resp):
    return [line for line in resp.text.splitlines() if line.strip()]


def _gather_posts(*payloads):
    """POST all payloads concurrently against the app, in one event loop."""

    async def main():
        transport = httpx2.ASGITransport(app=server.app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://lane-test"
        ) as c:
            return await asyncio.wait_for(
                asyncio.gather(*(c.post(path, json=body) for path, body in payloads)),
                timeout=20,
            )

    return asyncio.run(main())


def test_one_session_never_computes_twice_at_once(monkeypatch):
    meter = _Meter()
    monkeypatch.setitem(server.EXAMPLES, "fake.lane", _fake_example(meter))
    sweep, conv = _gather_posts(
        (
            "/sweep",
            {
                "geometry": "fake.lane",
                "_session": "tab-A",
                "freqs_mhz": [14.0, 14.1, 14.2, 14.3],
            },
        ),
        (
            "/converge",
            {"geometry": "fake.lane", "_session": "tab-A", "n_values": [5, 7, 9]},
        ),
    )
    assert sweep.status_code == 200
    assert conv.status_code == 200
    # 4 sweep points + 3 converge points all computed…
    assert len(_sweep_lines(sweep)) == 4 + 1  # + done record
    assert len(_sweep_lines(conv)) == 3 + 1
    # …and never two at once: the whole point of the lane.
    assert meter.peak == 1


def test_two_sessions_may_compute_concurrently(monkeypatch):
    # The inverse guard: the lane must serialize per session, not globally.
    meter = _Meter()
    monkeypatch.setitem(
        server.EXAMPLES, "fake.lane", _fake_example(meter, dwell_s=0.05)
    )
    a, b = _gather_posts(
        (
            "/sweep",
            {"geometry": "fake.lane", "_session": "tab-A", "freqs_mhz": [14.0, 14.1]},
        ),
        (
            "/sweep",
            {"geometry": "fake.lane", "_session": "tab-B", "freqs_mhz": [14.0, 14.1]},
        ),
    )
    assert a.status_code == 200
    assert b.status_code == 200
    assert meter.peak == 2


def test_warned_batch_needs_approval(client, monkeypatch):
    meter = _Meter()
    monkeypatch.setitem(
        server.EXAMPLES,
        "fake.big",
        _fake_example(meter, n_basis=cost.WARN_MIN_BASIS + 1, dwell_s=0.0),
    )
    body = {"geometry": "fake.big", "freqs_mhz": [14.0]}
    refused = client.post("/sweep", json=body)
    assert refused.status_code == 403
    assert "Sinusoidal" in refused.json()["detail"]
    approved = client.post("/sweep", json={**body, "_approved": True})
    assert approved.status_code == 200
    # The recommended combo runs without any approval.
    fine = client.post("/sweep", json={**body, "momwire_model": "sinusoidal"})
    assert fine.status_code == 200


def test_newer_generation_supersedes_a_streaming_sweep(monkeypatch):
    # An old-generation sweep (client state the user has since changed) is cut
    # off as soon as a newer-generation request enters the same session's lane.
    meter = _Meter()
    first_point_done = threading.Event()

    fake = _fake_example(meter, dwell_s=0.0)
    inner_sweep = fake.momwire_sweep

    def gated_sweep(req, freqs, cancel=None):
        if req.get("_gen") == 5 and first_point_done.is_set():
            # The old stream's SECOND point: sit in the "compute" until the
            # newer-generation request preempts us via the cancel token (the
            # lane trips it the moment gen 6 is admitted) — deterministic,
            # and exactly how a long momwire chunk experiences supersession.
            deadline = time.time() + 5
            while cancel is not None and not cancel.cancelled:
                if time.time() > deadline:
                    raise AssertionError("never preempted by the newer request")
                time.sleep(0.005)
            cancel.raise_if_cancelled()
        out = inner_sweep(req, freqs, cancel=cancel)
        if req.get("_gen") == 5:
            first_point_done.set()
        return out

    fake.momwire_sweep = gated_sweep
    monkeypatch.setitem(server.EXAMPLES, "fake.gen", fake)

    old_body = {
        "geometry": "fake.gen",
        "_session": "tab-G",
        "_gen": 5,
        "freqs_mhz": [14.0, 14.1, 14.2, 14.3],
    }
    new_body = {**old_body, "_gen": 6, "freqs_mhz": [14.0]}

    async def main():
        transport = httpx2.ASGITransport(app=server.app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://lane-test"
        ) as c:
            old_task = asyncio.create_task(c.post("/sweep", json=old_body))
            # Wait (off-loop event, set by the threadpool fake) until the old
            # stream's first point has computed and its second is gated.
            await asyncio.wait_for(asyncio.to_thread(first_point_done.wait), 5)
            new_resp = await c.post("/sweep", json=new_body)
            old_resp = await asyncio.wait_for(old_task, 10)
            return old_resp, new_resp

    old_resp, new_resp = asyncio.run(asyncio.wait_for(main(), timeout=20))
    assert new_resp.status_code == 200
    assert len(_sweep_lines(new_resp)) == 1 + 1
    # The gen-5 stream ended early: its remaining points were never solved.
    assert old_resp.status_code == 200
    assert len(_sweep_lines(old_resp)) < 4 + 1
