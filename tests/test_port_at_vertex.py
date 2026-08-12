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


def test_nec5_refuses_until_knot_mapping_lands(monkeypatch):
    """#898 piece 3 (the re-scoped #897) wires EX-at-knot; until then the
    refusal must name the port and the issue, not mumble about virtual
    ports. Any executable satisfies the constructor's exe gate — the
    refusal fires while the constructor resolves network sources, before
    anything runs."""
    from antennaknobs.engines.nec5 import NEC5Engine

    monkeypatch.setenv("NEC5_EXE", sys.executable)
    with pytest.raises(NotImplementedError, match="PortAtVertex"):
        NEC5Engine(_ApexDipole())
