"""AK#1469 slice 2, part A1: a port can name its wire and a position on it.

momwire#1059 gave `PortOnWire` a `wire` (the geometry wire, when it is not the
port's own name) and an `at` (an arclength fraction along that wire). These
gates cover the layers that name ports before any engine sees them: module
namespacing, and the named-wire validation every engine runs.
"""

from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import AntennaBuilder, Cell, Module, ModuleInstance, expand_modules
from antennaknobs.geometry import flat_wires_to_polylines
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


# ---------------------------------------------------------------------------
# the translator
# ---------------------------------------------------------------------------


def _point(t, pl, arc):
    """The 3D point `arc` metres along polyline `pl`."""
    poly = np.asarray(t["polylines"][pl], dtype=float)
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    k = min(int(np.searchsorted(cum, arc, side="right")) - 1, len(seg) - 1)
    return poly[k] + (arc - cum[k]) / seg[k] * (poly[k + 1] - poly[k])


def _chain():
    """`a` runs +x from 0 to 1; `w` is authored from x = 2 back to x = 1, so a
    walk from either end runs one of the two against its authored direction."""
    return [
        ((0.0, 0.0, 5.0), (1.0, 0.0, 5.0), 4, None, "a"),
        ((2.0, 0.0, 5.0), (1.0, 0.0, 5.0), 4, None, "w"),
    ]


def test_ports_named_after_their_wires_at_the_middle_change_nothing():
    """Bit for bit: the old one-feed-per-named-wire rule is the special case."""
    tups = _chain()
    legacy = flat_wires_to_polylines(tups)
    same = flat_wires_to_polylines(tups, gap_ports=[("a", "a", None), ("w", "w", None)])
    for key in ("feeds", "feed_names", "feed_edges", "feed_dirs"):
        assert same[key] == legacy[key], key


def test_each_gap_port_is_one_feed_at_its_own_position():
    t = flat_wires_to_polylines(
        [((0.0, 0.0, 5.0), (2.0, 0.0, 5.0), 8, None, "w")],
        gap_ports=[("feed", "w", None), ("load", "w", 0.25)],
    )
    assert t["feed_names"] == ["feed", "load"]
    where = {
        n: _point(t, pl, arc)
        for n, (pl, arc, _v) in zip(t["feed_names"], t["feeds"], strict=True)
    }
    assert where["feed"][0] == pytest.approx(1.0)
    assert where["load"][0] == pytest.approx(0.5)


def test_at_is_measured_from_the_authored_p0_whichever_way_the_walk_runs():
    t = flat_wires_to_polylines(
        _chain(), gap_ports=[("feed", "a", 0.25), ("load", "w", 0.25)]
    )
    where = {
        n: _point(t, pl, arc)
        for n, (pl, arc, _v) in zip(t["feed_names"], t["feeds"], strict=True)
    }
    assert where["feed"][0] == pytest.approx(0.25)  # a's p0 is x = 0
    assert where["load"][0] == pytest.approx(1.75)  # w's p0 is x = 2


def test_a_named_wire_no_port_sits_on_gets_no_feed():
    t = flat_wires_to_polylines(_chain(), gap_ports=[("feed", "a", None)])
    assert t["feed_names"] == ["feed"]


# ---------------------------------------------------------------------------
# the momwire engine
# ---------------------------------------------------------------------------

FREQ = 28.47
ARM = 0.25 * 299.792458 / FREQ


class _Dipole(AntennaBuilder):
    """One 21-segment wire. The feed port names it; an optional load port
    shares it a quarter of the way along, listed FIRST on purpose."""

    default_params = MappingProxyType(
        {
            "freq": FREQ,
            "design_freq": FREQ,
            "wire_name": "w",
            "port_wire": "w",
            "feed_at": None,
            "load_ohms": None,
        }
    )

    def build_wires(self):
        return [
            Wire((0.0, -ARM, 10.0), (0.0, ARM, 10.0), n_seg=21, name=self.wire_name)
        ]

    def build_network(self):
        ports, branches = {}, []
        if self.load_ohms is not None:
            ports["load"] = PortOnWire("load", wire=self.wire_name, at=0.25)
            branches.append(Load(port="load", r=self.load_ohms))
        ports["feed"] = PortOnWire("feed", wire=self.port_wire, at=self.feed_at)
        return Network(ports=ports, branches=branches, sources=[Driven(port="feed")])


def _z(**params):
    from antennaknobs.engines.momwire import MomwireEngine

    b = _Dipole(dict(_Dipole.default_params, **params))
    return complex(np.atleast_1d(MomwireEngine(b).impedance())[0])


@needs_position
def test_a_port_named_apart_from_its_wire_solves_like_one_named_after_it():
    z_after = _z(wire_name="feed", port_wire="feed")
    z_apart = _z()
    assert abs(z_apart - z_after) <= 1e-12 * abs(z_after)


@needs_position
def test_a_shorted_second_port_on_the_feed_wire_changes_nothing():
    """A near-zero series load closes its gap, so the wire is the plain dipole."""
    z_plain = _z()
    z_short = _z(load_ohms=1e-9)
    assert abs(z_short - z_plain) <= 1e-6 * abs(z_plain)


@needs_position
def test_an_open_second_port_changes_the_answer():
    z_plain = _z()
    z_open = _z(load_ohms=1e6)
    assert abs(z_open - z_plain) > 0.1 * abs(z_plain)


@needs_position
def test_the_feed_sits_where_at_says():
    from antennaknobs.engines.momwire import MomwireEngine

    eng = MomwireEngine(
        _Dipole(dict(_Dipole.default_params, feed_at=0.3, load_ohms=50.0))
    )
    pl, arc, _v = eng._feeds[eng._feed_names.index("feed")]
    poly = np.asarray(eng._polylines[pl], dtype=float)
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    k = min(int(np.searchsorted(cum, arc, side="right")) - 1, len(seg) - 1)
    point = poly[k] + (arc - cum[k]) / seg[k] * (poly[k + 1] - poly[k])
    assert point[1] == pytest.approx(-ARM + 0.3 * 2 * ARM)


@needs_position
def test_the_marker_follows_the_driven_port_not_the_first_one_listed():
    import antennaknobs.web.examples  # noqa: F401  registration order
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.web import adapter

    eng = MomwireEngine(_Dipole(dict(_Dipole.default_params, load_ohms=50.0)))
    assert eng._feed_names[0] == "load"
    pl, arc = adapter._primary_feed(eng)
    assert (pl, arc) == eng._feeds[eng._feed_names.index("feed")][:2]
