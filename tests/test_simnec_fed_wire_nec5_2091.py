"""A 1-segment fed wire's NEC-5 alternative in the SimNEC export (AK#2091).

Measured in SimNEC 5.5a11 on 2026-10-28, through a shim that logged the deck
SimNEC hands its NEC-5 engine: SimNEC writes its own ``EX`` on the knot at
the feed position and evens a fed wire's count to have one (a Jam of 3 went
to 2), but a 1-segment fed wire has no interior knot, and the source landed
on its start. ``NECOptions.Engine`` read 5 on NEC-5 and 2 on NEC-2, so the
exporter follows that wire's Jam line with a NEC-5-only Jam of 2, and every
other count is the deck's. The importer reads the guarded line as the
alternative it is: a read for antennaknobs' engines keeps the NEC2 block's
count and reports nothing ignored.
"""

from __future__ import annotations

import re
from types import MappingProxyType

import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.engines.pynec import PyNECEngine
from antennaknobs.network import Driven, Network, PortOnWire, Wire
from antennaknobs.simnec_export import export_ssn
from antennaknobs.simnec_import import parse_ssn

H, ARM = 10.0, 5.0
GUARD = "if (NECOptions.Engine == 5) $GW_2.JamSegments(2);"


def _dipole(n_feed: int, gap: float = 0.1):
    """A 10 m dipole at 14.2 MHz whose centre is a short fed wire (tag 2)."""

    class CentreFed(AntennaBuilder):
        default_params = MappingProxyType({"design_freq": 14.2, "freq": 14.2})

        def build_wires(self):
            return [
                Wire((-ARM - gap / 2, 0, H), (-gap / 2, 0, H), 15),
                Wire((-gap / 2, 0, H), (gap / 2, 0, H), n_feed, name="feed"),
                Wire((gap / 2, 0, H), (ARM + gap / 2, 0, H), 15),
            ]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed")},
                branches=[],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

    return CentreFed()


def _jam_lines(ssn: str) -> list[str]:
    """Every Jam statement in the script, guarded or not, in order."""
    return re.findall(
        r"(?:if \(NECOptions\.Engine == \d\) )?\$GW_\d+\.JamSegments\(\d+\);", ssn
    )


def test_a_one_segment_fed_wire_gets_the_nec5_alternative():
    ssn = export_ssn(_dipole(1), ground=None)
    assert _jam_lines(ssn) == [
        "$GW_1.JamSegments(15);",
        "$GW_2.JamSegments(1);",
        GUARD,
        "$GW_3.JamSegments(15);",
    ]
    # The NEC2 block itself is the NEC-2 / NEC-4.2 deck, unchanged.
    assert "GW 2 1 " in ssn
    assert "EX 0 2 1 " in ssn


@pytest.mark.parametrize("n_feed", [3, 5])
def test_a_longer_fed_wire_is_left_to_simnec(n_feed):
    """SimNEC evens these itself under NEC-5 (3 went to 2), so no guard."""
    ssn = export_ssn(_dipole(n_feed), ground=None)
    assert not any(ln.startswith("if") for ln in _jam_lines(ssn))
    assert f"$GW_2.JamSegments({n_feed});" in _jam_lines(ssn)


def test_simnecs_own_mesh_writes_no_jam_and_no_guard():
    """The convergence-study shape: SimNEC meshes, and put the source on the
    centre knot in the measurement."""
    assert _jam_lines(export_ssn(_dipole(1), ground=None, seg_per_wl=41)) == []


def test_unfed_one_segment_wires_get_no_guard():
    class Unfed(AntennaBuilder):
        default_params = MappingProxyType({"design_freq": 14.2, "freq": 14.2})

        def build_wires(self):
            return [
                Wire((-ARM, 0, H), (-0.05, 0, H), 15),
                Wire((-0.05, 0, H), (0.05, 0, H), 1),
                Wire((0.05, 0, H), (ARM, 0, H), 15),
                Wire((ARM, 0, H), (ARM + 1.0, 0, H), 3, name="feed"),
            ]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed")},
                branches=[],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

    lines = _jam_lines(export_ssn(Unfed(), ground=None))
    assert "$GW_2.JamSegments(1);" in lines
    assert not any(ln.startswith("if") for ln in lines)


def test_the_importer_keeps_the_nec2_count_and_ignores_nothing():
    b = _dipole(1)
    c = parse_ssn(export_ssn(b, ground=None), name="rt.ssn", network=True)
    assert c.ignored_directives == ()
    assert [t[2] for t in c.deck.wire_tuples(specs=True)] == [15, 1, 15]

    class RoundTrip(AntennaBuilder):
        default_params = MappingProxyType({"freq": 14.2})

        def build_wires(self):
            return c.deck.wire_tuples(specs=True)

        def build_network(self):
            return c.network()

    def z(builder) -> complex:
        v = PyNECEngine(builder, ground=None).impedance()
        while isinstance(v, (list, tuple)):
            v = v[0]
        return complex(v)

    assert z(RoundTrip()) == pytest.approx(z(b), rel=1e-9)
