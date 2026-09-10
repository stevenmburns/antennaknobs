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

The licensed NEC-5 engine is found the way the pip install finds it, through
``NEC5_EXE`` — and, for someone who double-clicks, through a one-line text
file ``NEC5_EXE.txt`` beside the executable holding the path to NEC5CL.exe.
The file wins only when the variable is unset. The server stays on
127.0.0.1: an engine you are licensed for must not be served past your own
machine.

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
NEC5_FILE = "NEC5_EXE.txt"


def _bundle_dir() -> Path:
    # One-dir bundle: the executable's own directory. Under a plain
    # interpreter (the smoke runs this file unfrozen too) it is the script's.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _nec5_from_file() -> str | None:
    candidate = _bundle_dir() / NEC5_FILE
    if not candidate.is_file():
        return None
    for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().strip('"')
        if line and not line.startswith("#"):
            return line
    return None


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


def _parse(argv: list[str]) -> dict:
    opts = {"port": None, "browser": True, "selftest": False}
    it = iter(argv)
    for a in it:
        if a == "--port":
            opts["port"] = int(next(it))
        elif a.startswith("--port="):
            opts["port"] = int(a.split("=", 1)[1])
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


def selftest() -> int:
    """The bundle proves itself: momwire's accelerator loaded, the quick
    start's first example solves, the server module imports. Printed, so a
    transcript is the diagnostic; exit 0 only when all three hold."""
    import momwire

    print(
        f"momwire {getattr(momwire, '__version__', '?')} accelerated = {momwire.accelerated}"
    )
    if not momwire.accelerated:
        print("FAIL: momwire's C++ accelerator did not load (OpenMP runtime missing?)")
        return 1
    from antennaknobs import Antenna, __version__
    from antennaknobs.designs.dipoles.invvee import Builder

    z = Antenna(Builder()).impedance()
    print(f"antennaknobs {__version__} invvee free space: {z}")
    import antennaknobs.web.server  # noqa: F401

    print("server import OK")
    print("SELFTEST OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    os.environ.setdefault("MPLBACKEND", "Agg")
    opts = _parse(sys.argv[1:] if argv is None else argv)
    if not os.environ.get("NEC5_EXE"):
        from_file = _nec5_from_file()
        if from_file:
            os.environ["NEC5_EXE"] = from_file
            print(f"NEC5_EXE = {from_file}  (from {NEC5_FILE})")
    if opts["selftest"]:
        return selftest()

    import uvicorn

    from antennaknobs import __version__
    from antennaknobs.web.server import app

    port = opts["port"] or _free_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"{NAME} {__version__}")
    print(f"  workbench: {url}")
    print(
        f"  NEC-5:     {os.environ.get('NEC5_EXE') or f'not set (put the path in {NEC5_FILE} beside this program)'}"
    )
    print("  stop:      Ctrl-C in this window")
    if opts["browser"]:
        threading.Thread(
            target=_open_when_up, args=(url, url + "healthz"), daemon=True
        ).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
