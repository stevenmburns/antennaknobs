"""The block builder's expression parser: the grammar it takes, everything it
refuses, and a fuzz over both (docs/design/block-builder.md, "Testing":
Safety)."""

from __future__ import annotations

import ast
import builtins
import math
import random
import struct

import pytest

from antennaknobs import block_expr as bx

PARAMS = {"a": 1.5, "b": -0.25, "n": 4, "width": 0.1378}
LAM = 10.530


def lookup(name):
    if name not in PARAMS:
        raise bx.ExprError(f"no param {name!r}")
    return PARAMS[name]


def value(text):
    return bx.evaluate(bx.parse(text), lookup, LAM)


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("1", 1),
        ("2.5", 2.5),
        (".5e1", 5.0),
        ("a + b", 1.5 + -0.25),
        ("a − b", 1.5 - -0.25),
        ("a × 2 ÷ 4", 1.5 * 2 / 4),
        ("-a", -1.5),
        ("--a", 1.5),
        ("-(a + b) * 2", -(1.5 + -0.25) * 2),
        ("a - (b - 1)", 1.5 - (-0.25 - 1)),
        ("λ * width / 2", LAM * 0.1378 / 2),
        ("wavelength * 0.25", LAM * 0.25),
        ("sqrt(a * a + 4)", math.sqrt(1.5 * 1.5 + 4)),
        ("sin(30)", math.sin(math.radians(30))),
        ("cos(360 * 1 / n)", math.cos(math.radians(360 * 1 / 4))),
        ("360 * n / 4", 360.0),
    ],
)
def test_the_grammar(text, want):
    got = value(text)
    assert got == want
    assert type(got) is type(want)


@pytest.mark.parametrize(
    "text",
    [
        "a.real",  # attribute access
        "__import__('os')",
        "().__class__",
        "a[0]",
        "a ** 2",
        "2 ^ 3",
        "pow(2, 3)",
        "abs(a)",
        "eval(1)",
        "exec",
        "lambda: 1",
        "a if b else 1",
        "a < b",
        "a, b",
        "'1'",
        '"x"',
        "sqrt(1, 2)",
        "sin",
        "1e999",
        "9" * 40,
        "1 +",
        "(1",
        "1)",
        "",
        "   ",
        "a b",
        "2a",
        "1..2",
        "#",
        "a;b",
        "a = 1",
        "π",
        "μ",
        "@",
        "\\",
        "{}",
        "[1]",
    ],
)
def test_outside_the_grammar_is_refused(text):
    with pytest.raises(bx.ExprError):
        value(text)


def test_an_unknown_name_is_the_callers_to_refuse():
    # The parser takes any NAME; the compiler checks it against the scope.
    assert bx.names(bx.parse("a + c * a")) == ["a", "c"]


def test_size_and_depth_are_bounded():
    with pytest.raises(bx.ExprError, match="longer than"):
        bx.parse("1+" * 200 + "1")
    with pytest.raises(bx.ExprError, match="nests deeper"):
        bx.parse("(" * 40 + "1" + ")" * 40)
    with pytest.raises(bx.ExprError, match="nests deeper"):
        bx.parse("-" * 40 + "1")
    with pytest.raises(bx.ExprError, match="nests deeper"):
        bx.parse("sqrt(" * 40 + "1" + ")" * 40)
    bx.parse("(" * 30 + "1" + ")" * 30)


def test_values_must_stay_finite_and_exact():
    with pytest.raises(bx.ExprError, match="division by zero"):
        value("a / (n - 4)")
    with pytest.raises(bx.ExprError, match="negative"):
        value("sqrt(b)")
    with pytest.raises(bx.ExprError, match="finite"):
        value("1e200 * 1e200")
    with pytest.raises(bx.ExprError, match="2\\*\\*53"):
        value("9007199254740993")
    with pytest.raises(bx.ExprError, match="2\\*\\*53"):
        value("100000000 * 100000000")
    with pytest.raises(bx.ExprError):
        bx.number(True)
    with pytest.raises(bx.ExprError):
        bx.number(float("nan"))
    with pytest.raises(bx.ExprError):
        bx.number("1")


# -- fuzz --------------------------------------------------------------------

_SOUP = [
    "a",
    "b",
    "n",
    "λ",
    "1",
    "0.5",
    "2e3",
    "+",
    "-",
    "*",
    "/",
    "−",
    "×",
    "÷",
    "(",
    ")",
    "sqrt",
    "sin",
    "cos",
    ".",
    ",",
    "[",
    "]",
    "**",
    "__class__",
    "import",
    "os",
    "'",
    "lambda",
    ":",
    "=",
    " ",
]


@pytest.fixture
def no_python_evaluation(monkeypatch):
    """The parser must not reach for Python's own evaluation: these raise
    if it does."""

    def refuse(*_a, **_k):
        raise AssertionError("block_expr called a Python evaluator")

    for name in ("eval", "exec", "compile"):
        monkeypatch.setattr(builtins, name, refuse)
    monkeypatch.setattr(ast, "parse", refuse)
    monkeypatch.setattr(ast, "literal_eval", refuse)


def test_fuzz_token_soup_parses_or_refuses_cleanly(no_python_evaluation):
    rng = random.Random(20261125)
    parsed = refused = 0
    for _ in range(5000):
        text = "".join(rng.choice(_SOUP) for _ in range(rng.randint(1, 14)))
        try:
            node = bx.parse(text)
        except bx.ExprError:
            refused += 1
            continue
        parsed += 1
        try:
            bx.evaluate(node, lambda nm: PARAMS.get(nm, 1.0), LAM)
        except bx.ExprError:
            pass
    # Both outcomes are exercised, so the fuzz is not vacuous either way.
    assert parsed > 300
    assert refused > 300


def _random_tree(rng, depth=0):
    r = rng.random()
    if depth > 5 or r < 0.3:
        return rng.choice(
            [
                bx.Num(rng.choice([1, 2, 3, 7])),
                bx.Num(rng.uniform(-5, 5)),
                bx.Num(-0.0),
                bx.Name(rng.choice(["a", "b", "n", "width"])),
                bx.Wavelength(),
            ]
        )
    if r < 0.4:
        return bx.Neg(_random_tree(rng, depth + 1))
    if r < 0.5:
        return bx.Call(rng.choice(["sin", "cos"]), _random_tree(rng, depth + 1))
    if r < 0.55:
        return bx.Call("sqrt", bx.BinOp("*", (t := _random_tree(rng, depth + 1)), t))
    op = rng.choice("+-*/")
    return bx.BinOp(op, _random_tree(rng, depth + 1), _random_tree(rng, depth + 1))


def _bits(v):
    return struct.pack("<d", float(v)), type(v)


def test_fuzz_generated_python_is_the_same_arithmetic():
    """``to_python``'s text, evaluated by Python (here, in the test only),
    gives the interpreter's bits: the parenthesisation keeps the tree."""
    rng = random.Random(7)
    env = {**PARAMS, "math": math, "wavelength": LAM}
    checked = 0
    for _ in range(3000):
        node = _random_tree(rng)
        try:
            want = bx.evaluate(node, lookup, LAM)
        except bx.ExprError:
            continue
        text = bx.to_python(node, lambda nm: nm)
        got = eval(text, {"__builtins__": {}}, env)  # noqa: S307 — test oracle
        assert _bits(got) == _bits(want), text
        checked += 1
    assert checked > 1500


def test_parenthesisation_keeps_a_right_operand_at_the_same_precedence():
    spell = str
    assert bx.to_python(bx.parse("a + (b + n)"), spell) == "a + (b + n)"
    assert bx.to_python(bx.parse("(a + b) + n"), spell) == "a + b + n"
    assert bx.to_python(bx.parse("a / (b * n)"), spell) == "a / (b * n)"
    assert bx.to_python(bx.parse("-(a * b)"), spell) == "-(a * b)"
    assert bx.to_python(bx.parse("--a"), spell) == "-(-a)"
    assert bx.to_python(bx.parse("λ * -width"), spell) == "wavelength * -width"
    assert bx.to_python(bx.parse("sin(a)"), spell) == "math.sin(math.radians(a))"


@pytest.mark.parametrize("text", ["١٢", "１２", "1\u30002", "1\u00a0+ 2"])
def test_digits_and_spaces_are_ascii_only(text):
    # Unicode decimal digits and spaces are outside the grammar, so refused
    # rather than read as the number they look like.
    with pytest.raises(bx.ExprError, match="is not part of an expression"):
        bx.parse(text)
