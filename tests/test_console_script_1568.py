"""#1568: a pip install puts an `antennaknobs` command on PATH.

Before this, the package declared no console entry point, so PyPI users had
only `python -m antennaknobs`; `antennaknobs sweep ...` typed in PowerShell
said "command not found" (Dan AC6LA, QRZ 1003328 #86). The declaration is
read from pyproject.toml directly, because the installed metadata only
carries it after a reinstall and CI's wheel-smoke lane is the place that
proves the installed command; the callable it names is resolved and called
here."""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _script() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return data["project"]["scripts"]["antennaknobs"]


def test_the_console_script_is_declared():
    assert _script() == "antennaknobs.cli:cli"


def test_the_entry_point_resolves_and_answers_help(capsys):
    module_name, attr = _script().split(":")
    target = getattr(importlib.import_module(module_name), attr)
    with pytest.raises(SystemExit) as exc:
        target(["--help"])
    assert exc.value.code == 0
    assert "sweep" in capsys.readouterr().out


def test_a_successful_run_returns_nothing_the_wrapper_turns_into_exit_0(capsys):
    module_name, attr = _script().split(":")
    target = getattr(importlib.import_module(module_name), attr)
    assert target(["list", "dipole"]) is None
    assert "dipole" in capsys.readouterr().out
