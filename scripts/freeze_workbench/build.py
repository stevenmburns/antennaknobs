"""Build the frozen antennaknobs workbench (issue #1349).

Run from the repo root, in an environment where antennaknobs[web] (this
checkout or the wheel) and pyinstaller are installed::

    python scripts/freeze_workbench/build.py

Produces ``dist/antennaknobs-workbench/``: the launcher
``antennaknobs-workbench[.exe]``, the command line ``antennaknobs-cli[.exe]``
beside it (issue #1566), and the one ``_internal`` runtime they share. The
directory must be kept together. One-dir on purpose — one-file self-extracts
on every launch (momwire's EZNEC bundle measured ~17 s per launch that way).

TWO EXECUTABLES, ONE BUNDLE, which is why this drives PyInstaller through a
GENERATED SPEC FILE rather than the command line it used through #1349: the
command line builds one entry point per run, and a second run would produce a
second ``_internal`` and double the zip. A spec can name two ``EXE(...)``
objects and feed both to one ``COLLECT(...)``, which is PyInstaller's own
multi-executable one-dir layout. The spec is written fresh into ``build/`` on
every build from the constants below — it is a build artefact, not a file to
hand-edit.

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
# The second executable (issue #1566). A shim: it runs the workbench program
# beside it with `--cli` in front of the user's arguments, so the bundle holds
# ONE copy of the code. PyInstaller keeps a one-dir program's module archive
# inside its own executable — the workbench is 21.7 MB of bootloader plus a
# 21.6 MB PYZ — so a second full entry point would have shared `_internal`
# (322 MB) but carried a second copy of that archive: +21 MB on a 76 MB zip
# for the same code. `entry_cli.py` imports only the standard library and
# freezes to 1.8 MB. Measured 2026-09-17; `cli_main.py` has the reasoning.
CLI_NAME = "antennaknobs-cli"

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
    # The interactive backend (issue #1566). `antennaknobs-cli` with no --fn
    # opens the chart in a window with matplotlib's toolbar — zoom and pan on
    # the Smith chart — and matplotlib reaches its backends by string, so
    # neither this module nor tkinter under it is visible to the static
    # trace. Naming it here is also what pulls tkinter in, which in turn
    # triggers PyInstaller's own tkinter hook and collects Tcl/Tk's script
    # library into `_internal` (~7 MB); `tkinter.Tk()` reads `init.tcl` from
    # it at startup, so without the hook an interactive chart dies on a
    # missing file rather than a missing import. A build on a Python with no
    # tkinter (this Linux venv) merely warns that the hidden import was not
    # found, and the bundle is the Agg-only one it always was — which is why
    # smoke.py's Tk gate reports itself skipped there rather than passing.
    "matplotlib.backends.backend_tkagg",
)

# Modules kept OUT of the bundle by name. Two reasons, both about what a
# developer's build venv happens to contain rather than what the program
# needs:
#
# PyNEC is GPL and the workbench is not. `pyproject.toml` keeps it out of
# every extra on purpose and antennaknobs#1354's text coupling means no
# served path imports it — but `collect_submodules('antennaknobs')` follows
# the BUILD VENV, so a developer whose venv has `pynec-accel` installed
# shipped `PyNEC.py`, `_PyNEC*.so` and a 27 MB `pynec_accel.libs/` without
# being told. Measured 2026-09-10 on a dev box: 36 MB of GPL code in the
# bundle. `pynec-accel` publishes the two top-level names below; `smoke.py`
# gate 0 asserts the OUTCOME, so the licence does not rest on this list
# tracking the wheel.
#
# Nothing in a served path imports pandas, and the shipped v0.73.0 Windows
# zip has none — but a build venv that happens to have it gets 18 MB of it
# collected. Excluded by name so the bundle's contents are a property of this
# file rather than of whoever's venv ran it.
#
# tkinter was on this list until #1566 and is deliberately NOT any more: the
# CLI's interactive charts need it.
EXCLUDES = (
    "PyQt6",
    "PySide6",
    "IPython",
    "PyNEC",
    "_PyNEC",
    "pandas",
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

BEFORE EXTRACTING: right-click the downloaded zip, Properties, tick
"Unblock", OK - then extract. Windows marks a file it downloaded, and every
file extracted from a marked zip inherits the mark, so unblocking the one zip
before it becomes several hundred files is the easy moment. If this folder
came out of a zip you did not unblock, delete the folder, unblock the zip and
extract it again; nothing else here depends on the old folder.

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

THE COMMAND LINE
================

{CLI_NAME}.exe in this folder is the same program's command line - what
`python -m antennaknobs` runs for someone who installed from PyPI. Open a
PowerShell window in this folder (Shift+right-click the folder background,
"Open PowerShell window here") and put .\\ in front of the name:

    .\\{CLI_NAME}.exe --help
    .\\{CLI_NAME}.exe sweep --param nominal_nsegs --builder dipoles.invvee:dipole --engine momwire:bspline

The second line is a convergence study: one cold solve per segment count, a
table of R, X and the change in reflection coefficient per rung, and a
Richardson-extrapolated Z* under it. With no --fn the chart opens in a window
with the matplotlib toolbar, so the Smith chart zooms and pans; add
--fn out.png to write the picture to a file instead.

It finds NEC-5 and NEC-2 the way the workbench does, through the same
NEC5_EXE.txt and NEC2_EXE.txt beside it, the same variables and the same
settings.toml, so an engine set up once is set up for both. It does the work
by running {NAME}.exe, so it needs that file and
_internal beside it like everything else here.

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


def _write_version_file(name: str, description: str, filename: str) -> Path:
    """The PyInstaller `version=` text for one executable, generated fresh
    from the package's OWN version (issue #1517 follow-up) — the same source
    the web label and the console banner read, so Explorer's Properties ->
    Details can never disagree with either. Windows-only: a version resource
    is a PE concept, and PyInstaller merely warns and ignores `version=`
    elsewhere.

    Both executables in the bundle get one (issue #1566), at the same version
    and under the same ProductName: they are two faces of one program, and a
    second .exe with no resource at all would be the unlabelled file in the
    folder."""
    text = build_version_info(
        version("antennaknobs"),
        name=name,
        product_name="antennaknobs workbench",
        company="Steven Burns",
        copyright_str=_license_copyright(),
        file_description=description,
    )
    out = Path("build") / filename
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


def _exe_block(
    variable: str, pyz: str, scripts: str, name: str, version_file: Path | None
) -> str:
    """One ``EXE(...)`` object for the spec. Every argument below is
    PyInstaller's own default for a `--onedir --console` build (the shape
    `pyi-makespec` writes), so the two executables differ only in their
    script, their name and their version resource."""
    version = repr(str(version_file.resolve())) if version_file else "None"
    return f"""{variable} = EXE(
    {pyz},
    {scripts},
    [],
    exclude_binaries=True,
    name={name!r},
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version={version},
)
"""


def _write_spec(
    datas: list[tuple[str, str]],
    binaries: list[tuple[str, str]],
    version_files: dict[str, Path],
) -> Path:
    """The generated ``.spec``: two entry points, one collected folder.

    `datas` and `binaries` are the entries this file computes itself (the
    designs directory; on Windows the vendored DLLs). The package-wide
    collection stays in the spec as `collect_submodules` /
    `collect_data_files` calls, which are what the old command line's
    `--collect-submodules` / `--collect-data` flags became anyway.

    Only the workbench Analysis collects anything: the shim imports nothing
    but the standard library, and COLLECT normalises the two TOCs into one,
    so `_internal` is exactly the folder the single-entry build produced.
    """
    spec = Path("build") / f"{NAME}.spec"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(
        f"""# -*- mode: python ; coding: utf-8 -*-
# GENERATED by scripts/freeze_workbench/build.py on every build — edit that
# file, never this one.
#
# Two EXE objects, one COLLECT (issue #1566): `antennaknobs-workbench` is the
# program, `antennaknobs-cli` the shim that runs it with `--cli`. One
# `_internal`, one dist folder, one zip.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = {list(HIDDEN_IMPORTS)!r}
hiddenimports += collect_submodules('antennaknobs')
hiddenimports += collect_submodules('momwire')

datas = collect_data_files('antennaknobs') + collect_data_files('schemdraw')
datas += {datas!r}
binaries = {binaries!r}
excludes = {list(EXCLUDES)!r}

a = Analysis(
    [{str(HERE / "entry.py")!r}],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
cli_a = Analysis(
    [{str(HERE / "entry_cli.py")!r}],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
cli_pyz = PYZ(cli_a.pure)

{_exe_block("exe", "pyz", "a.scripts", NAME, version_files.get(NAME))}
{_exe_block("cli_exe", "cli_pyz", "cli_a.scripts", CLI_NAME, version_files.get(CLI_NAME))}
coll = COLLECT(
    exe,
    cli_exe,
    a.binaries,
    a.datas,
    cli_a.binaries,
    cli_a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name={NAME!r},
)
""",
        encoding="utf-8",
    )
    return spec


def main() -> int:
    # The design catalog is discovered by LISTING the package's `designs`
    # directory (`adapter.list_designs` walks it with iterdir), and a frozen
    # bundle keeps modules inside its archive with no directory to list. So
    # the directory ships as data beside the archive too — the modules still
    # import from the archive; the listing sees the files.
    import antennaknobs

    designs = Path(antennaknobs.__file__).resolve().parent / "designs"
    datas = [(str(designs), "antennaknobs/designs")]
    binaries: list[tuple[str, str]] = []
    version_files: dict[str, Path] = {}
    if os.name == "nt":
        runtime = _openmp_runtime()
        if runtime is None:
            print(
                f"ERROR: {OPENMP_DLL} is nowhere this build can see it; the "
                "bundle would ship with a dead accelerator (momwire#737)",
                file=sys.stderr,
            )
            return 1
        binaries.append((str(runtime), "."))
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
                binaries.append((str(vendored), "."))
                print(f"vendored runtime: {vendored}")
        version_files[NAME] = _write_version_file(
            NAME, "antennaknobs workbench", "workbench_version_info.txt"
        )
        version_files[CLI_NAME] = _write_version_file(
            CLI_NAME, "antennaknobs command line", "cli_version_info.txt"
        )
        print(f"version resources: {sorted(version_files)} ({version('antennaknobs')})")
    spec = _write_spec(datas, binaries, version_files)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        "dist",
        "--workpath",
        "build",
        str(spec),
    ]
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        return result.returncode
    bundle = Path("dist") / NAME
    exes = []
    for name in (NAME, CLI_NAME):
        # `glob(name + "*")` rather than an `.exe` test: the suffix is the
        # platform's, and CLI_NAME must not match the workbench's own glob.
        found = next(
            (p for p in bundle.glob(f"{name}*") if p.is_file() and p.stem == name),
            None,
        )
        if found is None:
            print(f"ERROR: no {name} executable in {bundle}", file=sys.stderr)
            return 1
        exes.append(found)
    _prune_gpl(bundle)
    _readme(bundle)
    signer = _load_sign()
    # ONE signing list, one signtool invocation, both executables (#1566) —
    # the second .exe is as much a release binary as the first, and an
    # unsigned file in a signed folder is the one Windows warns about.
    signed = signer.sign_if_configured(exes)
    mode = os.environ.get("MOMWIRE_SIGN_MODE")
    if mode and not signed:
        print(
            f"ERROR: MOMWIRE_SIGN_MODE={mode} promises a signed build but no "
            "signing identity reached build.py",
            file=sys.stderr,
        )
        return 1
    state = "signed" if signed else "unsigned"
    print(f"built {' and '.join(str(p) for p in exes)} ({state})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
