"""What only the hosted instance does: crash reports from visitors' browsers.

Everything here is dormant on a local workbench. The server consults
``ANTENNAKNOBS_HOSTED`` (server._HOSTED) before calling in, so nothing a
local install does ever reports anywhere (the #846 beacon rule: nothing
phones home from a local install).

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
"""

from __future__ import annotations

import json
import logging
import re

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
