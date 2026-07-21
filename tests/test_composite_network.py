"""Composite network components (issue #489): expansion, namespacing,
aliasing, budget attribution, and stdlib-box equivalence oracles.

The design record lives in issue #489: composites follow the convergent
HCL-survey shape ("generators are code, modules are data") — factory
functions parameterize, `Instance` kwargs are the formal/actual port map,
expansion flattens at Network construction so engines only ever see plain
branches.
"""

import pytest

from antennaknobs.network import (
    TL,
    Composite,
    Driven,
    Instance,
    Load,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
    TwoPort,
)
from antennaknobs.station import bypass, t_network_tuner, unun


def _ports(**kinds):
    out = {}
    for name, kind in kinds.items():
        out[name] = PortOnWire(name) if kind == "real" else PortVirtual(name)
    return out


# ---------------------------------------------------------------------------
# expansion mechanics
# ---------------------------------------------------------------------------
def test_expansion_namespaces_internals_and_stamps_paths():
    net = Network(
        ports=_ports(feed="real", li="virt", rig="virt"),
        branches=[
            Instance(
                "tuner",
                t_network_tuner(c1_pF=30, c2_pF=500, l_uH=2.5, ql=200),
                rig="rig",
                out="li",
            ),
            TL(a="li", b="feed", z0=600, length=20.0),
        ],
        sources=[Driven(port="rig")],
    )
    # tee midpoint became a namespaced auto-declared virtual port
    assert isinstance(net.ports["tuner.m"], PortVirtual)
    assert net.branch_paths == ["tuner.", "tuner.", "tuner.", ""]
    # flattened branches reference final names
    tp1, sh, tp2, tl = net.branches
    assert (tp1.a, tp1.b) == ("rig", "tuner.m")
    assert sh.port == "tuner.m"
    assert (tp2.a, tp2.b) == ("tuner.m", "li")
    assert isinstance(tl, TL)


def test_nested_instances_compose_paths():
    box = Composite(
        ports=("rig", "ant"),
        branches=(
            Instance("un", unun(7.0, lmag_uH=8), line="mid", ant="ant"),
            TL(a="rig", b="mid", z0=50, length=5.0),
        ),
    )
    net = Network(
        ports=_ports(ant="real", rig="virt"),
        branches=[Instance("sta", box, rig="rig", ant="ant")],
        sources=[Driven(port="rig")],
    )
    assert "sta.mid" in net.ports
    assert net.branch_paths == ["sta.un.", "sta."]


def test_binding_one_actual_to_two_formals_fuses():
    # parent-side fan-in needs no aliasing: kwargs may repeat an actual
    box = Composite(ports=("a", "b"), branches=(TwoPort(a="a", b="b", r=50.0),))
    net = Network(
        ports=_ports(feed="real", n="virt"),
        branches=[Instance("x", box, a="n", b="n")],
        sources=[Driven(port="feed")],
    )
    (br,) = net.branches
    assert (br.a, br.b) == ("n", "n")


# ---------------------------------------------------------------------------
# aliasing
# ---------------------------------------------------------------------------
def test_bypass_merges_nodes_and_moves_source():
    net = Network(
        ports=_ports(feed="real", rig="virt"),
        branches=[Instance("t", bypass(), a="rig", b="feed")],
        sources=[Driven(port="rig", voltage=2 + 0j)],
    )
    # the virtual node folded into the real port; no branches remain
    assert set(net.ports) == {"feed"}
    assert net.branches == []
    assert net.sources == [Driven(port="feed", voltage=2 + 0j)]


def test_internal_fanout_to_two_formals():
    """One internal node surfacing under two formal names (the #489
    aliasing case 2): the whole class merges onto the real actual."""
    splitter = Composite(
        ports=("inp", "out_a", "out_b"),
        branches=(TwoPort(a="inp", b="n1", r=10.0),),
        aliases=(("n1", "out_a"), ("n1", "out_b")),
    )
    net = Network(
        ports=_ports(fa="real", vb="virt", rig="virt"),
        branches=[Instance("sp", splitter, inp="rig", out_a="fa", out_b="vb")],
        sources=[Driven(port="rig")],
    )
    (br,) = net.branches
    assert (br.a, br.b) == ("rig", "fa")  # canonical = the real port
    assert "vb" not in net.ports and "sp.n1" not in net.ports


def test_alias_two_real_ports_rejected():
    with pytest.raises(ValueError, match="geometry ports"):
        Network(
            ports=_ports(fa="real", fb="real", rig="virt"),
            branches=[Instance("t", bypass(), a="fa", b="fb")],
            sources=[Driven(port="rig")],
        )


def test_internal_alias_canonicalizes_to_external_name():
    # one internal node surfacing under one formal: canonical is the
    # bound (top-level) name, the internal name disappears
    box = Composite(
        ports=("inp", "out"),
        branches=(TwoPort(a="inp", b="n1", r=10.0),),
        aliases=(("n1", "out"),),
    )
    net = Network(
        ports=_ports(feed="real", rig="virt"),
        branches=[Instance("x", box, inp="rig", out="feed")],
        sources=[Driven(port="rig")],
    )
    (br,) = net.branches
    assert (br.a, br.b) == ("rig", "feed")
    assert "x.n1" not in net.ports


def test_conflicting_sources_after_merge_rejected():
    with pytest.raises(ValueError, match="conflicting sources"):
        Network(
            ports=_ports(feed="real", a="virt", b="virt"),
            branches=[
                Instance("t", bypass(), a="a", b="b"),
                TwoPort(a="b", b="feed", r=1.0),
            ],
            sources=[
                Driven(port="a", voltage=1 + 0j),
                Driven(port="b", voltage=2 + 0j),
            ],
        )


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def test_instance_portmap_must_cover_formals():
    box = bypass()
    with pytest.raises(ValueError, match="missing formals"):
        Instance("t", box, a="x")
    with pytest.raises(ValueError, match="unknown formals"):
        Instance("t", box, a="x", b="y", c="z")


def test_instance_name_rules():
    with pytest.raises(ValueError, match="no '.'"):
        Instance("a.b", bypass(), a="x", b="y")


def test_instance_actual_must_be_declared_port():
    with pytest.raises(ValueError, match="unknown port"):
        Network(
            ports=_ports(feed="real"),
            branches=[Instance("t", bypass(), a="feed", b="nope")],
            sources=[Driven(port="feed")],
        )


def test_composite_rejects_sources_in_body():
    with pytest.raises(ValueError, match="branches or Instances"):
        Composite(ports=("a",), branches=(Driven(port="a"),))


def test_top_level_typo_still_caught():
    # instance expansion must not weaken top-level port validation
    with pytest.raises(ValueError, match="unknown port"):
        Network(
            ports=_ports(feed="real"),
            branches=[Shunt(port="feeed", c=1e-12)],
            sources=[Driven(port="feed")],
        )


# ---------------------------------------------------------------------------
# solve-level equivalence + budget attribution (engine oracle)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def _tuner_engines():
    """The doublet_ladder_tuner design solved twice: hand-built branches
    (the pre-#489 idiom) vs the stdlib t_network_tuner instance."""
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.designs.wire.doublet_ladder_tuner import Builder

    class HandBuilt(Builder):
        def build_network(self):
            return Network(
                ports=_ports(feed="real", li="virt", m="virt", rig="virt"),
                branches=[
                    TL.from_cable("openwire-600", "li", "feed", self.line_len_m),
                    TwoPort(a="rig", b="m", c=self.series_c1_pF * 1e-12),
                    Shunt(
                        port="m",
                        l=self.shunt_l_uH * 1e-6,
                        ql=self.coil_q if self.coil_q > 0 else None,
                    ),
                    TwoPort(a="m", b="li", c=self.series_c2_pF * 1e-12),
                ],
                sources=[Driven(port="rig", voltage=1 + 0j)],
            )

    return MomwireEngine(Builder()), MomwireEngine(HandBuilt())


def test_stdlib_tuner_matches_hand_built(_tuner_engines):
    eng_box, eng_hand = _tuner_engines
    z_box, z_hand = eng_box.impedance()[0], eng_hand.impedance()[0]
    assert z_box == pytest.approx(z_hand, rel=1e-12)


def test_budget_rows_carry_instance_prefix(_tuner_engines):
    eng_box, _ = _tuner_engines
    eng_box.input_power()  # triggers the excited solve + budget
    labels = [label for label, _w in eng_box._excited_power_budget]
    assert any(label.startswith("tuner: ") for label in labels), labels
    # the box's own namespace is stripped inside its rows
    assert "tuner: Shunt m" in labels, labels


def test_bypass_equals_bare_antenna():
    """A bypassed matchbox is electrically absent: Z equals the bare
    antenna's driving-point Z exactly."""
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.designs.loops.skyloop_lmatch import Builder

    class Bypassed(Builder):
        def build_network(self):
            return Network(
                ports=_ports(feed="real", **{"in": "virt"}),
                branches=[Instance("match", bypass(), a="in", b="feed")],
                sources=[Driven(port="in", voltage=1 + 0j)],
            )

    class Bare(Builder):
        def build_network(self):
            return Network(
                ports=_ports(feed="real"),
                branches=[],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

    z_byp = MomwireEngine(Bypassed()).impedance()[0]
    z_bare = MomwireEngine(Bare()).impedance()[0]
    assert z_byp == pytest.approx(z_bare, rel=1e-12)


def test_l_network_zero_arms_is_passthrough():
    """The stdlib L-match with both arms at zero is inert (issue #285
    degenerate-endpoint physics carried through the composite)."""
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.designs.loops.skyloop_lmatch import Builder

    b = Builder(params=dict(Builder.default_params))
    b.series_L_uH = 0.0
    b.shunt_C_pF = 0.0
    z = MomwireEngine(b).impedance()[0]

    class Bare(Builder):
        def build_network(self):
            return Network(
                ports=_ports(feed="real"),
                branches=[],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

    z_bare = MomwireEngine(Bare()).impedance()[0]
    assert z == pytest.approx(z_bare, rel=1e-9)


def test_unun_pynec_boxed_equals_hand_built():
    """The composite path is engine-agnostic: on PyNEC's reducer path,
    challenger's unun instance solves identically to the same network
    written as raw branches (cross-engine physics is out of scope here —
    this oracles only the expansion)."""
    from antennaknobs.network import Transformer
    from antennaknobs.engines.pynec import PyNECEngine
    from antennaknobs.designs.verticals.challenger import Builder

    class HandBuilt(Builder):
        def build_network(self):
            return Network(
                ports=_ports(ant="real", rig="virt"),
                branches=[
                    Transformer(
                        a="rig",
                        b="ant",
                        n=1.0 / self.turns,
                        lmag=self.lmag_uH * 1e-6,
                        qlmag=self.qlmag if self.qlmag > 0 else None,
                    )
                ],
                sources=[Driven(port="rig", voltage=1 + 0j)],
            )

    z_box = PyNECEngine(Builder(), ground=None).impedance()[0]
    z_hand = PyNECEngine(HandBuilt(), ground=None).impedance()[0]
    assert z_box == pytest.approx(z_hand, rel=1e-9)


def test_load_inside_composite_on_real_port():
    """A Load in a composite body bound to a real port lands on the wire
    (the termination path), same as a top-level Load."""
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.designs.broadband.t2fd import Builder

    class Boxed(Builder):
        def build_network(self):
            term_box = Composite(
                ports=("t",), branches=(Load(port="t", r=self.term_r),)
            )
            return Network(
                ports=_ports(feed="real", term="real"),
                branches=[Instance("res", term_box, t="term")],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

    z_box = MomwireEngine(Boxed()).impedance()[0]
    z_ref = MomwireEngine(Builder()).impedance()[0]
    assert z_box == pytest.approx(z_ref, rel=1e-12)
