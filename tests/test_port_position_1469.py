"""AK#1469 slice 2, part A1: a port can name its wire and a position on it.

momwire#1059 gave `PortOnWire` a `wire` (the geometry wire, when it is not the
port's own name) and an `at` (an arclength fraction along that wire). These
gates cover the layers that name ports before any engine sees them: module
namespacing, and the named-wire validation every engine runs.
"""

import pytest

from antennaknobs import Cell, Module, ModuleInstance, expand_modules
from antennaknobs.network import (
    Driven,
    Load,
    Network,
    PortAtEnd,
    PortOnWire,
    PortOnWireFloating,
    Wire,
)
from antennaknobs.wire_catalog import (
    port_at,
    port_wire,
    validate_named_wires_referenced,
)

needs_position = pytest.mark.skipif(
    not hasattr(PortOnWire("x"), "at"),
    reason="the installed momwire's PortOnWire has no wire/at (momwire#1059)",
)


def _cell():
    return Cell(feeds=("w",), wires=[Wire((0, -1, 10), (0, 1, 10), n_seg=11, name="w")])


def _net(*ports, branches=()):
    return Network(
        ports={p.name: p for p in ports},
        branches=list(branches),
        sources=[Driven(port=ports[0].name)],
    )


def test_a_plain_port_reads_the_old_way():
    p = PortOnWire("feed")
    assert port_wire(p) == "feed" and port_at(p) is None


# ---------------------------------------------------------------------------
# module namespacing
# ---------------------------------------------------------------------------


@needs_position
def test_namespacing_keeps_the_wire_and_the_position():
    """It used to rebuild the port from its name and `distributed` alone,
    silently dropping both new fields."""
    mod = Module(
        cell=_cell(),
        ports={
            "feed": PortOnWire("feed", wire="w", at=0.5),
            "load": PortOnWire("load", wire="w", at=0.25),
        },
        branches=(Load(port="load", r=50.0),),
    )
    a = expand_modules([ModuleInstance("e0", mod)])
    assert a.ports["e0.feed"] == PortOnWire("e0.feed", wire="e0.w", at=0.5)
    assert a.ports["e0.load"] == PortOnWire("e0.load", wire="e0.w", at=0.25)
    assert {w.name for w in a.wires} - {None} == {"e0.w"}


@needs_position
def test_namespacing_keeps_a_floating_port_floating():
    mod = Module(
        cell=_cell(), ports={"bal": PortOnWireFloating("bal", wire="w", at=0.4)}
    )
    p = expand_modules([ModuleInstance("e0", mod)]).ports["e0.bal"]
    assert type(p) is PortOnWireFloating
    assert (p.wire, p.at) == ("e0.w", 0.4)


def test_a_plain_port_still_namespaces_as_before():
    cell = Cell(
        feeds=("feed",), wires=[Wire((0, -1, 10), (0, 1, 10), n_seg=11, name="feed")]
    )
    a = expand_modules(
        [ModuleInstance("e0", Module(cell=cell, ports={"feed": PortOnWire("feed")}))]
    )
    assert a.ports["e0.feed"] == PortOnWire("e0.feed")


@needs_position
def test_a_module_port_must_sit_on_a_cell_feed():
    with pytest.raises(ValueError, match="sits on wire 'x'"):
        Module(cell=_cell(), ports={"feed": PortOnWire("feed", wire="x")})


def test_a_plain_module_port_is_still_named_after_its_feed():
    with pytest.raises(ValueError, match="names no cell feed"):
        Module(cell=_cell(), ports={"feed": PortOnWire("feed")})


# ---------------------------------------------------------------------------
# the named-wire validation
# ---------------------------------------------------------------------------


@needs_position
def test_two_ports_on_one_wire_are_accepted():
    validate_named_wires_referenced(
        ["w"],
        _net(
            PortOnWire("feed", wire="w"),
            PortOnWire("load", wire="w", at=0.25),
            branches=[Load(port="load", r=50.0)],
        ),
    )


@needs_position
def test_a_wire_named_only_through_a_ports_wire_is_not_orphaned():
    validate_named_wires_referenced(
        ["w", None], _net(PortOnWire("feed", wire="w", at=0.3))
    )


def test_an_unreferenced_named_wire_is_still_orphaned():
    with pytest.raises(ValueError, match="issue #578"):
        validate_named_wires_referenced(["w", "stray"], _net(PortOnWire("w")))


@needs_position
def test_a_distributed_port_cannot_share_its_wire():
    with pytest.raises(ValueError, match="distributed port 'feed'"):
        validate_named_wires_referenced(
            ["w"],
            _net(
                PortOnWire("feed", wire="w", distributed=True),
                PortOnWire("load", wire="w", at=0.25),
                branches=[Load(port="load", r=50.0)],
            ),
        )


@needs_position
@pytest.mark.parametrize(("at_a", "at_b"), [(None, 0.5), (0.25, 0.25)])
def test_two_ports_at_one_point_are_refused(at_a, at_b):
    with pytest.raises(ValueError, match="same point"):
        validate_named_wires_referenced(
            ["w"],
            _net(
                PortOnWire("feed", wire="w", at=at_a),
                PortOnWire("load", wire="w", at=at_b),
                branches=[Load(port="load", r=50.0)],
            ),
        )


@needs_position
def test_a_gap_port_and_an_end_port_still_cannot_share_a_wire():
    net = Network(
        ports={"feed": PortOnWire("feed", wire="w"), "gnd": PortAtEnd("w")},
        sources=[Driven(port="feed")],
    )
    with pytest.raises(ValueError, match="both a PortOnWire and a"):
        validate_named_wires_referenced(["w"], net)
