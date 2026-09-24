"""AK#1705: every constant SY symbol of an imported ``.nec`` deck is a knob.

The four driving decks are in ``tests/fixtures/sy_knobs_1705`` (provenance in
its README). What is pinned here:

- the classification (`nec_import.classify_sy`) on each deck, labels and
  units included -- which symbols are knobs, which are derived, and why the
  rest are neither;
- default identity: the design at its default knob values builds exactly
  today's import (the whole-corpus version is
  ``scripts/census_sy_knobs_1705.py``);
- a knob move equals importing a copy of the deck with that one SY value
  edited by hand, and the helper that checks it fails when the override path
  is switched off (the negative control);
- refusals by name, and the design building again at a good value after one;
- the optimizer and the tracker moving a knob through the app's own solve
  entry, with a derived symbol following.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import numpy as np
import pytest

import antennaknobs.file_designs as file_designs
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import classify_sy, parse_nec, resolve_sy

FIXTURES = Path(__file__).parent / "fixtures" / "sy_knobs_1705"
PRIMARY = "3el-inverted-V.nec"
DECKS = (PRIMARY, "moxon435_optimised.nec", "GndScreen.nec", "3elYagiGain.nec")


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def _kinds(name: str) -> dict[str, str]:
    return {s.name: s.kind for s in classify_sy(_text(name))}


def _design(name: str):
    return builder_from_file(str(FIXTURES / name))


def _adapter():
    # The registry package first: it resolves the adapter <-> examples import
    # cycle in the order the app does.
    importlib.import_module("antennaknobs.web.examples")
    from antennaknobs.web import adapter

    return adapter


def _plain_wires(cls, deck):
    return cls.auto_mesh(cls(), list(deck.wire_tuples(specs=True)))


def _edit_sy(text: str, spelling: str, literal: str) -> str:
    """The deck with ``spelling``'s one SY assignment set to ``literal``."""
    pat = re.compile(
        r"(?im)^(\s*SY\b[^'\n]*?(?<![\w.])"
        + re.escape(spelling)
        + r"\s*=\s*)([^,'\n]+?)(\s*(?:,|'|$))"
    )
    hits = list(pat.finditer(text))
    assert len(hits) == 1, spelling
    m = hits[0]
    return text[: m.start(2)] + literal + text[m.end(2) :]


def _moved(sym):
    if sym.integer:
        return sym.default + 1
    return sym.default * 1.1 if sym.default else 0.5


def _assert_move_is_hand_edit(cls, text: str, sym, value) -> None:
    """Moving ``sym`` to ``value`` builds exactly the hand-edited deck, AND
    moves the geometry or the network -- so a knob that silently did nothing
    cannot pass by also leaving the hand-edited reference alone."""
    params = dict(cls.default_params)
    params[sym.param] = value
    moved = cls(params)
    literal = str(int(value)) if sym.integer else repr(float(value))
    if sym.unit:
        literal += "*" + re.search(r"([A-Za-z_]\w*)\s*$", sym.expr).group(1)
    hand = parse_nec(_edit_sy(text, sym.spelling, literal), network=True)
    wires, net = moved.build_wires(), moved.build_network()
    assert wires == _plain_wires(cls, hand)
    assert net == hand.network()
    base = cls()
    assert (wires, net) != (base.build_wires(), base.build_network()), (
        f"moving {sym.param} changed nothing"
    )


# -- classification ----------------------------------------------------------


def test_primary_deck_nine_commented_constants_are_knobs():
    syms = {s.name: s for s in classify_sy(_text(PRIMARY))}
    knobs = {n for n, s in syms.items() if s.kind == "knob"}
    derived = {n for n, s in syms.items() if s.kind == "derived"}
    assert knobs == {
        "hgh",
        "len",
        "ang",
        "refl",
        "refd",
        "refa",
        "dirl",
        "dird",
        "dira",
    }
    # `SY z=len*cos(ang/2), x=...` is written `-X` / `hgh-Z` in the GW cards:
    # one symbol, whatever the case.
    assert derived == {
        "z", "x", "rzi", "ry", "refh", "rz", "rx", "dzi", "dy", "dirh", "dz", "dx"
    }  # fmt: skip
    assert syms["hgh"].label == "Height tower"
    assert syms["refa"].label == "Guy wire angle with XY plane"
    cls = _design(PRIMARY)
    assert cls.default_params["sy_hgh"] == 21.0
    # AK#1709: the knob shows the SY spelling; the comment is the tooltip
    # description, not a second copy of the label.
    assert cls.default_params["ui_params"]["sy_len"]["label"] == "len"
    assert cls.default_params["ui_params"]["sy_len"]["description"] == "Length radiator"
    assert [k for k in cls.default_params if k.startswith("sy_")] == [
        f"sy_{n}" for n in ("hgh", "len", "ang", "refl", "refd", "refa", "dirl", "dird", "dira")
    ]  # fmt: skip


def test_moxon_five_labelled_knobs():
    cls = _design("moxon435_optimised.nec")
    ui = cls.default_params["ui_params"]
    knobs = [k for k in cls.default_params if k.startswith("sy_")]
    assert knobs == ["sy_width", "sy_length", "sy_gapstart", "sy_gap", "sy_radius"]
    assert [ui[k]["label"] for k in knobs] == [
        "width", "length", "gapstart", "gap", "radius",
    ]  # fmt: skip
    assert [ui[k]["description"] for k in knobs[:4]] == ["A", "E", "D", "C"]


def test_gndscreen_literal_arithmetic_is_a_knob_and_counts_follow_the_deck():
    syms = {s.name: s for s in classify_sy(_text("GndScreen.nec"))}
    assert syms["ra"].kind == "knob" and syms["ra"].default == 22.5  # 360/16
    assert {syms[n].kind for n in ("segv", "segh", "rseg")} == {"derived"}
    assert syms["cu"].kind == "knob" and syms["cu"].reaches == {"LD"}
    assert syms["fe"].kind == "inert"  # defined, never used
    # One card, two assignments, a comment with two comma-separated labels.
    assert (syms["ra"].label, syms["radl"].label) == ("Nr radials", "radial length")
    cls = _design("GndScreen.nec")
    base = cls().file_deck_parsed
    assert base.wires[0].n_seg == 20  # segV = int(hgh)
    params = dict(cls.default_params, sy_hgh=23.7)
    deck = cls(params).file_deck_parsed
    assert deck.wires[0].n_seg == 23  # re-meshed as the author wrote it
    assert deck.wires[1].n_seg == 26  # segH = int(len - hgh)
    assert deck.wires[0].p2[2] == 23.7


def test_cebik_yagi_frequency_units_and_zero_default():
    syms = {s.name: s for s in classify_sy(_text("3elYagiGain.nec"))}
    assert syms["fr"].kind == "knob"
    assert {"FR", "GW"} <= syms["fr"].reaches
    assert syms["fr"].label == "Enter Desired Frequency in MHz."
    assert syms["inp"].kind == "unit"  # Inp=mm
    assert syms["scal"].kind == "unit"  # the GS scale factor
    assert syms["hgh"].kind == "knob" and syms["hgh"].default == 0.0
    cls = _design("3elYagiGain.nec")
    ui = cls.default_params["ui_params"]
    # The zero default spans +- the deck's own extent: the largest coordinate
    # it writes (the reflector's half length here).
    extent = max(abs(c) for w in cls.file_deck_parsed.wires for c in (*w.p1, *w.p2))
    assert (ui["sy_hgh"]["min"], ui["sy_hgh"]["max"]) == (-extent, extent)
    assert ui["sy_hgh"]["step"] == 0.01
    note = ui["notes"]
    assert "sy_fr also sets the FR card" in note and "14.05 MHz" in note
    assert "Inp (a unit selector)" in note and "Scal (a unit selector)" in note
    # The app's frequency stays at the deck's.
    assert cls.default_params["freq"] == 14.05


def test_the_adapter_publishes_the_knobs_with_their_labels():
    ex = _adapter()._make_example(
        "user.t", _design("3elYagiGain.nec"), defer_hints=True
    )
    specs = {p.name: p for p in ex.param_schema}
    assert specs["sy_fr"].label == "Fr"  # the deck's own spelling, case kept
    assert specs["sy_fr"].description == "Enter Desired Frequency in MHz."
    assert specs["sy_hgh"].min < 0 < specs["sy_hgh"].max
    assert specs["sy_wd"].min == pytest.approx(5.0) and specs["sy_wd"].max == 15.0


def test_ak1709_primary_deck_served_schema_labels_are_the_sy_spellings():
    """The 3el-inverted-V knob grid (AK#1709 acceptance): every knob's
    served `label` is the deck's own SY spelling, and its `description`
    carries the SY card's comment -- through the same adapter path
    `GET /examples` uses, not just `_SyKnobs.ui_params()` in isolation."""
    ex = _adapter()._make_example("user.t", _design(PRIMARY), defer_hints=True)
    specs = {p.name: p for p in ex.param_schema}
    expected = {
        "hgh": "Height tower",
        "len": "Length radiator",
        "ang": "Angle between wires",
        "refl": "Lenght reflector",
        "refd": "Distance from radiator",
        "refa": "Guy wire angle with XY plane",
        "dirl": "Length reflector",
        "dird": "Distance from radiator",
        "dira": "Guy wire angle with XY plane",
    }
    for spelling, comment in expected.items():
        spec = specs[f"sy_{spelling}"]
        assert spec.label == spelling
        assert spec.description == comment


def test_integer_unit_redefined_and_frequency_only_symbols():
    deck = """CM synthetic
CE
SY n=21 'segments
SY r=1.5*mm 'wire radius
SY f=14.1
SY a=1
SY a=a*2
SY half=5*a/2
GW 1 n -half 0 10 half 0 10 r
GE 0
EX 0 1 11 0 1 0
FR 0 1 0 0 f 0
EN
"""
    syms = {s.name: s for s in classify_sy(deck)}
    assert syms["n"].kind == "knob" and syms["n"].integer and syms["n"].default == 21
    assert isinstance(syms["n"].default, int)
    assert (syms["r"].unit, syms["r"].default) == ("mm", 1.5)
    assert syms["f"].kind == "frequency"
    assert syms["a"].kind == "redefined"
    assert syms["half"].kind == "derived"
    with pytest.raises(ValueError, match="'a' is assigned 2 times"):
        parse_nec(deck, network=True, sy_overrides={"a": 3.0})
    with pytest.raises(ValueError, match="defines no SY symbol 'nope'"):
        parse_nec(deck, network=True, sy_overrides={"nope": 3.0})


def test_integer_and_unit_knob_moves_equal_hand_edits(tmp_path):
    deck = """CE
SY n=21 'segments
SY r=1.5*mm 'wire radius
SY len=10.1
GW 1 n -len 0 10 len 0 10 r
GE 0
EX 0 1 11 0 1 0
FR 0 1 0 0 14.1 0
EN
"""
    path = tmp_path / "unit.nec"
    path.write_text(deck)
    cls = builder_from_file(str(path))
    ui = cls.default_params["ui_params"]
    assert ui["sy_r"]["unit"] == "mm" and cls.default_params["sy_r"] == 1.5
    syms = {s.name: s for s in cls.file_sy_knobs.symbols}
    _assert_move_is_hand_edit(cls, deck, syms["n"], 23)
    _assert_move_is_hand_edit(cls, deck, syms["r"], 2.0)
    # The radius the engines see is metres: 2.0 mm.
    params = dict(cls.default_params, sy_r=2.0)
    assert cls(params).build_wires()[0].spec.radius == 2.0 * 1e-3


# -- default identity and moves -----------------------------------------------


@pytest.mark.parametrize("name", DECKS)
def test_default_values_reproduce_the_import_exactly(name):
    cls = _design(name)
    plain = parse_nec(_text(name), name=name, network=True)
    b = cls()
    wires = b.build_wires()
    assert wires == _plain_wires(cls, plain)
    assert repr(wires) == repr(_plain_wires(cls, plain))  # -0.0 is not 0.0
    assert b.build_network() == plain.network()
    # The instance's deck came through the override re-parse, not the import.
    deck = b.file_deck_parsed
    assert deck == plain and deck is not cls.file_deck_parsed
    assert cls.file_sy_knobs._parse.cache_info().misses >= 1


@pytest.mark.parametrize("name", DECKS)
def test_each_knob_move_equals_a_hand_edited_deck(name):
    cls = _design(name)
    text = _text(name)
    for sym in cls.file_sy_knobs.symbols:
        _assert_move_is_hand_edit(cls, text, sym, _moved(sym))


def test_negative_control_the_move_check_fails_without_the_override_path(
    monkeypatch,
):
    """Switch the overrides off at the seam `_SyKnobs` parses through: the
    move helper must then fail, or it proves nothing."""
    cls = _design(PRIMARY)
    sym = cls.file_sy_knobs.symbols[0]
    real = file_designs.parse_nec

    def no_overrides(text, **kw):
        kw.pop("sy_overrides", None)
        return real(text, **kw)

    monkeypatch.setattr(file_designs, "parse_nec", no_overrides)
    fresh = _design(PRIMARY)  # a new cache, parsed through the patched seam
    with pytest.raises(AssertionError):
        _assert_move_is_hand_edit(fresh, _text(PRIMARY), sym, _moved(sym))


def test_a_derived_symbol_follows_on_the_primary_deck():
    cls = _design(PRIMARY)
    params = dict(cls.default_params, sy_len=11.0, sy_ang=100.0)
    w = cls(params).file_deck_parsed.wires[0]
    # GW 1 20 -X 0 hgh-Z ...: x = len*sin(ang/2), z = len*cos(ang/2).
    import math

    assert w.p1 == pytest.approx(
        (-11.0 * math.sin(math.radians(50.0)), 0.0, 21.0 - 11.0 * math.cos(math.radians(50.0)))
    )  # fmt: skip


def test_primary_deck_z_on_momwire_is_the_hand_edited_decks(tmp_path):
    """Z, not just geometry, on momwire: the knob-moved design and the
    hand-edited deck, each built through `builder_from_file`, solve
    bit-identically; and the default design solves as today's import."""
    cls = _design(PRIMARY)
    text = _text(PRIMARY)
    edited = tmp_path / "edited.nec"
    edited.write_text(_edit_sy(text, "len", "10.9"))
    params = dict(cls.default_params, sy_len=10.9)
    z_knob = MomwireEngine(cls(params), ground=None).impedance()
    z_hand = MomwireEngine(builder_from_file(str(edited))(), ground=None).impedance()
    assert np.array_equal(np.asarray(z_knob), np.asarray(z_hand))
    frozen = tmp_path / "frozen.nec"
    frozen.write_text(resolve_sy(text))  # the same deck with no SY cards
    z_default = MomwireEngine(cls(), ground=None).impedance()
    z_frozen = MomwireEngine(builder_from_file(str(frozen))(), ground=None).impedance()
    assert not np.array_equal(np.asarray(z_knob), np.asarray(z_default))
    assert builder_from_file(str(frozen)).file_sy_knobs is None
    # resolve_sy prints each value with %g-style digits, so this one is a
    # tolerance: the SY-free deck is the same antenna to ~1e-6 relative.
    assert np.allclose(z_default, z_frozen, rtol=1e-5)


# -- refusals -----------------------------------------------------------------


def test_topology_change_is_refused_by_name_and_the_design_keeps_working():
    cls = _design("moxon435_optimised.nec")
    bad = dict(cls.default_params, sy_gap=0.0)
    with pytest.raises(ValueError) as exc:
        cls(bad).build_wires()
    msg = str(exc.value)
    assert "sy_gap = 0" in msg
    assert "wire 1 (tag 1) end 1 now meets wire 4 (tag 4) end 1" in msg
    assert "topology is frozen" in msg
    # The last good value still builds, and so does the next good one.
    assert cls().build_wires() == _plain_wires(
        cls, parse_nec(_text("moxon435_optimised.nec"), network=True)
    )
    assert len(cls(dict(cls.default_params, sy_gap=9.0)).build_wires()) == 6


def test_zero_length_wire_is_refused_by_name():
    cls = _design("moxon435_optimised.nec")
    with pytest.raises(
        ValueError, match=r"sy_width = 0 .*wire 2 \(tag 2\) would have zero length"
    ):
        cls(dict(cls.default_params, sy_width=0.0)).build_network()


def test_ground_contact_and_segment_count_refusals_name_the_knob():
    cls = _design("GndScreen.nec")
    with pytest.raises(
        ValueError, match="sy_radh = 0 .*from above the ground plane to in it"
    ):
        cls(dict(cls.default_params, sy_radh=0.0)).build_wires()
    with pytest.raises(ValueError, match="sy_hgh = 0.5 .*segment count must be >= 1"):
        cls(dict(cls.default_params, sy_hgh=0.5)).build_wires()
    with pytest.raises(ValueError, match="sy_len = nan is not a number"):
        cls(dict(cls.default_params, sy_len=float("nan"))).build_wires()


def test_a_deck_without_sy_cards_imports_exactly_as_before(tmp_path):
    path = tmp_path / "plain.nec"
    path.write_text(resolve_sy(_text(PRIMARY)))
    cls = builder_from_file(str(path))
    assert cls.file_sy_knobs is None
    assert set(cls.default_params) == {"freq", "design_freq", "ui_params"}
    assert "SY" not in (cls.default_params["ui_params"].get("notes") or "")
    assert cls.file_deck_parsed is cls().file_deck_parsed


# -- the optimizer and the tracker, through the app's solve entry -----------

SMALL = """CM a dipole with one derived symbol
CE
SY len=10.4 'Dipole length
SY h=10 'Height
SY half=len/2
GW 1 21 -half 0 h half 0 h 1e-3
GE 0
EX 0 1 11 0 1 0
FR 0 1 0 0 14.1 0
EN
"""


def _small_example(tmp_path):
    adapter = _adapter()
    path = tmp_path / "small.nec"
    path.write_text(SMALL)
    cls = builder_from_file(str(path))
    return cls, adapter._make_example("user.small", cls, defer_hints=True)


def _spy(ex, seen):
    def solve(req, cancel=None):
        out = ex.momwire_solve(req, cancel=cancel)
        seen.append((float(req.get("sy_len", 10.4)), out["z_in_im"]))
        return out

    return solve


def test_the_optimizer_moves_a_sy_knob_and_the_derived_symbol_follows(tmp_path):
    from antennaknobs.web.optimize import optimize

    cls, ex = _small_example(tmp_path)
    seen: list = []
    base = {"geometry": "user.small", "measurement_freq_mhz": 14.1, "sy_len": 10.4}
    res = optimize(
        base,
        [{"name": "sy_len", "min": 9.5, "max": 10.8}],
        "resonance",
        solve_fn=_spy(ex, seen),
        max_evals=8,
    )
    lens = {v for v, _ in seen}
    assert len(lens) >= 2
    # The knob reached the solve: different lengths, different reactances.
    assert len({x for _, x in seen}) == len(lens)
    assert res["objective_after"] < res["objective_before"]
    best = res["params"]["sy_len"]
    wire = cls(dict(cls.default_params, sy_len=best)).build_wires()[0]
    assert (wire.p0[0], wire.p1[0]) == (-best / 2, best / 2)  # half = len/2


def test_the_tracker_moves_a_sy_knob_through_the_same_solve(tmp_path):
    from antennaknobs.web.tracker import Tracker

    cls, ex = _small_example(tmp_path)
    seen: list = []
    tr = Tracker(
        {
            "geometry": "user.small",
            "measurement_freq_mhz": 14.1,
            "sy_len": 10.4,
            "sy_h": 10.0,
        },
        [{"name": "sy_len", "min": 9.5, "max": 10.8}],
        "resonance",
        solve_fn=_spy(ex, seen),
    )
    st = tr.start("sy_h", 10.0)
    assert st["status"] == "tracking", st
    first = st["params"]["sy_len"]
    assert 9.5 <= first <= 10.8 and first != 10.4
    st = tr.tick(10.5)  # drag the height; the tracker re-holds the length
    assert st["status"] == "tracking", st
    held = st["params"]["sy_len"]
    assert len({v for v, _ in seen}) >= 3
    wire = cls(dict(cls.default_params, sy_len=held, sy_h=10.5)).build_wires()[0]
    assert (wire.p1[0], wire.p1[2]) == (held / 2, 10.5)  # half = len/2
