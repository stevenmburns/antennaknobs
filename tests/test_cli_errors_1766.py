"""Clean one-line CLI errors for an unavailable --engine and a file given as a
--builder name (AK#1766; QRZ 1003328 #166).

Both used to surface badly: an engine spec is validated AFTER argparse, so its
`ArgumentTypeError` escaped as a traceback, and `nec2`/`nec5` without a
configured binary read "unknown engine" though the name is right. A deck
file named where a design name goes (`--builder user.4n2loopsegs.nec`) said
only "unknown builder" with no hint that `@file.nec` is the file route.
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import antennaknobs as ant

cli_mod = importlib.import_module("antennaknobs.cli")

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture
def no_external_engines(tmp_path, monkeypatch):
    """No NEC-2/NEC-5 on the roster, no env var, no settings file."""
    for name in ("nec2", "nec5"):
        monkeypatch.delitem(cli_mod.ENGINE_CLASSES, name, raising=False)
    monkeypatch.delenv("NEC2_EXE", raising=False)
    monkeypatch.delenv("NEC5_EXE", raising=False)
    settings = tmp_path / "no-such-settings.toml"
    monkeypatch.setenv("ANTENNAKNOBS_SETTINGS", str(settings))
    return settings


def _cli_error(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        ant.cli(argv)
    err = capsys.readouterr().err
    return exc.value.code, err


def _one_error_line(err):
    lines = [ln for ln in err.splitlines() if ": error: " in ln]
    assert len(lines) == 1, err
    assert "Traceback" not in err
    return lines[0]


@pytest.mark.parametrize(
    ("engine", "env_var", "key"),
    [("nec2", "NEC2_EXE", "nec2_exe"), ("nec5", "NEC5_EXE", "nec5_exe")],
)
def test_unconfigured_external_engine_names_what_it_needs(
    engine, env_var, key, no_external_engines, capsys
):
    code, err = _cli_error(
        [
            "pattern",
            "--builder",
            "dipoles.invvee",
            "--engine",
            engine,
            "--fn",
            os.devnull,
        ],
        capsys,
    )
    assert code == 2
    line = _one_error_line(err)
    assert " pattern: error: " in line
    assert f"engine {engine!r} needs" in line
    assert f"{env_var} environment variable" in line
    assert key in line and "settings.toml" in line
    assert "unknown engine" not in line


def test_multi_engine_sweep_reports_the_missing_engine(no_external_engines, capsys):
    """The issue's own repro: a comma list naming nec2 on the sweep."""
    code, err = _cli_error(
        [
            "sweep",
            "--builder",
            "specialty.hentenna",
            "--param",
            "nominal_nsegs",
            "--range",
            "8",
            "10",
            "--npoints",
            "2",
            "--engine",
            "nec2,momwire",
            "--overlay",
            "--ground",
            "free",
        ],
        capsys,
    )
    assert code == 2
    line = _one_error_line(err)
    assert " sweep: error: engine 'nec2' needs a NEC-2 console binary" in line
    assert "NEC2_EXE" in line and "nec2_exe" in line


def test_plural_engines_subcommand_is_covered(no_external_engines, capsys):
    code, err = _cli_error(
        [
            "compare_patterns",
            "--builders",
            "dipoles.invvee",
            "--engines",
            "momwire",
            "nec5",
            "--fn",
            os.devnull,
        ],
        capsys,
    )
    assert code == 2
    assert "engine 'nec5' needs" in _one_error_line(err)


def test_unknown_engine_lists_valid_names(no_external_engines, capsys):
    code, err = _cli_error(
        [
            "pattern",
            "--builder",
            "dipoles.invvee",
            "--engine",
            "bogus",
            "--fn",
            os.devnull,
        ],
        capsys,
    )
    assert code == 2
    line = _one_error_line(err)
    assert "unknown engine 'bogus'; available: " in line
    assert "momwire" in line
    # The configurable ones are named too, so the user learns they exist.
    assert "nec2" in line and "nec5" in line


def test_configured_path_that_is_not_executable(
    tmp_path, no_external_engines, monkeypatch
):
    fake = tmp_path / "nec2c"
    fake.write_text("not a binary")  # no execute bit
    monkeypatch.setenv("NEC2_EXE", str(fake))
    msg = cli_mod._engine_unavailable_message("nec2")
    assert "$NEC2_EXE" in msg and "not an executable file" in msg


def test_settings_file_path_is_reported_as_the_source(no_external_engines):
    no_external_engines.write_text(
        "[engines]\nnec5_exe = '/definitely/not/here/nec5cl'\n", encoding="utf-8"
    )
    msg = cli_mod._engine_unavailable_message("nec5")
    assert "nec5_exe in settings.toml" in msg
    assert "/definitely/not/here/nec5cl" in msg


def test_pynec_absent_names_the_package(monkeypatch):
    monkeypatch.delitem(cli_mod.ENGINE_CLASSES, "pynec", raising=False)
    assert "pynec-accel" in cli_mod._engine_unavailable_message("pynec")


def test_no_traceback_in_a_real_process(tmp_path):
    """End to end through `python -m antennaknobs`: the exit status and the
    stderr a user sees, with no binary configured anywhere."""
    env = {k: v for k, v in os.environ.items() if k not in ("NEC2_EXE", "NEC5_EXE")}
    env["ANTENNAKNOBS_SETTINGS"] = str(tmp_path / "none.toml")
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(SRC), env.get("PYTHONPATH", "")) if p
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "antennaknobs",
            "pattern",
            "--builder",
            "dipoles.invvee",
            "--engine",
            "nec2",
            "--fn",
            os.devnull,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=300,
    )
    assert proc.returncode == 2, proc.stderr
    assert "Traceback" not in proc.stderr
    assert "engine 'nec2' needs a NEC-2 console binary" in proc.stderr


# --- builder spelling -------------------------------------------------------


@pytest.fixture
def deck_dir(tmp_path, monkeypatch):
    """A working directory holding Dan's deck, and an empty user folder."""
    (tmp_path / "4n2LoopSegs.nec").write_text("CM\nCE\n", encoding="utf-8")
    users = tmp_path / "users"
    users.mkdir()
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(users))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _builder_error(spec):
    with pytest.raises(SystemExit) as exc:
        ant.cli(["draw", "--builder", spec, "--fn", os.devnull])
    return str(exc.value.code)


@pytest.mark.parametrize("spec", ["user.4n2loopsegs.nec", "4n2loopsegs.nec"])
def test_file_given_as_design_name_suggests_the_at_form(spec, deck_dir):
    msg = _builder_error(spec)
    assert "\n" not in msg
    assert f"unknown builder {spec!r}: no design is named that" in msg
    # The file's REAL name (case-insensitive match in the cwd), not a guess.
    assert "to load a file use --builder @4n2LoopSegs.nec" in msg
    assert "user.<name>" in msg and "family.design[:variant]" in msg


def test_file_name_with_no_such_file_still_points_at_at(deck_dir):
    """No other.nec is here, so the hint names the form, not a path that
    does not exist."""
    msg = _builder_error("user.other.nec")
    assert "to load a file use --builder @<path to other.nec>" in msg
    assert "@other.nec" not in msg


def test_python_file_name_points_at_the_user_name(deck_dir):
    msg = _builder_error("user.mything.py")
    assert "--builder user.mything" in msg
    assert "@" not in msg.split("builder forms:")[0]


def test_deck_in_user_folder_suggests_its_user_name(deck_dir):
    (deck_dir / "users" / "MyLoop.nec").write_text("CM\nCE\n", encoding="utf-8")
    msg = _builder_error("user.myloop.nec")
    assert "--builder user.MyLoop" in msg


def test_file_name_is_not_silently_reinterpreted(deck_dir):
    """The refusal must stay a refusal: `user.x.nec` never loads the file."""
    assert cli_mod.resolve_class("user.4n2loopsegs.nec") is None
    with pytest.raises(SystemExit):
        cli_mod.get_builder("user.4n2LoopSegs.nec")


def test_plain_typo_keeps_the_short_message(deck_dir):
    msg = _builder_error("dipoles.invee")
    assert msg.startswith("unknown builder 'dipoles.invee'; builder forms:")


def test_user_design_name_in_the_wrong_case(deck_dir):
    (deck_dir / "users" / "MyLoop.nec").write_text("CM\nCE\n", encoding="utf-8")
    msg = _builder_error("user.myloop")
    assert "did you mean --builder user.MyLoop?" in msg
