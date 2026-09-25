"""AK#1734: a SimNEC ``.ssn``'s ``prm`` declarations and plain top-level
constant assignments are knobs.

``prm`` is Anvil's explicit form of the passive declaration that makes a name
a parameter of the circuit element (the Anvil manual, "Passive
Declaration"; SimNEC 2.6a1 added it). A plain ``name = value;`` at top level
is the implicit form of the same thing, with the script setting the value.
What is pinned here, on the AK#1714/AK#1716 machinery:

- AC6LA's DipoleVarLen written five ways (``len;``, ``prm len;``,
  ``prm len = 10.2;``, ``dcl len = 10.2;``, ``len = 10.2;``) gives one knob
  at 10.2, the same wires, network and impedance; the param names are
  ``par_len`` for an input (its value saved on the element), ``dcl_len`` for
  a dcl line, and ``prm_len`` for a parameter the script assigns;
- ``prm len,hei,fp;`` declares three inputs, three knobs;
- a ``prm_`` move equals the script line edited by hand, not the element's
  saved value (the script sets it on every run), and a saved value that
  disagrees with the script is reported;
- negative controls: a ``prm`` computed from other names follows rather
  than being a knob; a parameter assigned from an output (``Trap23 =
  R2.z;``), twice, or inside ``at(...) { }`` is refused by name when a card
  reads it; ``prm file[];`` and the ``prm num; prm runs; prm logLvl;``
  boilerplate change nothing.
"""

from __future__ import annotations

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
SAVED = "<p>\n                       <numericParam>len</numericParam>"


def _text() -> str:
    return (FIXTURES / VARLEN).read_text(encoding="utf-8")


def _written(stmt: str, *, saved: bool = True) -> str:
    """DipoleVarLen with its ``len;`` statement written as ``stmt``. With
    ``saved=False`` the element's ``len`` parameter is dropped too, as SimNEC
    drops a parameter nothing references any more (a ``dcl`` name is not
    one)."""
    text = _text()
    assert text.count("\nlen;\n") == 1
    text = text.replace("\nlen;\n", f"\n{stmt}\n")
    if not saved:
        start = text.index(SAVED)
        end = text.index("</p>", text.index("</sweepParam>", start)) + len("</p>")
        text = text[:start] + text[end:]
        assert "numericParam" not in text
    return text


def _write(tmp_path, text: str, name: str = VARLEN) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _design(tmp_path, text: str, name: str = VARLEN):
    return builder_from_file(str(_write(tmp_path, text, name)))


def _frozen(cls, text: str, name: str):
    """Wires and network of ``text`` imported with knobs OFF."""
    circuit = _ssn_circuit(text, name)
    wires = cls.auto_mesh(cls(), list(circuit.deck.wire_tuples(specs=True)))
    return wires, circuit.network()


def _edit_line(text: str, head: str, literal: str) -> str:
    """``text`` with the one ``<head> = <value>;`` script statement's value
    set to ``literal``: the hand edit a ``prm_`` move must equal."""
    pat = re.compile(rf"(\n{re.escape(head)}\s*=\s*)([^;\n]+)(;)")
    hits = list(pat.finditer(text))
    assert len(hits) == 1, head
    m = hits[0]
    return text[: m.start(2)] + literal + text[m.end(2) :]


def _edit_saved(text: str, name: str, literal: str) -> str:
    pat = re.compile(
        rf"(<numericParam>{re.escape(name)}</numericParam>\s*<v>)([^<]*)(</v>)"
    )
    hits = list(pat.finditer(text))
    assert len(hits) == 1, name
    m = hits[0]
    return text[: m.start(2)] + literal + text[m.end(2) :]


# -- one dipole, five spellings ---------------------------------------------

WAYS = [
    ("len;", True, "par_len"),
    ("prm len;", True, "par_len"),
    ("prm len = 10.2;", True, "prm_len"),
    ("dcl len = 10.2;", False, "dcl_len"),
    ("len = 10.2;", True, "prm_len"),
]


@pytest.mark.parametrize(("stmt", "saved", "param"), WAYS)
def test_every_spelling_publishes_one_knob_at_10_2(tmp_path, stmt, saved, param):
    text = _written(stmt, saved=saved)
    syms = classify_dcl(text)
    assert [(s.name, s.kind, s.default, s.param) for s in syms] == [
        ("len", "knob", 10.2, param)
    ]
    cls = _design(tmp_path, text)
    assert cls.default_params[param] == 10.2
    assert cls.default_params["ui_params"][param] == {"label": "len"}
    note = cls.default_params["ui_params"]["notes"]
    assert f"is a knob ({param})." in note
    # The declaration is read, so nothing is reported unapplied.
    assert "not applied" not in note
    assert "saved value" not in note


def test_every_spelling_builds_the_same_dipole_and_the_same_z(tmp_path):
    built = []
    for k, (stmt, saved, param) in enumerate(WAYS):
        text = _written(stmt, saved=saved)
        cls = _design(tmp_path, text, f"v{k}.ssn")
        b = cls()
        wires, net = b.build_wires(), b.build_network()
        # Bit for bit the file imported with knobs off, as in #1714/#1716.
        ref_w, ref_n = _frozen(cls, text, f"v{k}.ssn")
        assert wires == ref_w and repr(wires) == repr(ref_w)
        assert net == ref_n
        assert cls.file_sy_knobs._parse.cache_info().misses >= 1
        assert wires[0].p1 == (0.0, 10.2, 9.0)
        z = np.asarray(MomwireEngine(b, ground=None).impedance())
        built.append((repr(wires), net, z))
    first_w, first_n, first_z = built[0]
    for w, n, z in built[1:]:
        assert w == first_w
        assert n == first_n
        assert np.array_equal(z, first_z)


@pytest.mark.parametrize("stmt", ["prm len = 10.2;", "len = 10.2;"])
def test_an_assigned_parameter_moves_as_its_script_line_edited(tmp_path, stmt):
    text = _written(stmt)
    cls = _design(tmp_path, text)
    moved = cls(dict(cls.default_params, prm_len=11.5))
    wires, net = moved.build_wires(), moved.build_network()
    head = stmt.split("=")[0].strip()
    hand_w, hand_n = _frozen(cls, _edit_line(text, head, "11.5"), VARLEN)
    assert wires == hand_w and repr(wires) == repr(hand_w)
    assert net == hand_n
    assert wires[0].p1 == (0.0, 11.5, 9.0)
    assert cls().build_wires()[0].p1 == (0.0, 10.2, 9.0)


def test_negative_control_the_move_check_fails_without_the_override_path(
    tmp_path, monkeypatch
):
    real = file_designs.parse_ssn

    def no_overrides(text, **kw):
        kw.pop("dcl_overrides", None)
        return real(text, **kw)

    monkeypatch.setattr(file_designs, "parse_ssn", no_overrides)
    text = _written("len = 10.2;")
    cls = _design(tmp_path, text)
    moved = cls(dict(cls.default_params, prm_len=11.5)).build_wires()
    hand, _ = _frozen(cls, _edit_line(text, "len", "11.5"), VARLEN)
    assert moved != hand


def test_the_script_line_not_the_saved_value_sets_an_assigned_parameter(tmp_path):
    """SimNEC runs `len = 10.2;` before it reads the cards, so the element's
    saved value is overwritten on every run: an edit to it moves nothing, and
    when it disagrees with the script the note says so."""
    text = _edit_saved(_written("len = 10.2;"), "len", "10.3")
    circuit = parse_ssn(text)
    assert circuit.deck == parse_ssn(_written("len = 10.2;")).deck
    assert circuit.saved_param_notes == (
        "element parameter len's saved value 10.3 is not used: the script "
        "sets it ('len = 10.2' is 10.2)",
    )
    cls = _design(tmp_path, text)
    assert cls.default_params["prm_len"] == 10.2
    assert cls().build_wires()[0].p1 == (0.0, 10.2, 9.0)
    assert "saved value 10.3 is not used" in cls.default_params["ui_params"]["notes"]
    # Agreement is silent.
    assert parse_ssn(_written("len = 10.2;")).saved_param_notes == ()
    assert parse_ssn(_written("len = 10.2;", saved=False)).saved_param_notes == ()


# -- prm declarations ---------------------------------------------------------


def _one_wire(pre: str, fields: str, params: dict[str, str]) -> str:
    text = _ssn(
        f"""//t
P1 w1 gnd;
P2 w2 gnd;
{pre}
NEC2
GW 1 11 {fields} 0.0005
FR 0 1 0 0 7.1 0
EX 0 1 6 0 1 0
NECEND
"""
    )
    saved = "".join(
        f"<p><numericParam>{k}</numericParam><v>{v}</v></p>" for k, v in params.items()
    )
    return text.replace("<escapeHatch/>", "<escapeHatch/>" + saved, 1)


def test_one_prm_statement_declares_three_inputs(tmp_path):
    params = {"len": "10", "hei": "12", "fp": "1.5"}
    text = _one_wire("prm len,hei,fp;  // dims", "fp 0 hei fp len hei", params)
    syms = classify_dcl(text)
    assert [(s.name, s.kind, s.default, s.param, s.label) for s in syms] == [
        ("len", "knob", 10.0, "par_len", "dims"),
        ("hei", "knob", 12.0, "par_hei", "dims"),
        ("fp", "knob", 1.5, "par_fp", "dims"),
    ]
    cls = _design(tmp_path, text, "t.ssn")
    note = cls.default_params["ui_params"]["notes"]
    assert "3 element parameters are knobs (par_len, par_hei, par_fp)." in note
    assert "not applied" not in note
    w = cls(dict(cls.default_params, par_hei=7.0, par_fp=2.0)).build_wires()[0]
    assert (w.p0, w.p1) == ((2.0, 0.0, 7.0), (2.0, 10.0, 7.0))
    # Each moves as its saved value edited in the XML.
    for name, v in (("len", "11"), ("hei", "13"), ("fp", "2.5")):
        moved = cls(dict(cls.default_params, **{f"par_{name}": float(v)}))
        hand, _ = _frozen(cls, _edit_saved(text, name, v), "t.ssn")
        assert moved.build_wires() == hand


def test_a_prm_computed_from_another_name_follows_and_is_no_knob(tmp_path):
    # AC6LA's `prm wl = mps/G.MHz/1e6;` shape, on names this import reads.
    text = _one_wire(
        "prm f;\nprm wl = 300/f;", "0 -wl/4 10 0 wl/4 10", {"f": "7.5", "wl": "40"}
    )
    syms = {s.name: s for s in classify_dcl(text)}
    assert (syms["f"].kind, syms["f"].param) == ("knob", "par_f")
    assert (syms["wl"].kind, syms["wl"].param) == ("derived", "prm_wl")
    cls = _design(tmp_path, text, "t.ssn")
    assert "prm_wl" not in cls.default_params
    assert cls().build_wires()[0].p1 == (0.0, 10.0, 10.0)
    assert cls(dict(cls.default_params, par_f=15.0)).build_wires()[0].p1[1] == 5.0


def test_a_prm_computed_from_a_member_is_refused_by_name():
    text = _one_wire("prm wl = mps/G.MHz/1e6;", "0 0 10 0 wl 10", {"wl": "42.2"})
    with pytest.raises(
        ValueError,
        match=r"names 'wl', a parameter of the element that the script assigns "
        r"\('prm wl = mps/G.MHz/1e6'\), so an output",
    ):
        parse_ssn(text)


def test_a_plain_assignment_from_an_undefined_name_is_refused_by_name():
    text = _one_wire("wl = mps/GNMHz;", "0 0 10 0 wl 10", {})
    with pytest.raises(ValueError, match=r"'wl = mps/GNMHz' reads 'mps'"):
        parse_ssn(text)


def test_a_file_parameter_is_harmless():
    base = _written("len;")
    text = _written("prm file[]; len;")
    assert classify_dcl(text) == classify_dcl(base)
    assert parse_ssn(text) == parse_ssn(base)


def test_the_prm_boilerplate_changes_nothing(tmp_path):
    base = _written("len;")
    text = _written("prm num; prm runs; prm logLvl; len;")
    assert classify_dcl(text) == classify_dcl(base)
    assert parse_ssn(text) == parse_ssn(base)
    a, b = _design(tmp_path, base, "a.ssn"), _design(tmp_path, text, "b.ssn")
    assert a.default_params == b.default_params
    assert repr(a().build_wires()) == repr(b().build_wires())


# -- names the script computes are refused, not knobs ------------------------


def test_a_parameter_assigned_an_output_is_refused_by_name():
    # AC6LA's 2x3 trap dipole: `Trap23 = R2.z;`, saved as a parameter too.
    text = _one_wire("Trap23 = R2.z;", "0 0 10 0 Trap23 10", {"Trap23": "(2+j3)"})
    with pytest.raises(
        ValueError,
        match=r"names 'Trap23', a parameter of the element that the script "
        r"assigns \('Trap23 = R2.z'\), so an output",
    ):
        parse_ssn(text)


@pytest.mark.parametrize("saved", [True, False])
def test_a_name_assigned_twice_is_refused(saved):
    text = _written("len = 10.2;\nlen = 11;", saved=saved)
    # Saved on the element, it is an output; not saved, it is no constant.
    message = "so an output" if saved else "assigns 2 times, so it is not a constant"
    with pytest.raises(ValueError, match=rf"names 'len', .*{message}"):
        parse_ssn(text)
    with pytest.raises(ValueError):
        classify_dcl(text)


@pytest.mark.parametrize("saved", [True, False])
def test_an_assignment_inside_a_block_is_refused(saved):
    text = _written("at(finalValue) {\n\tlen = 10.2;\n}", saved=saved)
    with pytest.raises(ValueError, match=r"names 'len', .*'len = 10.2'"):
        parse_ssn(text)


def test_an_unread_plain_assignment_is_reported_unapplied_as_before():
    circuit = parse_ssn(_written("len;\nhgt = 9.144;"))
    assert circuit.ignored_directives == ("hgt = 9.144",)


@pytest.mark.parametrize(
    "header", ["if (hei > 1)", "else", "while (go)", "for ($i=0; $i &lt; 2; $i++)"]
)
def test_a_braceless_conditional_body_is_refused(header):
    text = _one_wire(f"{header}\n    hgt = 9.144;", "0 0 hgt 0 10 hgt", {})
    with pytest.raises(ValueError, match=r"names 'hgt', .*'hgt = 9.144'"):
        parse_ssn(text)


def test_a_statement_after_a_one_line_if_is_still_a_knob():
    # Positive control for the above: `if (c) Call(x);` carries its own body.
    text = _one_wire(
        "if (go) Print(hgt);\nhgt = 9.144;  // Height", "0 0 hgt 0 10 hgt", {}
    )
    syms = classify_dcl(text)
    assert [(s.name, s.kind, s.param, s.label) for s in syms] == [
        ("hgt", "knob", "prm_hgt", "Height")
    ]
