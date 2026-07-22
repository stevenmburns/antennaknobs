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

Records are keyed by the design's path **relative to the store's own
directory** (``"foo.py"``), not its absolute path. The store lives inside the
design folder, so a relative key means "this file in my own directory" — the
same identity, but portable: mount the folder into a Docker container at
``/root/.antennaknobs/designs`` (compose.yaml does) or move it to another
machine and trust travels with it, where absolute keys silently matched
nothing. This is NOT folder-level trust — records are still per-file and
``pinned`` mode still checks the content hash. (``always`` mode was already a
name-not-content grant, and anyone who can forge the relative key could
already edit ``.trust.json`` itself — store integrity is assumed either way.)
Legacy absolute keys are migrated to relative on load; a design outside the
store's directory (``$ANTENNAKNOBS_TRUST_FILE`` pointing elsewhere) still
keys by absolute path.
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

# v2: design keys are store-dir-relative (portable); v1 keyed absolute paths.
# The loader migrates v1 keys transparently and never gates on the version.
_STORE_VERSION = 2


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
    """The store key for a design: its path relative to the store's own
    directory when it lives there (portable across mount points — see the
    module docstring), else its resolved absolute path."""
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(store_path().resolve().parent))
    except ValueError:
        return str(resolved)


def _migrate_keys(designs: dict) -> dict:
    """Rewrite legacy absolute keys that point inside the store's directory
    to the relative form (pre-portability stores; a folder that has been
    mounted at several paths may carry SEVERAL absolute spellings of the
    same file). On collision an ``always`` record wins over ``pinned`` —
    both were explicit user grants, and ``always`` is the broader one the
    user has stated for the file."""
    store_dir = store_path().resolve().parent
    migrated: dict = {}
    for key, rec in designs.items():
        p = Path(key)
        if p.is_absolute():
            try:
                key = str(p.resolve().relative_to(store_dir))
            except ValueError:
                # The key points outside the store dir. Two cases:
                # - The folder has been RELOCATED since the record was
                #   written (a Docker volume at /root/..., a moved home
                #   dir): the recorded path no longer exists in this
                #   environment, but a file with that name sits next to
                #   the store. The default store always lived alongside
                #   its designs, so treat the record as this folder's own.
                # - A custom $ANTENNAKNOBS_TRUST_FILE store legitimately
                #   records out-of-dir designs: those paths still exist
                #   here, so the guard leaves them keyed absolute.
                if not p.exists() and (store_dir / p.name).is_file():
                    key = p.name
        prev = migrated.get(key)
        if prev is None or (
            prev.get("mode") == "pinned" and rec.get("mode") == "always"
        ):
            migrated[key] = rec
    return migrated


def _load_store() -> dict:
    p = store_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {"version": _STORE_VERSION, "designs": {}}
    if not isinstance(data, dict) or "designs" not in data:
        return {"version": _STORE_VERSION, "designs": {}}
    data["designs"] = _migrate_keys(data["designs"])
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
            f"{Path(self.path).name}: not allowed to run yet.\n"
            f"{self.report.summary()}\n"
            f"Review it, then allow it: `antennaknobs allow "
            f"{Path(self.path).stem}` (add --edits if it's your own file). "
            f"Only allow designs from sources you trust."
        )
