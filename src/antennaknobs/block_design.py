"""Block programs: a design as JSON data, run without ``exec``.

The block builder (docs/design/block-builder.md) stores a design as a tree
of blocks, documented in docs/design/block-json-v1.md. This module checks
the tree (:func:`compile_program`) and runs it (:func:`run`) by driving a
real :class:`~antennaknobs.transform.TransformStack`, so its output is the
``Wire`` list a hand-written ``build_wires()`` returns and everything after
it (``auto_mesh``, the degenerate-wire refusals, the engines) is the
existing pipeline. :func:`blocks_builder` wraps a tree as an
``AntennaBuilder`` subclass. ``block_codegen`` renders the same tree as
Python for display and export; ``tests/test_block_equivalence.py`` holds
the two to the same bits.

No text from the tree is ever executed: expressions go through
``block_expr``'s hand-written parser, names are checked against a fixed
pattern, and a wire catalog name must be a key of ``WIRES``.

Every refusal is a :class:`BlockError` naming the block it belongs to
(its ``id`` if it carries one, else its JSON pointer), so an editor can put
the message on that block. :func:`compile_program` collects every error it
can find in one pass and raises them together as :class:`BlockProgramError`;
:func:`run` stops at the first.

Joins stay inside one transform block (Steve, 2026-11-24, Q2): a point is a
position in the frame of the block it was made in, so a wire may use only
points made in its own frame. ``with_wire`` and a ``repeat`` without an
``each`` transform do not change the frame and so do not end it.
"""

from __future__ import annotations

import builtins
import json
import keyword
import math
import re
from itertools import pairwise
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from . import block_expr as bx
from .builder import AntennaBuilder
from .transform import Transform, TransformStack
from .wire_catalog import WIRES, Wire

SCHEMA_VERSION = 1

# Bounds that hold for any program, so a design from a stranger cannot run
# away on the hosted app (the design note's "Hosted, eventually": a fixed cap
# on loop counts and on nesting). 256 passes covers the catalog's largest
# repeat (120 radials) twice over; three nested repeats is an array of
# rotated elements of repeated parts, more than any catalog design uses.
MAX_REPEAT_COUNT = 256
MAX_REPEAT_NESTING = 3
# The hosted deck upload's segment cap is 3000 and every wire is at least
# one segment, so a program with more wires than that cannot be solved there.
MAX_WIRES = 3000
# A JSON tree this size is hundreds of screens of blocks; the cap bounds the
# compile pass before the run caps apply.
MAX_BLOCKS = 2000
# Statements run plus repeat passes. Wires alone do not bound a run: three
# nested repeats of 256 with only lets inside emit nothing for 16.7 M passes.
# 100 000 is 33 statements for each of MAX_WIRES wires.
MAX_STEPS = 100_000
MAX_NAME_CHARS = 40
MAX_DESIGN_NAME_CHARS = 80
MAX_ID_CHARS = 64
MAX_FILE_BYTES = 1_000_000

UNITS = ("m", "λ", "°", "")
AXES = ("x", "y", "z")
PLANES = ("yz", "xz", "xy")
# The coordinate a plane's mirror negates: Transform.mirrorYZ is x -> -x.
PLANE_AXIS = {"yz": 0, "xz": 1, "xy": 2}
FEED_EX = 1 + 0j

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
# Names the generated module binds or calls; a user name must not shadow one.
_CODEGEN_NAMES = frozenset(
    {
        "self",
        "st",
        "math",
        "side",
        "wavelength",
        "Wire",
        "Transform",
        "TransformStack",
        "WIRES",
        "MappingProxyType",
        "AntennaBuilder",
        "Builder",
        *bx.FUNCTIONS,
        *bx.WAVELENGTH_NAMES,
    }
)
_FRAMEWORK = frozenset(
    {"design_freq", "freq", "ui_params", *AntennaBuilder.FRAMEWORK_PARAMS}
)


class BlockError(ValueError):
    """One refusal, on one block: ``{block_id, message}`` for the editor."""

    def __init__(self, block_id: str, message: str):
        super().__init__(block_id, message)
        self.block_id = block_id
        self.message = message

    def __eq__(self, other):
        return isinstance(other, BlockError) and self.as_dict() == other.as_dict()

    def __hash__(self):
        return hash((self.block_id, self.message))

    def __str__(self):
        return f"block {self.block_id}: {self.message}"

    def as_dict(self):
        return {"block_id": self.block_id, "message": self.message}


class BlockProgramError(ValueError):
    """Every error :func:`compile_program` found, in tree order."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(str(e) for e in self.errors))

    def as_dicts(self):
        return [e.as_dict() for e in self.errors]


# --------------------------------------------------------------------------
# The compiled program: the tree with its expressions parsed and its names
# resolved. Both the interpreter and block_codegen walk this, never the raw
# JSON, so a check made here holds for both.
# --------------------------------------------------------------------------


@dataclass
class Stmt:
    kind: str
    block_id: str
    args: dict
    body: list = field(default_factory=list)


@dataclass
class Param:
    name: str
    value: int | float
    unit: str
    min: int | float | None
    max: int | float | None


@dataclass
class Program:
    name: str
    freq_mhz: int | float
    params: list
    body: list
    uses_wavelength: bool = False
    uses_math: bool = False
    uses_transform: bool = False
    uses_wires_catalog: bool = False
    uses_wire: bool = False

    @property
    def default_params(self):
        d = {"design_freq": self.freq_mhz, "freq": self.freq_mhz}
        ui = {}
        for p in self.params:
            d[p.name] = p.value
            rng = {k: v for k, v in (("min", p.min), ("max", p.max)) if v is not None}
            if rng:
                ui[p.name] = rng
        if ui:
            d["ui_params"] = MappingProxyType(ui)
        return MappingProxyType(d)


# What each block kind holds: (required keys, optional keys, has a body).
_SHAPES = {
    "let": ({"name", "value"}, set(), False),
    "point": ({"name", "at"}, set(), False),
    "mirror_point": ({"name", "of", "across"}, set(), False),
    "wire": ({"from", "to"}, {"feed"}, False),
    "wire_x": ({"from", "to"}, {"y", "z", "feed"}, False),
    "wire_y": ({"from", "to"}, {"x", "z", "feed"}, False),
    "wire_z": ({"from", "to"}, {"x", "y", "feed"}, False),
    "path": ({"points"}, {"feed_segment"}, False),
    "loop": ({"points"}, {"feed_segment"}, False),
    "move": ({"by", "body"}, set(), True),
    "rotate": ({"axis", "deg", "body"}, set(), True),
    "mirror": ({"across", "body"}, set(), True),
    "both_sides": ({"across", "body"}, set(), True),
    "repeat": ({"count", "body"}, {"var", "each"}, True),
    "with_wire": ({"spec", "body"}, set(), True),
}
_DESIGN_KEYS = ({"block", "name", "freq_mhz", "body"}, {"params", "id", "schema"})
_PARAM_KEYS = ({"name", "value"}, {"unit", "min", "max"})


class _Scope:
    """Names visible at one point of the tree. ``frame`` marks a block that
    changes the coordinate frame; a point lookup does not cross it."""

    def __init__(self, parent=None, frame=False, owner=None):
        self.parent = parent
        self.frame = frame
        self.owner = owner
        self.values = {}  # let / loop variable -> declaring block id
        self.points = {}  # point -> declaring block id

    def value(self, name):
        s = self
        while s is not None:
            if name in s.values:
                return True
            s = s.parent
        return False

    def point(self, name):
        """``(found, other_frame_block)``: whether the point is visible here,
        and if not, the id of the block that made it in another frame."""
        s = self
        crossed = False
        while s is not None:
            if name in s.points:
                return (not crossed), s.points[name]
            if s.frame:
                crossed = True
            s = s.parent
        return False, None


class _Compiler:
    def __init__(self):
        self.errors = []
        self.declared = {}  # every name in the program -> its block id
        self.params = set()
        self.blocks = 0
        self.prog = None

    def err(self, block_id, message):
        self.errors.append(BlockError(block_id, message))

    # -- names --------------------------------------------------------------

    def declare(self, block_id, name, what):
        if not isinstance(name, str) or not _NAME.match(name):
            self.err(
                block_id,
                f"{name!r} is not a {what} name: use letters, digits and _ "
                "(a letter first)",
            )
            return False
        if len(name) > MAX_NAME_CHARS:
            self.err(
                block_id, f"the {what} name {name!r} is longer than {MAX_NAME_CHARS}"
            )
            return False
        if (
            keyword.iskeyword(name)
            or name in _CODEGEN_NAMES
            or hasattr(builtins, name)
            or name in _FRAMEWORK
            or hasattr(AntennaBuilder, name)
        ):
            self.err(block_id, f"{name!r} is a reserved name; choose another")
            return False
        if name in self.declared:
            self.err(
                block_id,
                f"{name!r} is already the name of block {self.declared[name]}; "
                "every name in a design is used once",
            )
            return False
        self.declared[name] = block_id
        return True

    # -- expressions --------------------------------------------------------

    def expr(self, block_id, raw, scope, what):
        try:
            if isinstance(raw, dict):
                if set(raw) != {"ref"}:
                    raise bx.ExprError(f"{what}: an object here holds only 'ref'")
                node = bx.parse(raw["ref"])
                if not isinstance(node, bx.Name | bx.Wavelength):
                    raise bx.ExprError(f"{what}: 'ref' names one param or let")
            elif isinstance(raw, str):
                node = bx.parse(raw)
            else:
                node = bx.number(raw)
        except bx.ExprError as exc:
            self.err(block_id, f"{what}: {exc}")
            return None
        for name in bx.names(node):
            if name not in self.params and not scope.value(name):
                where = self.declared.get(name)
                hint = (
                    f" (block {where} declares it, but not where this block can see it)"
                    if where
                    else ""
                )
                self.err(block_id, f"{what}: no param or let is named {name!r}{hint}")
                return None
        self._note_uses(node)
        return node

    def _note_uses(self, node):
        if isinstance(node, bx.Wavelength):
            self.prog.uses_wavelength = True
        elif isinstance(node, bx.Neg):
            self._note_uses(node.operand)
        elif isinstance(node, bx.BinOp):
            self._note_uses(node.left)
            self._note_uses(node.right)
        elif isinstance(node, bx.Call):
            self.prog.uses_math = True
            self._note_uses(node.arg)

    def triple(self, block_id, raw, scope, what):
        if not isinstance(raw, list) or len(raw) != 3:
            self.err(block_id, f"{what}: give three coordinates [x, y, z]")
            return None
        out = [
            self.expr(block_id, c, scope, f"{what} {a}")
            for a, c in zip(AXES, raw, strict=True)
        ]
        return None if any(c is None for c in out) else tuple(out)

    def point_ref(self, block_id, raw, scope, what):
        """A wire end: a point's name, or literal coordinates."""
        if isinstance(raw, list):
            t = self.triple(block_id, raw, scope, what)
            return None if t is None else ("at", t)
        if isinstance(raw, str):
            found, other = scope.point(raw)
            if found:
                return ("point", raw)
            if other is not None:
                self.err(
                    block_id,
                    f"{what}: point {raw!r} was made in another transform block "
                    f"({other}); a wire joins only points made in its own block",
                )
            else:
                self.err(block_id, f"{what}: no point is named {raw!r} here")
            return None
        self.err(block_id, f"{what}: give a point name or [x, y, z]")
        return None

    # -- blocks -------------------------------------------------------------

    def design(self, tree):
        root = "/"
        if not isinstance(tree, dict) or tree.get("block") != "design":
            self.err(root, 'a block program is one object with "block": "design"')
            return None
        bid = self.block_id(tree, root)
        self.keys(bid, tree, *_DESIGN_KEYS)
        schema = tree.get("schema", SCHEMA_VERSION)
        if schema != SCHEMA_VERSION:
            self.err(
                bid, f"schema {schema!r} is not {SCHEMA_VERSION}, the one this reads"
            )
        name = tree.get("name")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > MAX_DESIGN_NAME_CHARS
            or any(_is_line_breaking(c) for c in name)
        ):
            # The name is the one free text the generated file carries (as a
            # comment), so it may not hold anything that ends a line.
            self.err(
                bid,
                f"name: one line of text, at most {MAX_DESIGN_NAME_CHARS} characters",
            )
            name = "design"
        freq = tree.get("freq_mhz")
        if (
            isinstance(freq, bool)
            or not isinstance(freq, int | float)
            or not math.isfinite(freq)
            or freq <= 0
        ):
            self.err(bid, "freq_mhz: the design frequency, a positive number of MHz")
            freq = 1.0
        self.prog = Program(name=name, freq_mhz=freq, params=[], body=[])
        raw_params = tree.get("params", [])
        if not isinstance(raw_params, list):
            self.err(bid, "params: a list of param objects")
            raw_params = []
        for i, rp in enumerate(raw_params):
            p = self.param(rp, f"/params/{i}")
            if p is not None:
                self.prog.params.append(p)
        self.prog.body = self.body(tree, "", _Scope(frame=True, owner=bid), nesting=0)
        return self.prog

    def param(self, raw, pointer):
        if not isinstance(raw, dict):
            self.err(pointer, "a param is an object with a name and a value")
            return None
        bid = self.block_id(raw, pointer)
        self.keys(bid, raw, *_PARAM_KEYS)
        ok = self.declare(bid, raw.get("name"), "param")
        vals = {}
        for k in ("value", "min", "max"):
            v = raw.get(k)
            if v is None and k != "value":
                vals[k] = None
                continue
            if (
                isinstance(v, bool)
                or not isinstance(v, int | float)
                or not math.isfinite(v)
            ):
                self.err(bid, f"{k}: a finite number")
                ok = False
            vals[k] = v
        unit = raw.get("unit", "")
        if unit not in UNITS:
            self.err(bid, f"unit: one of {', '.join(repr(u) for u in UNITS)}")
            ok = False
        if ok and vals["min"] is not None and vals["max"] is not None:
            if not vals["min"] < vals["max"]:
                self.err(bid, "min must be below max")
                ok = False
        if not ok:
            return None
        self.params.add(raw["name"])
        return Param(raw["name"], vals["value"], unit, vals["min"], vals["max"])

    def block_id(self, raw, pointer):
        given = raw.get("id") if isinstance(raw, dict) else None
        if given is None:
            return pointer or "/"
        if not isinstance(given, str) or not given or len(given) > MAX_ID_CHARS:
            self.err(pointer or "/", f"id: a string of 1 to {MAX_ID_CHARS} characters")
            return pointer or "/"
        return given

    def keys(self, bid, raw, required, optional):
        have = set(raw)
        for k in sorted(required - have):
            self.err(bid, f"missing {k!r}")
        extra = have - required - optional - {"block", "id"}
        for k in sorted(extra):
            self.err(bid, f"{k!r} is not a field of this block")

    def body(self, raw, pointer, scope, nesting):
        items = raw.get("body")
        if not isinstance(items, list):
            if "body" in raw:
                self.err(self.block_id(raw, pointer or "/"), "body: a list of blocks")
            return []
        out = []
        for i, item in enumerate(items):
            s = self.block(item, f"{pointer}/body/{i}", scope, nesting)
            if s is not None:
                out.append(s)
        return out

    def block(self, raw, pointer, scope, nesting):
        self.blocks += 1
        if self.blocks > MAX_BLOCKS:
            if self.blocks == MAX_BLOCKS + 1:
                self.err(pointer, f"the program has more than {MAX_BLOCKS} blocks")
            return None
        if not isinstance(raw, dict):
            self.err(pointer, "a block is an object with a 'block' field")
            return None
        bid = self.block_id(raw, pointer)
        kind = raw.get("block")
        if kind not in _SHAPES:
            self.err(
                bid,
                f"{kind!r} is not a block; the blocks are design, "
                + ", ".join(sorted(_SHAPES)),
            )
            return None
        required, optional, has_body = _SHAPES[kind]
        self.keys(bid, raw, required, optional)
        if not required <= set(raw):
            return None
        handler = getattr(self, f"b_{kind}")
        return handler(raw, bid, pointer, scope, nesting)

    def feed(self, bid, raw):
        f = raw.get("feed")
        if f is None:
            return None
        if f != "centre":
            # An off-centre or end feed is a port on the wire, which the
            # network side owns (phase 3 / the station rail), not an ex.
            self.err(bid, "feed: 'centre' is the only feed position in v1")
            return None
        return FEED_EX

    def b_let(self, raw, bid, pointer, scope, nesting):
        value = self.expr(bid, raw["value"], scope, "value")
        if not self.declare(bid, raw["name"], "let"):
            return None
        # In scope even when its value failed, so the blocks that use it do
        # not each report it again; the program is refused either way.
        scope.values[raw["name"]] = bid
        if value is None:
            return None
        return Stmt("let", bid, {"name": raw["name"], "value": value})

    def b_point(self, raw, bid, pointer, scope, nesting):
        at = self.triple(bid, raw["at"], scope, "at")
        if not self.declare(bid, raw["name"], "point"):
            return None
        scope.points[raw["name"]] = bid
        if at is None:
            return None
        return Stmt("point", bid, {"name": raw["name"], "at": at})

    def b_mirror_point(self, raw, bid, pointer, scope, nesting):
        of = None
        if isinstance(raw["of"], str):
            of = self.point_ref(bid, raw["of"], scope, "of")
        else:
            self.err(bid, "of: the name of a point")
        across = raw["across"]
        if across not in PLANES:
            self.err(bid, f"across: one of {', '.join(PLANES)}")
        if not self.declare(bid, raw["name"], "point"):
            return None
        scope.points[raw["name"]] = bid
        if of is None or across not in PLANES:
            return None
        return Stmt(
            "mirror_point", bid, {"name": raw["name"], "of": of[1], "across": across}
        )

    def b_wire(self, raw, bid, pointer, scope, nesting):
        a = self.point_ref(bid, raw["from"], scope, "from")
        b = self.point_ref(bid, raw["to"], scope, "to")
        ex = self.feed(bid, raw)
        self.prog.uses_wire = True
        if a is None or b is None:
            return None
        return Stmt("wire", bid, {"from": a, "to": b, "ex": ex})

    def _axis(self, raw, bid, scope, axis):
        a = self.expr(bid, raw["from"], scope, "from")
        b = self.expr(bid, raw["to"], scope, "to")
        off = {}
        for k in AXES:
            if k != axis and k in raw:
                off[k] = self.expr(bid, raw[k], scope, k)
        ex = self.feed(bid, raw)
        if a is None or b is None or any(v is None for v in off.values()):
            return None
        return Stmt(f"wire_{axis}", bid, {"from": a, "to": b, "off": off, "ex": ex})

    def b_wire_x(self, raw, bid, pointer, scope, nesting):
        return self._axis(raw, bid, scope, "x")

    def b_wire_y(self, raw, bid, pointer, scope, nesting):
        return self._axis(raw, bid, scope, "y")

    def b_wire_z(self, raw, bid, pointer, scope, nesting):
        return self._axis(raw, bid, scope, "z")

    def _path(self, raw, bid, scope, closed):
        pts = raw["points"]
        least = 3 if closed else 2
        if not isinstance(pts, list) or len(pts) < least:
            self.err(bid, f"points: a list of at least {least} points")
            return None
        refs = [
            self.point_ref(bid, p, scope, f"point {i + 1}") for i, p in enumerate(pts)
        ]
        n = len(pts) if closed else len(pts) - 1
        seg = raw.get("feed_segment")
        if seg is not None and (
            isinstance(seg, bool) or not isinstance(seg, int) or not 0 <= seg < n
        ):
            self.err(bid, f"feed_segment: a wire number from 0 to {n - 1}")
            return None
        if any(r is None for r in refs):
            return None
        return Stmt(
            "loop" if closed else "path", bid, {"points": refs, "feed_segment": seg}
        )

    def b_path(self, raw, bid, pointer, scope, nesting):
        return self._path(raw, bid, scope, closed=False)

    def b_loop(self, raw, bid, pointer, scope, nesting):
        return self._path(raw, bid, scope, closed=True)

    def _nested(self, raw, bid, pointer, scope, nesting, frame):
        inner = _Scope(scope, frame=frame, owner=bid)
        return self.body(raw, pointer, inner, nesting)

    def b_move(self, raw, bid, pointer, scope, nesting):
        by = self.triple(bid, raw["by"], scope, "by")
        body = self._nested(raw, bid, pointer, scope, nesting, frame=True)
        self.prog.uses_transform = True
        return None if by is None else Stmt("move", bid, {"by": by}, body)

    def b_rotate(self, raw, bid, pointer, scope, nesting):
        axis = raw["axis"]
        if axis not in AXES:
            self.err(bid, "axis: x, y or z")
        deg = self.expr(bid, raw["deg"], scope, "deg")
        body = self._nested(raw, bid, pointer, scope, nesting, frame=True)
        self.prog.uses_transform = True
        if axis not in AXES or deg is None:
            return None
        return Stmt("rotate", bid, {"axis": axis, "deg": deg}, body)

    def _plane(self, raw, bid):
        if raw["across"] not in PLANES:
            self.err(bid, f"across: one of {', '.join(PLANES)}")
            return None
        return raw["across"]

    def b_mirror(self, raw, bid, pointer, scope, nesting):
        plane = self._plane(raw, bid)
        body = self._nested(raw, bid, pointer, scope, nesting, frame=True)
        self.prog.uses_transform = True
        return None if plane is None else Stmt("mirror", bid, {"across": plane}, body)

    def b_both_sides(self, raw, bid, pointer, scope, nesting):
        plane = self._plane(raw, bid)
        body = self._nested(raw, bid, pointer, scope, nesting, frame=True)
        self.prog.uses_transform = True
        return (
            None if plane is None else Stmt("both_sides", bid, {"across": plane}, body)
        )

    def b_repeat(self, raw, bid, pointer, scope, nesting):
        if nesting >= MAX_REPEAT_NESTING:
            self.err(bid, f"repeats nest at most {MAX_REPEAT_NESTING} deep")
            return None
        count = self.expr(bid, raw["count"], scope, "count")
        if isinstance(count, bx.Num) and not _valid_count(count.value):
            self.err(bid, f"count: a whole number from 0 to {MAX_REPEAT_COUNT}")
            count = None
        var = raw.get("var", "i")
        inner = _Scope(scope, owner=bid)
        ok = self.declare(bid, var, "loop variable")
        if ok:
            inner.values[var] = bid
        each = None
        if "each" in raw:
            each = self.each(bid, raw["each"], inner)
            inner.frame = True
            self.prog.uses_transform = True
        body = self.body(raw, pointer, inner, nesting + 1)
        if count is None or not ok or ("each" in raw and each is None):
            return None
        return Stmt("repeat", bid, {"count": count, "var": var, "each": each}, body)

    def each(self, bid, raw, scope):
        """A repeat's per-pass transform: ``{"move": [dx, dy, dz]}`` or
        ``{"rotate": {"axis": "z", "deg": expr}}``, its expressions seeing
        the loop variable."""
        if not isinstance(raw, dict) or len(raw) != 1:
            self.err(bid, 'each: {"move": [dx, dy, dz]} or {"rotate": {"axis", "deg"}}')
            return None
        ((kind, val),) = raw.items()
        if kind == "move":
            by = self.triple(bid, val, scope, "each move")
            return None if by is None else ("move", by)
        if kind == "rotate":
            if (
                not isinstance(val, dict)
                or set(val) != {"axis", "deg"}
                or val["axis"] not in AXES
            ):
                self.err(bid, 'each rotate: {"axis": "x" | "y" | "z", "deg": ...}')
                return None
            deg = self.expr(bid, val["deg"], scope, "each rotate deg")
            return None if deg is None else ("rotate", val["axis"], deg)
        self.err(bid, f"each: {kind!r} is not move or rotate")
        return None

    def b_with_wire(self, raw, bid, pointer, scope, nesting):
        spec = raw["spec"]
        if not isinstance(spec, str) or spec not in WIRES:
            self.err(bid, f"spec: one of the wire catalog's names ({', '.join(WIRES)})")
            spec = None
        body = self._nested(raw, bid, pointer, scope, nesting, frame=False)
        self.prog.uses_wires_catalog = True
        return None if spec is None else Stmt("with_wire", bid, {"spec": spec}, body)


def _is_line_breaking(c):
    import unicodedata

    return unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn")


def _valid_count(v):
    if isinstance(v, float):
        if not v.is_integer():
            return False
        v = int(v)
    return 0 <= v <= MAX_REPEAT_COUNT


def compile_program(tree) -> Program:
    """Check ``tree`` (a block program, parsed JSON) and return it compiled,
    or raise :class:`BlockProgramError` with every error found."""
    c = _Compiler()
    prog = c.design(tree)
    if c.errors:
        raise BlockProgramError(c.errors)
    return prog


# --------------------------------------------------------------------------
# The interpreter.
# --------------------------------------------------------------------------


@dataclass
class Run:
    """A program's wires (before ``auto_mesh``: counts are ``None``) and,
    for each, the id of the block that emitted it."""

    wires: list
    block_of_wire: list


class _Env:
    def __init__(self, parent=None):
        self.parent = parent
        self.vars = {}

    def get(self, name):
        e = self
        while e is not None:
            if name in e.vars:
                return e.vars[name]
            e = e.parent
        raise KeyError(name)


class _Interpreter:
    def __init__(self, prog, builder):
        self.prog = prog
        self.builder = builder
        self.params = {p.name for p in prog.params}
        self.wavelength = builder.design_wavelength if prog.uses_wavelength else None
        self.st = TransformStack()
        self.current = None
        self.block_of_wire = []
        self.steps = 0
        self.st.tracer = self._trace

    def _trace(self, kind, st):
        if kind == "emit":
            self.block_of_wire.append(self.current)
            if len(st.wires) > MAX_WIRES:
                raise BlockError(
                    self.current, f"the design has more than {MAX_WIRES} wires"
                )

    def value(self, node, env, bid):
        def lookup(name):
            if name in self.params:
                return getattr(self.builder, name)
            return env.get(name)

        try:
            return bx.evaluate(node, lookup, self.wavelength)
        except bx.ExprError as exc:
            raise BlockError(bid, str(exc)) from None

    def triple(self, t, env, bid):
        return tuple(self.value(c, env, bid) for c in t)

    def end(self, ref, env, bid):
        kind, v = ref
        return env.get(v) if kind == "point" else self.triple(v, env, bid)

    def step(self, bid):
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise BlockError(bid, f"the design runs more than {MAX_STEPS} steps")

    def body(self, stmts, env):
        for s in stmts:
            self.current = s.block_id
            self.step(s.block_id)
            getattr(self, f"r_{s.kind}")(s, env)

    def r_let(self, s, env):
        env.vars[s.args["name"]] = self.value(s.args["value"], env, s.block_id)

    def r_point(self, s, env):
        env.vars[s.args["name"]] = self.triple(s.args["at"], env, s.block_id)

    def r_mirror_point(self, s, env):
        p = env.get(s.args["of"])
        k = PLANE_AXIS[s.args["across"]]
        env.vars[s.args["name"]] = tuple(-c if i == k else c for i, c in enumerate(p))

    def r_wire(self, s, env):
        a = self.end(s.args["from"], env, s.block_id)
        b = self.end(s.args["to"], env, s.block_id)
        if a == b:
            raise BlockError(s.block_id, "the wire starts and ends at the same point")
        self.st.emit(Wire(a, b, ex=s.args["ex"]))

    def _r_axis(self, s, env, method):
        a = self.value(s.args["from"], env, s.block_id)
        b = self.value(s.args["to"], env, s.block_id)
        if a == b:
            raise BlockError(s.block_id, "the wire starts and ends at the same point")
        off = {k: self.value(v, env, s.block_id) for k, v in s.args["off"].items()}
        method(a, b, ex=s.args["ex"], **off)

    def r_wire_x(self, s, env):
        self._r_axis(s, env, self.st.wire_x)

    def r_wire_y(self, s, env):
        self._r_axis(s, env, self.st.wire_y)

    def r_wire_z(self, s, env):
        self._r_axis(s, env, self.st.wire_z)

    def _r_path(self, s, env, closed):
        pts = [self.end(r, env, s.block_id) for r in s.args["points"]]
        ring = [*pts, pts[0]] if closed else pts
        for i, (a, b) in enumerate(pairwise(ring)):
            if a == b:
                raise BlockError(s.block_id, f"wire {i} of the path has zero length")
        seg = s.args["feed_segment"]
        kw = {} if seg is None else {"ex": FEED_EX, "ex_segment": seg}
        self.st.path(pts, closed=closed, **kw)

    def r_path(self, s, env):
        self._r_path(s, env, closed=False)

    def r_loop(self, s, env):
        self._r_path(s, env, closed=True)

    def _r_under(self, s, env, tr):
        with self.st.push_pop_tr(tr):
            self.body(s.body, _Env(env))

    def r_move(self, s, env):
        self._r_under(
            s, env, Transform.translate(*self.triple(s.args["by"], env, s.block_id))
        )

    def r_rotate(self, s, env):
        deg = self.value(s.args["deg"], env, s.block_id)
        self._r_under(s, env, _ROT[s.args["axis"]](deg))

    def r_mirror(self, s, env):
        self._r_under(s, env, _MIRROR[s.args["across"]]())

    def r_both_sides(self, s, env):
        for side in (Transform(), _MIRROR[s.args["across"]]()):
            self._r_under(s, env, side)

    def r_repeat(self, s, env):
        n = self.value(s.args["count"], env, s.block_id)
        if isinstance(n, bool) or not _valid_count(n):
            raise BlockError(
                s.block_id,
                f"count is {n!r}; a whole number from 0 to {MAX_REPEAT_COUNT}",
            )
        var, each = s.args["var"], s.args["each"]
        for i in range(int(n)):
            inner = _Env(env)
            inner.vars[var] = i
            self.current = s.block_id
            self.step(s.block_id)
            if each is None:
                self.body(s.body, inner)
            elif each[0] == "move":
                tr = Transform.translate(*self.triple(each[1], inner, s.block_id))
                with self.st.push_pop_tr(tr):
                    self.body(s.body, _Env(inner))
            else:
                tr = _ROT[each[1]](self.value(each[2], inner, s.block_id))
                with self.st.push_pop_tr(tr):
                    self.body(s.body, _Env(inner))

    def r_with_wire(self, s, env):
        with self.st.wire_spec(WIRES[s.args["spec"]]):
            self.body(s.body, _Env(env))


_ROT = {"x": Transform.rotX, "y": Transform.rotY, "z": Transform.rotZ}
_MIRROR = {"yz": Transform.mirrorYZ, "xz": Transform.mirrorXZ, "xy": Transform.mirrorXY}


def run(prog: Program, builder) -> Run:
    """Run ``prog`` with ``builder``'s knob values; :class:`BlockError` on
    the first block that cannot run."""
    it = _Interpreter(prog, builder)
    it.body(prog.body, _Env())
    return Run(it.st.wires, it.block_of_wire)


def blocks_builder(tree) -> type[AntennaBuilder]:
    """An ``AntennaBuilder`` subclass that builds ``tree``. Its knobs are the
    program's params (plus ``design_freq`` / ``freq``); ``build_wires`` runs
    the interpreter, and ``AntennaBuilder`` meshes the result as it does any
    design's."""
    prog = compile_program(tree)

    class BlocksBuilder(AntennaBuilder):
        default_params = prog.default_params
        block_program = prog

        def build_wires(self):
            return run(prog, self).wires

    BlocksBuilder.__qualname__ = BlocksBuilder.__name__ = "BlocksBuilder"
    return BlocksBuilder


def load_tree(path) -> dict:
    """The block program in the JSON file ``path``."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise SystemExit(f"{p}: no such file")
    if p.stat().st_size > MAX_FILE_BYTES:
        raise SystemExit(f"{p}: a block program is at most {MAX_FILE_BYTES} bytes")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{p}: not JSON ({exc})") from None


def builder_from_json_file(path) -> type[AntennaBuilder]:
    """:func:`blocks_builder` for a ``.json`` file, with every compile error
    printed one per line instead of a traceback."""
    tree = load_tree(path)
    try:
        return blocks_builder(tree)
    except BlockProgramError as exc:
        lines = "\n".join(f"  {e}" for e in exc.errors)
        raise SystemExit(f"{path}: the block program has errors:\n{lines}") from None
