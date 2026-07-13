"""Static safety screening of user design files (antennaknobs.design_screen).

The screen is defense-in-depth against a naive user running a malicious `.py`
they were handed — it AST-parses without executing and refuses files that do
things a real antenna design never needs. These tests pin: (1) every shipped
design screens clean (the allow-list is calibrated to real designs), (2) the
dangerous constructs are caught, (3) the loader refuses a flagged file unless a
trust override is set, and (4) legitimate designs still load.
"""

from pathlib import Path

import pytest

import antennaknobs as ant
import antennaknobs.designs as builtin_designs
from antennaknobs import design_screen as ds

CLEAN = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder
import math

class Builder(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0, "half_length": 5.0})

    def build_wires(self):
        h = self.half_length * math.cos(0.0)
        n = self.nominal_nsegs
        return [
            ((0.0, -h, 0.0), (0.0, -0.01, 0.0), n, None),
            ((0.0, 0.01, 0.0), (0.0, h, 0.0), n, None),
            ((0.0, -0.01, 0.0), (0.0, 0.01, 0.0), 1, 1 + 0j),
        ]
"""


def _prepend_to_clean(*lines: str) -> str:
    """Insert extra statements into CLEAN's build_wires body so they screen in
    a realistic file (import lines go at module top instead)."""
    inject = "\n".join(f"        {ln}" for ln in lines)
    return CLEAN.replace(
        "        h = self.half_length", inject + "\n        h = self.half_length"
    )


# --- 1. every built-in design is clean --------------------------------------


def _builtin_design_files():
    root = Path(builtin_designs.__file__).parent
    return [p for p in sorted(root.rglob("*.py")) if p.name != "__init__.py"]


@pytest.mark.parametrize("path", _builtin_design_files(), ids=lambda p: p.stem)
def test_builtin_designs_screen_clean(path):
    report = ds.screen_file(path)
    assert not report.blocked, report.summary()


# --- 2. dangerous constructs are caught -------------------------------------


@pytest.mark.parametrize(
    "src, needle",
    [
        ("import os\n", "os"),
        ("import subprocess\n", "subprocess"),
        ("import socket\n", "socket"),
        ("from urllib import request\n", "urllib"),
        ("import shutil, ctypes\n", "shutil"),
        ("open('/etc/passwd')\n", "open"),
        ("exec('x=1')\n", "exec"),
        ("eval('1+1')\n", "eval"),
        ("compile('x', 'f', 'exec')\n", "compile"),
        ("__import__('os')\n", "__import__"),
        ("y = ().__class__.__bases__\n", "__bases__"),
        ("z = object.__subclasses__()\n", "__subclasses__"),
        ("g = (lambda: 0).__globals__\n", "__globals__"),
        ("b = __builtins__\n", "__builtins__"),
    ],
)
def test_dangerous_constructs_are_high(src, needle):
    report = ds.screen_source(src, "x.py")
    assert report.blocked
    assert report.high, f"expected a HIGH finding for {needle!r}"
    assert any(needle in f.message for f in report.high)


def test_data_driven_design_screens_clean():
    # A design that loads geometry from a sidecar via the blessed read_json
    # helper imports only from antennaknobs — no open/pathlib — so it passes.
    src = _prepend_to_clean('spec = read_json(self, "wires.json")')
    assert not ds.screen_source(src, "data.py").blocked


@pytest.mark.parametrize("mod", ["json", "csv"])
def test_benign_data_parsers_allowed(mod):
    # Parsing formats is harmless (they can't reach the filesystem alone);
    # allow-listed so a design may e.g. parse an inline JSON string.
    assert not ds.screen_source(f"import {mod}\n", "x.py").blocked


def test_unrecognized_import_is_medium_not_high():
    # A stdlib module that isn't obviously dangerous but is off-contract:
    # flagged so the user notices, but not alarming.
    report = ds.screen_source("import turtle\n", "x.py")
    assert report.blocked
    assert not report.high
    assert report.medium and "turtle" in report.medium[0].message


def test_dynamic_getattr_is_medium_constant_getattr_is_clean():
    dynamic = ds.screen_source("getattr(x, name)\n", "x.py")
    assert dynamic.medium and not dynamic.high
    constant = ds.screen_source("getattr(x, 'freq')\n", "x.py")
    assert not constant.blocked


def test_relative_import_flagged():
    report = ds.screen_source("from . import helper\n", "x.py")
    assert report.blocked
    assert any("relative import" in f.message for f in report.findings)


def test_clean_design_screens_clean():
    assert not ds.screen_source(CLEAN, "good.py").blocked


def test_syntax_error_propagates_not_wrapped():
    # An unparseable file can't run anyway; the native SyntaxError (with the
    # line/reason the author needs) must surface rather than a screen finding.
    with pytest.raises(SyntaxError):
        ds.screen_source("def build(:\n", "broken.py")


# Note: the loader trust gate (which files execute) is tested in
# test_design_trust.py. This file covers only the pure static analyzer.


# --- 3. `antennaknobs screen <file>` CLI ------------------------------------


def test_screen_cli_clean_file_exits_zero(tmp_path, capsys):
    f = tmp_path / "good.py"
    f.write_text(CLEAN)
    ant.cli(["screen", str(f)])  # no SystemExit on a clean file
    assert "nothing unusual" in capsys.readouterr().out


def test_screen_cli_malicious_file_exits_one(tmp_path, capsys):
    f = tmp_path / "great_antenna.py"
    f.write_text(CLEAN.replace("import math\n", "import math\nimport socket\n"))
    with pytest.raises(SystemExit) as ei:
        ant.cli(["screen", str(f)])
    assert ei.value.code == 1
    assert "socket" in capsys.readouterr().out


def test_screen_cli_missing_file_exits_two(tmp_path, capsys):
    with pytest.raises(SystemExit) as ei:
        ant.cli(["screen", str(tmp_path / "nope.py")])
    assert ei.value.code == 2
