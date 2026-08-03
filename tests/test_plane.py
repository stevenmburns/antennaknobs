"""Measurement-plane picking (issue #652, option c).

`driven_at` is a graph surgery with judgement in it — what counts as
"upstream of the plane", what survives the cut — so that is where the tests
are, plus one engine oracle pinning the semantics the module exists for:
plane = feed measures the BARE antenna, not the antenna with a dangling
open-ended coax on it.
"""

import importlib

import pytest

from antennaknobs.network import (
    TL,
    Driven,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
    TwoPort,
)
from antennaknobs.plane import driven_at, planes_of


def build(name):
    return importlib.import_module(f"antennaknobs.designs.{name}").Builder()


def _ports(**kinds):
    return {
        name: (PortOnWire(name) if kind == "real" else PortVirtual(name))
        for name, kind in kinds.items()
    }


def _tuner_line_net():
    """rig → [tuner: series C, shunt L, series C] → li → 600 Ω line → feed.

    "li" is a NAMED mid-chain port, so all three planes are pickable.
    """
    return Network(
        ports=_ports(feed="real", li="virt", m="virt", rig="virt"),
        branches=[
            TwoPort(a="rig", b="m", c=30e-12),
            Shunt(port="m", l=2.5e-6),
            TwoPort(a="m", b="li", c=500e-12),
            TL(a="li", b="feed", z0=600, length=20.0),
        ],
        sources=[Driven(port="rig", voltage=2 + 0j)],
    )


# ---------------------------------------------------------------------------
# the cut
# ---------------------------------------------------------------------------
def test_the_natural_plane_is_the_network_itself():
    net = _tuner_line_net()
    assert driven_at(net, "rig") is net


def test_planes_read_source_to_antenna():
    # Every named top-level port on the chain is a legitimate readout point,
    # in source → antenna order — including "m", the tuner's own tee node,
    # because this fixture NAMES it at top level. (A composite's interior
    # gets a dotted auto-name instead and is deliberately not offered.)
    assert planes_of(_tuner_line_net()) == ["rig", "m", "li", "feed"]


def test_a_mid_chain_plane_keeps_only_the_antenna_side():
    net = driven_at(_tuner_line_net(), "li")
    assert [type(b).__name__ for b in net.branches] == ["TL"]
    assert net.sources == [Driven(port="li", voltage=2 + 0j)]  # drive kept
    # The tuner's nodes are gone with it; the plane and the antenna stay.
    assert set(net.ports) == {"li", "feed"}


def test_the_feed_plane_is_the_bare_antenna():
    net = driven_at(_tuner_line_net(), "feed")
    assert net.branches == []
    assert set(net.ports) == {"feed"}
    assert net.sources == [Driven(port="feed", voltage=2 + 0j)]


def test_instance_paths_survive_the_cut():
    """branch_paths is derived-only on Network, so the surgery restores it —
    the power budget and the schematic group by it."""
    sta = build("verticals.stub_matched_vertical").build_network()
    assert any(p for p in sta.branch_paths)  # the design uses a composite
    cut = driven_at(sta, "feed")
    assert len(cut.branch_paths) == len(cut.branches)


def test_attachments_are_not_upstream_of_anything():
    """A trap is wired into the structure; no plane disconnects it."""
    net = build("multiband.trap_dipole").build_network()
    assert planes_of(net) == [net.sources[0].port]
    assert driven_at(net, net.sources[0].port) is net


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------
def test_an_unknown_port_is_refused():
    with pytest.raises(ValueError, match="no port named"):
        driven_at(_tuner_line_net(), "vna")


def test_a_floating_gap_is_not_a_plane():
    """`wire.doublet_balanced_tuner`'s feed is a floating pair — there is no
    reference terminal for a single-ended VNA to drive against."""
    net = build("wire.doublet_balanced_tuner").build_network()
    with pytest.raises(ValueError, match="floating gap"):
        driven_at(net, "feed")
    assert "feed" not in planes_of(net)


def test_a_multi_feed_drive_has_no_plane_to_move():
    net = build("arrays.bowtie4x4").build_network()
    assert planes_of(net) == []
    with pytest.raises(ValueError, match="multi-feed"):
        driven_at(net, "feed0")


# ---------------------------------------------------------------------------
# the physics the module exists for
# ---------------------------------------------------------------------------
def test_plane_feed_measures_the_bare_antenna_not_a_dangling_stub():
    """The issue sketched "just re-solve with Driven(port='feed')" — but
    moving the source alone leaves the coax as an open-ended stub hanging on
    the feedpoint, which is a different (and wrong) measurement. The prune
    is the difference between "VNA at the feedpoint, coax unscrewed" and
    "VNA at the feedpoint, coax dangling"."""
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.designs.dipoles.invvee_coax_station import Builder

    class AtFeed(Builder):
        def build_network(self):
            return driven_at(super().build_network(), "feed")

    class Dangling(Builder):
        def build_network(self):
            net = super().build_network()
            return Network(
                ports=dict(net.ports),
                branches=list(net.branches),
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

    class Bare(Builder):
        def build_network(self):
            net = super().build_network()
            return Network(
                ports={"feed": net.ports["feed"]},
                branches=[],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

    z_plane = MomwireEngine(AtFeed()).impedance()[0]
    z_bare = MomwireEngine(Bare()).impedance()[0]
    z_dangling = MomwireEngine(Dangling()).impedance()[0]
    z_rig = MomwireEngine(Builder()).impedance()[0]
    assert z_plane == pytest.approx(z_bare, rel=1e-12)
    assert abs(z_plane - z_dangling) > 1.0  # the stub loads the feedpoint
    assert abs(z_plane - z_rig) > 1.0  # and the rig plane is a third thing
