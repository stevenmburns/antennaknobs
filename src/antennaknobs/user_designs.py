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

from dataclasses import replace

from . import design_screen, design_trust

USER_NS = "user"
_MODULE_PREFIX = "antennaknobs._user_designs"

# Antenna DATA files that count as designs in a user folder (issue #1419): a
# NEC card deck, a SimNEC circuit or an MMANA-GAL model (AK#1897) dropped
# beside the ``.py`` designs shows up as ``user.<stem>`` with no stub, through
# the same pure-data loader the CLI's ``@file`` spec uses. Data never
# executes, so these bypass the trust gate that Python designs go through.
DECK_SUFFIXES = (".nec", ".ssn", ".maa", ".ez")


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


class NoBuilderError(AttributeError):
    """The file imported cleanly but defines no ``Builder``.

    Its own class, not a bare ``AttributeError``, because the two callers want
    opposite things and only the *cause* tells them apart. A CLI user who typed
    a design name deserves the message; the web's registry sweep is looking at
    every ``.py`` in the folder, and a user's scratch program sitting next to
    their designs is not a broken design — it is not a design at all. An
    ``AttributeError`` raised from INSIDE a user's module (a typo in their
    ``Builder``) must keep reaching the error panel, which is exactly what a
    shared exception type could not distinguish.

    Subclasses ``AttributeError`` so existing handlers and the CLI's message
    are unchanged.
    """


# The name a terrain file binds its preset to (issue #1292), as a design file
# binds its class to ``Builder``.
TERRAIN_ATTR = "TERRAIN"

# The copied authoring templates: reference files, never loaded.
_TEMPLATE_STEMS = ("TEMPLATE", "TERRAIN_TEMPLATE")


def _is_design_file(path: Path) -> bool:
    """Skip private files and the copied authoring templates."""
    stem = path.stem
    return not (stem.startswith("_") or stem in _TEMPLATE_STEMS)


def is_deck_file(path: Path) -> bool:
    """True for a data-file design (``.nec`` / ``.ssn`` / ``.maa`` / ``.ez``) as
    opposed to a Python one — the two load differently and only the Python
    one needs trusting."""
    return path.suffix.lower() in DECK_SUFFIXES


def load_builder(path: Path, *, trust: bool | None = None):
    """Import a single user file by path and return its ``Builder`` class.
    Re-executes the file on every call, so edits are picked up live.

    A terrain file (see `load_user_file`) is not a design: it raises
    `NoBuilderError`, saying what the file is.
    """
    kind, obj = load_user_file(path, trust=trust)
    if kind == "terrain":
        raise NoBuilderError(
            f"{path.name} defines a terrain (`{TERRAIN_ATTR}`), not an antenna "
            "design; pick it as the ground's terrain in the web app"
        )
    return obj


def _terrain_preset(path: Path, preset):
    """The file's `TERRAIN`, named after the file, or the reason it cannot
    be used, in words for the error panel."""
    from .terrain import BUILTIN_PRESET_NAMES, TerrainPreset

    stem = path.stem
    if not isinstance(preset, TerrainPreset):
        raise TypeError(
            f"`{TERRAIN_ATTR}` must be a TerrainPreset (from antennaknobs.terrain), "
            f"and it is a {type(preset).__name__}"
        )
    for what in ("name", "label"):
        given = getattr(preset, what)
        if given not in ("", stem):
            raise ValueError(
                f"`{TERRAIN_ATTR}` sets {what}={given!r}, but a terrain file is "
                f"named by its file name ({stem!r}); leave {what} out, or rename "
                "the file"
            )
    if stem in BUILTIN_PRESET_NAMES:
        raise ValueError(
            f"{stem!r} is a built-in terrain and a file cannot replace it; "
            f"rename {path.name} (for example to {stem}_mine.py)"
        )
    return replace(preset, name=stem, label=stem)


def load_user_file(path: Path, *, trust: bool | None = None):
    """Import a single user file by path and say what it is:
    ``("design", Builder)`` or ``("terrain", TerrainPreset)``.

    A folder holds two kinds of Python file (issue #1292). A design defines
    ``Builder``. A terrain defines ``TERRAIN = TerrainPreset(...)`` and no
    ``Builder``; there is one per file, and the file's name is the preset's
    name and its label in the ground panel. A file with both is refused, and
    a file with neither raises `NoBuilderError`.

    Re-executes the file on every call, so edits are picked up live.

    A user design runs with full privileges, so it executes only if it is
    *trusted* (see ``design_trust``): the file's contents are recorded in the
    trust store, or the blanket ``ANTENNAKNOBS_TRUST_USER_DESIGNS`` env flag is
    set. An untrusted file raises ``DesignNotTrustedError`` — carrying the
    advisory screen report so a UI/CLI can show what the design does before the
    user decides — and is NOT executed. Pass ``trust=True`` to bypass the gate
    for a file you already vouch for (e.g. programmatic/test use).

    A ``.nec`` / ``.ssn`` file is data, not code: it goes through
    ``file_designs.builder_from_file`` (the CLI's ``@file`` loader), which
    parses and never executes, so the trust gate does not apply and ``trust``
    is ignored.
    """
    if is_deck_file(path):
        from .file_designs import builder_from_file

        return "design", builder_from_file(str(path))
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
    preset = getattr(mod, TERRAIN_ATTR, None)
    if cls is not None and preset is not None:
        raise ValueError(
            f"this file defines both `Builder` and `{TERRAIN_ATTR}`; a file is "
            "one antenna design or one terrain, so move one of them to a file "
            "of its own"
        )
    if preset is not None:
        return "terrain", _terrain_preset(path, preset)
    if cls is None:
        raise NoBuilderError(
            "no `Builder` class found — define `class Builder(AntennaBuilder): ...`"
        )
    return "design", cls


def _scan() -> Iterator[tuple[str, Path, Path | None]]:
    """``(stem, path, winner)`` for every candidate file in every folder:
    ``winner`` is None for the file that carries its stem, and that file's
    path for each later one of the same stem."""
    seen: dict[str, Path] = {}
    for d in user_design_dirs():
        if not d.is_dir():
            continue
        entries = sorted(d.glob("*.py")) + sorted(
            p for p in d.iterdir() if p.is_file() and is_deck_file(p)
        )
        for path in entries:
            if not _is_design_file(path):
                continue
            winner = seen.setdefault(path.stem, path)
            yield path.stem, path, (None if winner is path else winner)


def iter_design_files() -> Iterator[tuple[str, Path]]:
    """Yield ``(stem, path)`` for each user design file across all folders,
    first-folder-wins on a duplicate stem (matching the web's priority order).

    Within one folder the ``.py`` designs come first and the data-file designs
    (``.nec`` / ``.ssn``, issue #1419) after them, so a stub beside its deck —
    the documented ``my_yagi.py`` + ``my_yagi.nec`` recipe — is the design and
    the bare deck of the same stem is not listed twice."""
    for stem, path, winner in _scan():
        if winner is None:
            yield stem, path


def iter_shadowed_files() -> Iterator[tuple[str, Path, Path]]:
    """Yield ``(stem, path, winner)`` for each file `iter_design_files` leaves
    out because ``winner`` already carries its stem."""
    for stem, path, winner in _scan():
        if winner is not None:
            yield stem, path, winner


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
