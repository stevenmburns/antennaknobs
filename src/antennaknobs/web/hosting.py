"""What only the hosted instance does: crash reports from visitors' browsers,
session pinning across a fleet of machines, and usage counters.

Everything here is dormant on a local workbench. Crash reports and counters
are gated on ``ANTENNAKNOBS_HOSTED`` (server._HOSTED), so nothing a local
install does ever reports anywhere (the #846 beacon rule: nothing phones home
from a local install). Pinning is gated on ``FLY_MACHINE_ID``, which Fly sets
on its machines and nothing else does.

Crash reports (AK#1851)
-----------------------
The frontend's error boundary and its global ``error`` /
``unhandledrejection`` handlers POST ``/client-error``; the hosted server logs
ONE line per report and stores nothing. The line carries exactly three
fields, each bounded and scrubbed:

- ``message``: the error's message;
- ``component_stack``: React's component stack, when the boundary caught it;
- ``version``: the antennaknobs version the page was served by.

No IP, no URL, no user agent, no deck text, no knob values. The ``?deck=``
link carries a visitor's whole deck, so anything shaped like a URL query or
fragment is cut out of both text fields before the line is written (the
frontend cuts it too; the server does not trust that). The client address
keys the per-client rate limit in memory and is never written.

Session pinning (AK#405)
------------------------
Three things assume one page's requests reach one machine: the lane rule
(one solve at a time per session, ``LaneRegistry`` is per process), the
opened-deck cache (``deck.<sha12>`` is parsed into one machine's memory), and
the per-machine limits. With more than one machine, Fly's edge routes each
request to the nearest healthy one, which a session's requests need not share.

So the page pins itself, and the server only says where it is:

- every HTTP response carries ``X-AK-Machine: <FLY_MACHINE_ID>``;
- the ``/ws`` channel's first message is ``{"_kind": "machine", "id": ...}``;
- the page sends ``fly-force-instance-id: <id>`` on its requests, which Fly's
  proxy routes to that machine (https://fly.io/docs/networking/dynamic-request-routing/);
- a browser cannot set a header on a WebSocket, so the page asks for its
  machine in the ``/ws`` URL (``?fly_instance=<id>``), and a machine that is
  not that one answers the upgrade with ``fly-replay: instance=<id>`` instead
  of accepting it, which the proxy replays to the right machine (the same
  page: "an application returning fly-replay headers should not negotiate a
  web socket upgrade itself").

Off Fly there is no machine id: no header, no first message, no replay, and
the page never pins, so every request is byte-identical to before.

Usage counters (AK#405)
-----------------------
Prometheus counters, per machine, served on their own port (``[metrics]`` in
fly.toml points Fly's scraper at it; it is not behind the public
``[http_service]``). No IP, no session id, no deck content: every label is
drawn from a fixed roster, so the series count is bounded by the catalog and
the engine and ground rosters.

- ``ak_solves_total{design, engine, ground}``: live solves the server paid
  for (cache hits and failures excluded);
- ``ak_sessions_total{kind}``: live-solve connections, by what their first
  solve was of (``catalog`` / ``user`` / ``deck``);
- ``ak_deck_opens_total{dialect, outcome}``: ``POST /deck``, by the dialect it
  was read in and ``ok`` / ``refused`` / ``busy``.

``design`` is the catalog name, or the literal ``deck`` or ``user``, never a
file name or hash. Off unless hosted.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from . import decks as _decks

_logger = logging.getLogger("antennaknobs.client_error")

# Field caps. A message is a sentence; a component stack is a few dozen
# component frames. Longer is either a runaway or someone's payload.
MESSAGE_MAX = 500
STACK_MAX = 4000
# The body the endpoint reads at all (the two caps above, JSON-escaped, with
# room to spare). Larger is refused unread.
BODY_MAX = 16 * 1024

# Per-client and fleet-wide budgets, per minute. The client side already sends
# at most a few per page load; these bound what a script could make the log
# say, per address and in total.
PER_CLIENT_PER_MIN = 6
TOTAL_PER_MIN = 120

_VERSION_RE = re.compile(r"[0-9A-Za-z.+\-]{1,40}")
# A URL's query and fragment, and any bare `?k=v...` / `deck=...` run: the
# opened-deck link carries a whole deck in its query.
_URL_TAIL_RE = re.compile(
    r"((?:[a-z][a-z0-9+.\-]*:)?//[^\s?#)'\"]*)[?#][^\s)'\"]*", re.I
)
_QUERY_RE = re.compile(r"\?[^\s)'\"]*=[^\s)'\"]*")
_DECK_PARAM_RE = re.compile(r"\bdeck=[^\s&)'\"]*")


def scrub(text: str) -> str:
    """``text`` with every URL query and fragment, and any deck parameter,
    cut out."""
    text = _URL_TAIL_RE.sub(r"\1", text)
    text = _QUERY_RE.sub("", text)
    return _DECK_PARAM_RE.sub("deck=…", text)


def _field(value, cap: int) -> str:
    if not isinstance(value, str):
        return ""
    text = scrub(value)
    return text if len(text) <= cap else text[:cap] + "…"


def client_error_record(payload) -> dict:
    """The three fields a report is logged with, bounded and scrubbed.
    Anything else in ``payload`` is dropped unread."""
    if not isinstance(payload, dict):
        payload = {}
    version = payload.get("version")
    return {
        "message": _field(payload.get("message"), MESSAGE_MAX),
        "component_stack": _field(payload.get("component_stack"), STACK_MAX),
        "version": (
            version
            if isinstance(version, str) and _VERSION_RE.fullmatch(version)
            else "unknown"
        ),
    }


class ClientErrorSink:
    """Rate-limits and logs crash reports. One per process."""

    def __init__(
        self,
        per_client: int = PER_CLIENT_PER_MIN,
        total: int = TOTAL_PER_MIN,
    ) -> None:
        self._per_client = _decks.RateLimiter(per_client)
        self._total = _decks.RateLimiter(total)

    def report(self, payload, client: str) -> bool:
        """Log ``payload``'s record unless ``client`` (an address, used as a
        key only) or the fleet is over its budget. True if logged."""
        if not self._per_client.allow(client) or not self._total.allow("*"):
            return False
        record = client_error_record(payload)
        _logger.warning("client-error: %s", json.dumps(record, ensure_ascii=False))
        return True


# ---------------------------------------------------------------------------
# Session pinning (AK#405)
# ---------------------------------------------------------------------------

MACHINE_HEADER = "x-ak-machine"
# The /ws query parameter a pinned page names its machine with.
WS_PIN_PARAM = "fly_instance"
# Fly machine ids are short lowercase hex; anything else is not one, and is
# never echoed into a header.
_MACHINE_ID_RE = re.compile(r"[0-9a-z]{1,64}")


def machine_id() -> str | None:
    """This machine's Fly id, or None off Fly (or for a malformed value)."""
    mid = os.environ.get("FLY_MACHINE_ID", "").strip()
    return mid if _MACHINE_ID_RE.fullmatch(mid) else None


def machine_hello() -> str | None:
    """The /ws channel's first message on Fly, None elsewhere."""
    mid = machine_id()
    return json.dumps({"_kind": "machine", "id": mid}) if mid else None


def _ws_pin(scope) -> str | None:
    raw = scope.get("query_string", b"").decode("latin-1")
    want = parse_qs(raw).get(WS_PIN_PARAM, [None])[0]
    return want if want and _MACHINE_ID_RE.fullmatch(want) else None


class HostingMiddleware:
    """Pure ASGI. On Fly: stamps ``X-AK-Machine`` on every HTTP response and
    replays a ``/ws`` upgrade pinned to another machine there. Off Fly it
    passes HTTP and WebSocket scopes through untouched.

    ``on_startup`` runs once at the server's lifespan startup (the hosted
    metrics endpoint), never at import, so importing the app in a test or a
    second interpreter binds no port."""

    def __init__(self, app, on_startup=None) -> None:
        self.app = app
        self.on_startup = on_startup

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind == "lifespan":
            if self.on_startup is not None:
                self.on_startup()
            await self.app(scope, receive, send)
            return
        mid = machine_id()
        if mid is None:
            await self.app(scope, receive, send)
            return
        if kind == "websocket":
            want = _ws_pin(scope)
            if want is not None and want != mid:
                await self._replay(scope, send, want)
                return
            await self.app(scope, receive, send)
            return
        if kind != "http":
            await self.app(scope, receive, send)
            return
        stamp = (MACHINE_HEADER.encode(), mid.encode())

        async def stamped(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [*message.get("headers", []), stamp]
            await send(message)

        await self.app(scope, receive, stamped)

    @staticmethod
    async def _replay(scope, send, want: str) -> None:
        if "websocket.http.response" in scope.get("extensions", {}):
            await send(
                {
                    "type": "websocket.http.response.start",
                    "status": 409,
                    "headers": [
                        (b"fly-replay", f"instance={want}".encode()),
                        (b"content-length", b"0"),
                    ],
                }
            )
            await send({"type": "websocket.http.response.body", "body": b""})
        else:
            # A server without the denial-response extension cannot replay;
            # refusing the upgrade sends the page back unpinned.
            await send({"type": "websocket.close", "code": 1013})


# ---------------------------------------------------------------------------
# Usage counters (AK#405)
# ---------------------------------------------------------------------------

METRICS_PORT_DEFAULT = 9091
METRICS_PATH = "/metrics"

_GROUNDS = frozenset({"fast", "sommerfeld", "mininec", "pec", "terrain"})
_EXTERNAL_ENGINES = frozenset({"pynec", "nec5", "nec2", "nec42"})
_DECK_DIALECTS = frozenset({"nec2", "nec4", "nec5"})

_HELP = {
    "ak_solves_total": (
        "Live solves the server paid for (cache hits and failures excluded).",
        ("design", "engine", "ground"),
    ),
    "ak_sessions_total": (
        "Live-solve connections, by what their first solve was of.",
        ("kind",),
    ),
    "ak_deck_opens_total": (
        "Opened decks (POST /deck), by dialect read in and outcome.",
        ("dialect", "outcome"),
    ),
}


def design_label(key, catalog) -> str:
    """The catalog name, or the literal ``deck`` / ``user``; ``other`` for a
    key the catalog does not hold (never a file name or hash)."""
    if not isinstance(key, str):
        return "other"
    if key.startswith("deck."):
        return "deck"
    if key.startswith("user."):
        return "user"
    return key if key in catalog else "other"


def session_kind(key, catalog) -> str:
    label = design_label(key, catalog)
    if label in ("deck", "user", "other"):
        return label
    return "catalog"


def engine_label(req: dict, momwire_models) -> str:
    """The solver from the fixed roster: an external engine's name, the
    momwire model, or ``other``."""
    solver = req.get("solver")
    if solver in _EXTERNAL_ENGINES:
        return solver
    if solver in (None, "momwire"):
        model = req.get("momwire_model")
        if model is None:
            return "momwire"
        return model if model in momwire_models else "other"
    return "other"


def ground_label(req: dict, model) -> str:
    """``free`` with ground off, else the ground model from the fixed roster."""
    if not req.get("ground", False):
        return "free"
    return model if model in _GROUNDS else "other"


def dialect_label(dialect) -> str:
    """A deck's dialect from the fixed set: ``nec2`` / ``nec4`` / ``nec5``,
    ``ssn`` (a SimNEC file, no NEC cards), ``auto`` (detection asked for, on
    a refusal before anything was read), else ``other``."""
    if dialect in _DECK_DIALECTS or dialect == "ssn":
        return dialect
    if dialect in (None, "", "auto"):
        return "auto"
    return "other"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class UsageCounters:
    """The hosted instance's counters. ``enabled=False`` (a local workbench)
    makes every ``inc`` a no-op and the exposition empty."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()
        self._counts: dict[str, dict[tuple[str, ...], int]] = {n: {} for n in _HELP}

    def inc(self, name: str, *labels: str) -> None:
        if not self.enabled:
            return
        names = _HELP[name][1]
        if len(labels) != len(names):
            raise ValueError(f"{name} takes labels {names}, got {labels}")
        with self._lock:
            series = self._counts[name]
            series[labels] = series.get(labels, 0) + 1

    def value(self, name: str, *labels: str) -> int:
        with self._lock:
            return self._counts[name].get(labels, 0)

    def series(self, name: str) -> dict[tuple[str, ...], int]:
        with self._lock:
            return dict(self._counts[name])

    def exposition(self) -> str:
        """The Prometheus text format (version 0.0.4)."""
        if not self.enabled:
            return ""
        lines = []
        with self._lock:
            for name, (help_text, names) in _HELP.items():
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} counter")
                for labels, n in sorted(self._counts[name].items()):
                    body = ",".join(
                        f'{k}="{_escape(v)}"'
                        for k, v in zip(names, labels, strict=True)
                    )
                    lines.append(f"{name}{{{body}}} {n}")
        return "\n".join(lines) + "\n"


def metrics_port() -> int:
    """``ANTENNAKNOBS_METRICS_PORT``, else 9091 (fly.toml's ``[metrics]``
    port, which must agree). 0 takes any free port."""
    try:
        port = int(os.environ.get("ANTENNAKNOBS_METRICS_PORT", ""))
    except ValueError:
        return METRICS_PORT_DEFAULT
    return port if 0 <= port < 65536 else METRICS_PORT_DEFAULT


def serve_metrics(
    counters: UsageCounters, host: str = "0.0.0.0", port: int | None = None
) -> ThreadingHTTPServer:
    """Serve ``counters`` at ``/metrics`` on their own port, from a daemon
    thread. Fly scrapes it on 0.0.0.0 (https://fly.io/docs/monitoring/metrics/);
    it is not behind the public ``[http_service]``, so the edge never serves
    it. Returns the server (its ``server_address`` has the bound port)."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] != METRICS_PATH:
                self.send_error(404)
                return
            body = counters.exposition().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:
            # A scrape every 15 s would otherwise be a log line every 15 s.
            return

    srv = ThreadingHTTPServer(
        (host, metrics_port() if port is None else port), _Handler
    )
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name="ak-metrics", daemon=True).start()
    return srv
