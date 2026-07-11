import pytest

from antennaknobs.designs.dipoles.invvee import Builder

from types import MappingProxyType

from antennaknobs.sweep import resolve_range

from antennaknobs.cli import resolve_class
from types import ModuleType


def test_resolve_class():
    def check(res):
        return res is not None and not isinstance(res, ModuleType)

    assert check(resolve_class("beams.moxon.Builder"))
    assert check(resolve_class("beams.moxon.Builder"))

    assert not check(resolve_class("beams.moxon.Builder0"))
    assert check(resolve_class("freq_based_dipole.Builder"))
    assert check(resolve_class("freq_based_dipole.FancyBuilder"))
    assert not check(resolve_class("freq_based_dipole.Builder0"))
    assert check(resolve_class("beams.moxon"))
    assert check(resolve_class("freq_based_dipole"))
    assert not check(resolve_class("fail"))

    # A bare, unqualified basename still resolves via the family-subpackage
    # fallback (interactive convenience). Integration tests use the explicit
    # "family.name" form; this keeps the fallback itself covered.
    assert check(resolve_class("hexbeam"))

    assert check(resolve_class("subdir.moxon.Builder"))

    assert check(resolve_class("dipoles.invvee"))


def test_resolve_class_ambiguous_bare_name(monkeypatch):
    """A bare name that resolves under more than one family must error with
    the candidates rather than silently picking the first."""
    import importlib
    import types as _types

    # The package re-exports a cli() function, shadowing the submodule
    # attribute — fetch the actual module object explicitly.
    cli = importlib.import_module("antennaknobs.cli")

    monkeypatch.setattr(cli, "_design_families", lambda: ["fam_a", "fam_b"])

    class _B:
        pass

    def fake_import(name):
        if name in (
            "antennaknobs.designs.fam_a.dupe",
            "antennaknobs.designs.fam_b.dupe",
        ):
            m = _types.ModuleType(name)
            m.Builder = _B
            return m
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(cli, "import_module", fake_import)

    with pytest.raises(ValueError, match="ambiguous"):
        cli.resolve_class("dupe")


def test_unit_params():
    dp = Builder(
        {
            "freq": 1,
            "design_freq": 14,
            "base": 7,
            "length_factor": 0.9,
            "angle_deg": 28.6479,
        }
    )
    assert dp.freq == 1
    assert dp.base == 7
    assert dp.length_factor == 0.9

    dp._params["freq"] = 2
    assert dp.freq == 2
    assert dp._params["freq"] == 2

    dp.freq = 3
    assert dp.freq == 3
    assert dp._params["freq"] == 3

    dp.z0 = 50
    assert dp.z0 == 50
    assert dp._params["z0"] == 50

    assert not hasattr(dp, "excitation")


def test_dict_update_options():
    p = {"a": 0, "b": 1}

    q = dict(p, **{"b": 2})
    assert p["a"] == 0 and p["b"] == 1
    assert q["a"] == 0 and q["b"] == 2

    r = dict(p, b=2)
    assert p["a"] == 0 and p["b"] == 1
    assert r["a"] == 0 and r["b"] == 2

    s = dict(p)
    s["b"] = 2
    assert p["a"] == 0 and p["b"] == 1
    assert s["a"] == 0 and s["b"] == 2

    p = MappingProxyType({"a": 0, "b": 1})

    q = dict(p, **{"b": 2})
    assert p["a"] == 0 and p["b"] == 1
    assert q["a"] == 0 and q["b"] == 2

    r = dict(p, b=2)
    assert p["a"] == 0 and p["b"] == 1
    assert r["a"] == 0 and r["b"] == 2

    s = dict(p)
    s["b"] = 2
    assert p["a"] == 0 and p["b"] == 1
    assert s["a"] == 0 and s["b"] == 2


def test_resolve_range():
    # test all eight cases of potential None arguments

    def check(res, gold):
        return all(abs(r - g) < 0.01 for r, g in zip(res, gold))

    check(
        resolve_range(default_value=100, rng=None, center=None, fraction=None),
        (80, 125),
    )
    check(
        resolve_range(default_value=100, rng=None, center=30, fraction=None), (24, 37.5)
    )
    check(
        resolve_range(default_value=100, rng=None, center=None, fraction=1.5),
        (66.667, 150),
    )
    check(resolve_range(default_value=100, rng=None, center=30, fraction=1.5), (20, 45))

    check(
        resolve_range(default_value=100, rng=(7, 11), center=None, fraction=None),
        (7, 11),
    )
    check(
        resolve_range(default_value=100, rng=(7, 11), center=30, fraction=None), (7, 11)
    )
    check(
        resolve_range(default_value=100, rng=(7, 11), center=None, fraction=1.5),
        (7, 11),
    )
    check(
        resolve_range(default_value=100, rng=(7, 11), center=30, fraction=1.5), (7, 11)
    )
