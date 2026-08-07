"""Threadpool → event-loop progress bridge (issue #773, unit 2).

Every concurrency claim here is pinned with an explicit handshake — a
``threading.Event`` in one direction, an awaited task in the other — never a
wall-clock sleep. A broken wakeup path therefore shows up as a *hang* caught by
``asyncio.wait_for``/``join(timeout=...)``, not as an intermittent failure.

The producer always runs on a real OS thread (``threading.Thread``, or
``run_in_threadpool`` where the production shape matters); nothing here fakes
the thread boundary the bridge exists to cross.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from fastapi.concurrency import run_in_threadpool

from antennaknobs.web.progress_stream import (
    ProgressEvent,
    ProgressStream,
    ProgressStreamClosed,
)

TIMEOUT = 4.0  # only ever reached on a HANG; kept under the suite's 5 s ceiling


def _kinds(events: list[ProgressEvent]) -> list[str]:
    return [e.kind for e in events]


def _ns(events: list[ProgressEvent]) -> list[int]:
    return [e.data["n"] for e in events if e.kind == "progress"]


# ---------------------------------------------------------------------------
# Gate 1 — ordering across a real thread boundary
# ---------------------------------------------------------------------------


def test_ordering_preserved_with_a_free_running_worker_thread():
    """200 events published from a worker while the consumer drains: the
    delivered sequence is exactly the published one, terminal event last."""

    async def main():
        stream = ProgressStream(maxsize=1024)  # deliberately never full here

        def producer():
            for n in range(200):
                stream.publish({"n": n})
            stream.finish({"ok": True})

        thread = threading.Thread(target=producer, name="probe-producer")
        received: list[ProgressEvent] = []

        async def drain():
            async for event in stream.events():
                received.append(event)

        task = asyncio.ensure_future(drain())
        await asyncio.sleep(0)  # consumer is parked on the wake event
        thread.start()
        await asyncio.wait_for(task, TIMEOUT)
        thread.join(TIMEOUT)
        return stream, received

    stream, received = asyncio.run(main())
    assert _ns(received) == list(range(200))
    assert _kinds(received)[-1] == "result"
    assert _kinds(received).count("result") == 1
    assert received[-1].data == {"ok": True}
    assert stream.dropped == 0


def test_ordering_holds_under_lockstep_ping_pong():
    """The strongest ordering probe: the worker publishes only after the loop
    has acknowledged the previous event, so every single event genuinely
    crosses the thread boundary while the consumer is live. Also proves the
    wakeup path — with no wakeup this deadlocks rather than passing slowly."""

    async def main():
        stream = ProgressStream(maxsize=4)
        acked = threading.Event()
        waits_ok: list[bool] = []

        def producer():
            for n in range(25):
                stream.publish({"n": n})
                waits_ok.append(acked.wait(TIMEOUT))
                acked.clear()
            stream.finish({"evals": 25})

        thread = threading.Thread(target=producer, name="pingpong-producer")
        received: list[ProgressEvent] = []

        async def drain():
            async for event in stream.events():
                received.append(event)
                acked.set()  # threading.Event.set is safe from the loop thread

        task = asyncio.ensure_future(drain())
        await asyncio.sleep(0)
        thread.start()
        await asyncio.wait_for(task, TIMEOUT)
        thread.join(TIMEOUT)
        return received, waits_ok

    received, waits_ok = asyncio.run(main())
    assert all(waits_ok) and len(waits_ok) == 25
    assert _ns(received) == list(range(25))
    assert _kinds(received)[-1] == "result"


def test_ordering_holds_under_run_in_threadpool():
    """The production shape: the producer is an anyio worker started by
    ``run_in_threadpool``, exactly as ``_solve_at`` will be."""

    async def main():
        stream = ProgressStream(maxsize=64)
        received: list[ProgressEvent] = []
        worker_threads: set[int] = set()

        def producer():
            for n in range(50):
                worker_threads.add(threading.get_ident())
                stream.publish({"n": n})

        async def drain():
            async for event in stream.events():
                received.append(event)

        task = asyncio.ensure_future(drain())
        await asyncio.sleep(0)
        with stream.sealed():
            await run_in_threadpool(producer)
            stream.finish({"ok": True})
        await asyncio.wait_for(task, TIMEOUT)
        return received, worker_threads

    received, worker_threads = asyncio.run(main())
    assert worker_threads and threading.get_ident() not in worker_threads
    assert _ns(received) == list(range(50))
    assert _kinds(received)[-1] == "result"


# ---------------------------------------------------------------------------
# Gate 2 — consumer disconnect terminates the producer
# ---------------------------------------------------------------------------


def test_consumer_disconnect_raises_in_the_producer_and_frees_its_thread():
    """The consumer breaks out mid-run (a client disconnect). The next publish
    on the worker raises ProgressStreamClosed, the thread exits, and the
    process is back to its baseline thread count — nothing parked."""
    baseline = threading.active_count()
    permit = threading.Event()
    published: list[int] = []
    raised: list[BaseException] = []

    async def main():
        stream = ProgressStream(maxsize=4)

        def producer():
            try:
                for n in range(10_000):
                    assert permit.wait(TIMEOUT)
                    permit.clear()
                    stream.publish({"n": n})
                    published.append(n)
            except BaseException as exc:
                raised.append(exc)

        thread = threading.Thread(target=producer, name="disconnect-producer")
        thread.start()
        permit.set()  # release exactly one publish

        seen = 0
        async for _event in stream.events():
            seen += 1
            if seen == 3:
                break  # client disconnected; the generator's finally closes
            permit.set()  # let the worker produce the next one
        return stream, thread, seen

    stream, thread, seen = asyncio.run(main())
    assert seen == 3
    assert stream.done

    # The worker is parked on our test permit, not on the stream: publish never
    # blocks under the drop policy. Release it and it must die immediately.
    permit.set()
    thread.join(TIMEOUT)
    assert not thread.is_alive()
    assert isinstance(raised[0], ProgressStreamClosed)
    assert len(published) == 3  # stopped at the disconnect, not at 10_000
    # No thread leaked. "<=" rather than "==" only because an unrelated pool
    # elsewhere in the suite may wind down during this test; it can never go up.
    assert threading.active_count() <= baseline


def test_publish_after_close_raises_from_either_caller():
    stream = ProgressStream()
    stream.publish({"n": 0})
    stream.close()
    with pytest.raises(ProgressStreamClosed):
        stream.publish({"n": 1})
    assert stream.done
    assert stream.finish({"late": True}) is False


def test_close_is_idempotent_and_drops_the_backlog():
    stream = ProgressStream(maxsize=8)
    for n in range(4):
        stream.publish({"n": n})
    stream.close()
    stream.close()

    async def main():
        return [e async for e in stream.events()]

    assert asyncio.run(main()) == []


def test_a_closed_loop_closes_the_stream_instead_of_queueing_into_a_void():
    """If the consumer's loop is gone (worker outliving the request), the one
    loop entry point raises RuntimeError; the bridge must convert that into a
    closed stream rather than buffering for a consumer that cannot return."""
    stream = ProgressStream()

    async def bind():
        async for _event in stream.events():  # pragma: no cover - never yields
            break

    loop = asyncio.new_event_loop()
    task = loop.create_task(bind())
    loop.run_until_complete(asyncio.sleep(0))
    task.cancel()
    loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
    # events()'s finally already closed the stream; re-open it to isolate the
    # closed-loop path from the ordinary disconnect path.
    stream._closed = False
    loop.close()

    with pytest.raises(ProgressStreamClosed):
        for n in range(2):  # first publish trips the closed loop, second raises
            stream.publish({"n": n})
    assert stream.done


# ---------------------------------------------------------------------------
# Gate 3 — bounded buffer: drop oldest, count the drops
# ---------------------------------------------------------------------------


def test_overflow_drops_the_oldest_and_counts_them():
    """No consumer has ever bound a loop — the worst case for a buffer, and
    fully deterministic: maxsize + k publishes leave exactly the newest
    maxsize, with k counted."""
    stream = ProgressStream(maxsize=5)

    def producer():
        for n in range(12):
            stream.publish({"n": n})
        stream.finish({"ok": True})

    thread = threading.Thread(target=producer, name="overflow-producer")
    thread.start()
    thread.join(TIMEOUT)

    async def main():
        return [e async for e in stream.events()]

    received = asyncio.run(main())
    assert _ns(received) == [7, 8, 9, 10, 11]  # newest five, in order
    assert stream.dropped == 7
    assert _kinds(received)[-1] == "result"


def test_a_stalled_consumer_sees_the_newest_state_and_never_loses_the_result():
    """Consumer slower than producer, with a live loop. It takes one event,
    stalls until the worker has finished producing, then drains: it sees the
    newest maxsize progress events plus the terminal one, which is exempt from
    the bound. Ordering of what survives is still publication order."""

    async def main():
        stream = ProgressStream(maxsize=4)
        saw_first = threading.Event()
        settled = threading.Event()

        def producer():
            stream.publish({"n": 0})
            assert saw_first.wait(TIMEOUT)
            for n in range(1, 13):
                stream.publish({"n": n})
            stream.finish({"ok": True})
            settled.set()  # every producer action is now complete

        thread = threading.Thread(target=producer, name="stall-producer")
        received: list[ProgressEvent] = []

        async def drain():
            async for event in stream.events():
                received.append(event)
                if len(received) == 1:
                    saw_first.set()
                    # Stall on the loop without blocking it, and without a
                    # sleep: resume only once the producer is provably done.
                    await asyncio.to_thread(settled.wait, TIMEOUT)

        task = asyncio.ensure_future(drain())
        await asyncio.sleep(0)
        thread.start()
        await asyncio.wait_for(task, TIMEOUT)
        thread.join(TIMEOUT)
        return stream, received

    stream, received = asyncio.run(main())
    assert _ns(received) == [0, 9, 10, 11, 12]
    assert stream.dropped == 8  # events 1..8, the stale ones
    assert received[-1].kind == "result"  # terminal bypasses the bound


def test_maxsize_must_be_positive():
    with pytest.raises(ValueError):
        ProgressStream(maxsize=0)


# ---------------------------------------------------------------------------
# Gate 4 — the loop is touched through exactly one entry point
# ---------------------------------------------------------------------------


class _LoopSpy:
    """Records every attribute the bridge reads off the loop, and the thread
    that read it. Anything other than ``call_soon_threadsafe`` reaching this
    from a worker thread is a violation of the module invariant."""

    def __init__(self, loop):
        self._loop = loop
        self.touched: list[tuple[str, str]] = []
        self.callback_threads: list[str] = []

    def call_soon_threadsafe(self, callback, *args):
        self.touched.append(("call_soon_threadsafe", threading.current_thread().name))

        def wrapped():
            self.callback_threads.append(threading.current_thread().name)
            callback(*args)

        return self._loop.call_soon_threadsafe(wrapped)

    def __getattr__(self, name):
        self.touched.append((name, threading.current_thread().name))
        return getattr(self._loop, name)


def test_worker_touches_the_loop_only_through_call_soon_threadsafe():
    async def main():
        stream = ProgressStream(maxsize=16)
        received: list[ProgressEvent] = []

        async def drain():
            async for event in stream.events():
                received.append(event)

        task = asyncio.ensure_future(drain())
        for _ in range(100):  # bounded: binding takes one scheduling step
            if stream._loop is not None:
                break
            await asyncio.sleep(0)
        assert stream._loop is not None
        spy = _LoopSpy(stream._loop)
        stream._loop = spy

        loop_thread = threading.current_thread().name
        no_loop_in_worker: list[bool] = []

        def producer():
            try:
                asyncio.get_running_loop()
                no_loop_in_worker.append(False)
            except RuntimeError:
                no_loop_in_worker.append(True)
            for n in range(5):
                stream.publish({"n": n})
            stream.finish({"ok": True})

        thread = threading.Thread(target=producer, name="invariant-producer")
        thread.start()
        await asyncio.wait_for(task, TIMEOUT)
        thread.join(TIMEOUT)
        return spy, received, loop_thread, no_loop_in_worker

    spy, received, loop_thread, no_loop_in_worker = asyncio.run(main())
    assert no_loop_in_worker == [True]  # the worker has no loop of its own
    assert len(received) == 6
    # Every loop access came from the worker, and every one of them was the
    # single documented entry point.
    assert {name for name, _ in spy.touched} == {"call_soon_threadsafe"}
    assert {thread for _, thread in spy.touched} == {"invariant-producer"}
    # ...and the scheduled callback (the asyncio.Event set) ran on the loop.
    assert set(spy.callback_threads) == {loop_thread}


def test_publishing_before_any_consumer_needs_no_loop_at_all():
    stream = ProgressStream(maxsize=8)
    done = threading.Event()

    def producer():
        for n in range(3):
            stream.publish({"n": n})
        done.set()

    thread = threading.Thread(target=producer, name="preconsumer-producer")
    thread.start()
    assert done.wait(TIMEOUT)
    thread.join(TIMEOUT)
    assert stream._loop is None
    assert not stream.done


# ---------------------------------------------------------------------------
# Gate 5 — completion is distinguishable from silence
# ---------------------------------------------------------------------------


def test_silence_leaves_the_consumer_pending_and_finish_ends_it():
    async def main():
        stream = ProgressStream()
        received: list[ProgressEvent] = []

        async def drain():
            async for event in stream.events():
                received.append(event)

        task = asyncio.ensure_future(drain())
        for _ in range(5):
            await asyncio.sleep(0)
        pending_while_silent = not task.done()
        done_while_silent = stream.done

        stream.publish({"n": 0})
        stream.finish({"ok": True})
        await asyncio.wait_for(task, TIMEOUT)
        return received, pending_while_silent, done_while_silent, stream.done

    received, pending, done_while_silent, done_after = asyncio.run(main())
    assert pending is True  # silence: still listening, nothing decided
    assert done_while_silent is False
    assert done_after is True
    assert _kinds(received) == ["progress", "result"]


def test_error_terminates_the_stream_like_a_result():
    async def main():
        stream = ProgressStream()
        stream.publish({"n": 0})
        stream.fail("solver exploded")
        return [e async for e in stream.events()]

    received = asyncio.run(main())
    assert _kinds(received) == ["progress", "error"]
    assert received[-1].data == {"detail": "solver exploded"}


def test_first_terminal_event_wins():
    stream = ProgressStream()
    assert stream.finish({"ok": True}) is True
    assert stream.fail("too late") is False

    async def main():
        return [e async for e in stream.events()]

    received = asyncio.run(main())
    assert _kinds(received) == ["result"]
    assert received[0].data == {"ok": True}


def test_publish_after_a_terminal_event_raises():
    stream = ProgressStream()
    stream.finish({"ok": True})
    with pytest.raises(ProgressStreamClosed):
        stream.publish({"n": 0})


def test_event_kinds_match_the_sse_names_of_contract_c2():
    stream = ProgressStream()
    stream.publish({"n": 0})
    stream.finish({"ok": True})

    async def main():
        return [e async for e in stream.events()]

    received = asyncio.run(main())
    assert [e.kind for e in received] == ["progress", "result"]
    assert [e.terminal for e in received] == [False, True]
    assert ProgressEvent("error", {}).terminal is True


# ---------------------------------------------------------------------------
# Producer death — sealed() guarantees the consumer never hangs
# ---------------------------------------------------------------------------


def test_sealed_converts_a_dead_producer_into_an_error_event():
    async def main():
        stream = ProgressStream()
        escaped: list[BaseException] = []

        def producer():
            try:
                with stream.sealed():
                    stream.publish({"n": 0})
                    raise ValueError("boom")
            except BaseException as exc:
                escaped.append(exc)

        thread = threading.Thread(target=producer, name="dying-producer")
        received: list[ProgressEvent] = []

        async def drain():
            async for event in stream.events():
                received.append(event)

        task = asyncio.ensure_future(drain())
        await asyncio.sleep(0)
        thread.start()
        await asyncio.wait_for(task, TIMEOUT)
        thread.join(TIMEOUT)
        return received, escaped

    received, escaped = asyncio.run(main())
    assert isinstance(escaped[0], ValueError)  # the producer still sees it
    assert _kinds(received) == ["progress", "error"]
    assert received[-1].data["detail"] == "ValueError: boom"


def test_sealed_terminates_a_producer_that_forgot_to_finish():
    async def main():
        stream = ProgressStream()

        def producer():
            with stream.sealed():
                stream.publish({"n": 0})

        thread = threading.Thread(target=producer, name="forgetful-producer")
        received: list[ProgressEvent] = []

        async def drain():
            async for event in stream.events():
                received.append(event)

        task = asyncio.ensure_future(drain())
        await asyncio.sleep(0)
        thread.start()
        await asyncio.wait_for(task, TIMEOUT)
        thread.join(TIMEOUT)
        return received

    received = asyncio.run(main())
    assert _kinds(received) == ["progress", "error"]
    assert "without a result" in received[-1].data["detail"]


def test_sealed_leaves_a_real_result_alone():
    stream = ProgressStream()
    with stream.sealed():
        stream.publish({"n": 0})
        stream.finish({"ok": True})

    async def main():
        return [e async for e in stream.events()]

    received = asyncio.run(main())
    assert _kinds(received) == ["progress", "result"]


def test_sealed_reraises_consumer_disconnect_without_masking_it():
    stream = ProgressStream()
    stream.close()
    with pytest.raises(ProgressStreamClosed):
        with stream.sealed():
            stream.publish({"n": 0})


def test_second_consumer_is_refused():
    async def main():
        stream = ProgressStream()
        stream.finish({"ok": True})
        first = [e async for e in stream.events()]
        with pytest.raises(RuntimeError, match="single consumer"):
            async for _event in stream.events():  # pragma: no cover
                pass
        return first

    assert _kinds(asyncio.run(main())) == ["result"]
