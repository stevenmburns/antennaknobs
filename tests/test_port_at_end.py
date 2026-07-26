"""PortAtEnd (issue #579) — junction-node ports at conductor ends.

A `PortAtEnd(wire_name, end)` resolves to the NODE at a wire's authored
endpoint: geometry translation forces a polyline boundary there and momwire
hosts a junction port (momwire#172 — the node's KCL row becomes the port's
drive/readout vector). This is the attachment a floating multi-terminal
element needs and a `PortOnWire` gap cannot provide (issue #576 mapped the
dead-end-stub and bridge-idiom failure modes).

The physics oracle here is the previously-IMPOSSIBLE case: a BalancedLine
feeding a dipole through end ports at the arm roots. With stub attachment
this read as an open line (zdiff-insensitive, −j336 Ω); through end ports it
must match ideal transmission-line theory — the same load must be recovered
through different zdiff values, and an off-quarter-wave length must land on
the TL transform formula.
"""

import cmath
from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.geometry import flat_wires_to_polylines
from antennaknobs.network import (
    BalancedLine,
    Driven,
    Network,
    PortAtEnd,
    PortOnWire,
    PortVirtual,
    Wire,
)

FREQ = 28.47
WL = 299.792458 / FREQ
ARM = 0.24 * WL
SPACING = 0.042


# ---------------------------------------------------------------------------
# geometry translation
# ---------------------------------------------------------------------------


def test_end_port_synthesizes_lone_end_junction():
    out = flat_wires_to_polylines(
        [
            Wire((0, 0, 0), (0, 1, 0), n_seg=5, name="a"),
            Wire((0, 1, 0), (0, 2, 0), n_seg=5, ex=1 + 0j),
        ],
        end_ports=[("a", "p0")],
    )
    # the two collinear wires chain into one polyline whose start hosts a
    # 1-entry junction group; the name registered no gap feed
    assert out["junctions"] == [[(0, "start")]]
    assert out["end_port_junctions"] == {("a", "p0"): 0}
    assert out["feed_names"] == [None]


def test_end_port_splits_mid_chain_node_into_two_entry_junction():
    out = flat_wires_to_polylines(
        [
            Wire((0, 0, 0), (0, 1, 0), n_seg=5, name="a"),
            Wire((0, 1, 0), (0, 2, 0), n_seg=5, ex=1 + 0j),
        ],
        end_ports=[("a", "p1")],
    )
    # the shared node is forced to be a boundary: two polylines meet there
    # and KCL still carries the current through
    j = out["end_port_junctions"][("a", "p1")]
    assert len(out["junctions"][j]) == 2


def test_end_port_unknown_or_ambiguous_name_rejected():
    wires = [Wire((0, 0, 0), (0, 1, 0), n_seg=5, ex=1 + 0j)]
    with pytest.raises(ValueError, match="no build_wires"):
        flat_wires_to_polylines(wires, end_ports=[("nope", "p0")])
    dup = [
        Wire((0, 0, 0), (0, 1, 0), n_seg=5, name="a"),
        Wire((1, 0, 0), (1, 1, 0), n_seg=5, name="a"),
        Wire((2, 0, 0), (2, 1, 0), n_seg=5, ex=1 + 0j),
    ]
    with pytest.raises(ValueError, match="unique"):
        flat_wires_to_polylines(dup, end_ports=[("a", "p0")])


def test_port_at_end_validates_end_token():
    with pytest.raises(ValueError, match="'p0' or 'p1'"):
        PortAtEnd("w", end="start")


# ---------------------------------------------------------------------------
# the physics oracle: BalancedLine-fed dipole through end ports
# ---------------------------------------------------------------------------


class _BLDipole(AntennaBuilder):
    """Two separated dipole arms fed through a BalancedLine whose far end is
    a differentially-driven virtual pair — the exact testbed that was blocked
    by stub attachment in #576's validation."""

    default_params = MappingProxyType(
        {
            "design_freq": FREQ,
            "freq": FREQ,
            "zd": 500.0,
            "blen": 0.25 * WL,
        }
    )

    def build_wires(self):
        s = SPACING
        z = 0.25 * WL
        return [
            Wire((0, 0, z), (0, -ARM, z), name="armA"),
            Wire((s, 0, z), (s, ARM, z), name="armB"),
        ]

    def build_network(self):
        return Network(
            ports={
                "ta": PortAtEnd("armA", end="p0"),
                "tb": PortAtEnd("armB", end="p0"),
                "s1": PortVirtual("s1"),
                "s2": PortVirtual("s2"),
            },
            branches=[
                BalancedLine(
                    a1="s1", a2="s2", b1="ta", b2="tb", zdiff=self.zd, length=self.blen
                )  # fmt: skip
            ],
            sources=[
                Driven(port="s1", voltage=0.5 + 0j),
                Driven(port="s2", voltage=-0.5 + 0j),
            ],
        )


def _zdiff_in(zd, blen):
    from antennaknobs.engines.momwire import MomwireEngine

    b = _BLDipole(dict(_BLDipole.default_params, zd=zd, blen=blen))
    eng = MomwireEngine(b, ground=None)
    return 2 * complex(eng.impedance()[0])


@pytest.mark.antenna_computation_check
def test_balanced_line_through_end_ports_obeys_tl_theory():
    """Quarter-wave transform recovers the SAME physical load through two
    different zdiff values (Z_L = zdiff²/Z_in), the load is the expected
    dipole-class impedance, and an off-quarter length lands on the full TL
    transform formula with that load. Stub attachment failed every one of
    these (zdiff-insensitive open-line signature)."""
    lq = 0.25 * WL
    z500 = _zdiff_in(500.0, lq)
    z200 = _zdiff_in(200.0, lq)
    zl_a = 500.0**2 / z500
    zl_b = 200.0**2 / z200
    assert abs(zl_a - zl_b) / abs(zl_a) < 0.02  # same load either way
    assert 50.0 < zl_a.real < 90.0  # a dipole, not an open

    l15 = 0.15 * WL
    z15 = _zdiff_in(500.0, l15)
    t = cmath.tan(2 * cmath.pi * l15 / WL)
    expect = 500.0 * (zl_a + 1j * 500.0 * t) / (500.0 + 1j * zl_a * t)
    assert abs(z15 - expect) / abs(expect) < 0.02


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


def test_pynec_rejects_port_at_end():
    from antennaknobs.engines.pynec import PyNECEngine

    with pytest.raises(ValueError, match="momwire"):
        PyNECEngine(_BLDipole())


def test_wire_name_shared_between_port_kinds_rejected():
    class B(_BLDipole):
        def build_network(self):
            net = super().build_network()
            ports = dict(net.ports)
            ports["armA"] = PortOnWire("armA")
            return Network(
                ports=ports, branches=list(net.branches), sources=list(net.sources)
            )

    from antennaknobs.engines.momwire import MomwireEngine

    with pytest.raises(ValueError, match="both"):
        MomwireEngine(B())


def test_unreferenced_named_wire_still_rejected_alongside_end_ports():
    class B(_BLDipole):
        def build_wires(self):
            return super().build_wires() + [Wire((1, 0, 0), (1, 1, 0), name="stray")]

    from antennaknobs.engines.momwire import MomwireEngine

    with pytest.raises(ValueError, match="stray"):
        MomwireEngine(B())
