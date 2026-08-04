"""Network → schematic (issue #652).

The lowering is the part with judgement in it — which branches form the spine,
what hangs beneath it, and when an author's fragment replaces the defaults — so
that is where the tests are. Rendering is checked for "it produced an SVG";
schemdraw owns the pixels.
"""

import importlib

import pytest

import antennaknobs as ant
from antennaknobs.network import (
    Composite,
    Driven,
    FloatingBalun,
    Instance,
    Network,
    PortOnWire,
    PortOnWireFloating,
    PortVirtual,
    Shunt,
    TL,
)
from antennaknobs.schematic import (
    Element,
    lower,
    render_svg,
    retn,
    series,
    shunt,
    terminals_of,
)

has_schemdraw = pytest.importorskip


def build(name):
    return importlib.import_module(f"antennaknobs.designs.{name}").Builder()


def kinds(sch):
    return [(b.label, [(e.kind, e.orient) for e in b.elements]) for b in sch.blocks]


# ---------------------------------------------------------------------------
# lowering
# ---------------------------------------------------------------------------
def test_a_station_chain_lowers_source_to_antenna():
    sch = lower(build("dipoles.invvee_coax_station").build_network())
    assert sch.source == "rig"
    assert sch.ends_in_antenna
    assert kinds(sch) == [("TL", [("coax", "series")])]


def test_a_shunt_branch_hangs_beneath_the_spine():
    sch = lower(build("wire.efhw_sloper").build_network())
    orients = [e.orient for b in sch.blocks for e in b.elements]
    assert "series" in orients and "shunt" in orients


def test_a_stub_is_drawn_as_a_shunt_even_though_it_is_a_line():
    """A stub is a length of line used as a shunt; the rib's orientation comes
    from the topology, not from the branch type's own default."""
    sch = lower(build("verticals.stub_matched_vertical").build_network())
    (block,) = sch.blocks
    assert [e.orient for e in block.elements] == ["shunt", "series"]
    assert all(e.kind == "coax" for e in block.elements)


def test_branches_group_under_the_instance_they_came_from():
    sch = lower(build("wire.doublet_ladder_tuner").build_network())
    labels = [b.label for b in sch.blocks]
    assert "tuner" in labels  # the composite draws as one box, not three


def test_an_author_fragment_replaces_the_default_symbols():
    """The T-network's coil belongs BETWEEN its capacitors — an ordering the
    branch list cannot express and the author can."""
    sch = lower(build("wire.doublet_ladder_tuner").build_network())
    tuner = next(b for b in sch.blocks if b.label == "tuner")
    assert [e.kind for e in tuner.elements] == ["capacitor", "inductor", "capacitor"]
    assert [e.orient for e in tuner.elements] == ["series", "shunt", "series"]


def test_a_box_without_a_fragment_still_draws():
    """The fallback is the whole reason there is always a picture."""
    body = Composite(
        ports=("a", "b"), branches=(TL(a="a", b="b", z0=75.0, length=3.0),)
    )
    assert body.schematic is None
    net = Network(
        ports={"rig": PortVirtual("rig"), "far": PortVirtual("far")},
        branches=[Instance("mystery", body, a="rig", b="far")],
        sources=[Driven(port="rig")],
    )
    sch = lower(net)
    assert sch.blocks and sch.blocks[0].elements[0].kind == "coax"


def test_a_multi_feed_antenna_says_so_instead_of_drawing_a_chain():
    sch = lower(build("arrays.bowtie4x4").build_network())
    assert sch.blocks == []
    assert any("multi-feed" in n for n in sch.notes)


def test_one_terminal_loads_still_appear():
    """`multiband.trap_dipole` is all traps in the legs — no chain at all, but
    emphatically not nothing to draw. They are attachments rather than blocks:
    a trap is wired into the antenna, not between the rig and it."""
    sch = lower(build("multiband.trap_dipole").build_network())
    assert sch.blocks == []
    assert [a.nodes for a in sch.attachments] == [("trap_l",), ("trap_r",)]
    assert sch.ends_in_antenna  # the source is sitting on the antenna


def test_a_long_chain_keeps_its_order():
    """The chain is the LONGEST run that reaches an antenna, not the shortest.

    An LPDA's phasing line is nine sections between ten driven elements, so
    the first hop already lands on an antenna port — stopping there would draw
    one section and lose the other eight.
    """
    sch = lower(build("broadband.lpda").build_network())
    assert len(sch.blocks) == 9
    assert all(e.kind == "coax" for b in sch.blocks for e in b.elements)


def test_labels_carry_the_values():
    sch = lower(build("wire.doublet_ladder_tuner").build_network())
    text = " ".join(e.label for b in sch.blocks for e in b.elements)
    assert "pF" in text and "µH" in text and "Ω" in text


def test_power_annotates_the_blocks_that_burn():
    net = build("verticals.stub_matched_vertical").build_network()
    budget = [("match: TL rig→feed", 0.004), ("match.stub: TL rig→far", 0.001)]
    sch = lower(net, budget=budget)
    assert sch.blocks[0].watts == pytest.approx(0.005)
    # ...and without a budget nothing is claimed.
    assert lower(net).blocks[0].watts is None


def test_power_reaches_a_bare_branch_by_its_own_label():
    """`dipoles.invvee_coax_station` — the design the issue opens with — is
    ONE bare TL, no composite: there is no "<path>: " prefix to own budget
    rows by. The block matches its branch's own "TL rig→feed" row instead,
    or the design that exists to model feedline loss shows none at all."""
    net = build("dipoles.invvee_coax_station").build_network()
    sch = lower(net, budget=[("TL rig→feed", 0.004)])
    assert sch.blocks[0].watts == pytest.approx(0.004)


def test_power_reaches_an_attachment():
    """A trap in a dipole leg burns power where it hangs, not on a chain."""
    net = build("multiband.trap_dipole").build_network()
    sch = lower(net, budget=[("Load trap_l", 0.002), ("Load trap_r", 0.001)])
    assert [a.watts for a in sch.attachments] == [
        pytest.approx(0.002),
        pytest.approx(0.001),
    ]


def test_duplicate_budget_labels_accumulate():
    """Two probes can share one label (a parallel Shunt stamps group-1 and a
    series one group-2 under the same "Shunt <port>"); a plain dict(budget)
    kept only the last row's watts."""
    net = build("verticals.stub_matched_vertical").build_network()
    budget = [("match: TL rig→feed", 0.004), ("match: TL rig→feed", 0.001)]
    assert lower(net, budget=budget).blocks[0].watts == pytest.approx(0.005)


# ---------------------------------------------------------------------------
# the return conductor
#
# A single-ended branch returns through the datum; a balanced pair returns
# through its partner conductor. Walking single nodes cannot see the second
# kind, and drawing it against an implied ground asserts a bond the hardware
# does not have — so these are the tests that the return path is real.
# ---------------------------------------------------------------------------
def test_a_balanced_chain_reaches_the_antenna():
    """`wire.doublet_balanced_tuner` is rig → floating balun → balanced tuner →
    open-wire line → doublet. Walking single nodes read the `BalancedLine` as
    its a1↔b2 diagonal and the `FloatingBalun` as primary↔b, so the walk never
    arrived and the drawing said "no path from the source to an antenna"."""
    sch = lower(build("wire.doublet_balanced_tuner").build_network())
    assert sch.ends_in_antenna
    assert sch.balanced_end  # it arrives as a PAIR, not on one wire
    assert not sch.notes


def test_a_split_roller_draws_one_coil_in_each_leg():
    """The balanced tuner's inductance is half in each leg. Which conductor a
    branch advances is the whole difference between that and one coil with an
    imaginary ground under it — and it is only visible if the walk carries the
    return."""
    sch = lower(build("wire.doublet_balanced_tuner").build_network())
    tuner = next(b for b in sch.blocks if b.label == "tuner")
    assert [(e.kind, e.orient, e.leg) for e in tuner.elements] == [
        ("balun", "series", "signal"),
        ("inductor", "series", "signal"),
        ("inductor", "series", "return"),
        ("capacitor", "shunt", "signal"),  # differential, across the two legs
    ]
    assert all(e.balanced for e in tuner.elements)


def test_a_differential_element_is_a_rung_not_a_drop_to_ground():
    """The resonating cap bridges the two legs of a floating tuner. There is
    no ground there to drop to, and drawing one would bond the section the
    balun exists to keep floating."""
    sch = lower(build("wire.doublet_balanced_tuner").build_network())
    cap = next(
        e for b in sch.blocks for e in b.elements if e.kind == "capacitor"
    )  # fmt: skip
    assert cap.orient == "shunt" and cap.balanced


def test_a_rib_is_drawn_in_exactly_one_box():
    """A node the chain passes through belongs to two consecutive blocks, so
    keying a rib by node alone drew the differential capacitor twice."""
    sch = lower(build("wire.doublet_balanced_tuner").build_network())
    caps = [e for b in sch.blocks for e in b.elements if e.kind == "capacitor"]
    assert len(caps) == 1


def test_a_floating_port_is_recognised_by_its_terminals():
    """A `PortOnWireFloating("feed")` is wired as feed.p / feed.n and the bare
    name is not a node at all, so a walk looking for the port name never
    arrives at the antenna it is looking for."""
    net = build("wire.doublet_balanced_tuner").build_network()
    assert "feed" in net.ports
    assert not any("feed" in terminals_of(br) for br in net.branches)
    assert lower(net).ends_in_antenna


def test_a_common_mode_pin_keeps_its_ground():
    """`Shunt` is defined as R/L/C to the common, so it stays a drop to ground
    even inside a floating section — that is what a 100 MΩ common-mode pin IS
    (SPICE's rshunt, drawn), and the ground is what explains the resistor.
    The pair's two pins are one per leg, not two on the signal side."""
    sch = lower(build("arrays.bowtie1x2_bl").build_network())
    pins = [e for b in sch.blocks for e in b.elements if e.kind == "resistor"]
    assert len(pins) == 2
    assert not any(e.balanced for e in pins)  # to the datum, not across
    assert {e.leg for e in pins} == {"signal", "return"}
    assert all("100 MΩ" == e.label for e in pins)


def test_a_grounded_shield_is_the_datum():
    """`bowtie1x2_bl` writes the shield as `Shunt(port="JC2", l=0.0)` — a bond,
    not a component. Without merging it the balanced line hanging off that
    shield has a return the walk cannot recognise."""
    sch = lower(build("arrays.bowtie1x2_bl").build_network())
    assert sch.ends_in_antenna and sch.balanced_end


def test_a_second_antenna_is_not_drawn_in_line():
    """`bowtie1x2_bl` feeds two elements in parallel from one point. Drawing
    the second in the chain would say they are in series, which is the
    opposite of what they are — it is a feed BRANCH (issue #685), forked at
    the junction and drawn as its own chain to its own antenna."""
    sch = lower(build("arrays.bowtie1x2_bl").build_network())
    assert len(sch.blocks) == 1  # the trunk carries exactly one arm
    (br,) = sch.branches
    assert (br.origin, br.parent, br.at) == ("JC1", -1, 0)
    assert br.antenna_name == "feed1" and br.balanced_end
    assert [b.label for b in br.blocks] == ["BalancedLine"]
    # The fork is a drawn chain now, so nothing is demoted to an attachment
    # row and there is no note apologising for the drawing.
    assert sch.attachments == [] and sch.notes == []


def test_a_branch_owns_its_own_ribs():
    """feed1's common-mode pins hang on feed1's chain exactly as feed0's hang
    on the trunk — one per leg, to the datum. Before #685 they were opaque
    attachment rows."""
    sch = lower(build("arrays.bowtie1x2_bl").build_network())
    (br,) = sch.branches
    pins = [e for b in br.blocks for e in b.elements if e.kind == "resistor"]
    assert len(pins) == 2
    assert not any(e.balanced for e in pins)  # to the datum, not across
    assert {e.leg for e in pins} == {"signal", "return"}


def test_every_fan_out_design_grows_a_branch():
    """The junction class is not one design: any array that models its
    feedlines forks somewhere."""
    for name, antenna in [
        ("arrays.delta_looparray_network", "loop2"),
        ("wire.expanded_lazy_h", "hi"),
    ]:
        sch = lower(build(name).build_network())
        (br,) = sch.branches
        assert br.antenna_name == antenna
        assert sch.attachments == [] and sch.notes == []


def test_the_chain_marks_the_ports_it_passes_through():
    """An LPDA's chain touches d8…d1 on the way to d0; without marks they are
    anonymous wire (issue #685)."""
    sch = lower(build("broadband.lpda").build_network())
    assert sch.marks == [(b, f"d{9 - b}") for b in range(1, 9)]
    sch = lower(build("multiband.hexbeam_5band").build_network())
    assert sch.marks == [(1, "feed1"), (2, "feed2"), (3, "feed3")]


def test_a_branch_can_fork_mid_chain():
    """A depth-2 corporate tree forks at an interior junction, not at the
    source — the junction gets named, and the branch records which block
    boundary it forks at."""
    net = Network(
        ports={
            "rig": PortVirtual("rig"),
            "J": PortVirtual("J"),
            "ant0": PortOnWire("ant0"),
            "ant1": PortOnWire("ant1"),
        },
        branches=[
            TL(a="rig", b="J", z0=50.0, length=5.0),
            TL(a="J", b="ant0", z0=75.0, length=3.0),
            TL(a="J", b="ant1", z0=75.0, length=3.0),
        ],
        sources=[Driven(port="rig")],
    )
    sch = lower(net)
    assert len(sch.blocks) == 2  # rig→J, J→ant0
    (br,) = sch.branches
    assert (br.origin, br.parent, br.at) == ("J", -1, 1)
    assert br.antenna_name == "ant1"


def test_a_chain_among_parallel_feeds_names_the_port_it_reached():
    """`bowtie1x2_bl`'s two lines are value-identical, so the chain and the
    feed1 attachment read as the same components listed twice unless the
    chain says which feed it landed on. A single-antenna design stays
    unnamed — there is nothing to confuse its chain with."""
    sch = lower(build("arrays.bowtie1x2_bl").build_network())
    assert sch.antenna_name == "feed0"
    sch = lower(build("dipoles.invvee_coax_station").build_network())
    assert sch.antenna_name == ""


def test_a_structure_with_no_feed_chain_does_not_invent_one():
    """`wire.sterba_bl`'s four risers share no node with each other or with the
    source. The old walk wandered the graph and drew them as a plausible
    series chain from the rig — a picture that reads correctly and is
    fabricated."""
    sch = lower(build("wire.sterba_bl").build_network())
    assert sch.blocks == []
    assert len(sch.attachments) == 4
    assert all(len(a.nodes) == 4 for a in sch.attachments)
    assert any("wired into the structure" in n for n in sch.notes)


def test_a_single_ended_branch_will_not_carry_a_floating_pair():
    """A coax returns through its shield and a `Transformer` spans both
    windings node-to-datum, so neither can carry a pair onward. Refusing the
    move is what makes the walk report a gap instead of quietly bonding a
    floating section to ground to get past it."""
    net = Network(
        ports={
            "rig": PortVirtual("rig"),
            "ant": PortOnWireFloating("ant"),
            "sL": PortVirtual("sL"),
            "sR": PortVirtual("sR"),
        },
        branches=[
            FloatingBalun(primary="rig", a="sL", b="sR", n=1.0),
            # a coax spliced into one leg of the floating secondary: its
            # return is its shield, so it cannot carry the pair onward
            TL(a="sL", b="ant.p", z0=50.0, length=1.0),
            # `Network` enforces SPICE's rule that every node needs a path to
            # the datum, so the loose leg is pinned the way SPICE users pin
            # one — a large resistor, `rshunt` by another name.
            Shunt(port="sR", r=1e8),
        ],
        sources=[Driven(port="rig")],
    )
    sch = lower(net)
    assert not sch.ends_in_antenna
    assert any("no run of branches" in n for n in sch.notes)


# ---------------------------------------------------------------------------
# the wrapper vocabulary
# ---------------------------------------------------------------------------
def test_the_fragment_api_is_plain_data():
    """`station.py` must be able to declare a drawing without importing any
    drawing library."""
    el = series("inductor", "2.5 µH")
    assert isinstance(el, Element) and el.orient == "series"
    assert shunt("capacitor", "180 pF").orient == "shunt"
    # Where a symbol sits takes two answers: which way it runs, and which
    # conductor that is.
    assert retn("inductor", "2.5 µH").leg == "return"
    assert shunt("resistor", "100 MΩ", leg="return").leg == "return"
    import antennaknobs.station as station_mod

    assert "schemdraw" not in str(vars(station_mod).keys())


def test_terminals_are_read_per_class_not_guessed():
    """Shunt/Load name their node `port`; a field-name guess would miss them."""
    assert terminals_of(TL(a="x", b="y", z0=50, length=1.0)) == ("x", "y")
    assert terminals_of(Shunt(port="z", c=1e-12)) == ("z",)


# ---------------------------------------------------------------------------
# rendering + CLI
# ---------------------------------------------------------------------------
def test_render_produces_an_svg(tmp_path):
    pytest.importorskip("schemdraw")
    out = tmp_path / "s.svg"
    svg = render_svg(lower(build("wire.doublet_ladder_tuner").build_network()), out)
    assert svg.lstrip().startswith("<?xml") or "<svg" in svg
    assert out.read_text() == svg


@pytest.mark.parametrize(
    "design",
    [
        "verticals.stub_matched_vertical",
        "wire.efhw_sloper",
        "dipoles.invvee_coax_station",
        "multiband.trap_dipole",
        "broadband.lpda",
        "arrays.bowtie4x4",
        "arrays.bowtie1x2_bl",
        "wire.expanded_lazy_h",
    ],
)
def test_every_shape_in_the_corpus_renders(design, tmp_path):
    """Including the awkward ones: no chain, one-terminal loads, 16 sources,
    corporate-feed forks."""
    pytest.importorskip("schemdraw")
    svg = render_svg(lower(build(design).build_network()), tmp_path / "s.svg")
    assert "<svg" in svg


def test_render_draws_both_arms_and_the_marks():
    """The fan-out renders as two named antenna ends — not one chain plus an
    attachment footnote — and a marked chain writes the port names it passes."""
    pytest.importorskip("schemdraw")
    svg = render_svg(lower(build("arrays.bowtie1x2_bl").build_network()))
    assert "antenna (feed0)" in svg and "antenna (feed1)" in svg
    assert "wired into the antenna structure" not in svg
    svg = render_svg(lower(build("broadband.lpda").build_network()))
    assert all(f">d{i}</tspan>" in svg for i in range(1, 9))


def test_a_picked_plane_marks_the_cut_but_keeps_the_whole_chain():
    """Plane UX (issue #652 c): the drawing is the picker, so the FULL chain
    stays on screen — the cut index says where the marker goes and which
    blocks are the disconnected upstream."""
    net = build("wire.doublet_ladder_tuner").build_network()
    sch = lower(net, plane="li")
    assert (sch.plane, sch.plane_cut) == ("li", 1)
    assert len(sch.blocks) == 2  # tuner (upstream) + line, both still drawn
    # A cut at the chain's end marks the antenna terminals themselves.
    assert lower(net, plane="feed").plane_cut == 2
    # The natural plane and an unknown one mark nothing — the drawing never
    # crashes; plane.driven_at is the validating gate.
    assert lower(net, plane="rig").plane_cut is None
    assert lower(net, plane="bogus").plane_cut is None


def test_render_draws_the_plane_marker():
    pytest.importorskip("schemdraw")
    net = build("dipoles.invvee_coax_station").build_network()
    svg = render_svg(lower(net, plane="feed"))
    assert "plane: feed" in svg
    # without a picked plane, no marker
    assert "plane:" not in render_svg(lower(net))


def test_render_burn_is_a_fraction_of_input_when_p_in_is_known(tmp_path):
    """With p_in the annotation is the same percent the power-budget table
    shows, placed where it burns; without a reference it falls back to the
    canonical drive's raw milliwatts."""
    pytest.importorskip("schemdraw")
    net = build("dipoles.invvee_coax_station").build_network()
    budget = [("TL rig→feed", 0.004)]
    with_pin = render_svg(lower(net, budget=budget, p_in=0.016))
    assert "(25.0%)" in with_pin
    without = render_svg(lower(net, budget=budget))
    assert "mW" in without and "%" not in without


def test_cli_writes_a_file(tmp_path):
    pytest.importorskip("schemdraw")
    out = tmp_path / "cli.svg"
    ant.cli(f"schematic --builder wire.doublet_ladder_tuner --out {out}".split())
    assert "<svg" in out.read_text()


def test_cli_refuses_an_antenna_with_no_network():
    with pytest.raises(SystemExit, match="no build_network"):
        ant.cli("schematic --builder dipoles.invvee".split())
