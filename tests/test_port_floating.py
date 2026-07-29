"""`PortOnWireFloating` — a gap port with BOTH terminals exposed as nodes.

An ordinary `PortOnWire` is stamped node-to-datum: its second terminal is
bonded to the common return (`network_reduce`'s "every port's second terminal
is bonded to it"). That is a stamping convention, not physics — the MoM only
ever knows gap voltage and gap current. This port type drops the bond and
exposes both sides as dotted sub-nodes `"<name>.p"` / `"<name>.n"`.

The load-bearing property is that it needs nothing from the SOLVER — only the
shared reducer's stamp changes, from `G[:n,:n] = Y` to the congruence `AᵀYA`.
So unlike `PortAtEnd` it works on every engine, which the equivalence test
below checks on momwire and PyNEC alike.

Prior art: SimNEC's `NECSource({w1,w2}, wire, percent)` takes two arbitrary
circuit nets; its Ruthroff/Guanella balun sample runs the two sides of one
antenna gap into two *different* choke inductors — the case a node-to-datum
port cannot express at all.
"""

from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.pynec import PyNECEngine
from antennaknobs.network import (
    TL,
    Driven,
    Network,
    PortOnWire,
    PortOnWireFloating,
    PortVirtual,
    Shunt,
    Wire,
)

WL = 299.792458 / 14.0


class _Doublet(AntennaBuilder):
    """Half-wave doublet fed through 7 m of 450 Ω line. ``floating`` swaps the
    gap port between the two kinds; the floating build additionally shorts its
    "-" terminal to the datum, which must make the two IDENTICAL."""

    default_params = MappingProxyType(
        {"design_freq": 14.0, "freq": 14.0, "floating": 0}
    )

    def build_wires(self):
        a = 0.25 * WL
        return [
            Wire((0, -a, 10), (0, -0.05, 10)),
            Wire((0, -0.05, 10), (0, 0.05, 10), name="feed"),
            Wire((0, 0.05, 10), (0, a, 10)),
        ]

    def build_network(self):
        fl = bool(self.floating)
        cls = PortOnWireFloating if fl else PortOnWire
        branches = [TL(a="rig", b="feed.p" if fl else "feed", z0=450.0, length=7.0)]
        if fl:
            branches.append(Shunt(port="feed.n", l=0.0))  # ideal short to datum
        return Network(
            ports={"feed": cls("feed"), "rig": PortVirtual("rig")},
            branches=branches,
            sources=[Driven(port="rig")],
        )


def _z(engine_cls, floating):
    b = _Doublet(dict(_Doublet.default_params, floating=int(floating)))
    return complex(engine_cls(b, ground=None).impedance()[0])


@pytest.mark.parametrize(
    "engine_cls", [MomwireEngine, PyNECEngine], ids=["momwire", "pynec"]
)
def test_floating_port_with_shorted_return_equals_grounded_port(engine_cls):
    """The reducer's correctness oracle: bonding the floating port's "-"
    terminal to the datum reproduces the node-to-datum stamp EXACTLY, because
    the congruence AᵀYA degenerates to the historical `G[:n,:n] = Y` when the
    "-" node is the datum. Measured 2026-07-29 to ~1e-13 on both engines
    (momwire 239.147 - 617.142j, PyNEC 229.745 - 632.761j).

    Running on PyNEC is the point: this port type asks nothing of the solver,
    so it carries none of `PortAtEnd`'s engine-parity break."""
    z_grounded = _z(engine_cls, False)
    z_floating = _z(engine_cls, True)
    assert abs(z_floating - z_grounded) < 1e-9 * abs(z_grounded)


class _SplitTerminals(_Doublet):
    """The case a node-to-datum port cannot express at all: the gap's two
    terminals go to two DIFFERENT branches (SimNEC's Guanella sample runs them
    into two separate choke inductors). Here each side gets its own line back
    to a common rig node, which is what makes the network CM-determinate."""

    def build_network(self):
        return Network(
            ports={
                "feed": PortOnWireFloating("feed"),
                "rig": PortVirtual("rig"),
            },
            branches=[
                TL(a="rig", b="feed.p", z0=450.0, length=7.0),
                TL(a="rig", b="feed.n", z0=450.0, length=7.2),
            ],
            sources=[Driven(port="rig")],
        )


def test_two_terminals_may_drive_different_branches():
    z = complex(MomwireEngine(_SplitTerminals(), ground=None).impedance()[0])
    assert abs(z) > 0 and z.real == z.real  # solved, finite, not NaN


def test_bare_port_name_is_not_a_node():
    """Addressing a floating port by its bare name is an authoring error — it
    has two terminals and no single node."""

    class Bad(_Doublet):
        def build_network(self):
            return Network(
                ports={
                    "feed": PortOnWireFloating("feed"),
                    "rig": PortVirtual("rig"),
                },
                branches=[TL(a="rig", b="feed", z0=450.0, length=7.0)],
                sources=[Driven(port="rig")],
            )

    with pytest.raises(ValueError, match="unknown port"):
        Bad().build_network()


def test_driving_a_floating_port_is_rejected():
    """v1 scope: a floating gap is an attachment point, not a drive point —
    driving it is ambiguous (which terminal is the reference?). Drive through
    the network instead, as SimNEC's samples do. Caught at authoring time by
    `Network`, so it never reaches an engine."""

    class Bad(_Doublet):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWireFloating("feed")},
                branches=[],
                sources=[Driven(port="feed")],
            )

    with pytest.raises(ValueError, match="attachment point, not a drive point"):
        Bad().build_network()


def test_physical_port_voltage_is_the_drop_across_the_gap():
    """Regression: the excited far-field/current solve must be driven with the
    gap voltage `v[p] - v[n]`, not the "+" node against a datum the port is
    deliberately not bonded to.

    Getting this wrong under-drives the antenna SILENTLY — the driven-point
    impedance reads off the termination branch and stays correct, so SWR and
    the power budget look fine while the radiated field is wrong. It surfaced
    as `wire.doublet_balanced_tuner` reporting -3.46 dBi for a 0.72 lambda
    free-space doublet (correct: +2.56 dBi).

    Oracle: the floating build with its "-" terminal shorted to the datum must
    match the grounded build's FAR FIELD, not merely its impedance."""
    ff = {}
    for floating in (False, True):
        b = _Doublet(dict(_Doublet.default_params, floating=int(floating)))
        eng = MomwireEngine(b, ground=None)
        eng.impedance()
        pat = eng.far_field(n_theta=45, n_phi=72, del_theta=2, del_phi=5)
        ff[floating] = max(max(r) for r in pat.rings)
    assert abs(ff[True] - ff[False]) < 1e-6, ff
