"""A jacketed wire laid on the ground reopens as one lying ON it (AK#2355).

AK's NEC-5 writer spells an insulated wire as the a′ + L′ pair (AK#1523):
the GW card at the equivalent radius a′, an LD 2 carrying the jacket's L′.
Reading it back recovers the conductor radius exactly, but (b, εr) only as a
family (AK#1591), and the importer reported one canonical member (εr 2). For
the catalog's #12 PVC (b 1.70 mm, εr 3.5) that member is b = 2.11 mm, so a
radial laid on the soil with its axis one jacket radius up (h = 1.70 mm)
reopened as a jacket sunk into it, and bs2 refused the deck. Every member is
the same wire electrically; the one that RESTS on the ground is the reading
of such a deck that is a wire lying on the ground, and it is what the writer
was given.
"""

from __future__ import annotations

import math
from types import MappingProxyType

import pytest
from momwire import equivalent_radius, insulation_inductance

from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import make_engine_factory
from antennaknobs.file_designs import builder_from_file
from antennaknobs.engines._nec_wire import (
    CANONICAL_INSULATION_EPS_R,
    jacket_from_equivalent_radius,
    jacket_resting_at,
    nec_wire_material,
)
from antennaknobs.nec5_export import export_nec5
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Driven, Load, Network, PortAtVertex, Wire
from antennaknobs.wire_catalog import WireSpec, wire_from_catalog

FREQ = 7.15
SOIL = ("finite", 13.0, 0.005)
RADIAL = wire_from_catalog("12-awg-pvc")
B = RADIAL.insulation_radius  # 1.70 mm: the radials' axis height, on the soil
MAST = WireSpec(radius=0.0254, conductivity=2.5e7)


def _pair(spec: WireSpec) -> tuple[float, float]:
    mat = nec_wire_material(spec.radius, spec.conductivity, spec)
    return mat.radius, mat.inductance


class _RadialVertical(AntennaBuilder):
    """A loaded 10 m vertical on four #12 PVC radials lying on the soil."""

    default_params = MappingProxyType({"freq": FREQ, "design_freq": FREQ})

    def build_wires(self):
        wires = [
            Wire((0, 0, B), (0, 0, 5.0), 10, name="mast", spec=MAST),
            Wire((0, 0, 5.0), (0, 0, 10.0), 10, spec=MAST),
        ]
        for x, y in ((8, 0), (-8, 0), (0, 8), (0, -8)):
            wires.append(Wire((0, 0, B), (x, y, B), 12, spec=RADIAL))
        return wires

    def build_network(self):
        return Network(
            # At the mast's base, on the radial hub: a knot, where the NEC-5
            # deck puts it too, so the reopened deck is the same antenna.
            ports={
                "feed": PortAtVertex(wire="mast", end="p0"),
                "coil": PortAtVertex(wire="mast", end="p1"),
            },
            # A loading coil, as the KC8QVO vertical's traps: a lumped load
            # makes it a multiport solve, the route that met the jacket.
            branches=[Load(port="coil", l=2e-6, ql=300.0)],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )


def _deck() -> str:
    return export_nec5(
        _RadialVertical(),
        ground=SOIL,
        design="t",
        rung="t",
        ground_name="finite",
        # The network route, which `antennaknobs export` takes: its reopened
        # deck reaches bs2 through the port Y-matrix, where the stand-off
        # check met the invented jacket.
        networks=True,
    )


def _reopened(deck: str):
    d = parse_nec(deck, network=True)

    class Reopened(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ})

        def build_wires(self):
            return d.wire_tuples(specs=True)

        def build_network(self):
            return d.network()

    return d, Reopened()


def test_the_resting_member_keeps_the_pair_exactly():
    a_eq, l_ins = _pair(RADIAL)
    a, b, eps_r = jacket_resting_at(a_eq, l_ins, B)
    assert math.isclose(a, RADIAL.radius, rel_tol=1e-12)
    assert b == B
    # The catalog's own jacket: the writer's (b, εr), back exactly.
    assert math.isclose(eps_r, RADIAL.insulation_eps_r, rel_tol=1e-9)
    assert math.isclose(float(equivalent_radius(a, b, eps_r)), a_eq, rel_tol=1e-12)
    assert math.isclose(float(insulation_inductance(a, b, eps_r)), l_ins, rel_tol=1e-12)


def test_no_member_rests_at_or_under_a_prime_and_none_is_needed_above_b():
    a_eq, l_ins = _pair(RADIAL)
    _a, canonical_b, _e = jacket_from_equivalent_radius(a_eq, l_ins)
    assert jacket_resting_at(a_eq, l_ins, a_eq) is None
    assert jacket_resting_at(a_eq, l_ins, 0.9 * a_eq) is None
    assert jacket_resting_at(a_eq, l_ins, canonical_b) is None
    assert jacket_resting_at(a_eq, l_ins, 10.0) is None


def test_radials_on_the_soil_reopen_resting_on_it():
    d, _ = _reopened(_deck())
    ins = dict(d.wire_insulation)
    radial_wires = [wi for wi, w in enumerate(d.wires) if w.p1[2] == w.p2[2]]
    assert len(radial_wires) == 4
    for wi in radial_wires:
        b, eps_r = ins[wi]
        assert math.isclose(b, B, rel_tol=1e-12), (wi, b)
        # εr comes back from the deck's printed a′ and L′, 7 figures each.
        assert math.isclose(eps_r, RADIAL.insulation_eps_r, rel_tol=1e-5)


def test_a_jacketed_wire_in_the_air_keeps_the_canonical_member():
    a_eq, l_ins = _pair(RADIAL)
    deck = (
        "CE\n"
        f"GW 1,11,0.,-5.,10.,0.,5.,10.,{a_eq:.17E}\n"
        "GE 1\n"
        f"LD 2,1,0,0,0.,{l_ins:.17E},0.\n"
        "GN 2,0,0,0,13.,.005\n"
        f"FR 0,1,0,0,{FREQ}\n"
        "EX 0,1,6,0,1.,0.\n"
        "XQ\nEN\n"
    )
    d = parse_nec(deck, network=True)
    ((_wi, (_b, eps_r)),) = d.wire_insulation
    assert eps_r == CANONICAL_INSULATION_EPS_R


def test_bs2_serves_the_reopened_deck_at_the_design_s_own_z(tmp_path):
    """The AK#2355 repro, through the route that opens a ``.nec`` file in the
    app and the CLI (`file_designs.builder_from_file`): bs2 refused the
    reopened deck ("A jacketed wire may REST on the soil but not sink into
    it"). Now it serves it, at the native design's impedance. The tolerance
    is the NEC-5 round trip's own: a BARE-radial copy of this design reopens
    2-3e-4 from its native Z on bs2 and razor2p alike (printed card
    precision), with no jacket involved."""
    path = tmp_path / "radials.nec"
    path.write_text(_deck())
    bs2 = make_engine_factory("momwire:bs2", SOIL)
    native = complex(bs2(_RadialVertical()).impedance()[0])
    again = complex(bs2(builder_from_file(str(path))()).impedance()[0])
    assert again == pytest.approx(native, rel=1e-3)
