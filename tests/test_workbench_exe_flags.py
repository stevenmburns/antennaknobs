"""The packaged workbench's engine flags, ``--nec5-exe`` and ``--nec2-exe``.

The engine path already had two routes into the workbench: the ``NEC5_EXE`` /
``NEC2_EXE`` variables and a one-line ``NEC5_EXE.txt`` / ``NEC2_EXE.txt`` beside
the program. The variable is spelled one way in PowerShell and another in
Command Prompt, and users mix the two up, so the path can also go on the
command line, which reads the same in both. The order is flag, then variable,
then file.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "scripts" / "freeze_workbench")
)
import entry

ENGINES = [
    ("NEC5_EXE", "--nec5-exe", "NEC5_EXE.txt"),
    ("NEC2_EXE", "--nec2-exe", "NEC2_EXE.txt"),
]


@pytest.fixture
def bundle(monkeypatch, tmp_path):
    """An empty folder standing in for the one beside the executable, with both
    variables unset. setenv to "" rather than delenv: the code under test
    writes os.environ directly, and a delenv on an absent name records nothing
    for monkeypatch to restore, which is how a #1428 test once leaked its
    capture directory into another module."""
    for var, _flag, _fname in ENGINES:
        monkeypatch.setenv(var, "")
    monkeypatch.setattr(entry, "_bundle_dir", lambda: tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    "argv",
    [
        [
            "--nec5-exe",
            r"C:\EZNEC 7.0\Docs\NEC5CL_x13.exe",
            "--nec2-exe",
            "/usr/bin/nec2c",
        ],
        ["--nec5-exe=C:\\EZNEC 7.0\\Docs\\NEC5CL_x13.exe", "--nec2-exe=/usr/bin/nec2c"],
    ],
)
def test_both_spellings_of_each_flag_parse(argv):
    opts = entry._parse(argv)
    assert opts["nec5_exe"] == r"C:\EZNEC 7.0\Docs\NEC5CL_x13.exe"
    assert opts["nec2_exe"] == "/usr/bin/nec2c"


@pytest.mark.parametrize(
    "flag", ["--nec5-exe", "--nec2-exe", "--port", "--capture-dir", "--log-level"]
)
def test_a_flag_missing_its_value_is_a_usage_error_naming_the_flag(flag, capsys):
    with pytest.raises(SystemExit) as exc:
        entry._parse(["--no-browser", flag])
    assert exc.value.code == 2
    assert flag in capsys.readouterr().err


@pytest.mark.parametrize(("var", "flag", "fname"), ENGINES)
@pytest.mark.parametrize(
    ("given_flag", "given_var", "given_file", "expected"),
    [
        ("/from/flag", "/from/var", "/from/file", "/from/flag"),
        ("/from/flag", None, "/from/file", "/from/flag"),
        (None, "/from/var", "/from/file", "/from/var"),
        (None, None, "/from/file", "/from/file"),
        (None, None, None, ""),
    ],
)
def test_flag_then_variable_then_file(
    bundle, monkeypatch, var, flag, fname, given_flag, given_var, given_file, expected
):
    if given_var:
        monkeypatch.setenv(var, given_var)
    if given_file:
        (bundle / fname).write_text(f"# the engine\n{given_file}\n")
    entry._apply_capture_opts(entry._parse([flag, given_flag] if given_flag else []))
    entry._apply_exe_files()
    assert os.environ.get(var, "") == expected


def test_main_settles_both_engines_before_anything_starts(bundle, monkeypatch):
    """One launch, all three routes at once: NEC-5 named by flag over a file,
    NEC-2 by variable over a file. `selftest` stands in for the server, so what
    it sees is what the workbench would start with."""
    (bundle / "NEC5_EXE.txt").write_text("/from/file/nec5\n")
    (bundle / "NEC2_EXE.txt").write_text("/from/file/nec2\n")
    monkeypatch.setenv("NEC2_EXE", "/from/var/nec2")
    monkeypatch.setenv("MPLBACKEND", "Agg")
    seen = {}

    def fake_selftest():
        seen.update({var: os.environ[var] for var, _flag, _fname in ENGINES})
        return 0

    monkeypatch.setattr(entry, "selftest", fake_selftest)
    assert entry.main(["--selftest", "--nec5-exe", "/from/flag/nec5"]) == 0
    assert seen == {"NEC5_EXE": "/from/flag/nec5", "NEC2_EXE": "/from/var/nec2"}


@pytest.mark.parametrize(("var", "flag", "fname"), ENGINES)
def test_the_startup_line_names_every_route_when_no_engine_is_set(
    bundle, var, flag, fname
):
    line = entry._engine_line(var)
    assert line.startswith("not set")
    assert flag in line and fname in line


@pytest.mark.parametrize(("var", "flag", "fname"), ENGINES)
def test_the_startup_line_flags_a_path_that_is_not_an_executable_file(
    bundle, monkeypatch, var, flag, fname
):
    """A mistyped path used to print as if it were fine, and the engine's tab
    then never appeared. `find_exe` treats a path that is not an executable
    file as no engine, so the startup line says so."""
    missing = bundle / "no-such-engine.exe"
    monkeypatch.setenv(var, str(missing))
    assert "not an executable file" in entry._engine_line(var)

    real = bundle / "engine.exe"
    real.write_text("")
    real.chmod(0o755)
    monkeypatch.setenv(var, str(real))
    assert entry._engine_line(var) == str(real)


@pytest.mark.parametrize(
    "argv",
    [["--settings", r"C:\ak\settings.toml"], [r"--settings=C:\ak\settings.toml"]],
)
def test_the_settings_flag_sets_the_variable_the_server_reads(argv, monkeypatch):
    """AK#1492: --settings becomes ANTENNAKNOBS_SETTINGS, in both spellings."""
    monkeypatch.setenv("ANTENNAKNOBS_SETTINGS", "")
    opts = entry._parse(argv)
    assert opts["settings"] == r"C:\ak\settings.toml"
    entry._apply_capture_opts(opts)
    assert os.environ["ANTENNAKNOBS_SETTINGS"] == r"C:\ak\settings.toml"


def test_the_settings_flag_missing_its_value_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        entry._parse(["--settings"])
    assert exc.value.code == 2
    assert "--settings needs a value" in capsys.readouterr().err


@pytest.mark.parametrize(("var", "flag", "fname"), ENGINES)
def test_the_settings_file_sits_between_the_variable_and_the_text_file(
    bundle, monkeypatch, var, flag, fname
):
    """AK#1492: an engine the settings file names is left for the library to
    read, so NEC5_EXE.txt is not consulted, and a variable still wins."""
    key = {"NEC5_EXE": "nec5_exe", "NEC2_EXE": "nec2_exe"}[var]
    settings = bundle / "settings.toml"
    settings.write_text(f'[engines]\n{key} = "/from/settings"\n')
    monkeypatch.setenv("ANTENNAKNOBS_SETTINGS", str(settings))
    (bundle / fname).write_text("/from/file\n")
    entry._apply_capture_opts(entry._parse([]))
    entry._apply_exe_files()
    assert os.environ.get(var, "") == ""
    line = entry._engine_line(var)
    assert line.startswith("/from/settings") and "from settings.toml" in line
    monkeypatch.setenv(var, "/from/var")
    assert entry._engine_line(var).startswith("/from/var")
