"""QRZ 1003328 #170 (AC6LA): the solver slot's "wire radius (m)" field reached
momwire only. NEC-5 wrote ``GW ... 5.0E-04`` while the slot said 0.001, because
the NEC-5, NEC-2 and PyNEC engines took no radius at all.

They now take ``wire_radius`` with MomwireEngine's precedence: a wire's own
spec beats everything; else a radius other than 0.0005 (the field's untouched
"auto" value) is the default; else the design's ``build_wire_material()``
radius; else 0.0005. The material cards follow the radius the GW card carries,
so a jacket's equivalent radius and its LD 5 rescale are computed there.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest
from fastapi.testclient import TestClient

from antennaknobs import AntennaBuilder
from antennaknobs.designs.dipoles.invvee import Builder as InvVee
from antennaknobs.engines import NEC5Engine, PyNECEngine
from antennaknobs.engines._nec_wire import (
    effective_default_radius,
    nec_wire_material,
)
from antennaknobs.network import WIRES, Wire, WireSpec
from antennaknobs.nec_export import export_nec
from antennaknobs.simnec_export import export_ssn

OVERRIDE = 0.001


class Mixed(AntennaBuilder):
    """One wire with its own spec, one without."""

    default_params = MappingProxyType({"freq": 300.0})

    def build_wires(self):
        return [
            Wire(
                (0.0, -0.24, 0.0),
                (0.0, 0.0, 0.0),
                7,
                spec=WireSpec(radius=2e-4, conductivity=3.5e7),
                ex=1.0,
            ),
            Wire((0.0, 0.0, 0.0), (0.0, 0.24, 0.0), 7),
        ]


def _jacketed():
    b = InvVee()
    b.wire_type = "18-awg-pvc"
    return b


def _nec5(builder, **kw):
    return NEC5Engine(builder, ground=None, require_exe=False, **kw).deck(
        [builder.freq]
    )


def _nec2(builder, **kw):
    return export_nec(builder, ground=None, **kw)


def _gw_radii(deck):
    return [float(ln.split()[-1]) for ln in deck.splitlines() if ln.startswith("GW ")]


def _ld(deck):
    return [ln for ln in deck.splitlines() if ln.startswith("LD ")]


# ---------------------------------------------------------------------------
# the precedence itself
# ---------------------------------------------------------------------------


def test_precedence_matches_momwire():
    spec = WireSpec(radius=3e-4)
    assert effective_default_radius(None, None) == 0.0005
    assert effective_default_radius(0.0005, None) == 0.0005
    assert effective_default_radius(0.0005, spec) == 3e-4  # 0.0005 is "auto"
    assert effective_default_radius(None, spec) == 3e-4
    assert effective_default_radius(OVERRIDE, spec) == OVERRIDE
    assert effective_default_radius(OVERRIDE, None) == OVERRIDE


# ---------------------------------------------------------------------------
# (1) the auto value leaves every deck byte for byte
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("make", [InvVee, Mixed, _jacketed])
@pytest.mark.parametrize("write", [_nec5, _nec2])
def test_auto_radius_is_byte_identical(make, write):
    base = write(make())
    assert write(make(), wire_radius=0.0005) == base
    assert write(make(), wire_radius=None) == base


@pytest.mark.parametrize("make", [InvVee, _jacketed])
def test_auto_radius_ssn_is_byte_identical(make):
    base = export_ssn(make(), ground=None)
    assert export_ssn(make(), ground=None, wire_radius=0.0005) == base


# ---------------------------------------------------------------------------
# (2) a plain design takes the override on every GW card
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("write", [_nec5, _nec2])
def test_plain_design_takes_the_override(write):
    assert set(_gw_radii(write(InvVee()))) == {0.0005}
    assert set(_gw_radii(write(InvVee(), wire_radius=OVERRIDE))) == {OVERRIDE}


def test_nec5_writes_1e_minus_3():
    gws = [ln for ln in _nec5(InvVee(), wire_radius=OVERRIDE).splitlines()]
    gws = [ln for ln in gws if ln.startswith("GW ")]
    assert gws and all(ln.endswith(" 1.000000E-03") for ln in gws), gws


def test_ssn_takes_the_override():
    s = export_ssn(InvVee(), ground=None, wire_radius=OVERRIDE)
    gws = [ln for ln in s.splitlines() if ln.startswith("GW ")]
    assert gws and all(float(ln.split()[-1]) == OVERRIDE for ln in gws), gws


def test_pynec_engine_radius():
    eng = PyNECEngine(InvVee(), ground=None, wire_radius=OVERRIDE)
    assert {eng._gw_radius_for(t) for t in eng.tups} == {OVERRIDE}


# ---------------------------------------------------------------------------
# (3) a wire's own spec keeps its radius
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("write", [_nec5, _nec2])
def test_per_wire_spec_keeps_its_radius(write):
    assert _gw_radii(write(Mixed())) == [2e-4, 0.0005]
    assert _gw_radii(write(Mixed(), wire_radius=OVERRIDE)) == [2e-4, OVERRIDE]
    # The spec'd wire's LD card is its own and does not move.
    assert _ld(write(Mixed(), wire_radius=OVERRIDE)) == _ld(write(Mixed()))


# ---------------------------------------------------------------------------
# (4) a design-level material: the override wins, the cards follow it
# ---------------------------------------------------------------------------


def _floats(line):
    out = []
    for tok in line.split()[1:]:
        try:
            out.append(float(tok))
        except ValueError:
            pass
    return out


@pytest.mark.parametrize("write", [_nec5, _nec2])
def test_design_material_cards_follow_the_override(write):
    spec = WIRES["18-awg-pvc"]
    r = 0.0007  # inside the 1.05 mm jacket
    assert spec.radius < r < spec.insulation_radius
    base = write(_jacketed())
    moved = write(_jacketed(), wire_radius=r)

    want_base = nec_wire_material(spec.radius, spec.conductivity, spec)
    want = nec_wire_material(r, spec.conductivity, spec)
    assert _gw_radii(base) == [pytest.approx(want_base.radius, rel=1e-6)] * 3
    assert _gw_radii(moved) == [pytest.approx(want.radius, rel=1e-6)] * 3

    ld5, ld2 = _ld(moved)
    assert ld5.startswith("LD 5 0 0 0 ") and ld2.startswith("LD 2 0 0 0 ")
    assert _floats(ld5)[4] == pytest.approx(want.conductivity, rel=1e-6)
    assert _floats(ld2)[5] == pytest.approx(want.inductance, rel=1e-6)
    # And both cards moved off the spec-radius deck's values.
    b5, b2 = _ld(base)
    assert _floats(b5)[4] == pytest.approx(want_base.conductivity, rel=1e-6)
    assert _floats(b2)[5] == pytest.approx(want_base.inductance, rel=1e-6)
    assert ld5 != b5 and ld2 != b2

    # Nothing but GW and LD lines differ.
    diff = [
        (a, b)
        for a, b in zip(base.splitlines(), moved.splitlines(), strict=True)
        if a != b
    ]
    assert diff and all(a.split()[0] in ("GW", "LD") for a, _ in diff), diff


def test_ssn_insulation_thickness_follows_the_override():
    spec = WIRES["18-awg-pvc"]
    s = export_ssn(_jacketed(), ground=None, wire_radius=0.0007)
    (line,) = [ln for ln in s.splitlines() if "NECOptions.Insulation(" in ln]
    thick = float(line.split("(")[1].split(",")[1])
    assert thick == pytest.approx(spec.insulation_radius - 0.0007, rel=1e-9)


# ---------------------------------------------------------------------------
# (5) through the adapter: the request's radius reaches the decks
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    import antennaknobs.web.server as _server

    return TestClient(_server.app)


@pytest.mark.parametrize("dialect", ["nec5", "nec2"])
def test_download_carries_the_slot_radius(client, dialect):
    req = {"geometry": "dipoles.invvee", "dialect": dialect}
    auto = client.post("/export_nec", json=req)
    explicit_auto = client.post("/export_nec", json={**req, "wire_radius": 0.0005})
    moved = client.post("/export_nec", json={**req, "wire_radius": OVERRIDE})
    assert auto.status_code == explicit_auto.status_code == moved.status_code == 200
    # The #1389 byte-equality holds at the untouched field.
    assert explicit_auto.text == auto.text
    assert set(_gw_radii(auto.text)) == {0.0005}
    assert set(_gw_radii(moved.text)) == {OVERRIDE}
    if dialect == "nec5":
        assert "CM wire radius 0.001 m (the solver slot's override)" in moved.text
        assert "slot's override" not in auto.text


def _adapter_builder():
    import antennaknobs.web.examples  # noqa: F401  (before the adapter)
    from antennaknobs.web import adapter

    b = adapter._build_builder(InvVee, {"geometry": "dipoles.invvee"})
    return adapter, b


def test_nec5_engine_factory_takes_the_slot_radius(monkeypatch):
    import antennaknobs.engines.nec5 as nec5

    monkeypatch.setattr(nec5, "find_nec5", lambda *_a, **_k: "/bin/true")
    adapter, b = _adapter_builder()
    eng = adapter._make_nec5_engine({"wire_radius": OVERRIDE}, b)
    assert set(_gw_radii(eng.deck([b.freq]))) == {OVERRIDE}
    eng = adapter._make_nec5_engine({}, b)
    assert set(_gw_radii(eng.deck([b.freq]))) == {0.0005}


def test_nec2_engine_factory_takes_the_slot_radius(monkeypatch):
    import antennaknobs.engines.nec2 as nec2

    monkeypatch.setattr(nec2, "find_nec2", lambda *_a, **_k: "/bin/true")
    adapter, b = _adapter_builder()
    eng = adapter._make_nec2_engine({"wire_radius": OVERRIDE}, b)
    assert set(_gw_radii(eng.deck(b.freq))) == {OVERRIDE}


def test_pynec_engine_factory_takes_the_slot_radius():
    adapter, b = _adapter_builder()
    eng = adapter._make_pynec_engine({"wire_radius": OVERRIDE}, b)
    assert {eng._gw_radius_for(t) for t in eng.tups} == {OVERRIDE}


def test_an_override_that_swallows_the_jacket_is_refused_as_momwire_refuses_it():
    """18-awg-pvc's jacket is 1.05 mm; a 1.2 mm override leaves no jacket.
    momwire refuses by name; every NEC writer now says the same sentence
    rather than writing a GW radius smaller than the conductor."""
    b = InvVee()
    b.wire_type = "18-awg-pvc"
    match = (
        r"insulation_radius \(0\.00105\) must exceed the conductor radius \(0\.0012\)"
    )
    with pytest.raises(ValueError, match=match):
        export_nec(b, ground="free", wire_radius=0.0012)
    with pytest.raises(ValueError, match=match):
        NEC5Engine(b, ground="free", require_exe=False, wire_radius=0.0012).deck()
