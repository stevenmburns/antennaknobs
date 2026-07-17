"""Issue #424: the SY evaluator's hard contract — every failure is a
``ValueError``, every success is a finite float.

The #417 ast-based evaluator violated this on live probes: ZeroDivisionError
and OverflowError escaped, and ``1e5000`` silently put z = inf into wire
geometry. The custom Pratt parser owns its whole grammar (no CPython parser
in the path), enforces explicit depth/size caps, and pins 4nec2's
BASIC-convention precedence: ``^`` binds tighter than unary minus
(``-2^2 = -4``) and associates right (``2^3^2 = 512``).
"""

import random

import pytest

from antennaknobs.nec_import import parse_nec


def _deck(sy, field="h"):
    return f"CE t\n{sy}\nGW 1 11 0 0 0 0 0 {field} 0.001\nGE 0\nEX 0 1 6 0 1 0\nEN\n"


def _h(text):
    return parse_nec(text, name="t").wires[0].p2[2]


# ---- precedence: BASIC convention, pinned -------------------------------


def test_power_binds_tighter_than_unary_minus():
    assert _h(_deck("SY h=-2^2")) == pytest.approx(-4.0)
    assert _h(_deck("SY h=0-(-2^2)")) == pytest.approx(4.0)


def test_power_is_right_associative():
    assert _h(_deck("SY h=2^3^2")) == pytest.approx(512.0)


def test_unary_in_exponent():
    assert _h(_deck("SY h=2^-3+1")) == pytest.approx(1.125)


# ---- the hard contract ----------------------------------------------------


@pytest.mark.parametrize(
    "expr",
    [
        "1/0",
        "1%0",
        "9e9^9e9",  # overflow
        "9^9^9^9",  # nested-pow overflow
        "1e5000",  # non-finite literal
        "-1e5000",
        "2*1e308*1e308",  # overflow via multiply
        "sqr(-1)",  # domain error
        "log(0)",
        "(" * 200 + "1" + ")" * 200,  # depth cap
        "1+" * 500 + "1",  # size cap
        "",
        "(",
        "1+",
        "1 2",
        "sin()",
        "sin(1,2)",
        "nosuchfn(1)",
        "import os",
        "__class__",
        "1..5",
    ],
)
def test_hostile_expression_is_clean_valueerror(expr):
    with pytest.raises(ValueError):
        parse_nec(_deck(f"SY h={expr}"), name="t")


def test_hostile_field_expression_is_clean_valueerror():
    with pytest.raises(ValueError):
        parse_nec(_deck("SY a=1", field="a/0"), name="t")


def test_fuzz_finite_or_valueerror():
    """Invariant sweep: random expressions either evaluate to a finite float
    or raise ValueError — never anything else, never a non-finite value."""
    rng = random.Random(424)
    atoms = ["1", "2.5", ".5", "3.", "1e2", "a", "b", "pi", "mm", "9e300"]
    ops = ["+", "-", "*", "/", "^", "%"]
    funcs = ["sin", "cos", "sqr", "atn", "int", "log", "exp", "abs"]

    def gen(depth):
        r = rng.random()
        if depth > 4 or r < 0.35:
            return rng.choice(atoms)
        if r < 0.55:
            return f"{gen(depth + 1)}{rng.choice(ops)}{gen(depth + 1)}"
        if r < 0.7:
            return f"({gen(depth + 1)})"
        if r < 0.85:
            return f"-{gen(depth + 1)}"
        return f"{rng.choice(funcs)}({gen(depth + 1)})"

    for _ in range(300):
        expr = gen(0)
        deck = _deck(f"SY a=2, b=0, h={expr}")
        try:
            h = _h(deck)
        except ValueError:
            continue
        assert h == h and abs(h) != float("inf"), expr  # finite


def test_normal_expressions_still_work():
    assert _h(_deck("SY h=10*sin(30)")) == pytest.approx(5.0)
    assert _h(_deck("SY h=61ft")) == pytest.approx(61 * 0.3048)
    assert _h(_deck("SY lambda=300/14.1, h=lambda/4")) == pytest.approx(300 / 14.1 / 4)
