"""Thread-safe progress bridge: threadpool worker → asyncio consumer (issue #773).

The optimiser's objective runs under ``run_in_threadpool``, so its
``on_progress`` callback fires on an anyio worker thread and cannot ``await``.
The endpoint that streams those events is an async ``StreamingResponse`` on the
event loop. :class:`ProgressStream` is that bridge and nothing else — no web
framework, no optimiser import — so its concurrency claims are provable in
isolation. Producer side is :meth:`ProgressStream.publish` (one dict, matching
the ``Callable[[dict], None]`` of contract C3); consumer side is
:meth:`ProgressStream.events`.

Why this mechanism
------------------
``asyncio.Queue`` is not thread safe: its ``put_nowait`` mutates a deque and
wakes futures with no lock, so calling it from a worker corrupts waiter state
under contention — the classic defect that survives single-user local dev and
falls over under load. ``queue.Queue.get`` is thread safe but *blocks*, which
on the loop thread stalls every other request; wrapping it in
``run_in_executor`` costs one more parked thread per pending get, which is the
same disease. ``janus`` exists precisely for this and would be the obvious
answer, but a new third-party dependency is out of scope here.

So: a plain :class:`collections.deque` under a :class:`threading.Lock` holds
the events (mutation from either thread is safe), and the consumer is woken
through ``loop.call_soon_threadsafe`` — the *only* loop API documented as
callable from another OS thread.

INVARIANT: no asyncio object is touched from the worker thread except
``loop.call_soon_threadsafe`` inside :meth:`_wake_consumer`. That method is the
single documented entry point; everything else the producer calls (``publish``,
``finish``, ``fail``, ``close``) touches only the lock, the deque and plain
attributes. The loop reference itself is captured by the *consumer* in
:meth:`events` and only ever read (under the lock) by ``_wake_consumer``.

Bounded queue: drop oldest, with a counter
------------------------------------------
The buffer is capped at ``maxsize`` and a full ``publish`` discards the OLDEST
pending event, increments :attr:`dropped`, and returns without blocking.
Rejected alternatives and why:

* *Unbounded* — a browser that stops reading (backgrounded tab, dead TCP
  socket that has not timed out yet) grows the buffer for the whole run.
* *Block, with or without timeout* — parks an anyio worker thread on a
  consumer that may never drain. anyio's default limiter is 40 threads for the
  whole process, so a handful of stalled browsers stalls every solve on the
  box. A blocked producer is exactly the "works locally, fails under load"
  failure this unit exists to rule out.

Dropping the oldest (rather than the newest) is what a progress readout wants:
these events are *state*, not a ledger. A superseded eval count / objective /
SWR has no value once a newer one exists, so a slow consumer should see the
current state, not a stale prefix. Delivered events keep their relative order —
they are a subsequence of what was published, never a reordering.

Terminal events bypass the bound entirely: they are stored in a separate slot,
so the run's actual result can never be dropped no matter how far behind the
consumer is.

Termination
-----------
Exactly one terminal event (``result`` or ``error``) ends a stream, matching
contract C2. The iterator yields it and then stops, so a consumer can always
distinguish "the run ended" (iteration finished, and the last event says how)
from "nothing yet" (iteration still pending). Teardown works from either end:

* consumer gone — :meth:`events` calls :meth:`close` on exit (return, break,
  task cancellation, generator finalisation), after which :meth:`publish`
  raises :class:`ProgressStreamClosed` on the worker, which propagates out of
  the objective and aborts the run promptly instead of computing solves nobody
  will read.
* producer gone — :meth:`sealed` guarantees a terminal event even if the
  producer raises or returns without one, so the consumer can never hang
  waiting on a thread that has already died.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

# Event kinds are the SSE event names of contract C2 verbatim, so a consumer
# can frame one as ``f"event: {ev.kind}\ndata: {json.dumps(ev.data)}\n\n"``
# without a translation table.
EventKind = Literal["progress", "result", "error"]

_TERMINAL_KINDS = ("result", "error")

# Events buffered before the oldest starts being dropped. One progress event is
# a few hundred bytes and is produced at most once per MoM solve (seconds
# apart), so this is minutes of backlog for a consumer that is merely slow —
# deep enough that only a consumer that has genuinely stopped reading hits it.
DEFAULT_MAXSIZE = 64


class ProgressStreamClosed(RuntimeError):
    """Raised by :meth:`ProgressStream.publish` once the stream is finished —
    the consumer disconnected, its loop died, or a terminal event was already
    delivered. Producers are expected to let it propagate: it is the signal
    that the work being reported on is no longer wanted."""


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """One SSE-shaped event. ``data`` is the caller's payload, stored by
    reference and never mutated by this module."""

    kind: EventKind
    data: dict

    @property
    def terminal(self) -> bool:
        return self.kind in _TERMINAL_KINDS


class ProgressStream:
    """A single-producer / single-consumer bridge from a worker thread to the
    event loop. See the module docstring for the mechanism and the drop policy.

    Every public method is safe to call from any thread. Only :meth:`events`
    requires a running loop, and only it may be called concurrently by one
    consumer.
    """

    def __init__(self, *, maxsize: int = DEFAULT_MAXSIZE) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self._maxsize = int(maxsize)
        self._lock = threading.Lock()
        self._pending: deque[ProgressEvent] = deque()
        self._terminal: ProgressEvent | None = None
        self._closed = False
        self._dropped = 0
        # Written once by the consumer in events(); read under the lock by
        # _wake_consumer. The producer never touches either object directly.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None

    # -- producer side (any thread) -----------------------------------------

    def publish(self, payload: dict) -> None:
        """Queue one ``progress`` event. Never blocks.

        Signature-compatible with contract C3's ``on_progress``. Raises
        :class:`ProgressStreamClosed` if nobody is listening any more.
        """
        with self._lock:
            if self._closed:
                raise ProgressStreamClosed("progress stream closed by consumer")
            if self._terminal is not None:
                raise ProgressStreamClosed("progress stream already terminated")
            if len(self._pending) >= self._maxsize:
                self._pending.popleft()
                self._dropped += 1
            self._pending.append(ProgressEvent("progress", payload))
        self._wake_consumer()

    def finish(self, result: dict) -> bool:
        """Terminate the stream with the run's final payload. Returns False if
        the stream was already terminal or closed (first terminal wins, so a
        late ``fail`` after a ``finish`` cannot rewrite history)."""
        return self._terminate("result", result)

    def fail(self, detail: str) -> bool:
        """Terminate the stream with an error. Returns False if already
        terminal or closed."""
        return self._terminate("error", {"detail": detail})

    def close(self) -> None:
        """Abandon the stream from either end. Idempotent. Pending events are
        discarded and the next :meth:`publish` raises. The consumer calls this
        on its way out; a producer can call it to disown a stream nobody
        terminated."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._pending.clear()
        self._wake_consumer()

    @contextmanager
    def sealed(self) -> Iterator[ProgressStream]:
        """Guarantee exactly one terminal event around a producer body.

        An exception escaping the body becomes an ``error`` event before it
        propagates; a body that returns without calling :meth:`finish` gets a
        terminal event anyway. Without this, a producer that dies between
        events leaves the consumer awaiting a thread that no longer exists.
        :class:`ProgressStreamClosed` is re-raised untouched — the consumer is
        already gone, so there is nothing left to seal.
        """
        try:
            yield self
        except ProgressStreamClosed:
            raise
        except BaseException as exc:
            self.fail(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            # No-op when a terminal event was already set.
            self.fail("producer exited without a result")

    # -- consumer side (event loop only) ------------------------------------

    async def events(self) -> AsyncIterator[ProgressEvent]:
        """Yield events in publication order, ending with the terminal one.

        Iteration stops after a ``result``/``error`` event, or immediately if
        the stream was closed without one. :meth:`close` runs on the way out
        however iteration ends, so a disconnected client tears the producer
        down.
        """
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._loop is not None:
                raise RuntimeError("ProgressStream supports a single consumer")
            self._loop = loop
            self._wake = asyncio.Event()
        wake = self._wake
        try:
            while True:
                # Clear BEFORE draining: a publish that lands between the
                # drain and the await has already scheduled its set(), which
                # then runs on the loop and cannot be lost.
                wake.clear()
                while True:
                    event, last = self._take()
                    if event is not None:
                        yield event
                    if last:
                        return
                    if event is None:
                        break  # drained; go wait
                await wake.wait()
        finally:
            self.close()

    def __aiter__(self) -> AsyncIterator[ProgressEvent]:
        return self.events()

    # -- state ---------------------------------------------------------------

    @property
    def dropped(self) -> int:
        """Progress events discarded because the consumer fell behind. A
        consumer can report this alongside the result; a non-zero value means
        the readout skipped evals, never that the run did."""
        with self._lock:
            return self._dropped

    @property
    def done(self) -> bool:
        """True once a terminal event exists or the stream was closed — i.e.
        no further progress will ever be published."""
        with self._lock:
            return self._closed or self._terminal is not None

    # -- internals -----------------------------------------------------------

    def _terminate(self, kind: EventKind, data: dict) -> bool:
        with self._lock:
            if self._closed or self._terminal is not None:
                return False
            self._terminal = ProgressEvent(kind, data)
        self._wake_consumer()
        return True

    def _take(self) -> tuple[ProgressEvent | None, bool]:
        """Pop the next deliverable event. Returns ``(event, last)``; a None
        event with ``last`` False means "drained, nothing terminal yet"."""
        with self._lock:
            if self._pending:
                return self._pending.popleft(), False
            if self._terminal is not None:
                # Terminal delivered: the stream is over, so later publishes
                # must raise rather than queue into a stream nobody reads.
                self._closed = True
                return self._terminal, True
            return None, self._closed

    def _wake_consumer(self) -> None:
        """THE loop entry point (see the module invariant). Called from either
        thread; a no-op until a consumer has bound its loop."""
        with self._lock:
            loop, wake = self._loop, self._wake
        if loop is None or wake is None:
            return
        try:
            loop.call_soon_threadsafe(wake.set)
        except RuntimeError:
            # Loop already closed — the consumer's process/task is gone for
            # good, so close so the producer's next publish raises rather than
            # queueing into a void. (A merely *stopped* loop accepts the
            # callback silently; only a closed one raises.)
            with self._lock:
                self._closed = True
                self._pending.clear()
