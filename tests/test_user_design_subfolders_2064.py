"""Subfolders of the user designs folder are name parts (AK#2064).

A user on QRZ made ``mydesigns/my_dipole.py`` in the designs folder and nothing
made it appear: the scan read the top level only. The studies folder beside it
already read subfolders as name parts (``feeds/e7.py`` is the study
``feeds/e7``), so the designs folder now does the same:
``mydesigns/my_dipole.py`` is ``user.mydesigns.my_dipole``. A file at the top
level keeps the name it always had.
"""

from __future__ import annotations

import sys

import pytest

import antennaknobs.web.examples  # noqa: F401 — bootstraps the adapter + REGISTRY
from antennaknobs import design_trust
from antennaknobs import user_designs as core
from antennaknobs.cli import get_builder
from antennaknobs.web import user_designs
from antennaknobs.web.examples import REGISTRY

DESIGN = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    label = "{label}"
    default_params = MappingProxyType({{"freq": 14.0, "half_length": {h}}})

    def build_wires(self):
        h = self.half_length
        n = self.nominal_nsegs
        return [
            ((0.0, -h, 0.0), (0.0, -0.01, 0.0), n, None),
            ((0.0, 0.01, 0.0), (0.0, h, 0.0), n, None),
            ((0.0, -0.01, 0.0), (0.0, 0.01, 0.0), 1, 1 + 0j),
        ]
"""


def _write(path, label="d", h=5.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DESIGN.format(label=label, h=h))
    return path


@pytest.fixture
def userdir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)  # no ./antenna_designs from the repo's cwd

    def _clear():
        for k in [k for k in REGISTRY if k.startswith("user.")]:
            del REGISTRY[k]

    _clear()
    yield tmp_path
    _clear()


def test_a_design_in_a_subfolder_is_named_by_its_path(userdir):
    _write(userdir / "my_dipole.py")
    _write(userdir / "mydesigns" / "my_dipole.py")
    _write(userdir / "mydesigns" / "my_dipole_B.py")
    _write(userdir / "a" / "b" / "x.py")
    assert sorted(name for name, _ in core.iter_design_files()) == [
        "a.b.x",
        "my_dipole",
        "mydesigns.my_dipole",
        "mydesigns.my_dipole_B",
    ]


def test_a_rescan_picks_up_a_new_subfolder_without_a_restart(userdir):
    _write(userdir / "my_dipole.py")
    assert user_designs.refresh() == []
    assert "user.mydesigns.my_dipole" not in REGISTRY
    _write(userdir / "mydesigns" / "my_dipole.py")
    assert user_designs.refresh() == []
    assert "user.mydesigns.my_dipole" in REGISTRY
    assert "user.my_dipole" in REGISTRY
    _write(userdir / "mydesigns" / "my_dipole_B.py")
    user_designs.refresh()
    assert "user.mydesigns.my_dipole_B" in REGISTRY


def test_two_files_of_one_name_in_two_subfolders_are_two_designs(userdir):
    """Each keeps its own module: the old module name was the file name
    alone, so the second import replaced the first in `sys.modules`."""
    _write(userdir / "a" / "x.py", label="from a", h=4.0)
    _write(userdir / "b" / "x.py", label="from b", h=6.0)
    a = core.load_builder(core.find_design_file("a.x"))
    b = core.load_builder(core.find_design_file("b.x"))
    assert (a.label, b.label) == ("from a", "from b")
    assert a.__module__ != b.__module__
    assert sys.modules[a.__module__] is not sys.modules[b.__module__]


def test_private_and_dotted_subfolders_are_skipped(userdir):
    _write(userdir / "_drafts" / "x.py")
    _write(userdir / ".git" / "x.py")
    _write(userdir / "v1.2" / "x.py")
    _write(userdir / "ok" / "_helper.py")
    _write(userdir / "ok" / "TEMPLATE.py")  # a template only at the top level
    assert [name for name, _ in core.iter_design_files()] == ["ok.TEMPLATE"]


def test_the_cli_resolves_a_subfolder_design(userdir):
    _write(userdir / "mydesigns" / "my_dipole.py", label="sub")
    assert get_builder("user.mydesigns.my_dipole").label == "sub"


def test_trust_is_kept_per_file_in_a_subfolder(userdir, monkeypatch):
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_FILE", raising=False)
    a = _write(userdir / "a" / "x.py")
    b = _write(userdir / "b" / "x.py")
    design_trust.trust(a, mode="pinned")
    assert design_trust.is_trusted(a)
    assert not design_trust.is_trusted(b)
    errors = {e["name"]: e for e in user_designs.refresh()}
    assert "user.a.x" in REGISTRY
    assert errors["user.b.x"]["trust_required"]
    # The prompt names the design the way the allow command takes it.
    assert "allow b.x`" in errors["user.b.x"]["message"]


def test_a_scanned_folder_inside_the_designs_folder_keeps_its_own_names(userdir):
    """``./antenna_designs`` is scanned on its own; when it sits inside the
    designs folder it is not also read as a subfolder of it."""
    _write(userdir / "antenna_designs" / "x.py")
    assert [name for name, _ in core.iter_design_files()] == ["x"]
    assert core._user_name(userdir / "antenna_designs" / "x.py") == "x"
