"""User-authored design discovery, live reload, error surfacing, scaffolding.

See web/user_designs.py — local users drop a Builder file in their user dir
and it registers under `user.<filename>` with no restart.
"""

from pathlib import Path

import pytest

import antennaknobs.web.examples  # noqa: F401 — bootstraps the adapter + REGISTRY
from antennaknobs.web import user_designs
from antennaknobs.web.examples import REGISTRY

VALID = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    label = "Test dipole"
    default_params = MappingProxyType({"freq": 14.0, "half_length": 5.0})

    def build_wires(self):
        h = self.half_length
        n = self.nominal_nsegs
        return [
            ((0.0, -h, 0.0), (0.0, -0.01, 0.0), n, None),
            ((0.0, 0.01, 0.0), (0.0, h, 0.0), n, None),
            ((0.0, -0.01, 0.0), (0.0, 0.01, 0.0), 1, 1 + 0j),
        ]
"""

BROKEN_BUILD = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0})

    def build_wires(self):
        return undefined_name  # NameError when geometry is built
"""

NO_BUILDER = "x = 1\n"


@pytest.fixture
def userdir(tmp_path, monkeypatch):
    """A clean temp user-design dir; strips any user.* from the shared
    REGISTRY before and after so tests don't leak into each other."""
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))

    def _clear():
        for k in [k for k in REGISTRY if k.startswith("user.")]:
            del REGISTRY[k]

    _clear()
    yield tmp_path
    _clear()


def test_valid_design_registers(userdir):
    (userdir / "my_dipole.py").write_text(VALID)
    errors = user_designs.refresh()
    assert errors == []
    assert "user.my_dipole" in REGISTRY
    assert REGISTRY["user.my_dipole"].name == "user.my_dipole"


def test_broken_geometry_loads_but_fails_on_solve(userdir):
    # build_wires is no longer run at registration (lazy: the builder only runs
    # when the design is selected/solved), so a geometry error does NOT block
    # loading — the design registers, and the error surfaces on solve instead
    # of in the load panel. Load-level errors (syntax/import/no-Builder) are
    # still caught at registration; see the tests below.
    (userdir / "oops.py").write_text(BROKEN_BUILD)
    errors = user_designs.refresh()
    assert errors == []
    assert "user.oops" in REGISTRY
    with pytest.raises(NameError):
        REGISTRY["user.oops"].momwire_solve({})


def test_format_solve_error_points_at_user_file(userdir):
    # The on-solve error banner (server.py) formats exceptions via this helper;
    # it should name the user's file + line, not framework internals.
    (userdir / "boom.py").write_text(BROKEN_BUILD)
    user_designs.refresh()
    with pytest.raises(NameError) as ei:
        REGISTRY["user.boom"].momwire_solve({})
    msg = user_designs.format_solve_error(ei.value)
    assert "NameError" in msg
    assert "boom.py" in msg and "line" in msg


def test_missing_builder_reports_error(userdir):
    (userdir / "nobuilder.py").write_text(NO_BUILDER)
    errors = user_designs.refresh()
    assert "user.nobuilder" not in REGISTRY
    assert any("Builder" in e["message"] for e in errors)


def test_one_bad_design_does_not_block_a_good_one(userdir):
    # A load-level failure (no Builder) is isolated to its own file.
    (userdir / "good.py").write_text(VALID)
    (userdir / "bad.py").write_text(NO_BUILDER)
    errors = user_designs.refresh()
    assert "user.good" in REGISTRY
    assert {e["name"] for e in errors} == {"user.bad"}


def test_reload_picks_up_edits(userdir):
    f = userdir / "d.py"
    f.write_text(VALID)
    assert user_designs.refresh() == []
    assert "user.d" in REGISTRY

    f.write_text(NO_BUILDER)  # break it at load level (no Builder)
    errors = user_designs.refresh()
    assert "user.d" not in REGISTRY
    assert errors and errors[0]["name"] == "user.d"

    f.write_text(VALID)  # fix it
    assert user_designs.refresh() == []
    assert "user.d" in REGISTRY


def test_template_file_is_skipped(userdir):
    (userdir / "TEMPLATE.py").write_text(VALID)
    user_designs.refresh()
    assert "user.TEMPLATE" not in REGISTRY


# --- builtin designs are copy-portable (issue #341) -----------------------
#
# The advertised authoring workflow is `cp` a builtin design into the user
# dir and start editing. That only works if design files use absolute
# imports (relative imports break under the path-based loader, which has no
# package context). Representative sample: one plain design, one carrying a
# Network, one deriving from another design.

PORTABLE_BUILTINS = [
    "dipoles/invvee.py",  # plain AntennaBuilder
    "dipoles/short_dipole_loaded.py",  # has a Network (Driven + Load)
    "dipoles/pota_invvee.py",  # derives from another design's Builder
]


@pytest.mark.parametrize("relpath", PORTABLE_BUILTINS)
def test_builtin_design_copies_verbatim_to_user_dir(relpath, tmp_path, monkeypatch):
    import shutil

    from antennaknobs import AntennaBuilder
    from antennaknobs import designs as builtin_designs
    from antennaknobs import user_designs as core_user_designs

    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    src = Path(builtin_designs.__file__).parent / relpath
    stem = f"my_{src.stem}"
    shutil.copy(src, tmp_path / f"{stem}.py")

    cls = core_user_designs.resolve_user_design(stem)
    assert cls is not None and issubclass(cls, AntennaBuilder)
    assert cls().build_wires()  # defaults produce geometry


def test_scaffold_creates_assets(tmp_path, monkeypatch):
    target = tmp_path / "designs"
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(target))
    user_designs.ensure_scaffold()
    assert (target / "TEMPLATE.py").is_file()
    assert (target / "CLAUDE.md").is_file()

    # The shipped template must itself be a loadable design (copied under a
    # non-TEMPLATE name, since TEMPLATE.py is skipped by discovery).
    (target / "example_from_template.py").write_text(
        (target / "TEMPLATE.py").read_text()
    )
    errors = user_designs.refresh()
    try:
        assert "user.example_from_template" in REGISTRY
        assert not any(e["name"] == "user.example_from_template" for e in errors)
    finally:
        for k in [k for k in REGISTRY if k.startswith("user.")]:
            del REGISTRY[k]
