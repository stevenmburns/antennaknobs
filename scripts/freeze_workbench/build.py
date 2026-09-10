"""Build the frozen antennaknobs workbench (issue #1349).

Run from the repo root, in an environment where antennaknobs[web] (this
checkout or the wheel) and pyinstaller are installed::

    python scripts/freeze_workbench/build.py

Produces ``dist/antennaknobs-workbench/``: the launcher
``antennaknobs-workbench[.exe]`` and its ``_internal`` runtime. The directory
must be kept together. One-dir on purpose — one-file self-extracts on every
launch (momwire's EZNEC bundle measured ~17 s per launch that way).

Signing is opt-in through the environment, exactly as momwire's EZNEC bundle
signs (``sign.py`` here is that file, verbatim): unset, the build is unsigned
and needs no signtool; ``MOMWIRE_SIGN_MODE`` set promises a signed build and
fails the build if no identity reached it.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "antennaknobs-workbench"

# LLVM's OpenMP runtime, which momwire's Windows extensions link
# (`/openmp:llvm`) and PyInstaller does not collect: momwire#737 shipped two
# bundles with a dead accelerator before the EZNEC lane learned this. Same
# lookup as momwire's build.py: import the extension, ask the loader.
OPENMP_DLL = "libomp140.x86_64.dll"

# uvicorn imports its event loop, its HTTP and WebSocket protocol classes
# and its lifespan handler by STRING at startup, which PyInstaller's static
# trace cannot see; the app's design catalog is walked with pkgutil, which
# it cannot see either. Every name here was found by a frozen launch that
# died with ModuleNotFoundError, or is the sibling of one that did.
HIDDEN_IMPORTS = (
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "websockets.legacy",
    "websockets.legacy.server",
    "anyio._backends._asyncio",
    "matplotlib.backends.backend_agg",
)


def _openmp_runtime() -> Path | None:
    import ctypes
    import ctypes.util

    try:
        import momwire._accelerators  # noqa: F401
    except ImportError as exc:
        print(f"WARNING: {exc}; looking for {OPENMP_DLL} on PATH", file=sys.stderr)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetModuleFileNameW.restype = ctypes.c_uint32
    kernel32.GetModuleFileNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    handle = kernel32.GetModuleHandleW(OPENMP_DLL)
    if handle:
        buffer = ctypes.create_unicode_buffer(32768)
        if kernel32.GetModuleFileNameW(handle, buffer, len(buffer)):
            return Path(buffer.value)
    located = ctypes.util.find_library(OPENMP_DLL)
    if located and Path(located).is_file():
        return Path(located)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry and (candidate := Path(entry) / OPENMP_DLL).is_file():
            return candidate
    return None


def _load_sign():
    spec = importlib.util.spec_from_file_location(
        "freeze_workbench_sign", HERE / "sign.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _readme(bundle: Path) -> None:
    ak = version("antennaknobs")
    mw = version("momwire")
    (bundle / "README.txt").write_text(
        f"""antennaknobs workbench {ak}  (momwire {mw})
================================================

Double-click {NAME}.exe. A console window opens, the workbench starts on
this computer, and your browser opens at it (http://127.0.0.1:<port>/).
Keep the console window open while you use the workbench; Ctrl-C or
closing it stops the server. Nothing is installed; delete the folder to
remove it. Keep the folder together: the program needs _internal beside it.

Options (from a PowerShell or Command Prompt window in this folder):
    {NAME}.exe --port 8000       a fixed port
    {NAME}.exe --no-browser      print the URL only
    {NAME}.exe --selftest        prove the bundle and exit

NEC-5 (optional, needs your own licensed engine; EZNEC Pro+ ships
NEC5CL.exe): put its full path on one line in a text file named
NEC5_EXE.txt beside {NAME}.exe, for example

    C:\\Program Files\\EZNEC Pro+\\NEC5CL.exe

and start the workbench again; the NEC-5 tab appears in the solver panel.
The NEC5_EXE environment variable is honoured too and wins over the file.
The server listens on 127.0.0.1 only.

This is the same program as `pip install "antennaknobs[web]"`, packaged.
Docs: https://antennaknobs.dev/   Source: https://github.com/stevenmburns/antennaknobs
""",
        encoding="utf-8",
    )


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--console",
        "--name",
        NAME,
        "--collect-submodules",
        "antennaknobs",
        "--collect-data",
        "antennaknobs",
        "--collect-submodules",
        "momwire",
        "--collect-submodules",
        "scipy",
        "--collect-data",
        "schemdraw",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "PyQt6",
        "--exclude-module",
        "PySide6",
        "--exclude-module",
        "IPython",
    ]
    for name in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", name]
    if os.name == "nt":
        runtime = _openmp_runtime()
        if runtime is None:
            print(
                f"ERROR: {OPENMP_DLL} is nowhere this build can see it; the "
                "bundle would ship with a dead accelerator (momwire#737)",
                file=sys.stderr,
            )
            return 1
        cmd += ["--add-binary", f"{runtime}{os.pathsep}."]
        print(f"openmp runtime: {runtime}")
    cmd.append(str(HERE / "entry.py"))
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        return result.returncode
    bundle = Path("dist") / NAME
    exe = next((p for p in bundle.glob(f"{NAME}*") if p.is_file()), None)
    if exe is None:
        print(f"ERROR: no {NAME} executable in {bundle}", file=sys.stderr)
        return 1
    _readme(bundle)
    signer = _load_sign()
    signed = signer.sign_if_configured([exe])
    mode = os.environ.get("MOMWIRE_SIGN_MODE")
    if mode and not signed:
        print(
            f"ERROR: MOMWIRE_SIGN_MODE={mode} promises a signed build but no "
            "signing identity reached build.py",
            file=sys.stderr,
        )
        return 1
    print(f"built {exe} ({'signed' if signed else 'unsigned'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
