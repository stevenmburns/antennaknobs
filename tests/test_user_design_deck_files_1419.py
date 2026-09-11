"""Issue #1419: a bare ``.nec`` / ``.ssn`` in the user-designs folder is a
design — listed as ``user.<stem>``, loaded through the CLI's pure-data
``@file`` loader, never trust-gated — and a ``.py`` stub beside a deck of
the same stem is the one that wins."""

import pytest

import antennaknobs.web.examples  # noqa: F401 — bootstraps the adapter + REGISTRY
from antennaknobs import user_designs
from antennaknobs.builder import AntennaBuilder
from antennaknobs.design_trust import DesignNotTrustedError
from antennaknobs.web import user_designs as web_user_designs
from antennaknobs.web.examples import REGISTRY

DECK = """CM 20 m dipole, 4nec2 style
CE
SY len=10.1 'half-length in metres
SY h=10
SY r=1*mm
GW 1 21 -len 0 h len 0 h r
GE 0
EK
EX 0 1 11 0 1 0
FR 0 1 0 0 14.1 0
EN
"""

STUB = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    label = "the stub wins"
    default_params = MappingProxyType({"freq": 14.1})
    def build_wires(self):
        return [((-5.0, 0.0, 10.0), (5.0, 0.0, 10.0))]
"""


@pytest.fixture
def userdir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    yield tmp_path
    for key in [k for k in REGISTRY if k.startswith("user.")]:
        del REGISTRY[key]


def test_bare_deck_is_listed_and_resolves_without_trust(userdir):
    (userdir / "my_yagi.nec").write_text(DECK)
    assert [s for s, _ in user_designs.iter_design_files()] == ["my_yagi"]
    # No trust store entry, no env flag: a Python design would raise here.
    cls = user_designs.resolve_user_design("my_yagi")
    assert issubclass(cls, AntennaBuilder)
    b = cls()
    assert b.freq == pytest.approx(14.1)
    wires = b.build_wires()
    assert len(wires) == 1
    (p0, p1) = wires[0].p0, wires[0].p1
    assert p0 == pytest.approx((-10.1, 0.0, 10.0))
    assert p1 == pytest.approx((10.1, 0.0, 10.0))
    assert wires[0].spec.radius == pytest.approx(1e-3)


def test_python_design_still_needs_trust_but_deck_does_not(userdir):
    (userdir / "stub_only.py").write_text(STUB)
    (userdir / "deck_only.nec").write_text(DECK)
    with pytest.raises(DesignNotTrustedError):
        user_designs.resolve_user_design("stub_only")
    assert user_designs.resolve_user_design("deck_only") is not None


def test_stub_beside_its_deck_wins_and_is_listed_once(userdir):
    (userdir / "my_yagi.nec").write_text(DECK)
    (userdir / "my_yagi.py").write_text(STUB)
    files = list(user_designs.iter_design_files())
    assert [s for s, _ in files] == ["my_yagi"]
    assert files[0][1].suffix == ".py"


def test_private_and_upper_case_suffix(userdir):
    (userdir / "_scratch.nec").write_text(DECK)
    (userdir / "SHOUT.NEC").write_text(DECK)
    assert [s for s, _ in user_designs.iter_design_files()] == ["SHOUT"]


def test_web_refresh_registers_a_bare_deck_with_no_error(userdir):
    (userdir / "my_yagi.nec").write_text(DECK)
    errors = web_user_designs.refresh()
    assert errors == []
    assert "user.my_yagi" in REGISTRY


def test_web_refresh_reports_a_broken_deck_as_an_error_not_a_crash(userdir):
    (userdir / "bad.nec").write_text("GW 1 21 not a number\nEN\n")
    errors = web_user_designs.refresh()
    assert len(errors) == 1
    assert errors[0]["name"] == "user.bad"
    assert errors[0]["trust_required"] is False
    assert "user.bad" not in REGISTRY
