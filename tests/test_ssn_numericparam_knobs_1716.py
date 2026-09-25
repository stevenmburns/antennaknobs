"""AK#1716: a SimNEC ``.ssn``'s element parameters are knobs.

A bare name in the NETWORK script (no ``dcl``, no ``$``) is a parameter of
the circuit element, and SimNEC saves its value on the element as a
``<numericParam>``. The driving circuits are AC6LA's, in
``tests/fixtures/ssn_numericparam_1716`` (provenance in its README). What is
pinned here, on the AK#1714 machinery (`test_ssn_dcl_knobs_1714`):

- the knob lists: ``par_len`` at 10.2, and ``par_segs`` at 30, an integer
  knob that reaches ``$GW_1.JamSegments(segs)`` rather than a card;
- default identity against the knobs-off import;
- a ``len`` move equals the file with the numericParam's ``<v>`` edited in
  the XML, and a ``segs`` move the file with ``JamSegments(segs)`` rewritten
  as a literal, both imported with knobs off; the move check fails with the
  override path switched off (the negative control);
- inputs told from outputs: a parameter the script assigns is refused by
  name when the cards read it, as is a name with no parameter at all;
- refusals by name: a JamSegments count of 0 or 2.5, an unknown
  ``Conductivities.<name>``.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pytest
from test_simnec_import import _ssn

import antennaknobs.file_designs as file_designs
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import _ssn_circuit, builder_from_file
from antennaknobs.simnec_import import classify_dcl, parse_ssn

FIXTURES = Path(__file__).parent / "fixtures" / "ssn_numericparam_1716"
VARLEN = "DipoleVarLen.ssn"
VARSEGS = "DipoleVarLenSegs.ssn"
CIRCUITS = (VARLEN, VARSEGS)


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _design(name: str):
    return builder_from_file(str(FIXTURES / name))


def _write(tmp_path, text: str, name: str = "t.ssn") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _edit_param(text: str, name: str, literal: str) -> str:
    """``text`` with the element's saved value of parameter ``name`` set to
    ``literal`` in the XML: the hand edit a ``par_`` knob move must equal."""
    pat = re.compile(
        rf"(<numericParam>{re.escape(name)}</numericParam>\s*<v>)([^<]*)(</v>)"
    )
    hits = list(pat.finditer(text))
    assert len(hits) == 1, name
    m = hits[0]
    return text[: m.start(2)] + literal + text[m.end(2) :]


def _edit_jam(text: str, literal: str) -> str:
    """``text`` with ``JamSegments(segs)`` written as ``JamSegments(literal)``."""
    assert text.count("$GW_1.JamSegments(segs);") == 1
    return text.replace("$GW_1.JamSegments(segs);", f"$GW_1.JamSegments({literal});")


def _frozen(cls, text: str, name: str):
    """Wires and network of ``text`` imported with knobs OFF (no overrides):
    the reference a knob is compared against, never the knob path itself."""
    circuit = _ssn_circuit(text, name)
    wires = cls.auto_mesh(cls(), list(circuit.deck.wire_tuples(specs=True)))
    return wires, circuit.network()


def _assert_move_is_hand_edit(cls, param: str, value, edited: str, name: str):
    """Moving ``param`` to ``value`` builds exactly the hand-edited file, AND
    moves the geometry or the network -- so a knob that silently did nothing
    cannot pass by also leaving the hand-edited reference alone."""
    moved = cls(dict(cls.default_params, **{param: value}))
    wires, net = moved.build_wires(), moved.build_network()
    hand_w, hand_n = _frozen(cls, edited, name)
    assert wires == hand_w and repr(wires) == repr(hand_w)
    assert net == hand_n
    base = cls()
    assert (wires, net) != (base.build_wires(), base.build_network()), (
        f"moving {param} changed nothing"
    )
    return wires


# -- what the two files publish ----------------------------------------------


def test_dipole_var_len_publishes_len_at_its_saved_value():
    syms = classify_dcl(_text(VARLEN))
    assert [(s.name, s.kind, s.default, s.param) for s in syms] == [
        ("len", "knob", 10.2, "par_len")
    ]
    cls = _design(VARLEN)
    assert cls.default_params["par_len"] == 10.2
    ui = cls.default_params["ui_params"]
    assert ui["par_len"] == {"label": "len"}
    note = ui["notes"]
    assert "1 element parameter is a knob (par_len)." in note
    # `len;` and JamSegments(30) are applied, so nothing is reported unapplied.
    assert "not applied" not in note
    wire = cls().build_wires()[0]
    assert (wire.p0, wire.p1) == ((0.0, 0.0, 9.0), (0.0, 10.2, 9.0))


def test_dipole_var_len_segs_publishes_an_integer_segment_knob():
    syms = {s.name: s for s in classify_dcl(_text(VARSEGS))}
    assert list(syms) == ["len", "segs"]
    assert syms["segs"].integer and syms["segs"].default == 30
    assert syms["segs"].reaches == {"GW"}
    cls = _design(VARSEGS)
    assert (cls.default_params["par_len"], cls.default_params["par_segs"]) == (
        10.2,
        30,
    )
    assert type(cls.default_params["par_segs"]) is int
    note = cls.default_params["ui_params"]["notes"]
    assert "2 element parameters are knobs (par_len, par_segs)." in note
    assert "not applied" not in note
    assert cls.file_deck_parsed.wires[0].n_seg == 30
    assert cls.file_deck_parsed.pinned_wires


def test_copper_is_simnecs_named_conductivity():
    wires = _design(VARLEN)().build_wires()
    assert {w.spec.conductivity for w in wires} == {1.0 / 1.74e-8}


# -- default identity and moves ---------------------------------------------


@pytest.mark.parametrize("name", CIRCUITS)
def test_default_values_reproduce_the_import_exactly(name):
    cls = _design(name)
    b = cls()
    wires, net = b.build_wires(), b.build_network()
    ref_w, ref_n = _frozen(cls, _text(name), name)
    assert wires == ref_w and repr(wires) == repr(ref_w)
    assert net == ref_n
    deck = b.file_deck_parsed
    assert deck == cls.file_deck_parsed and deck is not cls.file_deck_parsed
    assert cls.file_sy_knobs._parse.cache_info().misses >= 1


@pytest.mark.parametrize("name", CIRCUITS)
def test_a_len_move_equals_the_saved_value_edited_in_the_xml(name):
    cls = _design(name)
    edited = _edit_param(_text(name), "len", "11.5")
    wires = _assert_move_is_hand_edit(cls, "par_len", 11.5, edited, name)
    assert wires[0].p1 == (0.0, 11.5, 9.0)


def test_a_segs_move_equals_jamsegments_written_as_that_count():
    cls = _design(VARSEGS)
    for n in (1, 31, 44):
        edited = _edit_jam(_text(VARSEGS), str(n))
        wires = _assert_move_is_hand_edit(cls, "par_segs", n, edited, VARSEGS)
        assert wires[0].n_seg == n


def test_a_segs_move_equals_the_saved_value_edited_too():
    """The same move against the other hand edit: the parameter's saved value."""
    cls = _design(VARSEGS)
    edited = _edit_param(_text(VARSEGS), "segs", "44")
    _assert_move_is_hand_edit(cls, "par_segs", 44, edited, VARSEGS)


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
    cls = _design(VARSEGS)  # a new cache, parsed through the patched seam
    with pytest.raises(AssertionError):
        _assert_move_is_hand_edit(
            cls, "par_len", 11.5, _edit_param(_text(VARSEGS), "len", "11.5"), VARSEGS
        )
    with pytest.raises(AssertionError):
        _assert_move_is_hand_edit(
            cls, "par_segs", 31, _edit_jam(_text(VARSEGS), "31"), VARSEGS
        )


def test_a_moved_len_moves_z_as_the_hand_edited_file_does(tmp_path):
    cls = _design(VARLEN)
    edited = _write(tmp_path, _edit_param(_text(VARLEN), "len", "10.6"), VARLEN)
    z_knob = MomwireEngine(cls(dict(cls.default_params, par_len=10.6)), ground=None)
    z_hand = MomwireEngine(builder_from_file(str(edited))(), ground=None)
    z_default = MomwireEngine(cls(), ground=None)
    zk, zh, zd = (np.asarray(e.impedance()) for e in (z_knob, z_hand, z_default))
    assert np.array_equal(zk, zh)
    assert not np.array_equal(zk, zd)


# -- inputs, outputs, and names with no parameter ----------------------------


def test_a_parameter_the_script_assigns_is_an_output_and_refused_by_name():
    # AC6LA's 3-el Yagi assigns its SegCnt parameter inside `at(finalValue)`;
    # the same shape here makes `len` a result SimNEC computes, not an input.
    text = _text(VARLEN).replace(
        "$GW_1.JamSegments(30);",
        "$GW_1.JamSegments(30);\nat(finalValue) {\n\tlen = 3;\n}",
    )
    with pytest.raises(
        ValueError,
        match=r"names 'len', a parameter of the element that the script assigns "
        r"\('len = 3'\), so an output",
    ):
        parse_ssn(text)
    with pytest.raises(ValueError, match="so an output"):
        classify_dcl(text)


def test_a_name_with_no_parameter_is_still_refused_by_name():
    text = _text(VARLEN).replace(
        "<numericParam>len</numericParam>", "<numericParam>length</numericParam>"
    )
    with pytest.raises(
        ValueError,
        match=r"names 'len', which the script never defines .* or saves as an "
        r"element parameter",
    ):
        parse_ssn(text)


def _one_wire(pre: str, field: str, params: dict[str, str], post: str = "") -> str:
    text = _ssn(
        f"""//t
P1 w1 gnd;
P2 w2 gnd;
{pre}
NEC2
GW 1 11 0 -5 10 0 5 {field} 0.0005
FR 0 1 0 0 7.1 0
EX 0 1 6 0 1 0
NECEND
{post}"""
    )
    saved = "".join(
        f"<p><numericParam>{k}</numericParam><v>{v}</v></p>" for k, v in params.items()
    )
    return text.replace("<escapeHatch/>", "<escapeHatch/>" + saved, 1)


def test_a_temporary_is_never_a_parameter():
    # SimNEC Manual, "Variables and Basic Parameters": a `$` name is a
    # temporary; only a name without one becomes a parameter.
    with pytest.raises(ValueError, match=r"names '\$h', which the script never"):
        parse_ssn(_one_wire("", "$h", {"$h": "12"}))


def test_a_dcl_constant_reading_a_parameter_follows_it(tmp_path):
    text = _one_wire("h;  // Height\ndcl top = h + 2;", "top", {"h": "10"})
    syms = {s.name: s for s in classify_dcl(text)}
    assert (syms["h"].kind, syms["top"].kind) == ("knob", "derived")
    assert syms["h"].param == "par_h" and syms["h"].label == "Height"
    cls = builder_from_file(str(_write(tmp_path, text)))
    assert (
        "1 element parameter is a knob (par_h); 1 derived"
        in (cls.default_params["ui_params"]["notes"])
    )
    assert cls(dict(cls.default_params, par_h=7.0)).build_wires()[0].p1[2] == 9.0


def test_a_file_mixing_both_speaks_of_script_constants(tmp_path):
    text = _one_wire("h;\ndcl w = 5;", "h+w", {"h": "5"})
    cls = builder_from_file(str(_write(tmp_path, text)))
    assert list(k for k in cls.default_params if k[:4] in ("par_", "dcl_")) == [
        "par_h",
        "dcl_w",
    ]
    assert (
        "2 script constants are knobs (par_h, dcl_w)"
        in (cls.default_params["ui_params"]["notes"])
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "carries no value"),
        ("(2.4+j319.8)", "complex value"),
        ("k*2", "is not a number"),
    ],
)
def test_a_saved_value_that_is_no_real_number_is_refused_by_name(value, message):
    with pytest.raises(ValueError, match=rf"parameter h = .*{message}"):
        parse_ssn(_one_wire("h;", "h", {"h": value}))


def test_segments_per_wavelength_may_name_a_parameter():
    # AC6LA's Synth examples: `NECOptions.segmentsPerWavelength = segsWL;`
    # with segsWL a parameter of 10. It feeds only the mesh note.
    text = _one_wire("NECOptions.segmentsPerWavelength = segsWL;", "10", {})
    with pytest.raises(ValueError, match="bad NECOptions.segmentsPerWavelength"):
        parse_ssn(text)
    text = _one_wire(
        "NECOptions.segmentsPerWavelength = segsWL;", "10", {"segsWL": "10"}
    )
    assert parse_ssn(text).seg_per_wl == 10
    assert classify_dcl(text) == ()


# -- refusals by name ---------------------------------------------------------


@pytest.mark.parametrize("saved", ["0", "2.5"])
def test_a_saved_segment_count_that_is_not_whole_and_positive_is_refused(saved):
    text = _edit_param(_text(VARSEGS), "segs", saved)
    with pytest.raises(
        ValueError,
        match=rf"JamSegments\(segs\).* asks for {saved} segments \(segs = {saved}\)"
        r"; JamSegments takes a whole count of 1 or more",
    ):
        parse_ssn(text)


@pytest.mark.parametrize("value", [0, 2.5])
def test_an_override_segment_count_that_is_not_whole_and_positive_is_refused(value):
    with pytest.raises(ValueError, match=rf"\(segs = {value:g}\)"):
        parse_ssn(_text(VARSEGS), dcl_overrides={"segs": value})


def test_the_segs_knob_at_zero_is_refused_naming_it():
    cls = _design(VARSEGS)
    with pytest.raises(
        ValueError, match=r"par_segs = 0 \(the file has 30\) is refused: .*segs = 0"
    ):
        cls(dict(cls.default_params, par_segs=0)).build_wires()
    assert cls(dict(cls.default_params, par_segs=12)).build_wires()[0].n_seg == 12


def test_a_jamsegments_count_naming_nothing_defined_is_refused_by_name():
    text = _text(VARSEGS).replace("JamSegments(segs)", "JamSegments(nsegs)")
    with pytest.raises(ValueError, match="JamSegments\\(nsegs\\).* names 'nsegs'"):
        parse_ssn(text)


def test_an_unknown_conductivity_name_is_refused_by_name():
    text = _text(VARLEN).replace("Conductivities.copper", "Conductivities.bogus")
    with pytest.raises(
        ValueError, match="names Conductivities.bogus, which SimNEC does not define"
    ):
        parse_ssn(text)


def test_parse_ssn_refuses_an_override_the_cards_do_not_read():
    with pytest.raises(ValueError, match="no dcl constant or element parameter 'LEN'"):
        parse_ssn(_text(VARLEN), dcl_overrides={"LEN": 10.0})
    with pytest.raises(ValueError, match="not a finite number"):
        parse_ssn(_text(VARLEN), dcl_overrides={"len": math.inf})
