"""A port at a wire END stays at that end when another port shares the wire
(AK#1619).

AK#1605 fixed this in the SITE-PLAN path: `wire_catalog.on_site` calls an
endpoint a site of both families, so a wire whose only port is at its end is
never split, and deck 0019's base feed reproduces the licensed NEC-5 exactly.
The SPAN-SPLITTING path still centred it. `split_spans`' contract was "every
port at `positions` (fractions in (0, 1), distinct)", an endpoint port is out
of that contract, and the segment-centre rule gives every port "a short piece
[u - x, u + x] centred on it" — which for a port at 0.0 is a piece [0, 2x]
whose centre is x, not 0. It fired only when a SECOND port on the wire forced
a split at all, which is why one base feed and nothing else was already right.

Measured where it mattered. `0116/0117_40-meter-four-square-array` are four
9.9822 m verticals on six segments, each driven at its base by `EX 4,N,-1`,
with a `TL` joining the midpoints of two of them. The line's port forces the
split and the base feed came out at 0.6238875 m — 1/16 of the way up, the
centre of the span [0, 1/8]. Against `momwire.eznec.serve`, which feeds the
contact, that deck read 1.022e-01. It reads 1.208e-02 now, and the bar in
`test_two_routes_agree_corpus_1584.py` moved with it.

The KNOT family was worse and less visible. An end port took the first piece
away from the interior port that owned its `hi` knot, so that port pointed at
a piece name nothing emitted and the design RAISED `end port references wire
name 'w@load0' but no build_wires() tuple carries that name`. No NEC deck
reaches it — a card's port lands on a knot, which is on-grid, so nothing
splits — but the library does, which is how `_BaseFedVertical` below reaches
it. Both families are parametrised here for that reason.
"""

import itertools
import pathlib
from types import MappingProxyType

import momwire
import numpy as np
import pytest
from momwire.razor import RazorSolver

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.network import Driven, Load, Network, PortOnWire, Wire

DECKS = (
    pathlib.Path(momwire.__file__).resolve().parents[2] / "tests/fixtures/eznec/decks"
)
HEIGHT = 10.0
LOAD_AT = 0.31

# The two families, each through the engine that ships it: "centre" (a port at
# the middle of a piece of its own) and "knot" (a port at the knot two pieces
# share). The split runs on both.
FAMILIES = {
    "centre": {},
    "knot": dict(solver=RazorSolver, solver_kwargs={"nec5_quadrature": True}),
}


class _BaseFedVertical(AntennaBuilder):
    """0116's shape in the library: a ground-mounted vertical fed AT the
    contact, with a 50 ohm load partway up whose position is off every site of
    the wire's own six segments, so the wire must be split."""

    default_params = MappingProxyType(
        {
            "freq": 7.1,
            "design_freq": 7.1,
            "n_seg": 6,
            "feed_at": 0.0,
            "load_at": LOAD_AT,
        }
    )

    def build_wires(self):
        return [Wire((0.0, 0.0, 0.0), (0.0, 0.0, HEIGHT), n_seg=self.n_seg, name="w")]

    def build_wire_material(self):
        return WireSpec(radius=1e-3)

    def build_network(self):
        ports = {
            "feed": PortOnWire("feed", wire="w", at=self.feed_at),
            "load0": PortOnWire("load0", wire="w", at=self.load_at),
        }
        return Network(
            ports=ports,
            branches=[Load(port="load0", r=50.0)],
            sources=[Driven(port="feed")],
        )


def _engine(family, **params):
    builder = _BaseFedVertical(dict(_BaseFedVertical.default_params, **params))
    eng = MomwireEngine(builder, ground="pec", ground_z=0.0, **FAMILIES[family])
    eng.impedance()
    return eng


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_the_base_feed_is_at_the_contact_when_a_load_shares_the_wire(family):
    """THE gate. Before AK#1619 the centre family put this feed 0.625 m up a
    10 m vertical and the knot family raised."""
    eng = _engine(family)
    # Not vacuous: the wire really was split, so the fed path is the one under
    # test rather than the whole-wire path that was always right.
    assert eng._split_ports, "nothing split — this case no longer asks anything"
    arcs = sorted(arc for _wire, arc, _v in eng._feeds)
    assert arcs == pytest.approx([0.0, LOAD_AT * HEIGHT], abs=1e-12)
    assert eng._split_port_at["feed"] == 0.0


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_the_split_pieces_still_cover_the_wire_exactly_once(family):
    """The end port is placed, not cut to, so the cuts are the interior ports'
    alone — and the pieces must still be the whole wire, end to end."""
    eng = _engine(family)
    (split,) = eng._split_wires.values()
    spans = split.plan.spans
    assert spans[0].lo == 0.0 and spans[-1].hi == 1.0
    assert all(a.hi == b.lo for a, b in itertools.pairwise(spans))
    # Every port placed exactly once, and the feed at the wire's own p0.
    assert spans[0].p0_port == 0
    assert sum(s.port is not None for s in spans) == 1


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_a_piece_is_never_both_a_gap_port_and_a_vertex_port(family):
    """Why the knot family used to raise, in the form it takes now.

    A `PortAtVertex` is a series EMF that needs its wire gapless, and a
    `PortOnWire` cuts a delta gap in it; `validate_named_wires_referenced`
    refuses a wire carrying both by name (issues #579, #898). An end port has
    nowhere else to go than the piece that bounds it, so on the knot family the
    port sharing that piece takes the POSITIONED spelling at the same knot —
    what `momwire.eznec.serve` does for every network end, and what AK#1617
    already moved a crowded junction onto."""
    from antennaknobs.network import PortAtVertex

    eng = _engine(family)
    meshed = eng._network_as_meshed(eng.builder.build_network())
    by_piece = {}
    for name, port in meshed.ports.items():
        by_piece.setdefault(getattr(port, "wire", None), []).append(port)
    for piece, ports in by_piece.items():
        kinds = {isinstance(p, PortAtVertex) for p in ports}
        assert len(kinds) == 1, f"{piece} carries both spellings: {ports}"


def test_the_four_square_base_feeds_sit_at_the_contact():
    """The deck the issue was found on, through the shipping route.

    Its `TL` joins the midpoints of verticals 1 and 3, so those two wires carry
    two ports and are split; the other two carry one port and are not. All four
    base feeds belong at arclength 0."""
    path = DECKS / "0116_40-meter-four-square-array.nec"
    cls = builder_from_file(str(path))
    eng = MomwireEngine(cls(), ground=cls.file_ground)
    eng.impedance()
    assert eng._split_ports, "nothing split — the TL port should force it"

    meshed = eng._network_as_meshed(cls().build_network())
    feeds = {n: p for n, p in meshed.ports.items() if n.startswith("feed")}
    assert len(feeds) == 4
    assert all(p.at == 0.0 for p in feeds.values()), feeds

    arcs = sorted(arc for _wire, arc, _v in eng._feeds)
    # Four contacts and the two line ports, at the midpoint of a 9.9822 m
    # vertical. 0.6238875 -- 1/16 of the way up -- is what this used to read.
    assert arcs == pytest.approx([0.0, 0.0, 0.0, 0.0, 4.9911, 4.9911], abs=1e-9)


def test_a_sixteenth_of_the_way_up_is_a_different_antenna():
    """Why this is a defect and not a rounding preference, on the deck's own
    vertical: the same solver, the same six-segment mesh, the same ground, only
    the feed's arclength moving from the contact to where the split used to put
    it. 1.8 % on a bare vertical -- and 10.2 % on 0116, where four of them are
    coupled through a line.

    A direct solver call, deliberately: the question here is what the ARCLENGTH
    is worth, not what antennaknobs does with it. The gates above are the ones
    that read the shipping path."""
    from momwire.bspline import BSplineSolver

    length = 9.9822

    def z(arclength):
        solver = BSplineSolver(
            wires=[np.array([[0.0, 0.0, 0.0], [0.0, 0.0, length]])],
            n_per_edge_per_wire=[[6]],
            wire_radius=1e-3,
            wavelength=299.8 / 7.1,
            degree=2,
            feed_model="point",
            feed_wire_index=0,
            feed_arclength=arclength,
            ground_z=0.0,
        )
        return complex(solver.compute_impedance()[0])

    contact, centred = z(0.0), z(0.0625 * length)
    assert abs(centred - contact) / abs(contact) > 1.5e-2
