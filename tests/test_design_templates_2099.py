"""The designs folder's templates reach a new folder (AK#2099).

Cristiano (IZ4HDM) installed the 0.108.6 Windows workbench and found
CLAUDE.md alone in ~/.antennaknobs/designs: PyInstaller's collect_data_files
leaves .py files out by default, so TEMPLATE.py and TERRAIN_TEMPLATE.py never
reached the bundle, and `ensure_scaffold` skipped what was missing without a
word. The build now asks for them, the frozen selftest fails without them,
and the scaffold says when one is missing.
"""

from __future__ import annotations

from pathlib import Path

# The server first, as the app and the frozen selftest import it: importing
# user_designs alone is a circular import through the adapter.
from antennaknobs.web import server  # noqa: F401
from antennaknobs.web import user_designs

BUILD = (
    Path(__file__).resolve().parents[1] / "scripts" / "freeze_workbench" / "build.py"
)


def test_this_install_has_every_template():
    assert user_designs.missing_assets() == []


def test_the_scaffold_copies_what_it_has_and_names_what_it_lacks(
    tmp_path, monkeypatch, capsys
):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "CLAUDE.md").write_text("notes\n")
    home = tmp_path / "designs"
    monkeypatch.setattr(user_designs, "_ASSETS", assets)
    monkeypatch.setattr(user_designs, "default_user_dir", lambda: home)
    assert user_designs.missing_assets() == ["TEMPLATE.py", "TERRAIN_TEMPLATE.py"]
    user_designs.ensure_scaffold()
    assert sorted(p.name for p in home.iterdir()) == ["CLAUDE.md"]
    out = capsys.readouterr().out
    assert "TEMPLATE.py is missing" in out and "TERRAIN_TEMPLATE.py is missing" in out


def test_the_frozen_build_asks_for_the_py_templates():
    text = BUILD.read_text(encoding="utf-8")
    assert "include_py_files=True" in text
    assert "web/user_design_assets/*" in text
