"""PortAtVertex (issue #898) — the series apex feed at a junction knot.

A `PortAtVertex(wire_name, end)` inserts a delta-gap voltage in the
current path THROUGH the node at the named wire's endpoint, in series
with that wire's connection to it: feeding an inverted vee at its exact
vertex, with no bridge wire. It resolves to momwire's series node gap
(momwire#305). Deliberately distinct from `PortAtEnd`, which is the
SHUNT junction port (momwire#172's KCL row): the two answer different
physics questions at the same node.

The physics oracle is the colinear identity momwire pins solver-side
(momwire's test_colinear_split_identity): a dipole split at its centre
and apex-fed must reproduce the ordinary centre-fed single wire through
the ENGINE path — translation, network reduction, excitation and all.
"""

import sys
from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.geometry import flat_wires_to_polylines
from antennaknobs.network import (
    Driven,
    Network,
    PortAtVertex,
    Wire,
)

FREQ = 27.0
WL = 299.792458 / FREQ
ARM = 2.6
NSEG = 16


# ---------------------------------------------------------------------------
# geometry translation: the member map
# ---------------------------------------------------------------------------


def test_end_port_members_names_the_polyline_end():
    out = flat_wires_to_polylines(
        [
            Wire((0, 0, 0), (0, 0, ARM), n_seg=NSEG, name="a"),
            Wire((0, 0, ARM), (0, 0, 2 * ARM), n_seg=NSEG, name="b"),
        ],
        end_ports=[("a", "p1"), ("b", "p0")],
    )
    members = out["end_port_members"]
    j = out["end_port_junctions"][("a", "p1")]
    group = out["junctions"][j]
    # both names resolve to members of the SAME two-entry junction group,
    # and to DIFFERENT members of it (each names its own wire's end)
    assert members[("a", "p1")] in group
    assert members[("b", "p0")] in group
    assert members[("a", "p1")] != members[("b", "p0")]
    assert len(group) == 2


def test_port_at_vertex_validates_end_token():
    with pytest.raises(ValueError, match="'p0' or 'p1'"):
        PortAtVertex("w", end="start")


# ---------------------------------------------------------------------------
# the engine-path oracle: apex-fed split dipole == centre-fed single wire
# ---------------------------------------------------------------------------


class _ApexDipole(AntennaBuilder):
    """A straight dipole spelled as two arm wires meeting at the origin
    end-to-end, fed at the shared vertex — no bridge wire, no gap cut.

    Only the port-referenced arm carries a name: an unreferenced name is
    an open gap by the #578 rule, so the degree-2 invariance variant names
    the OTHER arm instead of adding a second name."""

    default_params = MappingProxyType({"design_freq": FREQ, "freq": FREQ})

    # (which arm carries the name, which authored end the port names)
    vertex = (0, "p1")

    def build_wires(self):
        arm_idx, _end = self.vertex
        names = ["arm" if i == arm_idx else None for i in range(2)]
        return [
            Wire((0, 0, -ARM), (0, 0, 0), n_seg=NSEG, name=names[0]),
            Wire((0, 0, 0), (0, 0, ARM), n_seg=NSEG, name=names[1]),
        ]

    def build_network(self):
        _arm_idx, end = self.vertex
        return Network(
            ports={"apex": PortAtVertex("arm", end=end)},
            branches=[],
            sources=[Driven(port="apex", voltage=1 + 0j)],
        )


class _PlainDipole(AntennaBuilder):
    """The same conductor as one wire with the legacy centre feed."""

    default_params = MappingProxyType({"design_freq": FREQ, "freq": FREQ})

    def build_wires(self):
        return [Wire((0, 0, -ARM), (0, 0, ARM), n_seg=2 * NSEG, ex=1 + 0j)]


def _z(builder):
    from antennaknobs.engines.momwire import MomwireEngine

    return complex(MomwireEngine(builder, ground=None).impedance()[0])


@pytest.mark.antenna_computation_check
def test_apex_fed_split_matches_centre_fed_single_wire():
    """The momwire#300-class identity through the whole engine path.
    Measured 2026-08-12: ~0.5 Ω of split-node march term at this mesh."""
    za = _z(_ApexDipole())
    zp = _z(_PlainDipole())
    assert abs(za - zp) < 2.0, f"apex {za:.3f} vs plain {zp:.3f}"
    assert za.real > 0


@pytest.mark.antenna_computation_check
def test_vertex_wire_choice_is_immaterial_at_degree_two():
    """PortAtVertex('armA','p1') and PortAtVertex('armB','p0') name the
    same through-current port at a two-wire vertex (momwire#305)."""

    class _OtherArm(_ApexDipole):
        vertex = (1, "p0")

    assert abs(_z(_ApexDipole()) - _z(_OtherArm())) < 1e-6


# ---------------------------------------------------------------------------
# guards: the engines that cannot express it refuse by name
# ---------------------------------------------------------------------------


def test_pynec_rejects_port_at_vertex():
    from antennaknobs.engines.pynec import PyNECEngine

    with pytest.raises(ValueError, match="NEC-2 cannot represent"):
        PyNECEngine(_ApexDipole())


# ---------------------------------------------------------------------------
# NEC-5: the native EX-at-knot mapping (#898 piece 3, the re-scoped #897)
# ---------------------------------------------------------------------------


class _OddApex(_ApexDipole):
    """Odd arm counts: visible parity exemption — a vertex-only wire keeps
    its authored mesh because the source sits at an END knot."""

    def build_wires(self):
        arm_idx, _end = self.vertex
        names = ["arm" if i == arm_idx else None for i in range(2)]
        return [
            Wire((0, 0, -ARM), (0, 0, 0), n_seg=15, name=names[0]),
            Wire((0, 0, 0), (0, 0, ARM), n_seg=15, name=names[1]),
        ]


def test_nec5_maps_vertex_to_end_knot(monkeypatch):
    """The deck spells the apex as NEC-5's native knot source: EX at the
    named wire's own end (segment n_seg end 2 for p1 / segment 1 end 1
    for p0), and a vertex-only wire's authored ODD count survives — the
    even-parity coercion exists to put a knot mid-wire, which an end feed
    does not need."""
    from antennaknobs.engines.nec5 import NEC5Engine

    monkeypatch.setenv("NEC5_EXE", sys.executable)
    deck = NEC5Engine(_OddApex()).deck([FREQ])
    assert "GW 1 15 " in deck  # authored mesh kept (no even bump)
    assert "GW 2 15 " in deck
    assert "EX 0 1 15 2 " in deck  # arm p1: its own end knot

    class _P0(_OddApex):
        vertex = (1, "p0")

    deck = NEC5Engine(_P0()).deck([FREQ])
    assert "EX 0 2 1 1 " in deck  # arm p0: segment 1, end 1


def test_nec5_still_coerces_gap_fed_wires(monkeypatch):
    """The exemption is surgical: a centre-fed wire still needs its middle
    knot, so the even bump stays for everything that is not vertex-only."""
    from antennaknobs.engines.nec5 import NEC5Engine

    monkeypatch.setenv("NEC5_EXE", sys.executable)

    class _OddPlain(_PlainDipole):
        def build_wires(self):
            return [Wire((0, 0, -ARM), (0, 0, ARM), n_seg=31, ex=1 + 0j)]

    deck = NEC5Engine(_OddPlain()).deck([FREQ])
    assert "GW 1 32 " in deck
    assert "EX 0 1 16 2 " in deck


nec5_live = pytest.mark.skipif(
    __import__("antennaknobs.engines.nec5", fromlist=["find_nec5"]).find_nec5() is None,
    reason="licensed NEC-5 binary not configured (NEC5_EXE)",
)


def _apex_at(n):
    class _A(_ApexDipole):
        def build_wires(self):
            arm_idx, _end = self.vertex
            names = ["arm" if i == arm_idx else None for i in range(2)]
            return [
                Wire((0, 0, -ARM), (0, 0, 0), n_seg=n, name=names[0]),
                Wire((0, 0, 0), (0, 0, ARM), n_seg=n, name=names[1]),
            ]

    return _A()


@nec5_live
@pytest.mark.antenna_computation_check
def test_nec5_apex_feed_agrees_with_momwire():
    """The A/B the arc exists for: the same apex-fed split dipole through
    NEC-5's native knot source and momwire's series node gap.

    NEC-5's raw reading marches at O(1/N) — its own knot discretization,
    the momwire#890 finding — so the comparison uses the #872/#890 pair
    recipe: Richardson-extrapolate the (N, 2N) pair and compare THAT
    against momwire's nearly-stationary d=2 answer. Measured 2026-08-12:
    raw gaps 3.9/2.0/1.2 Ω at 16/32/64 per arm; the extrapolated pair
    lands 0.11 Ω from momwire."""
    from antennaknobs.engines.nec5 import NEC5Engine

    z32 = complex(NEC5Engine(_apex_at(32)).impedance()[0])
    z64 = complex(NEC5Engine(_apex_at(64)).impedance()[0])
    z5 = 2 * z64 - z32  # first-order Richardson on the O(1/N) march
    zm = _z(_apex_at(64))
    assert abs(z5 - zm) < 0.5, (
        f"NEC-5 pair {z5:.3f} (raw {z32:.3f} / {z64:.3f}) vs momwire {zm:.3f}"
    )
    # And the raw N=64 reading is inside the march-sized envelope — a
    # sign/addressing bug would blow this by an order of magnitude.
    assert abs(z64 - zm) < 2.0
