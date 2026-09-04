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

# A user's scratch program living beside their designs — the case that used to
# fill the UI banner (a moxon derivation, not a design).
SCRATCH = """
import math

def moxon_dims(freq_mhz):
    lam = 299.792458 / freq_mhz
    return {"A": 0.256 * lam, "B": 0.043 * lam}

if __name__ == "__main__":
    print(moxon_dims(14.1))
"""

# Defines a Builder that blows up when the registry constructs it. THIS is a
# broken design and must keep the banner.
BUILDER_RAISES = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0})

    def __init__(self, *a, **k):
        raise RuntimeError("boom while constructing")
"""

# Fails before the Builder check can run, so we cannot know whether it had one.
IMPORT_RAISES = "raise RuntimeError('boom at import')\n"


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


def test_a_module_without_a_builder_is_skipped_silently(userdir):
    """The designs folder is a plain directory and users keep other work in
    it. A .py file with no ``Builder`` is not a broken design, it is not a
    design — so it is not registered AND not reported.

    This inverts the old behaviour deliberately: it used to raise "no
    `Builder` class found" into the UI's red banner, which trained the eye to
    ignore a banner that also carries real breakage."""
    (userdir / "nobuilder.py").write_text(NO_BUILDER)
    (userdir / "moxon_derivation.py").write_text(SCRATCH)
    errors = user_designs.refresh()
    assert "user.nobuilder" not in REGISTRY
    assert "user.moxon_derivation" not in REGISTRY
    assert errors == []


def test_a_builder_that_fails_to_construct_still_reports(userdir):
    """The other half, and the reason the skip is keyed on a dedicated
    exception rather than on AttributeError: a file that DOES define a
    Builder and then fails is a real broken design and keeps the banner."""
    (userdir / "boom.py").write_text(BUILDER_RAISES)
    errors = user_designs.refresh()
    assert "user.boom" not in REGISTRY
    assert [e["name"] for e in errors] == ["user.boom"]
    assert "boom while constructing" in errors[0]["message"]


def test_a_file_that_fails_at_import_still_reports(userdir):
    """It never reaches the ``Builder`` check, so we cannot know whether it
    had one. Reported rather than skipped — the conservative direction, and
    the one that cannot hide a broken design."""
    (userdir / "explodes.py").write_text(IMPORT_RAISES)
    errors = user_designs.refresh()
    assert [e["name"] for e in errors] == ["user.explodes"]
    assert "boom at import" in errors[0]["message"]


def test_one_bad_design_does_not_block_a_good_one(userdir):
    """A load-level failure is isolated to its own file — and a scratch
    program in the same folder disturbs neither. `bad.py` defines a Builder
    that raises; NO_BUILDER would no longer be an error at all."""
    (userdir / "good.py").write_text(VALID)
    (userdir / "bad.py").write_text(BUILDER_RAISES)
    (userdir / "scratch.py").write_text(SCRATCH)
    errors = user_designs.refresh()
    assert "user.good" in REGISTRY
    assert "user.scratch" not in REGISTRY
    assert {e["name"] for e in errors} == {"user.bad"}


def test_reload_picks_up_edits(userdir):
    f = userdir / "d.py"
    f.write_text(VALID)
    assert user_designs.refresh() == []
    assert "user.d" in REGISTRY

    f.write_text(BUILDER_RAISES)  # break it at load level (Builder raises)
    errors = user_designs.refresh()
    assert "user.d" not in REGISTRY
    assert errors and errors[0]["name"] == "user.d"

    # Edited down to something that is no longer a design at all: it leaves
    # the registry, and it leaves QUIETLY — the same file can move between
    # "broken design" and "not a design", and only the first is the UI's
    # business.
    f.write_text(NO_BUILDER)
    assert user_designs.refresh() == []
    assert "user.d" not in REGISTRY

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
