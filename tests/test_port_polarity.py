"""Port sign convention follows the AUTHORED wire direction (issue #580).

`flat_wires_to_polylines` walks the wire graph from boundary nodes; a port
edge's delta-gap sign convention (EMF direction / positive-current
direction) follows the polyline walk. Pre-fix the authored p0->p1 direction
of a named tuple was discarded, so each port's polarity was a traversal
accident — benign for single-feed designs, load-bearing whenever RELATIVE
polarity between ports matters (a TL between two ports with one polarity
flipped is exactly a hidden `transposed` toggle; BalancedLine crossover
wiring presupposes polarity control). PyNEC always honored the authored
direction (each tuple is its own GW card; NEC's EX drive and current
readout follow the card direction), so this was also a live cross-engine
disagreement on walker-reversed port edges.

The fix: the translator reports `feed_dirs` (+1 when the walk traversed the
tuple p0->p1, -1 when reversed) and MomwireEngine folds the sign into its
feed weight matrix W — the diagonal congruence Y_port = D.Y_walk.D with
V_walk = D.V_port. Contract: "the port's + terminal is toward p1."
"""

from types import MappingProxyType

import numpy as np

from antennaknobs import AntennaBuilder
from antennaknobs.geometry import flat_wires_to_polylines
from antennaknobs.network import TL, Driven, Network, PortOnWire, Wire

FREQ = 28.0
WL = 299.792458 / FREQ
ARM = 0.23 * WL
SEP = 0.15 * WL
GAP = 0.2


# ---------------------------------------------------------------------------
# 1. Translator: feed_dirs reports the walk direction relative to authoring
# ---------------------------------------------------------------------------


def _chain(feed_reversed=False):
    """Three collinear wires; the named port wire is embedded MID-CHAIN, so
    the walker threads through it (the case where the walk used to win)."""
    lo, hi = (0.0, 1.0, 0.0), (0.0, 2.0, 0.0)
    f0, f1 = (hi, lo) if feed_reversed else (lo, hi)
    return [
        ((0.0, 0.0, 0.0), lo, 5, None),
        Wire(f0, f1, 3, name="feed"),
        (hi, (0.0, 3.0, 0.0), 5, None),
    ]


def test_feed_dir_is_plus_one_when_walk_matches_authoring():
    out = flat_wires_to_polylines(_chain())
    assert out["feed_dirs"] == [1]


def test_feed_dir_is_minus_one_when_authored_against_the_walk():
    out = flat_wires_to_polylines(_chain(feed_reversed=True))
    assert out["feed_dirs"] == [-1]


def test_feed_dir_tracks_walk_reversal_from_registration_order():
    """Reversing the LIST order makes the walk start from the other chain
    end and traverse the (unchanged) authored feed tuple backwards; feed_dirs
    is exactly the record of that accident."""
    out = flat_wires_to_polylines(list(reversed(_chain())))
    assert out["feed_dirs"] == [-1]


def test_cycle_cut_port_edge_is_always_authored_direction():
    """The cycle-cut special case stacks the cut port edge [p0, p1] — the
    authored direction — so its feed_dir is +1 for either authoring."""
    a, b, c, d = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
    )
    loop = [
        Wire(a, b, 3, ex=1 + 0j, name="feed"),
        (b, c, 3, None),
        (c, d, 3, None),
        (d, a, 3, None),
    ]
    assert flat_wires_to_polylines(loop)["feed_dirs"] == [1]
    loop[0] = Wire(b, a, 3, ex=1 + 0j, name="feed")
    assert flat_wires_to_polylines(loop)["feed_dirs"] == [1]


# ---------------------------------------------------------------------------
# 2. Engine-level fixture: two coupled dipoles joined by a TL — relative
#    port polarity is observable in the driving-point impedance.
# ---------------------------------------------------------------------------


class _TwoDipolesTL(AntennaBuilder):
    """Parallel dipoles at x=0 ("fa", driven) and x=SEP ("fb"), joined by a
    TL. Each named feed wire sits mid-chain between two collinear arm wires.
    `flip_b` reverses the authored direction of fb's wire; `reorder_b` lists
    dipole b's wires in reverse order (which reverses the WALK through the
    unchanged authored tuples); `transposed` half-twists the TL."""

    default_params = MappingProxyType(
        {"freq": FREQ, "transposed": False, "flip_b": False, "reorder_b": False}
    )

    @staticmethod
    def _dipole(x, name, flip):
        lo, hi = (x, -GAP, 10.0), (x, GAP, 10.0)
        f0, f1 = (hi, lo) if flip else (lo, hi)
        return [
            Wire((x, -ARM, 10.0), lo, 15),
            Wire(f0, f1, 3, name=name),
            Wire(hi, (x, ARM, 10.0), 15),
        ]

    def build_wires(self):
        b = self._dipole(SEP, "fb", self.flip_b)
        if self.reorder_b:
            b = b[::-1]
        return self._dipole(0.0, "fa", False) + b

    def build_network(self):
        return Network(
            ports={"fa": PortOnWire("fa"), "fb": PortOnWire("fb")},
            branches=[
                TL(
                    a="fa",
                    b="fb",
                    z0=300.0,
                    length=0.31 * WL,
                    transposed=self.transposed,
                )
            ],
            sources=[Driven(port="fa", voltage=1 + 0j)],
        )


def _z_momwire(**kw):
    from antennaknobs.engines import MomwireEngine
    from momwire import SinusoidalSolver

    builder = _TwoDipolesTL(dict(_TwoDipolesTL.default_params, **kw))
    return complex(
        MomwireEngine(builder, solver=SinusoidalSolver, ground="free").impedance()[0]
    )


def _z_pynec(**kw):
    from antennaknobs.engines import PyNECEngine

    builder = _TwoDipolesTL(dict(_TwoDipolesTL.default_params, **kw))
    return complex(PyNECEngine(builder, ground="free").impedance()[0])


def test_polarity_is_observable():
    """Sanity for the fixture: the TL's half-twist changes Zin materially,
    so the tests below are actually exercising relative port polarity."""
    z_nt, z_t = _z_momwire(), _z_momwire(transposed=True)
    assert abs(z_t - z_nt) / abs(z_nt) > 0.1


def test_authored_direction_is_the_contract():
    """THE contract statement: reversing port b's authored wire direction is
    exactly the TL half-twist. Identical mesh — the two cases differ only by
    the diagonal sign congruence vs the transposed stamp, so they agree to
    machine precision."""
    z_twist = _z_momwire(transposed=True)
    z_flip = _z_momwire(flip_b=True)
    np.testing.assert_allclose(
        [z_flip.real, z_flip.imag], [z_twist.real, z_twist.imag], rtol=1e-12
    )
    # And flipping BOTH knobs lands back on the untwisted answer.
    z_both = _z_momwire(flip_b=True, transposed=True)
    z_base = _z_momwire()
    np.testing.assert_allclose(
        [z_both.real, z_both.imag], [z_base.real, z_base.imag], rtol=1e-12
    )


def test_walk_invariance_under_wire_list_reorder():
    """Reordering build_wires() reverses the walk through dipole b's
    mid-chain port wire but changes NO authored direction — the result must
    not move (pre-fix this silently toggled the TL's polarity). The mesh is
    assembled in a different order, so near-machine rather than exact."""
    z_base = _z_momwire()
    z_re = _z_momwire(reorder_b=True)
    np.testing.assert_allclose(
        [z_re.real, z_re.imag], [z_base.real, z_base.imag], rtol=1e-8
    )
    # Same invariance with the authored flip in play.
    z_flip = _z_momwire(flip_b=True)
    z_flip_re = _z_momwire(flip_b=True, reorder_b=True)
    np.testing.assert_allclose(
        [z_flip_re.real, z_flip_re.imag], [z_flip.real, z_flip.imag], rtol=1e-8
    )


def test_cross_engine_polarity_agrees():
    """PyNEC always honored the authored direction (GW cards are authored
    p0->p1; EX and current readouts follow the card). Pre-fix momwire
    followed the walker instead, so flip_b disagreed cross-engine by ~66%
    on this fixture. Post-fix both engines agree to MoM-basis tolerance on
    every polarity-sensitive variant (pattern of
    test_balanced_line_cross_engine_agrees)."""
    for kw in ({"flip_b": True}, {"flip_b": True, "transposed": True}):
        z_mw = _z_momwire(**kw)
        z_py = _z_pynec(**kw)
        assert abs(z_py - z_mw) / abs(z_mw) < 0.02, kw


def test_pynec_authored_contract_holds():
    """Lock the same contract on PyNEC: authored flip == TL half-twist
    (bit-identical NEC decks up to the swapped card endpoints)."""
    z_twist = _z_pynec(transposed=True)
    z_flip = _z_pynec(flip_b=True)
    np.testing.assert_allclose(
        [z_flip.real, z_flip.imag], [z_twist.real, z_twist.imag], rtol=1e-9
    )
