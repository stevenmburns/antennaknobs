"""PyInstaller entry point for the frozen antennaknobs workbench (issue #1349).

``antennaknobs-workbench[.exe]``: start the web workbench on a free localhost
port and open the default browser at it. The same package, the same momwire
wheel and the same frontend bundle as ``pip install antennaknobs[web]``; the
executable is packaging, not a fork. Console stays open with the URL and the
server log, and Ctrl-C stops it.

    antennaknobs-workbench              # free port, browser opens
    antennaknobs-workbench --port 8000  # a fixed port
    antennaknobs-workbench --no-browser # print the URL only
    antennaknobs-workbench --selftest   # prove the bundle: accelerator +
                                        # one solve, printed, exit 0
    antennaknobs-workbench --capture-dir C:\\ak-captures
                                        # every NEC-5 / NEC-2 run leaves its
                                        # deck and printout there (AK#1428)
    antennaknobs-workbench --log-level DEBUG
                                        # the decks and printouts in this
                                        # window too, as they run
    antennaknobs-workbench --nec5-exe "C:\\EZNEC 7.0\\Docs\\NEC5CL_x13.exe"
                                        # the licensed NEC-5 engine; reads the
                                        # same in PowerShell and Command Prompt
    antennaknobs-workbench --nec2-exe C:\\4nec2\\exe\\nec2dxs11.exe
                                        # a NEC-2 console binary, the same way
    antennaknobs-workbench --settings C:\\ak\\settings.toml
                                        # where the workbench starts: switches,
                                        # ground, solver slots (AK#1492)

The licensed NEC-5 engine is found four ways, first match wins: the
``--nec5-exe PATH`` flag; the ``NEC5_EXE`` variable the pip install reads;
``nec5_exe`` in the settings file's ``[engines]`` table (AK#1492); and, for
someone who double-clicks, a one-line text file ``NEC5_EXE.txt`` beside the
executable holding the path to NEC5CL.exe. The flag exists because the
variable is spelled one way in PowerShell (``$env:NEC5_EXE = "..."``) and
another in Command Prompt (``set NEC5_EXE=...``), and users mix the two up.
The server stays on 127.0.0.1: an engine you are licensed for must not be
served past your own machine.

Startup settings (AK#1492) come from ``--settings PATH``, else the
``ANTENNAKNOBS_SETTINGS`` variable, else ``settings.toml`` in the
``.antennaknobs`` folder in your home directory, the one that holds
``designs``. The Settings menu's "Save as my defaults" writes that file.

``--nec2-exe`` / ``NEC2_EXE`` / ``NEC2_EXE.txt`` do the same for a NEC-2
console binary (nec2c, nec2++, 4nec2's nec2dxs*.exe). The bundle ships none:
nec2++ is GPLv2, and shipping it would make this zip a combined work (#1354).
It is the one engine most users already have, because 4nec2 installs one.

A separate script rather than ``-m antennaknobs.web.server`` because
PyInstaller wants a file to trace from, and because the browser-opening and
the NEC5_EXE.txt convenience are this program's and not the library's.
"""

from __future__ import annotations

import multiprocessing
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

NAME = "antennaknobs-workbench"
# One file per engine, named after the variable it fills, beside the exe, and
# one flag per engine that fills the same variable. NEC-5 is licensed software
# the user supplies (#825); NEC-2 is freely available but GPL, so the bundle
# drives a user-supplied binary rather than ship one (#1354). The same rule for
# both: the flag beats the variable, and the variable beats the file.
EXE_FILES = {"NEC5_EXE": "NEC5_EXE.txt", "NEC2_EXE": "NEC2_EXE.txt"}
EXE_FLAGS = {"NEC5_EXE": "--nec5-exe", "NEC2_EXE": "--nec2-exe"}
NEC5_FILE = EXE_FILES["NEC5_EXE"]
NEC2_FILE = EXE_FILES["NEC2_EXE"]


def _bundle_dir() -> Path:
    # One-dir bundle: the executable's own directory. Under a plain
    # interpreter (the smoke runs this file unfrozen too) it is the script's.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _exe_from_file(name: str) -> str | None:
    """The first non-comment line of `name` beside the executable, or None."""
    candidate = _bundle_dir() / name
    if not candidate.is_file():
        return None
    for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().strip('"')
        if line and not line.startswith("#"):
            return line
    return None


def _nec5_from_file() -> str | None:
    return _exe_from_file(NEC5_FILE)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _open_when_up(url: str, health: str, *, deadline_s: float = 120.0) -> None:
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        try:
            with urllib.request.urlopen(health, timeout=2) as r:  # noqa: S310 — loopback http only
                if r.status == 200:
                    webbrowser.open(url)
                    return
        except Exception:  # noqa: BLE001 — polling until the server binds
            time.sleep(0.5)


def _value(it, flag: str) -> str:
    """The argument after `flag`, or a usage error naming the flag. Without
    this, ``--nec5-exe`` typed with the path forgotten ends in a traceback."""
    try:
        return next(it)
    except StopIteration:
        print(f"{NAME}: {flag} needs a value", file=sys.stderr)
        raise SystemExit(2) from None


def _parse(argv: list[str]) -> dict:
    opts = {
        "port": None,
        "browser": True,
        "selftest": False,
        "log_level": None,
        "capture_dir": None,
        "nec5_exe": None,
        "nec2_exe": None,
        "settings": None,
    }
    it = iter(argv)
    for a in it:
        if a == "--port":
            opts["port"] = int(_value(it, a))
        elif a.startswith("--port="):
            opts["port"] = int(a.split("=", 1)[1])
        elif a == "--log-level":
            opts["log_level"] = _value(it, a)
        elif a.startswith("--log-level="):
            opts["log_level"] = a.split("=", 1)[1]
        elif a == "--capture-dir":
            opts["capture_dir"] = _value(it, a)
        elif a.startswith("--capture-dir="):
            opts["capture_dir"] = a.split("=", 1)[1]
        elif a in EXE_FLAGS.values():
            opts[a[2:].replace("-", "_")] = _value(it, a)
        elif a.startswith(tuple(f"{flag}=" for flag in EXE_FLAGS.values())):
            flag, value = a.split("=", 1)
            opts[flag[2:].replace("-", "_")] = value
        elif a == "--settings":
            opts["settings"] = _value(it, a)
        elif a.startswith("--settings="):
            opts["settings"] = a.split("=", 1)[1]
        elif a == "--no-browser":
            opts["browser"] = False
        elif a == "--selftest":
            opts["selftest"] = True
        elif a in ("-h", "--help"):
            print(__doc__)
            raise SystemExit(0)
        else:
            print(f"{NAME}: unknown option {a!r}", file=sys.stderr)
            raise SystemExit(2)
    return opts


def _apply_capture_opts(opts: dict) -> None:
    """The two AK#1428 flags become the environment variables the library
    reads (`antennaknobs.engine_capture`), so the exe, `uvicorn` and the CLI
    share one code path. A flag beats a variable already in the environment;
    the variable alone still works without the flag."""
    if opts.get("log_level"):
        os.environ["ANTENNAKNOBS_LOG_LEVEL"] = str(opts["log_level"])
    if opts.get("capture_dir"):
        os.environ["ANTENNAKNOBS_CAPTURE_DIR"] = str(opts["capture_dir"])
    # --nec5-exe / --nec2-exe become NEC5_EXE / NEC2_EXE the same way. A flag
    # beats a variable already set, and a set variable means NEC5_EXE.txt is
    # not consulted, so the order is flag, then variable, then file.
    if opts.get("nec5_exe"):
        os.environ["NEC5_EXE"] = str(opts["nec5_exe"])
    if opts.get("nec2_exe"):
        os.environ["NEC2_EXE"] = str(opts["nec2_exe"])
    # --settings becomes ANTENNAKNOBS_SETTINGS, which the server reads at every
    # page load (AK#1492).
    if opts.get("settings"):
        os.environ["ANTENNAKNOBS_SETTINGS"] = str(opts["settings"])


def _settings_line() -> str:
    """What the startup summary says about the settings file."""
    from antennaknobs.web.settings import settings_path

    path = settings_path()
    if path.is_file():
        return str(path)
    return f"{path}  (none yet: the Settings menu's 'Save as my defaults' writes it)"


def _apply_exe_files() -> None:
    """``NEC5_EXE.txt`` / ``NEC2_EXE.txt`` beside the executable, for a variable
    still unset after the flags. A variable already set, by the environment or
    by ``--nec5-exe`` / ``--nec2-exe``, is left alone, and so is an engine the
    settings file names (the library reads that itself). That makes the order
    flag, then variable, then settings.toml, then text file."""
    from antennaknobs.settings_file import engine_exe

    for var, fname in EXE_FILES.items():
        if os.environ.get(var) or engine_exe(var):
            continue
        from_file = _exe_from_file(fname)
        if from_file:
            os.environ[var] = from_file
            print(f"{var} = {from_file}  (from {fname})")


def _engine_line(var: str) -> str:
    """What the startup summary says about one engine. An unset engine names
    the routes to set it. A path that is not an executable file gets a note:
    the engines' `find_exe` treats it as no engine at all, so its tab never
    appears, and before this the path printed as if it were fine."""
    from antennaknobs.settings_file import ENGINE_KEYS, engine_exe

    path, source = os.environ.get(var), ""
    if not path:
        path = engine_exe(var)
        source = "from settings.toml" if path else ""
    if not path:
        return (
            f"not set ({EXE_FLAGS[var]} PATH, [engines] {ENGINE_KEYS[var]} in "
            f"settings.toml, or the path in {EXE_FILES[var]} beside this program)"
        )
    p = Path(path).expanduser()
    if p.is_file() and os.access(p, os.X_OK):
        return f"{path}  ({source})" if source else path
    note = "not an executable file, so this engine is off: check the path"
    return f"{path}  ({source}; {note})" if source else f"{path}  ({note})"


def selftest() -> int:
    """The bundle proves itself: momwire's accelerator loaded, the quick
    start's first example solves, the server module imports. Printed, so a
    transcript is the diagnostic; exit 0 only when all three hold."""
    from importlib.metadata import version

    import momwire

    # Which build ran, not only whether one did (issue #1405): since momwire's
    # double build (momwire#1032), `accelerated = True` cannot tell avx2 from sse2.
    variant = getattr(momwire, "accelerator_variant", None)
    print(
        f"momwire {version('momwire')} accelerated = {momwire.accelerated} "
        f"variant = {variant}"
    )
    if not momwire.accelerated:
        print("FAIL: momwire's C++ accelerator did not load (OpenMP runtime missing?)")
        return 1
    from antennaknobs import Antenna
    from antennaknobs.designs.dipoles.invvee import Builder

    z = Antenna(Builder()).impedance()
    print(f"antennaknobs {version('antennaknobs')} invvee free space: {z}")
    import antennaknobs.web.server  # noqa: F401

    print("server import OK")
    print("SELFTEST OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    os.environ.setdefault("MPLBACKEND", "Agg")
    opts = _parse(sys.argv[1:] if argv is None else argv)
    _apply_capture_opts(opts)
    _apply_exe_files()
    if opts["selftest"]:
        return selftest()

    from importlib.metadata import version

    import uvicorn

    from antennaknobs.web.server import app

    port = opts["port"] or _free_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"{NAME} {version('antennaknobs')}  (momwire {version('momwire')})")
    print(f"  workbench: {url}")
    print(f"  NEC-5:     {_engine_line('NEC5_EXE')}")
    print(f"  NEC-2:     {_engine_line('NEC2_EXE')}")
    print(f"  settings:  {_settings_line()}")
    from antennaknobs.settings_file import capture_dir

    capture = os.environ.get("ANTENNAKNOBS_CAPTURE_DIR") or capture_dir()
    if capture:
        print(
            f"  capture:   {capture}  "
            "(every engine deck and printout, as nec5/ and nec2/ <hash>.nec + .out)"
        )
    if os.environ.get("ANTENNAKNOBS_LOG_LEVEL"):
        print(f"  log level: {os.environ['ANTENNAKNOBS_LOG_LEVEL']}")
    print("  stop:      Ctrl-C in this window")
    if opts["browser"]:
        threading.Thread(
            target=_open_when_up, args=(url, url + "healthz"), daemon=True
        ).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
