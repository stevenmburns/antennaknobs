"""A ground-contact feed sits AT the contact, not at its cell's centre
(AK#1605).

AK#1598 routed a wire end standing in the ground plane to a positioned port,
which was right, and put it at the first mesh cell's CENTRE, which was not.
The argument was that a segment gap is `E = V/Delta` over "the mesh cell
containing s_f", so the contact and that centre are one drive — true, and true
only under `feed_model="segment"`. The default is `"point"` on both
`BSplineSolver` and `SinusoidalGalerkinSolver` (momwire#654), where the drive
is `E = V*delta(s - s_f)` and where in the cell the point sits IS the answer.

It also explained a standing disagreement between two of OUR OWN shipping
routes: `momwire.eznec.serve` (the signed Windows drop-in) fed the contact all
along, antennaknobs (the workbench and CLI) fed the cell centre. Nothing
compared them, which is why a 29 %-in-X gap went unnoticed — hence
`test_the_two_routes_agree_on_a_shared_deck` below, which is the gate that was
missing rather than the one that failed.

Depends on momwire#1135: `PortOnWire` refused an endpoint, which is what made
AK#1598 reach for the cell centre in the first place.
"""

import numpy as np
import pytest

from antennaknobs.engine import split_spans
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec
from antennaknobs.wire_catalog import on_site

# A base-fed vertical from momwire's own EZNEC corpus: one wire, 10 segments,
# GN 1 perfect ground, `EX 4,1,-1` at the base.
DECK = "momwire/tests/fixtures/eznec/decks/0019_vertical-over-real-ground.nec"


def _ak(path):
    cls = builder_from_file(path)
    return np.asarray(MomwireEngine(cls(), ground=cls.file_ground).impedance())


def test_the_feed_is_at_the_contact():
    deck = parse_nec(open(DECK, errors="replace").read(), name="0019", network=True)
    (src,) = deck.network().sources
    assert deck.network().ports[src.port].at == 0.0


def test_the_two_routes_agree_on_a_shared_deck():
    """THE gate, and the one that did not exist.

    `momwire.eznec.serve` and antennaknobs' `builder_from_file` route are two
    ways into the same solver, shipped to different users — serve in the signed
    Windows drop-in, the AK route in the workbench and CLI. They disagreed by
    1.775e-02 on this deck, entirely because of where the contact feed sat.

    The bar is deliberately far from both numbers: five times the 3.7e-4 that
    remained when this was written, and forty times under the 1.8e-2 the
    placement bug cost. A regression in placement cannot pass it.

    That 3.7e-4 is now GONE, and this docstring used to explain it wrongly:
    it was read as route CONFIG (quadrature and basis defaults), on the
    strength of its being present with no loads at all. It was the SPEED OF
    LIGHT — the two routes turned the deck's frequency into a wavelength with
    different constants (AK#1607). With that shared, the two routes agree here
    to 1.2e-17. The bar stays where it is: this test's subject is placement,
    and the tight gate on the constant lives in
    `test_deck_speed_of_light_1607.py`, which would fail first."""
    from momwire.deck._nec5 import parse_nec5
    from momwire.eznec import serve

    run = serve(parse_nec5(open(DECK, errors="replace").read()))
    (mw,) = (complex(s.impedance) for s in run.sources)
    (ak,) = _ak(DECK)
    rel = abs(ak - mw) / abs(mw)
    assert rel < 2e-3, f"AK {ak!r} vs serve {mw!r}, rel {rel:.3e}"


def test_the_cell_centre_is_a_different_drive_under_the_point_model():
    """Why this is a defect and not a preference, measured on the deck itself.

    The same solver, the same mesh, the same ground — only the feed's arclength
    moves, from the contact to the centre of the cell it stands in. Under the
    default point model that is 29 % in X. (Under `segment` the two are
    bit-identical, which is what made AK#1598's argument look sound.)"""
    from momwire.bspline import BSplineSolver

    wires = [np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 10.3]])]
    lam = 42.827494

    def z(arclength, model):
        s = BSplineSolver(
            wires=[w.copy() for w in wires],
            n_per_edge_per_wire=[[10]],
            wire_radius=0.02,
            wavelength=lam,
            degree=2,
            feed_model=model,
            feed_wire_index=0,
            feed_arclength=arclength,
            ground_z=0.0,
        )
        return complex(s.compute_impedance()[0])

    centre = 0.5 * 10.3 / 10
    at_contact, at_centre = z(0.0, "point"), z(centre, "point")
    assert abs(at_centre.imag - at_contact.imag) / abs(at_contact.imag) > 0.25

    # ... and the model is what decides it, which is the whole correction.
    assert z(0.0, "segment") == pytest.approx(z(centre, "segment"), rel=0, abs=0)


def test_an_endpoint_counts_as_a_site_for_both_families():
    """`on_site` decides whether the wire is SPLIT so a port lands on one. An
    endpoint cannot be split to — the span around it has zero width — and does
    not need to be, since the engines place an arclength exactly or snap to the
    end segment. The "knot" family already agreed; "centre" now does too."""
    for family in ("centre", "knot"):
        assert on_site(10, 0.0, family)
        assert on_site(10, 1.0, family)
    # The interior rule is untouched.
    assert on_site(10, 0.05, "centre") and not on_site(10, 0.05, "knot")
    assert on_site(10, 0.1, "knot") and not on_site(10, 0.1, "centre")


@pytest.mark.parametrize(
    "u",
    [
        [0.0],
        [1.0],
        [0.0, 0.3],
        [0.7, 1.0],
        [0.0, 1.0],
        [0.0, 0.5, 1.0],
        # the guard's end of it: the interior port's own piece runs out to the
        # end the other port already occupies, so ONE piece carries both.
        [0.0, 0.05],
        [0.95, 1.0],
    ],
)
def test_a_split_places_every_port_and_slivers_nothing(u):
    """The failure a port at an endpoint used to cause, one layer down, and
    (AK#1619) the one it caused after that.

    `split_spans` reserves the room between a port and the wire end so the
    port's span does not overrun it. At an endpoint that room is zero, and one
    `half` serves both sides (`lo = ui - xi`, `hi = ui + xi`), so the zero
    collapsed the span entirely and reached the geometry layer as
    `degenerate edge (p0==p1 within eps)`.

    This test carried only those width assertions, and its name promised more
    than it measured: it never checked that an END port lands ON the end. It
    did not, and AK#1619 is what that cost. The end ports are now filtered out
    of the geometry — the cuts are the interior ports' — and recorded on the
    piece that bounds them, so what has to be checked is PLACEMENT: every port
    placed exactly once, an end port at its end and every other port on a site
    of a piece.

    Not reachable from a NEC deck today — a NEC-5 load lands on a knot, which
    is always on-grid, so the split does not run — but reachable through the
    library, and `split_spans` is a pure function whose contract this is."""
    for parity in ("odd", "even"):
        plan = split_spans(10, u, parity)
        assert all(s.hi > s.lo for s in plan.spans), plan.spans
        assert all(s.n_seg >= 1 for s in plan.spans), plan.spans
        assert plan.spans[0].lo == 0.0 and plan.spans[-1].hi == 1.0

        # port -> (the piece it is on, where on it: 0.0/1.0 a wire end, None
        # the site the cut made). A piece may carry an end port AND a port of
        # its own, so this is a census, not one entry per span.
        placed = {}
        for j, s in enumerate(plan.spans):
            for i, where in ((s.p0_port, 0.0), (s.port, None), (s.p1_port, 1.0)):
                if i is not None:
                    assert i not in placed, f"{parity} {u}: port {i} placed twice"
                    placed[i] = (j, where)
        assert sorted(placed) == list(range(len(u))), f"{parity} {u}: {plan.spans}"
        last = len(plan.spans) - 1
        for i, (j, where) in placed.items():
            if u[i] == 0.0:
                assert (j, where) == (0, 0.0), f"{parity} {u}: port {i} at {where}"
            elif u[i] == 1.0:
                assert (j, where) == (last, 1.0), f"{parity} {u}: port {i} at {where}"
            else:
                assert where is None, f"{parity} {u}: interior port {i} at {where}"
