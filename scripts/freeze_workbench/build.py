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
import re
import subprocess
import shutil
import sys
from importlib.metadata import version
from pathlib import Path

from version_file import build_version_info

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


def _vendored_dlls() -> list[Path]:
    """Every DLL delvewheel vendored beside momwire (`momwire.libs\\`), in
    whatever mangled names it gave them."""
    import momwire

    libs = Path(momwire.__file__).resolve().parent.parent / "momwire.libs"
    return sorted(libs.glob("*.dll")) if libs.is_dir() else []


def _loaded_openmp() -> Path | None:
    """The OpenMP runtime this process already has mapped, whatever it is
    called. delvewheel renames vendored DLLs, so match on the stem rather
    than the exact filename."""
    import ctypes
    import ctypes.wintypes as wt

    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wt.HANDLE
    kernel32.GetCurrentProcess.argtypes = []
    psapi.EnumProcessModules.restype = wt.BOOL
    psapi.EnumProcessModules.argtypes = [
        wt.HANDLE,
        ctypes.POINTER(wt.HMODULE),
        wt.DWORD,
        ctypes.POINTER(wt.DWORD),
    ]
    psapi.GetModuleFileNameExW.restype = wt.DWORD
    psapi.GetModuleFileNameExW.argtypes = [
        wt.HANDLE,
        wt.HMODULE,
        wt.LPWSTR,
        wt.DWORD,
    ]
    proc = kernel32.GetCurrentProcess()
    handles = (wt.HMODULE * 4096)()
    needed = wt.DWORD()
    if not psapi.EnumProcessModules(
        proc,
        handles,
        ctypes.sizeof(handles),
        ctypes.byref(needed),
    ):
        return None
    stem = OPENMP_DLL[: -len(".dll")]
    buffer = ctypes.create_unicode_buffer(32768)
    for i in range(min(needed.value // ctypes.sizeof(wt.HMODULE), len(handles))):
        if psapi.GetModuleFileNameExW(proc, handles[i], buffer, len(buffer)):
            path = Path(buffer.value)
            if path.name.lower().startswith(stem.lower()) and path.is_file():
                return path
    return None


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
    # The PyPI wheel is delvewheel-repaired: the vendored runtime moves to
    # `momwire.libs\` and gains a content-hash suffix
    # (libomp140.x86_64-<hash>.dll), so the name lookup above misses it even
    # though the extension has it loaded. Ask the loader what is actually
    # mapped rather than guessing a filename.
    if (found := _loaded_openmp()) is not None:
        return found
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
remove it. Keep the folder together: the program runs the code in
_internal beside it, so the .exe alone is not the whole program.

To update: extract the WHOLE new zip into a fresh folder rather than
copying just the .exe over an old one — an old _internal left in place
keeps running the old code under the new .exe's name, with no obvious
sign beyond the version shown under the page's title and in this
window's startup line.

Options (from a PowerShell or Command Prompt window in this folder):
    {NAME}.exe --port 8000       a fixed port
    {NAME}.exe --no-browser      print the URL only
    {NAME}.exe --selftest        prove the bundle and exit

NEC-5 (optional, needs your own licensed engine; EZNEC Pro+ keeps it in
its Docs folder as NEC5CL_x13.exe, the suffix being the build): put its
full path on one line in a text file named
NEC5_EXE.txt beside {NAME}.exe, for example

    C:\\EZNEC 7.0\\Docs\\NEC5CL_x13.exe

and start the workbench again; the NEC-5 tab appears in the solver panel.
The NEC5_EXE environment variable is honoured too and wins over the file.
The server listens on 127.0.0.1 only.

NEC-2 (optional, and you may already have one): 4nec2 installs a console
NEC-2 as nec2dxs*.exe in its exe folder, and nec2c / nec2++ are free
downloads. Put the full path on one line in NEC2_EXE.txt beside
{NAME}.exe, for example

    C:\\4nec2\\exe\\nec2dxs11.exe

and start the workbench again; the NEC-2 tab appears in the solver panel, and
the startup line "NEC-2:" in this window confirms the path. NEC2_EXE is
honoured too and wins over the file. Both invocation styles work -- the file
names on standard input, or -i/-o arguments -- and the engine finds out which
by running your binary once. No NEC-2 is bundled on purpose: nec2++ is GPLv2
and shipping it would change this zip's licence.

This is the same program as `pip install "antennaknobs[web]"`, packaged.
Docs: https://antennaknobs.dev/   Source: https://github.com/stevenmburns/antennaknobs
""",
        encoding="utf-8",
    )


def _license_copyright() -> str:
    """The LegalCopyright string for the version resource, read from LICENSE
    so it can never drift from the file that actually governs the software."""
    text = (HERE.parent.parent / "LICENSE").read_text(encoding="utf-8")
    m = re.search(r"Copyright \(c\) .+", text)
    return m.group(0) if m else "Copyright (c) Steven Burns"


def _write_version_file() -> Path:
    """The PyInstaller `--version-file` text, generated fresh from the
    package's OWN version (issue #1517 follow-up) — the same source the web
    label and the console banner read, so Explorer's Properties -> Details
    can never disagree with either. Windows-only: a version resource is a PE
    concept, and PyInstaller merely warns and ignores `version=` elsewhere."""
    text = build_version_info(
        version("antennaknobs"),
        name=NAME,
        product_name="antennaknobs workbench",
        company="Steven Burns",
        copyright_str=_license_copyright(),
    )
    out = Path("build") / "workbench_version_info.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def _prune_gpl(bundle: Path) -> None:
    """Remove any PyNEC artefact the collector left behind.

    `--exclude-module PyNEC/_PyNEC` drops the importable code, and on a venv
    with `pynec-accel` installed that is 36 MB of it. What the module exclude
    does NOT drop is the distribution's `*.dist-info/` — PyInstaller collects
    installed metadata independently of whether the module ships — so a build
    from such a venv still emitted `pynec_accel-1.7.6.dist-info/` with its
    METADATA, RECORD and `licenses/`.

    That is metadata rather than GPL source, so it is not the licence breach
    the module would be; it is removed anyway, because "no PyNEC anything in
    the bundle" is a rule that can be checked, and "some PyNEC files but only
    the harmless ones" is not. `smoke.py` gate 0 asserts the outcome.
    """
    hits = [
        p
        for p in bundle.rglob("*")
        if "pynec" in p.name.lower() and (p.is_dir() or p.is_file())
    ]
    for p in sorted(hits, key=lambda q: -len(q.parts)):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()
    if hits:
        print(f"pruned {len(hits)} PyNEC artefact(s) the collector added")


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
        "--specpath",
        "build",
        "--collect-submodules",
        "antennaknobs",
        "--collect-data",
        "antennaknobs",
        "--collect-submodules",
        "momwire",
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
        # PyNEC is GPL and the workbench is not. `pyproject.toml` keeps it out
        # of every extra on purpose and antennaknobs#1354's text coupling means
        # no served path imports it — but `--collect-submodules antennaknobs`
        # follows the BUILD VENV, so a developer whose venv has `pynec-accel`
        # installed shipped `PyNEC.py`, `_PyNEC*.so` and a 27 MB
        # `pynec_accel.libs/` without being told. Measured 2026-09-10 on a dev
        # box: 36 MB of GPL code in the bundle. `pynec-accel` publishes the two
        # top-level names below; `smoke.py` gate 0 asserts the OUTCOME, so the
        # licence does not rest on this list tracking the wheel.
        "--exclude-module",
        "PyNEC",
        "--exclude-module",
        "_PyNEC",
        # Nothing in a served path imports pandas, and the shipped v0.73.0
        # Windows zip has none — but a build venv that happens to have it gets
        # 18 MB of it collected. Excluded by name so the bundle's contents are
        # a property of this file rather than of whoever's venv ran it.
        "--exclude-module",
        "pandas",
    ]
    for name in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", name]
    # The design catalog is discovered by LISTING the package's `designs`
    # directory (`adapter.list_designs` walks it with iterdir), and a frozen
    # bundle keeps modules inside its archive with no directory to list. So
    # the directory ships as data beside the archive too — the modules still
    # import from the archive; the listing sees the files.
    import antennaknobs

    designs = Path(antennaknobs.__file__).resolve().parent / "designs"
    cmd += ["--add-data", f"{designs}{os.pathsep}antennaknobs/designs"]
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
        # delvewheel vendors EVERY non-system DLL the extension links, not
        # just the OpenMP one, and renames each with a content hash — the
        # published wheel also carries msvcp140-<hash>.dll, which the
        # extension imports by that mangled name. Shipping only the OpenMP
        # DLL leaves the accelerator dead with "DLL load failed ... The
        # specified module could not be found". At runtime delvewheel's
        # `os.add_dll_directory` patch in momwire/__init__.py cannot help:
        # frozen, the package runs from the archive. So flatten the whole
        # vendored directory next to the bundle's own DLLs.
        for vendored in _vendored_dlls():
            if vendored != runtime:
                cmd += ["--add-binary", f"{vendored}{os.pathsep}."]
                print(f"vendored runtime: {vendored}")
        version_file = _write_version_file()
        cmd += ["--version-file", str(version_file)]
        print(f"version resource: {version_file} ({version('antennaknobs')})")
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
    _prune_gpl(bundle)
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
