"""AK#1469 slice 2, part A2: an engine chooses a wire's segment count so a
positioned port sits exactly on a site of its grid.

A segment-centre engine (PyNEC, NEC-2, sinusoidal, BSpline d=2) needs a
segment centre at the port; a knot engine (NEC-5, razor, BSpline d=1) needs an
interior knot. The count grows to at most twice the authored count. Past that,
the parity count stays and the engine places the port on its nearest site. A
wire whose ports all sit at the middle keeps exactly the counts it had.
"""

from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Load, Network, PortOnWire, Wire
from antennaknobs.wire_catalog import on_site, site_count

needs_position = pytest.mark.skipif(
    not hasattr(PortOnWire("x"), "at"),
    reason="the installed momwire's PortOnWire has no wire/at (momwire#1059)",
)


@pytest.mark.parametrize(
    ("n", "positions", "family", "m"),
    [
        (20, [None], "centre", 21),  # the old odd rule
        (21, [None], "knot", 22),  # the old even rule
        (20, [0.3], "centre", 25),
        (21, [0.3], "centre", 25),
        (20, [0.3], "knot", 20),
        (21, [0.3], "knot", 30),
        (20, [1 / 3], "knot", 21),
        (20, [1 / 3], "centre", None),  # no count puts a centre at a third
        (20, [0.25, None], "knot", 20),
        (20, [0.25, None], "centre", None),  # odd and 2 mod 4 at once
        (20, [0.123], "knot", None),  # 1000 segments, past the 2x cap
    ],
)
def test_site_count(n, positions, family, m):
    assert site_count(n, positions, family) == m


def test_on_site():
    assert on_site(25, 0.3, "centre") and not on_site(20, 0.3, "centre")
    assert on_site(20, 0.3, "knot") and not on_site(21, 0.3, "knot")


FREQ = 28.47
ARM = 0.25 * 299.792458 / FREQ


class _Dipole(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": FREQ,
            "design_freq": FREQ,
            "n_seg": 20,
            "feed_at": None,
            "load_at": None,
        }
    )

    def build_wires(self):
        return [Wire((0.0, -ARM, 10.0), (0.0, ARM, 10.0), n_seg=self.n_seg, name="w")]

    def build_network(self):
        ports = {"feed": PortOnWire("feed", wire="w", at=self.feed_at)}
        branches = []
        if self.load_at is not None:
            ports["load"] = PortOnWire("load", wire="w", at=self.load_at)
            branches.append(Load(port="load", r=50.0))
        return Network(ports=ports, branches=branches, sources=[Driven(port="feed")])


def _b(**params):
    return _Dipole(dict(_Dipole.default_params, **params))


@needs_position
def test_a_middle_port_keeps_the_old_parity_counts():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.nec5 import NEC5Engine
    from antennaknobs.engines.pynec import PyNECEngine

    assert PyNECEngine(_b()).tups[0][2] == 21
    assert NEC5Engine(_b(n_seg=21), require_exe=False).tups[0][2] == 22


@needs_position
def test_pynec_centres_a_segment_on_the_port():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    assert PyNECEngine(_b(feed_at=0.3)).tups[0][2] == 25


@needs_position
def test_momwire_bspline_centres_a_segment_on_the_port():
    from antennaknobs.engines.momwire import MomwireEngine

    assert MomwireEngine(_b(feed_at=0.3))._edge_segments == [[25]]


@needs_position
def test_nec5_puts_a_knot_on_the_port_and_writes_it():
    from antennaknobs.engines.nec5 import NEC5Engine

    eng = NEC5Engine(_b(n_seg=21, feed_at=0.3), require_exe=False)
    assert eng.tups[0][2] == 30
    deck = eng.deck([FREQ])
    cards = [
        " ".join(line.split()[:5])
        for line in deck.splitlines()
        if line.startswith("EX")
    ]
    assert cards == ["EX 0 1 9 2"]


@needs_position
def test_every_port_on_the_wire_is_honoured_at_once():
    from antennaknobs.engines.nec5 import NEC5Engine

    # a knot at the middle (even) and at a quarter (a multiple of 4), from 21 up
    assert NEC5Engine(_b(n_seg=21, load_at=0.25), require_exe=False).tups[0][2] == 24


@needs_position
def test_an_unreachable_position_keeps_the_parity_count():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    assert PyNECEngine(_b(feed_at=1 / 3)).tups[0][2] == 21
