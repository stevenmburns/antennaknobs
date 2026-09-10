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
import shutil
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
remove it. Keep the folder together: the program needs _internal beside it.

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

This is the same program as `pip install "antennaknobs[web]"`, packaged.
Docs: https://antennaknobs.dev/   Source: https://github.com/stevenmburns/antennaknobs
""",
        encoding="utf-8",
    )


def _strip_debug_only(bundle: Path) -> None:
    """`strip --strip-debug` every ELF in the bundle: drop the DWARF, keep the
    symbol table.

    Not PyInstaller's `--strip`, which is `strip` with its defaults and takes
    the symbol table with it. momwire#1030 measured the difference on the
    largest binary here: 34.8 MB unstripped, 2.2 MB with `--strip-debug` and
    1998 symbols kept, 1.9 MB with `-s` and no symbols at all. 0.4 MB for
    named backtraces, in the one place where the person hitting the crash has
    neither a source tree nor a debugger.

    Failures are per-file and non-fatal: a binary that will not strip ships
    unstripped. Bigger, never broken.
    """
    stripped = kept = 0
    before = sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file())
    for p in bundle.rglob("*"):
        if not p.is_file() or p.is_symlink():
            continue
        try:
            with p.open("rb") as fh:
                if fh.read(4) != b"\x7fELF":
                    continue
        except OSError:
            continue
        try:
            subprocess.run(
                ["strip", "--strip-debug", str(p)],
                check=True,
                capture_output=True,
            )
            stripped += 1
        except (OSError, subprocess.CalledProcessError):
            kept += 1
    after = sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file())
    print(
        f"stripped DWARF from {stripped} ELF file(s), symbols kept"
        + (f", {kept} refused" if kept else "")
        + f": {before / 1048576:.0f} MB -> {after / 1048576:.0f} MB"
    )


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
    if os.name != "nt":
        # Linux/macOS only. The published momwire Linux wheel ships its two
        # extensions UNSTRIPPED — `_accelerators.so` is 34.8 MB "with
        # debug_info, not stripped", `_near_interface_accel.so` 5.4 MB —
        # against 1.8 MB for the same extension in the Windows zip, because
        # MSVC puts debug info in a separate .pdb that is not shipped. So the
        # 41 MB momwire entry in a Linux bundle is debug symbols, not a
        # platform difference: `strip --strip-unneeded` takes those two files
        # from 41 MB to 3 MB, and the stripped `_accelerators.so` is 1.9 MB,
        # which is the Windows figure.
        #
        # NOT on Windows, and this is the reason rather than a preference:
        # signed binaries must not be repacked after signing (#1349), and
        # `sign.py` runs on the collected bundle.
        #
        # PyInstaller's `--strip` is `strip` with its defaults, which discards
        # the SYMBOL TABLE as well as the DWARF. `_strip_debug_only()` below
        # runs `strip --strip-debug` instead, for the reason momwire#1030
        # settled on the same question: across momwire's two extensions the
        # symbol table costs 0.4 MB and buys a segfault backtrace that names
        # the functions instead of printing addresses. A frozen bundle is
        # exactly where that matters — the user reporting the crash has no
        # source tree and no debugger.
        pass  # handled after the build by `_strip_debug_only`
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
    if os.name != "nt":
        _strip_debug_only(bundle)
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
