"""The user's settings file, as the library reads it (AK#1492).

``settings.toml`` lives in the ``.antennaknobs`` folder in the home directory
(``$ANTENNAKNOBS_SETTINGS`` names another). The web workbench reads its
``[switches]``, ``[ground]`` and ``[slots]`` (``antennaknobs.web.settings``).
Two tables are for the library itself, so that the CLI and the workbench find
the same engines and capture folder:

    [engines]
    nec5_exe = "C:\\EZNEC 7.0\\Docs\\NEC5CL_x13.exe"
    nec2_exe = "C:\\4nec2\\exe\\nec2dxs11.exe"

    [capture]
    dir = "C:\\ak-captures"

An environment variable (``NEC5_EXE``, ``NEC2_EXE``,
``ANTENNAKNOBS_CAPTURE_DIR``, which the packaged workbench's flags set) always
wins over the file. The hosted instance reads no file.

Only a person editing the file sets these two tables. The page's "Save as my
defaults" never writes them, because a path the server executes must not be
settable by a web request.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

SETTINGS_ENV = "ANTENNAKNOBS_SETTINGS"
HOSTED_ENV = "ANTENNAKNOBS_HOSTED"

# The environment variable each file entry stands in for.
ENGINE_KEYS = {"NEC5_EXE": "nec5_exe", "NEC2_EXE": "nec2_exe"}

_cache: dict = {"key": None, "data": None, "error": None}


def settings_path() -> Path:
    """``$ANTENNAKNOBS_SETTINGS``, else ``~/.antennaknobs/settings.toml``. Read
    fresh each call so tests and the workbench flag can redirect it."""
    env = os.environ.get(SETTINGS_ENV)
    if env:
        return Path(env).expanduser()
    return Path.home() / ".antennaknobs" / "settings.toml"


def hosted() -> bool:
    """The same flag the web server reads: the hosted instance reads no file."""
    return os.environ.get(HOSTED_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def read_settings() -> tuple[dict | None, str | None]:
    """The parsed file and None, or None and why it could not be read, or
    (None, None) when there is no file. Cached on the file's modification time
    and size, so a caller asking per engine lookup costs one stat."""
    if hosted():
        return None, None
    path = settings_path()
    try:
        st = path.stat()
    except OSError:
        return None, None
    key = (str(path), st.st_mtime_ns, st.st_size)
    if _cache["key"] != key:
        try:
            data, error = tomllib.loads(path.read_text(encoding="utf-8")), None
        except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as exc:
            data, error = None, f"{path.name} is not valid TOML ({exc})"
        _cache.update(key=key, data=data, error=error)
    return _cache["data"], _cache["error"]


def _string(table: str, key: str) -> str | None:
    data, _ = read_settings()
    section = data.get(table) if isinstance(data, dict) else None
    value = section.get(key) if isinstance(section, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def engine_exe(env_var: str) -> str | None:
    """The file's path for the engine ``env_var`` names (``NEC5_EXE`` ->
    ``[engines] nec5_exe``), or None."""
    key = ENGINE_KEYS.get(env_var)
    return _string("engines", key) if key else None


def capture_dir() -> str | None:
    """The file's ``[capture] dir``, or None."""
    return _string("capture", "dir")
