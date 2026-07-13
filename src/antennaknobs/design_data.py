"""Read a data file that ships next to a user design.

Data-driven designs load geometry from a JSON/CSV sidecar rather than hard-code
it. ``read_data`` / ``read_json`` are the blessed way to do that: they need no
``open``/``pathlib`` import, and they confine reads to the *calling design's own
folder* so they can't be turned into an arbitrary-file read.

They take the ``builder`` (i.e. ``self`` inside ``build_wires``) as their first
argument — that's how they find which design's folder to confine to (via the
builder's defining module), without the design having to plumb ``__file__`` and
without any stack introspection. Passing the real builder keeps the confinement
anchor correct and unfakeable::

    from antennaknobs import AntennaBuilder, read_json

    class Builder(AntennaBuilder):
        def build_wires(self):
            spec = read_json(self, "my_wires.json")
            ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["read_data", "read_json"]

# Cap on a single sidecar data file, so a design (or a mistaken huge file) can't
# read an arbitrarily large file into memory. Generous for coordinate lists.
_MAX_SIDECAR_BYTES = 4 * 1024 * 1024  # 4 MiB


def _design_dir(builder) -> Path:
    """The folder the ``builder``'s design file lives in, for resolving
    co-located data files — its defining module's ``__file__``. Works for both
    built-in designs (their package folder) and user designs (their user-dir
    folder)."""
    mod = sys.modules.get(type(builder).__module__)
    origin = getattr(mod, "__file__", None)
    if not origin:
        raise RuntimeError(
            "cannot locate this design's folder to read a data file from "
            "(the design isn't backed by a file on disk)"
        )
    return Path(origin).resolve().parent


def read_data(builder, name: str) -> str:
    """Read a text data file that ships next to ``builder``'s design and return
    its contents — e.g. a JSON or CSV wire list, so geometry can be authored as
    *data* rather than code.

    ``builder`` is the design instance (``self`` inside ``build_wires``); it
    supplies the folder the read is confined to. Deliberately confined so it
    can't become an arbitrary-file read:

    - ``name`` resolves **inside that design's own folder** only. An absolute
      path, a ``..`` that climbs out, or a symlink that points outside the
      folder is rejected — a design can read its own sidecar, never
      ``~/.ssh/id_rsa``.
    - Read-only, and capped at 4 MiB.
    """
    if not isinstance(name, str) or not name:
        raise ValueError("read_data(name): name must be a non-empty string")
    if Path(name).is_absolute():
        raise ValueError(
            f"read_data({name!r}): must be a filename inside the design's "
            f"folder, not an absolute path"
        )
    base = _design_dir(builder)
    # resolve() first so symlinks and any ``..`` are collapsed, THEN confirm the
    # real target is still inside the design folder.
    target = (base / name).resolve()
    if not target.is_relative_to(base):
        raise ValueError(
            f"read_data({name!r}): resolves outside the design's folder "
            f"({base}); data files must live next to the design"
        )
    if not target.is_file():
        raise FileNotFoundError(
            f"read_data({name!r}): no such data file next to the design "
            f"(expected {target})"
        )
    size = target.stat().st_size
    if size > _MAX_SIDECAR_BYTES:
        raise ValueError(
            f"read_data({name!r}): file is {size} bytes, over the "
            f"{_MAX_SIDECAR_BYTES}-byte limit for design data files"
        )
    return target.read_text(encoding="utf-8")


def read_json(builder, name: str):
    """``read_data`` followed by ``json.loads`` — the common case for a
    data-driven design. Returns the parsed object."""
    return json.loads(read_data(builder, name))
