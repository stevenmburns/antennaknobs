"""SimNEC ``.ssn`` forms a user's files carry that the import refused.

- A Generator ``MHz`` holding several frequencies (``3.55 14.05 21.1 28.3``):
  SimNEC solves at the last and marks every one; the design opens at the last
  and offers each as a band.
- A NECSource whose value or place names a slider (a bare ``Cap_F;`` saved as
  a ``<numericParam>``): read at the saved value, and a knob whose every
  value is the file saved with it.
- A place given by name is read to its written number's decimals, as the
  same number inline is: ``dcl P = 66.4;`` on 122 segments is knot 81.
- A place on no site of the wire (71.89 % of 122 segments) is that place,
  exactly: the same positioned port a 4nec2 ``71.89%`` LD card gives
  (AK#1496), which each engine meshes around (AK#1511) -- not a refusal, and
  not the nearest site.

Every fixture is synthetic.
"""

from __future__ import annotations

import pytest
from test_simnec_import import _SCRIPT_M, _el, _ssn

import antennaknobs.simnec_import as simnec_import
from antennaknobs.cli import make_engine_factory
from antennaknobs.file_designs import builder_from_text
from antennaknobs.simnec_import import parse_ssn, parse_ssn_station


def _with_mhz(text: str, mhz: str) -> str:
    """``text`` (an `_ssn` circuit) with its Generator's MHz written ``mhz``."""
    old = "<p><n>MHz</n><v>7.1</v></p>"
    assert text.count(old) == 1
    return text.replace(old, f"<p><n>MHz</n><v>{mhz}</v></p>")


# --- a Generator MHz list ---------------------------------------------------


def test_a_generator_mhz_list_solves_at_its_last_frequency_and_keeps_them_all():
    text = _with_mhz(_ssn(_SCRIPT_M), "3.55 14.05 21.1 28.3")
    c = parse_ssn(text)
    assert c.freq_mhz == 28.3
    assert c.freqs == (3.55, 14.05, 21.1, 28.3)
    assert parse_ssn_station(text).freqs == c.freqs
    assert parse_ssn_station(text).freq_mhz == 28.3


def test_a_listed_design_opens_at_the_last_and_offers_each_as_a_band():
    B = builder_from_text(
        "multi.ssn", _with_mhz(_ssn(_SCRIPT_M), "3.55 14.05 21.1 28.3")
    )
    assert B.default_params["freq"] == 28.3 == B.default_params["design_freq"]
    assert B().operating_bands() == [
        ("3.55 MHz", 3.55),
        ("14.05 MHz", 14.05),
        ("21.1 MHz", 21.1),
        ("28.3 MHz", 28.3),
    ]
    assert "lists 4 frequencies" in B.default_params["ui_params"]["notes"]


def test_one_generator_frequency_is_read_as_before_with_no_bands():
    text = _ssn(_SCRIPT_M)
    c = parse_ssn(text)
    assert (c.freq_mhz, c.freqs) == (7.1, (7.1,))
    B = builder_from_text("one.ssn", text)
    assert B.default_params["freq"] == 7.1
    assert not hasattr(B, "operating_bands")


def test_a_list_with_a_word_in_it_is_refused_by_name():
    with pytest.raises(ValueError, match=r"bad GENERATOR MHz '3\.55 abc'"):
        parse_ssn(_with_mhz(_ssn(_SCRIPT_M), "3.55 abc"))


# --- a NECSource reading a slider, and its place -----------------------------

# A 10 m, 122-segment wire fed at segment 61's centre: knot k sits at
# k / 122 of the wire, segment s's centre at (s - 0.5) / 122. 66.4 % is
# 81.008 segments in, within half a digit (0.061 segments) of knot 81;
# 71.89 % is 87.706 in, 0.21 from segment 88's centre and 0.29 from knot 88.
_WIRE = "GW 1 122 0 -5 10 0 5 10 0.0005"
_FEED = "EX 0 1 61 0 1 0"


def _script(*after: str, before: tuple[str, ...] = ()) -> str:
    """The 122-segment wire's script: ``before`` above the NEC2 block (bare
    slider declarations, dcl constants), ``after`` below it."""
    return "\n".join(
        ["//t", "P1 w1 gnd;", *before, "NECUnits meters;", "NEC2", _WIRE, _FEED]
        + ["NECEND", *after]
    )


def _with_sliders(text: str, **saved: str) -> str:
    """``text`` with each ``name=value`` saved on the NETWORK element as SimNEC
    saves a slider: ``<p><numericParam>name</numericParam><v>value</v></p>``."""
    head, equ, tail = text.partition("<p><n>equ</n>")
    assert equ and "<p><n>equ</n>" not in tail
    sliders = "".join(
        f"<p><numericParam>{n}</numericParam><v>{v}</v></p>" for n, v in saved.items()
    )
    return head + sliders + equ + tail


def _slider_file(cap_f="47p", cap_pct="71.89"):
    return _with_sliders(
        _ssn(
            _script(
                "$cap = NECSource(C(Cap_F), $GW_1, Cap_Pct);",
                before=("Cap_F;", "Cap_Pct;"),
            )
        ),
        Cap_F=cap_f,
        Cap_Pct=cap_pct,
    )


def _inline_file(value="47p", pct="71.89"):
    return _ssn(_script(f"$cap = NECSource(C({value}), $GW_1, {pct});"))


def _z(cls, engine="momwire:razor-2p", **params) -> complex:
    built = cls({**cls.default_params, **params})
    return complex(make_engine_factory(engine, None)(built).impedance()[0])


def test_a_necsource_reads_its_sliders_saved_values():
    (ld,) = parse_ssn(_slider_file(), network=True).deck.loads
    (inline,) = parse_ssn(_inline_file(), network=True).deck.loads
    assert ld == inline
    assert ld.c == pytest.approx(47e-12, rel=1e-15) and ld.at == 0.7189


def test_the_sliders_a_necsource_reads_are_knobs():
    B = builder_from_text("sliders.ssn", _slider_file())
    p = B.default_params
    assert p["par_Cap_F"] == pytest.approx(47e-12, rel=1e-15)
    assert p["par_Cap_Pct"] == 71.89


@pytest.mark.parametrize(
    ("knob", "saved"),
    [
        ({"par_Cap_F": 33e-12}, {"cap_f": "33p"}),
        ({"par_Cap_Pct": 40.0}, {"cap_pct": "40"}),
        ({"par_Cap_Pct": 66.4}, {"cap_pct": "66.4"}),
        (
            {"par_Cap_F": 1e-10, "par_Cap_Pct": 22.5},
            {"cap_f": "100p", "cap_pct": "22.5"},
        ),
    ],
)
def test_a_slider_knob_value_is_the_file_saved_with_it(knob, saved):
    B = builder_from_text("sliders.ssn", _slider_file())
    got = _z(B, **knob)
    want_cls = builder_from_text("saved.ssn", _slider_file(**saved))
    want = _z(want_cls)
    assert got == pytest.approx(want, rel=1e-12)
    assert abs(got - _z(B)) > 1e-3 * abs(want)


def test_a_slider_a_button_tunes_is_still_a_knob():
    """A Button's NelderMead naming the sliders runs only on a click: it does
    not make them outputs."""
    text = _with_sliders(
        _ssn(
            _script(
                "$cap = NECSource(C(Cap_F), $GW_1, Cap_Pct);",
                "Button Tune() {",
                "    $NM = NelderMead",
                "        (POSITIVES, TOLERANCE=0.01, COUNT=10, Cap_F, Cap_Pct) {",
                "            SWR(A.Z, 50);",
                "    }",
                "}",
                before=("Cap_F;", "Cap_Pct;"),
            )
        ),
        Cap_F="47p",
        Cap_Pct="71.89",
    )
    p = builder_from_text("button.ssn", text).default_params
    assert "par_Cap_F" in p and "par_Cap_Pct" in p


@pytest.mark.parametrize(
    "named",
    [
        _ssn(_script("$cap = NECSource(C(47p), $GW_1, P);", before=("dcl P = 66.4;",))),
        _ssn(
            _script(
                "$cap = NECSource(C(47p), $GW_1, P);",
                before=("dcl Q = 66.4;", "dcl P = Q;"),
            )
        ),
        _with_sliders(
            _ssn(_script("$cap = NECSource(C(47p), $GW_1, P);", before=("P;",))),
            P="66.4",
        ),
    ],
    ids=["dcl", "dcl-of-dcl", "slider"],
)
def test_a_place_by_name_is_read_to_its_written_decimals(named):
    """66.4 written inline is knot 81 of 122 (81.008, within half its last
    digit); the same number by name is the same knot, to the bit."""
    (inline,) = parse_ssn(_inline_file(pct="66.4"), network=True).deck.loads
    (ld,) = parse_ssn(named, network=True).deck.loads
    assert (inline.seg, inline.edge, inline.at) == (81, 2, None)
    assert ld == inline
    assert _z(builder_from_text("n.ssn", named)) == _z(
        builder_from_text("i.ssn", _inline_file(pct="66.4"))
    )


def test_a_computed_place_stays_exact():
    """``P * 1`` is computed, so it has no written decimals: 66.4 % is then
    0.008 segments off knot 81, and is carried as that place."""
    (ld,) = parse_ssn(
        _ssn(
            _script(
                "$cap = NECSource(C(47p), $GW_1, P * 1);", before=("dcl P = 66.4;",)
            )
        ),
        network=True,
    ).deck.loads
    assert (ld.edge, ld.at) == (0, 0.664)


# --- a place on no site -------------------------------------------------------

# The same load as a 4nec2 percentage on a .nec deck (AK#1496): the existing
# positioned-load route, the oracle for where 71.89 % lands.
_NEC_AT = (
    f"CM\nCE\n{_WIRE}\nGE 0\n{_FEED}\nLD 0 1 71.89% 71.89% 0 0 47e-12\n"
    "FR 0 1 0 0 7.1 0\nXQ\nEN\n"
)


def _engine(cls, engine):
    return make_engine_factory(engine, None)(cls(dict(cls.default_params)))


def _off_site_zs(engine):
    """``(at 71.89 %, the 4nec2 deck at 71.89 %, segment 88's centre, knot 88)``."""
    seg88 = repr(87.5 / 122 * 100)
    knot88 = repr(88 / 122 * 100)
    return tuple(
        _z(builder_from_text(n, t), engine)
        for n, t in (
            ("at.ssn", _inline_file()),
            ("at.nec", _NEC_AT),
            ("c88.ssn", _inline_file(pct=seg88)),
            ("k88.ssn", _inline_file(pct=knot88)),
        )
    )


def _lands_at_the_place(engine) -> bool:
    at, oracle, centre, knot = _off_site_zs(engine)
    return (
        at == pytest.approx(oracle, rel=1e-12)
        and abs(at - centre) > 1e-4 * abs(at)
        and abs(at - knot) > 1e-4 * abs(at)
    )


def test_a_place_on_no_site_is_carried_as_that_fraction():
    c = parse_ssn(_inline_file(), network=True)
    (ld,) = c.deck.loads
    # Segment 88 is the one whose centre is nearest, as a 4nec2 percentage
    # records it; the place is the fraction.
    assert (ld.seg, ld.edge, ld.at) == (88, 0, 0.7189)
    port = c.network().ports["load1"]
    assert (port.wire, port.at) == ("w1", 0.7189)


@pytest.mark.parametrize("engine", ["momwire:bspline", "momwire:razor-2p"])
def test_a_place_on_no_site_solves_there_not_at_the_nearest_site(engine):
    assert _lands_at_the_place(engine)
    texts = [
        a["text"]
        for a in _engine(builder_from_text("at.ssn", _inline_file()), engine).advisories
        if a["category"] == "FeedPlacement"
    ]
    assert any("'load1' at 0.7189" in t and "split" in t for t in texts), texts


def test_rounding_the_place_to_a_site_fails_the_check(monkeypatch):
    """The negative control: the same check, with the importer's fraction
    dropped so the load sits on its segment's centre, fails."""
    from dataclasses import replace

    place = simnec_import._place_at_knots

    def rounded(deck, script, where):
        deck = place(deck, script, where)
        return replace(deck, loads=tuple(replace(ld, at=None) for ld in deck.loads))

    monkeypatch.setattr(simnec_import, "_place_at_knots", rounded)
    assert not _lands_at_the_place("momwire:bspline")


def test_a_source_on_no_site_is_carried_as_that_fraction():
    text = _ssn(
        "\n".join(
            ["//t", "P1 w1 gnd;", "P2 w2 gnd;", "NECUnits meters;", "NEC2", _WIRE]
            + ["NECEND", "$src = NECSource({w2, gnd}, $GW_1, 71.89);"]
        )
    )
    (f,) = parse_ssn(text, network=True).deck.feeds
    assert (f.seg, f.edge, f.at) == (88, 0, 0.7189)


# --- a station value bound to the block's slider ------------------------------


def _bound_file(c1_f="=A.C1_F", saved="90.85p") -> str:
    """The dipole with a shunt C between it and the Generator whose F is
    written ``c1_f``, and the NETWORK block, labelled A, saving a C1_F
    slider at ``saved``."""
    text = _with_sliders(
        _ssn(_SCRIPT_M, extra_elements=_el("SHUNT_CAP", {"F": c1_f, "Q": 0}, "C1")),
        C1_F=saved,
    )
    old = "<type>NETWORK</type>"
    assert text.count(old) == 1
    return text.replace(old, old + "<sweeperLabel>A</sweeperLabel>")


def test_a_station_value_bound_to_a_slider_reads_its_saved_value():
    c = parse_ssn(_bound_file(), network=True)
    (c1,) = c.chain
    assert c1.get("F") == "90.85p"
    assert "SHUNT_CAP C1's F is A.C1_F, read at its saved value 90.85p" in c.chain_notes
    assert parse_ssn_station(_bound_file()).chain == c.chain
    B = builder_from_text("bound.ssn", _bound_file())
    assert B.default_params["stn_C1_F"] == 90.85
    assert _z(B) == _z(builder_from_text("plain.ssn", _bound_file(c1_f="90.85p")))


def test_a_binding_to_nothing_is_still_refused_by_name():
    with pytest.raises(ValueError, match=r"bad 'F' value '=B\.C1_F'"):
        builder_from_text("bound.ssn", _bound_file(c1_f="=B.C1_F"))


def test_a_station_value_saved_to_full_precision_is_still_a_knob():
    """1.7827090187647904E-10 shows as 178.270901876 pF (12 digits), 2.7e-12
    off: the knob at that default is still the file as saved."""
    B = builder_from_text("full.ssn", _bound_file(saved="1.7827090187647904E-10"))
    assert B.default_params["stn_C1_F"] == 178.270901876
    plain = builder_from_text("plain.ssn", _bound_file(c1_f="1.7827090187647904E-10"))
    assert _z(B) == _z(plain)


@pytest.mark.parametrize("pct", ["150", "-5", "100.5"])
def test_a_place_off_the_wire_is_refused(pct):
    # Between sites is carried as that place; past either end is no place.
    with pytest.raises(ValueError, match="off the wire"):
        builder_from_text("t.ssn", _inline_file(pct=pct))
