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
    Instance,
    Network,
    PortVirtual,
    Shunt,
    TL,
)
from antennaknobs.schematic import (
    Element,
    lower,
    render_svg,
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
    """`multiband.trap_dipole` is all traps on the feed — no chain at all, but
    emphatically not nothing to draw."""
    sch = lower(build("multiband.trap_dipole").build_network())
    assert len(sch.blocks) == 2
    assert all(e.orient == "shunt" for b in sch.blocks for e in b.elements)


def test_a_long_chain_keeps_its_order():
    sch = lower(build("broadband.lpda").build_network())
    assert len(sch.blocks) >= 5
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


# ---------------------------------------------------------------------------
# the wrapper vocabulary
# ---------------------------------------------------------------------------
def test_the_fragment_api_is_plain_data():
    """`station.py` must be able to declare a drawing without importing any
    drawing library."""
    el = series("inductor", "2.5 µH")
    assert isinstance(el, Element) and el.orient == "series"
    assert shunt("capacitor", "180 pF").orient == "shunt"
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
    ],
)
def test_every_shape_in_the_corpus_renders(design, tmp_path):
    """Including the awkward ones: no chain, one-terminal loads, 16 sources."""
    pytest.importorskip("schemdraw")
    svg = render_svg(lower(build(design).build_network()), tmp_path / "s.svg")
    assert "<svg" in svg


def test_cli_writes_a_file(tmp_path):
    pytest.importorskip("schemdraw")
    out = tmp_path / "cli.svg"
    ant.cli(f"schematic --builder wire.doublet_ladder_tuner --out {out}".split())
    assert "<svg" in out.read_text()


def test_cli_refuses_an_antenna_with_no_network():
    with pytest.raises(SystemExit, match="no build_network"):
        ant.cli("schematic --builder dipoles.invvee".split())
