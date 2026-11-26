"""Interpreter ≡ generated Python (docs/design/block-builder.md, "Testing").

For every template and a fuzzed set of block programs, the wires the
interpreter builds equal, bit for bit, the wires from exec-ing the code
``block_codegen`` writes. This is the gate that keeps G1 true: the Python a
user is shown is the design the server ran. Exec happens here, in the test,
and nowhere in the package.

The disabled-path probe at the end swaps one emitter for one that drops its
transform and proves the gate then fails, so a green run is not a gate that
compares nothing."""

from __future__ import annotations

import random
import struct

import pytest

from antennaknobs import block_codegen, block_design
from antennaknobs.block_design import BlockError, blocks_builder
from antennaknobs.block_templates import NAMES, template


def _f(v):
    return struct.pack("<d", float(v))


def _bits(wires):
    """Every field of every wire, floats as their IEEE bytes, so 0.0 and
    -0.0 differ and so does any last bit."""
    out = []
    for w in wires:
        ex = None if w.ex is None else (_f(complex(w.ex).real), _f(complex(w.ex).imag))
        out.append(
            (
                tuple(_f(c) for c in w.p0),
                tuple(_f(c) for c in w.p1),
                w.n_seg,
                ex,
                w.name,
                w.spec,
            )
        )
    return out


def _exec_builder(tree):
    ns = {}
    code = block_codegen.generate(tree)
    exec(compile(code, "<generated>", "exec"), ns)  # noqa: S102 — the test's oracle
    return ns["Builder"]


def _params_sets(tree, rng):
    """The defaults, and two draws of every knob within ±20 %."""
    base = dict(blocks_builder(tree).default_params)
    out = [base]
    for _ in range(2):
        p = dict(base)
        for q in tree.get("params", []):
            # An int knob (a repeat count) stays a whole number.
            if not isinstance(q["value"], int):
                p[q["name"]] = q["value"] * rng.uniform(0.8, 1.2)
        out.append(p)
    return out


def assert_equivalent(tree, rng):
    """Interpreter and generated code agree for ``tree`` at several knob
    settings; returns the number of wires compared."""
    ours = blocks_builder(tree)
    theirs = _exec_builder(tree)
    assert dict(ours.default_params) == dict(theirs.default_params)
    n = 0
    for params in _params_sets(tree, rng):
        a = ours(params).build_wires()
        b = theirs(params).build_wires()
        assert _bits(a) == _bits(b)
        n += len(a)
    return n


@pytest.mark.parametrize("name", NAMES)
def test_templates_run_the_same_as_their_python(name):
    assert assert_equivalent(template(name), random.Random(name)) > 0


# -- fuzzed programs ----------------------------------------------------------


class _Fuzz:
    """Random block programs over every block kind. Coordinates come from
    random expressions over the params, the lets and the loop variables, so
    the arithmetic, the scoping and the transforms are all exercised."""

    def __init__(self, rng):
        self.rng = rng
        self.k = 0

    def fresh(self, stem):
        self.k += 1
        return f"{stem}{self.k}"

    def expr(self, values):
        r = self.rng
        atoms = [*values, "λ", repr(round(r.uniform(-3, 3), 3)), str(r.randint(1, 5))]
        a, b, c = (r.choice(atoms) for _ in range(3))
        return r.choice(
            [
                a,
                f"{a} + {b}",
                f"{a} * ({b} - {c})",
                f"-{a} / ({r.randint(2, 9)})",
                f"sin({a} * 40) * {b}",
                f"cos({a}) + sqrt({r.randint(1, 9)} + {b} * {b})",
                f"{a} − {b} × {c} ÷ 7",
            ]
        )

    def coords(self, values):
        return [self.expr(values) for _ in range(3)]

    def body(self, values, points, depth, repeats):
        r = self.rng
        out = []
        values = list(values)
        points = list(points)
        for _ in range(r.randint(1, 4)):
            kind = r.choice(
                ["let", "point", "mirror_point", "wire", "axis", "path", "loop", "nest"]
            )
            if kind == "let":
                name = self.fresh("v")
                out.append({"block": "let", "name": name, "value": self.expr(values)})
                values.append(name)
            elif kind == "point":
                name = self.fresh("P")
                out.append({"block": "point", "name": name, "at": self.coords(values)})
                points.append(name)
            elif kind == "mirror_point" and points:
                name = self.fresh("M")
                out.append(
                    {
                        "block": "mirror_point",
                        "name": name,
                        "of": r.choice(points),
                        "across": r.choice(["yz", "xz", "xy"]),
                    }
                )
                points.append(name)
            elif kind == "wire":
                ends = [
                    r.choice(points) if points and r.random() < 0.6 else None
                    for _ in "ab"
                ]
                w = {
                    "block": "wire",
                    "from": ends[0] or self.coords(values),
                    "to": ends[1] or self.coords(values),
                }
                if r.random() < 0.2:
                    w["feed"] = "centre"
                out.append(w)
            elif kind == "axis":
                axis = r.choice("xyz")
                w = {
                    "block": f"wire_{axis}",
                    "from": self.expr(values),
                    "to": self.expr(values),
                }
                for other in "xyz":
                    if other != axis and r.random() < 0.5:
                        w[other] = self.expr(values)
                if r.random() < 0.2:
                    w["feed"] = "centre"
                out.append(w)
            elif kind in ("path", "loop"):
                n = r.randint(3, 5)
                pts = [
                    r.choice(points)
                    if points and r.random() < 0.3
                    else self.coords(values)
                    for _ in range(n)
                ]
                b = {"block": kind, "points": pts}
                if r.random() < 0.3:
                    b["feed_segment"] = r.randrange(n if kind == "loop" else n - 1)
                out.append(b)
            elif kind == "nest" and depth < 4:
                out.append(self.nest(values, points, depth, repeats))
        return out

    def nest(self, values, points, depth, repeats):
        r = self.rng
        kind = r.choice(
            ["move", "rotate", "mirror", "both_sides", "repeat", "with_wire"]
        )
        if kind == "repeat" and repeats >= 2:
            kind = "move"
        # A transform starts a new frame: its body sees no outer points (Q2).
        inner_points = points if kind == "with_wire" else []
        if kind == "repeat":
            var = self.fresh("i")
            b = {
                "block": "repeat",
                "var": var,
                "count": r.choice([0, 1, 2, 3, "n"]),
                "body": None,
            }
            each = r.choice([None, "move", "rotate"])
            if each == "move":
                b["each"] = {"move": self.coords([*values, var])}
            elif each == "rotate":
                b["each"] = {
                    "rotate": {"axis": r.choice("xyz"), "deg": f"360 * {var} / 3"}
                }
            if each is None:
                inner_points = points
            b["body"] = self.body([*values, var], inner_points, depth + 1, repeats + 1)
            return b
        b = {"block": kind}
        if kind == "move":
            b["by"] = self.coords(values)
        elif kind == "rotate":
            b["axis"] = r.choice("xyz")
            b["deg"] = self.expr(values)
        elif kind in ("mirror", "both_sides"):
            b["across"] = r.choice(["yz", "xz", "xy"])
        else:
            b["spec"] = r.choice(["14-awg", "28-awg-pvc", "12-awg"])
        b["body"] = self.body(values, inner_points, depth + 1, repeats)
        return b

    def program(self):
        r = self.rng
        params = [
            {
                "name": "p",
                "value": round(r.uniform(0.5, 2), 4),
                "unit": "m",
                "min": 0.1,
                "max": 3,
            },
            {"name": "q", "value": round(r.uniform(-1, 1), 4)},
            {"name": "n", "value": r.randint(1, 3)},
        ]
        return {
            "block": "design",
            "name": "fuzz",
            "freq_mhz": round(r.uniform(3, 30), 3),
            "params": params,
            "body": self.body(["p", "q"], [], 0, 0),
        }


def test_fuzzed_programs_run_the_same_as_their_python():
    rng = random.Random(20261125)
    ran = wires = refused = 0
    kinds = set()
    for _ in range(300):
        tree = _Fuzz(rng).program()
        try:
            n = assert_equivalent(tree, rng)
        except BlockError:
            # A random program can make a zero-length wire or a sqrt of a
            # negative; the interpreter refusing it is not a mismatch.
            refused += 1
            continue
        ran += 1
        wires += n
        kinds |= {s.kind for s in _walk(block_design.compile_program(tree).body)}
    assert ran >= 250, (ran, refused)
    assert wires > 3000
    # Every block kind was generated and compared at least once.
    assert kinds == set(block_design._SHAPES)


def _walk(stmts):
    for s in stmts:
        yield s
        yield from _walk(s.body)


# -- the disabled-path probe ---------------------------------------------------


def _move_without_its_transform(g, s, d):
    # The probe: emit a move's body as though the move were not there.
    g.body(s.body, d)


def test_a_codegen_that_drops_a_transform_fails_the_gate(monkeypatch):
    tree = template("hentenna")
    assert_equivalent(tree, random.Random(1))
    monkeypatch.setitem(block_codegen.EMITTERS, "move", _move_without_its_transform)
    with pytest.raises(AssertionError):
        assert_equivalent(tree, random.Random(1))


def test_the_bit_comparison_sees_a_sign_of_zero():
    # The comparison is on bytes: a codegen that wrote 0.0 where the
    # interpreter made -0.0 would be caught even though 0.0 == -0.0.
    from antennaknobs import Wire

    a = [Wire((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))]
    b = [Wire((-0.0, 0.0, 0.0), (1.0, 0.0, 0.0))]
    assert a == b
    assert _bits(a) != _bits(b)


def _seamed():
    """A rotated square from a repeat and a rotated half under both sides:
    each has corners an ulp apart until its block shares the seams."""
    side = {"block": "wire_y", "from": "-h", "to": "h", "x": "h"}
    return {
        "block": "design",
        "name": "seams",
        "freq_mhz": 14.2,
        "params": [{"name": "h", "value": 1.37}],
        "body": [
            {
                "block": "repeat",
                "var": "k",
                "count": 4,
                "each": {"rotate": {"axis": "z", "deg": "90 * k"}},
                "body": [side],
            },
            {
                "block": "both_sides",
                "across": "yz",
                "body": [
                    {
                        "block": "rotate",
                        "axis": "z",
                        "deg": 90,
                        "body": [{"block": "wire_y", "from": 0, "to": 1, "x": 3}],
                    }
                ],
            },
        ],
    }


def test_a_codegen_that_drops_the_shared_seams_fails_the_gate(monkeypatch):
    tree = _seamed()
    assert_equivalent(tree, random.Random(2))
    real = block_codegen.generate

    def unseamed(t):
        return real(t).replace("with st.shared_seams():", "if True:")

    monkeypatch.setattr(block_codegen, "generate", unseamed)
    with pytest.raises(AssertionError):
        assert_equivalent(tree, random.Random(2))


def test_programs_nested_to_the_cap_run_the_same_as_their_python():
    rng = random.Random(12)
    heads = [
        {"block": "move", "by": [0.1, "i0 * 0.2", 0.3]},
        {"block": "rotate", "axis": "x", "deg": 17},
        {"block": "mirror", "across": "xz"},
        {"block": "with_wire", "spec": "14-awg"},
        {"block": "both_sides", "across": "yz"},
        {"block": "rotate", "axis": "y", "deg": "5 + i0"},
    ]
    for _ in range(20):
        body = [{"block": "wire_z", "from": 0.5, "to": 1.5, "x": 0.25}]
        # Outermost a repeat with an each (3), then 9 levels of the rest.
        left = block_design.MAX_NESTING - 3
        while left > 0:
            h = dict(rng.choice(heads))
            cost = 3 if h["block"] == "both_sides" else 1
            if cost > left:
                continue
            left -= cost
            h["body"] = body
            body = [h]
        tree = {
            "block": "design",
            "name": "deep",
            "freq_mhz": 7.1,
            "body": [
                {
                    "block": "repeat",
                    "var": "i0",
                    "count": 3,
                    "each": {"rotate": {"axis": "z", "deg": "120 * i0"}},
                    "body": body,
                }
            ],
        }
        assert assert_equivalent(tree, rng) > 0
