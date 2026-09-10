"""Build the frozen NEC-5 corpus tool (issue #1376).

Run from the repo root, in an environment where pyinstaller is installed —
nothing else: the tool is one file, standard library only, and the build
must stay that way (the smoke proves it against a plain interpreter)::

    python scripts/freeze_nec5_corpus/build.py

Produces ``dist/nec5_corpus/``: ``nec5_corpus[.exe]``, a ``README.txt``, the
script's ``SECURITY-REVIEW.md`` (which must name this VERSION), the tool's
full ``README.md``, and ``catalog-nec5/`` — antennaknobs' own catalog designs
written as NEC-5 decks (476 of them, MIT, with a manifest) by
``export_catalog_nec5.py``, which is included too. The export needs
antennaknobs importable in the BUILD environment (not in the exe: the exe
stays standard-library only, and the smoke proves it with ``-S``); no NEC-5
engine is needed, the export builds its engine with ``require_exe=False``.
ONE-FILE on purpose, the opposite of the workbench's choice: a 2,000-line
stdlib script freezes to about 10 MB, self-extracts in well under a second,
and the working group asked for a tool, not a folder. (The workbench is
one-dir because its 160 MB bundle measured ~17 s per launch as one-file.)

Signing is opt-in through the environment, exactly as the workbench signs
(``scripts/freeze_workbench/sign.py`` is momwire's file, verbatim; loaded
from there, not copied): unset, the build is unsigned and needs no signtool;
``MOMWIRE_SIGN_MODE`` set promises a signed build and fails the build if no
identity reached it.

Why its own build and not a second EXE in the workbench bundle: the people
who want a NEC-5 regression corpus do not all want an antenna modeller, and
the tool changes on its own cadence. It is built on demand by
``.github/workflows/freeze-nec5-corpus.yml`` and published under its own
release tag, ``nec5-corpus-v<VERSION>``; it rides no antennaknobs release.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"
SIGN = ROOT / "scripts" / "freeze_workbench" / "sign.py"
REVIEW = SCRIPT.parent / "SECURITY-REVIEW.md"
EXPORT = SCRIPT.parent / "export_catalog_nec5.py"
TOOL_README = SCRIPT.parent / "README.md"
CATALOG = "catalog-nec5"
NAME = "nec5_corpus"
DIST = ROOT / "dist" / NAME

SCRIPT_URL = "https://github.com/stevenmburns/antennaknobs/blob/main/scripts/nec5_corpus/nec5_corpus.py"
README_URL = "https://github.com/stevenmburns/antennaknobs/blob/main/scripts/nec5_corpus/README.md"


def tool_version(script: Path = SCRIPT) -> str:
    """The ``VERSION = "..."`` literal in the script — what its reports record
    and what the release tag carries. Read from the text, not imported: the
    build environment need not be able to import the tool."""
    m = re.search(r'^VERSION = "([^"]+)"$', script.read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit(f"no VERSION literal in {script}")
    return m.group(1)


def _load_sign():
    spec = importlib.util.spec_from_file_location("freeze_workbench_sign", SIGN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _readme(bundle: Path, version: str, exe_name: str) -> None:
    (bundle / "README.txt").write_text(
        f"""nec5_corpus {version} -- a NEC-5 regression corpus from the public NEC-2 decks
==========================================================================

This is scripts/nec5_corpus/nec5_corpus.py from the antennaknobs repository,
packaged so that it runs without Python installed. Same tool, same version,
same reports: a translate-report.jsonl or check-report.jsonl written by this
program and one written by the script compare line for line.

catalog-nec5/ holds antennaknobs' own catalog designs as NEC-5 decks (MIT,
ours to share; manifest.json says what each is), written by the included
export_catalog_nec5.py from the same commit as this program. They are a
ready-made regression set: `{exe_name} check --exe <NEC5CL> --src catalog-nec5`.

Run it from a PowerShell or Command Prompt window in this folder:

    {exe_name} list                                    the sources fetch knows
    {exe_name} fetch     --out raw                     download the public decks
    {exe_name} translate --src raw --out nec5          rewrite them for NEC-5
    {exe_name} check     --exe "C:\\EZNEC 7.0\\Docs\\NEC5CL_x13.exe" --src nec5 --keep-dir failed
    {exe_name} compare   before.jsonl after.jsonl      diff two check reports
    {exe_name} --version

check needs your own licensed NEC-5 engine (EZNEC Pro+ keeps NEC5CL in its
Docs folder); nothing here contains or contacts one. Every subcommand takes
--help. The first launch takes a moment while the program unpacks itself.

Before you run it, SECURITY-REVIEW.md beside this file says what the program
can and cannot do to your machine: which subcommand touches the network and
where, what it writes and where, what it starts, and how to check the
signature and the checksum or build it yourself from the script.

What translate changes and why, what check classifies, and how compare
reads the reports:
    {README_URL}
The script itself, for anyone with a working Python 3.8 or newer:
    {SCRIPT_URL}

Source: https://github.com/stevenmburns/antennaknobs   Docs: https://antennaknobs.dev/
""",
        encoding="utf-8",
    )


def main() -> int:
    version = tool_version()
    if DIST.exists():
        shutil.rmtree(DIST)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--console",
        "--name",
        NAME,
        "--specpath",
        str(ROOT / "build"),
        "--workpath",
        str(ROOT / "build" / NAME),
        "--distpath",
        str(DIST),
        # A stdlib script pulls none of these; named so that a build venv
        # that happens to have them cannot grow the exe.
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "numpy",
        "--exclude-module",
        "antennaknobs",
        "--exclude-module",
        "momwire",
        str(SCRIPT),
    ]
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode
    exe = next((p for p in DIST.glob(f"{NAME}*") if p.is_file()), None)
    if exe is None:
        print(f"ERROR: no {NAME} executable in {DIST}", file=sys.stderr)
        return 1
    _readme(DIST, version, exe.name)
    # The review speaks for one version; the test suite pins it to VERSION.
    if f"nec5_corpus.py version {version}" not in REVIEW.read_text(encoding="utf-8"):
        print(f"ERROR: {REVIEW} does not name version {version}", file=sys.stderr)
        return 1
    shutil.copy(REVIEW, DIST / REVIEW.name)
    shutil.copy(TOOL_README, DIST / TOOL_README.name)
    shutil.copy(EXPORT, DIST / EXPORT.name)
    # The catalog decks, from the build environment's antennaknobs (the exe
    # itself excludes the package; this is a sibling process).
    export = subprocess.run(
        [sys.executable, str(EXPORT), "--out", str(DIST / CATALOG)], cwd=ROOT
    )
    if export.returncode != 0:
        print(
            "ERROR: catalog export failed (is antennaknobs installed here?)",
            file=sys.stderr,
        )
        return export.returncode
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
    size = exe.stat().st_size / 1e6
    print(
        f"built {exe} v{version} {size:.1f} MB ({'signed' if signed else 'unsigned'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
