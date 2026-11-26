"""Block programs as Python: the readable twin of ``block_design``.

:func:`generate` renders a block program as the house-style design a careful
author would write: an ``AntennaBuilder`` subclass whose ``build_wires``
drives a ``TransformStack`` with ``with st.push_pop_tr(...)``, ``st.path``,
``st.wire_x`` and plain ``for`` loops, one statement or one ``with`` per
block (docs/design/block-builder.md, "The block vocabulary"). Names carry
through: a param is ``self.<name>``, a let or a point is the bare name.

The text is for display and export only; nothing here executes it. The
interpreter stays the one that runs a block design, and
``tests/test_block_equivalence.py`` holds the two to the same bits.

The file ends with a trailer, ``# antennaknobs-blocks: v1 <base64>``, the
block program as canonical JSON. :func:`reopen` gives the program back only
when the code above the trailer is still exactly what the trailer
generates; a hand-edited file raises :class:`HandEditedError`, carrying the
saved program, and is never parsed as Python.
"""

from __future__ import annotations

import base64
import binascii
import json

from . import block_expr as bx
from .block_design import PLANE_AXIS, compile_program

TRAILER_PREFIX = "# antennaknobs-blocks: v1 "
_INDENT = "    "
_LINE = 88  # ruff format's line length, so a short point stays on one line
_MIRROR = {"yz": "mirrorYZ", "xz": "mirrorXZ", "xy": "mirrorXY"}
_ROT = {"x": "rotX", "y": "rotY", "z": "rotZ"}
_EX = "1 + 0j"


class NotABlocksFileError(ValueError):
    """The text carries no readable ``antennaknobs-blocks`` trailer."""


class HandEditedError(ValueError):
    """The code no longer matches the program its trailer holds. ``tree``
    is that saved program, for an editor that offers to open the blocks as
    they were saved (and lose the hand edits)."""

    def __init__(self, tree):
        self.tree = tree
        super().__init__(
            "this file was edited by hand after the block builder wrote it; "
            "its code no longer matches its blocks"
        )


def canonical_json(tree) -> str:
    return json.dumps(tree, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class _Gen:
    def __init__(self, prog):
        self.prog = prog
        self.params = {p.name for p in prog.params}
        self.lines = []

    def spell(self, name):
        return f"self.{name}" if name in self.params else name

    def e(self, node):
        return bx.to_python(node, self.spell)

    def triple(self, t):
        return "(" + ", ".join(self.e(c) for c in t) + ")"

    def end(self, ref):
        kind, v = ref
        return v if kind == "point" else self.triple(v)

    def emit(self, depth, text):
        self.lines.append(_INDENT * depth + text)

    def body(self, stmts, depth):
        if not stmts:
            self.emit(depth, "pass")
        for s in stmts:
            EMITTERS[s.kind](self, s, depth)


def _let(g, s, d):
    g.emit(d, f"{s.args['name']} = {g.e(s.args['value'])}")


def _point(g, s, d):
    line = f"{s.args['name']} = {g.triple(s.args['at'])}"
    if len(_INDENT * d + line) <= _LINE:
        g.emit(d, line)
        return
    # Too long for one line: one coordinate a line, as ruff format writes it.
    g.emit(d, f"{s.args['name']} = (")
    for c in s.args["at"]:
        g.emit(d + 1, f"{g.e(c)},")
    g.emit(d, ")")


def _mirror_point(g, s, d):
    p, k = s.args["of"], PLANE_AXIS[s.args["across"]]
    parts = ", ".join(f"-{p}[{i}]" if i == k else f"{p}[{i}]" for i in range(3))
    g.emit(d, f"{s.args['name']} = ({parts})")


def _feed(s):
    return f", ex={_EX}" if s.args["ex"] is not None else ""


def _wire(g, s, d):
    a, b = g.end(s.args["from"]), g.end(s.args["to"])
    g.emit(d, f"st.emit(Wire({a}, {b}{_feed(s)}))")


def _axis_wire(g, s, d):
    off = "".join(f", {k}={g.e(v)}" for k, v in s.args["off"].items())
    a, b = g.e(s.args["from"]), g.e(s.args["to"])
    g.emit(d, f"st.{s.kind}({a}, {b}{off}{_feed(s)})")


def _path(g, s, d):
    refs = s.args["points"]
    pts = "[" + ", ".join(g.end(r) for r in refs) + "]"
    closed = s.kind == "loop"
    extra = ", closed=True" if closed else ""
    seg = s.args["feed_segment"]
    if seg is not None:
        extra += f", ex={_EX}"
        # One wire needs no index; the interpreter passes 0, the same wire.
        if closed or len(refs) > 2:
            extra += f", ex_segment={seg}"
    g.emit(d, f"st.path({pts}{extra})")


def _with(g, s, d, head):
    g.emit(d, f"with {head}:")
    g.body(s.body, d + 1)


def _move(g, s, d):
    x, y, z = (g.e(c) for c in s.args["by"])
    _with(g, s, d, f"st.push_pop_tr(Transform.translate({x}, {y}, {z}))")


def _rotate(g, s, d):
    _with(
        g,
        s,
        d,
        f"st.push_pop_tr(Transform.{_ROT[s.args['axis']]}({g.e(s.args['deg'])}))",
    )


def _mirror(g, s, d):
    _with(g, s, d, f"st.push_pop_tr(Transform.{_MIRROR[s.args['across']]}())")


def _both_sides(g, s, d):
    g.emit(d, f"for side in (Transform(), Transform.{_MIRROR[s.args['across']]}()):")
    _with(g, s, d + 1, "st.push_pop_tr(side)")


def _repeat(g, s, d):
    count = s.args["count"]
    if isinstance(count, bx.Num):
        n = repr(int(count.value))
    else:
        # The interpreter refuses a count that is not a whole number, so
        # int() here only changes the type, never the value.
        n = f"int({g.e(count)})"
    g.emit(d, f"for {s.args['var']} in range({n}):")
    each = s.args["each"]
    if each is None:
        g.body(s.body, d + 1)
    elif each[0] == "move":
        x, y, z = (g.e(c) for c in each[1])
        _with(g, s, d + 1, f"st.push_pop_tr(Transform.translate({x}, {y}, {z}))")
    else:
        _with(g, s, d + 1, f"st.push_pop_tr(Transform.{_ROT[each[1]]}({g.e(each[2])}))")


def _with_wire(g, s, d):
    _with(g, s, d, f'st.wire_spec(WIRES["{s.args["spec"]}"])')


# One emitter per block kind. A table, so a test can swap one out and prove
# the equivalence gate notices (the disabled-path probe).
EMITTERS = {
    "let": _let,
    "point": _point,
    "mirror_point": _mirror_point,
    "wire": _wire,
    "wire_x": _axis_wire,
    "wire_y": _axis_wire,
    "wire_z": _axis_wire,
    "path": _path,
    "loop": _path,
    "move": _move,
    "rotate": _rotate,
    "mirror": _mirror,
    "both_sides": _both_sides,
    "repeat": _repeat,
    "with_wire": _with_wire,
}


def _module(prog, body_lines):
    out = [f"# {prog.name}", "#"]
    out += [
        "# Written by the antennaknobs block builder from the block program in",
        "# this file's last line. A hand edit is fine Python, but the builder",
        "# then keeps the file as Python and will not reopen it as blocks.",
        "",
    ]
    if prog.uses_math:
        out.append("import math")
    out.append("from types import MappingProxyType")
    out.append("")
    names = ["AntennaBuilder"]
    if prog.uses_transform:
        names.append("Transform")
    names.append("TransformStack")
    if prog.uses_wire:
        names.append("Wire")
    out.append(f"from antennaknobs import {', '.join(names)}")
    if prog.uses_wires_catalog:
        out.append("from antennaknobs.wire_catalog import WIRES")
    out += ["", "", "class Builder(AntennaBuilder):"]
    out.append(f"{_INDENT}default_params = MappingProxyType(")
    out.append(f"{_INDENT * 2}{{")
    defaults = prog.default_params
    for k, v in defaults.items():
        if k == "ui_params":
            continue
        out.append(f'{_INDENT * 3}"{k}": {v!r},')
    if "ui_params" in defaults:
        out.append(f'{_INDENT * 3}"ui_params": MappingProxyType(')
        out.append(f"{_INDENT * 4}{{")
        for k, rng in defaults["ui_params"].items():
            inner = ", ".join(f'"{rk}": {rv!r}' for rk, rv in rng.items())
            out.append(f'{_INDENT * 5}"{k}": {{{inner}}},')
        out.append(f"{_INDENT * 4}}}")
        out.append(f"{_INDENT * 3}),")
    out.append(f"{_INDENT * 2}}}")
    out.append(f"{_INDENT})")
    out += ["", f"{_INDENT}def build_wires(self):"]
    if prog.uses_wavelength:
        out.append(f"{_INDENT * 2}wavelength = self.design_wavelength")
    out.append(f"{_INDENT * 2}st = TransformStack()")
    out += body_lines
    out.append(f"{_INDENT * 2}return st.wires")
    return out


def generate_code(tree) -> str:
    """The Python for ``tree`` without its trailer."""
    prog = compile_program(tree)
    g = _Gen(prog)
    for s in prog.body:
        EMITTERS[s.kind](g, s, 2)
    return "\n".join(_module(prog, g.lines)) + "\n"


def trailer(tree) -> str:
    data = base64.b64encode(canonical_json(tree).encode("utf-8")).decode("ascii")
    return TRAILER_PREFIX + data


def generate(tree) -> str:
    """The saved ``.py`` for ``tree``: :func:`generate_code` and the
    trailer that lets :func:`reopen` give the blocks back."""
    return generate_code(tree) + "\n\n" + trailer(tree) + "\n"


def reopen(text) -> dict:
    """The block program a saved file holds. Raises
    :class:`NotABlocksFileError` for a file with no readable trailer and
    :class:`HandEditedError` when the code is no longer what the trailer
    generates. Only the trailer is decoded; the code is compared as text."""
    text = text.replace("\r\n", "\n")
    body = text.rstrip("\n")
    head, _, last = body.rpartition("\n")
    if not last.startswith(TRAILER_PREFIX):
        raise NotABlocksFileError("this file has no antennaknobs-blocks trailer")
    try:
        raw = base64.b64decode(last[len(TRAILER_PREFIX) :].strip(), validate=True)
        tree = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        raise NotABlocksFileError(
            "the antennaknobs-blocks trailer is not readable"
        ) from None
    try:
        expected = generate(tree)
    except ValueError:
        raise NotABlocksFileError(
            "the antennaknobs-blocks trailer holds no valid block program"
        ) from None
    if text != expected:
        raise HandEditedError(tree)
    return tree
