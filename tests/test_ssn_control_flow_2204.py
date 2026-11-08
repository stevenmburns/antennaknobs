"""The .ssn script's control flow and functions, evaluated (AK#2204).

`if` / `else` on a constant condition reads the branch SimNEC takes, and a
constant set there is set once; `NECOptions.Engine` reads 2, SimNEC's NEC-2
engine, whose cards the NEC2 block is. A condition that is no constant, a
loop body and a phase block apply nothing: a model statement in one refuses
the file by name and line, and a read-out does not. A function whose body is
one `return <expression>` is evaluated where a value calls it; any other is
refused by name. Every call shape is read from its parsed form, so spacing,
line breaks and comments inside it do not matter. Every fixture is synthetic.
"""

from __future__ import annotations

import pytest
from test_ssn_parser_2204 import DIPOLE, LOAD, ONE_LINE, SEG6, _loads, _ssn

from antennaknobs.simnec_import import _Script, classify_dcl, parse_ssn

OTHER = f"$ld = NECSource(R(2k), $GW_1, {SEG6});"
OTHER_LOADS = _loads(OTHER)


def _refusal(*after: str) -> str:
    with pytest.raises(ValueError, match="could not be read") as e:
        _loads(*after)
    return str(e.value)


# --- if / else --------------------------------------------------------------


@pytest.mark.parametrize(
    ("pick", "want"), [("1", ONE_LINE), ("0", OTHER_LOADS), ("2*0.5", ONE_LINE)]
)
def test_a_constant_condition_reads_the_branch_it_takes(pick, want):
    assert ONE_LINE != OTHER_LOADS
    script = [f"dcl pick = {pick};", f"if (pick == 1) {{ {LOAD} }} else {{ {OTHER} }}"]
    assert _loads(*script) == want


@pytest.mark.parametrize(
    "spelling",
    [
        f"if (NECOptions.Engine == 2) {{\n  {LOAD}\n}} else {{\n  {OTHER}\n}}",
        f"if (NECOptions.Engine == 5)\n  {OTHER}\nelse\n  {LOAD}",
        f"if (NECOptions.Engine != 2) {OTHER} else if (1) {LOAD} else {OTHER}",
        f"if (NECOptions.Engine >= 4 || NECOptions.Engine < 2) {OTHER} else {LOAD}",
    ],
)
def test_an_engine_branch_reads_as_simnec_s_nec2_engine(spelling):
    assert _loads(spelling) == ONE_LINE


def test_a_constant_set_in_the_branch_taken_is_set_once():
    """The untaken branch's assignment is never run, so `$r` has one value."""
    assert (
        _loads(
            "if (1) { $r = 1k; } else { $r = 5k; }",
            f"$ld = NECSource(R($r) ||| L(2u) ||| C(30p), $GW_1, {SEG6});",
        )
        == ONE_LINE
    )


def test_a_condition_that_is_no_constant_refuses_its_model_statements():
    message = _refusal(f"if (G.MHz > 10) {{\n  {LOAD}\n}} else {{\n  {OTHER}\n}}")
    assert "line 10: $ld = NECSource(R(1k)" in message
    assert "line 12: $ld = NECSource(R(2k)" in message
    assert "inside if (G.MHz > 10)" in message


@pytest.mark.parametrize(
    "condition",
    [
        "G.MHz > 10",  # the frequency: no one value
        "$x > 0",  # a name set twice
        "later > 0",  # set only after the `if`
    ],
)
def test_what_a_condition_reads_must_be_constant_when_it_runs(condition):
    message = _refusal("$x = 1;", "$x = 2;", f"if ({condition}) {LOAD}", "later = 1;")
    assert f"inside if ({condition})" in message


def test_a_read_out_under_a_condition_that_is_no_constant_is_harmless():
    assert _loads(LOAD, 'if (G.MHz > 10) $label = "hi"; else errorOutln("lo");') == (
        ONE_LINE
    )


# --- loops and phase blocks ---------------------------------------------------


@pytest.mark.parametrize(
    "loop",
    [
        f"for ($i = 0; $i < 2; $i++) {{ {LOAD} }}",
        f"for ($i = 0; $i < 2; $i++)\n  {LOAD}",
        f"$i = 0;\nwhile ($i < 1) {{ {LOAD} $i++; }}",
        f"do {{ {LOAD} }} while (0);",
    ],
)
def test_a_model_statement_in_a_loop_refuses_by_name(loop):
    message = _refusal(loop)
    assert "$ld = NECSource(R(1k)" in message
    assert "inside the loop" in message


def test_a_loop_that_only_computes_a_read_out_opens():
    """The bundled examples' segment count, in an `at(finalValue)` block."""
    script = [
        LOAD,
        "at(finalValue) {",
        "  SegCnt = 0;",
        "  for($i=0; $i<SizeOf(Antenna._NECBLOCK.wires); $i++) {",
        "    SegCnt = SegCnt + SizeOf(Antenna._NECBLOCK.wires[$i].currents);",
        "    $seen++;",
        "  }",
        "}",
        "$n = 0; while ($n < 3) $n++;",
    ]
    assert _loads(*script) == ONE_LINE


def test_a_model_statement_in_a_phase_block_refuses_by_name():
    message = _refusal("finalize {", "  $GW_1.Insulation(0.45m, 3.5, 0);", "}")
    assert "line 10: $GW_1.Insulation(0.45m, 3.5, 0)" in message
    assert "changes the model" in message


# --- functions ----------------------------------------------------------------


@pytest.mark.parametrize(
    "definition",
    [
        "dcl f(x) { return 2*x; }",
        "dcl f(x) {\n  return 2 * x; // twice\n}",
        "dcl g(a, b) { return a + b; }\ndcl f(x) { return g(x, x); }",
    ],
)
def test_a_one_return_function_is_evaluated_in_a_value(definition):
    load = f"$ld = NECSource(R(f(500)) ||| L(2u) ||| C(30p), $GW_1, {SEG6});"
    assert _loads(definition, load) == ONE_LINE


def test_a_function_can_return_a_whole_impedance():
    script = [
        "dcl trap(r, l, c) { return R(r) ||| L(l) ||| C(c); }",
        f"$ld = NECSource(trap(1k, 2u, 30p), $GW_1, {SEG6});",
    ]
    assert _loads(*script) == ONE_LINE


@pytest.mark.parametrize(
    ("definition", "why"),
    [
        ("dcl f(x) { $y = 2*x; return $y; }", "is not one `return <expression>;`"),
        ("dcl f(x) { if (x > 1) return x; }", "is not one `return <expression>;`"),
        ("dcl f(x) { return f(x); }", "calls itself too deeply"),
        ("dcl f(x, y) { return x*y; }", "takes 2 argument(s)"),
    ],
)
def test_any_other_function_in_a_value_refuses_by_name(definition, why):
    message = _refusal(
        definition, f"$ld = NECSource(R(f(500)) ||| L(2u) ||| C(30p), $GW_1, {SEG6});"
    )
    assert "NECSource(R(f(500))" in message
    assert why in message


def test_a_function_that_builds_the_antenna_is_never_a_read_out():
    """Its body is not run, and an assignment calling it is no read-out."""
    script = [
        f"dcl addLoad(w) {{ {LOAD} return 1; }}",
        "$done = addLoad($GW_1);",
    ]
    assert "line 10: $done = addLoad($GW_1)" in _refusal(*script)


def test_a_function_never_called_changes_nothing():
    assert _loads(f"dcl unused(w) {{ {OTHER} return 1; }}", LOAD) == ONE_LINE


# --- line numbers ---------------------------------------------------------------


def test_a_refusal_names_the_line_a_statement_starts_on():
    message = _refusal(
        "if (G.MHz > 1) $label = 1; // a read-out, no reason for what follows",
        f"$ld = NECSource(R($nowhere) ||| L(2u),\n    $GW_1, {SEG6});",
        "FancyNewThing(1, 2);",
    )
    # `_ssn` puts its own eight lines first.
    assert "line 10: $ld = NECSource(R($nowhere)" in message
    assert "$nowhere has no one constant value" in message
    assert "line 12: FancyNewThing(1, 2)" in message
    assert "inside" not in message


# --- knobs ------------------------------------------------------------------------


def _knob_ssn(*script: str) -> str:
    """`_ssn` with the dipole's length the constant ``len``."""
    return _ssn(*script).replace(DIPOLE, DIPOLE.replace("10.2", "len"))


def test_a_condition_on_a_knob_follows_the_knob():
    text = _knob_ssn(
        "dcl len = 10.2;",
        f"if (len > 5) {LOAD} else {OTHER}",
    )
    assert [s.name for s in classify_dcl(text, name="t.ssn")] == ["len"]

    def loads(**over):
        c = parse_ssn(text, name="t.ssn", network=True, dcl_overrides=over)
        return [(ld.wire, ld.seg, ld.r, ld.l, ld.c) for ld in c.deck.loads]

    assert loads() == ONE_LINE
    assert loads(len=4.0) == OTHER_LOADS


def test_a_constant_set_in_the_branch_taken_is_a_knob():
    text = _knob_ssn("if (NECOptions.Engine == 2) { dcl len = 10.2; }")
    assert [s.name for s in classify_dcl(text, name="t.ssn")] == ["len"]
    c = parse_ssn(text, name="t.ssn", network=True)
    assert c.deck.wires == parse_ssn(_ssn(), name="t.ssn", network=True).deck.wires


# --- every call shape, read from its parse ---------------------------------------


def _reading(*after: str):
    c = parse_ssn(_ssn(*after), name="t.ssn", network=True)
    d = c.deck
    return (
        d.wires,
        d.loads,
        d.feeds,
        d.wire_insulation,
        d.wire_insulation_loss_tangent,
        d.pinned_wires,
        c.ground,
        c.conductivity,
        c.seg_per_wl,
    )


@pytest.mark.parametrize(
    ("plain", "spaced"),
    [
        (
            "$GW_1.JamSegments(7);",
            "$GW_1 . JamSegments ( // seven\n 7 ) ;",
        ),
        (
            "dcl n = 7; $GW_1.JamSegments(n);",
            "dcl n = 7; $GW_1 .JamSegments( /* the count */ n );",
        ),
        (
            "$GW_1.Insulation(0.45m, 3.5, 0);",
            "$GW_1 . Insulation ( 0.45m ,\n 3.5 , /* none */ 0 ) ;",
        ),
        (
            "NECOptions.Insulation(0.45m, 3.5, 0);",
            "NECOptions . Insulation(0.45m, 3.5, 0);",
        ),
        (
            'NECOptions.Insulation("W7EL", 0.00045, 3.5, 0.01);',
            'NECOptions . Insulation ( "W7EL" ,\n 0.00045, 3.5, 0.01 ) ;',
        ),
        (LOAD, LOAD.replace("NECSource(", "NECSource /* src */ (\n ")),
        (
            "Ra 1k n1 n2;\nLa 2u n1 n2;\nCa 30p n1 n2;\n"
            f"$ld = NECSource({{n1, n2}}, $GW_1, {SEG6});",
            "Ra 1k n1 n2;\nLa 2u n1 n2;\nCa 30p n1 n2;\n"
            f"dcl ld = NECSource( {{ n1 ,\n n2 }} , $GW_1 , {SEG6} ) ;",
        ),
        ("PerfectGround();", "PerfectGround ( /* pec */ ) ;"),
        ("SommerfeldGround(0.005, 13);", "SommerfeldGround (\n 0.005 , 13 ) ;"),
        ("MiniNECGround(0.005, 13);", "MiniNECGround( 0.005 ,// soil\n 13 );"),
        ("NECOptions.mhosPerMeter = 5.8e7;", "NECOptions . mhosPerMeter =\n 5.8e7 ;"),
        (
            "NECOptions.mhosPerMeter = Conductivities.copper;",
            "NECOptions.mhosPerMeter = /* Cu */ Conductivities.copper;",
        ),
        (
            "NECOptions.segmentsPerWavelength = 20;",
            "NECOptions . segmentsPerWavelength = 20 ; // per wave",
        ),
    ],
)
def test_every_call_shape_reads_however_it_is_spaced(plain, spaced):
    assert _reading(plain) != _reading()  # the statement really does something
    assert _reading(spaced) == _reading(plain)


def test_the_field_step_is_read_however_it_is_spaced():
    """It changes no solved number, so a malformed one shows it is read."""
    assert _reading("NECOptions .fieldStep= 2;") == _reading()
    with pytest.raises(ValueError, match="bad NECOptions.fieldStep value"):
        _reading("NECOptions . fieldStep = two;")


def test_the_units_command_reads_however_it_is_spaced():
    script = _Script("NECUnits feet,\n  inches ; // display", "t.ssn")
    assert script.display_units == ("feet", "inches")
