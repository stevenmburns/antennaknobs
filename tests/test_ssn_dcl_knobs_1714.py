"""AK#1714: the dcl constants a SimNEC ``.ssn``'s NEC cards read are knobs.

The two driving circuits are AC6LA's, in ``tests/fixtures/ssn_dcl_knobs_1714``
(provenance in its README). What is pinned here:

- SimNEC's expression rules, row by row against the values SimNEC 5.3 itself
  printed for the probe circuits (`SIMNEC_MEASURED`), and the refusals of
  everything outside the subset read;
- the classification (`simnec_import.classify_dcl`): spellings, comments,
  the ``dcl_`` / ``tmp_`` params;
- default identity: the design at its default knob values builds exactly the
  knobs-off import (the whole-corpus version is
  ``scripts/census_dcl_knobs_1714.py``);
- a knob move equals the same file with that one ``dcl`` value edited by
  hand, imported with knobs off -- and, for the Yagi, a block of plain
  numbers with no dcl at all; the helper that checks it fails when the
  override path is switched off (the negative control), and a moved knob
  moves Z on momwire;
- refusals by name (topology, zero length, an undefined name), and files
  without dcl constants building exactly as before.
"""

from __future__ import annotations

import importlib
import math
import re
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from test_simnec_import import _ssn

import antennaknobs.file_designs as file_designs
import antennaknobs.simnec_import as simnec_import
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import _ssn_circuit, builder_from_file
from antennaknobs.simnec_import import classify_dcl, parse_ssn

FIXTURES = Path(__file__).parent / "fixtures" / "ssn_dcl_knobs_1714"
YAGI = "3el-20m-yagi-sy.ssn"
HALF_SQUARES = "half-squares-sy.ssn"
CIRCUITS = (YAGI, HALF_SQUARES)


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def _design(name: str):
    return builder_from_file(str(FIXTURES / name))


def _adapter():
    importlib.import_module("antennaknobs.web.examples")
    from antennaknobs.web import adapter

    return adapter


def _write(tmp_path, text: str, name: str = "t.ssn") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _edit_dcl(text: str, spelling: str, literal: str) -> str:
    """``text`` with the one uncommented ``dcl spelling = ...;`` set to
    ``literal``: the hand edit a knob move must equal."""
    pat = re.compile(rf"(\bdcl\s+{re.escape(spelling)}\s*=\s*)([^;\n]+?)(\s*;)")
    hits = [
        m
        for m in pat.finditer(text)
        if "//" not in text[text.rfind("\n", 0, m.start()) + 1 : m.start()]
    ]
    assert len(hits) == 1, spelling
    m = hits[0]
    return text[: m.start(2)] + literal + text[m.end(2) :]


def _frozen(cls, text: str, name: str):
    """Wires and network of ``text`` imported with knobs OFF (no overrides):
    the reference a knob is compared against, never the knob path itself."""
    circuit = _ssn_circuit(text, name)
    wires = cls.auto_mesh(cls(), list(circuit.deck.wire_tuples(specs=True)))
    return wires, circuit.network()


def _moved(sym):
    return sym.default + 1 if sym.integer else sym.default * 1.1


def _assert_move_is_hand_edit(cls, text: str, name: str, sym, value) -> None:
    """Moving ``sym`` to ``value`` builds exactly the hand-edited file, AND
    moves the geometry or the network -- so a knob that silently did nothing
    cannot pass by also leaving the hand-edited reference alone."""
    moved = cls(dict(cls.default_params, **{sym.param: value}))
    wires, net = moved.build_wires(), moved.build_network()
    hand_w, hand_n = _frozen(cls, _edit_dcl(text, sym.spelling, repr(value)), name)
    assert wires == hand_w and repr(wires) == repr(hand_w)
    assert net == hand_n
    base = cls()
    assert (wires, net) != (base.build_wires(), base.build_network()), (
        f"moving {sym.param} changed nothing"
    )


def _equ(text: str) -> str:
    """The NETWORK script holding the NEC2 block."""
    _, infos, pos = simnec_import._nec_block(text, "t")
    return infos[pos][1]["equ"]


def _one_wire(dcls: str, field: str, *, fr: str = "FR 0 1 0 0 7.1 0") -> str:
    """A dipole whose top end's z is ``field``, below a script with ``dcls``."""
    return _ssn(
        f"""//t
P1 w1 gnd;
P2 w2 gnd;
{dcls}
NEC2
GW 1 11 0 -5 10 0 5 {field} 0.0005
{fr}
EX 0 1 6 0 1 0
NECEND"""
    )


def _value(dcls: str, field: str) -> float:
    return parse_ssn(_one_wire(dcls, field), network=True).deck.wires[0].p2[2]


# -- SimNEC's expression rules, as SimNEC printed them ----------------------

# Each row: (script lines, card field, the value SimNEC 5.3 (legacyNEC2C)
# wrote into the deck it constructed, as %e with 7 significant digits).
# Source: scratch/simnec-expr-probe/probe{A_trig,B_ops}.ssn, SimNEC's decks
# captured as captured-141420.nec and captured-141434.nec. Compared to 5e-7
# relative, the precision SimNEC printed.
SIMNEC_MEASURED = [
    # probe A: trig is RADIANS (4nec2's SY trig is degrees), and the
    # built-in constants.
    ("dcl p = Sin(30);", "p", -0.9880316),
    ("dcl p = Sin(Pi/6);", "p", 0.5),
    ("dcl p = Cos(60);", "p", -0.9524130),
    ("dcl p = Tan(45);", "p", 1.619775),
    ("dcl p = Atan(1);", "p", 0.7853982),
    ("dcl p = Asin(0.5);", "p", 0.5235988),
    ("dcl p = Sqrt(2);", "p", 1.414214),
    ("dcl p = Pi;", "p", 3.141593),
    ("dcl p = mpf;", "p", 0.3048),
    ("dcl p = fpm;", "p", 3.280840),
    # probe B: operators, suffixes, references.
    ("dcl p = -2^2;", "p", 4.0),  # unary minus binds tighter than ^
    ("dcl p = 2^3^2;", "p", 64.0),  # ^ groups LEFT
    ("dcl p = 2**3;", "p", 8.0),
    ("dcl p = 10/4;", "p", 2.5),  # true division
    ("dcl p = 7%3;", "p", 1.0),
    ("dcl p = Int(2.7);", "p", 2.0),
    ("dcl p = Int(-2.7);", "p", -2.0),  # Int truncates toward zero
    ("dcl p = 1.5u*1e6;", "p", 1.5),
    ("dcl p = 1m*1000;", "p", 1.0),  # m is milli, not metres
    ("dcl p = 2k/1000;", "p", 2.0),
    ("dcl p = 2.5E-1;", "p", 0.25),
    ("dcl q = Int(2.7); dcl p = q*3;", "p", 6.0),  # a dcl naming a dcl
    ("$t = 3; dcl p = $t*2;", "p", 6.0),  # a $ temporary
    ("dcl p = 2*3+4;", "p", 10.0),
    ("dcl p = 2+3*4;", "p", 14.0),
]


@pytest.mark.parametrize(("dcls", "field", "simnec"), SIMNEC_MEASURED)
def test_expression_matches_what_simnec_printed(dcls, field, simnec):
    assert math.isclose(_value(dcls, field), simnec, rel_tol=5e-7, abs_tol=1e-12)


def test_a_card_field_is_an_expression_too():
    # The field itself, not only a dcl: SimNEC evaluates both the same way.
    assert _value("dcl a = 2;", "-a^2") == 4.0
    assert _value("dcl a = 3;", "a*mpf+5m") == 3 * 0.3048 + 0.005


def test_the_measured_conventions_sit_in_one_place(monkeypatch):
    """Every convention the probes measured is one field of `ANVIL`; flipping
    it flips the answer, so a re-measurement is a one-line change."""
    rules = simnec_import.ANVIL
    assert (rules.trig_unit, rules.unary_over_power, rules.power_assoc) == (
        "radians",
        True,
        "left",
    )
    assert (rules.int_rounding, rules.builtins_case_sensitive) == ("trunc", True)
    monkeypatch.setattr(simnec_import, "ANVIL", replace(rules, trig_unit="degrees"))
    assert math.isclose(_value("dcl p = Sin(30);", "p"), 0.5)
    monkeypatch.setattr(simnec_import, "ANVIL", replace(rules, power_assoc="right"))
    assert _value("dcl p = 2^3^2;", "p") == 512.0
    monkeypatch.setattr(simnec_import, "ANVIL", replace(rules, unary_over_power=False))
    assert _value("dcl p = -2^2;", "p") == -4.0


# Conventions the probes have NOT settled: the rows pin today's choice, and
# each names what would change it.
UNMEASURED = [
    # TODO(AK#1714): measure -7%3 in SimNEC. Java's % (fmod) gives -1; a
    # floor modulus would give 2.
    ("dcl p = -7%3;", "p", -1.0),
]


@pytest.mark.parametrize(("dcls", "field", "expected"), UNMEASURED)
def test_unmeasured_conventions_pin_todays_choice(dcls, field, expected):
    assert _value(dcls, field) == expected


@pytest.mark.parametrize(
    ("dcls", "field", "message"),
    [
        # Built-in names are case-sensitive: SimNEC refused probeC_case.ssn's
        # `sin(30)` / `SIN(30)` with "Missing Method Declaration (or
        # inconsistent number of args) (maybe: 'Sin' ...Capitalization)".
        ("dcl p = sin(30);", "p", r"no function sin\(...\).*did you mean 'Sin'"),
        ("dcl p = SIN(30);", "p", r"no function SIN\(...\).*did you mean 'Sin'"),
        ("dcl p = SQRT(4);", "p", r"did you mean 'Sqrt'"),
        ("", "PI", r"names 'PI', which the script never defines .*did you mean 'Pi'"),
        ("", "MPF", r"did you mean 'mpf'"),
        ("dcl p = Log10(2);", "p", r"the function Log10\(...\) is not read"),
        ("dcl p = 1g;", "p", "wire gauge"),
        ("dcl p = 0+j50;", "p", "complex value"),
        ("dcl a = 1; dcl b = 2;", "a|||b", "'|||b' is SimNEC syntax"),
        ("dcl a = 1;", "a/_45", "rotate operator"),
        ("dcl a = 2;", "a^-1", "'\\^-' is an Anvil suffix operator"),
        ("dcl a = 2;", "G.MHz", "'.MHz' is SimNEC syntax"),
        ("dcl a = -4;", "Sqrt(a)", r"Sqrt\(-4\) failed"),
        ("dcl a = -8;", "a^(1/3)", "not a real number"),
        ("dcl a = b*2; dcl b = 3;", "a", "reads 'b' before the script defines it"),
        ("dcl a = 1; a = 2;", "a", "assigns 2 times"),
        ("at(finalValue) { dcl a = 3; }", "a", "outside any { } block"),
        ("if (x) $a = 3;", "$a", "does not set as a constant"),
        ("dcl a = 1;", "A", "names 'A', which the script never defines"),
    ],
)
def test_outside_the_subset_is_refused_by_name(dcls, field, message):
    with pytest.raises(ValueError, match=message):
        parse_ssn(_one_wire(dcls, field), network=True)


def test_names_are_case_sensitive():
    assert _value("dcl DY = 3; dcl dy = 4;", "DY*10+dy") == 34.0
    # A script constant may be spelled like 4nec2's `pi`; SimNEC's is `Pi`.
    assert _value("dcl pi = 3;", "pi+Pi") == 3 + math.pi


# -- classification and what the design publishes ----------------------------


def test_yagi_seven_commented_constants_are_knobs():
    syms = {s.name: s for s in classify_dcl(_text(YAGI))}
    assert list(syms) == ["hgh", "len", "rlen", "rdis", "dlen", "ddis", "rad"]
    assert {s.kind for s in syms.values()} == {"knob"}
    assert syms["hgh"].default == 50 * 0.3048
    assert syms["hgh"].label == "Height (50 feet)  [was hgh = 50ft]"
    assert syms["len"].expr == "2.5601*2"
    cls = _design(YAGI)
    ui = cls.default_params["ui_params"]
    params = [k for k in cls.default_params if k.startswith("dcl_")]
    assert params == [f"dcl_{n}" for n in syms]
    # The knob shows the script's spelling; the // comment is the tooltip.
    assert ui["dcl_len"] == {
        "label": "len",
        "description": "Driven element half-length",
    }
    note = ui["notes"]
    assert "7 dcl constants are knobs (dcl_hgh, dcl_len" in note
    # `FR 0 0 0 0 freq 0`: freq's dcl is commented out; SimNEC's FR is
    # advisory, so the card is dropped, and the Generator sets 14.2 MHz.
    assert "FR card not read: FR\t0\t0\t0\t0\tfreq\t0 (names freq" in note
    assert cls.default_params["freq"] == 14.2
    # The dcl lines are applied now, so no longer listed as not applied.
    assert "dcl hgh" not in note


def test_half_squares_mixed_case_and_load_constants():
    syms = {s.name: s for s in classify_dcl(_text(HALF_SQUARES))}
    assert list(syms) == ["dy", "hgh", "rad", "len", "sln", "Xc", "Cu"]
    assert syms["Xc"].reaches == {"LD"} and syms["Cu"].reaches == {"LD"}
    assert syms["Xc"].param == "dcl_Xc"  # case kept: SimNEC names are
    cls = _design(HALF_SQUARES)
    note = cls.default_params["ui_params"]["notes"]
    # `dcl R_4 = 0+j50` feeds only an N-block R component: not a card
    # constant, so it stays unapplied, as before AK#1714.
    assert "dcl R_4 = 0+j50" in note
    assert "dcl_R_4" not in cls.default_params


def test_the_adapter_publishes_the_knobs_with_their_spellings():
    ex = _adapter()._make_example("user.t", _design(YAGI), defer_hints=True)
    specs = {p.name: p for p in ex.param_schema}
    assert specs["dcl_hgh"].label == "hgh"
    assert specs["dcl_hgh"].description == "Height (50 feet)  [was hgh = 50ft]"
    assert specs["dcl_rad"].label == "rad"


def test_derived_constant_follows_and_a_temporary_is_a_tmp_knob(tmp_path):
    text = _ssn(
        """//t
P1 w1 gnd;
P2 w2 gnd;
dcl hgh = 10;  // Height
$half = 2.5;
dcl top = hgh + $half;
NEC2
GW 1 11 0 -5 hgh 0 5 hgh 0.0005
GW 2 3 0 5 hgh 0 5 top 0.0005
EX 0 1 6 0 1 0
NECEND"""
    )
    syms = {s.name: s for s in classify_dcl(text)}
    assert (syms["hgh"].kind, syms["$half"].kind, syms["top"].kind) == (
        "knob",
        "knob",
        "derived",
    )
    assert syms["$half"].param == "tmp_half"
    cls = builder_from_file(str(_write(tmp_path, text)))
    wires = cls(dict(cls.default_params, dcl_hgh=12.0, tmp_half=1.0)).build_wires()
    assert wires[1].p1[2] == 13.0  # top = hgh + $half follows both knobs


# -- default identity and moves ---------------------------------------------


@pytest.mark.parametrize("name", CIRCUITS)
def test_default_values_reproduce_the_import_exactly(name):
    cls = _design(name)
    b = cls()
    wires, net = b.build_wires(), b.build_network()
    ref_w, ref_n = _frozen(cls, _text(name), name)
    assert wires == ref_w and repr(wires) == repr(ref_w)  # -0.0 is not 0.0
    assert net == ref_n
    # The instance's deck came through the override re-parse, not the import.
    deck = b.file_deck_parsed
    assert deck == cls.file_deck_parsed and deck is not cls.file_deck_parsed
    assert cls.file_sy_knobs._parse.cache_info().misses >= 1


@pytest.mark.parametrize("name", CIRCUITS)
def test_each_knob_move_equals_a_hand_edited_file(name):
    cls = _design(name)
    for sym in cls.file_sy_knobs.symbols:
        _assert_move_is_hand_edit(cls, _text(name), name, sym, _moved(sym))


def test_yagi_move_equals_a_block_of_plain_numbers():
    """The reference with no dcl at all: the Yagi's cards with each name
    replaced by its value (the moved one moved), so the import reads a deck
    of plain numbers through the path every .ssn took before AK#1714."""
    cls = _design(YAGI)
    values = {s.name: s.default for s in cls.file_sy_knobs.symbols}
    values["len"] = 5.5
    text = _text(YAGI)
    for line in re.findall(r"(?m)^dcl .*$", text):
        text = text.replace(line, "")
    # The FR card naming the undefined `freq` goes too (the knob path drops
    # it), so the block names nothing at all.
    text = re.sub(r"(?m)^FR\t.*\bfreq\b.*$", "", text)
    for n in sorted(values, key=len, reverse=True):
        text = re.sub(rf"(?<![\w.])-{n}\b", repr(-values[n]), text)
        text = re.sub(rf"(?<![\w.$])\b{n}\b(?=\s)", repr(values[n]), text)
    assert (
        simnec_import._dcl_cards(
            simnec_import._Script(_equ(text), YAGI), YAGI
        ).constants
        == ()
    )
    plain_w, plain_n = _frozen(cls, text, YAGI)
    moved = cls(dict(cls.default_params, dcl_len=5.5))
    assert moved.build_wires() == plain_w
    assert moved.build_network() == plain_n
    assert moved.build_wires()[1].p0[0] == -5.5


def test_negative_control_the_move_check_fails_without_the_override_path(
    monkeypatch,
):
    """Switch the overrides off at the seam the knobs parse through: the move
    helper must then fail, or it proves nothing."""
    real = file_designs.parse_ssn

    def no_overrides(text, **kw):
        kw.pop("dcl_overrides", None)
        return real(text, **kw)

    monkeypatch.setattr(file_designs, "parse_ssn", no_overrides)
    cls = _design(YAGI)  # a new cache, parsed through the patched seam
    sym = cls.file_sy_knobs.symbols[1]
    with pytest.raises(AssertionError):
        _assert_move_is_hand_edit(cls, _text(YAGI), YAGI, sym, _moved(sym))


def test_a_moved_knob_moves_z_as_the_hand_edited_file_does(tmp_path):
    """Z, not just geometry, on momwire: the knob-moved Yagi and the
    hand-edited file, each through `builder_from_file`, solve bit-identically,
    and differently from the defaults."""
    cls = _design(YAGI)
    edited = _write(tmp_path, _edit_dcl(_text(YAGI), "len", "5.3"), YAGI)
    z_knob = MomwireEngine(cls(dict(cls.default_params, dcl_len=5.3)), ground=None)
    z_hand = MomwireEngine(builder_from_file(str(edited))(), ground=None)
    z_default = MomwireEngine(cls(), ground=None)
    zk, zh, zd = (np.asarray(e.impedance()) for e in (z_knob, z_hand, z_default))
    assert np.array_equal(zk, zh)
    assert not np.array_equal(zk, zd)


def test_wire_material_is_the_deck_ld5_never_both():
    """The Yagi writes both `NECOptions.mhosPerMeter = 2.49E+07` and `LD 5`
    cards; the Half-Squares' LD 5 names a knob (`Cu`) beside its own
    mhosPerMeter. The deck's LD 5 is the one material, and moving `Cu` moves
    it: nothing is applied twice."""
    yagi = _design(YAGI)()
    assert {w.spec.conductivity for w in yagi.build_wires()} == {2.49e7}
    cls = _design(HALF_SQUARES)
    moved = cls(dict(cls.default_params, dcl_Cu=3.0e7))
    assert {w.spec.conductivity for w in moved.build_wires()} == {3.0e7}


# -- refusals -----------------------------------------------------------------


def test_topology_change_is_refused_by_name_and_the_design_keeps_working():
    cls = _design(HALF_SQUARES)
    with pytest.raises(ValueError) as exc:
        cls(dict(cls.default_params, dcl_dy=0.0)).build_wires()
    msg = str(exc.value)
    assert "dcl_dy = 0 (the file has 12.678)" in msg
    assert "wire 1 (tag 1) end 1 now meets wire 4 (tag 4) end 1" in msg
    assert "topology is frozen" in msg
    with pytest.raises(ValueError, match="dcl_sln = 31.0444 .*from above the ground"):
        cls(dict(cls.default_params, dcl_sln=31.0444)).build_wires()
    # The next good value builds.
    assert len(cls(dict(cls.default_params, dcl_dy=13.0)).build_wires()) == 6


def test_zero_length_wire_is_refused_by_name():
    cls = _design(YAGI)
    with pytest.raises(
        ValueError, match=r"dcl_len = 0 .*wire 2 \(tag 2\) would have zero length"
    ):
        cls(dict(cls.default_params, dcl_len=0.0)).build_network()


def test_an_undefined_name_in_the_geometry_is_refused_by_name(tmp_path):
    # AC6LA's Yagi with the radius's dcl commented out, as its freq's is.
    text = _text(YAGI).replace("dcl rad = .005", "//dcl rad = .005")
    with pytest.raises(ValueError, match="names 'rad', which the script never"):
        builder_from_file(str(_write(tmp_path, text, YAGI)))


def test_parse_ssn_refuses_an_override_the_cards_do_not_read():
    with pytest.raises(ValueError, match="no dcl constant 'HGH'"):
        parse_ssn(_text(YAGI), dcl_overrides={"HGH": 10.0})
    with pytest.raises(ValueError, match="not a finite number"):
        parse_ssn(_text(YAGI), dcl_overrides={"hgh": math.nan})


# -- files without dcl constants: exactly as before ---------------------------


@pytest.mark.parametrize(
    "path",
    sorted(
        p
        for p in (Path(__file__).parent / "fixtures").rglob("*.ssn")
        if p.parent != FIXTURES
    ),
    ids=lambda p: p.name,
)
def test_a_circuit_without_dcl_constants_publishes_no_knobs(path):
    cls = builder_from_file(str(path))
    assert cls.file_sy_knobs is None
    assert set(cls.default_params) == {"freq", "design_freq", "ui_params"}
    assert "dcl" not in (cls.default_params["ui_params"].get("notes") or "")
    assert cls.file_deck_parsed is cls().file_deck_parsed


def test_nec2_and_necend_lines_may_carry_a_comment():
    plain = parse_ssn(_one_wire("", "10"), network=True)
    text = _one_wire("", "10").replace("NEC2\n", "NEC2  // ======\n")
    text = text.replace("NECEND", "NECEND  // ======").replace(
        "EX 0 1 6 0 1 0", "EX 0 1 6 0 1 0  // the feed"
    )
    assert parse_ssn(text, network=True).deck == plain.deck
