"""What the external engines saw — the two knobs behind AK#1428.

A user whose NEC-5 or NEC-2 run disagrees with ours needs to send us exactly
what the engine was given and exactly what it printed, and needs to see the
deck themselves (the ``EX`` card is usually the question). Two environment
variables, read once per process, serve both:

``ANTENNAKNOBS_LOG_LEVEL``
    ``DEBUG`` / ``INFO`` / ``WARNING`` … Sets the level of the ``antennaknobs``
    logger tree (not the root, so uvicorn's and matplotlib's own chatter stay
    at their defaults) and installs a stderr handler if no handler exists
    yet. At ``INFO`` every engine run is one line (deck hash, seconds,
    printout length); at ``DEBUG`` the full deck text goes to the log before
    the binary runs and the full printout after it.

``ANTENNAKNOBS_CAPTURE_DIR``
    A directory. Every engine run writes ``<engine>/<hash>.nec`` (the deck)
    and ``<engine>/<hash>.out`` (the printout) under it, ``<engine>`` being
    ``nec5`` or ``nec2``. This is the file pair to attach to a report. For
    NEC-5 it is the engine's existing ``capture_dir`` (#872): a deck whose
    printout is already there is served from disk without running the
    binary. For NEC-2 it is write-only.

The frozen workbench exposes them as ``--log-level`` and ``--capture-dir``
(``scripts/freeze_workbench/entry.py``); the server and the CLI read the
variables from their launch environment. Unset, nothing changes: no handler
is installed and no file is written.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

LOG_LEVEL_ENV = "ANTENNAKNOBS_LOG_LEVEL"
CAPTURE_DIR_ENV = "ANTENNAKNOBS_CAPTURE_DIR"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging_from_env() -> int | None:
    """Apply ``ANTENNAKNOBS_LOG_LEVEL`` to the ``antennaknobs`` logger tree.

    Returns the numeric level applied, or None when the variable is unset.
    Idempotent: a second call re-applies the level and installs no second
    handler. A misspelt level raises ``ValueError`` naming it, rather than
    silently logging nothing — the whole point of setting it is to see
    something."""
    raw = os.environ.get(LOG_LEVEL_ENV, "").strip()
    if not raw:
        return None
    level = logging.getLevelName(raw.upper())
    if not isinstance(level, int):
        raise ValueError(
            f"{LOG_LEVEL_ENV}={raw!r} is not a log level "
            "(DEBUG, INFO, WARNING, ERROR, CRITICAL)"
        )
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(handler)
    logging.getLogger("antennaknobs").setLevel(level)
    return level


def capture_dir_from_env(engine: str) -> Path | None:
    """``ANTENNAKNOBS_CAPTURE_DIR/<engine>`` as a Path, or None when unset."""
    raw = os.environ.get(CAPTURE_DIR_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser() / engine
