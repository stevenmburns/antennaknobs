"""AK#1712: the user's cancel, or a newer solve, stops EVERY server-side
compute for the session, and promptly.

The defect: "Cancel solve" was client-side only, so nothing reached the server
and a cold Sommerfeld fill ran on for many minutes. Behind it sat routes whose
engine never saw a token at all: /pattern and /engine_io took lane turns
without binding one, a NEC-5 / NEC-2 binary had no kill switch on any route,
/pattern_metrics ran gen-less so a newer solve could never supersede it, and
an /optimize eval in flight ran out after its client left.

Every test drives a STUB that blocks until its token trips (or, for the
subprocess engines, a real child process that sleeps until killed), so a
route that fails to pass the token fails the test by timing out, not by
computing anything real. The house pattern is test_solve_lane.py's: TestClient
for sequential and websocket traffic, an in-loop httpx2 ASGITransport client
where two requests must overlap.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx2
import momwire
import pytest
from fastapi.testclient import TestClient

from antennaknobs.engines._external import cancel_scope, run_exe
from antennaknobs.web import server
from antennaknobs.web.lane import SolveLane, Superseded

# How long a stub waits for its token before giving up. Long enough that a
# route which never trips it is unmistakable; the assertions wait far less.
HOLD_S = 6.0
# The promptness bar: a tripped token must stop the compute within this.
PROMPT_S = 2.0


class _Blocker:
    """A compute that runs until its token trips, then raises SolveAborted
    like a momwire checkpoint. With no token (the defect) it holds for HOLD_S
    and fails, so the caller's wait on `aborted` times out."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.aborted = threading.Event()
        self.calls = 0

    def run(self, cancel) -> None:
        self.calls += 1
        self.started.set()
        deadline = time.monotonic() + HOLD_S
        while time.monotonic() < deadline:
            if cancel is not None and cancel.cancelled:
                self.aborted.set()
                raise momwire.SolveAborted()
            time.sleep(0.005)
        raise AssertionError("the token never tripped")


def _fake_example(blocker: _Blocker, *, block_first_only: bool = False):
    """An AntennaExample stand-in whose momwire paths all go through
    `blocker`. `block_first_only` lets the next solve on the same socket
    answer at once, proving the channel survives a cancel."""

    def _maybe_block(cancel):
        if not block_first_only or blocker.calls == 0:
            blocker.run(cancel)

    def momwire_solve(req, cancel=None):
        _maybe_block(cancel)
        return {"z_in_re": 50.0, "z_in_im": 0.0, "geometry": req.get("geometry")}

    def far_field_metrics(req, cancel=None):
        if req.get("_gen") == 6:  # the newer request: answers at once
            return {"peak_gain_dbi": 2.0}
        blocker.run(cancel)
        return {"peak_gain_dbi": 1.0}

    return SimpleNamespace(
        multi_feed=False,
        count_basis=lambda req: 100,
        momwire_solve=momwire_solve,
        far_field_metrics=far_field_metrics,
    )


# ---------------------------------------------------------------------------
# A subprocess engine: a real child that sleeps until it is killed
# ---------------------------------------------------------------------------

_CHILD = (
    "import os, sys, time\n"
    "sys.stdin.read()\n"
    "open(sys.argv[1], 'w').write(str(os.getpid()))\n"
    "time.sleep(60)\n"
)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class _ChildEngine:
    """A backend module stand-in (NEC-5's shape: solve / pattern / per-point
    sweep) whose every call launches the sleeping child through `run_exe`,
    the one launch point the real NEC-5 and NEC-2 wrappers share. A class
    instance rather than a SimpleNamespace because the server keys
    `_BACKEND_NAME` by the module object."""

    def __init__(self, tmp_path: Path) -> None:
        self.pidfile = tmp_path / "child.pid"

    def _run(self) -> None:
        run_exe(
            [sys.executable, "-c", _CHILD, str(self.pidfile)],
            stdin_text="",
            cwd=str(self.pidfile.parent),
            timeout=HOLD_S * 2,
        )
        raise AssertionError("the child ran to completion: it was never killed")

    def solve(self, req):
        self._run()

    def pattern(self, req):
        if req.get("_gen") == 6:
            return {"available": True, "gain_dbi": []}
        self._run()

    def _sweep_at(self, req, f):
        self._run()

    def child_pid(self, timeout: float = 10.0) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                text = self.pidfile.read_text()
            except FileNotFoundError:
                text = ""
            if text:
                return int(text)
            time.sleep(0.01)
        raise AssertionError("the engine child never started")

    def assert_killed(self, pid: int) -> None:
        deadline = time.monotonic() + PROMPT_S
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        if _alive(pid):  # don't leave it behind whatever the verdict
            os.kill(pid, 9)
            raise AssertionError(f"engine child {pid} still running after cancel")


@pytest.fixture()
def child_engine(monkeypatch, tmp_path):
    eng = _ChildEngine(tmp_path)
    monkeypatch.setitem(server._EXTERNAL_BACKENDS, "nec5", (eng, lambda: True))
    monkeypatch.setitem(server._BACKEND_NAME, eng, "nec5")
    monkeypatch.setattr(server, "_SOLVE_CACHE", server._SOLVE_CACHE.__class__())
    monkeypatch.setattr(server, "_ENGINE_IO_CACHE", server._ENGINE_IO_CACHE.__class__())
    blocker = _Blocker()
    monkeypatch.setitem(server.EXAMPLES, "fake.cancel", _fake_example(blocker))
    return eng


def _in_loop(coro_fn):
    """Run an async scenario against the app in one event loop."""

    async def main():
        transport = httpx2.ASGITransport(app=server.app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://cancel-1712"
        ) as c:
            return await coro_fn(c)

    return asyncio.run(asyncio.wait_for(main(), timeout=30))


async def _wait(event: threading.Event, timeout: float) -> bool:
    return await asyncio.to_thread(event.wait, timeout)


# ---------------------------------------------------------------------------
# The lane primitive
# ---------------------------------------------------------------------------


class _FakeToken:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def test_cancel_all_stops_every_kind_and_generation_but_does_not_stick():
    async def main():
        lane = SolveLane(token_factory=_FakeToken)
        # A gen-less compare row holds the lane; a sweep and a live solve wait.
        running = lane.turn("pattern_metrics")
        token = await running.__aenter__()
        queued = [
            asyncio.create_task(_enter(lane, "sweep", 3)),
            asyncio.create_task(_enter(lane, "live", 3)),
        ]
        await asyncio.sleep(0)
        lane.cancel_all(4)
        assert token.cancelled  # gen-less, yet cancelled
        for t in queued:
            with pytest.raises(Superseded):
                await t
        await running.__aexit__(None, None, None)
        # Nothing sticks: the next request runs (its generation is current).
        async with lane.turn("live", 5) as t2:
            assert not t2.cancelled
        # A batch issued BEFORE the cancel that arrives after it is stale.
        with pytest.raises(Superseded):
            async with lane.turn("sweep", 3):
                pass

    async def _enter(lane, kind, gen):
        async with lane.turn(kind, gen):
            pass

    asyncio.run(main())


# ---------------------------------------------------------------------------
# /ws: the cancel message
# ---------------------------------------------------------------------------


def test_ws_cancel_message_stops_the_live_solve(monkeypatch):
    blocker = _Blocker()
    monkeypatch.setitem(
        server.EXAMPLES, "fake.cancel", _fake_example(blocker, block_first_only=True)
    )
    monkeypatch.setattr(server, "_SOLVE_CACHE", server._SOLVE_CACHE.__class__())
    # The stub's response is not a real solve; skip the derived fields.
    for name in (
        "_attach_request_cuts",
        "_attach_derived_em_fields",
        "_attach_gain_norm",
        "_attach_in_medium_fraction",
    ):
        monkeypatch.setattr(server, name, lambda *a, **k: None)
    with TestClient(server.app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"geometry": "fake.cancel", "_session": "t-ws", "_seq": 1})
        assert blocker.started.wait(5)
        ws.send_json({"_kind": "cancel", "_session": "t-ws", "_seq": 2})
        assert blocker.aborted.wait(PROMPT_S), "the cancel never reached the solve"
        # The socket survives, and the next solve is answered (the cancelled
        # one sends nothing: the client already stopped waiting for it).
        ws.send_json({"geometry": "fake.cancel", "_session": "t-ws", "_seq": 3})
        reply = ws.receive_json()
        assert reply["_seq"] == 3 and "error" not in reply


def test_ws_cancel_message_kills_a_live_subprocess_engine(child_engine):
    with TestClient(server.app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json(
            {"geometry": "fake.cancel", "solver": "nec5", "_session": "t-x", "_seq": 1}
        )
        pid = child_engine.child_pid()
        ws.send_json({"_kind": "cancel", "_session": "t-x", "_seq": 2})
        child_engine.assert_killed(pid)


def test_ws_cancel_message_stops_a_genless_pattern_metrics(monkeypatch):
    # The reported shape: a compare-table row (no generation) mid-fill when
    # the user presses cancel on the live channel. One TestClient context, so
    # the POST and the socket share the app's event loop and its lanes.
    blocker = _Blocker()
    monkeypatch.setitem(server.EXAMPLES, "fake.cancel", _fake_example(blocker))
    with TestClient(server.app) as client:
        out: dict = {}

        def post():
            out["r"] = client.post(
                "/pattern_metrics",
                json={"geometry": "fake.cancel", "_session": "t-pm"},
            ).json()

        th = threading.Thread(target=post)
        th.start()
        try:
            assert blocker.started.wait(5)
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"_kind": "cancel", "_session": "t-pm", "_seq": 9})
                assert blocker.aborted.wait(PROMPT_S), "cancel missed /pattern_metrics"
        finally:
            th.join(HOLD_S + 2)
    assert out["r"]["available"] is False


# ---------------------------------------------------------------------------
# /pattern_metrics: the live row carries a generation
# ---------------------------------------------------------------------------


def test_newer_generation_supersedes_the_live_pattern_metrics(monkeypatch):
    blocker = _Blocker()
    monkeypatch.setitem(server.EXAMPLES, "fake.cancel", _fake_example(blocker))
    body = {"geometry": "fake.cancel", "_session": "t-g", "_gen": 5}

    async def scenario(c):
        old = asyncio.create_task(c.post("/pattern_metrics", json=body))
        assert await _wait(blocker.started, 5)
        new = await c.post("/pattern_metrics", json={**body, "_gen": 6})
        assert await _wait(blocker.aborted, PROMPT_S), "gen 6 did not supersede gen 5"
        return (await old).json(), new.json()

    old, new = _in_loop(scenario)
    assert old["available"] is False
    assert new["available"] is True and new["metrics"]["peak_gain_dbi"] == 2.0


def test_a_pinned_row_is_not_superseded_by_a_newer_generation(monkeypatch):
    # The other half of the contract: a pinned row describes a frozen
    # snapshot and sends no generation, so a knob drag must not cancel it.
    seen: dict = {}

    def far_field_metrics(req, cancel=None):
        if req.get("_gen") == 6:
            return {"peak_gain_dbi": 2.0}
        seen["started"] = True
        time.sleep(0.3)
        seen["cancelled"] = cancel.cancelled
        return {"peak_gain_dbi": 1.0}

    monkeypatch.setitem(
        server.EXAMPLES,
        "fake.cancel",
        SimpleNamespace(count_basis=lambda r: 100, far_field_metrics=far_field_metrics),
    )
    pinned = {"geometry": "fake.cancel", "_session": "t-p"}

    async def scenario(c):
        old = asyncio.create_task(c.post("/pattern_metrics", json=pinned))
        while not seen.get("started"):
            await asyncio.sleep(0.01)
        await c.post("/pattern_metrics", json={**pinned, "_gen": 6})
        return (await old).json()

    assert _in_loop(scenario)["available"] is True
    assert seen["cancelled"] is False


# ---------------------------------------------------------------------------
# /pattern, /engine_io, /sweep through a subprocess engine
# ---------------------------------------------------------------------------


def test_newer_pattern_kills_the_running_engine(child_engine):
    body = {"geometry": "fake.cancel", "solver": "nec5", "_session": "t-pat", "_gen": 5}

    async def scenario(c):
        old = asyncio.create_task(c.post("/pattern", json=body))
        pid = await asyncio.to_thread(child_engine.child_pid)
        await c.post("/pattern", json={**body, "_gen": 6})
        await asyncio.to_thread(child_engine.assert_killed, pid)
        return (await old).json()

    assert _in_loop(scenario) == {"available": False}


def test_session_cancel_kills_the_engine_io_rerun(child_engine):
    body = {"geometry": "fake.cancel", "solver": "nec5", "_session": "t-io", "_gen": 5}

    async def scenario(c):
        req = asyncio.create_task(c.post("/engine_io", json=body))
        pid = await asyncio.to_thread(child_engine.child_pid)
        server._LANES.cancel("t-io", 6)  # what the /ws cancel message calls
        await asyncio.to_thread(child_engine.assert_killed, pid)
        return (await req).json()

    out = _in_loop(scenario)
    assert out["available"] is False and out["superseded"] is True


def test_session_cancel_kills_an_external_sweep_point(child_engine):
    body = {
        "geometry": "fake.cancel",
        "solver": "nec5",
        "_session": "t-sw",
        "_gen": 5,
        "freqs_mhz": [14.0, 14.1, 14.2],
    }

    async def scenario(c):
        req = asyncio.create_task(c.post("/sweep", json=body))
        pid = await asyncio.to_thread(child_engine.child_pid)
        server._LANES.cancel("t-sw", 6)
        await asyncio.to_thread(child_engine.assert_killed, pid)
        return await req

    resp = _in_loop(scenario)
    assert resp.status_code == 200
    assert resp.text.strip() == ""  # no point solved, no done record


# ---------------------------------------------------------------------------
# /optimize: the eval in flight stops with its client
# ---------------------------------------------------------------------------


def test_optimize_eval_in_flight_stops_when_the_stream_closes(monkeypatch):
    blocker = _Blocker()
    monkeypatch.setitem(server.EXAMPLES, "fake.cancel", _fake_example(blocker))
    body = {
        "geometry": "fake.cancel",
        "length_factor": 1.05,
        "optimize": {
            "free": [{"name": "length_factor", "min": 0.9, "max": 1.1}],
            "objective": "swr",
        },
    }

    async def scenario(c):
        req = asyncio.create_task(
            c.post("/optimize", json=body, headers={"Accept": "text/event-stream"})
        )
        assert await _wait(blocker.started, 5)
        req.cancel()  # the client goes away mid-eval
        try:
            await req
        except asyncio.CancelledError:
            pass
        return await _wait(blocker.aborted, PROMPT_S)

    assert _in_loop(scenario), "the optimizer's eval ran on after its client left"


# ---------------------------------------------------------------------------
# run_exe itself
# ---------------------------------------------------------------------------


def test_run_exe_without_a_token_is_plain_subprocess_run(tmp_path):
    proc = run_exe(
        [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
        stdin_text="deck",
        cwd=str(tmp_path),
        timeout=30,
    )
    assert proc.returncode == 0 and proc.stdout.strip() == "DECK"


def test_run_exe_under_a_token_still_answers_and_honours_timeout(tmp_path):
    tok = momwire.CancelToken()
    with cancel_scope(tok):
        proc = run_exe(
            [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
            stdin_text="deck",
            cwd=str(tmp_path),
            timeout=30,
        )
        assert proc.stdout.strip() == "DECK"
        import subprocess

        t0 = time.monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            run_exe(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdin_text="",
                cwd=str(tmp_path),
                timeout=0.5,
            )
        assert time.monotonic() - t0 < 5


def test_run_exe_kills_the_child_when_the_token_trips(tmp_path):
    eng = _ChildEngine(tmp_path)
    tok = momwire.CancelToken()
    err: dict = {}

    def target():
        with cancel_scope(tok):
            try:
                eng._run()
            except BaseException as e:  # noqa: BLE001 — carried to the assertion
                err["e"] = e

    th = threading.Thread(target=target)
    th.start()
    pid = eng.child_pid()
    t0 = time.monotonic()
    tok.cancel()
    th.join(PROMPT_S)
    assert not th.is_alive()
    assert isinstance(err.get("e"), momwire.SolveAborted)
    assert time.monotonic() - t0 < PROMPT_S
    eng.assert_killed(pid)


def test_a_raw_accelerator_abort_is_a_cancel_not_an_error():
    # Measured on GndScreen (AK#1712): a cancelled Sommerfeld remainder fill
    # raised momwire's raw C++ `AcceleratorAborted` (that kernel is not in
    # momwire's remap list), and /pattern_metrics answered it as an ERROR.
    # `_shed`, the threadpool shim every solve route dispatches through,
    # makes it the one abort type the routes catch.
    AcceleratorAborted = type("AcceleratorAborted", (RuntimeError,), {})

    def fill():
        raise AcceleratorAborted("accelerator solve aborted")

    with pytest.raises(momwire.SolveAborted):
        server._shed(fill)
