"""The station rail's chain model (docs/design/block-builder.md, "The station
rail"): attaching to any catalog design, the codegen gate, reading the house
style back, and the placement enumeration.

The codegen gate: each catalog station, written as a rail chain, reproduces
the design's own network, both as the `Network` the chain builds and as the
Python text it writes, compiled here (a test is the only place generated text
is ever run) and solved as a design in its own right. Compared by the
rig-port impedance at the design's default frequency in free space: the
network is what is under test, and free space keeps the fills cheap.
"""

import importlib
import warnings

import pytest

import antennaknobs.web.server  # noqa: F401 — adapter import order (registry)
from antennaknobs import station_rail as sr
from antennaknobs.network import (
    TL,
    Driven,
    Load,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
)
from antennaknobs.plane import antenna_side
from antennaknobs.station_rail_solve import SolvedAntenna, solve_chain
from antennaknobs.web.adapter import _make_momwire_engine, list_designs

# The house tolerance for two spellings of one network
# (tests/test_composite_network.py).
REL = 1e-12


def _builder(design):
    return importlib.import_module(f"antennaknobs.designs.{design}").Builder()


def _z(builder):
    return complex(_make_momwire_engine({}, builder).impedance()[0])


def _exec(text):
    """The Builder a generated file defines. Tests only: production reads a
    file through `sr.read_python`, never by running it."""
    ns: dict = {}
    exec(compile(text, "<station_rail>", "exec"), ns)  # generated text under test
    return ns["Builder"]


def solved(design, req=None):
    """``(att, SolvedAntenna)`` the way the endpoints build them."""
    b = _builder(design)
    att = sr.attach(design, b)
    if att.form == "wire":
        wires = b.build_wires
        object.__setattr__(b, "build_wires", lambda: sr.wires_for(att, wires()))
    bare = sr.antenna_network(att)
    object.__setattr__(b, "build_network", lambda: bare)
    return att, SolvedAntenna(_make_momwire_engine(req or {}, b))


@pytest.mark.parametrize("design", sr.CATALOG_STATIONS)
def test_catalog_chain_reproduces_the_design_network(design):
    b = _builder(design)
    att = sr.attach(design, b)
    chain, origin = sr.starting_chain(att, b)
    assert origin == "design"
    z_design = _z(_builder(design))

    net = sr.to_network(chain, att)
    nb = _builder(design)
    object.__setattr__(nb, "build_network", lambda: net)
    z_chain = _z(nb)

    z_file = _z(_exec(sr.to_python(chain, att))())

    _att, sa = solved(design)
    z_rail = complex(*(solve_chain(sa, chain, att)[k] for k in ("z_re", "z_im")))

    for z in (z_chain, z_file, z_rail):
        assert z == pytest.approx(z_design, rel=REL), (design, z, z_design)
    # The seam carries the chain: a changed chain moves the answer.
    longer = sr.check_chain(chain)
    longer["items"].insert(0, {"kind": "cable", "cable": "RG-58", "length_m": 1.0})
    z_longer = complex(*(solve_chain(sa, longer, att)[k] for k in ("z_re", "z_im")))
    assert abs(z_longer - z_design) > 1e-3 * abs(z_design)
    # The catalog's own port and node names.
    assert set(net.ports) == set(_builder(design).build_network().ports)


def test_codegen_is_house_style_for_the_doublet():
    b = _builder("wire.doublet_ladder_tuner")
    att = sr.attach("wire.doublet_ladder_tuner", b)
    text = sr.to_python(sr.starting_chain(att, b)[0], att)
    assert '"li": PortVirtual("li"),  # line input' in text
    assert (
        'TL.from_cable(cable_from_catalog("openwire-600"), "li", "feed", 30.48)' in text
    )
    assert "t_network_tuner(c1_pF=81.2, c2_pF=500.0, l_uH=4.218, ql=200.0)" in text
    assert 'sources=[Driven(port="rig", voltage=1 + 0j)]' in text


# --- attaching to any design ------------------------------------------------------

# Every catalog design either attaches, in one of the three forms, or is
# refused with one of these reasons. Pinned as counts so a new design that
# lands in neither is noticed.
REFUSALS = {
    "is fed at": "several fed wires",
    "drives": "several sources",
    "floating": "floating feed",
    "multi-feed": "multi-feed",
}


def test_every_catalog_design_attaches_or_is_refused_by_name():
    forms, refused, odd = {}, {}, []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for design in list_designs():
            b = _builder(design)
            try:
                att = sr.attach(design, b)
            except sr.RailRefusal as e:
                why = next((v for k, v in REFUSALS.items() if k in str(e)), None)
                if why is None:
                    odd.append((design, str(e)))
                refused[why] = refused.get(why, 0) + 1
                continue
            forms[att.form] = forms.get(att.form, 0) + 1
            chain, _origin = sr.starting_chain(att, b)
            sr.to_network(chain, att)  # every starting chain builds
            frozen = sr.freeze(chain, att)[0]
            assert sr.read_python(sr.to_python(chain, att))[0] == frozen, design
    assert not odd, odd
    assert forms == {"wire": 44, "port": 13, "cut": 25}, forms
    assert refused == {
        "several fed wires": 20,
        "several sources": 2,
        "floating feed": 3,
        "multi-feed": 4,
    }, refused


# Designs whose station meets the antenna at more than the feed: a floating
# balun into an end-port pair, a phasing harness from a virtual junction.
MULTI_FEED = [
    "beams.yagi_endport",
    "dipoles.invvee_endport",
    "arrays.delta_looparray_network",
    "wire.expanded_lazy_h",
]


@pytest.mark.parametrize("design", MULTI_FEED)
def test_a_station_that_meets_the_antenna_twice_is_refused(design):
    with pytest.raises(sr.RailRefusal, match="multi-feed"):
        sr.attach(design, _builder(design))


def test_where_the_source_is_the_feed_the_antenna_is_the_whole_design():
    """No station to take off: the rail's antenna box is the design's network,
    every branch and port, so its probe is the design's own feed-point Z (the
    solve is gated in test_station_rail_probes). Over the whole catalog,
    structurally: building networks only."""
    seen = 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for design in list_designs():
            b = _builder(design)
            net = b.build_network()
            if net is None or len(net.sources) != 1:
                continue
            try:
                att = sr.attach(design, b)
            except sr.RailRefusal:
                continue
            if net.sources[0].port != att.feed:
                continue
            seen += 1
            bare = sr.antenna_network(att)
            assert bare.branches == net.branches, design
            assert bare.ports == net.ports, design
            assert bare.sources == net.sources, design
    assert seen >= 20, seen


def test_a_bond_on_another_antenna_port_stays_with_the_antenna():
    # A zero-value Shunt bonds an idle stub's port to the datum: it is wired
    # to that port, so it is the antenna's even with a station to take off.
    net = Network(
        ports={"feed": PortOnWire("feed"), "stub": PortOnWire("stub"), "rig": PortVirtual("rig")},
        branches=[
            TL(a="rig", b="feed", z0=50.0, length=3.0),
            Shunt(port="stub", r=0.0),
        ],
        sources=[Driven(port="rig", voltage=1 + 0j)],
    )  # fmt: skip
    side = antenna_side(net, "feed")
    assert side.branches == [Shunt(port="stub", r=0.0)]


def test_the_antenna_side_keeps_what_the_antenna_carries():
    # The trap dipole's traps are on their own wires: the antenna's.
    net = _builder("multiband.trap_dipole").build_network()
    side = antenna_side(net, "feed")
    assert len(side.branches) == len(net.branches)
    assert all(isinstance(br, Load) for br in side.branches)
    # The sky loop's L match has a shunt part on the feed: the station's.
    net = _builder("loops.skyloop_lmatch").build_network()
    side = antenna_side(net, "feed")
    assert side.branches == [] and set(side.ports) == {"feed"}
    assert side.ports["feed"] == PortOnWire("feed")


def test_a_wire_design_names_its_fed_wire():
    b = _builder("dipoles.invvee")
    att = sr.attach("dipoles.invvee", b)
    assert (att.form, att.feed) == ("wire", "feed")
    wires = sr.wires_for(att, b.build_wires())
    assert [w.name for w in wires if w.ex is None and w.name == "feed"] == ["feed"]
    assert all(w.ex is None for w in wires)


# --- reading the house style back ---------------------------------------------------


def _chains():
    """A spread of chains over the three forms: every kind, both tuners
    fixed and self-tuning, stubs either side of a series part, a node and a
    component renamed by hand."""
    yield "wire.doublet_ladder_tuner", None
    yield "dipoles.invvee", {
        "rig": "shack",
        "items": [
            {"kind": "cable", "cable": "RG-8X", "length_m": 12.0},
            {"kind": "shorted_stub", "freq_mhz": 28.47, "length_wl": 0.1, "cable": "RG-8X"},
            {"kind": "l_tuner", "tune_to": 50.0, "shunt_at": "auto", "ql": 200.0},
            {"kind": "line", "z0": 75.0, "length_m": 1.5, "vf": 0.66, "node": "q"},
            {"kind": "balun", "n": 1.0, "lmag_uH": 10.0, "qlmag": 100.0, "name": "choke"},
            {"kind": "open_stub", "freq_mhz": 28.47, "length_wl": 0.2, "z0": 300.0},
        ],
    }  # fmt: skip
    yield (
        "multiband.trap_dipole",
        {
            "rig": "rig",
            "items": [
                sr.palette_item("t_tuner", 28.0),
                {"kind": "unun", "turns": 3.0},
                {"kind": "cable", "cable": "LMR-400", "length_m": 20.0},
            ],
        },
    )
    yield "loops.skyloop_lmatch", {"rig": "rig", "items": []}
    yield (
        "dipoles.ocf_dipole",
        {
            "rig": "rig",
            "items": [{"kind": "shorted_stub", "freq_mhz": 7.0, "length_wl": 0.125}],
        },
    )


@pytest.mark.parametrize(
    ("design", "chain"), list(_chains()), ids=lambda v: str(v)[:24]
)
def test_chain_to_code_to_chain_is_identity(design, chain):
    b = _builder(design)
    att = sr.attach(design, b)
    if chain is None:
        chain = sr.starting_chain(att, b)[0]
    chain, _ = sr.freeze(sr.check_chain(chain), att)
    text = sr.to_python(chain, att)
    back, antenna = sr.read_python(text)
    assert back == chain
    assert antenna == {"module": att.module, "form": att.form, "feed": att.feed}
    assert sr.to_python(back, att) == text


def _doublet_text():
    b = _builder("wire.doublet_ladder_tuner")
    att = sr.attach("wire.doublet_ladder_tuner", b)
    return sr.to_python(sr.freeze(sr.starting_chain(att, b)[0], att)[0], att)


def test_layout_and_comments_do_not_matter_and_ints_read_as_floats():
    text = _doublet_text()
    edited = (
        text.replace("  # line input", "")
        .replace("ql=200.0", "ql=200")
        .replace(
            'TL.from_cable(cable_from_catalog("openwire-600"), "li", "feed", 30.48)',
            'TL.from_cable(\n                    cable_from_catalog("openwire-600"),'
            ' "li", "feed", 30.48\n                )',
        )
    )
    assert edited != text
    assert sr.read_python(edited)[0] == sr.read_python(text)[0]


# Each hand edit outside the house style, and the words its refusal must use.
OUTSIDE = [
    ("30.48)", "self.line_len_m)", "not a literal"),
    ("from antennaknobs.station", "import os\nfrom antennaknobs.station", "nothing else"),
    ('"tuner",\n', '"tuner",\n', None),  # control: unchanged reads
    ("t_network_tuner(", "my_tuner(", "not a component the rail offers"),
    ("    def build_network(self):", "    x = 1\n\n    def build_network(self):", "build_network"),
    ('Driven(port="rig"', 'Driven(port="li"', "house style"),
    ("voltage=1 + 0j", "voltage=2 + 0j", "house style"),
    ("class Builder(Antenna):", "class Builder(Antenna, dict):", "the class is Builder"),
    ("def build_network(self):", "def build_network(self)", "not Python"),
]  # fmt: skip


@pytest.mark.parametrize(("old", "new", "why"), OUTSIDE)
def test_a_file_outside_the_house_style_is_refused_with_a_reason(old, new, why):
    text = _doublet_text()
    assert old in text
    edited = text.replace(old, new, 1)
    if why is None:
        sr.read_python(edited)
        return
    with pytest.raises(sr.RailRefusal, match=why):
        sr.read_python(edited)


def test_reordered_branches_are_refused_not_reordered():
    """Two branches swapped by hand, each keeping its nodes, is still a
    working network, but not one the rail writes: refused, not reordered."""
    lines = _doublet_text().splitlines()
    start = lines.index(" " * 12 + "branches=[") + 1
    end = lines.index(" " * 12 + "],")
    elements, cur = [], []
    for ln in lines[start:end]:
        if ln.startswith(" " * 16) and not ln.startswith(" " * 17) and cur:
            if not ln.strip().startswith(")"):
                elements.append(cur)
                cur = []
        cur.append(ln)
    elements.append(cur)
    assert len(elements) == 2
    swapped = lines[:start] + elements[1] + elements[0] + lines[end:]
    with pytest.raises(sr.RailRefusal, match="house style"):
        sr.read_python("\n".join(swapped) + "\n")


def test_a_chain_with_bad_values_is_refused():
    for bad, why in [
        ({"items": [{"kind": "cable", "cable": "RG-999", "length_m": 1.0}]}, "unknown cable"),
        ({"items": [{"kind": "cable", "cable": "RG-8X"}]}, "needs length_m"),
        ({"items": [{"kind": "cable", "cable": "RG-8X", "length_m": "1"}]}, "number"),
        ({"items": [{"kind": "toaster"}]}, "unknown component kind"),
        ({"items": [{"kind": "balun", "n": 1.0, "name": "a b"}]}, "identifier"),
        ({"rig": "1x", "items": []}, "identifier"),
        ({"version": 2, "items": []}, "version"),
        ({"items": [{"kind": "l_tuner", "tune_to": 50.0, "mode": "low\nx"}]}, "one of"),
        ({"items": [{"kind": "l_tuner", "tune_to": 50.0, "shunt_at": "ant"}]}, "one of"),
    ]:  # fmt: skip
        with pytest.raises(sr.RailRefusal, match=why):
            sr.check_chain(bad)


# --- placements --------------------------------------------------------------------


def _doublet():
    b = _builder("wire.doublet_ladder_tuner")
    return sr.attach("wire.doublet_ladder_tuner", b)


def _two_box():
    return {
        "rig": "rig",
        "items": [
            {"kind": "cable", "cable": "RG-8X", "length_m": 10.0},
            sr.palette_item("t_tuner", 7.1),
        ],
    }


# Palette key -> cards on rig / RG-8X 10 m / T tuner / feed: three junctions
# and three nodes, except that a part put either side of its own twin is one
# circuit, offered once: RG-8X beside the RG-8X (a longer coax), and the
# palette's fixed T beside the same fixed T.
TWO_BOX_COUNTS = {
    "coax": 2,
    "ladder": 3,
    "line": 3,
    "auto_l": 3,
    "auto_t": 3,
    "t_tuner": 2,
    "balun_1_1": 3,
    "balun_4_1": 3,
    "unun_49_1": 3,
    "shorted_stub": 3,
    "open_stub": 3,
}


def test_every_palette_entry_has_a_two_box_count():
    assert set(TWO_BOX_COUNTS) == set(sr.PALETTE)


@pytest.mark.parametrize("key", sorted(sr.PALETTE))
def test_placements_on_a_two_box_chain(key):
    att = _doublet()
    cards = sr.placements(_two_box(), att, sr.palette_item(key, 7.1))
    assert len(cards) == TWO_BOX_COUNTS[key]
    for c in cards:
        sr.to_network(c["chain"], att)  # every card builds
    assert len({sr._circuit(c["chain"]) for c in cards}) == len(cards)


def test_series_part_goes_either_side_of_a_stub_and_stubs_commute():
    att = _doublet()
    chain = _two_box()
    chain["items"].insert(1, sr.palette_item("shorted_stub", 7.1))
    series = sr.placements(chain, att, sr.palette_item("ladder", 7.1))
    assert [c["pos"] for c in series] == [0, 1, 2, 3]
    stubs = sr.placements(chain, att, sr.palette_item("open_stub", 7.1))
    assert [c["pos"] for c in stubs] == [0, 1, 3]


@pytest.mark.parametrize("second", ["auto_l", "auto_t"])
@pytest.mark.parametrize("first", ["auto_l", "auto_t"])
def test_a_second_self_tuning_tuner_is_never_offered(first, second):
    att = _doublet()
    chain = _two_box()
    chain["items"].insert(0, sr.palette_item(first, 7.1))
    assert sr.placements(chain, att, sr.palette_item(second, 7.1)) == []
    assert sr.refusal(chain, sr.palette_item(second, 7.1))
    # A fixed tuner is still welcome; either side of the fixed T is one circuit.
    assert len(sr.placements(chain, att, sr.palette_item("t_tuner", 7.1))) == 3


def test_coax_onto_a_balanced_feed_is_offered_with_an_advisory():
    att = _doublet()
    cards = sr.placements(_two_box(), att, sr.palette_item("coax", 7.1))
    at_feed = cards[-1]
    assert at_feed["where"].startswith("at the antenna")
    assert any("balanced feed" in a for a in at_feed["advisories"])
    assert not cards[0]["advisories"]


def test_a_feed_of_unknown_balance_gets_no_balance_advisory():
    att = sr.attach("dipoles.invvee", _builder("dipoles.invvee"))
    assert att.balanced is None
    cards = sr.placements(_two_box(), att, sr.palette_item("coax", 28.0))
    assert not any("balanced feed" in a for c in cards for a in c["advisories"])


def test_an_edit_renames_nothing_else():
    att = _doublet()
    b = _builder("wire.doublet_ladder_tuner")
    chain, _ = sr.freeze(sr.starting_chain(att, b)[0], att)
    before = sr.to_python(chain, att).splitlines()
    card = sr.placements(chain, att, sr.palette_item("auto_l", 7.1))[0]  # at the rig
    after = sr.to_python(card["chain"], att).splitlines()
    # The T keeps "tuner" and li keeps its name; the new box is "tuner2".
    tuner = " " * 20 + '"tuner",'
    assert tuner in before and tuner in after
    assert " " * 20 + '"tuner2",' in after
    assert " " * 20 + 'out="li",' in after


def test_generated_names_keep_clear_of_the_antennas_own():
    # The trap dipole's network already names its trap ports; a chain's
    # generated node names must not collide with any of them.
    att = sr.attach("multiband.trap_dipole", _builder("multiband.trap_dipole"))
    chain = {"rig": "rig", "items": [sr.palette_item("coax", 28.0)] * 3}
    nodes, _ = sr.layout(chain, att)
    assert not (set(nodes) - {att.feed}) & set(att.reserved)


def test_any_text_writes_as_one_python_literal():
    import ast

    for v in ['a\nb"c\\', "RG-8X", "Ω\x00\t"]:
        assert ast.literal_eval(sr._lit(v)) == v
