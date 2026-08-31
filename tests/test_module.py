"""Tests for the paired geometry+network Module layer (Suggestion B) and the
lattice() array front-end (Suggestion C).

The headline guarantee is the "crux" one: a feed's geometry wire name and its
network port name are produced by the SAME namespacing, so they are equal by
construction — never the two independently-typed f-strings the current array
designs rely on. The end-to-end test proves a network-driven lattice matches
the legacy ex-phasor builder to machine precision.
"""

import numpy as np
import pytest
from types import MappingProxyType

from antennaknobs import (
    AntennaBuilder,
    Cell,
    Module,
    ModuleInstance,
    Transform,
    Wire,
    expand_modules,
    lattice,
)
from antennaknobs.builder import _shift_entry
from antennaknobs.network import Driven, Network, PortAtEnd, PortOnWire, PortVirtual, TL


def _bowtie_cell():
    from antennaknobs.designs.specialty import bowtie

    ew = bowtie.Builder().build_wires()
    # name the ex-carrying feed edge and drop the inline excitation (the port
    # drives it now).
    cw = [w._replace(name="feed", ex=None) if w.ex is not None else w for w in ew]
    return Cell(feeds=("feed",), wires=cw), ew


def _bowtie_module():
    cell, _ = _bowtie_cell()
    return Module(cell=cell, ports={"feed": PortOnWire("feed")})


# --------------------------------------------------------------------------
# the crux: one name, both faces
# --------------------------------------------------------------------------
def test_feed_port_name_equals_wire_name_by_construction():
    a = expand_modules(lattice(_bowtie_module(), nx=2, nz=2, dy=4, dz=4))
    wire_names = {w.name for w in a.wires} - {None}
    assert set(a.feeds) <= wire_names, "a feed port must name an actual wire"
    assert len(a.feeds) == len(set(a.feeds)) == 4
    assert a.feeds == ["e0_0.feed", "e0_1.feed", "e1_0.feed", "e1_1.feed"]


def test_design_never_types_a_per_element_name():
    """A design drives the array off assembly.feeds — no hand-derived strings."""
    a = expand_modules(lattice(_bowtie_module(), nx=2, nz=1, dy=4, dz=4))
    net = Network(
        ports=a.ports,
        branches=a.branches,
        sources=[Driven(port=f) for f in a.feeds],  # <- the only place feeds are used
    )
    assert set(net.ports) == {"e0_0.feed", "e1_0.feed"}


# --------------------------------------------------------------------------
# end-to-end physics: network lattice == legacy ex-phasor builder
# --------------------------------------------------------------------------
def test_lattice_4x4_network_matches_ex_based_impedance():
    from antennaknobs.engines import MomwireEngine
    from antennaknobs.designs.specialty import bowtie

    class ModArray(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.47, "design_freq": 28.47})

        def _els(self):
            return lattice(_bowtie_module(), nx=4, nz=4, dy=4.0, dz=4.0)

        def build_wires(self):
            return expand_modules(self._els()).wires

        def build_network(self):
            a = expand_modules(self._els())
            return Network(
                ports=a.ports,
                branches=a.branches,
                sources=[Driven(port=f) for f in a.feeds],
            )

    class ExArray(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.47, "design_freq": 28.47})

        def build_wires(self):
            ew = bowtie.Builder().build_wires()
            out = []
            for i in range(4):
                for j in range(4):
                    yoff, zoff = (i - 1.5) * 4.0, (j - 1.5) * 4.0
                    out.extend(_shift_entry(w, yoff, zoff, lambda ex: ex) for w in ew)
            return out

    z_mod = np.array(MomwireEngine(ModArray()).impedance())
    z_ex = np.array(MomwireEngine(ExArray()).impedance())
    assert len(z_mod) == len(z_ex) == 16
    rel = np.abs(z_mod - z_ex) / np.abs(z_ex)
    # the network path (PortOnWire + Driven) and the ex delta-gap are the same
    # feed — agreement is machine precision, not a physics tolerance.
    assert rel.max() < 1e-9, rel


def test_lattice_geometry_matches_manual_shift_entry_grid():
    from antennaknobs.designs.specialty import bowtie

    ew = bowtie.Builder().build_wires()
    a = expand_modules(lattice(_bowtie_module(), nx=3, nz=2, dy=4.0, dz=5.0))

    manual = []
    for i in range(3):
        for j in range(2):
            yoff, zoff = (i - 1.0) * 4.0, (j - 0.5) * 5.0
            manual.extend(_shift_entry(w, yoff, zoff, lambda ex: ex) for w in ew)

    assert len(a.wires) == len(manual) == 6 * len(ew)
    for p, m in zip(a.wires, manual, strict=True):
        assert p.p0 == pytest.approx(m.p0)
        assert p.p1 == pytest.approx(m.p1)


# --------------------------------------------------------------------------
# terminals — the manifold connection, bound like an Instance port map
# --------------------------------------------------------------------------
def test_terminal_binding_namespaces_feed_and_binds_terminal():
    cell = Cell(feeds=("feed",), wires=[Wire((0, -1, 5), (0, 1, 5), name="feed")])
    mod = Module(
        cell=cell,
        ports={"feed": PortOnWire("feed")},
        terminals=("drv",),
        branches=(TL(a="feed", b="drv", z0=100.0, length=1.0),),
    )
    a = expand_modules(
        [
            ModuleInstance("e0", mod, Transform.translate(0, 0, 0), drv="drv"),
            ModuleInstance("e1", mod, Transform.translate(0, 5, 0), drv="drv"),
        ]
    )
    # feed ports are namespaced; the shared terminal binds to the common node
    assert set(a.ports) == {"e0.feed", "e1.feed"}
    tls = [b for b in a.branches if isinstance(b, TL)]
    assert {(b.a, b.b) for b in tls} == {("e0.feed", "drv"), ("e1.feed", "drv")}


def test_lattice_bind_supplies_terminal_map():
    cell = Cell(feeds=("feed",), wires=[Wire((0, -1, 5), (0, 1, 5), name="feed")])
    mod = Module(
        cell=cell,
        ports={"feed": PortOnWire("feed")},
        terminals=("drv",),
        branches=(TL(a="feed", b="drv", z0=50.0, length=0.5),),
    )
    insts = lattice(mod, nx=2, nz=2, dy=3, dz=3, bind=lambda i, j: {"drv": "drv"})
    a = expand_modules(insts)
    assert all(b.b == "drv" for b in a.branches)
    assert len(a.ports) == 4


def test_port_at_end_feed_is_supported():
    cell = Cell(feeds=("feedL",), wires=[Wire((0, 0, 0), (0, 2, 0), name="feedL")])
    mod = Module(cell=cell, ports={"eL": PortAtEnd("feedL", end="p1")})
    a = expand_modules([ModuleInstance("e0", mod)])
    assert isinstance(a.ports["e0.eL"], PortAtEnd)
    assert a.ports["e0.eL"].wire == "e0.feedL"  # geometry name namespaced too
    assert a.feeds == ["e0.eL"]


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
def test_module_rejects_portonwire_key_name_mismatch():
    cell = Cell(feeds=("feed",), wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")])
    with pytest.raises(ValueError, match="must equal PortOnWire name"):
        Module(cell=cell, ports={"wrong": PortOnWire("feed")})


def test_module_rejects_feed_port_naming_no_cell_feed():
    cell = Cell(feeds=("feed",), wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")])
    with pytest.raises(ValueError, match="names no cell feed"):
        Module(cell=cell, ports={"ghost": PortOnWire("ghost")})


def test_module_rejects_branch_referencing_unknown_node():
    cell = Cell(feeds=("feed",), wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")])
    with pytest.raises(ValueError, match="not a module port or terminal"):
        Module(
            cell=cell,
            ports={"feed": PortOnWire("feed")},
            branches=(TL(a="feed", b="nowhere", z0=50, length=1.0),),
        )


def test_module_internal_virtual_node_is_allowed():
    cell = Cell(feeds=("feed",), wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")])
    mod = Module(
        cell=cell,
        ports={"feed": PortOnWire("feed"), "mid": PortVirtual("mid")},
        terminals=("drv",),
        branches=(
            TL(a="feed", b="mid", z0=50, length=0.3),
            TL(a="mid", b="drv", z0=50, length=0.3),
        ),
    )
    a = expand_modules([ModuleInstance("e0", mod, drv="drv")])
    assert isinstance(a.ports["e0.mid"], PortVirtual)
    assert a.feeds == ["e0.feed"]  # the virtual mid-node is not a feed


def test_instance_requires_all_terminals_bound():
    cell = Cell(feeds=("feed",), wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")])
    mod = Module(
        cell=cell,
        ports={"feed": PortOnWire("feed")},
        terminals=("drv",),
        branches=(TL(a="feed", b="drv", z0=50, length=1.0),),
    )
    with pytest.raises(ValueError, match="missing \\['drv'\\]"):
        ModuleInstance("e0", mod)  # forgot drv=...


def test_instance_name_with_dot_raises():
    with pytest.raises(ValueError, match="no '\\.'"):
        ModuleInstance("a.b", _bowtie_module())
