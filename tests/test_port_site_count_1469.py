"""AK#1469 slice 2, part A2, as split-always made it (AK#1511): a positioned
port sits exactly on a site of its engine's grid, on the wire's own count.

A segment-centre engine (PyNEC, NEC-2, sinusoidal, BSpline d=2) needs a
segment centre at the port; a knot engine (NEC-5, razor, BSpline d=1) needs an
interior knot. A wire carrying a positioned port keeps its authored count,
with no parity bump and no re-count. When its ports are all sites of that
count it stays whole; otherwise PyNEC, NEC-2 and NEC-5 split it so every port
sits exactly on a site. A wire whose ports all sit at the middle keeps exactly
the counts it had.
"""

from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Load, Network, PortOnWire, Wire
from antennaknobs.wire_catalog import on_site

needs_position = pytest.mark.skipif(
    not hasattr(PortOnWire("x"), "at"),
    reason="the installed momwire's PortOnWire has no wire/at (momwire#1059)",
)


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
def test_pynec_feeds_a_segment_centre_of_the_authored_count():
    """0.275 is the centre of segment 6 of 20: the wire keeps its even 20, with
    no parity bump, and the port feeds that segment. 0.3 is no centre of 20,
    so that wire is split instead of re-counted to 25."""
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    assert [t[2] for t in PyNECEngine(_b(feed_at=0.275)).tups] == [20]
    assert "w" in PyNECEngine(_b(feed_at=0.3))._split_wires


@needs_position
def test_momwire_keeps_the_authored_count_of_a_positioned_wire():
    """No re-count on momwire either: its default basis feeds 0.3 at the exact
    arclength of the authored 20 segments."""
    from antennaknobs.engines.momwire import MomwireEngine

    assert MomwireEngine(_b(feed_at=0.3))._edge_segments == [[20]]


@needs_position
def test_nec5_feeds_a_knot_of_the_authored_count_and_writes_it():
    """0.3 is knot 6 of 20: the wire stays whole and the EX card names that
    knot. On 21 segments it is no knot, so NEC-5 cuts the wire there instead of
    re-counting it to 30."""
    from antennaknobs.engines.nec5 import NEC5Engine

    eng = NEC5Engine(_b(feed_at=0.3), require_exe=False)
    assert [t[2] for t in eng.tups] == [20]
    deck = eng.deck([FREQ])
    cards = [
        " ".join(line.split()[:5])
        for line in deck.splitlines()
        if line.startswith("EX")
    ]
    assert cards == ["EX 0 1 6 2"]
    assert "w" in NEC5Engine(_b(n_seg=21, feed_at=0.3), require_exe=False)._split_wires


@needs_position
def test_every_port_on_the_wire_is_honoured_at_once():
    """The middle and a quarter are both knots of 20, so that wire stays whole;
    on 21 segments neither is, and the wire is cut at both."""
    from antennaknobs.engines.nec5 import NEC5Engine

    assert [t[2] for t in NEC5Engine(_b(load_at=0.25), require_exe=False).tups] == [20]
    cut = NEC5Engine(_b(n_seg=21, load_at=0.25), require_exe=False)
    assert cut._split_ports == {"load": "w@load", "feed": "w@feed"}


@needs_position
def test_an_unreachable_position_splits_the_wire_it_sits_on():
    """A third is no segment centre of 20, so the port gets a short piece of its
    own centred on it, a third of the way to the nearer end either side, with
    plain wire at each end (AK#1511)."""
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    assert [(t[2], t[4]) for t in PyNECEngine(_b(feed_at=1 / 3)).tups] == [
        (4, None),
        (5, "w@feed"),
        (11, None),
    ]


@needs_position
def test_an_unreachable_position_shared_with_a_second_port_splits_for_both():
    """Each port gets its own short piece; the load's is pegged at a third of
    its end distance, the feed's at a third of its own (AK#1511)."""
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    assert [(t[2], t[4]) for t in PyNECEngine(_b(feed_at=1 / 3, load_at=0.8)).tups] == [
        (4, None),
        (5, "w@feed"),
        (6, None),
        (3, "w@load"),
        (3, None),
    ]


# ---------------------------------------------------------------------------
# the offset advisory
# ---------------------------------------------------------------------------


def _placement_notes(advisories):
    return [a for a in advisories if a["category"] == "FeedPlacement"]


@needs_position
def test_an_exactly_placed_port_raises_no_advisory():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    assert _placement_notes(PyNECEngine(_b(feed_at=0.275)).advisories) == []


@needs_position
def test_pynec_says_it_split_a_wire_carrying_two_ports():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    (note,) = _placement_notes(PyNECEngine(_b(feed_at=1 / 3, load_at=0.8)).advisories)
    assert "'feed' at 0.3333 and 'load' at 0.8" in note["text"]
    assert "segment centre" in note["text"] and "mm away" not in note["text"]


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
