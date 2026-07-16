"""Per-session single-lane solve scheduling (issue #382).

One :class:`SolveLane` per client session serializes every solve-producing
compute — the live ``/ws`` solve, each ``/sweep`` chunk, each ``/converge``
point, ``/norm_check``, ``/pattern``, ``/pattern_metrics``. Holding the lane
is the only way to compute, so "no two solver computations run concurrently
for one session" is structural, not a client-side heuristic.

Turns are granted by ``(priority, arrival)`` — the live solve always
outranks background batches — and carry the session's *generation*: the
client's monotonic ``_seq``/``_gen`` counter. Newer generations supersede
older work (queued turns raise :class:`Superseded`; the running turn's
CancelToken is tripped so it aborts at the next momwire solver checkpoint).
A turn of the same kind supersedes its predecessor regardless of generation:
the client re-issued the job, so the old stream is already abandoned.
"""

from __future__ import annotations

import asyncio
import itertools
from contextlib import asynccontextmanager

# Lane priority per job kind (lower wins). The live solve draws the heatmap
# the user is staring at; norm-check/pattern are single dwell-triggered
# solves; sweep/converge are long batches that should soak up whatever the
# lane has left. Unknown kinds sort last.
PRIORITY = {
    "live": 0,
    "norm_check": 1,
    "pattern": 1,
    "pattern_metrics": 1,
    "sweep": 2,
    "converge": 2,
}
_PRIORITY_DEFAULT = 9

# Kinds where a new arrival supersedes an older one of the same kind: the
# client holds at most one of each (re-issuing means the old stream is
# abandoned). pattern_metrics is deliberately absent — the compare table
# legitimately runs one request per design row at once.
SAME_KIND_SUPERSEDES = frozenset({"live", "sweep", "converge", "norm_check", "pattern"})


class Superseded(Exception):
    """Newer client intent overtook this turn before it ran; abandon the job.

    Raised out of ``lane.turn(...)`` — never after the turn was granted (a
    running turn is preempted via its CancelToken instead, surfacing as
    ``momwire.SolveAborted`` from the solver).
    """


def _default_token_factory():
    # Deferred so the lane primitive (and its unit tests) don't pay the
    # momwire import; the server passes real CancelTokens into the solvers.
    import momwire

    return momwire.CancelToken()


class _Turn:
    __slots__ = ("kind", "gen", "order", "ready", "token")

    def __init__(self, kind: str, gen: int | None, order: int, token) -> None:
        self.kind = kind
        self.gen = gen
        self.order = order
        self.token = token
        self.ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    @property
    def rank(self) -> tuple[int, int]:
        return (PRIORITY.get(self.kind, _PRIORITY_DEFAULT), self.order)


class SolveLane:
    """One serialized compute lane: a priority-ordered, generation-aware
    turnstile. All bookkeeping happens in synchronous stretches on the event
    loop (no locks needed); the only awaits are on a turn's grant future."""

    def __init__(self, token_factory=None) -> None:
        self._token_factory = token_factory or _default_token_factory
        self.gen = 0  # highest client generation seen
        self._order = itertools.count()
        self._running: _Turn | None = None
        self._waiting: list[_Turn] = []

    @property
    def idle(self) -> bool:
        return self._running is None and not self._waiting

    @asynccontextmanager
    async def turn(self, kind: str, gen: int | None = None):
        """Wait for exclusive compute rights; yield this turn's CancelToken.

        Raises :class:`Superseded` (possibly immediately — a request carrying
        a generation older than the lane's is stale on arrival) if newer
        intent overtakes this turn while it is queued.
        """
        t = _Turn(kind, gen, next(self._order), self._token_factory())
        self._supersede_overtaken_by(t)
        if t.gen is not None and t.gen < self.gen:
            raise Superseded  # stale on arrival: a newer generation exists
        self._waiting.append(t)
        self._grant_if_free()
        try:
            await t.ready
        except BaseException:
            # Superseded while queued, or the awaiting task itself was
            # cancelled (client torn down before the grant — or, in a narrow
            # race, just after it: release then too).
            if t in self._waiting:
                self._waiting.remove(t)
            self._release(t)
            raise
        try:
            yield t.token
        finally:
            self._release(t)

    def advance(self, gen: int | None) -> None:
        """Fold newer client intent into the lane without taking a turn.

        The /ws reader calls this the moment a newer request lands, so an
        older running compute (e.g. a benchmark-mesh sweep chunk) is
        preempted at its next checkpoint right away — the superseding live
        turn itself won't be admitted until the solver loop gets to it, and
        waiting for that would leave the stale chunk grinding meanwhile.
        """
        if gen is None or gen <= self.gen:
            return
        self.gen = gen
        for w in list(self._waiting):
            if w.gen is not None and w.gen < self.gen:
                self._waiting.remove(w)
                w.ready.set_exception(Superseded())
        r = self._running
        if r is not None and r.gen is not None and r.gen < self.gen:
            r.token.cancel()

    def _supersede_overtaken_by(self, new: _Turn) -> None:
        if new.gen is not None and new.gen > self.gen:
            self.gen = new.gen
        for w in list(self._waiting):
            if self._overtaken(w, new):
                self._waiting.remove(w)
                w.ready.set_exception(Superseded())
        r = self._running
        if r is not None and self._overtaken(r, new):
            # Preempt mid-compute: the solver raises SolveAborted at its next
            # checkpoint. (PyNEC solves have no checkpoints — they run out
            # their current call; admission bounds how long that can be.)
            r.token.cancel()

    def _overtaken(self, old: _Turn, new: _Turn) -> bool:
        if old.kind == new.kind and old.kind in SAME_KIND_SUPERSEDES:
            return True  # re-issued job: the old stream is abandoned
        return old.gen is not None and old.gen < self.gen

    def _grant_if_free(self) -> None:
        if self._running is not None or not self._waiting:
            return
        t = min(self._waiting, key=lambda w: w.rank)
        self._waiting.remove(t)
        self._running = t
        t.ready.set_result(None)

    def _release(self, t: _Turn) -> None:
        if self._running is t:
            self._running = None
        self._grant_if_free()


class LaneRegistry:
    """SolveLanes keyed by client session id.

    Sessions are minted client-side (one UUID per workbench tab) and stamped
    on every request as ``_session``. A request without one (curl, scripts,
    old clients) gets a private throwaway lane: admission still applies,
    serialization doesn't — cross-session coupling is explicitly not this
    module's job. Idle lanes are dropped on turn exit, so disconnect-only
    traffic can't leak entries.
    """

    def __init__(self, token_factory=None) -> None:
        self._token_factory = token_factory
        self._lanes: dict[str, SolveLane] = {}

    def lane(self, session: str | None) -> SolveLane:
        if session is None:
            return SolveLane(self._token_factory)
        found = self._lanes.get(session)
        if found is None:
            found = self._lanes[session] = SolveLane(self._token_factory)
        return found

    def advance(self, session: str | None, gen: int | None) -> None:
        """See :meth:`SolveLane.advance`. No-op for unknown/sessionless keys
        (nothing to preempt — a lane only exists while work is in it)."""
        if session is None:
            return
        found = self._lanes.get(session)
        if found is not None:
            found.advance(gen)

    @asynccontextmanager
    async def turn(self, session: str | None, kind: str, gen: int | None = None):
        # No await between the lookup and the waiter registering inside
        # lane.turn's entry, so a lane can't be reaped out from under a
        # not-yet-registered waiter.
        found = self.lane(session)
        try:
            async with found.turn(kind, gen) as token:
                yield token
        finally:
            if session is not None and found.idle:
                self._lanes.pop(session, None)

    def __len__(self) -> int:  # observability + tests
        return len(self._lanes)


@asynccontextmanager
async def cancel_on_disconnect(request, token, interval: float = 0.25):
    """Trip ``token`` if the HTTP client goes away mid-compute.

    The streaming endpoints only used to notice a disconnect *between*
    chunks — useless when one benchmark-mesh chunk takes minutes. This
    watcher polls ``request.is_disconnected()`` for the duration of a turn,
    so an abandoned tab stops the burn at the next solver checkpoint.
    """

    async def _watch() -> None:
        while not await request.is_disconnected():
            await asyncio.sleep(interval)
        token.cancel()

    task = asyncio.create_task(_watch())
    try:
        yield
    finally:
        task.cancel()
