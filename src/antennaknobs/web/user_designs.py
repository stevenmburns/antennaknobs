"""Web-layer glue for user-authored antenna designs.

The discovery + path-loading core lives in ``antennaknobs.user_designs``
(no web dependency, shared with the CLI). This module layers on the bits that
are specific to the running web app: registering each design into ``REGISTRY``
under ``user.<filename>``, scaffolding the folder on first run, and formatting
load errors for the "failed to load" UI panel.
"""

from __future__ import annotations

import os
import shutil
import traceback
from pathlib import Path

from antennaknobs.design_trust import DesignNotTrustedError
from antennaknobs.user_designs import (
    USER_NS,
    default_user_dir,
    iter_design_files,
    load_builder,
    user_design_dirs,
)

from . import adapter
from .examples import REGISTRY

__all__ = [
    "USER_NS",
    "default_user_dir",
    "user_design_dirs",
    "ensure_scaffold",
    "refresh",
    "format_solve_error",
]

_ASSETS = Path(__file__).resolve().parent / "user_design_assets"


def ensure_scaffold() -> None:
    """Create the default user folder and keep its reference assets current.

    ``TEMPLATE.py`` and ``CLAUDE.md`` are shipped documentation, not user
    content — the workflow is copy-then-rename, so they're safe to refresh from
    the packaged copies on every startup. That's what lets an *existing* install
    pick up updated authoring guidance (e.g. the design_freq tuning note) after
    an upgrade, not just brand-new folders. Any other ``*.py`` in the folder is
    a user design and is never touched.

    Idempotent and best-effort — never raises into startup."""
    d = default_user_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        for asset in ("TEMPLATE.py", "CLAUDE.md"):
            src = _ASSETS / asset
            if src.is_file():
                shutil.copyfile(src, d / asset)
    except OSError as exc:  # read-only home, permissions, … — log and move on
        print(f"[user_designs] could not scaffold {d}: {exc!r}")


def _format_error(path: Path, exc: Exception) -> str:
    """A short, user-facing message pointing at the line in *their* file."""
    tb = traceback.extract_tb(exc.__traceback__)
    here = [fr for fr in tb if fr.filename == str(path)]
    where = f" (line {here[-1].lineno})" if here else ""
    return f"{type(exc).__name__}: {exc}{where}"


def format_solve_error(exc: BaseException) -> str:
    """Format a solve/geometry-time exception for the UI error banner.

    Geometry now builds lazily on selection, so a user design's build_wires()
    error surfaces here rather than in the load panel. Point at the deepest
    frame inside a user-design folder when the failure came from someone's own
    file (the common case); otherwise fall back to just type + message.
    """
    tb = traceback.extract_tb(exc.__traceback__)
    dirs: list[str] = []
    for d in user_design_dirs():
        try:
            dirs.append(str(d.resolve()))
        except OSError:
            dirs.append(str(d))
    frame = None
    for fr in tb:
        try:
            fp = str(Path(fr.filename).resolve())
        except OSError:
            fp = fr.filename
        if any(fp == d or fp.startswith(d + os.sep) for d in dirs):
            frame = fr  # keep the deepest (last) frame in a user folder
    where = f" ({Path(frame.filename).name}, line {frame.lineno})" if frame else ""
    return f"{type(exc).__name__}: {exc}{where}"


def refresh() -> list[dict]:
    """Reload every user design into ``REGISTRY`` under ``user.<filename>``,
    replacing any previously-loaded user designs.

    Returns a list of ``{"name", "file", "message"}`` for files that failed to
    load — surfaced in the UI so the author (or Claude) can fix them. A broken
    file never takes down the rest.
    """
    for key in [k for k in REGISTRY if k.startswith(f"{USER_NS}.")]:
        del REGISTRY[key]

    errors: list[dict] = []
    for stem, path in iter_design_files():
        name = f"{USER_NS}.{stem}"
        try:
            cls = load_builder(path)
            # Construct (cheap — validates default_params) but do NOT run
            # build_wires here: registration must not execute a user's geometry
            # code, so a slow or hanging builder can't stall startup or a page
            # refresh. defer_hints=True pushes every build_wires-derived hint to
            # the first solve/geometry of this design. Geometry errors therefore
            # surface on selection (via the solve/geometry error path) rather
            # than in this load panel — import/syntax/construction errors still
            # surface here.
            cls()
            REGISTRY[name] = adapter._make_example(name, cls, defer_hints=True)
        except DesignNotTrustedError as exc:
            # Not an error — the user just hasn't trusted this file to run yet.
            # Surface it distinctly (with the advisory) so the UI can offer a
            # trust prompt rather than showing it as a broken design.
            errors.append(
                {
                    "name": name,
                    "file": str(path),
                    "trust_required": True,
                    "message": str(exc),
                    "advisory": [
                        {
                            "severity": f.severity,
                            "message": f.message,
                            "line": f.lineno,
                        }
                        for f in exc.report.findings
                    ],
                }
            )
        except Exception as exc:  # noqa: BLE001 — surface, don't crash
            errors.append(
                {
                    "name": name,
                    "file": str(path),
                    "trust_required": False,
                    "message": _format_error(path, exc),
                }
            )
    return errors
