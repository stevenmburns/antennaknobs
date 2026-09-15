"""AK#1469 slice 2, part A2: an engine chooses a wire's segment count so a
positioned port sits exactly on a site of its grid.

A segment-centre engine (PyNEC, NEC-2, sinusoidal, BSpline d=2) needs a
segment centre at the port; a knot engine (NEC-5, razor, BSpline d=1) needs an
interior knot. The count grows to at most twice the authored count. Past that,
a wire carrying that one port is split so the port sits at the middle of a
piece (AK#1510), and a wire carrying several keeps the parity count, each port
on the engine's nearest site. A wire whose ports all sit at the middle keeps
exactly the counts it had.
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
def test_an_unreachable_position_splits_the_wire_it_sits_on():
    """No count puts a centre at a third, so the wire is cut at two thirds and
    the port fed at the middle of the first piece (AK#1510)."""
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    assert [(t[2], t[4]) for t in PyNECEngine(_b(feed_at=1 / 3)).tups] == [
        (13, "w"),
        (7, None),
    ]


@needs_position
def test_an_unreachable_position_shared_with_a_second_port_keeps_the_parity_count():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    assert [t[2] for t in PyNECEngine(_b(feed_at=1 / 3, load_at=0.8)).tups] == [21]


# ---------------------------------------------------------------------------
# the offset advisory
# ---------------------------------------------------------------------------


def _placement_notes(advisories):
    return [a for a in advisories if a["category"] == "FeedPlacement"]


@needs_position
def test_an_exactly_placed_port_raises_no_advisory():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    assert _placement_notes(PyNECEngine(_b(feed_at=0.3)).advisories) == []


@needs_position
def test_pynec_names_the_offset_it_could_not_avoid_between_two_ports():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    notes = _placement_notes(PyNECEngine(_b(feed_at=1 / 3, load_at=0.8)).advisories)
    (note,) = [n for n in notes if "'feed'" in n["text"]]
    assert "segment centre" in note["text"] and "mm away" in note["text"]


@needs_position
def test_nec5_says_it_split_the_wire_past_the_cap():
    from antennaknobs.engines.nec5 import NEC5Engine

    (note,) = _placement_notes(
        NEC5Engine(_b(feed_at=0.123), require_exe=False).advisories
    )
    assert "knot" in note["text"] and "split" in note["text"]


@needs_position
def test_momwire_reports_a_snapping_solvers_own_placement():
    """Razor snaps to its knots. At 0.123 no knot count up to 2x reaches the
    port, so razor places it on its nearest knot and the note says how far."""
    from momwire import RazorSolver

    from antennaknobs.engines.momwire import MomwireEngine

    eng = MomwireEngine(_b(feed_at=0.123), solver=RazorSolver)
    eng.impedance()
    (note,) = _placement_notes(eng.advisories)
    assert "'feed'" in note["text"] and "mm away" in note["text"]


@needs_position
def test_momwire_bspline_places_exactly_and_says_nothing():
    from antennaknobs.engines.momwire import MomwireEngine

    eng = MomwireEngine(_b(feed_at=0.3))
    eng.impedance()
    assert _placement_notes(eng.advisories) == []


@needs_position
def test_the_app_serves_the_note():
    pytest.importorskip("PyNEC")
    import antennaknobs.web.examples  # noqa: F401  registration order
    from antennaknobs.engines.pynec import PyNECEngine
    from antennaknobs.web import adapter

    served = adapter._solver_advisories(PyNECEngine(_b(feed_at=1 / 3)))
    assert _placement_notes(served)
