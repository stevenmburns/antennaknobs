"""Draw a design's network as a schematic (issue #652).

The circuit half of a design — feedline, tuner, balun, the port the source
sits on — has until now been visible only as a power-budget loss ledger, so an
element that burns nothing (an ideal `TL`, a `bypass()`) appeared *nowhere*.
This module turns a `Network` into a picture.

## Why authors draw their own boxes

Auto-derivation cannot produce a good schematic. `wire.doublet_ladder_tuner`'s
L-network lowers to `TwoPort → Shunt → TwoPort`: three anonymous boxes, because
"this is an L-network" is not in the branch list — it is in the head of
whoever wrote `l_network_tuner`. So a component may carry its own **fragment**,
this module places the fragments along the chain, and anything without one
falls back to a per-type default symbol. There is always a picture; a fragment
only makes it a *good* picture.

## The vocabulary is deliberately not schemdraw

Fragments are written with :func:`series` / :func:`shunt` / :func:`ground`,
which produce plain data. Rendering happens later, through schemdraw (an
optional extra). That keeps `station.py` free of any drawing library, keeps
the renderer swappable, and means a fragment can be inspected and tested
without drawing anything.

    def l_network_schematic(l_uH, c_pF):
        return (
            series("inductor", f"{l_uH:g} µH"),
            shunt("capacitor", f"{c_pF:g} pF"),
        )

## Layout

Every catalog network is small (≤ 9 branches, node degree ≤ 3), so the layout
is a **spine with ribs**: the path from the source to the antenna runs left to
right, and anything hanging off a spine node drops to ground beneath it. No
graph-layout engine, and none needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .network import (
    TL,
    Admittance,
    Autotransformer,
    BalancedLine,
    FloatingBalun,
    Load,
    PortOnWire,
    PortOnWireFloating,
    Shunt,
    TouchstoneLoad,
    TouchstoneTwoPort,
    Transformer,
    TwoPort,
)

__all__ = [
    "Element",
    "Schematic",
    "Block",
    "series",
    "shunt",
    "ground",
    "lower",
    "fragment_of",
    "terminals_of",
]

#: Symbol kinds the renderer knows. Anything else falls back to a labelled box,
#: so a fragment referencing an unknown kind degrades instead of failing.
KINDS = (
    "inductor",
    "capacitor",
    "resistor",
    "coax",
    "line",
    "transformer",
    "balun",
    "box",
    "short",
    "open",
    "antenna",
    "source",
)


@dataclass(frozen=True)
class Element:
    """One drawn symbol. ``orient`` is ``"series"`` (along the spine) or
    ``"shunt"`` (down to the datum).

    The two text slots mean the same thing whichever way the symbol is drawn:
    ``label`` is *what it is* (an impedance, a value) and ``sublabel`` is the
    second line (a line's length). How a shunt ends is not text — it is
    ``term``, so the renderer draws it as a glyph and writes the word itself.
    """

    kind: str
    label: str = ""
    orient: str = "series"
    sublabel: str = ""
    term: str = ""  # "short" | "open" — a shunt's far end


def series(kind: str, label: str = "", sublabel: str = "") -> Element:
    """A symbol in the signal path."""
    return Element(kind=kind, label=label, orient="series", sublabel=sublabel)


def shunt(kind: str, label: str = "", sublabel: str = "", term: str = "") -> Element:
    """A symbol from the spine down to the common datum.

    ``term`` names how the drop ends — ``"short"`` or ``"open"`` for a stub,
    whose two flavors are different matches and must not draw alike. Left
    empty (an R/L/C to common) the drop simply grounds.
    """
    return Element(kind=kind, label=label, orient="shunt", sublabel=sublabel, term=term)


def ground(label: str = "") -> Element:
    """An explicit connection to the datum (a shorted stub's far end)."""
    return Element(kind="short", label=label, orient="shunt")


@dataclass
class Block:
    """One box on the spine: its label and the elements that draw it."""

    label: str
    elements: tuple[Element, ...]
    path: str = ""
    watts: float | None = None


@dataclass
class Schematic:
    """A whole drawing: the source, the chain, and what it ends in."""

    source: str
    blocks: list[Block] = field(default_factory=list)
    ends_in_antenna: bool = True
    title: str = ""
    notes: list[str] = field(default_factory=list)


# --- terminals -------------------------------------------------------------
# Each branch class names its terminals differently (Shunt/Load use `port`,
# FloatingBalun has a third `primary`), so the lowering needs an explicit map
# rather than a guess-by-field-name. Keep in step with network.py.
TERMINALS = {
    "TL": ("a", "b"),
    "BalancedLine": ("a1", "a2", "b1", "b2"),
    "Shunt": ("port",),
    "Load": ("port",),
    "TwoPort": ("a", "b"),
    "Transformer": ("a", "b"),
    "Autotransformer": ("a", "b"),
    "FloatingBalun": ("primary", "a", "b"),
    "TouchstoneLoad": ("port",),
    "TouchstoneTwoPort": ("a", "b"),
}


def terminals_of(branch) -> tuple[str, ...]:
    """Node names a branch touches, in wiring order."""
    if isinstance(branch, Admittance):
        return tuple(branch.ports)
    names = TERMINALS.get(type(branch).__name__, ())
    return tuple(
        v for v in (getattr(branch, f, None) for f in names) if isinstance(v, str)
    )


# --- default symbols for bare branches -------------------------------------
def _fmt_len(m):
    return f"{m:.2f} m" if m >= 1.0 else f"{m * 100:.0f} cm"


def _val(v):
    """A component value, to three significant figures.

    `%g` prints whatever float arithmetic produced — a trap resonating at a
    round frequency gives "6.46181 pF" and a 1:7 unun gives "1:0.142857",
    neither of which is a number anyone winds or buys. Plain decimal at every
    magnitude a component takes: `%g` would flip to an exponent at 1e5 and
    `%.3g` as early as 1000, which is only a 600 Ω line away.
    """
    a = abs(v)
    if a == 0.0:
        return "0"
    places = max(0, 2 - int(math.floor(math.log10(a))))
    return f"{v:.{places}f}".rstrip("0").rstrip(".") if places else f"{v:.0f}"


def default_elements(branch) -> tuple[Element, ...]:
    """The fallback picture for a branch with no author-supplied fragment.

    Deliberately plain: enough to see that the element is there and what type
    it is. A box that wants to look like what it *is* supplies a fragment.
    """
    if isinstance(branch, TL):
        return (series("coax", f"{_val(branch.z0)} Ω", _fmt_len(branch.length)),)
    if isinstance(branch, BalancedLine):
        return (
            series("line", f"{_val(branch.zdiff)} Ω pair", _fmt_len(branch.length)),
        )
    if isinstance(branch, Transformer):
        return (series("transformer", f"1:{_val(branch.n)}"),)
    if isinstance(branch, Autotransformer):
        return (series("transformer", "autotransformer"),)
    if isinstance(branch, FloatingBalun):
        # Its own kind, not "transformer": the whole point of this branch is
        # that the secondary is NOT bonded to the datum, so it must never be
        # drawn with the return leg a `Transformer` has.
        return (series("balun", f"balun 1:{_val(branch.n)}"),)
    if isinstance(branch, Shunt):
        return (shunt(_rlc_kind(branch), _rlc_label(branch)),)
    if isinstance(branch, Load):
        return (shunt(_rlc_kind(branch), _rlc_label(branch)),)
    if isinstance(branch, TwoPort):
        return (series(_rlc_kind(branch), _rlc_label(branch)),)
    if isinstance(branch, TouchstoneLoad):
        return (shunt("box", "measured 1-port"),)
    if isinstance(branch, TouchstoneTwoPort):
        return (series("box", "measured 2-port"),)
    if isinstance(branch, Admittance):
        return (series("box", "admittance"),)
    return (series("box", type(branch).__name__),)


def _rlc_kind(br):
    """The dominant symbol for an R/L/C branch — whichever one it actually is."""
    has = [
        k for k, v in (("resistor", br.r), ("inductor", br.l), ("capacitor", br.c)) if v
    ]
    return has[0] if len(has) == 1 else ("box" if has else "short")


def _rlc_label(br):
    bits = []
    if getattr(br, "r", None):
        bits.append(f"{_val(br.r)} Ω")
    if getattr(br, "l", None):
        bits.append(f"{_val(br.l * 1e6)} µH")
    if getattr(br, "c", None):
        bits.append(f"{_val(br.c * 1e12)} pF")
    return " ".join(bits) if bits else "short"


# --- lowering --------------------------------------------------------------
def _real_ports(net):
    return {
        name
        for name, p in net.ports.items()
        if isinstance(p, (PortOnWire, PortOnWireFloating))
    }


def fragment_of(net, path):
    """The author-supplied fragment for the instance at ``path``, or None.

    Flattening erases `Instance` objects, so the `Composite` is recovered from
    ``net.composites`` — which exists precisely so the author's drawing
    survives the flattening that the solver needs.
    """
    comp = (getattr(net, "composites", None) or {}).get(path)
    frag = getattr(comp, "schematic", None) if comp is not None else None
    if frag is None:
        return None
    return tuple(frag() if callable(frag) else frag)


def lower(net, *, title: str = "", budget=None) -> Schematic:
    """`Network` → :class:`Schematic`.

    Walks source → antenna to find the spine, groups consecutive spine
    branches by the composite instance they came from (so a box draws as a
    box), hangs everything else beneath the node it attaches to, and lets an
    author-supplied fragment replace the default symbols for its box.

    ``budget`` (the reducer's ``(label, watts)`` list) annotates each block
    with what it burns — which is what puts the power budget *in* the topology
    instead of beside it.
    """
    sch = Schematic(source=net.sources[0].port if net.sources else "", title=title)
    if not net.sources:
        sch.notes.append("no source: nothing to draw a chain from")
        return sch
    if len(net.sources) > 1:
        sch.notes.append(
            f"{len(net.sources)} driven ports — a multi-feed antenna rather "
            "than a chain, so there is no single line to draw"
        )
        return sch

    real = _real_ports(net)
    branches = list(net.branches)
    paths = list(net.branch_paths or [""] * len(branches))

    adj: dict[str, list] = {}
    for idx, br in enumerate(branches):
        ts = terminals_of(br)
        if len(ts) >= 2:
            adj.setdefault(ts[0], []).append((ts[-1], idx))
            adj.setdefault(ts[-1], []).append((ts[0], idx))

    from collections import deque

    prev, q, target = {sch.source: None}, deque([sch.source]), None
    while q:
        node = q.popleft()
        if node in real:
            target = node
            break
        for nxt, idx in adj.get(node, []):
            if nxt not in prev:
                prev[nxt] = (node, idx)
                q.append(nxt)

    spine = []  # [(branch_index, from_node, to_node)]
    if target is None:
        sch.ends_in_antenna = False
        sch.notes.append("no path from the source to an antenna port")
    else:
        cur = target
        while prev.get(cur):
            node, idx = prev[cur]
            spine.append((idx, node, cur))
            cur = node
        spine.reverse()
    on_spine = {idx for idx, _a, _b in spine}

    # Ribs: every non-spine branch, filed under the spine node it touches.
    ribs: dict[str, list[int]] = {}
    for idx, br in enumerate(branches):
        if idx in on_spine:
            continue
        for t in terminals_of(br):
            ribs.setdefault(t, []).append(idx)
            break

    watts = dict(budget or [])

    def burned(path):
        """Watts this block burns, children included.

        Budget labels are "<path>: <branch>" with the trailing dot stripped
        ("match: TL rig→feed"), and a nested box appears as "match.stub: ...",
        so a block owns both its own rows and its descendants'.
        """
        if not path:
            return None
        base = path[:-1]
        total = sum(
            w
            for k, w in watts.items()
            if k.startswith(f"{base}: ") or k.startswith(f"{base}.")
        )
        return total or None

    def elements_for(idxs, path):
        frag = fragment_of(net, path) if path else None
        if frag is not None:
            return frag
        out = []
        for i in idxs:
            out.extend(default_elements(branches[i]))
        return tuple(out)

    # Group consecutive spine branches sharing an instance path.
    i = 0
    while i < len(spine):
        idx, a_node, b_node = spine[i]
        path = paths[idx]
        group, nodes = [idx], {a_node, b_node}
        while i + 1 < len(spine) and path and paths[spine[i + 1][0]] == path:
            i += 1
            group.append(spine[i][0])
            nodes |= {spine[i][1], spine[i][2]}
        els = list(elements_for(group, path))
        if fragment_of(net, path) is None:
            # Ribs are already inside an author's fragment; only the default
            # rendering needs them appended.
            for node in nodes:
                for rib in ribs.get(node, []):
                    # A rib belongs to this block if it came from the same
                    # instance or from one nested inside it — a stub tuner's
                    # stub sits at "match.stub." under the section's "match.".
                    if not path or paths[rib].startswith(path):
                        # A rib hangs off the spine whatever the branch's own
                        # default orientation says: a stub is a length of line
                        # (drawn in series on its own) used as a shunt here.
                        els.extend(
                            replace(e, orient="shunt")
                            for e in default_elements(branches[rib])
                        )
        sch.blocks.append(
            Block(
                label=path[:-1] if path else type(branches[idx]).__name__,
                elements=tuple(els),
                path=path,
                watts=burned(path),
            )
        )
        i += 1

    if not spine:
        for idx, br in enumerate(branches):
            sch.blocks.append(
                Block(
                    label=paths[idx][:-1] or type(br).__name__,
                    elements=default_elements(br),
                    path=paths[idx],
                    watts=burned(paths[idx]),
                )
            )
    return sch


# --- rendering -------------------------------------------------------------
# schemdraw supplies the symbols and the SVG; the layout above is ours,
# because schemdraw's API is a cursor, not a layout engine. Kept in one place
# so the renderer stays swappable — nothing above this line imports it.
_SCHEMDRAW_SYMBOLS = {
    "inductor": "Inductor2",
    "capacitor": "Capacitor",
    "resistor": "Resistor",
    "coax": "Coax",
    "line": "Coax",
    "transformer": "Transformer",
    "balun": "Transformer",
    "short": "Line",
    "open": "Gap",
    "box": "RBox",
}

DX, DY = 3.2, 2.2  # spine step and rib drop, in schemdraw units
FONTSIZE = 8  # one size for every label — element, block, note and terminal
SUBFONT = 7  # the second line under an element (a line's length, a stub's end)
LEADIN = 1.4  # source → first block (widened below when a shunt lands on the
# first spine node, so its left-hand label clears the source circle).
LEADOUT = 0.9  # last block → antenna
GAP = 0.9  # between two blocks, so their enclosures never touch
TERM = 0.5  # shunt symbol → its termination glyph
SRC_R = 0.5  # radius of the source circle, for label clearance


def _text_width(s: str, fontsize: float = FONTSIZE) -> float:
    """Rough width of a label, in drawing units.

    schemdraw's SVG canvas is 36 pt per unit and its default font averages
    about half the point size per character. Only ever used to *reserve*
    space, so an approximation that errs wide is the safe kind.
    """
    return 0.55 * fontsize * len(s) / 36.0


def _label_room(el) -> float:
    """Width to reserve for a drop's left-hand labels."""
    return max(
        _text_width(el.label),
        _text_width(el.sublabel, SUBFONT),
    )


def _exit_x(e, fallback: float) -> float:
    """Where the spine leaves a drawn element.

    Two-terminal symbols expose ``end``; a Transformer exposes its secondary
    (``s1``) instead. Anything else falls back to a plain step.
    """
    for anchor in ("end", "s1"):
        if anchor in e.absanchors:
            return float(e.absanchors[anchor][0])
    return fallback


def _exit_y(e, fallback: float) -> float:
    """Where a drop really ends — see `_exit_x`, one axis over."""
    if "end" in e.absanchors:
        return float(e.absanchors["end"][1])
    return fallback


def render_svg(sch: Schematic, path=None) -> str:
    """Draw a :class:`Schematic` and return SVG (also written to ``path``).

    Needs the optional extra: ``pip install 'antennaknobs[schematic]'``.
    """
    try:
        import schemdraw
        import schemdraw.elements as elm
    except ImportError as e:  # pragma: no cover — depends on the install
        raise ImportError(
            "drawing a schematic needs schemdraw: pip install 'antennaknobs[schematic]'"
        ) from e

    schemdraw.use("svg")
    d = schemdraw.Drawing(show=False)
    d.config(unit=DX, fontsize=FONTSIZE)

    def symbol(kind):
        return getattr(elm, _SCHEMDRAW_SYMBOLS.get(kind, "RBox"))

    x, y = 0.0, 0.0
    # `.to()` rather than `.up()`: an element's default length is one unit
    # (DX), so `.up()` from the datum overshoots the spine and leaves a bare
    # wire sticking out of the top of the source.
    d += elm.SourceSin().at((x, y - DY)).to((x, y))
    d += (
        elm.Label()
        .at((x - SRC_R - 0.15, y - DY / 2.0))
        .label(sch.source or "source", halign="right")
    )
    d += elm.Ground().at((x, y - DY))

    # A shunt on the first spine node labels itself leftward, into the source.
    # Reserve the room here rather than nudging the label, so the drop stays
    # on the node it is electrically attached to.
    leadin = LEADIN
    first = sch.blocks[0].elements[0] if sch.blocks and sch.blocks[0].elements else None
    if first is not None and first.orient == "shunt":
        leadin = max(leadin, SRC_R + 0.3 + _label_room(first) + 0.5)
    d += elm.Line().at((x, y)).to((x + leadin, y))
    x += leadin

    for n, block in enumerate(sch.blocks):
        if n:
            d += elm.Line().at((x, y)).to((x + GAP, y))
            x += GAP
        x0 = x
        drawn = []  # what the block's enclosure has to contain
        tall = False  # the last symbol drawn reaches below the spine
        for el in block.elements:
            if el.orient == "shunt":
                if tall and (el.label or el.sublabel):
                    # Same reservation as LEADIN: a drop labels itself
                    # leftward, and a transformer fills the whole band below
                    # the spine, so step clear before dropping.
                    pad = _label_room(el) + 0.4
                    lead = elm.Line().at((x, y)).to((x + pad, y))
                    d += lead
                    drawn.append(lead)
                    x += pad
                tall = False
                # Drawn to an explicit endpoint for the same reason as the
                # source, and so the termination lands *on* the end rather
                # than part-way up a symbol that is longer than DY.
                e = symbol(el.kind)().at((x, y)).to((x, y - DY))
                d += e
                drawn.append(e)
                # Placed absolutely and right-aligned rather than as labels
                # on the element: schemdraw's label locations are in the
                # element's own rotated frame, which puts "left" of a drop
                # straight through the symbol body. Stacked so a drop reads
                # like a series element turned on its side — value, then the
                # second line under it.
                # Where the drop really ends: a Coax ignores both `.to()` and
                # `.length()` and keeps its own 3.0-unit body, so terminating
                # at the requested DY draws the glyph over the symbol's own
                # trailing lead.
                bot = _exit_y(e, y - DY)
                mid = (y + bot) / 2.0
                for text, dy, size in (
                    (el.label, 0.2, FONTSIZE),
                    (el.sublabel, -0.25, SUBFONT),
                ):
                    if not text:
                        continue
                    lab = (
                        elm.Label()
                        .at((x - 0.5, mid + dy))
                        .label(text, halign="right", fontsize=size)
                    )
                    d += lab
                    drawn.append(lab)
                ey = bot - TERM
                d += elm.Line().at((x, bot)).to((x, ey))
                # A stub's far end is the whole point of it: shorted and open
                # are different matches, and they used to draw identically.
                # The word comes from the data, so every stub says it the
                # same way instead of each fragment spelling its own.
                if el.term:
                    # A shorted stub is a bar across the far end of the cable,
                    # not a connection to earth: a ground symbol there claims
                    # a bond the hardware does not have. The word carries it.
                    end_mark = (
                        elm.Dot(open=True).at((x, ey))
                        if el.term == "open"
                        else elm.Line().at((x - 0.25, ey)).to((x + 0.25, ey))
                    )
                    d += end_mark
                    drawn.append(end_mark)
                    sub = (
                        elm.Label()
                        .at((x + 0.4, ey))
                        .label(
                            "open" if el.term == "open" else "shorted",
                            halign="left",
                            fontsize=SUBFONT,
                        )
                    )
                    d += sub
                    drawn.append(sub)
                else:
                    d += elm.Ground().at((x, ey))
            else:
                wound = el.kind in ("transformer", "balun")
                e = symbol(el.kind)().at((x, y)).right().label(el.label, loc="top")
                if wound:
                    # Not a two-terminal symbol: schemdraw's Transformer is a
                    # winding pair anchored at its primary, so it has no
                    # start/end and is 1.0 units wide, not DX. Enter on the
                    # primary top and leave from the secondary top, or the
                    # spine steps DX and leaves a gap where the coupling is.
                    e.anchor("p1")
                if el.sublabel:
                    # Clear of the symbol body: a Coax is ~0.3 units tall, so
                    # the default label offset lands the text inside it.
                    e.label(el.sublabel, loc="bottom", ofst=0.5, fontsize=SUBFONT)
                d += e
                drawn.append(e)
                if wound:
                    # The winding bottoms are terminals, not loose ends. A
                    # `Transformer` spans BOTH windings node-to-datum, so both
                    # return legs ground; a `FloatingBalun`'s secondary is
                    # deliberately unbonded, and grounding it would draw the
                    # one connection the element exists to avoid.
                    returns = ["p2"] if el.kind == "balun" else ["p2", "s2"]
                    for anchor in returns:
                        if anchor not in e.absanchors:  # pragma: no cover
                            continue
                        px, py = e.absanchors[anchor]
                        lead = elm.Line().at((px, py)).to((px, py - TERM))
                        d += lead
                        drawn.append(lead)
                        g = elm.Ground().at((px, py - TERM))
                        d += g
                        drawn.append(g)
                x = _exit_x(e, x + DX)
                tall = wound
        if x == x0:  # a block of pure shunts still needs a step
            e = elm.Line().at((x, y)).to((x + DX, y))
            d += e
            drawn.append(e)
            x += DX
        # An enclosure means "this is a box you named". A block with no path
        # is a bare branch the flattening never grouped — drawing a dashed
        # box round a lone TL and captioning it with its class name is noise,
        # and two such boxes in a row visibly collide.
        if block.path:
            note = block.label
            if block.watts:
                note = f"{note}  ({block.watts * 1e3:.2f} mW)"
            # A dashed enclosure, not a floating caption: the label names a
            # box in the design, so the drawing shows where that box stops.
            box = (
                elm.EncircleBox(drawn, padx=0.35, pady=0.35)
                .linestyle("--")
                .color("gray")
            )
            if note:
                box.label(note, loc="top", color="black")
            d += box

    if sch.ends_in_antenna:
        d += elm.Line().at((x, y)).to((x + LEADOUT, y))
        # No `.up()`: Antenna pins its own theta=0 and already draws its mast
        # upward, so rotating it lays the whole symbol on its side.
        d += elm.Antenna().at((x + LEADOUT, y)).label("antenna", loc="right")
    for i, note in enumerate(sch.notes):
        d += elm.Label().at((0.0, y - DY - 1.6 - i * 0.9)).label(note)

    d.draw()
    svg = d.get_imagedata("svg").decode("utf-8")
    if path is not None:
        with open(path, "w") as fh:
            fh.write(svg)
    return svg
