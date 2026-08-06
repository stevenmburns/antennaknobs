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

Fragments are written with :func:`series` / :func:`retn` / :func:`shunt` /
:func:`ground`, which produce plain data. Rendering happens later, through
schemdraw (an optional extra). That keeps `station.py` free of any drawing
library, keeps the renderer swappable, and means a fragment can be inspected
and tested without drawing anything.

    def l_network_schematic(l_uH, c_pF):
        return (
            series("inductor", f"{l_uH:g} µH"),
            shunt("capacitor", f"{c_pF:g} pF"),
        )

## Layout, and the return conductor

The chain runs left to right, source to antenna, with anything hanging off it
drawn where it attaches. What makes that more than a line of boxes is the
**return**: a single-ended branch returns through the common datum and can be
walked one node at a time, but a balanced pair returns through its partner
conductor and a `FloatingBalun` secondary has no datum at all. So the chain is
found by walking *pairs* of nodes — (signal, return) — and a balanced section
is drawn as two conductors, with the isolation barrier at the balun and no
ground symbol past it. Drawing an implied ground there would assert a bond the
hardware does not have, which is the one thing a schematic must not do.

Nothing forces a network to be a *single* chain either. A corporate feed
forks: the trunk carries one arm and every other arm is a `Branch` (issue
#685) — its own chain, forked at a junction dot on the drawing and ending at
its own named antenna. Ports a chain merely passes through (an LPDA's
phasing line touches every element) are marked and named on the wire.

Nothing forces a network to be a chain at all. A trap sits in a dipole leg and
a Sterba curtain's risers bridge points on the structure; those are
`Schematic.attachments`, drawn where they attach and named by the nodes they
bridge, because inventing a series chain for them produces a picture that
looks right and is false.
"""

from __future__ import annotations

import math
import re
from collections import namedtuple
from dataclasses import dataclass, field, replace

from .network import (
    TL,
    Admittance,
    Autotransformer,
    BalancedLine,
    FloatingBalun,
    Load,
    PortAtEnd,
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
    "Branch",
    "series",
    "retn",
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
    """One drawn symbol.

    Where a symbol sits takes two independent answers, so it has two fields.
    ``orient`` says which way it runs:

    ``series``  along a conductor;
    ``shunt``   across, out of that conductor;
    ``pair``    both conductors at once (a two-conductor line).

    ``leg`` says which conductor that is — ``signal`` or ``return``. A return
    leg only exists where the return is a wire on the page rather than the
    datum, which is what ``balanced`` records: the local reference is the
    datum when False and the partner conductor when True. :func:`lower` stamps
    both from the wiring; authors set ``leg`` (a coil in the cold leg is a
    fact about the box) and never ``balanced`` (whether the box floats is a
    fact about where it is wired).

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
    leg: str = "signal"
    balanced: bool = False


def series(kind: str, label: str = "", sublabel: str = "") -> Element:
    """A symbol in the signal conductor."""
    return Element(kind=kind, label=label, orient="series", sublabel=sublabel)


def retn(kind: str, label: str = "", sublabel: str = "") -> Element:
    """A symbol in the RETURN conductor — the second leg of a balanced section.

    Only meaningful where the return is drawn: between a `FloatingBalun`'s
    secondary and the antenna there is no datum, so the balanced tuner's
    roller inductance, split half into each leg, is one :func:`series` and one
    of these rather than a single symbol with an implied ground under it.
    """
    return Element(kind=kind, label=label, sublabel=sublabel, leg="return")


def shunt(
    kind: str,
    label: str = "",
    sublabel: str = "",
    term: str = "",
    leg: str = "signal",
) -> Element:
    """A symbol out of a conductor, across to the local reference.

    That reference is the datum in a single-ended section and the partner
    conductor in a balanced one, so the same fragment draws as a drop to
    ground on a coax-fed match and as a rung between the rails on a floating
    tuner — which is what the element physically is in each case.

    ``leg`` is which conductor it leaves from: a common-mode pin on each side
    of a balanced pair is two drops, one per leg, and drawing both from the
    signal side would put them on top of each other and misstate the
    symmetry that is the point of them.

    ``term`` names how the drop ends — ``"short"`` or ``"open"`` for a stub,
    whose two flavors are different matches and must not draw alike. Left
    empty (an R/L/C to common) the drop simply grounds.
    """
    return Element(
        kind=kind,
        label=label,
        orient="shunt",
        sublabel=sublabel,
        term=term,
        leg=leg,
    )


def ground(label: str = "") -> Element:
    """An explicit connection to the datum (a shorted stub's far end)."""
    return Element(kind="short", label=label, orient="shunt")


@dataclass
class Block:
    """One box on the chain: its label and the elements that draw it.

    ``nodes`` is set only on an attachment, where *where it is wired* is the
    whole content of the drawing — an attachment has no place on the chain to
    inherit that from.
    """

    label: str
    elements: tuple[Element, ...]
    path: str = ""
    watts: float | None = None
    nodes: tuple[str, ...] = ()


@dataclass
class Branch:
    """A feed branch (issue #685): a chain forked off another chain.

    A corporate feed splits at a junction; past the trunk each split is its
    own run of branches ending at its own antenna port. It is a *chain* —
    drawn with the same symbols, owning its own ribs — not an attachment: an
    attachment row says "wired into the antenna structure", which a feedline
    emphatically is not.

    ``parent`` is where it forks from: ``-1`` for the trunk, else an index
    into ``Schematic.branches``. ``at`` is the block boundary on that parent
    (0 = in front of its first block, ``len(blocks)`` = at its antenna end)
    and ``origin`` names the junction node there.
    """

    origin: str
    parent: int
    at: int
    blocks: list[Block] = field(default_factory=list)
    balanced_start: bool = False  # forks off a floating pair, not a node
    balanced_end: bool = False
    antenna_name: str = ""
    #: (block boundary, port name) — antenna ports this branch passes through.
    marks: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class FeedGroup:
    """Sources sharing one drive value, summarized as a row (issue #685).

    A 16-source array models no feed network at all — every element carries
    its own ideal generator. There is no chain to draw and inventing one (a
    single source fanned to 16 antennas) would fabricate a corporate feed
    the solve does not contain. What IS true is the grouping: N elements
    driven identically. One row per distinct drive says exactly that, and a
    phased multi-source design says it as one row per phase group.
    """

    count: int
    drive: str  # "1 V", "0.7 V ∠90°" — the group's shared source value
    ports: str  # "e0_0.feed … e15_0.feed" — first … last in natural order


@dataclass
class Schematic:
    """A whole drawing: the source, the chain, and what it ends in.

    ``branches`` are feed branches — the other arms of a corporate feed,
    forked off the trunk (or off another branch) at a named junction and
    ending at their own antenna ports.

    ``attachments`` are branches wired into the antenna structure rather than
    between the source and it — a trap in a dipole leg, a Sterba curtain's
    risers. They are not a feed chain and must not be drawn as one; the
    picture says where each one attaches instead.
    """

    source: str
    blocks: list[Block] = field(default_factory=list)
    # Input power for the same solve the block watts came from. Watts alone
    # are meaningless on the page — the canonical drive is 1 V, so a real
    # loss is fractions of a milliwatt — but watts/p_in is the same "12.3%"
    # the power-budget table shows, at the point in the chain where it burns.
    p_in: float | None = None
    ends_in_antenna: bool = True
    balanced_end: bool = False  # the chain reaches the antenna as a pair
    # The port the chain actually landed on, set only when the network has
    # more than one antenna port. A bowtie1x2_bl chain draws one of two
    # value-identical parallel lines; without naming its end, the chain and
    # the feed1 attachment read as the same components listed twice.
    antenna_name: str = ""
    # The picked measurement plane (issue #652 c), when it is NOT the natural
    # source. ``plane_cut`` is the block index the marker draws in front of
    # (len(blocks) = at the antenna); everything left of it is disconnected
    # for the solve being displayed and renders de-emphasised.
    plane: str = ""
    plane_cut: int | None = None
    title: str = ""
    notes: list[str] = field(default_factory=list)
    branches: list[Branch] = field(default_factory=list)
    #: (block boundary, port name) — antenna ports the trunk passes through.
    #: An LPDA's chain touches d8…d1 on the way to d0; without the marks they
    #: draw as anonymous wire (issue #685).
    marks: list[tuple[int, str]] = field(default_factory=list)
    #: Multi-source summary (issue #685): set INSTEAD of a chain when several
    #: sources drive the antenna directly — there is no feed network to walk.
    feed_groups: list[FeedGroup] = field(default_factory=list)
    attachments: list[Block] = field(default_factory=list)


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


def _natkey(s: str):
    """Natural sort key, so a feed-group range reads e0_0 … e15_0 rather than
    lexicographic order putting e15 before e2."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def _drive_text(v: complex) -> str:
    """A source value as it reads on the page: magnitude, phase if any."""
    mag = abs(v)
    ph = math.degrees(math.atan2(v.imag, v.real))
    return f"{mag:g} V ∠{ph:g}°" if abs(ph) > 1e-9 else f"{mag:g} V"


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


def _ohms(v):
    """A resistance with an SI prefix.

    Common-mode pins are megohms — the value is deliberately huge, being the
    drawn form of SPICE's `rshunt` — and "100000000 Ω" is a number nobody can
    read at a glance, which made a piece of pure modelling scaffolding look
    like a real 100 megohm resistor someone had chosen.
    """
    for scale, unit in ((1e9, "GΩ"), (1e6, "MΩ"), (1e3, "kΩ")):
        if abs(v) >= scale:
            return f"{_val(v / scale)} {unit}"
    return f"{_val(v)} Ω"


def _rlc_label(br):
    bits = []
    if getattr(br, "r", None):
        bits.append(_ohms(br.r))
    if getattr(br, "l", None):
        bits.append(f"{_val(br.l * 1e6)} µH")
    if getattr(br, "c", None):
        bits.append(f"{_val(br.c * 1e12)} pF")
    return " ".join(bits) if bits else "short"


# --- the graph the drawing is of -------------------------------------------
# A schematic connects by NODE IDENTITY, the way a netlist does; the wires on
# the page are a rendering of that graph, not the source of it. The part that
# needs care is the RETURN. A single-ended branch returns through the common
# datum, so a run of them can be walked one node at a time — but a balanced
# pair returns through its partner conductor, and a `FloatingBalun` secondary
# has no datum at all. Walking single nodes cannot see those: it read a
# `BalancedLine(a1, a2, b1, b2)` as the a1↔b2 diagonal, which is not a
# conductor, and a `FloatingBalun(primary, a, b)` as primary↔b, which drops a
# leg. Both designs that use them reported no path to the antenna.
#
# So the walk carries a PAIR — (signal, return) — and a branch advances the
# pair. Which conductor a branch advances is the whole difference between a
# coil in one leg of a balanced tuner and a coil in both.
#
# The datum's own status is a netlist question too, and the answer is SPICE's:
# every node needs a path to it. `Network.__post_init__` already enforces that
# (a common-mode-open node makes the MNA singular), and designs pin it exactly
# the way SPICE users do — `bowtie1x2_bl` writes `Shunt(port=…, r=1e8)`, the
# rshunt idiom. Here we only have to draw the result.

#: The common return. Not a node any design names — it is what a `Shunt`
#: shunts *to*, and the one net that may be drawn as a ground symbol.
DATUM = "#datum"


def _datum_nodes(net):
    """Every node that IS the datum: the datum plus whatever is bonded to it.

    A `Shunt` carrying no value is a bond rather than a component —
    `bowtie1x2_bl` writes the coax shield as ``Shunt(port="JC2", l=0.0)``.
    Merging it is the node collapse a simulator does for a 0 Ω element, and
    without it the balanced line hanging off that shield has a return the walk
    cannot recognise.
    """
    out = {DATUM}
    for br in net.branches:
        if isinstance(br, (Shunt, Load)) and not (br.r or br.l or br.c):
            out.add(br.port)
    return out


def _antenna_nodes(net):
    """Node name → port name, for every port that is a piece of antenna.

    Not simply the port names: a `PortOnWireFloating("feed")` is wired as
    ``feed.p`` / ``feed.n`` and the bare name is not a node at all, so a walk
    looking for ``"feed"`` never arrives. `PortAtEnd` was missing outright.
    """
    out = {}
    for name, p in net.ports.items():
        if isinstance(p, PortOnWireFloating):
            out[f"{name}.p"] = name
            out[f"{name}.n"] = name
        elif isinstance(p, (PortOnWire, PortAtEnd)):
            out[name] = name
    return out


#: One drawn step of the chain: which branch, how it is drawn, which conductor
#: it advanced, whether the return is a wire from here on, and the node pairs
#: either side of it.
Step = namedtuple("Step", "idx orient leg balanced pair_in pair_out")


def _moves(br, hot, cold, canon):
    """Ways ``br`` can carry the pair ``(hot, cold)`` one step onward.

    Yields ``(new_hot, new_cold, orient, leg, balanced)`` — the terminals the
    pair lands on, how the symbol runs, which conductor moved, and whether the
    return is a wire from here on. ``canon`` collapses datum-bonded nodes, so
    a branch wired to a grounded shield is seen to be wired to the datum,
    which is what it is.
    """
    single = cold == DATUM
    if isinstance(br, FloatingBalun):
        # The one element that changes what "return" MEANS: single-ended
        # primary in, floating pair out. Both directions, so a chain drawn
        # from either end finds it.
        a, b = canon(br.a), canon(br.b)
        if single and hot == canon(br.primary):
            yield br.a, br.b, "series", "signal", True
        if (hot, cold) in ((a, b), (b, a)):
            yield br.primary, DATUM, "series", "signal", False
        return
    if isinstance(br, BalancedLine):
        # Four terminals in two pairs. The pair enters on one end and leaves
        # on the other; a crossover is just the terminals wired the other way
        # round, which the second case picks up.
        for (a1, a2), (b1, b2) in (
            ((br.a1, br.a2), (br.b1, br.b2)),
            ((br.b1, br.b2), (br.a1, br.a2)),
        ):
            if (hot, cold) == (canon(a1), canon(a2)):
                yield b1, b2, "pair", "signal", True
            elif (hot, cold) == (canon(a2), canon(a1)):
                yield b2, b1, "pair", "signal", True
        return
    ts = terminals_of(br)
    if len(ts) != 2:
        return  # a one-terminal load never advances anything
    a, b = canon(ts[0]), canon(ts[1])
    if isinstance(br, (TL, Transformer, Autotransformer)):
        # Single-ended by construction — a coax returns through its shield and
        # a `Transformer` spans both windings node-to-datum — so these cannot
        # carry a floating pair onward. Refusing the move is what makes the
        # walk report a gap instead of quietly bonding a floating section to
        # ground to get past it.
        if single:
            if hot == a:
                yield b, DATUM, "series", "signal", False
            if hot == b:
                yield a, DATUM, "series", "signal", False
        return
    # A lumped bridge (`TwoPort`, a measured 2-port): it advances whichever
    # conductor it is wired into. That is how a roller inductance split half
    # into each leg draws as two symbols facing each other rather than one
    # symbol with an imaginary ground beneath it.
    if hot == a:
        yield b, cold, "series", "signal", not single
    if hot == b:
        yield a, cold, "series", "signal", not single
    if not single:
        if cold == a:
            yield hot, b, "series", "return", True
        if cold == b:
            yield hot, a, "series", "return", True


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


#: Ceiling on chain search — see :func:`_walk`. Every catalog network is
#: nowhere near it; it exists so a pathological one degrades to a shorter
#: drawing instead of hanging.
_WALK_BUDGET = 20000


def _walk(branches, start, targets, is_datum, used=frozenset()):
    """The longest run of branches carrying the source's pair to an antenna.

    Depth-first over ``(signal, return)`` states, no branch used twice.
    Returns a list of :data:`Step`, empty if nothing reaches an antenna node.

    *Longest*, not shortest, because the chain should show as much of the feed
    path as it can. A log-periodic's phasing line is nine sections strung
    between ten driven elements: the first hop already lands on an antenna
    port, so a shortest-path walk would draw one section and stop, and the
    other eight would vanish. Walking to the end of the line is also what a
    person drawing it does.

    ``start`` is a node name (paired with the datum) or a ``(hot, cold)``
    pair-state — the latter is how a branch chain is walked from the junction
    it forks at (issue #685). ``used`` masks branches other chains already
    claimed, so two chains never draw the same branch.
    """
    best = []
    budget = [_WALK_BUDGET]

    def canon(n):
        return DATUM if n in is_datum else n

    def dfs(state, taken, chain):
        nonlocal best
        if budget[0] <= 0:
            return
        budget[0] -= 1
        if chain and state[0] in targets and len(chain) > len(best):
            best = list(chain)
        hot, cold = state
        for idx, br in enumerate(branches):
            if idx in taken:
                continue
            for nhot, ncold, orient, leg, bal in _moves(br, hot, cold, canon):
                nhot, ncold = canon(nhot), canon(ncold)
                if nhot == ncold or nhot == DATUM:
                    continue  # a step onto its own return is not a step
                nxt = (nhot, ncold)
                chain.append(Step(idx, orient, leg, bal, state, nxt))
                dfs(nxt, taken | {idx}, chain)
                chain.pop()

    hot, cold = start if isinstance(start, tuple) else (start, DATUM)
    dfs((canon(hot), canon(cold)), frozenset(used), [])
    return best


def lower(net, *, title: str = "", budget=None, p_in=None, plane=None) -> Schematic:
    """`Network` → :class:`Schematic`.

    Walks source → antenna to find the chain, groups consecutive chain
    branches by the composite instance they came from (so a box draws as a
    box), hangs everything else at the node it attaches to, and lets an
    author-supplied fragment replace the default symbols for its box.

    ``budget`` (the reducer's ``(label, watts)`` list) annotates each block
    with what it burns — which is what puts the power budget *in* the topology
    instead of beside it. ``p_in`` is the same solve's input power; with it
    the annotation renders as the fraction the budget table already shows.

    ``plane`` marks a picked measurement plane (issue #652 c): the FULL chain
    still draws — the picker needs the whole thing on screen to point at —
    with a marker at the cut and the disconnected upstream de-emphasised. A
    plane the chain does not visit is quietly ignored: the drawing must never
    crash, and the solve path (`plane.driven_at`) is the validating gate.
    """
    sch = Schematic(
        source=net.sources[0].port if net.sources else "",
        title=title,
        p_in=p_in,
    )
    if not net.sources:
        sch.notes.append("no source: nothing to draw a chain from")
        return sch
    if len(net.sources) > 1:
        # A multi-feed antenna: there is no chain, and no feed network is
        # modelled between the sources. What there IS to draw is the
        # grouping — N elements driven identically — one summary row per
        # distinct drive value (issue #685). Keyed by the complex voltage,
        # so a phased design falls into one group per phase.
        by_drive: dict[complex, list[str]] = {}
        for src in net.sources:
            v = complex(getattr(src, "voltage", None) or 1.0)
            by_drive.setdefault(v, []).append(src.port)
        for v, ports in by_drive.items():
            names = sorted(ports, key=_natkey)
            sch.feed_groups.append(
                FeedGroup(
                    count=len(names),
                    drive=_drive_text(v),
                    ports=(
                        ", ".join(names)
                        if len(names) <= 3
                        else f"{names[0]} … {names[-1]}"
                    ),
                )
            )
        sch.notes.append(
            f"{len(net.sources)} driven ports — every element carries its own "
            "source; no feed network between them is modelled"
        )
        return sch

    branches = list(net.branches)
    paths = list(net.branch_paths or [""] * len(branches))
    is_datum = _datum_nodes(net)
    targets = _antenna_nodes(net)

    # Accumulated, not dict(budget): two probes can share one label (a
    # parallel Shunt stamps group-1 and a series one group-2 under the same
    # "Shunt <port>"), and a plain dict would keep only the last row's watts.
    watts: dict[str, float] = {}
    for k, w in budget or []:
        watts[k] = watts.get(k, 0.0) + w

    def burned(path):
        """Watts this block burns, children included.

        Budget labels are "<path>: <branch>" with the trailing dot stripped
        ("match: TL rig→feed", "match.stub: ..."), so a block owns both its
        own rows and its descendants'.
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

    #: Qualifiers the reducer appends to a branch's label for its sub-rows —
    #: "Transformer a→b (mag)", "Autotransformer a→b (lower)"/"(upper)".
    _QUALS = {"mag", "lower", "upper"}

    def burned_bare(idx):
        """Watts for a PATHLESS branch, matched by its own budget label.

        A bare branch has no "<path>: " prefix to own rows by; its rows are
        labelled "<Type> <terminals>" ("TL rig→feed", "Load trap_l").
        Reconstructing each exact format here would duplicate
        network_reduce's strings and drift, so the match is on what
        identifies the branch — the type-name prefix and the set of node
        names — letting the punctuation and any "(mag)" qualifier fall away.
        `invvee_coax_station`, the design the issue opens with, is one bare
        TL; without this its 30 m of coax showed no loss at all. Two bare
        same-type branches on identical nodes would each claim both rows,
        the same ambiguity the label scheme itself has.
        """
        br = branches[idx]
        prefix = f"{type(br).__name__} "
        want = set(terminals_of(br))
        if not want:
            return None
        total = 0.0
        for k, w in watts.items():
            if not k.startswith(prefix):
                continue
            rest = k[len(prefix) :]
            for sep in ("→", "(", ")", ","):
                rest = rest.replace(sep, " ")
            tokens = set(rest.split())
            if want <= tokens and tokens - want <= _QUALS:
                total += w
        return total or None

    chain = _walk(branches, sch.source, targets, is_datum)
    used = {st.idx for st in chain}
    sch.balanced_end = bool(chain) and chain[-1].balanced
    if chain and len(set(targets.values())) > 1:
        # Several antenna ports: say which one this chain reached, so it can
        # be told apart from a parallel feed drawn beside it.
        end_names = {targets[t] for t in chain[-1].pair_out if t in targets}
        sch.antenna_name = ", ".join(sorted(end_names))

    # Branch chains (issue #685). A corporate feed forks: for every antenna
    # port the trunk did not reach, walk again from each state the drawing
    # already holds, over the branches no chain has claimed. Each hit is a
    # feed branch — the other arm of the fan-out — recorded with the state it
    # forked from so the junction can be marked. Walks aim only at antenna
    # ports still unfed: a second path onto an antenna already drawn is not a
    # feed structure, and hijacking ribs to draw one would fabricate a loop.
    # New chains join the scan, so a depth-2 corporate tree forks off a fork.
    def _ports_on(ch):
        return {
            targets[t]
            for st in ch
            for s in (st.pair_in, st.pair_out)
            for t in s
            if t in targets
        }

    chains = [chain]
    forks: list[tuple[int, int, str] | None] = [None]  # (parent, state, node)
    fed = _ports_on(chain)
    grew = bool(chain)
    while grew:
        grew = False
        for ci in range(len(chains)):
            states_of = [chains[ci][0].pair_in]
            states_of += [st.pair_out for st in chains[ci]]
            for si, state in enumerate(states_of):
                unfed = {n: p for n, p in targets.items() if p not in fed}
                if not unfed:
                    break
                sub = _walk(branches, state, unfed, is_datum, used)
                if not sub:
                    continue
                used |= {st.idx for st in sub}
                chains.append(sub)
                forks.append((ci, si, state[0]))
                fed |= _ports_on(sub)
                grew = True

    # Nodes the drawing reaches — what an off-chain branch can attach TO.
    reached = {sch.source}
    for ch in chains:
        for st in ch:
            reached |= set(st.pair_in) | set(st.pair_out)
    reached.discard(DATUM)

    # Everything not on a chain is either a rib (it hangs at a node a chain
    # passes through) or an attachment (it is wired into the antenna
    # structure, not into the feed path). The distinction is the difference
    # between a matching stub and a Sterba curtain's riser, and collapsing it
    # is what let four disjoint risers draw as a plausible series chain.
    # Pairs the chains occupy, so a rib can be asked whether it bridges the
    # two conductors or goes to the datum — see `rungs` below.
    states = {
        frozenset(s) for ch in chains for st in ch for s in (st.pair_in, st.pair_out)
    }
    # Nodes that are the RETURN conductor, so a rib hanging off one is drawn
    # leaving that conductor rather than the signal one.
    cold = {s[1] for ch in chains for st in ch for s in (st.pair_in, st.pair_out)} - {
        DATUM
    }

    ribs: dict[str, list[int]] = {}
    rungs: set[int] = set()
    rib_leg: dict[int, str] = {}
    parallel: set[str] = set()
    for idx, br in enumerate(branches):
        if idx in used:
            continue
        ts = [t for t in terminals_of(br) if t not in is_datum]
        if not ts:
            continue  # a bond to the datum; the ground symbol already says it
        here = [t for t in ts if t in reached]
        # A branch reaching an antenna the chain never got to is a second feed,
        # not something hanging off this one. Drawing it in line would say the
        # two antennas are in series, which is the opposite of what it is.
        parallel_feed = any(t in targets and t not in reached for t in ts)
        if here and not parallel_feed:
            if len(ts) == 2 and frozenset(ts) in states:
                rungs.add(idx)
            elif here[0] in cold:
                rib_leg[idx] = "return"
            ribs.setdefault(here[0], []).append(idx)
        else:
            sch.attachments.append(
                Block(
                    label=paths[idx][:-1] or type(br).__name__,
                    elements=default_elements(br),
                    path=paths[idx],
                    watts=burned(paths[idx]) if paths[idx] else burned_bare(idx),
                    nodes=tuple(ts),
                )
            )
            if parallel_feed:
                parallel.update(
                    targets[t] for t in ts if t in targets and t not in reached
                )

    if chain and parallel:
        # Only worth saying where there IS a chain: it is the one case where a
        # reader could otherwise take the drawing for the whole feed.
        names = ", ".join(sorted(parallel))
        sch.notes.append(
            f"{names} fed in parallel from the same point, not through this chain"
        )
    if not chain:
        # Without a chain the drawing ends in an antenna only if the source is
        # sitting ON one — a driven wire port with the rest of the network
        # wired into the structure around it.
        sch.ends_in_antenna = sch.source in targets
        if not targets:
            sch.notes.append("no antenna port for a chain to end at")
        elif not sch.ends_in_antenna:
            sch.notes.append(
                f"no run of branches carries {sch.source} to an antenna port"
            )
        elif sch.attachments or ribs:
            sch.notes.append(
                "the source drives the antenna directly; the branches below "
                "are wired into the structure, not into the feed"
            )
        else:
            sch.notes.append("no run of branches carries the source to an antenna")

    def stamped(frag, balanced_in):
        """An author's fragment, with the local reference stamped onto it.

        A fragment says what the box contains; only the wiring says whether
        the box floats. The reference flips at a balun and nowhere else —
        that element *is* the isolation barrier, the same place a schematic
        capture tool draws its dashed line.
        """
        out, bal = [], balanced_in
        for e in frag:
            if e.kind == "balun":
                bal = True
            out.append(replace(e, balanced=bal))
        return tuple(out)

    def chain_elements(steps, path, balanced_in):
        """The symbols for one block's worth of chain steps."""
        frag = fragment_of(net, path) if path else None
        if frag is not None:
            return list(stamped(frag, balanced_in))
        out = []
        for st in steps:
            for e in default_elements(branches[st.idx]):
                # The branch's own default orientation says what the element
                # is on its own; the walk says which conductor it landed in.
                out.append(
                    replace(e, orient=st.orient, leg=st.leg, balanced=st.balanced)
                )
        return out

    # Group consecutive chain steps sharing an instance path.
    def group_steps(ch):
        groups = []  # [(steps, path, nodes)]
        starts = []  # each group's first chain-step index, for the plane cut
        i = 0
        while i < len(ch):
            starts.append(i)
            path = paths[ch[i].idx]
            group, nodes = [ch[i]], set(ch[i].pair_in)
            while i + 1 < len(ch) and path and paths[ch[i + 1].idx] == path:
                i += 1
                group.append(ch[i])
                nodes |= set(ch[i].pair_in)
            nodes |= set(group[-1].pair_out)
            nodes.discard(DATUM)
            groups.append((group, path, nodes))
            i += 1
        return groups, starts

    grouped = [group_steps(ch) for ch in chains]
    groups, starts = grouped[0]

    if plane and plane != sch.source and chain:
        # Where the picked plane sits: in front of the first step whose
        # entry pair carries it, or at the chain's end. Blocks wholly before
        # that step are the upstream the solve disconnected.
        cut = next(
            (k for k, st in enumerate(chain) if plane in st.pair_in),
            len(chain) if plane in chain[-1].pair_out else None,
        )
        if cut is not None:
            sch.plane = plane
            sch.plane_cut = sum(1 for s in starts if s < cut)

    # Assign each rib to EXACTLY ONE block, across every chain. A node a
    # chain passes through can belong to two consecutive blocks, so keying a
    # rib by node alone drew a balanced tuner's differential capacitor in
    # both boxes at once, and put an unun's magnetising shunt in the feedline
    # box as well as the unun. The block that owns it is the most specific
    # one whose instance path the rib's own path lies under — a stub tuner's
    # stub sits at "match.stub." under the section's "match.".
    owner: dict[tuple[int, int], list[int]] = {}
    for node, idxs in ribs.items():
        for ridx in idxs:
            cands = [
                (ci, gi)
                for ci, (gs, _starts) in enumerate(grouped)
                for gi, (_s, _p, nodes) in enumerate(gs)
                if node in nodes
            ]
            if not cands:
                continue

            def _rank(cg):
                path = grouped[cg[0]][0][cg[1]][1]
                depth = len(path) if paths[ridx].startswith(path) else -1
                return (depth, -cg[0], -cg[1])

            owner.setdefault(max(cands, key=_rank), []).append(ridx)

    def build_blocks(ci, balanced0):
        """One chain's steps → its blocks, ribs appended where they hang."""
        out = []
        balanced = balanced0
        for gi, (group, path, _nodes) in enumerate(grouped[ci][0]):
            els = chain_elements(group, path, balanced)
            balanced = group[-1].balanced
            if fragment_of(net, path) is None:
                # Ribs are already inside an author's fragment; only the
                # default rendering needs them appended.
                for rib in sorted(owner.get((ci, gi), [])):
                    # A rib crosses to the local reference whatever the
                    # branch's own default orientation says: a stub is a
                    # length of line, drawn in series on its own, used as a
                    # shunt here.
                    #
                    # WHICH reference is the rib's own wiring, not the
                    # section's. A `Shunt` is by definition R/L/C to the
                    # common, so it keeps its ground even inside a floating
                    # section — that is exactly what a 100 MΩ common-mode pin
                    # is, and drawing the ground is what explains why the
                    # resistor is there at all. Only a branch wired across
                    # both conductors is a rung between them.
                    els.extend(
                        replace(
                            e,
                            orient="shunt",
                            leg=rib_leg.get(rib, "signal"),
                            balanced=rib in rungs,
                        )
                        for e in default_elements(branches[rib])
                    )
            out.append(
                Block(
                    label=path[:-1] if path else type(branches[group[0].idx]).__name__,
                    elements=tuple(els),
                    path=path,
                    watts=burned(path) if path else burned_bare(group[0].idx),
                )
            )
        return out

    def marks_of(ci):
        """Antenna ports chain ``ci`` passes through, at interior boundaries.

        The end is the antenna symbol's own label and the start is the
        source's (or the junction's), so only the boundaries between blocks
        need naming — an LPDA's chain touches d8…d1 as anonymous wire
        otherwise.
        """
        gs, sts = grouped[ci]
        ch = chains[ci]
        out = []
        for b in range(1, len(gs)):
            nodes = set(ch[sts[b]].pair_in) - {DATUM}
            names = sorted({targets[n] for n in nodes if n in targets})
            if names:
                out.append((b, ", ".join(names)))
        return out

    sch.blocks = build_blocks(0, False)
    sch.marks = marks_of(0)
    for ci in range(1, len(chains)):
        pci, si, node = forks[ci]
        parent_starts = grouped[pci][1]
        sub = chains[ci]
        sch.branches.append(
            Branch(
                origin=node,
                parent=pci - 1,
                at=sum(1 for s in parent_starts if s < si),
                blocks=build_blocks(ci, sub[0].pair_in[1] != DATUM),
                balanced_start=sub[0].pair_in[1] != DATUM,
                balanced_end=sub[-1].balanced,
                antenna_name=", ".join(
                    sorted({targets[t] for t in sub[-1].pair_out if t in targets})
                ),
                marks=marks_of(ci),
            )
        )

    # Ribs at the source itself, with no chain to hang them on.
    if not chain:
        for node in sorted(ribs):
            for idx in ribs[node]:
                sch.blocks.append(
                    Block(
                        label=paths[idx][:-1] or type(branches[idx]).__name__,
                        elements=default_elements(branches[idx]),
                        path=paths[idx],
                        watts=burned(paths[idx]) if paths[idx] else burned_bare(idx),
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
SHUNT_STEP = 0.9  # past a drop, so two in a row do not land on the same x
PAIR_LEN = 4.6  # a two-conductor line, long enough to read as a line
ATTACH_ROW = 1.9  # between attachment rows, which carry two lines of text each


def _burn_text(watts: float, p_in: float | None) -> str:
    """How a block's dissipation reads on the page.

    As the fraction of input power when the solve's ``p_in`` is known — the
    same number the power-budget table shows, placed where it burns — and as
    raw milliwatts otherwise: the canonical 1 V drive gives watts no
    meaningful absolute scale, but with no reference there is nothing truer
    to print.
    """
    if p_in:
        return f"{watts / p_in:.1%}"
    return f"{watts * 1e3:.2f} mW"


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


def render_svg(sch: Schematic, path=None, color: str | None = None) -> str:
    """Draw a :class:`Schematic` and return SVG (also written to ``path``).

    Needs the optional extra: ``pip install 'antennaknobs[schematic]'``.

    ``color`` sets the drawing's stroke/text colour. Schemdraw passes it
    through to the SVG verbatim, so CSS's ``"currentColor"`` works: the web
    panel inlines the SVG and the schematic follows the app theme with no
    re-render (the default black would vanish on the dark theme).
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
    base_color = color or "black"
    if color is not None:
        d.config(color=color)
    # De-emphasis for the section a picked measurement plane disconnects
    # (issue #652 c). The upstream still DRAWS — the picker needs the whole
    # chain on screen to point at — but it is not part of the solve being
    # displayed, and the page must not pretend it is.
    DIM = "gray"

    def symbol(kind):
        return getattr(elm, _SCHEMDRAW_SYMBOLS.get(kind, "RBox"))

    def plane_marker(px, top, bot):
        """The picked measurement plane: a dash-dot line crossing the chain.

        Inherits the drawing colour from the config state on purpose — both
        call sites have just restored the full colour, and an explicit
        ``.color()`` would trip schemdraw's name validation on
        "currentColor", which only ``config`` passes through verbatim.
        `d.add`, not `d +=` — see `sync` for why.
        """
        d.add(elm.Line().at((px, top)).to((px, bot)).linestyle("-."))
        d.add(
            elm.Label()
            .at((px, top + 0.1))
            .label(f"plane: {sch.plane}", valign="bottom")
        )

    def draw_blocks(
        blocks,
        x,
        y,
        balanced,
        marks=None,
        dim_until=None,
        plane_at=None,
        b0=None,
        row_dim=False,
    ):
        """One chain's blocks, drawn left to right from ``(x, y)``.

        The trunk and every branch row (issue #685) are the same drawing;
        only where they start and end differs. Returns the two cursors, the
        return rail's y, the balance state and ``bxs`` — the x of every block
        boundary, which is where the chain's nodes live, so junction dots,
        pass-through marks and the plane marker all land on actual nodes.
        """
        # `d += element` is a rebinding, so without this the whole body
        # would see `d` as an unassigned local — the function-scope variant
        # of the trap `sync` documents.
        nonlocal d
        # The return conductor, when there is one, occupies the band the
        # ground drops otherwise use; the datum then moves down out of its
        # way, so a common-mode pin can drop past the return rail without
        # appearing to touch it. A crossing with no junction dot is exactly
        # how a schematic says "these are not connected".
        yr = y - DY  # the return conductor, in a balanced section
        xc = x  # the return conductor's own cursor
        bxs = [x if b0 is None else b0]

        def gnd_y():
            return (yr - DY) if balanced else (y - DY)

        def sync(drawn=None):
            """Bring both conductors up to the same x, wiring whichever lags.

            The two rails advance independently — a coil in one leg is one
            symbol — so a column ends by squaring them up.
            """
            nonlocal x, xc
            if not balanced:
                return
            at = max(x, xc)
            for cur, ry in ((x, y), (xc, yr)):
                if at - cur > 1e-9:
                    # `d.add`, not `d +=`: augmented assignment would make
                    # `d` a local of this function and raise on the first
                    # rail that actually needed squaring up.
                    line = d.add(elm.Line().at((cur, ry)).to((at, ry)))
                    if drawn is not None:
                        drawn.append(line)
            x = xc = at

        for n, block in enumerate(blocks):
            dim_n = row_dim or (dim_until is not None and n < dim_until)
            if dim_until is not None:
                d.config(color=DIM if n < dim_until else base_color)
            if n:
                d += elm.Line().at((x, y)).to((x + GAP, y))
                x += GAP
                if balanced:
                    d += elm.Line().at((xc, yr)).to((xc + GAP, yr))
                    xc += GAP
                # The node between two blocks — where junction dots, marks and
                # the plane marker land, so its x is recorded.
                bxs.append(x - GAP / 2.0)
                if marks and n in marks:
                    # An antenna port the chain passes through (issue #685): an
                    # LPDA's phasing line touches every element on the way to the
                    # last one, and without the dot they are anonymous wire.
                    d += elm.Dot().at((bxs[n], y))
                    d += (
                        elm.Label()
                        .at((bxs[n], y - 0.35))
                        .label(marks[n], fontsize=SUBFONT, valign="top")
                    )
            if plane_at == n:
                # The cut sits at the node this block starts from — mid-gap
                # between blocks, or on the lead-in for a cut at the first one.
                plane_marker(bxs[n], y + 0.9, gnd_y() + 0.3)
            x0 = x
            drawn = []  # what the block's enclosure has to contain
            tall = False  # the last symbol drawn reaches below the spine
            for el in block.elements:
                if el.orient == "pair":
                    # A two-conductor line: both rails, drawn as the pair it is
                    # rather than one line with the return taken on trust. It also
                    # STARTS the pair when it is fed from a grounded shield, so
                    # the return rail may have to be brought into existence here.
                    sync(drawn)
                    if not balanced:
                        # Fed from a grounded shield: the pair's second conductor
                        # IS the datum here, so it gets a ground symbol of its own
                        # rather than a wire routed back to the source's. Repeating
                        # the symbol is how a schematic draws a global net — and it
                        # keeps the claim local, which is the honest form of it.
                        balanced = True
                        xc = x
                        g = elm.Ground().at((x, yr))
                        d += g
                        drawn.append(g)
                    x1 = x + PAIR_LEN
                    for ry in (y, yr):
                        rail = elm.Line().at((x, ry)).to((x1, ry))
                        d += rail
                        drawn.append(rail)
                    for f in (0.3, 0.5, 0.7):  # spacers, the two-wire feeder idiom
                        xt = x + (x1 - x) * f
                        tick = (
                            elm.Line()
                            .at((xt, y))
                            .to((xt, yr))
                            .linestyle(":")
                            .color("gray")
                        )
                        d += tick
                        drawn.append(tick)
                    for text, ty, size, va in (
                        (el.label, y + 0.25, FONTSIZE, "bottom"),
                        (el.sublabel, yr - 0.3, SUBFONT, "top"),
                    ):
                        if not text:
                            continue
                        lab = (
                            elm.Label()
                            .at(((x + x1) / 2.0, ty))
                            .label(text, fontsize=size, valign=va)
                        )
                        d += lab
                        drawn.append(lab)
                    x = xc = x1
                    tall = False
                elif el.orient == "shunt" and el.balanced:
                    # A rung between the conductors — a differential capacitor
                    # across a floating tuner's output. Not a drop to ground:
                    # there is no ground here to drop to.
                    sync(drawn)
                    e = symbol(el.kind)().at((x, y)).to((x, yr))
                    d += e
                    drawn.append(e)
                    mid = (y + yr) / 2.0
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
                    tall = False
                elif el.orient == "series" and el.leg == "return":
                    # A symbol in the return conductor. It shares a column with
                    # the signal-side symbol it faces, so the two halves of a
                    # split roller inductance line up instead of stepping.
                    e = symbol(el.kind)().at((xc, yr)).right()
                    if el.label:
                        e.label(el.label, loc="bottom", ofst=0.4)
                    d += e
                    drawn.append(e)
                    xc = _exit_x(e, xc + DX)
                    sync(drawn)
                    tall = False
                elif el.orient == "shunt":
                    sync(drawn)
                    if tall and (el.label or el.sublabel):
                        # Same reservation as LEADIN: a drop labels itself
                        # leftward, and a transformer fills the whole band below
                        # the spine, so step clear before dropping.
                        pad = _label_room(el) + 0.4
                        lead = elm.Line().at((x, y)).to((x + pad, y))
                        d += lead
                        drawn.append(lead)
                        x += pad
                        if balanced:
                            lead2 = elm.Line().at((xc, yr)).to((xc + pad, yr))
                            d += lead2
                            drawn.append(lead2)
                            xc += pad
                    tall = False
                    # Which conductor the drop leaves. A common-mode pin on the
                    # return leg belongs on the return leg: drawing every drop
                    # from the signal conductor stacks the pair's two pins on one
                    # another and asserts a symmetry the circuit does not have.
                    ytop = yr if (balanced and el.leg == "return") else y
                    # Drawn to an explicit endpoint for the same reason as the
                    # source, and so the termination lands *on* the end rather
                    # than part-way up a symbol that is longer than DY.
                    e = symbol(el.kind)().at((x, ytop)).to((x, gnd_y()))
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
                    bot = _exit_y(e, gnd_y())
                    mid = (ytop + bot) / 2.0
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
                    # Step on. Two drops in a row otherwise land on the same x and
                    # draw straight through each other — which is exactly what the
                    # pair of common-mode pins on a balanced feed is.
                    rails = [(x, y)] + ([(xc, yr)] if balanced else [])
                    for cur, ry in rails:
                        line = elm.Line().at((cur, ry)).to((cur + SHUNT_STEP, ry))
                        d += line
                        drawn.append(line)
                    x += SHUNT_STEP
                    if balanced:
                        xc += SHUNT_STEP
                else:
                    wound = el.kind in ("transformer", "balun")
                    sync(drawn)
                    e = symbol(el.kind)().at((x, y)).right()
                    # A winding pair's "top" is level with the conductor it enters
                    # on, so the label lands across the symbol unless it is lifted.
                    e.label(el.label, loc="top", ofst=0.8 if wound else 0)
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
                        if el.kind == "balun":
                            # THE isolation barrier. Past it there is no datum:
                            # the secondary's lower terminal is not a loose end
                            # and not a ground, it is where the return conductor
                            # begins. Drawing that is the whole point of the
                            # element — a floating balun exists to NOT bond the
                            # two sides, and a schematic says so with a dashed
                            # line through the coupling and a second rail out.
                            balanced = True
                            sx, sy = e.absanchors["s2"]
                            start = elm.Line().at((sx, sy)).to((sx, yr))
                            d += start
                            drawn.append(start)
                            xc = sx
                            px, py = e.absanchors["p1"]
                            bar = (
                                elm.Line()
                                .at(((px + sx) / 2.0, y + 0.45))
                                .to(((px + sx) / 2.0, sy - 0.45))
                                .linestyle("--")
                                .color("gray")
                            )
                            d += bar
                            drawn.append(bar)
                        # The winding bottoms are terminals, not loose ends. A
                        # `Transformer` spans BOTH windings node-to-datum, so both
                        # return legs ground; a `FloatingBalun` grounds only its
                        # primary, the secondary having just become the pair.
                        returns = ["p2"] if el.kind == "balun" else ["p2", "s2"]
                        for anchor in returns:
                            if anchor not in e.absanchors:  # pragma: no cover
                                continue
                            px, py = e.absanchors[anchor]
                            gy = min(py - TERM, gnd_y())
                            lead = elm.Line().at((px, py)).to((px, gy))
                            d += lead
                            drawn.append(lead)
                            g = elm.Ground().at((px, gy))
                            d += g
                            drawn.append(g)
                    x = _exit_x(e, x + DX)
                    tall = wound
            sync(drawn)
            if x == x0:  # a block of pure shunts still needs a step
                e = elm.Line().at((x, y)).to((x + DX, y))
                d += e
                drawn.append(e)
                x += DX
                if balanced:
                    e2 = elm.Line().at((xc, yr)).to((xc + DX, yr))
                    d += e2
                    drawn.append(e2)
                    xc += DX
            # An enclosure means "this is a box you named". A block with no path
            # is a bare branch the flattening never grouped — drawing a dashed
            # box round a lone TL and captioning it with its class name is noise,
            # and two such boxes in a row visibly collide.
            if block.path:
                note = block.label
                if block.watts:
                    note = f"{note}  ({_burn_text(block.watts, sch.p_in)})"
                # A dashed enclosure, not a floating caption: the label names a
                # box in the design, so the drawing shows where that box stops.
                box = (
                    elm.EncircleBox(drawn, padx=0.35, pady=0.35)
                    .linestyle("--")
                    .color("gray")
                )
                if note:
                    # The box's own colour is the de-emphasis gray; the label
                    # re-asserts the drawing colour so it reads as content —
                    # unless the block is upstream of a picked plane, in which
                    # case dim is exactly what it should read as.
                    box.label(note, loc="top", color=DIM if dim_n else base_color)
                d += box
            elif block.watts:
                # A bare branch has no enclosure to caption, but its burn still
                # belongs on the page — the issue's opening design is one bare
                # TL. Centered under the block, below the symbol's own sublabel.
                d += (
                    elm.Label()
                    .at(((x0 + x) / 2.0, y - 1.15))
                    .label(
                        f"({_burn_text(block.watts, sch.p_in)})",
                        fontsize=SUBFONT,
                        valign="top",
                    )
                )

        bxs.append(max(x, xc))
        return x, xc, yr, balanced, bxs

    def draw_antenna_end(x, xc, y, yr, balanced, name, leadout):
        """The chain's end: the antenna it feeds, named when there are several."""
        nonlocal d  # `d +=` rebinds — see draw_blocks
        antenna_text = f"antenna ({name})" if name else "antenna"
        if balanced:
            # A pair does not arrive at a one-terminal antenna symbol. Both
            # conductors reach the structure — the two halves of a doublet —
            # so the drawing ends in the two arms it actually feeds.
            lead = max(leadout, SHUNT_STEP + LEADOUT)
            d += elm.Line().at((x, y)).to((x + lead, y))
            d += elm.Line().at((xc, yr)).to((xc + lead, yr))
            tip = max(x, xc) + lead
            arm = 1.1
            d += elm.Line().at((tip, y)).to((tip + arm, y + arm))
            d += elm.Line().at((tip, yr)).to((tip + arm, yr - arm))
            d += (
                elm.Label()
                .at((tip + arm + 0.2, (y + yr) / 2.0))
                .label(antenna_text, halign="left")
            )
        else:
            d += elm.Line().at((x, y)).to((x + leadout, y))
            # No `.up()`: Antenna pins its own theta=0 and already draws its
            # mast upward, so rotating it lays the whole symbol on its side.
            d += elm.Antenna().at((x + leadout, y)).label(antenna_text, loc="right")

    if sch.feed_groups:
        # Multi-source summary (issue #685): no chain exists and no feed
        # network is modelled, so the page shows the one true structure —
        # N elements driven identically — as one row per drive group,
        # instead of fabricating a fan-out the solve does not contain.
        gy = math.inf  # no chain ground band; the notes key off the bbox
        x = xc = 0.0
        ry = 0.0
        for fg in sch.feed_groups:
            d += elm.SourceSin().at((0.0, ry - DY)).to((0.0, ry))
            d += elm.Ground().at((0.0, ry - DY))
            d += (
                elm.Label()
                .at((-SRC_R - 0.15, ry - DY / 2.0))
                .label(fg.drive, halign="right")
            )
            d += elm.Line().at((0.0, ry)).to((LEADIN, ry))
            d += (
                elm.Antenna()
                .at((LEADIN, ry))
                .label(f"antenna ×{fg.count}  ({fg.ports})", loc="right")
            )
            ry = d.get_bbox().ymin - 2.0
    else:
        # A picked plane makes everything from the source to the cut a
        # disconnected stub of the drawing — the source glyph included.
        if sch.plane_cut is not None:
            d.config(color=DIM)
        # `.to()` rather than `.up()`: an element's default length is one unit
        # (DX), so `.up()` from the datum overshoots the spine and leaves a bare
        # wire sticking out of the top of the source.
        d += elm.SourceSin().at((0.0, -DY)).to((0.0, 0.0))
        d += (
            elm.Label()
            .at((-SRC_R - 0.15, -DY / 2.0))
            .label(sch.source or "source", halign="right")
        )
        d += elm.Ground().at((0.0, -DY))

        # A shunt on the first spine node labels itself leftward, into the source.
        # Reserve the room here rather than nudging the label, so the drop stays
        # on the node it is electrically attached to.
        leadin = LEADIN
        first = (
            sch.blocks[0].elements[0] if sch.blocks and sch.blocks[0].elements else None
        )
        if first is not None and first.orient == "shunt":
            leadin = max(leadin, SRC_R + 0.3 + _label_room(first) + 0.5)
        d += elm.Line().at((0.0, 0.0)).to((leadin, 0.0))

        x, xc, yr, balanced, bxs = draw_blocks(
            sch.blocks,
            leadin,
            0.0,
            False,
            marks=dict(sch.marks),
            dim_until=sch.plane_cut,
            plane_at=sch.plane_cut,
            b0=leadin / 2.0,
        )
        y = 0.0
        gy = (yr - DY) if balanced else (y - DY)

        leadout = LEADOUT
        if sch.plane_cut is not None:
            # Everything from here on — the antenna, attachments, notes — is on
            # the live side of any cut; restore the drawing colour. A cut at the
            # chain's very end marks the antenna terminals themselves — and its
            # label is centered on the marker, so the lead must reserve room for
            # the text or it draws straight through the antenna symbol. Same
            # reservation idiom as LEADIN: widen the wire, never nudge the text
            # off the thing it is electrically attached to.
            d.config(color=base_color)
            if sch.plane_cut == len(sch.blocks):
                # The margin covers the antenna triangle's overhang LEFT of its
                # mast (~0.5 unit) plus a visible gap; the label is centered on
                # the marker at leadout/2, so its right edge lands at
                # text_width/2 past centre and needs the difference clear.
                leadout = max(LEADOUT, _text_width(f"plane: {sch.plane}") + 1.5)
                plane_marker(x + leadout / 2.0, y + 0.9, gy + 0.3)

        # "antenna (feed0)" when the chain's end carries a name — it only does
        # when the network has other antenna ports to confuse it with.
        if sch.ends_in_antenna:
            draw_antenna_end(x, xc, y, yr, sch.balanced_end, sch.antenna_name, leadout)

        # Feed branches (issue #685): the other arms of a corporate feed. Each
        # forks at a junction on a chain already drawn — a dot there, the mark a
        # reader's cross-reference was missing — and draws as its own row below,
        # wired down from the junction and ending at its own named antenna. Rows
        # stack downward wherever the drawing so far ends, parent before child,
        # so a depth-2 corporate tree hangs off a row that already exists.
        rows = [(0.0, bxs, False)]  # per drawn chain: (y, boundary xs, dimmed)
        for br in sch.branches:
            py, pbxs, pdim = rows[br.parent + 1]
            # Upstream of a picked plane the fork is disconnected too, and a
            # branch inherits its parent's dimming transitively.
            dim = pdim or (
                br.parent == -1 and sch.plane_cut is not None and br.at < sch.plane_cut
            )
            px = pbxs[min(br.at, len(pbxs) - 1)]
            row_y = d.get_bbox().ymin - 1.8
            if dim:
                d.config(color=DIM)
            d += elm.Dot().at((px, py))
            if br.origin != sch.source:
                # The junction's name — the referent the "← JC1" cross-reference
                # used to dangle without. The source's own label already names a
                # fork at the source node.
                d += (
                    elm.Label()
                    .at((px + 0.2, py + 0.15))
                    .label(br.origin, halign="left", valign="bottom", fontsize=SUBFONT)
                )
            d += elm.Line().at((px, py)).to((px, row_y))
            lead = 1.0
            bfirst = (
                br.blocks[0].elements[0]
                if br.blocks and br.blocks[0].elements
                else None
            )
            if bfirst is not None and bfirst.orient == "shunt":
                lead = max(lead, _label_room(bfirst) + 0.7)
            d += elm.Line().at((px, row_y)).to((px + lead, row_y))
            bx, bxc, byr, _bal, bbxs = draw_blocks(
                br.blocks,
                px + lead,
                row_y,
                br.balanced_start,
                marks=dict(br.marks),
                b0=px,
                row_dim=dim,
            )
            draw_antenna_end(
                bx, bxc, row_y, byr, br.balanced_end, br.antenna_name, LEADOUT
            )
            if dim:
                d.config(color=base_color)
            rows.append((row_y, bbxs, dim))

    # Attachments: branches wired into the antenna structure rather than into
    # the feed. They have no place on the chain, and inventing one for them is
    # exactly the fabrication this drawing is meant to stop making — so they
    # are drawn where they are, named by the nodes they bridge.
    ay = min(gy, d.get_bbox().ymin + 0.8) - 1.4
    if sch.attachments:
        d += (
            elm.Label()
            .at((0.0, ay))
            .label("wired into the antenna structure:", halign="left")
        )
        for block in sch.attachments:
            ay -= ATTACH_ROW
            el = block.elements[0] if block.elements else None
            half = (len(block.nodes) + 1) // 2
            d += (
                elm.Label()
                .at((2.2, ay))
                .label(", ".join(block.nodes[:half]), halign="right", fontsize=SUBFONT)
            )
            e = symbol(el.kind if el else "box")().at((2.5, ay)).right().length(1.6)
            # A trap in a dipole leg burns power too; an attachment carries
            # its burn on the symbol since it has no enclosure to caption.
            top = el.label if el is not None else ""
            if block.watts:
                burn = f"({_burn_text(block.watts, sch.p_in)})"
                top = f"{top}  {burn}" if top else burn
            if top:
                e.label(top, loc="top", fontsize=SUBFONT)
            if el is not None and el.sublabel:
                e.label(el.sublabel, loc="bottom", ofst=0.4, fontsize=SUBFONT)
            d += e
            if block.nodes[half:]:
                d += (
                    elm.Label()
                    .at((_exit_x(e, 4.1) + 0.3, ay))
                    .label(
                        ", ".join(block.nodes[half:]), halign="left", fontsize=SUBFONT
                    )
                )
    for i, note in enumerate(sch.notes):
        d += elm.Label().at((0.0, ay - 1.4 - i * 0.9)).label(note, halign="left")

    # show=False here, not just on the Drawing constructor: draw() defaults
    # to show=True, which writes a temp file and xdg-opens it in the desktop
    # image viewer — one popup per render, i.e. per web knob tweak.
    d.draw(show=False)
    svg = d.get_imagedata("svg").decode("utf-8")
    if path is not None:
        # schemdraw emits Ω in every impedance label; an unpinned encoding
        # falls back to the platform default, which is cp1252 on stock
        # Windows and has no code point for it (issue #772).
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(svg)
    return svg
