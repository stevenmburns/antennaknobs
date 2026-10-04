"""Opened decks: a NEC deck the user brings, carried by the link.

A visitor opens their own ``.nec`` / ``.ssn`` in the workbench — on the hosted
app as well as locally — without installing anything. The design is the
deck's TEXT, and the browser keeps it: the page's link carries it compressed
(``?deck=<deflate-raw, base64url>&name=<file name>``), and every request for
that design carries it again (``_deck``), so the server holds no state a
restart or a second machine could lose. The server parses it with the same
importer ``@path`` uses (`file_designs.builder_from_text`) and keeps the
parsed design in a small LRU keyed by a content hash: ``deck.<hash12>``.
Nothing is written to disk, and an opened deck never enters the user-design
registry that `user_designs.refresh` rebuilds. (Asked for by Dan Maguire
AC6LA, QRZ 1005128 #40/#42: let MMANA / 4nec2 / EZNEC users share and study a
non-catalog model with nothing installed, "even if frozen with no knobs".)

Because the text is a stranger's, everything about it is bounded:

- the text (64 KB) before anything parses it;
- the structure (3000 segments, 200 wires) BEFORE a card builds it
  (`nec_import.GeometryLimits`), including counts an SY symbol or a knob
  reaches and the copies GM / GR / GX make;
- each solve's wall time (60 s hosted), enforced by a watchdog that trips the
  solve's own momwire CancelToken (`DeckGate.hold`);
- concurrency: hosted, one opened-deck solve at a time server-wide. A request
  that would wait more than ~10 s for it is answered "busy" at once instead
  of queueing (`DeckGate`);
- how often one client may open a new deck (`RateLimiter`).

The catalog designs are untouched by all of this: they keep the per-session
lanes and no global slot.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import math
import os
import threading
import time
import zlib
from collections import OrderedDict, deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from pathlib import PurePath

DECK_NS = "deck"
_PREFIX = f"{DECK_NS}."

#: Where to send someone whose model is over a hosted limit.
RUN_LOCALLY = "run it locally (pip install antennaknobs[web]) for larger models"
#: ...and someone already running it locally: the designs folder opens a
#: bare .nec / .ssn with none of an opened deck's limits.
USE_DESIGNS_FOLDER = (
    "to open a larger model, put the file in your designs folder "
    "(~/.antennaknobs/designs), where these limits do not apply"
)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except ValueError:
        return default


def is_deck(geometry) -> bool:
    """True for an opened deck's design key."""
    return isinstance(geometry, str) and geometry.startswith(_PREFIX)


def deck_key(name: str, text: str, dialect: str | None = None) -> str:
    """The design key for a deck: its file name and text, hashed. The name is
    in the hash because it is the design's label, so the same text opened
    under two names is two designs that look different. A chosen dialect is
    in it too: the same deck read as NEC-2 and as NEC-5 is two designs (its
    sources half a segment apart). Detection (None) hashes as it always did,
    so a link from before the choice existed names the same design."""
    tail = "" if dialect is None else f"\0{dialect}"
    h = hashlib.sha256(f"{name}\0{text}{tail}".encode("utf-8", "surrogatepass"))
    return f"{_PREFIX}{h.hexdigest()[:12]}"


#: The dialects a deck may be read in when the reader chooses
#: (`nec_import.parse_nec`'s ``dialect``); absent means detect.
DIALECTS = ("nec2", "nec4", "nec5")


def payload_dialect(payload) -> str | None:
    """The dialect a deck payload chooses (``dialect``), None to detect.
    ``"auto"`` and an empty value are detection too; anything else not in
    `DIALECTS` is refused by name."""
    if not isinstance(payload, dict):
        return None
    d = payload.get("dialect")
    if d is None or d == "" or d == "auto":
        return None
    if d not in DIALECTS:
        raise DeckError(
            f"dialect must be one of {', '.join(DIALECTS)} (or auto), not {d!r}"
        )
    return d


class DeckError(RuntimeError):
    """A deck refused before (or instead of) a solve. ``status`` is the HTTP
    status the REST path answers with; ``deck_status`` the word the client
    keys its message on ("refused", "busy", "budget", "rate", "missing")."""

    def __init__(
        self, message: str, *, status: int = 422, deck_status: str = "refused"
    ):
        super().__init__(message)
        self.message = message
        self.status = status
        self.deck_status = deck_status
        # `user_designs.format_solve_error` prints this verbatim, with no
        # exception class name in front of the user's message.
        self._formatted_solve_error = message


class DeckBusy(DeckError):
    def __init__(self, message: str):
        super().__init__(message, status=503, deck_status="busy")


class DeckBudgetExceeded(DeckError):
    def __init__(self, message: str):
        super().__init__(message, status=503, deck_status="budget")


@dataclass
class DeckSettings:
    """The limits, all env-overridable. ``hosted`` decides the defaults: a
    local install bounds the text and the structure (a parse must not take
    the app down) but has no solve budget, no global slot and no rate."""

    hosted: bool
    max_bytes: int = 64 * 1024
    max_segments: int = 3000
    max_wires: int = 200
    # The compressed form a request may carry: generous over max_bytes'
    # worst case (incompressible text grows ~4/3 in base64).
    max_payload_chars: int = 128 * 1024
    max_open: int = 64
    budget_s: float = field(default=0.0)
    busy_wait_s: float = 10.0
    opens_per_min: int = 0

    @property
    def bigger(self) -> str:
        """Where a model over a limit should go instead."""
        return RUN_LOCALLY if self.hosted else USE_DESIGNS_FOLDER

    @classmethod
    def from_env(cls, hosted: bool) -> DeckSettings:
        return cls(
            hosted=hosted,
            max_bytes=int(_env_float("ANTENNAKNOBS_DECK_MAX_BYTES", 64 * 1024)),
            max_segments=int(_env_float("ANTENNAKNOBS_DECK_MAX_SEGMENTS", 3000)),
            max_wires=int(_env_float("ANTENNAKNOBS_DECK_MAX_WIRES", 200)),
            # 0 = no budget. Hosted 60 s: Steve, 2026-10-03.
            budget_s=_env_float("ANTENNAKNOBS_DECK_BUDGET_S", 60.0 if hosted else 0.0),
            busy_wait_s=_env_float("ANTENNAKNOBS_DECK_BUSY_WAIT_S", 10.0),
            opens_per_min=int(
                _env_float("ANTENNAKNOBS_DECK_OPENS_PER_MIN", 10 if hosted else 0)
            ),
        )


def decode_payload(payload, settings: DeckSettings) -> tuple[str, str]:
    """``(name, text)`` from a request's deck payload: ``{"name", "z"}`` with
    ``z`` the text deflate-raw compressed and base64url'd (what the link and
    the browser carry), or ``{"name", "text"}`` (curl). Refuses by name: an
    unsupported extension, an over-size or undecodable payload. The text is
    decompressed with a hard output bound, so a small payload cannot expand
    past ``max_bytes``."""
    if not isinstance(payload, dict):
        raise DeckError("the deck payload must be an object with name and z (or text)")
    raw_name = payload.get("name")
    name = PurePath(str(raw_name or "deck.nec").replace("\\", "/")).name.strip()
    if not name or len(name) > 120:
        name = "deck.nec"
    ext = PurePath(name).suffix.lower()
    if ext not in (".nec", ".ssn"):
        raise DeckError(
            f"{name}: the workbench opens .nec (NEC card deck) and .ssn (SimNEC) "
            "files; export the model to .nec from your program first"
        )
    limit = settings.max_bytes
    too_big = DeckError(
        f"{name} is over the {limit // 1024} KB limit for an opened deck; "
        f"{settings.bigger}",
        status=413,
    )
    if "text" in payload and payload.get("z") is None:
        text = payload["text"]
        if not isinstance(text, str):
            raise DeckError("text must be a string")
        if len(text.encode("utf-8", "surrogatepass")) > limit:
            raise too_big
        return name, text
    z = payload.get("z")
    if not isinstance(z, str) or not z:
        raise DeckError("the deck payload carries no deck (z)")
    if len(z) > settings.max_payload_chars:
        raise too_big
    try:
        packed = base64.urlsafe_b64decode(z + "=" * (-len(z) % 4))
        d = zlib.decompressobj(-15)  # raw deflate, the browser's 'deflate-raw'
        data = d.decompress(packed, limit + 1)
        if len(data) > limit or d.unconsumed_tail:
            raise too_big
        data += d.flush()
    except DeckError:
        raise
    except (ValueError, zlib.error) as exc:
        raise DeckError(f"{name}: the link's deck does not decode ({exc})") from None
    if len(data) > limit:
        raise too_big
    # Old decks in the wild carry cp1252/latin-1 comment text; geometry cards
    # are ASCII, so replace rather than refuse (as builder_from_file does).
    return name, data.decode("utf-8", errors="replace")


class RateLimiter:
    """At most ``per_min`` events per key in any 60 s window. 0 = off."""

    def __init__(self, per_min: int, clock=time.monotonic) -> None:
        self.per_min = per_min
        self._clock = clock
        self._seen: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.per_min <= 0:
            return True
        now = self._clock()
        with self._lock:
            q = self._seen.setdefault(key, deque())
            while q and now - q[0] >= 60.0:
                q.popleft()
            if len(q) >= self.per_min:
                return False
            q.append(now)
            # Forget idle clients so the table cannot grow without bound.
            if len(self._seen) > 4096:
                for k in [k for k, v in self._seen.items() if not v]:
                    del self._seen[k]
            return True


def client_ip(headers, peer: str | None) -> str:
    """The client address a limit is keyed by (``headers`` a mapping with
    lower-case names). Behind Fly's proxy the socket peer is the proxy, so
    the address is the proxy's own ``Fly-Client-IP``, which it sets on every
    request and overwrites when a client sends one; else the LAST
    ``X-Forwarded-For`` hop (the one the nearest proxy appended -- every
    earlier entry is client-supplied); else the socket peer."""
    fly = headers.get("fly-client-ip")
    if fly:
        return fly.strip()
    xff = headers.get("x-forwarded-for")
    if xff:
        last = xff.split(",")[-1].strip()
        if last:
            return last
    return peer or "unknown"


class _Watchdog:
    """Trips ``token`` after ``budget_s`` of wall time (never when 0)."""

    def __init__(self, token, budget_s: float) -> None:
        self.token = token
        self.fired = False
        self._timer = None
        if budget_s > 0 and token is not None:
            self._timer = threading.Timer(budget_s, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        self.fired = True
        self.token.cancel()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()


class DeckGate:
    """The opened decks' admission to compute: one server-wide slot (hosted)
    and a per-solve wall-time budget.

    The slot is held for one solve-shaped turn (a live solve, a sweep chunk,
    a parameter-sweep point, an optimizer eval ...). A turn that finds it
    taken by ANOTHER client asks how long the holder may still run -- at most
    the budget less what it has used -- and answers busy AT ONCE when that is
    over ``busy_wait_s``, rather than queueing a visitor behind a stranger's
    minute-long solve; a shorter wait is waited out. The holder is named by
    its session (``owner``): a client's own work never reads as "another
    deck", it waits its turn (the session lane already orders it). A turn
    with no session is always "another" client.
    """

    _POLL_S = 0.1

    def __init__(self, settings: DeckSettings, clock=time.monotonic) -> None:
        self.settings = settings
        self._clock = clock
        self._lock = threading.Lock()
        self._since: float | None = None
        self._owner = None

    @property
    def slot_enabled(self) -> bool:
        return self.settings.hosted

    def _remaining(self) -> float:
        b = self.settings.budget_s
        return math.inf if b <= 0 else max(0.0, b - (self._clock() - self._since))

    def expected_wait(self, owner=None) -> float | None:
        """None when the slot is free (or off) or ``owner`` holds it; else the
        longest the current holder may still run, in seconds (inf without a
        budget)."""
        if not self.slot_enabled:
            return None
        with self._lock:
            if self._since is None or (owner is not None and owner == self._owner):
                return None
            return self._remaining()

    def busy_message(self, wait: float) -> str:
        more = "" if math.isinf(wait) else f" (for up to {math.ceil(wait)} s more)"
        return (
            f"The server is busy with another opened deck{more}. Try again in a "
            f"minute — or {RUN_LOCALLY}."
        )

    def would_refuse(self, owner=None) -> str | None:
        """The busy message when ``owner``'s turn arriving now would be
        refused, else None."""
        wait = self.expected_wait(owner)
        if wait is not None and wait > self.settings.busy_wait_s:
            return self.busy_message(wait)
        return None

    def _try_acquire(self, owner) -> tuple[bool, bool, float]:
        """``(taken, own, wait)``: the slot taken now, or who holds it (this
        owner's own earlier work, or another client) and for how long more."""
        with self._lock:
            if self._since is None:
                self._since, self._owner = self._clock(), owner
                return True, False, 0.0
            own = owner is not None and owner == self._owner
            return False, own, self._remaining()

    def _release(self) -> None:
        with self._lock:
            self._since, self._owner = None, None

    def _step(self, started: float, owner) -> bool:
        """One acquisition attempt: True when taken; DeckBusy when another
        client's wait would be too long (or has already been)."""
        taken, own, wait = self._try_acquire(owner)
        if taken:
            return True
        if own:
            return False  # our own earlier turn: it ends within its budget
        waited = self._clock() - started
        if wait > self.settings.busy_wait_s or waited > self.settings.busy_wait_s + 5:
            raise DeckBusy(self.busy_message(wait))
        return False

    def budget_message(self) -> str:
        return (
            f"This deck took longer than the hosted server's "
            f"{self.settings.budget_s:g} s solve budget, so the solve was stopped; "
            f"{RUN_LOCALLY}."
        )

    def translate(self, dog: _Watchdog | None, exc: BaseException) -> BaseException:
        """``exc`` as the caller should see it: an abort the watchdog caused
        is the budget's message, anything else passes through."""
        import momwire

        # A native kernel's raw abort (the server's `_shed` maps it to
        # SolveAborted, but a thread-side caller sees it first) is one too.
        aborted = isinstance(exc, momwire.SolveAborted) or (
            type(exc).__name__ == "AcceleratorAborted"
        )
        if dog is not None and dog.fired and aborted:
            return DeckBudgetExceeded(self.budget_message())
        return exc

    @asynccontextmanager
    async def hold(self, token, owner=None):
        """One opened-deck turn, on the event loop. Yields the watchdog."""
        if self.slot_enabled:
            started = self._clock()
            while not self._step(started, owner):
                await asyncio.sleep(self._POLL_S)
        dog = _Watchdog(token, self.settings.budget_s)
        try:
            yield dog
        except BaseException as exc:
            out = self.translate(dog, exc)
            if out is not exc:
                raise out from None
            raise
        finally:
            dog.stop()
            if self.slot_enabled:
                self._release()

    @contextmanager
    def hold_sync(self, token, owner=None):
        """`hold` for a worker thread (a held sweep's solve)."""
        if self.slot_enabled:
            started = self._clock()
            while not self._step(started, owner):
                time.sleep(self._POLL_S)
        dog = _Watchdog(token, self.settings.budget_s)
        try:
            yield dog
        except BaseException as exc:
            out = self.translate(dog, exc)
            if out is not exc:
                raise out from None
            raise
        finally:
            dog.stop()
            if self.slot_enabled:
                self._release()


class DeckStore:
    """The parsed opened decks, an LRU by design key. ``register`` is the
    caller's hook that turns ``(key, builder class)`` into a registered
    design and ``unregister`` removes one, so this module never imports the
    web registry (and its tests need no server)."""

    def __init__(self, settings: DeckSettings, register, unregister) -> None:
        self.settings = settings
        self._register = register
        self._unregister = unregister
        self._decks: OrderedDict[str, tuple[str, str]] = OrderedDict()
        self._lock = threading.Lock()

    def limits(self):
        from antennaknobs.nec_import import GeometryLimits

        return GeometryLimits(
            self.settings.max_segments,
            self.settings.max_wires,
            note=f"that is over the limit for an opened deck; {self.settings.bigger}",
        )

    def get(self, key: str) -> tuple[str, str] | None:
        """``(name, text)`` of an open deck, touched as recently used."""
        with self._lock:
            hit = self._decks.get(key)
            if hit is not None:
                self._decks.move_to_end(key)
            return hit

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._decks

    def open(
        self, name: str, text: str, dialect: str | None = None
    ) -> tuple[str, bool]:
        """Parse and register a deck; ``(key, new)``. A deck already open is
        only touched. Parse errors and limit refusals raise `DeckError`.
        ``dialect`` is the reader's choice (`payload_dialect`), None to
        detect; it is part of the key."""
        from antennaknobs.file_designs import builder_from_text

        key = deck_key(name, text, dialect)
        if self.get(key) is not None:
            return key, False
        try:
            cls = builder_from_text(name, text, limits=self.limits(), dialect=dialect)
            cls()  # default_params construct, as user designs are checked
        except DeckError:
            raise
        except (ValueError, SystemExit) as exc:
            raise DeckError(str(exc)) from None
        except Exception as exc:  # noqa: BLE001 — a stranger's deck: any failure to import it is a refusal by name, never a 500
            raise DeckError(f"{name}: {type(exc).__name__}: {exc}") from None
        self._register(key, cls)
        evicted = []
        with self._lock:
            self._decks[key] = (name, text)
            self._decks.move_to_end(key)
            while len(self._decks) > self.settings.max_open:
                evicted.append(self._decks.popitem(last=False)[0])
        for old in evicted:
            self._unregister(old)
        return key, True
