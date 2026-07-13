"""Discovery and path-loading of user-authored antenna designs.

Engine/UI-agnostic: pure filesystem + ``importlib`` with no dependency on the
``web`` package, so both the CLI (``antennaknobs.cli``) and the web adapter
resolve ``user.<name>`` designs from the same folders. The web layer
(``web/user_designs.py``) adds REGISTRY registration, scaffolding, and
error-panel formatting on top of this.

User designs live *outside* the installed package (so a ``pip`` upgrade never
clobbers them) and are loaded by file path. The ``user`` namespace can never
collide with or shadow a built-in family design.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Iterator
from pathlib import Path

from . import design_screen, design_trust

USER_NS = "user"
_MODULE_PREFIX = "antennaknobs._user_designs"


def default_user_dir() -> Path:
    """The primary user-design folder: ``$ANTENNAKNOBS_USER_DIR`` if set,
    else ``~/.antennaknobs/designs``. Read fresh each call so tests can
    redirect it via the environment."""
    env = os.environ.get("ANTENNAKNOBS_USER_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".antennaknobs" / "designs"


def user_design_dirs() -> list[Path]:
    """Folders scanned for user designs, in priority order: the default (or
    the env override) plus ``./antenna_designs`` if it exists in the cwd."""
    dirs = [default_user_dir()]
    seen = {d.resolve() for d in dirs if d.exists()}
    local = Path.cwd() / "antenna_designs"
    if local.is_dir() and local.resolve() not in seen:
        dirs.append(local)
    return dirs


def _is_design_file(path: Path) -> bool:
    """Skip private files and the copied authoring template."""
    stem = path.stem
    return not (stem.startswith("_") or stem == "TEMPLATE")


def load_builder(path: Path, *, trust: bool | None = None):
    """Import a single user file by path and return its ``Builder`` class.
    Re-executes the file on every call, so edits are picked up live.

    A user design runs with full privileges, so it executes only if it is
    *trusted* (see ``design_trust``): the file's contents are recorded in the
    trust store, or the blanket ``ANTENNAKNOBS_TRUST_USER_DESIGNS`` env flag is
    set. An untrusted file raises ``DesignNotTrustedError`` — carrying the
    advisory screen report so a UI/CLI can show what the design does before the
    user decides — and is NOT executed. Pass ``trust=True`` to bypass the gate
    for a file you already vouch for (e.g. programmatic/test use).
    """
    if trust is None:
        trust = design_trust.is_trusted(path)
    if not trust:
        # Advisory only: the screen report never blocks on its own, it just
        # tells the user what they're being asked to trust.
        report = design_screen.screen_file(path)
        raise design_trust.DesignNotTrustedError(path, report)
    modname = f"{_MODULE_PREFIX}.{path.stem}"
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not create import spec for {path.name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(modname, None)
        raise
    cls = getattr(mod, "Builder", None)
    if cls is None:
        raise AttributeError(
            "no `Builder` class found — define `class Builder(AntennaBuilder): ...`"
        )
    return cls


def iter_design_files() -> Iterator[tuple[str, Path]]:
    """Yield ``(stem, path)`` for each user design file across all folders,
    first-folder-wins on a duplicate stem (matching the web's priority order)."""
    seen: set[str] = set()
    for d in user_design_dirs():
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.py")):
            if not _is_design_file(path):
                continue
            if path.stem in seen:
                continue
            seen.add(path.stem)
            yield path.stem, path


def find_design_file(stem: str) -> Path | None:
    """The file backing user design ``stem``, or None if there is no such file."""
    for s, path in iter_design_files():
        if s == stem:
            return path
    return None


def resolve_user_design(stem: str):
    """Return the ``Builder`` class for user design ``stem``, or None if no
    such file exists. Load errors (syntax error, missing ``Builder``) propagate
    so someone debugging their own file sees the real cause."""
    path = find_design_file(stem)
    if path is None:
        return None
    return load_builder(path)
