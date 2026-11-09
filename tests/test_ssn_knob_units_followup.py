"""Knobs a SimNEC ``.ssn`` NECSource reads, after AK#2234.

- A knob read as the one argument of ``C(...)`` reads in pF, of ``L(...)`` in
  µH, as the station knobs do; of ``R(...)`` in Ω; as the place, in %. A name
  in two roles, or read anywhere else too, keeps SI and no unit.
- At its default a unit knob is the file as imported, to the bit: the default
  stands for the saved value, which a 12-digit default times its factor need
  not reproduce.

Every fixture is synthetic.
"""

from __future__ import annotations

import pytest
from test_simnec_import import _ssn
from test_ssn_dan_1109 import _script, _slider_file, _with_sliders, _z

from antennaknobs.file_designs import builder_from_text
from antennaknobs.nec_import import SySymbol
from antennaknobs.simnec_import import parse_ssn

# A full-precision value SimNEC's optimizer leaves: 164.487257334 pF at 12
# significant digits, 3.0e-12 off.
_FULL = "1.6448725733350855E-10"


def _units(cls) -> dict:
    ui = cls.default_params["ui_params"]
    return {
        k: (v, ui.get(k, {}).get("unit"))
        for k, v in cls.default_params.items()
        if k.startswith(("par_", "dcl_", "tmp_", "prm_"))
    }


def _coil_file(coil_h="3.9u", pct="24.6"):
    return _with_sliders(
        _ssn(
            _script(
                "$coil = NECSource(R(0.7) + L(Lx_H), $GW_1, Coil_Pct);",
                before=("Lx_H;", "Coil_Pct;"),
            )
        ),
        Lx_H=coil_h,
        Coil_Pct=pct,
    )


def _r_file(res="12.5"):
    return _with_sliders(
        _ssn(_script("$r = NECSource(R(Res) + L(2u), $GW_1, 40);", before=("Res;",))),
        Res=res,
    )


def _two_roles_file():
    """``X`` is a C in one load and an L in another: one value, two units."""
    return _with_sliders(
        _ssn(
            _script(
                "$a = NECSource(C(X), $GW_1, 30);",
                "$b = NECSource(L(X), $GW_1, 60);",
                before=("X;",),
            )
        ),
        X="1e-7",
    )


# --- units --------------------------------------------------------------------


def test_a_c_reads_in_pf_and_its_place_in_percent():
    assert _units(builder_from_text("c.ssn", _slider_file(cx_f="390.5p"))) == {
        "par_Cx_F": (390.5, "pF"),
        "par_Px": (41.23, "%"),
    }


def test_an_l_reads_in_uh():
    assert _units(builder_from_text("l.ssn", _coil_file())) == {
        "par_Lx_H": (3.9, "µH"),
        "par_Coil_Pct": (24.6, "%"),
    }


def test_an_r_reads_in_ohms_at_its_own_value():
    assert _units(builder_from_text("r.ssn", _r_file())) == {
        "par_Res": (12.5, "Ω"),
    }


def test_a_name_in_two_roles_keeps_si_and_no_unit():
    assert _units(builder_from_text("x.ssn", _two_roles_file())) == {
        "par_X": (1e-7, None),
    }


def test_a_name_computed_in_the_load_keeps_si_and_no_unit():
    """``C(Cx_F * 2)``: Cx_F is not the C, so it is not in pF."""
    text = _with_sliders(
        _ssn(_script("$cap = NECSource(C(Cx_F * 2), $GW_1, 40);", before=("Cx_F;",))),
        Cx_F="20p",
    )
    p = builder_from_text("m.ssn", text).default_params
    assert p["par_Cx_F"] == pytest.approx(20e-12, rel=1e-15)
    assert "unit" not in p["ui_params"]["par_Cx_F"]


def test_a_full_precision_c_shows_twelve_digits():
    assert _units(builder_from_text("f.ssn", _slider_file(cx_f=_FULL)))["par_Cx_F"] == (
        164.487257334,
        "pF",
    )


# --- the default round trip -----------------------------------------------------


def _inline(load: str) -> str:
    """The same wire with ``load`` written inline: no knob, the oracle."""
    return _ssn(_script(load))


@pytest.mark.parametrize(
    ("text", "oracle"),
    [
        (
            _slider_file(cx_f="390.5p"),
            _inline("$cap = NECSource(C(390.5p), $GW_1, 41.23);"),
        ),
        (
            _slider_file(cx_f=_FULL),
            _inline(f"$cap = NECSource(C({_FULL}), $GW_1, 41.23);"),
        ),
        (
            _slider_file(cx_f="3.689441732259042e-10", px="78.02121228132127"),
            _inline(
                "$cap = NECSource(C(3.689441732259042e-10), $GW_1, 78.02121228132127);"
            ),
        ),
        (
            _coil_file(coil_h="3.3170662054318844e-06"),
            _inline(
                "$coil = NECSource(R(0.7) + L(3.3170662054318844e-06), $GW_1, 24.6);"
            ),
        ),
        (
            _r_file(res="0.70000000000000007"),
            _inline("$r = NECSource(R(0.70000000000000007) + L(2u), $GW_1, 40);"),
        ),
    ],
    ids=["c", "c-full", "c-pct-full", "l-full", "r"],
)
def test_a_unit_knob_at_its_default_is_the_import_to_the_bit(text, oracle):
    B = builder_from_text("t.ssn", text)
    knobs = B.file_sy_knobs
    assert knobs is not None and len(knobs.symbols) >= 1
    imported = parse_ssn(text, network=True)
    at_default = knobs.parsed_for(B(dict(B.default_params)))
    assert at_default.deck.loads == imported.deck.loads
    assert at_default == imported
    assert imported.deck.loads == parse_ssn(oracle, network=True).deck.loads
    assert _z(B) == _z(builder_from_text("oracle.ssn", oracle))


def _full_c_round_trip() -> bool:
    """Whether the full-precision C's knob survives at its default with the
    load exactly as imported."""
    text = _slider_file(cx_f=_FULL)
    B = builder_from_text("f.ssn", text)
    if B.file_sy_knobs is None or "par_Cx_F" not in B.default_params:
        return False
    imported = parse_ssn(text, network=True)
    got = B.file_sy_knobs.parsed_for(B(dict(B.default_params)))
    return got.deck.loads == imported.deck.loads


def test_the_full_precision_default_survives():
    assert _full_c_round_trip()


def test_a_twelve_digit_default_times_its_factor_fails_the_round_trip(monkeypatch):
    """The negative control: the default multiplied back naively (164.487257334
    * 1e-12) is not the saved value, so the knobs are dropped as not
    reproducing the import."""

    def naive(self, knob_value):
        if self.unit_factor is not None:
            return float(knob_value) * self.unit_factor
        return float(knob_value)

    monkeypatch.setattr(SySymbol, "symbol_value", naive)
    assert not _full_c_round_trip()


# --- a knob value is the file saved with it ----------------------------------------


@pytest.mark.parametrize(
    ("make", "knob", "saved"),
    [
        (_slider_file, {"par_Cx_F": 330.0}, {"cx_f": "330p"}),
        (_slider_file, {"par_Cx_F": 164.487257335}, {"cx_f": "164.487257335p"}),
        (_coil_file, {"par_Lx_H": 1.5}, {"coil_h": "1.5u"}),
        (_r_file, {"par_Res": 40.0}, {"res": "40"}),
    ],
    ids=["c", "c-near-default", "l", "r"],
)
def test_a_unit_knob_value_is_the_file_saved_with_it(make, knob, saved):
    B = builder_from_text("t.ssn", make())
    got = _z(B, **knob)
    want = _z(builder_from_text("saved.ssn", make(**saved)))
    assert got == pytest.approx(want, rel=1e-12)


# --- a dcl constant only a NECSource reads ---------------------------------------


def _dcl_file(cx_f="270p", px="24.6", extra=()):
    return _ssn(
        _script(
            "$cap = NECSource(C(Cx_F), $GW_1, Px);",
            before=(f"dcl Cx_F = {cx_f};", f"dcl Px = {px};", *extra),
        )
    )


def test_a_dcl_constant_only_a_necsource_reads_is_a_knob_in_its_unit():
    assert _units(builder_from_text("d.ssn", _dcl_file())) == {
        "dcl_Cx_F": (270.0, "pF"),
        "dcl_Px": (24.6, "%"),
    }


def test_a_dcl_knob_at_its_default_is_the_import_to_the_bit():
    text = _dcl_file(cx_f=_FULL)
    B = builder_from_text("d.ssn", text)
    assert B.default_params["dcl_Cx_F"] == 164.487257334
    imported = parse_ssn(text, network=True)
    assert B.file_sy_knobs.parsed_for(B(dict(B.default_params))) == imported
    oracle = _inline(f"$cap = NECSource(C({_FULL}), $GW_1, 24.6);")
    assert imported.deck.loads == parse_ssn(oracle, network=True).deck.loads
    assert _z(B) == _z(builder_from_text("oracle.ssn", oracle))


@pytest.mark.parametrize(
    ("knob", "saved"),
    [
        ({"dcl_Cx_F": 330.0}, {"cx_f": "330p"}),
        ({"dcl_Px": 40.0}, {"px": "40"}),
        ({"dcl_Px": 41.23}, {"px": "41.23"}),
        (
            {"dcl_Cx_F": 100.0, "dcl_Px": 22.5},
            {"cx_f": "100p", "px": "22.5"},
        ),
    ],
)
def test_a_dcl_knob_value_is_the_file_saved_with_it(knob, saved):
    B = builder_from_text("d.ssn", _dcl_file())
    got = _z(B, **knob)
    want = _z(builder_from_text("saved.ssn", _dcl_file(**saved)))
    assert got == pytest.approx(want, rel=1e-12)
    assert abs(got - _z(B)) > 1e-3 * abs(want)


def test_a_computed_constant_is_derived_and_what_it_reads_is_the_knob():
    """``dcl Cx_F = Base * 2``: Cx_F follows Base, which is the knob -- in
    SI, since it is not itself the C."""
    text = _ssn(
        _script(
            "$cap = NECSource(C(Cx_F), $GW_1, 24.6);",
            before=("dcl Base = 120p;", "dcl Cx_F = Base * 2;"),
        )
    )
    B = builder_from_text("c.ssn", text)
    assert _units(B) == {"dcl_Base": (pytest.approx(120e-12, rel=1e-15), None)}
    got = _z(B, dcl_Base=165e-12)
    want = _z(builder_from_text("w.ssn", _dcl_file(cx_f="330p")))
    assert got == pytest.approx(want, rel=1e-12)


def test_a_redefined_constant_is_no_knob():
    """Set twice, ``P`` has no one value: the load reading it is refused by
    name, as before, and no knob stands for it."""
    text = _ssn(
        _script(
            "$cap = NECSource(C(47p), $GW_1, P);",
            before=("dcl P = 24.6;", "P = 40;"),
        )
    )
    with pytest.raises(ValueError, match="P has no one constant value"):
        builder_from_text("r.ssn", text)


def test_a_constant_on_a_card_and_in_a_load_moves_both():
    """``Z`` is the wire's height and the load's R: one knob, in SI, and a
    value of it is the file saved with it, card and load alike."""

    def text(z):
        return _ssn(
            "\n".join(
                [
                    "//t",
                    "P1 w1 gnd;",
                    f"dcl Z = {z};",
                    "NECUnits meters;",
                    "NEC2",
                    "GW 1 122 0 -5 Z 0 5 Z 0.0005",
                    "EX 0 1 61 0 1 0",
                    "NECEND",
                    "$r = NECSource(R(Z), $GW_1, 40);",
                ]
            )
        )

    B = builder_from_text("z.ssn", text(10))
    assert _units(B) == {"dcl_Z": (10.0, None)}
    got = _z(B, dcl_Z=12.0)
    assert got == pytest.approx(_z(builder_from_text("w.ssn", text(12))), rel=1e-12)


# --- the "not applied" note --------------------------------------------------------


def _ignored(text) -> tuple[str, ...]:
    return parse_ssn(text, network=True).ignored_directives


@pytest.mark.parametrize(
    "text",
    [
        _slider_file(),
        _dcl_file(),
        _with_sliders(
            _ssn(
                _script(
                    "$cap = NECSource(C(Cx_F), $GW_1, P);",
                    before=("Cx_F;", "dcl P = 24.6;"),
                )
            ),
            Cx_F="47p",
        ),
    ],
    ids=["sliders", "dcl", "both"],
)
def test_what_the_import_reads_is_not_listed_as_not_applied(text):
    assert _ignored(text) == ()
    assert "not applied" not in (parse_ssn(text, network=True).skipped_note() or "")


def test_a_bare_slider_declaration_is_not_a_directive():
    """``Cm_F;`` declares a slider a station value binds to (``=A.Cm_F``): no
    NECSource or card reads it, and there is nothing to apply."""
    text = _with_sliders(
        _ssn(_script(before=("Cm_F;",))),
        Cm_F="68.2p",
    )
    assert _ignored(text) == ()


def test_what_is_not_applied_is_still_listed():
    """A read-out of the load's current is left unread, and says so; so is a
    bare name no slider saves."""
    text = _slider_file().replace(
        "$cap = NECSource(C(Cx_F), $GW_1, Px);",
        "$cap = NECSource(C(Cx_F), $GW_1, Px);\ncapW = Abs($cap.p);\nunsaved;",
    )
    assert _ignored(text) == ("capW = Abs($cap.p)", "unsaved")
    assert (
        "not applied: capW = Abs($cap.p); unsaved"
        in parse_ssn(text, network=True).skipped_note()
    )
