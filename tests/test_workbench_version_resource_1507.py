"""The Windows version resource on the frozen exe (issue #1507 follow-up).

`scripts/freeze_workbench/version_file.py` has no PyInstaller import (it must
stay importable on Linux for this test), so it is loaded the same way
`test_workbench_exe_flags.py` loads `entry.py`: by adding the script
directory to `sys.path`.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "scripts" / "freeze_workbench")
)
import version_file


@pytest.mark.parametrize(
    ("v", "expected"),
    [
        ("0.77.0", (0, 77, 0, 0)),
        ("1.2.3", (1, 2, 3, 0)),
        ("0.77", (0, 77, 0, 0)),
        ("2", (2, 0, 0, 0)),
        # A dev/local suffix has no DWORD slot, so only the numeric release
        # in front of it is kept — the full string still rides the
        # FileVersion/ProductVersion *strings*, checked separately below.
        ("0.78.0.dev3", (0, 78, 0, 0)),
        ("0.78.0.dev3+g1234abc", (0, 78, 0, 0)),
        ("0.78.0rc1", (0, 78, 0, 0)),
    ],
)
def test_numeric_release_keeps_only_the_leading_release_segment(v, expected):
    assert version_file.numeric_release(v) == expected


def test_a_plain_release_string_appears_verbatim_in_the_generated_text():
    text = version_file.build_version_info(
        "0.77.0",
        name="antennaknobs-workbench",
        product_name="antennaknobs workbench",
        company="Steven Burns",
        copyright_str="Copyright (c) 2024 Steven Burns",
    )
    assert "(0, 77, 0, 0)" in text
    assert "'0.77.0'" in text
    assert "antennaknobs workbench" in text
    assert "Steven Burns" in text


def test_a_dev_version_keeps_the_full_string_and_a_numeric_tuple():
    """A dev/local version (e.g. between releases) must not crash the
    generator and must not silently truncate the string fields — only the
    DWORD tuple loses the suffix."""
    dev = "0.78.0.dev3+g1234abc"
    text = version_file.build_version_info(
        dev,
        name="antennaknobs-workbench",
        product_name="antennaknobs workbench",
        company="Steven Burns",
        copyright_str="Copyright (c) 2024 Steven Burns",
    )
    assert "(0, 78, 0, 0)" in text
    assert f"'{dev}'" in text


def test_generated_text_parses_as_a_vsversioninfo_literal():
    """The file PyInstaller's `--version-file` reads is eval()'d verbatim by
    `PyInstaller.utils.win32.versioninfo.load_version_info_from_text_file`
    inside that module's own namespace. `PyInstaller.utils.win32.versioninfo`
    itself only imports on Windows (`PyInstaller.compat.win32api` is
    Windows-only), so this parses the literal directly against that module's
    classes rather than through the loader function, and skips on any
    platform where the module cannot be imported at all."""
    try:
        import PyInstaller.utils.win32.versioninfo as vi
    except ImportError as exc:
        pytest.skip(f"PyInstaller.utils.win32.versioninfo not importable here: {exc}")

    text = version_file.build_version_info(
        "0.77.0",
        name="antennaknobs-workbench",
        product_name="antennaknobs workbench",
        company="Steven Burns",
        copyright_str="Copyright (c) 2024 Steven Burns",
    )
    info = eval(  # noqa: S307 — trusted, locally generated text, same as PyInstaller's own loader
        text,
        {
            "VSVersionInfo": vi.VSVersionInfo,
            "FixedFileInfo": vi.FixedFileInfo,
            "StringFileInfo": vi.StringFileInfo,
            "StringTable": vi.StringTable,
            "StringStruct": vi.StringStruct,
            "VarFileInfo": vi.VarFileInfo,
            "VarStruct": vi.VarStruct,
        },
    )
    assert isinstance(info, vi.VSVersionInfo)
    assert info.ffi.fileVersionMS == (0 << 16) | 77
    assert info.ffi.fileVersionLS == (0 << 16) | 0


def test_module_has_no_pyinstaller_import():
    """Load-bearing for the test above: this module must stay importable on
    Linux, where PyInstaller.utils.win32.versioninfo cannot be (it imports
    PyInstaller.compat.win32api, which is Windows-only)."""
    src = importlib.util.find_spec("version_file")
    assert src is not None
    text = Path(src.origin).read_text(encoding="utf-8")
    assert "import PyInstaller" not in text
