"""The `momwire.networks` shim (momwire#456 ws2 phase B).

`antennaknobs.network` and `antennaknobs.network_reduce` are compatibility
re-exports over the circuit spec and network solve that moved down into
momwire. These tests pin the two properties that make the move invisible to
the ~40 design modules and ~50 test modules importing through them:

* every re-exported name IS the momwire object, not a copy — a second class
  object would break every `isinstance` in the engines;
* the hierarchy `Network` that stayed behind is a SUBCLASS of the flat one,
  so `isinstance(net, momwire.networks.Network)` holds for what antennaknobs
  builds while `Composite`/`Instance` flattening stays app-side.

The behavioural half — that flattening still namespaces, aliases and
attributes correctly — is `tests/test_composite_network.py`, which this file
deliberately does not duplicate.
"""

import dataclasses

import momwire.networks as mw
import pytest

import antennaknobs.network as akn
import antennaknobs.network_reduce as akr

SPEC_NAMES = [
    "TL",
    "Load",
    "TwoPort",
    "Shunt",
    "Transformer",
    "Autotransformer",
    "Admittance",
    "BalancedLine",
    "FloatingBalun",
    "TouchstoneLoad",
    "TouchstoneTwoPort",
    "Branch",
    "Port",
    "Source",
    "Cable",
    "AdmittanceData",
    "Driven",
    "DrivenCurrent",
    "PortOnWire",
    "PortOnWireFloating",
    "PortAtEdge",
    "PortAtEnd",
    "PortAtVertex",
    "PortVirtual",
    "load_impedance",
    "load_series_admittance",
]

PRIVATE_NAMES = [
    "_branch_port_refs",
    "_rewrite_branch",
    "_series_rlc_impedance",
    "_parallel_rlc_admittance",
]


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_network_reexports_are_the_momwire_object(name):
    assert getattr(akn, name) is getattr(mw, name)


@pytest.mark.parametrize("name", PRIVATE_NAMES)
def test_private_helpers_still_importable_from_network(name):
    """They were reachable here before the move; the shim keeps them so the
    move PR did not have to churn their callers."""
    assert getattr(akn, name).__module__.startswith("momwire.networks")


@pytest.mark.parametrize("name", akr.__all__)
def test_network_reduce_reexports_are_the_momwire_object(name):
    assert getattr(akr, name) is getattr(mw, name)


def test_hierarchy_network_subclasses_the_flat_one():
    assert issubclass(akn.Network, mw.Network)
    assert akn.Network is not mw.Network


def test_a_built_network_is_a_momwire_network():
    net = akn.Network(
        ports={"ant": akn.PortOnWire("ant")},
        sources=[akn.Driven("ant")],
    )
    assert isinstance(net, mw.Network)
    assert isinstance(net, akn.Network)
    assert net.branch_paths == []


def test_branch_paths_stays_derived_not_passed():
    """The parent takes branch_paths as an ordinary field (antennaknobs
    flattens and hands it down); here it is computed by flattening, so
    passing one is still refused."""
    with pytest.raises(ValueError, match="branch_paths is derived"):
        akn.Network(
            ports={"ant": akn.PortOnWire("ant")},
            sources=[akn.Driven("ant")],
            branch_paths=["nope"],
        )


def test_flattening_fills_branch_paths_before_the_parent_validates():
    """One Instance, one top-level branch: the parent's flat validation sees
    the expanded branches AND a branch_paths aligned to them — it would raise
    on a length mismatch, and reject the namespaced internal node if the
    expansion had not declared it."""
    box = akn.Composite(
        ports=("a", "b"),
        branches=(akn.TwoPort("a", "m", r=10.0), akn.TwoPort("m", "b", r=20.0)),
    )
    net = akn.Network(
        ports={
            "ant": akn.PortOnWire("ant"),
            "rig": akn.PortVirtual("rig"),
        },
        branches=[
            akn.Instance("box", box, a="rig", b="ant"),
            akn.Shunt("ant", r=1000.0),
        ],
        sources=[akn.Driven("rig")],
    )
    assert net.branch_paths == ["box.", "box.", ""]
    assert len(net.branch_paths) == len(net.branches)
    assert net.ports["box.m"] == akn.PortVirtual("box.m")
    assert net.composites == {"box.": box}


def test_field_order_is_the_parents_then_composites():
    """Subclassing appends; it must not reorder. Positional construction and
    `dataclasses.replace` both read this order, and `composites` staying last
    is what keeps the pre-move signature intact."""
    assert [f.name for f in dataclasses.fields(akn.Network)] == [
        "ports",
        "branches",
        "sources",
        "branch_paths",
        "composites",
    ]
    assert [f.name for f in dataclasses.fields(mw.Network)] == [
        "ports",
        "branches",
        "sources",
        "branch_paths",
    ]


def test_replace_on_a_flat_momwire_network_round_trips():
    """The flat parent takes branch_paths as data, so `replace` works there —
    which is what antennaknobs' own flattening hands down."""
    flat = mw.Network(
        ports={"ant": mw.PortOnWire("ant"), "rig": mw.PortVirtual("rig")},
        branches=[mw.TwoPort("rig", "ant", r=10.0)],
        sources=[mw.Driven("rig")],
        branch_paths=["box."],
    )
    again = dataclasses.replace(flat, sources=[mw.Driven("rig", voltage=2 + 0j)])
    assert again.branch_paths == ["box."]
    assert again.sources[0].voltage == 2 + 0j


def test_cable_catalog_resolution_lives_in_antennaknobs():
    cable = akn.cable_from_catalog("RG-8X")
    assert isinstance(cable, mw.Cable)
    assert akn.TL.from_cable(cable, "rig", "ant", 30.48).z0 == cable.z0
