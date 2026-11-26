"""The block builder's arithmetic: a tiny grammar, parsed by hand.

A block program is data that the hosted app may accept from anyone
(docs/design/block-builder.md, G5), so its expressions are parsed here and
never handed to Python's ``eval``, ``exec``, ``compile`` or ``ast``. The
grammar is the whole language::

    expr   := term (("+" | "-" | "−") term)*
    term   := unary (("*" | "×" | "/" | "÷") unary)*
    unary  := ("-" | "−") unary | atom
    atom   := NUMBER | NAME | "λ" | FUNC "(" expr ")" | "(" expr ")"
    FUNC   := sqrt | sin | cos

``sin`` and ``cos`` take degrees, as every angle in the block vocabulary
does (``rotate`` and the ``°`` unit); the generated Python spells them
``math.sin(math.radians(x))``, the catalog's own idiom, so both sides call
the same libm functions on the same doubles. ``λ`` (or ``wavelength``) is
the design wavelength. A NAME is a param, a ``let`` or a loop variable; the
caller decides which names exist.

Everything outside the grammar is refused with :class:`ExprError`: attribute
access, indexing, calls to anything but the three functions, ``**``,
comparisons, strings, unknown names. Size is bounded too, so a hostile
expression cannot exhaust the parser or the evaluator: at most
:data:`MAX_EXPR_CHARS` characters and :data:`MAX_EXPR_DEPTH` levels of
nesting, every literal and every intermediate value finite, and an integer
no larger than 2**53 (above it, int and float arithmetic part ways, so the
generated Python could not promise the interpreter's bits).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# 256 characters is four lines of a hand-written design's longest
# expression; the catalog's longest geometry expression is under 100.
MAX_EXPR_CHARS = 256
# Parentheses, unary minus and calls each nest one level. 32 is far past
# anything readable and far inside Python's recursion limit, which both the
# evaluator here and the code generator's emitter walk under.
MAX_EXPR_DEPTH = 32
# Integers stay integers (so ``range(4)`` and ``360 * i / 4`` read as a
# person writes them), but only while every int is exactly a double.
MAX_EXACT_INT = 2**53

FUNCTIONS = ("sqrt", "sin", "cos")
WAVELENGTH_NAMES = ("λ", "wavelength")


class ExprError(ValueError):
    """An expression outside the grammar, or one that evaluates to no
    finite number. ``message`` is the sentence for the block's badge."""


@dataclass(frozen=True)
class Num:
    value: int | float


@dataclass(frozen=True)
class Name:
    name: str


@dataclass(frozen=True)
class Wavelength:
    pass


@dataclass(frozen=True)
class Neg:
    operand: object


@dataclass(frozen=True)
class BinOp:
    op: str  # one of + - * /
    left: object
    right: object


@dataclass(frozen=True)
class Call:
    func: str  # one of FUNCTIONS
    arg: object


_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<num>(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][+-]?[0-9]+)?)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*|λ)
  | (?P<op>[-+*/()−×÷])
    """,
    # ASCII: \s and the digit classes match only what the grammar names,
    # not every Unicode space or decimal digit ("١٢" is refused, not 12).
    re.VERBOSE | re.ASCII,
)
_CANONICAL_OP = {"−": "-", "×": "*", "÷": "/"}


def _tokens(text):
    pos = 0
    out = []
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            ch = text[pos]
            raise ExprError(
                f"{ch!r} at position {pos + 1} is not part of an expression "
                "(numbers, names, λ, + − × ÷, parentheses, sqrt/sin/cos)"
            )
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        tok = m.group()
        if kind == "op":
            tok = _CANONICAL_OP.get(tok, tok)
        out.append((kind, tok, m.start()))
    return out


def number(value):
    """``value`` as an expression literal, refused unless it is a finite
    int or float (a JSON ``true`` is a bool, which is an int to Python)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ExprError(f"{value!r} is not a number")
    return Num(_checked(value))


def _checked(v):
    if isinstance(v, int):
        if abs(v) > MAX_EXACT_INT:
            raise ExprError(f"{v} is larger than 2**53, the largest exact integer")
        return v
    if not math.isfinite(v):
        raise ExprError("the value is not a finite number")
    return v


class _Parser:
    def __init__(self, text):
        self.toks = _tokens(text)
        self.i = 0
        self.depth = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def nest(self):
        self.depth += 1
        if self.depth > MAX_EXPR_DEPTH:
            raise ExprError(f"the expression nests deeper than {MAX_EXPR_DEPTH} levels")

    def expr(self):
        node = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            node = BinOp(op, node, self.term())
        return node

    def term(self):
        node = self.unary()
        while self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            node = BinOp(op, node, self.unary())
        return node

    def unary(self):
        if self.peek()[1] == "-":
            self.take()
            self.nest()
            node = Neg(self.unary())
            self.depth -= 1
            return node
        return self.atom()

    def atom(self):
        kind, tok, pos = self.take()
        if kind is None:
            raise ExprError("the expression ends where a value was expected")
        if kind == "num":
            v = float(tok) if any(c in tok for c in ".eE") else int(tok)
            try:
                return Num(_checked(v))
            except ExprError as exc:
                raise ExprError(f"the literal {tok}: {exc}") from None
        if tok == "(":
            self.nest()
            node = self.expr()
            self.expect(")")
            self.depth -= 1
            return node
        if kind == "name":
            if self.peek()[1] == "(":
                if tok not in FUNCTIONS:
                    raise ExprError(
                        f"{tok}() is not a function here; the functions are "
                        f"{', '.join(FUNCTIONS)}"
                    )
                self.take()
                self.nest()
                node = Call(tok, self.expr())
                self.expect(")")
                self.depth -= 1
                return node
            if tok in WAVELENGTH_NAMES:
                return Wavelength()
            if tok in FUNCTIONS:
                raise ExprError(f"{tok} is a function: write {tok}(...)")
            return Name(tok)
        raise ExprError(f"{tok!r} at position {pos + 1} is not where a value goes")

    def expect(self, want):
        kind, tok, pos = self.take()
        if tok != want:
            where = "the end" if kind is None else f"{tok!r} at position {pos + 1}"
            raise ExprError(f"expected {want!r}, found {where}")


def parse(text):
    """The expression tree of ``text``, or :class:`ExprError`."""
    if not isinstance(text, str):
        raise ExprError(f"{text!r} is not an expression")
    if len(text) > MAX_EXPR_CHARS:
        raise ExprError(f"the expression is longer than {MAX_EXPR_CHARS} characters")
    p = _Parser(text)
    if not p.toks:
        raise ExprError("the expression is empty")
    node = p.expr()
    kind, tok, pos = p.peek()
    if kind is not None:
        raise ExprError(
            f"{tok!r} at position {pos + 1} does not continue the expression"
        )
    return node


def names(node):
    """Every NAME the expression reads, in first-use order."""
    out = []

    def walk(n):
        if isinstance(n, Name):
            if n.name not in out:
                out.append(n.name)
        elif isinstance(n, Neg):
            walk(n.operand)
        elif isinstance(n, BinOp):
            walk(n.left)
            walk(n.right)
        elif isinstance(n, Call):
            walk(n.arg)

    walk(node)
    return out


def evaluate(node, lookup, wavelength):
    """The value of ``node``. ``lookup(name)`` gives a NAME's value and
    ``wavelength`` is λ in metres. The arithmetic is Python's own on the
    same operands in the same order as :func:`to_python`'s text, which is
    what lets the interpreter and the generated code agree bit for bit."""
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Name):
        return lookup(node.name)
    if isinstance(node, Wavelength):
        return wavelength
    if isinstance(node, Neg):
        return _checked(-evaluate(node.operand, lookup, wavelength))
    if isinstance(node, BinOp):
        a = evaluate(node.left, lookup, wavelength)
        b = evaluate(node.right, lookup, wavelength)
        if node.op == "+":
            return _checked(a + b)
        if node.op == "-":
            return _checked(a - b)
        if node.op == "*":
            return _checked(a * b)
        if b == 0:
            raise ExprError("division by zero")
        return _checked(a / b)
    if isinstance(node, Call):
        x = evaluate(node.arg, lookup, wavelength)
        if node.func == "sqrt":
            if x < 0:
                raise ExprError(f"sqrt of a negative number ({x:g})")
            return math.sqrt(x)
        if node.func == "sin":
            return math.sin(math.radians(x))
        return math.cos(math.radians(x))
    raise TypeError(f"not an expression node: {node!r}")


# Precedence for parenthesising: a sum, a product, a unary minus, an atom.
_PREC = {"+": 1, "-": 1, "*": 2, "/": 2}


def to_python(node, spell):
    """``node`` as Python source. ``spell(name)`` gives a NAME's spelling
    (``self.width`` for a param, the bare name for a local). The text
    parses back to the same tree, so it evaluates in the same order:
    a right operand at its parent's precedence keeps its parentheses,
    because ``a + (b + c)`` and ``a + b + c`` round differently."""
    return _emit(node, spell)[0]


def _emit(node, spell):
    if isinstance(node, Num):
        text = repr(node.value)
        return text, (3 if text.startswith("-") else 4)
    if isinstance(node, Name):
        return spell(node.name), 4
    if isinstance(node, Wavelength):
        return "wavelength", 4
    if isinstance(node, Neg):
        text, prec = _emit(node.operand, spell)
        return "-" + (f"({text})" if prec <= 3 else text), 3
    if isinstance(node, BinOp):
        p = _PREC[node.op]
        lt, lp = _emit(node.left, spell)
        rt, rp = _emit(node.right, spell)
        if lp < p:
            lt = f"({lt})"
        if rp <= p:
            rt = f"({rt})"
        return f"{lt} {node.op} {rt}", p
    if isinstance(node, Call):
        inner = _emit(node.arg, spell)[0]
        if node.func == "sqrt":
            return f"math.sqrt({inner})", 4
        return f"math.{node.func}(math.radians({inner}))", 4
    raise TypeError(f"not an expression node: {node!r}")
