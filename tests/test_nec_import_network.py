"""Imported LD/TL networks must equal the same network authored by hand.

``parse_nec(network=True)`` turns a deck's LD/TL/NT cards into named wires
plus ``build_network()`` branches (issue #385). The equivalence tests here
pin the translation end to end: a deck imported this way and a Builder
authoring the identical geometry + network by hand must produce the SAME
impedance through the same engine/solver — so what's under test is purely
the translation (segment addressing, splitting, port naming), not the
physics, which the network system's own tests already pin (e.g.
``test_tl_composition.py`` against NEC's native ``tl_card``).

The whip tests then close the loop on the real benchmark deck
(``whip_antenna_8ft_groundplane.nec``, the deck the whole #383 arc was
built around): the TRANSLATION test (parse-only, fast) pins that its LD
cards become exactly the 90 nH / 3 pF post loads ``verticals.elt_whip``
models by hand; the full-size two-engine impedance validation is marked
``heavy_mesh`` and NEVER runs in CI — a 4392-segment solve is a benchmark,
not a unit test (~12 s, ~2.2 GB; it OOM-killed the GitHub runner on top of
the catalog lane's accumulated RSS). Run it manually after nec-import or
engine changes::

    python -m pytest -m heavy_mesh
"""

from pathlib import Path

import pytest

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import MomwireEngine
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Admittance, Driven, Load, Network, PortOnWire, TL
from momwire import BSplineSolver

FREQ = 14.1
DEG2 = {"degree": 2}


def _deck_builder(deck, freq=FREQ, radius=None):
    """Minimal Builder over an imported network-mode deck — exactly what a
    deck stub does: wire_tuples() for geometry, network() for the drive."""

    class B(AntennaBuilder):
        default_params = {"freq": freq}

        def build_wires(self):
            return deck.wire_tuples()

        def build_network(self):
            return deck.network()

        def build_wire_material(self):
            return WireSpec(radius=radius or deck.dominant_radius())

    return B()


def _momwire_z(builder):
    eng = MomwireEngine(builder, solver=BSplineSolver, solver_kwargs=DEG2, ground=None)
    return eng.impedance()[0]


def test_imported_ld_matches_hand_built_load():
    # A 10 m dipole on 10 segments, fed at segment 5, series coil at
    # segment 8 — both marks off-middle, so both split.
    deck = parse_nec(
        "GW 1 10 0 -5 10 0 5 10 0.001\nGE\nEX 0 1 5 0 1 0\nLD 0 1 8 8 0 2e-6 0\nEN\n",
        network=True,
    )

    class Hand(AntennaBuilder):
        """The same geometry and network authored the catalog way: the fed
        and loaded segments as named 1-segment wires on the deck's own
        1 m boundaries."""

        default_params = {"freq": FREQ}

        def build_wires(self):
            y = lambda k: float(-5 + k)  # noqa: E731 — segment boundary k
            seg = lambda a, b, n: ((0.0, y(a), 10.0), (0.0, y(b), 10.0), n)  # noqa: E731
            return [
                seg(0, 4, 4) + (None,),
                seg(4, 5, 1) + (None, "feed"),
                seg(5, 7, 2) + (None,),
                seg(7, 8, 1) + (None, "load1"),
                seg(8, 10, 2) + (None,),
            ]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "load1": PortOnWire("load1")},
                branches=[Load(port="load1", l=2e-6)],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

        def build_wire_material(self):
            return WireSpec(radius=0.001)

    z_imported = _momwire_z(_deck_builder(deck, radius=0.001))
    z_hand = _momwire_z(Hand())
    assert z_imported == pytest.approx(z_hand, rel=1e-9)
    # And the load actually acts: without it the dipole reads differently.
    bare = parse_nec(
        "GW 1 10 0 -5 10 0 5 10 0.001\nGE\nEX 0 1 5 0 1 0\nEN\n", network=True
    )
    z_bare = _momwire_z(_deck_builder(bare, radius=0.001))
    assert abs(z_imported - z_bare) > 1.0


def test_imported_tl_matches_hand_built_line():
    # Two 3-segment verticals a fixed distance apart, front fed, rear
    # reachable only through a crossed 300 Ohm line of the card's length.
    deck = parse_nec(
        "GW 1 3 0 0 10 0 0 13 0.001\n"
        "GW 2 3 4 0 10 4 0 13 0.001\n"
        "GE\n"
        "EX 0 1 2 0 1 0\n"
        "TL 1 2 2 2 -300 5.5 0 0 0 0\n"
        "EN\n",
        network=True,
    )

    class Hand(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wires(self):
            return [
                ((0.0, 0.0, 10.0), (0.0, 0.0, 13.0), 3, None, "feed"),
                ((4.0, 0.0, 10.0), (4.0, 0.0, 13.0), 3, None, "far"),
            ]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "far": PortOnWire("far")},
                branches=[TL(a="feed", b="far", z0=300.0, length=5.5, transposed=True)],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

        def build_wire_material(self):
            return WireSpec(radius=0.001)

    z_imported = _momwire_z(_deck_builder(deck, radius=0.001))
    z_hand = _momwire_z(Hand())
    assert z_imported == pytest.approx(z_hand, rel=1e-9)


def test_imported_reactive_tl_end_shunt_matches_hand_built_admittance():
    # A 300 Ohm line to a rear vertical, its far end terminated by a reactive
    # shunt G + jB (issue #423): B != 0 is no longer dropped — it becomes a
    # fixed 1-port Admittance at that port, exact at every frequency.
    deck = parse_nec(
        "GW 1 3 0 0 10 0 0 13 0.001\n"
        "GW 2 3 4 0 10 4 0 13 0.001\n"
        "GE\n"
        "EX 0 1 2 0 1 0\n"
        "TL 1 2 2 2 300 5.5 0 0 0.002 0.01\n"
        "EN\n",
        network=True,
    )
    assert "TL" not in deck.ignored  # translated, not dropped

    y_end = complex(0.002, 0.01)

    class Hand(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wires(self):
            return [
                ((0.0, 0.0, 10.0), (0.0, 0.0, 13.0), 3, None, "feed"),
                ((4.0, 0.0, 10.0), (4.0, 0.0, 13.0), 3, None, "far"),
            ]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "far": PortOnWire("far")},
                branches=[
                    TL(a="feed", b="far", z0=300.0, length=5.5),
                    Admittance(ports=("far",), y=((y_end,),)),
                ],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

        def build_wire_material(self):
            return WireSpec(radius=0.001)

    z_imported = _momwire_z(_deck_builder(deck, radius=0.001))
    z_hand = _momwire_z(Hand())
    assert z_imported == pytest.approx(z_hand, rel=1e-9)


def _whip_deck():
    text = Path(__file__).parent / "data" / "whip_antenna_8ft_groundplane.nec"
    return parse_nec(text.read_text(), name=text.name, network=True)


def test_whip_deck_network_translation():
    """The #385 acceptance oracle, translation half (parse-only, fast):
    the W8IO benchmark deck's two LD cards translate to exactly what
    verticals.elt_whip hand-models — a 90 nH series load on one grounded
    post and 3 pF on the other — with one feed and nothing left
    unmodelled but the RP output request."""
    net = _whip_deck().network()
    by_port = {br.port: br for br in net.branches}
    assert set(by_port) == {"load1", "load2"}
    assert by_port["load1"].l == pytest.approx(90e-9) and by_port["load1"].c is None
    assert by_port["load2"].c == pytest.approx(3e-12) and by_port["load2"].l is None
    assert [s.port for s in net.sources] == ["feed"]
    assert _whip_deck().ignored == ("RP",)


@pytest.mark.heavy_mesh
def test_whip_deck_full_size_benchmark():
    """The #385 acceptance oracle, physics half — NOT a unit test and never
    run in CI (see module docstring; `python -m pytest -m heavy_mesh`).
    The imported deck must land in the matched free-space impedance window
    the elt_whip catalog test pins (raw ~1.4+33.5j transformed to ~63+8j
    at 406 MHz), on both engines. Exercises the junction shattering that
    connects the matching straps to the whip (they cross it mid-wire —
    without the cuts the network floats on a stub and the match is
    garbage, and PyNEC refuses the geometry outright as a wire
    intersection). Measured 2026-07-15: momwire sinusoidal 63.09+8.09j,
    PyNEC 63.02+8.06j."""
    pytest.importorskip("PyNEC")
    from antennaknobs.engines import PyNECEngine
    from momwire import SinusoidalSolver

    b = _deck_builder(_whip_deck(), freq=406.0)
    z_nec = PyNECEngine(b, ground=None).impedance()[0]
    z_mom = MomwireEngine(b, solver=SinusoidalSolver, ground=None).impedance()[0]
    for z in (z_nec, z_mom):
        assert 50.0 < z.real < 75.0
        assert abs(z.imag) < 20.0
    assert z_mom == pytest.approx(z_nec, rel=0.05)


# --------------------------------------------------------------------------
# An all-zero NT is an OPEN, not a no-op (issue #961)
# --------------------------------------------------------------------------

#: momwire's byte fixture `dipole_nt_all_zero`, inlined rather than read out
#: of the submodule's test tree (those fixtures are not installed with
#: antennaknobs, and a path into `momwire/tests/` would break the moment the
#: submodule moves). Two parallel 5 m dipoles 1 m apart at 30 MHz; the NT
#: addresses the fed segment and its opposite number on the parasite.
_ALL_ZERO_NT_DECK = """CE an all-zero NT is not a no-op
GW 1 9 0. 0. -2.5 0. 0. 2.5 0.001
GW 2 9 1.0 0. -2.5 1.0 0. 2.5 0.001
GE 0
EX 0 1 5 0 1.
NT 1 5 2 5 0. 0. 0. 0. 0. 0.
FR 0 1 0 0 30. 0
EN
"""

#: nec2c's own answer for that deck, read from the committed capture
#: `momwire/tests/fixtures/nec_portal/dipole_nt_all_zero.out` (ANTENNA INPUT
#: PARAMETERS, tag 1 seg 5). nec2c ACCEPTS the all-zero card and opens the
#: gap it addresses; this is the number that behaviour produces.
_ALL_ZERO_NT_NEC2C_Z = complex(8.0243e01, 4.3247e01)


def test_all_zero_nt_is_translated_not_skipped():
    """The card is expressed, not ignored.

    Skipping it (the behaviour before #961) left the addressed segments
    UNCUT — a short where NEC has an open — and reported the deck as
    partially understood. The card now falls through to the resistive pi
    with every leg zero, which is exactly the open: the ports still get
    cut, and `network()` emits no branch for a None leg.
    """
    deck = parse_nec(_ALL_ZERO_NT_DECK, network=True)

    assert "NT" not in deck.ignored, deck.ignored_detail
    (nt,) = deck.nts
    assert (nt.series_r, nt.shunt_r_a, nt.shunt_r_b, nt.y) == (None, None, None, None)

    # The cut is the whole content of the card: the parasite's segment 5
    # becomes a port, and nothing is stamped across it.
    assert (nt.wire_b, nt.seg_b) in deck._port_plan
    assert deck.network().branches == []


def test_all_zero_nt_opens_the_gap_and_tracks_nec2c():
    """The oracle, and the antenna the old skip was answering instead.

    Deliberately gated against nec2c's captured answer for THIS deck rather
    than against a hand-built equivalent: the whole claim of #961 is that
    the importer and NEC agree about what the card MEANS, so a hand-built
    twin would only pin our own translation against itself.

    The control is the same deck with the NT card deleted — which is
    precisely what skipping it produced. It is nowhere near, which is why
    this was a wrong answer rather than a harmless omission.
    """
    z_open = _momwire_z(
        _deck_builder(parse_nec(_ALL_ZERO_NT_DECK, network=True), freq=30.0)
    )

    # Measured 80.536 + 43.63j against nec2c's 80.243 + 43.247j — 0.4 % and
    # 0.9 %, the ordinary BSpline-degree-2 vs NEC-2-pulse basis difference on
    # this geometry. Pinned at 3 % for mesh/basis headroom; it is two orders
    # of magnitude tighter than the gap to the control below.
    assert z_open == pytest.approx(_ALL_ZERO_NT_NEC2C_Z, rel=0.03)

    control_deck = "\n".join(
        ln for ln in _ALL_ZERO_NT_DECK.splitlines() if not ln.startswith("NT")
    )
    z_short = _momwire_z(
        _deck_builder(parse_nec(control_deck, network=True), freq=30.0)
    )

    # Measured 24.47 + 66.35j: the resistance is off by 3.3x. A gate that
    # only checked `z_open` would still pass if the translation regressed to
    # a short AND the tolerance were loosened, so the distance is pinned too.
    assert abs(z_short - _ALL_ZERO_NT_NEC2C_Z) > 0.5 * abs(_ALL_ZERO_NT_NEC2C_Z)
