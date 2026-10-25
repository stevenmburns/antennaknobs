"""Reading analyses back from their text, without running it (AK#2045).

A shared link carries the analyses a page built as the same stylized Python
a design's ``build_analyses()`` returns and `analyses.to_code` prints (``an.
Analysis(...)``, ``an.Sweep(...)``, ...), compressed the way an opened deck
is (deflate-raw, base64url: `pack` / `unpack`, the browser's
``CompressionStream("deflate-raw")``).

A link is a stranger's input, and on the hosted app ``exec`` of it would be
remote code execution, so this module NEVER executes the text. `read` parses
it with `ast` and walks the tree itself, constructing values only through a
whitelist of this package's own spec constructors (`CONSTRUCTORS`), from
keyword arguments, tuples and lists, dict literals with string keys (a group
knob's entries in an ``an.State``) and literal constants (numbers, a unary
minus on a number, strings, booleans, None). Every other node is refused BY
NAME (``refused: Name 'os'``, ``refused: Lambda``), before anything is
built. The constructors run their own checks, so a value the text could not
have been written for by hand is refused the same way it would be in a
design file.

What is not here, by design:

- ``an.Metric``: a callable metric names a Python function, and a function
  comes from a design or study file, never from a link (the rule
  `analyses.from_data` keeps for the workbench's data).
- any name but ``an``, any attribute but a whitelisted ``an.<Name>``, any
  call but a whitelisted constructor's, and any positional argument beyond
  the ones the printed form itself writes (`POSITIONAL`).

Bounds come first, so a hostile link costs no more than its own length:
`MAX_PACKED_CHARS` on the link parameter, `MAX_TEXT_CHARS` on the text it
decompresses to (the decompressor stops at that many bytes, so a small
payload cannot expand into a large one), `MAX_DEPTH` on bracket nesting
(counted on the token stream before `ast` sees the text) and `MAX_NODES` on
the tree.
"""

from __future__ import annotations

import ast
import base64
import io
import tokenize
import zlib

from antennaknobs import analyses as an

#: The longest link parameter read: the deck cap's own size (8000 characters
#: in ``lib/decks.ts``) with room to spare. Over it is refused unread.
MAX_PACKED_CHARS = 16_000

#: The longest text read, in bytes once decompressed. The three analyses of
#: ``dipoles.two_wire_doublet`` print to about 900; this is ~70 times that.
MAX_TEXT_CHARS = 64_000

#: The deepest bracket nesting read. The printed form nests about six deep
#: (list, Analysis, Cross, Cell, State, a group's dict).
MAX_DEPTH = 24

#: The most tree nodes read.
MAX_NODES = 20_000


class AnalysesTextError(ValueError):
    """The text (or the link parameter) is refused; the message says why,
    by name."""


# The constructors the text may call, by their ``an.<Name>``, and how many
# positional arguments each takes in the printed form (`analyses._call`
# prints a class's ``_positional`` fields positionally, `to_code` writes
# ``an.knob("name", ...)``, ``an.State("name", ...)`` and ``an.Role("name")``
# positionally, and the library calls take keywords only).
_CLASSES = (
    an.Analysis,
    an.Sweep,
    an.Cross,
    an.Cell,
    an.Ref,
    an.Hold,
    an.Band,
    an.Knob,
    an.BandResult,
    an.Result,
    an.Optimize,
    an.Rx,
    an.Swr,
    an.S11,
    an.Smith,
    an.Map,
    an.Table,
    an.Knobs,
    an.Elevation,
    an.Azimuth,
    an.PatternTable,
    an.MetricPlot,
    an.ElevationWindow,
    an.GainAt,
    an.PeakGain,
    an.TakeOff,
    an.PeakAzimuth,
    an.FrontToBack,
    an.AzBeamwidth,
    an.ElBeamwidth,
    an.Rdf,
)

#: ``an.<Name>`` -> (constructor, positional arguments allowed).
CONSTRUCTORS = {
    **{c.__name__: (c, len(getattr(c, "_positional", ()))) for c in _CLASSES},
    "State": (an.State, 1),
    "Role": (an.Role, 1),
    "AzMode": (an.AzMode, 1),
    "convergence": (an.convergence, 0),
    "band_swr": (an.band_swr, 0),
    "patterns": (an.patterns, 0),
    "knob": (an.knob, 1),
}

#: ``an.<Name>`` constants the text may name without calling.
CONSTANTS = {
    "FREQUENCY": an.FREQUENCY,
    "DENSITY": an.DENSITY,
    "PEAK_AZ": an.PEAK_AZ,
    "MEAN_AZ": an.MEAN_AZ,
}

#: Positional arguments per constructor, for the refusal's words.
POSITIONAL = {k: n for k, (_, n) in CONSTRUCTORS.items()}

_NOT_FROM_TEXT = {
    "Metric": "a callable metric names a Python function, which comes from a "
    "design or study file, never from shared text",
}


def _refuse(what: str) -> AnalysesTextError:
    return AnalysesTextError(f"refused: {what}")


# ── the link parameter ──────────────────────────────────────────────────────


def pack(text: str) -> str:
    """``text`` as the link carries it: UTF-8, deflate-raw, base64url with
    no padding (what ``lib/decks.ts`` writes for a deck)."""
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = c.compress(text.encode("utf-8")) + c.flush()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def unpack(z: str) -> str:
    """The text `pack` wrote, refused by name when it is over a bound, does
    not decode, or decompresses past `MAX_TEXT_CHARS` (the decompressor is
    told to stop there, so a bomb never expands)."""
    if not isinstance(z, str) or not z:
        raise AnalysesTextError("the link carries no analyses")
    if len(z) > MAX_PACKED_CHARS:
        raise AnalysesTextError(
            f"refused: the analyses parameter is {len(z)} characters, over "
            f"the {MAX_PACKED_CHARS} limit"
        )
    try:
        packed = base64.urlsafe_b64decode(z + "=" * (-len(z) % 4))
        d = zlib.decompressobj(-15)
        data = d.decompress(packed, MAX_TEXT_CHARS + 1)
        if len(data) > MAX_TEXT_CHARS or d.unconsumed_tail:
            raise _too_long()
        data += d.flush()
        if not d.eof:
            raise AnalysesTextError("the link's analyses are cut short")
    except AnalysesTextError:
        raise
    except (ValueError, zlib.error) as exc:
        raise AnalysesTextError(f"the link's analyses do not decode ({exc})") from None
    if len(data) > MAX_TEXT_CHARS:
        raise _too_long()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnalysesTextError(f"the link's analyses are not UTF-8 ({exc})") from None


def _too_long() -> AnalysesTextError:
    return AnalysesTextError(
        f"refused: the analyses decompress past the {MAX_TEXT_CHARS}-byte limit"
    )


# ── the text ────────────────────────────────────────────────────────────────


def write(analyses) -> str:
    """The text of one or more analyses: a list of their `to_code`, which
    `read` reads back to equal values."""
    items = (analyses,) if isinstance(analyses, an.Analysis) else tuple(analyses)
    body = "".join(f"    {an.to_code(a, 4)},\n" for a in items)
    return f"[\n{body}]\n"


def read(text: str) -> tuple[an.Analysis, ...]:
    """The analyses ``text`` writes, without executing it (module docstring):
    one ``an.<...>(...)`` expression, or a list or tuple of them, each an
    ``an.Analysis`` (or a library call that makes one). Anything else is an
    `AnalysesTextError` naming what was refused."""
    if not isinstance(text, str):
        raise AnalysesTextError("the analyses text must be a string")
    if len(text) > MAX_TEXT_CHARS:
        raise _too_long()
    _check_depth(text)
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise AnalysesTextError(f"the analyses text does not parse ({exc})") from None
    n = sum(1 for _ in ast.walk(tree))
    if n > MAX_NODES:
        raise _refuse(f"{n} tree nodes, over the {MAX_NODES} limit")
    # Walk the whole tree for refusals before constructing anything.
    _Check().visit(tree.body)
    body = tree.body
    nodes = body.elts if isinstance(body, (ast.List, ast.Tuple)) else [body]
    out = []
    for node in nodes:
        value = _build(node)
        if not isinstance(value, an.Analysis):
            raise _refuse(
                f"{type(value).__name__} at the top level; the text lists "
                "an.Analysis values"
            )
        out.append(value)
    return tuple(out)


def read_link(z: str) -> tuple[an.Analysis, ...]:
    """`read` of the text a link's ``analyses=`` parameter carries."""
    return read(unpack(z))


def _check_depth(text: str) -> None:
    """Refuse bracket nesting past `MAX_DEPTH` on the token stream, so the
    parser never recurses on a hostile depth (brackets inside a string are
    one STRING token and do not count)."""
    depth = 0
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type != tokenize.OP:
                continue
            if tok.string in "([{":
                depth += 1
                if depth > MAX_DEPTH:
                    raise _refuse(f"nesting deeper than {MAX_DEPTH}")
            elif tok.string in ")]}":
                depth -= 1
    except tokenize.TokenError as exc:
        raise AnalysesTextError(f"the analyses text does not parse ({exc})") from None
    except (SyntaxError, IndentationError) as exc:
        raise AnalysesTextError(f"the analyses text does not parse ({exc})") from None


def _number(node) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    )


def _attr_name(node: ast.Attribute) -> str:
    # The dotted text as written (unparsing is printing, not running),
    # shortened so a hostile chain cannot make a long refusal.
    text = ast.unparse(node)
    return text if len(text) <= 60 else f"{text[:57]}..."


class _Check(ast.NodeVisitor):
    """Every node the text may hold, and a refusal by name for any other.
    It visits only what it allows, so nothing below a refused node is
    reached."""

    def generic_visit(self, node):
        raise _refuse(type(node).__name__)

    def visit_Constant(self, node: ast.Constant):
        v = node.value
        if v is None or isinstance(v, (bool, int, float, str)):
            return
        raise _refuse(f"Constant of type {type(v).__name__}")

    def visit_UnaryOp(self, node: ast.UnaryOp):
        if isinstance(node.op, ast.USub) and _number(node.operand):
            return
        raise _refuse(
            f"UnaryOp {type(node.op).__name__}; only a minus on a literal number"
        )

    def visit_Tuple(self, node: ast.Tuple):
        for e in node.elts:
            self.visit(e)

    visit_List = visit_Tuple

    def visit_Dict(self, node: ast.Dict):
        for k, v in zip(node.keys, node.values, strict=True):
            if k is None:
                raise _refuse("** in a dict")
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                raise _refuse(f"dict key {type(k).__name__}; keys are strings")
            self.visit(v)

    def visit_Name(self, node: ast.Name):
        raise _refuse(f"Name {node.id!r}")

    def visit_Attribute(self, node: ast.Attribute):
        if not (isinstance(node.value, ast.Name) and node.value.id == "an"):
            raise _refuse(f"Attribute {_attr_name(node)!r}")
        if node.attr not in CONSTANTS:
            raise _refuse(f"Attribute {_attr_name(node)!r}")

    def visit_Call(self, node: ast.Call):
        f = node.func
        if not (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Name)
            and f.value.id == "an"
        ):
            what = (
                f"Name {f.id!r}"
                if isinstance(f, ast.Name)
                else f"Attribute {_attr_name(f)!r}"
                if isinstance(f, ast.Attribute)
                else type(f).__name__
            )
            raise _refuse(f"call of {what}")
        if f.attr in _NOT_FROM_TEXT:
            raise _refuse(f"an.{f.attr}: {_NOT_FROM_TEXT[f.attr]}")
        if f.attr not in CONSTRUCTORS:
            raise _refuse(f"call of Attribute {_attr_name(f)!r}")
        allowed = POSITIONAL[f.attr]
        for a in node.args:
            if isinstance(a, ast.Starred):
                raise _refuse(f"Starred argument to an.{f.attr}")
        if len(node.args) > allowed:
            raise _refuse(
                f"positional argument {allowed + 1} to an.{f.attr}, which takes "
                f"{allowed} positionally; pass it by keyword"
            )
        for kw in node.keywords:
            if kw.arg is None:
                raise _refuse(f"** argument to an.{f.attr}")
            if kw.arg.startswith("_"):
                raise _refuse(f"keyword {kw.arg!r} to an.{f.attr}")
        for a in node.args:
            self.visit(a)
        for kw in node.keywords:
            self.visit(kw.value)


def _build(node):
    """The value of a node `_Check` passed."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp):
        return -node.operand.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(_build(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return {k.value: _build(v) for k, v in zip(node.keys, node.values, strict=True)}
    if isinstance(node, ast.Attribute):
        return CONSTANTS[node.attr]
    if isinstance(node, ast.Call):
        fn, _ = CONSTRUCTORS[node.func.attr]
        args = [_build(a) for a in node.args]
        kwargs = {}
        for kw in node.keywords:
            if kw.arg in kwargs:
                raise _refuse(f"keyword {kw.arg!r} given twice to an.{node.func.attr}")
            kwargs[kw.arg] = _build(kw.value)
        try:
            return fn(*args, **kwargs)
        except (TypeError, ValueError) as exc:
            raise AnalysesTextError(f"an.{node.func.attr}: {exc}") from None
    raise _refuse(type(node).__name__)  # unreachable after _Check
