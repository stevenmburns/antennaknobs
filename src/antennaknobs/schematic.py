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
    "box",
    "short",
    "open",
    "antenna",
    "source",
)


@dataclass(frozen=True)
class Element:
    """One drawn symbol. ``orient`` is ``"series"`` (along the spine) or
    ``"shunt"`` (down to the datum)."""

    kind: str
    label: str = ""
    orient: str = "series"
    sublabel: str = ""


def series(kind: str, label: str = "", sublabel: str = "") -> Element:
    """A symbol in the signal path."""
    return Element(kind=kind, label=label, orient="series", sublabel=sublabel)


def shunt(kind: str, label: str = "", sublabel: str = "") -> Element:
    """A symbol from the spine down to the common datum."""
    return Element(kind=kind, label=label, orient="shunt", sublabel=sublabel)


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


def default_elements(branch) -> tuple[Element, ...]:
    """The fallback picture for a branch with no author-supplied fragment.

    Deliberately plain: enough to see that the element is there and what type
    it is. A box that wants to look like what it *is* supplies a fragment.
    """
    if isinstance(branch, TL):
        return (series("coax", f"{branch.z0:g} Ω", _fmt_len(branch.length)),)
    if isinstance(branch, BalancedLine):
        return (series("line", f"{branch.zdiff:g} Ω pair", _fmt_len(branch.length)),)
    if isinstance(branch, Transformer):
        return (series("transformer", f"1:{branch.n:g}"),)
    if isinstance(branch, Autotransformer):
        return (series("transformer", "autotransformer"),)
    if isinstance(branch, FloatingBalun):
        return (series("transformer", f"balun 1:{branch.n:g}"),)
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
        bits.append(f"{br.r:g} Ω")
    if getattr(br, "l", None):
        bits.append(f"{br.l * 1e6:g} µH")
    if getattr(br, "c", None):
        bits.append(f"{br.c * 1e12:g} pF")
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
    "short": "Line",
    "open": "Gap",
    "box": "RBox",
}

DX, DY = 3.2, 2.2  # spine step and rib drop, in schemdraw units


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
    d.config(unit=DX, fontsize=10)

    def symbol(kind):
        return getattr(elm, _SCHEMDRAW_SYMBOLS.get(kind, "RBox"))

    x, y = 0.0, 0.0
    d += elm.SourceSin().at((x, y - 2.0)).up().label(sch.source or "source", loc="left")
    d += elm.Ground().at((x, y - 2.0))
    d += elm.Line().at((x, y)).to((x + 0.7, y))
    x += 0.7

    for block in sch.blocks:
        x0 = x
        for el in block.elements:
            if el.orient == "shunt":
                d += (
                    symbol(el.kind)()
                    .at((x, y))
                    .down()
                    .label(el.label, loc="right", fontsize=8)
                )
                d += elm.Ground().at((x, y - DY))
            else:
                e = symbol(el.kind)().at((x, y)).right().label(el.label, fontsize=8)
                if el.sublabel:
                    e = e.label(el.sublabel, loc="bottom", fontsize=7)
                d += e
                x += DX
        if x == x0:  # a block of pure shunts still needs a step
            d += elm.Line().at((x, y)).to((x + DX, y))
            x += DX
        note = block.label
        if block.watts:
            note = f"{note}  ({block.watts * 1e3:.2f} mW)"
        if note:
            d += elm.Label().at(((x0 + x) / 2.0, y + 1.1)).label(note, fontsize=8)

    if sch.ends_in_antenna:
        d += elm.Line().at((x, y)).to((x + 0.7, y))
        d += elm.Antenna().at((x + 0.7, y)).up().label("antenna", loc="right")
    for i, note in enumerate(sch.notes):
        d += elm.Label().at((0.0, y - 4.0 - i * 0.9)).label(note, fontsize=8)

    d.draw()
    svg = d.get_imagedata("svg").decode("utf-8")
    if path is not None:
        with open(path, "w") as fh:
            fh.write(svg)
    return svg
