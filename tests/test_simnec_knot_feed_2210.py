"""A feed or load at a junction knot exports as SimNEC writes one (AK#2210).

SimNEC places a source or a load at a knot with ``NECSource(..., $GW_<tag>,
0 | 100)``: a percentage of one wire's length, at its end. The export used to
build its card block through the NEC-2 engine, which has no source at a knot,
and refused with that engine's advice (run it on NEC-5) even for a user already
on NEC-5. Every fixture is synthetic.
"""

from __future__ import annotations

import re
from html import unescape
from types import MappingProxyType

import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import make_engine_factory
from antennaknobs.network import (
    TL,
    Driven,
    Load,
    Network,
    PortAtEnd,
    PortAtVertex,
    PortVirtual,
    Wire,
)
from antennaknobs.simnec_export import SsnUnsupported, export_ssn
from antennaknobs.simnec_import import parse_ssn


class _Apex(AntennaBuilder):
    """A dipole fed at the knot between its two arms, with a tail wire whose
    knot with the right arm carries a parallel RLC."""

    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})
    # A re-imported .ssn is a deck design, which solves at NEC's c (AK#1685);
    # the same c here makes the round trip compare like with like.
    c_light_mhz_m = 299.8
    end = "p1"

    def build_wires(self):
        left = ((0.0, -5.0, 10.0), (0.0, 0.0, 10.0))
        if self.end == "p0":
            left = left[::-1]
        return [
            Wire(*left, 11, name="feed"),
            Wire((0.0, 0.0, 10.0), (0.0, 5.0, 10.0), 11, name="arm"),
            Wire((0.0, 5.0, 10.0), (0.0, 6.0, 10.0), 3),
        ]

    def build_network(self):
        return Network(
            ports={
                "feed": PortAtVertex("feed", end=self.end),
                "ld": PortAtVertex("arm", end="p1"),
            },
            branches=[
                Load("ld", r=4150.0, l=26.3e-6, c=4.91e-12, parallel=True),
            ],
            sources=[Driven(port="feed")],
        )


class _ApexP0(_Apex):
    end = "p0"


def _script(ssn: str) -> str:
    return unescape(re.search(r"<n>equ</n>\s*<v>(.*?)</v>", ssn, re.S).group(1))


def _z(builder) -> complex:
    return complex(
        make_engine_factory("momwire:razor-2p", None)(builder).impedance()[0]
    )


@pytest.mark.parametrize(("cls", "pct"), [(_Apex, "100"), (_ApexP0, "0")])
def test_a_knot_feed_is_simnecs_own_necsource_and_no_ex(cls, pct):
    script = _script(export_ssn(cls(), freq_mhz=14.0, ground=None))
    assert f"$feed = NECSource({{w2, gnd}}, $GW_1, {pct});" in script
    assert not [ln for ln in script.splitlines() if ln.startswith("EX")]
    assert "if (NECOptions.Engine == 2)" in script
    assert re.search(
        r"RK1 \(4150 \|\|\| L\(2\.63e-05\) \|\|\| C\(4\.91e-12\)\) kn1a kn1b;\s+"
        r"dcl KnotLoad1 = NECSource\(\{kn1a,kn1b\}, \$GW_2, 100\);",
        script,
    )


@pytest.mark.parametrize("cls", [_Apex, _ApexP0])
def test_the_export_reimports_to_the_same_ports_and_impedance(cls, tmp_path):
    ssn = export_ssn(cls(), freq_mhz=14.0, ground=None)
    back = parse_ssn(ssn, name="t.ssn", network=True)
    net = back.network()
    feeds = [p for p in net.ports.values() if isinstance(p, PortAtVertex)]
    assert len(feeds) == 2
    path = tmp_path / "back.ssn"
    path.write_text(ssn)
    from antennaknobs.file_designs import builder_from_file

    assert _z(builder_from_file(str(path))()) == pytest.approx(_z(cls()), rel=1e-9)


def test_a_junction_node_port_refuses_in_the_exports_own_words():
    class _Node(_Apex):
        def build_network(self):
            return Network(
                ports={"feed": PortAtEnd("feed", end="p1")},
                branches=[],
                sources=[Driven(port="feed")],
            )

    with pytest.raises(SsnUnsupported, match="junction-node port") as e:
        export_ssn(_Node(), freq_mhz=14.0, ground=None)
    assert "engine" not in str(e.value)


def test_a_station_chain_on_a_knot_feed_refuses_by_name():
    class _Station(_Apex):
        def build_network(self):
            return Network(
                ports={"feed": PortAtVertex("feed"), "rig": PortVirtual("rig")},
                branches=[TL(a="rig", b="feed", z0=50.0, length=10.0)],
                sources=[Driven(port="rig")],
            )

    with pytest.raises(SsnUnsupported, match="knot"):
        export_ssn(_Station(), freq_mhz=14.0, ground=None)
