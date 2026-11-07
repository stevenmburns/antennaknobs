"""The .ssn script read as statements, not lines (AK#2204).

SimNEC's script is C-like: a statement ends at `;`, may run over several
lines, and `//` / `/* … */` are comments wherever they sit. The importer used
to split each line on `;`, so a statement written over two lines, or a
comment in front of one, refused the file. Every fixture is synthetic.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from antennaknobs.simnec_import import _script_units, parse_ssn

DIPOLE = "GW 1,21,0,0,0,0,0,10.2,.001"
SEG6 = f"{5.5 / 21 * 100:.12g}"
LOAD = f"$ld = NECSource(R(1k) ||| L(2u) ||| C(30p), $GW_1, {SEG6});"


def _ssn(*after: str) -> str:
    script = "\n".join(
        [
            "//test",
            "P1 w1 gnd;",
            "NECUnits meters;",
            "NEC2",
            DIPOLE,
            "EX 0 1 11 0 1 0",
            "NECEND",
            "$GW_1.JamSegments(21);",
            *after,
        ]
    )
    root = ET.Element("SimNEC1p0")
    circuit = ET.SubElement(ET.SubElement(root, "SmithChartCircuit"), "CIRCUIT")
    for typ, label, params in (
        ("LOAD", "L", [("ohms", "1000000000")]),
        ("NETWORK", "A", [("equ", script)]),
        ("GENERATOR", "G", [("MHz", "14"), ("Zo", "50")]),
    ):
        el = ET.SubElement(circuit, "element")
        ET.SubElement(el, "type").text = typ
        ET.SubElement(el, "sweeperLabel").text = label
        for n, v in params:
            p = ET.SubElement(el, "p")
            ET.SubElement(p, "n").text = n
            ET.SubElement(p, "v").text = v
    return ET.tostring(root, encoding="unicode")


def _loads(*after: str):
    c = parse_ssn(_ssn(*after), name="t.ssn", network=True)
    return [(ld.wire, ld.seg, ld.r, ld.l, ld.c) for ld in c.deck.loads]


ONE_LINE = _loads(LOAD)


@pytest.mark.parametrize(
    "spelling",
    [
        # Split inside the argument list.
        f"$ld = NECSource(R(1k) ||| L(2u) ||| C(30p),\n    $GW_1, {SEG6});",
        # Split after an operator.
        f"$ld = NECSource(R(1k) |||\n  L(2u) ||| C(30p), $GW_1, {SEG6});",
        # Split after the assignment.
        f"$ld =\n  NECSource(R(1k) ||| L(2u) ||| C(30p), $GW_1, {SEG6});",
        # A comment in front, on the same line.
        f"/* the trap */ {LOAD}",
        # A comment over several lines in front.
        f"/* the\n trap */\n{LOAD}",
        # A trailing comment, and one between the arguments.
        f"$ld = NECSource(R(1k) ||| L(2u) ||| C(30p), // trap\n  $GW_1, {SEG6});",
        # Two statements on one line.
        f"$x = 1; {LOAD}",
    ],
)
def test_a_statement_reads_however_it_is_laid_out(spelling):
    assert ONE_LINE  # the load is really there
    assert _loads(spelling) == ONE_LINE


def test_a_commented_out_load_is_a_comment():
    """It used to reach the statement reader and refuse the file as unread."""
    assert _loads(f"/* {LOAD} */") == []
    assert _loads(f"// {LOAD}") == []


def test_semicolons_and_slashes_inside_a_string_are_text():
    units = list(
        _script_units('errorOutln("a; b // not a comment"); $x = 1; // note', "t")
    )
    assert units == [
        ("stmt", 'errorOutln("a; b // not a comment")', 1, "note"),
        ("stmt", "$x = 1", 1, "note"),
    ]


def test_a_control_header_on_its_own_line_stays_its_own_statement():
    units = list(
        _script_units("if (NECOptions.Engine == 2)\n  $x = 1;\nelse\n  $x = 2;", "t")
    )
    assert [u[1] for u in units] == [
        "if (NECOptions.Engine == 2)",
        "$x = 1",
        "else",
        "$x = 2",
    ]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("$x = 1; /* never closed", "comment is not closed"),
        ('errorOutln("never closed);', "string is not closed"),
        ("NEC2\nGW 1 3 0 0 0 0 0 1 .001", "missing its NECEND"),
    ],
)
def test_an_unclosed_construct_refuses_by_name(text, message):
    with pytest.raises(ValueError, match=message):
        list(_script_units(text, "t"))


# --- part 2: values are evaluated, not matched --------------------------------


@pytest.mark.parametrize(
    "spelling",
    [
        # A value from a constant set earlier.
        f"$r = 1k;\n$ld = NECSource(R($r) ||| L(2u) ||| C(30p), $GW_1, {SEG6});",
        # Arithmetic in a value.
        f"$ld = NECSource(R(400+600) ||| L(2*1u) ||| C(30p), $GW_1, {SEG6});",
        # The whole impedance in a constant.
        f"$z = R(1k) ||| L(2u) ||| C(30p);\n$ld = NECSource($z, $GW_1, {SEG6});",
        # The wire in a variable.
        f"$w = $GW_1;\n$ld = NECSource(R(1k) ||| L(2u) ||| C(30p), $w, {SEG6});",
        # The place computed.
        "$ld = NECSource(R(1k) ||| L(2u) ||| C(30p), $GW_1, 100*5.5/21);",
        # N-block element lines on the same two nodes are in parallel.
        f"Ra 1k n1 n2;\nLa 2u n1 n2;\nCa 30p n2 n1;\n$ld = NECSource({{n1, n2}}, $GW_1, {SEG6});",
    ],
)
def test_a_value_reads_however_it_is_computed(spelling):
    assert _loads(spelling) == ONE_LINE


def test_insulation_reads_from_constants_and_a_wire_variable():
    def jackets(*after):
        return parse_ssn(_ssn(*after), name="t.ssn").deck.wire_insulation

    plain = jackets("$GW_1.Insulation(0.45m, 3.5, 0);")
    assert plain
    assert jackets("$t = 0.45m;", "$GW_1.Insulation($t, 3.5, 0);") == plain
    assert jackets("$w = $GW_1;", "$w.Insulation(0.45m, 3.5, 0);") == plain
    assert jackets("NECOptions.Insulation(0.45m, 3.5, 0);") == plain


@pytest.mark.parametrize(
    "spelling",
    [
        # A name set twice has no one value.
        f"$r = 1k;\n$r = 2k;\n$ld = NECSource(R($r) ||| L(2u), $GW_1, {SEG6});",
        # A name set only inside a block.
        f"if (1) {{ $r = 1k; }}\n$ld = NECSource(R($r) ||| L(2u), $GW_1, {SEG6});",
        # SimNEC's notes disagree on where ||| sits against *.
        f"$ld = NECSource(2*R(500) ||| L(2u), $GW_1, {SEG6});",
        # Two elements in series through an inner node is not one LD card.
        f"Ra 1k n1 m;\nLa 2u m n2;\n$ld = NECSource({{n1, n2}}, $GW_1, {SEG6});",
        # An L with a Q.
        f"$ld = NECSource(R(1k) ||| L(2u, 300), $GW_1, {SEG6});",
    ],
)
def test_what_has_no_reading_refuses_by_name(spelling):
    with pytest.raises(ValueError, match="could not be read"):
        _loads(spelling)
