"""A jacket pair's LD 5 is σ′, and re-opening the deck keeps it σ′ (AK#2197).

AK's writers spell an insulated wire as the a′ + L′ pair: the GW card at the
equivalent radius a′, an LD 2 carrying L′, and an LD 5 carrying
σ′ = σ·(a/a′)² (`engines._nec_wire.nec_wire_material`, AK#1523). The import
inverted the radius back to a (AK#1591) but kept σ′ as the metal's σ, so any
writer scaled it again. On a jacketed inverted L over soil, the re-opened
deck solved 7-8 % from the same deck on the NEC-5 binary.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import make_engine_factory
from antennaknobs.nec5_export import export_nec5
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Driven, Network, PortOnWire, Wire
from antennaknobs.wire_catalog import WireSpec

FREQ = 14.0
JACKET = WireSpec(
    radius=1e-3, conductivity=5.8e7, insulation_radius=1.5e-3, insulation_eps_r=3.0
)


class _JacketedDipole(AntennaBuilder):
    default_params = MappingProxyType({"freq": FREQ, "design_freq": FREQ})

    def build_wires(self):
        return [
            Wire((0, -5.1, 10), (0, -0.05, 10), 20, spec=JACKET),
            Wire((0, -0.05, 10), (0, 0.05, 10), 1, name="feed", spec=JACKET),
            Wire((0, 0.05, 10), (0, 5.1, 10), 20, spec=JACKET),
        ]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed")},
            branches=[],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )


def _deck(builder) -> str:
    return export_nec5(builder, ground=None, design="t", rung="t", ground_name="free")


def _ld5(deck: str) -> list[str]:
    return [ln for ln in deck.splitlines() if ln.startswith("LD 5")]


def _reopened(deck: str):
    d = parse_nec(deck, network=True)

    class Reopened(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ})

        def build_wires(self):
            return d.wire_tuples(specs=True)

        def build_network(self):
            return d.network()

    return Reopened()


def test_the_jacketed_deck_round_trips_its_ld5():
    deck = _deck(_JacketedDipole())
    again = _deck(_reopened(deck))
    assert _ld5(deck)
    assert _ld5(again) == _ld5(deck)


def test_the_reopened_deck_solves_to_the_design_s_own_z():
    razor = make_engine_factory("momwire:razor-2p", None)
    native = complex(razor(_JacketedDipole()).impedance()[0])
    reopened = complex(razor(_reopened(_deck(_JacketedDipole()))).impedance()[0])
    assert reopened == pytest.approx(native, rel=1e-6)
