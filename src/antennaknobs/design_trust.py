"""Explicit, content-pinned trust for user-authored design files.

A user design runs with your full privileges when it loads (full Python is a
deliberate feature — see ``design_screen``). Since the language can't be a
safety boundary, the boundary is an explicit human trust decision, modelled on
VS Code's Workspace Trust and Office's macro prompt: nothing in the ``user.``
namespace executes until *you* have trusted it.

Trust is pinned to a file's **contents**, not its folder or path, for one
important reason: folder-level trust is a trap. You'd grant it once while the
folder is empty (or holds only your own designs), and it would then silently
bless every community ``.py`` you drop in later. Keying on the file hash means:

- a **new** file has no trust record → it prompts;
- an **edited or swapped** file no longer matches its stored hash → it re-prompts
  (so a silently-rewritten "trusted" design can't run unnoticed).

Two trust modes, chosen at the prompt:

- ``pinned`` — trust *this exact version* (stores the hash). For a design you
  received and reviewed; if it ever changes, you're asked again.
- ``always`` — trust *this file and your future edits* (path-level, no hash).
  For a design you author and iterate on, so live-editing never re-prompts.

Built-in designs are never subject to this — they ship in the installed package
and are loaded by import, not from the user directory.

The store is a small JSON file (``.trust.json`` in the user design dir, or
``$ANTENNAKNOBS_TRUST_FILE``). The env flag ``ANTENNAKNOBS_TRUST_USER_DESIGNS=1``
is a blanket "trust everything" escape hatch for CI/dev/single-user boxes.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import design_screen

__all__ = [
    "DesignNotTrustedError",
    "content_hash",
    "is_trusted",
    "trust",
    "untrust",
    "trust_status",
    "trust_all_enabled",
    "store_path",
]

_STORE_VERSION = 1


def trust_all_enabled() -> bool:
    """True if the blanket-trust escape hatch is set in the environment."""
    return os.environ.get("ANTENNAKNOBS_TRUST_USER_DESIGNS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def store_path() -> Path:
    """Where the trust store lives: ``$ANTENNAKNOBS_TRUST_FILE`` if set, else
    ``.trust.json`` in the primary user design dir. Read fresh each call so
    tests (which redirect ``ANTENNAKNOBS_USER_DIR``) stay isolated."""
    override = os.environ.get("ANTENNAKNOBS_TRUST_FILE")
    if override:
        return Path(override).expanduser()
    # Local import avoids an import cycle (user_designs imports this module).
    from .user_designs import default_user_dir

    return default_user_dir() / ".trust.json"


def content_hash(path: Path) -> str:
    """SHA-256 of a file's bytes — the identity a ``pinned`` record checks."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _resolved_key(path: Path) -> str:
    """The store key for a design: its resolved absolute path as a string."""
    return str(Path(path).resolve())


def _load_store() -> dict:
    p = store_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {"version": _STORE_VERSION, "designs": {}}
    if not isinstance(data, dict) or "designs" not in data:
        return {"version": _STORE_VERSION, "designs": {}}
    return data


def _save_store(store: dict) -> None:
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename so a crash can't leave a half-written store.
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def is_trusted(path: Path) -> bool:
    """True if this exact design file is trusted to execute: the blanket env
    flag is set, or the store holds an ``always`` record for its path, or a
    ``pinned`` record whose hash matches the file's current contents."""
    if trust_all_enabled():
        return True
    rec = _load_store()["designs"].get(_resolved_key(path))
    if not rec:
        return False
    if rec.get("mode") == "always":
        return True
    if rec.get("mode") == "pinned":
        try:
            return rec.get("sha256") == content_hash(path)
        except OSError:
            return False
    return False


def trust(path: Path, *, mode: str = "pinned") -> None:
    """Record trust for a design. ``mode="pinned"`` (default) trusts the file's
    current contents only; ``mode="always"`` trusts the path across future
    edits (for a file you author). Raises ``ValueError`` on an unknown mode."""
    if mode not in ("pinned", "always"):
        raise ValueError(f"unknown trust mode {mode!r}; use 'pinned' or 'always'")
    store = _load_store()
    if mode == "always":
        rec = {"mode": "always"}
    else:
        rec = {"mode": "pinned", "sha256": content_hash(path)}
    store["designs"][_resolved_key(path)] = rec
    _save_store(store)


def untrust(path: Path) -> bool:
    """Remove any trust record for a design. Returns True if one was removed."""
    store = _load_store()
    if store["designs"].pop(_resolved_key(path), None) is None:
        return False
    _save_store(store)
    return True


def trust_status(path: Path) -> str:
    """One of ``"always"``, ``"pinned"`` (current contents trusted),
    ``"stale"`` (a pinned record exists but the file changed), or ``"none"``."""
    rec = _load_store()["designs"].get(_resolved_key(path))
    if not rec:
        return "none"
    if rec.get("mode") == "always":
        return "always"
    if rec.get("mode") == "pinned":
        try:
            return "pinned" if rec.get("sha256") == content_hash(path) else "stale"
        except OSError:
            return "stale"
    return "none"


@dataclass(frozen=True)
class DesignNotTrustedError(Exception):
    """Raised by the loader when a user design isn't trusted to execute.

    Carries the advisory ``report`` (what the design does that's unusual) so a
    UI or the CLI can show it alongside the trust prompt, and the ``path`` so a
    "Trust" action knows what to record.
    """

    path: Path
    report: design_screen.ScreenReport

    def __str__(self) -> str:
        return (
            f"{Path(self.path).name}: not trusted to run yet.\n"
            f"{self.report.summary()}\n"
            f"Review it, then trust it: `antennaknobs trust "
            f"{Path(self.path).stem}` (add --edits if it's your own file). "
            f"Only trust designs from sources you trust."
        )
