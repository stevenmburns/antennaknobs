import copy
import itertools
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import ClassVar, Literal, NamedTuple

import numpy as np

from .network import GradedSegments, PortAtVertex, PortOnWire, Wire, as_wire
from .wire_catalog import (
    port_at,
    port_wire,
    refuse_coincident_ports,
    site_count,
)

_logger = logging.getLogger(__name__)

# The most a positioned port's wire grows, as a multiple of its own count, to
# put the port on a site of the engine's grid (AK#1469).
SITE_COUNT_CAP = 2

SegmentParity = Literal["odd", "even", "any"]


class FarField(NamedTuple):
    rings: list
    max_gain: float
    min_gain: float
    thetas: np.ndarray
    phis: np.ndarray
    # Issue #1341: what the readout found below the ground plane. Zero / None
    # for a deck with nothing below it (and for the NEC engines, whose RP is
    # their own). A momwire deck with in-medium currents the readout could
    # serve carries the share of current moment below the plane, the
    # largest change that imaging those currents as if above ground makes
    # in the lit hemisphere, and the sentence saying so; one it could not
    # serve raises `antennaknobs.in_medium.InMediumPatternRefusal` instead.
    in_medium_moment_fraction: float = 0.0
    in_medium_power_share: float = 0.0
    in_medium_pattern_delta_db: float = 0.0
    note: str | None = None


# ---------------------------------------------------------------------------
# The duck-typed power-budget protocol every engine stamps, and its ONE rule
# ---------------------------------------------------------------------------
#
# Three attributes, read by `cli.py`'s pattern/schematic commands and by the web
# adapter's `_budget_rows`, on whichever engine ran:
#
#   _excited_p_in            input power, watts
#   _excited_efficiency      structural efficiency, a fraction
#   _excited_power_budget    [(label, watts), ...]
#
# **THE ROWS ARE LOSSES.** Nothing else. Every consumer derives the remainder
# that reaches the antenna as `p_in - sum(watts)` — `cli.py` prints it as
# "antenna (accepted)" and `SolveReadout.tsx` renders the same subtraction — so a
# row that is not a loss is subtracted from the input as if it were.
#
# This was learned the expensive way (issue #1354). The NEC-5 wrapper stamped
# ("Radiated", P_rad) beside ("Wire loss", P_loss) because its printout's POWER
# BUDGET block lists both, and the NEC-2 wrapper copied it. On a lossless design
# that makes P_rad == P_in, so both consumers printed **"antenna (accepted):
# 0 mW (0.0%)"** where momwire printed 100 %. The web NEC-5 tab had been showing
# that zero on screen; the CLI only started showing it when #1397 first reached
# these rows with the subtraction.
#
# Radiated power is NOT a budget row. It is available as `_excited_efficiency`
# (times `_excited_p_in`) and, on the wrappers that parse it from a printout, as
# `_excited_p_radiated`. The frontend's own "radiated (incl. ground)" row comes
# from the norm check, which is the honest third ledger — a loss list was never
# the channel for it.


def refuse_graded_wires(tups, engine_name):
    """A card deck takes one uniform count per wire; the graded-mesh spelling
    (``GradedSegments``, momwire#674's node grading) carries a count per EDGE.

    NEC-5 expands a graded wire into consecutive GW cards since issue #1108 —
    one per panel, chained, each with its own count — and renumbers every
    tag-addressed site through `NEC5Engine._tag_of`. **PyNEC is the caller
    that is left**, and the reason is the one this docstring always gave: a
    NEC-2 deck's EX/LD/NT cards reference wires by tag, and this package does
    not renumber them, so expanding there would silently move every downstream
    reference. Doing for PyNEC what #1108 did for NEC-5 is a real change, not
    a config line."""
    for i, t in enumerate(tups):
        if isinstance(as_wire(t).n_seg, GradedSegments):
            raise NotImplementedError(
                f"{engine_name}: wire {i} uses the graded-mesh spelling "
                "(GradedSegments), which only the momwire engine consumes "
                "today — a card deck numbers wires by tag, and a graded "
                "expansion would shift every EX/LD/NT reference"
            )


class WireCurrents(NamedTuple):
    """Per-wire knot positions + complex currents at the solve frequency.

    Engines decompose geometry differently — MomwireEngine returns one
    entry per polyline (post-translator), PyNECEngine returns one entry
    per build_wires() tuple. Callers (e.g. the web UI) treat each entry
    as an independent rendering primitive rather than assuming the lists
    are aligned across engines.
    """

    knot_positions: np.ndarray  # (M, 3) float
    knot_currents: np.ndarray  # (M,)   complex


def placement_note(port, wire, at, placed, offset_m, site):
    """AK's advisory for a positioned port an engine could not place exactly
    (AK#1469): where it was asked for, where it went, and how far that is."""
    return {
        "category": "FeedPlacement",
        "text": (
            f"Port {port!r} asks for {at:.4g} of the way along wire {wire!r}. "
            f"This engine's nearest {site} is at {placed:.4g}, "
            f"{abs(offset_m) * 1000:.3g} mm away, so the port is placed there. "
            "Nothing was refused (AK#1469)."
        ),
    }


def _and_list(items):
    """'a', 'a and b', 'a, b and c'."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def split_note(wire, ports, site):
    """AK's advisory for a wire an engine split so every positioned port on it
    is fed exactly (AK#1511): the ports and their positions, that no count up
    to the cap puts a site at all of them, and how each port is fed. The feeds
    are exact, so there is no offset to report. `ports` is ``[(port, at)]`` in
    order along the wire."""
    listed = _and_list([f"{port!r} at {at:.4g}" for port, at in ports])
    one = len(ports) == 1
    who = f"port {listed}" if one else f"ports {listed}"
    where = "there" if one else "at all of them"
    each = "the port is" if one else "every port is"
    if site == "knot" and one:
        how = (
            "so the wire is split there and the port is fed exactly, at the knot "
            "the two pieces share"
        )
    elif site == "knot":
        how = (
            "so the wire is split at each port and every port is fed exactly, at "
            "the knot the pieces on either side share"
        )
    else:
        how = (
            f"so the wire is split and {each} fed exactly, at the middle of a "
            "short piece of its own"
        )
    return {
        "category": "FeedPlacement",
        "text": (
            f"Wire {wire!r} carries {who} of its length. No segment count up to "
            f"{SITE_COUNT_CAP}× the wire's own puts a {site} {where}, {how} "
            "(AK#1511)."
        ),
    }


# A value within this of a half counts as the half. A piece's length in
# segments comes out of floating point: (1 - 0.77) * 150 is 34.49999999999999,
# where its mirror image, 0.23 * 150, may be 34.5. Without the tolerance a wire
# and its mirror image could get different counts.
_HALF_TOL = 1e-9


def _nearest_count(segments):
    """The count, at least 1, nearest `segments`. A half rounds up, 46.5 -> 47,
    to within `_HALF_TOL`, the same convention as `_nearest_odd_count`."""
    return max(1, math.floor(segments + 0.5 + _HALF_TOL))


def _nearest_odd_count(segments):
    """The odd count, at least 1, nearest `segments`: its middle is a segment
    centre. A tie, an even `segments` exactly between two odd counts (to within
    `_HALF_TOL`), takes the larger one, so the rule never depends on which odd
    count sits at an even half-index: 2 -> 3, 4 -> 5, 6 -> 7."""
    return max(1, 2 * math.floor((segments - 1) / 2 + 0.5 + _HALF_TOL) + 1)


class SplitSpan(NamedTuple):
    """One piece of a split wire, as fractions of the wire (AK#1511)."""

    lo: float
    hi: float
    n_seg: int
    # The index, in order along the wire, of the port this piece feeds: at its
    # middle on a segment-centre engine, at its `hi` knot on a knot engine.
    # None for a plain filler (or a knot engine's last piece).
    port: int | None


class SplitPlan(NamedTuple):
    """How `split_spans` cuts a wire (AK#1511)."""

    spans: tuple[SplitSpan, ...]
    # Centre engines: each port's half-width x, so its piece is [u - x, u + x].
    # Empty for a knot engine.
    half: tuple[float, ...]
    # Centre engines: whether the end guard fired at the wire's p0 / p1 end.
    guard: tuple[bool, bool]


def split_spans(n_seg, positions, parity):
    """The pieces a wire of `n_seg` segments is cut into so that every port at
    `positions` (fractions in (0, 1), distinct) is fed exactly (AK#1511). The
    deterministic rule decided on the issue; with h = 1/n_seg:

    A knot engine (even parity) cuts at every port. Each piece takes the count
    nearest length/h, at least 1, a half rounding up (`_nearest_count`), and
    port i is fed at the `hi` knot of piece i, which it shares with piece i + 1.

    A segment-centre engine (odd parity) gives port i a short piece
    [u_i - x_i, u_i + x_i] centred on it, with the odd count nearest 2 x_i / h
    (at least 1), so its middle segment's centre is the port. x_i is the
    smallest of its limits:

    - g/4 for each neighbouring port at gap g;
    - for an end port, b/3 for its wire end at distance b. The guard: with
      OTHER the smallest of the port's remaining limits (its neighbour's g/4
      and, for a lone port, the other end's b'/3), an end with b <= h and
      b <= OTHER has the limit b instead, so the piece runs to that end with no
      filler. The two ends of a lone port cannot both fire (b <= b'/3 and
      b' <= b/3 together need b = 0).

    Plain fillers take the gaps, each the count nearest length/h, at least 1, a
    half rounding up, and the zero-length filler where the guard fired is
    omitted. So a filler between
    two ports is at least g/2, an end filler at least 2b/3, and every piece has
    a lower bound set by the local geometry: no slivers."""
    n = max(int(n_seg), 1)
    u = sorted(float(a) for a in positions)
    k = len(u)
    if parity == "even":
        cuts = [0.0, *u, 1.0]
        return SplitPlan(
            spans=tuple(
                SplitSpan(lo, hi, _nearest_count((hi - lo) * n), i if i < k else None)
                for i, (lo, hi) in enumerate(itertools.pairwise(cuts))
            ),
            half=(),
            guard=(False, False),
        )
    h = 1.0 / n
    half = []
    guard = [False, False]
    for i, ui in enumerate(u):
        near = []
        if i > 0:
            near.append((ui - u[i - 1]) / 4)
        if i < k - 1:
            near.append((u[i + 1] - ui) / 4)
        ends = []
        if i == 0:
            ends.append((0, ui))
        if i == k - 1:
            ends.append((1, 1.0 - ui))
        limits = list(near)
        for side, b in ends:
            other = min(near + [b2 / 3 for s2, b2 in ends if s2 != side])
            if b <= h and b <= other:
                guard[side] = True
                limits.append(b)
            else:
                limits.append(b / 3)
        half.append(min(limits))
    spans = []
    edge = 0.0
    for i, (ui, xi) in enumerate(zip(u, half, strict=True)):
        lo = 0.0 if i == 0 and guard[0] else ui - xi
        hi = 1.0 if i == k - 1 and guard[1] else ui + xi
        if not (i == 0 and guard[0]):
            spans.append(SplitSpan(edge, lo, _nearest_count((lo - edge) * n), None))
        spans.append(SplitSpan(lo, hi, _nearest_odd_count(2 * xi * n), i))
        edge = hi
    if not guard[1]:
        spans.append(SplitSpan(edge, 1.0, _nearest_count((1.0 - edge) * n), None))
    return SplitPlan(spans=tuple(spans), half=tuple(half), guard=tuple(guard))


class WireSplit(NamedTuple):
    """One authored wire as an engine split it (AK#1511)."""

    # (port name, at) in order along the wire, the middle as 0.5.
    ports: tuple[tuple[str, float], ...]
    # The wire name of the piece each port feeds, in the same order.
    pieces: tuple[str, ...]
    plan: SplitPlan


def _piece_name(wire, port, taken):
    """The wire name of the piece `port` feeds on split wire `wire`:
    ``"<wire>@<port>"``, with ``#2``, ``#3``, ... appended in the rare case a
    wire of the design already carries that name. Deterministic, and never a
    name in `taken`, which it joins (AK#1511)."""
    base = f"{wire}@{port}"
    name, i = base, 1
    while name in taken:
        i += 1
        name = f"{base}#{i}"
    taken.add(name)
    return name


def _fed_record(port, index, wire, site):
    """One `SimulationEngine.fed_segments` record for a straight wire. A knot
    record carries the segment on the knot's far side too, the same length
    unless a split says otherwise."""
    n = int(wire.n_seg)
    length = float(np.linalg.norm(np.subtract(wire.p1, wire.p0)))
    rec = {
        "port": port,
        "wire": index,
        "segments": n,
        "length_m": length / n,
        "site": site,
    }
    if site == "knot":
        rec["length_after_m"] = length / n
    return rec


def _builder_network(builder):
    """The builder's `build_network()`, or None when it has none."""
    build = getattr(builder, "build_network", None)
    return build() if callable(build) else None


def fed_records(wires, network, parity, owners=None):
    """`SimulationEngine.fed_segments` over an engine's COERCED wire list and
    its network AS MESHED (AK#1456): the legacy ``ex`` wires, then every gap
    or end port, each on the wire it names.

    A port NEC-5 feeds through a wire split at its ports (AK#1510, AK#1511)
    arrives as a `PortAtVertex` at the p1 end of the piece named for it
    (``<wire>@<port>``), and `owners` (the authored entry each wire came from)
    says the next piece is the same wire. That source is the knot the two
    pieces share, so its record is a knot whose two segments are that piece's
    last and the next piece's first. A segment-centre engine's split port
    arrives as a gap at the middle of its own piece, and reports that piece."""
    from .network import PortAtEnd

    wires = [as_wire(t) for t in wires]
    site = "knot" if parity == "even" else "centre"
    out = [
        _fed_record(None, i, w, site)
        for i, w in enumerate(wires)
        if w.ex is not None and not isinstance(w.n_seg, GradedSegments)
    ]
    if network is None:
        return out
    by_name = {w.name: i for i, w in enumerate(wires) if w.name is not None}
    for name, port in network.ports.items():
        if isinstance(port, PortOnWire):
            index, where = by_name.get(port_wire(port)), site
        elif isinstance(port, (PortAtVertex, PortAtEnd)):
            index, where = by_name.get(port.wire), "end"
        else:
            continue
        if index is None or isinstance(wires[index].n_seg, GradedSegments):
            continue
        nxt = index + 1
        if (
            where == "end"
            and getattr(port, "end", None) == "p1"
            and owners is not None
            and len(owners) == len(wires)
            and nxt < len(wires)
            and owners[nxt] == owners[index]
        ):
            rec = _fed_record(name, index, wires[index], "knot")
            rec["length_after_m"] = _fed_record(None, nxt, wires[nxt], "knot")[
                "length_m"
            ]
        else:
            rec = _fed_record(name, index, wires[index], where)
        out.append(rec)
    return out


def _port_positions(builder):
    """``({wire name: [(port name, at), ...]}, referenced)`` for the gap ports
    of the builder's network (AK#1469): every wire carrying a gap port with an
    explicit position, and the set of wire names any port references.

    A wire whose ports all sit at the middle is absent: the parity rule already
    serves it, and the old counts must not move. No builder (a stub borrowing
    the coercion) means no positions."""
    build = getattr(builder, "build_network", None)
    net = build() if callable(build) else None
    if net is None:
        return {}, set()
    by_wire: dict = {}
    referenced = set()
    for name, port in net.ports.items():
        if isinstance(port, PortOnWire):
            referenced.add(port_wire(port))
            if not getattr(port, "distributed", False):
                by_wire.setdefault(port_wire(port), []).append((name, port_at(port)))
        elif isinstance(getattr(port, "wire", None), str):
            referenced.add(port.wire)
    positions = {
        w: ports
        for w, ports in by_wire.items()
        if any(at is not None for _name, at in ports)
    }
    return positions, referenced


class SimulationEngine(ABC):
    supports_far_field: ClassVar[bool] = False
    # Engines that demand a specific basis parity override this. The
    # geometry loader bumps a FED or NAMED wire's n_seg up to the next
    # valid value so the attachment lands on a middle segment (we never
    # bump down — n=0 is invalid); unmarked wires keep their exact count
    # (issue #450). "any" disables coercion.
    segment_parity: ClassVar[SegmentParity] = "any"
    # An engine whose gap can only sit on a site of its own grid sets this: a
    # wire whose positioned ports no count up to the cap puts on sites, one
    # port or several, is split so every port sits exactly on one (AK#1510,
    # AK#1511; `split_spans`): at the middle of a short piece of its own for a
    # segment-centre engine, at the knot two pieces share for a knot engine.
    # momwire never splits.
    splits_wire_at_feed: ClassVar[bool] = False

    def __init__(self, builder):
        self.builder = builder

    def _refuse_ge_minus_one_contact(self, ground):
        """Refuse a file design whose deck says `GE -1` and has a FREE wire
        end in the ground plane, when this engine applies a ground
        (antennaknobs#1460; the rule is `nec_import.ge_minus_one_contact_refusal`).

        Every engine calls this right after resolving its ground, before any
        binary probe. Catalog designs carry no parsed deck and never refuse.
        """
        deck = getattr(self.builder, "file_deck_parsed", None)
        if deck is None:
            return
        from .nec_import import ge_minus_one_contact_refusal

        message = ge_minus_one_contact_refusal(deck, ground)
        if message is not None:
            raise ValueError(message)

    @staticmethod
    def coerce_n_seg(n_seg: int, parity: SegmentParity) -> int:
        # Floor below the parity step. n_seg=0 is invalid for every engine
        # (momwire divides edge length by it), and even-parity engines need
        # at least 2 segments to host a feed straddling a midpoint.
        if parity == "even":
            n_seg = max(2, n_seg)
            return n_seg + 1 if n_seg % 2 == 1 else n_seg
        if parity == "odd":
            n_seg = max(1, n_seg)
            return n_seg + 1 if n_seg % 2 == 0 else n_seg
        return max(1, n_seg)

    @property
    def advisories(self):
        """AK's own notes on how this engine meshed the design, as
        ``{"category", "text"}``: one per wire it split so the positioned ports
        on it are fed exactly (AK#1511). Empty for an ordinary design, whose
        ports all sit at a wire's middle or on a site of a re-meshed count.

        A splitting engine never places a port on a nearest site, so there is
        no offset note here; momwire's snapping bases report their own."""
        site = {"odd": "segment centre", "even": "knot"}.get(self.segment_parity)
        return [
            split_note(wire, split.ports, site)
            for wire, split in (getattr(self, "_split_wires", None) or {}).items()
        ]

    def _network_as_meshed(self, net):
        """`net` as this engine meshes it (AK#1510, AK#1511), so every reader
        of a split port's position (segment, knot, card, drive point, reducer
        attach) feeds the site the split made, never `at` re-applied to a
        piece. A shallow copy: the builder's network is untouched.

        Each port on a split wire maps to the piece named for it
        (`_piece_name`). On a segment-centre engine the port sits at the MIDDLE
        of that piece. On a knot engine it is the series source at the piece's
        p1 end, the knot it shares with the next piece: the `PortAtVertex`
        NEC-5 serves natively (issue #898), whose source and loads sit at that
        knot as they would at an interior one."""
        pieces = getattr(self, "_split_ports", None)
        if net is None or not pieces:
            return net

        def meshed_port(name, port):
            piece = pieces.get(name)
            if piece is None:
                return port
            if self.segment_parity == "even":
                return PortAtVertex(wire=piece, end="p1")
            return replace(port, wire=piece, at=None)

        meshed = copy.copy(net)
        meshed.ports = {name: meshed_port(name, p) for name, p in net.ports.items()}
        return meshed

    def _authored_currents(self, currents):
        """One `WireCurrents` per authored ``build_wires()`` entry (AK#1510).
        Every piece of a split wire joins back into that wire, in order, so a
        caller indexing currents by the design's own wires finds each one where
        the design wrote it. The knot at each cut takes the mean of the two
        pieces' end currents, the rule every interior knot follows."""
        owners = getattr(self, "_tup_authored", None)
        if not getattr(self, "_split_wires", None) or owners is None:
            return currents
        out, last = [], None
        for owner, wc in zip(owners, currents, strict=True):
            if owner == last:
                prev = out[-1]
                joint = 0.5 * (prev.knot_currents[-1] + wc.knot_currents[0])
                out[-1] = WireCurrents(
                    knot_positions=np.concatenate(
                        [prev.knot_positions, wc.knot_positions[1:]]
                    ),
                    knot_currents=np.concatenate(
                        [prev.knot_currents[:-1], [joint], wc.knot_currents[1:]]
                    ),
                )
            else:
                out.append(wc)
            last = owner
        return out

    def fed_segments(self):
        """The segment each feed and port sits on, as THIS engine meshes it
        (AK#1456): ``[{"port", "wire", "segments", "length_m", "site"}]``.

        Engines differ here by construction. The parity coercion puts a delta
        gap mid-segment on an odd count (momwire's bs2, PyNEC, NEC-2) and a
        NEC-5 source on the centre knot of an even count, so the house 50 mm
        gap wire is one 50 mm segment on one engine and two 25 mm segments on
        the other. A near-open driving point is sensitive to that size, so a
        row comparing engines records both.

        ``site`` is ``"centre"`` (a gap in the middle of a segment
        ``length_m`` long), ``"knot"`` (a source between two such segments)
        or ``"end"`` (a port at the wire's end). ``port`` is the network
        port's name, or None for a legacy ``ex`` feed; ``wire`` indexes the
        engine's coerced wire list, or is None where the engine keeps none.
        A knot record also carries ``length_after_m``, the segment on the
        knot's far side. It equals ``length_m`` except where a wire is split at
        its ports (AK#1510, AK#1511) and the source is the knot two pieces
        share. Read
        from the engine's own coerced wires and its network as meshed, so it
        reports what the engine solves, and it needs no solve."""
        tups = getattr(self, "tups", None)
        if tups is None:
            return []
        return fed_records(
            tups,
            self._network_as_meshed(_builder_network(self.builder)),
            self.segment_parity,
            getattr(self, "_tup_authored", None),
        )

    def _split_wire(self, t, at_here, parity, taken):
        """Wire entry `t` cut by `split_spans` so every port in `at_here`
        (``[(port name, at)]``, None the middle) is fed exactly (AK#1511),
        recording the split on `_split_wires` and `_split_ports`. Returns the
        pieces in p0 -> p1 order.

        Every piece keeps the wire's orientation and spec, and neighbours meet
        at the same point. The piece a port feeds is named for it
        (`_piece_name`), so the meshed network can point that port at it;
        fillers are unnamed. A legacy ``ex`` on the wire rides on the first fed
        piece: a positioned port only exists in a `build_network()` design,
        where PyNEC and NEC-2 ignore ``ex`` and NEC-5 refuses the mix, and the
        refusal must still see it."""
        wire = as_wire(t)
        refuse_coincident_ports(wire.name, at_here)
        middle = [(port, 0.5 if at is None else float(at)) for port, at in at_here]
        ordered = tuple(sorted(middle, key=lambda p: p[1]))
        plan = split_spans(wire.n_seg, [at for _port, at in ordered], parity)
        names = tuple(_piece_name(wire.name, port, taken) for port, _at in ordered)

        def point(frac):
            if frac == 0.0:
                return wire.p0
            if frac == 1.0:
                return wire.p1
            return tuple(
                float(a + frac * (b - a)) for a, b in zip(wire.p0, wire.p1, strict=True)
            )

        pieces = []
        ex = wire.ex
        for span in plan.spans:
            name = None if span.port is None else names[span.port]
            here, ex = (ex, None) if name is not None else (None, ex)
            p0, p1 = point(span.lo), point(span.hi)
            if isinstance(t, Wire) or len(t) == 6:
                pieces.append(
                    wire._replace(p0=p0, p1=p1, n_seg=span.n_seg, ex=here, name=name)
                )
            else:
                pieces.append((p0, p1, span.n_seg, here, name))
        self._split_wires[wire.name] = WireSplit(ports=ordered, pieces=names, plan=plan)
        self._split_ports.update(
            {port: name for (port, _at), name in zip(ordered, names, strict=True)}
        )
        _logger.info(
            "%s split wire %r into %d pieces so %s sit(s) exactly on its sites",
            type(self).__name__,
            wire.name,
            len(pieces),
            ", ".join(f"{port!r} at {at:.6g}" for port, at in ordered),
        )
        return pieces

    def _parity_exempt_names(self):
        """Wire names exempt from parity coercion even though marked.

        Coercion exists to land a MID-WIRE attachment on a middle segment;
        an engine whose port sits at a wire END (NEC-5's EX-at-knot for
        `PortAtVertex`, issue #898) overrides this to exempt wires whose
        only attachment is such a port — bumping their count would change
        the author's mesh for nothing."""
        return frozenset()

    def _coerce_wire_tuples(self, tups):
        """Returns the input tuples with each n_seg bumped to the engine's
        required parity. Logs once per distinct (n_in, n_out) shift so a
        converge sweep doesn't spam the log per-edge. Reads
        self.segment_parity so subclasses can set it per-instance (e.g.
        MomwireEngine, where the parity depends on the chosen solver)."""
        parity = self.segment_parity
        if parity == "any":
            return tups
        positions, referenced = _port_positions(getattr(self, "builder", None))
        family = {"odd": "centre", "even": "knot"}.get(parity)
        splits = getattr(self, "splits_wire_at_feed", False)
        # Authored wire name -> WireSplit for each wire split at its ports, port
        # name -> the piece that feeds it, and the authored entry each output
        # entry came from (AK#1510, AK#1511).
        self._split_wires = {}
        self._split_ports = {}
        self._tup_authored = []
        taken = referenced | {as_wire(t).name for t in tups} - {None}
        seen = set()
        out = []
        for index, t in enumerate(tups):
            w = as_wire(t)
            if isinstance(w.n_seg, GradedSegments):
                # Graded wires are structural (no ex/name — the geometry
                # walk enforces it) and carry explicit per-panel counts;
                # parity coercion never applies to them.
                out.append(t)
                self._tup_authored.append(index)
                continue
            # Parity coercion exists to land an engine attachment on a wire's
            # middle segment: a feed's delta gap (odd parity) or an even-parity
            # solver's midpoint. Only wires that HOST an attachment — a legacy
            # EX (``ex``) or a named network port (``name``: feed/load/TL/NT) —
            # need it. Coercing an UNMARKED wire's segment count is gratuitous,
            # and for a deck whose author chose an exact mesh (nec_import) on a
            # tightly-coupled structure like a capacity hat it changes the
            # modeled coupling enough to corrupt the impedance — reactance sign
            # flip on the spiral-hat verticals (issue #450). Preserve unmarked
            # wires' n_seg verbatim; NEC-2 and every momwire basis accept any
            # per-edge count (the count only has to be valid, i.e. ≥ 1).
            # Catalog consequence: a native design whose ``segs_for`` lands an
            # EVEN count on an unfed wire now keeps it (was silently bumped to
            # odd), so its impedance shifts a hair under the odd-parity engines,
            # and a knob move can flip an unfed wire's parity mid-sweep — a
            # ~0.01 Ω wobble, not a bug. Measured design deltas: 0.00 Ω for
            # PyNEC/Sinusoidal/BSpline-d2, 0.05 Ω for the d=1 tent basis.
            marked = (
                w.ex is not None or w.name is not None
            ) and w.name not in self._parity_exempt_names()
            n_new = self.coerce_n_seg(w.n_seg, parity) if marked else max(1, w.n_seg)
            # A port positioned along this wire (AK#1469) wants a count at which
            # its position is a site of this engine's grid, not just the middle,
            # up to SITE_COUNT_CAP times the authored count, one count for every
            # port on the wire at once. Past that, an engine that splits cuts
            # the wire so every port on it, one or several, sits exactly on a
            # site (AK#1511).
            at_here = positions.get(w.name) if marked else None
            if at_here and family is not None:
                m = site_count(
                    w.n_seg,
                    [at for _name, at in at_here],
                    family,
                    cap=SITE_COUNT_CAP,
                )
                if m is not None:
                    n_new = m
                elif splits:
                    pieces = self._split_wire(t, at_here, parity, taken)
                    self._tup_authored += [index] * len(pieces)
                    out.extend(pieces)
                    continue
            if n_new != w.n_seg and (w.n_seg, n_new) not in seen:
                seen.add((w.n_seg, n_new))
                _logger.info(
                    "%s bumped n_seg=%d → %d for %s parity",
                    type(self).__name__,
                    w.n_seg,
                    n_new,
                    parity,
                )
            # Preserve the entry's original shape: plain tuples stay plain
            # (so tests and shape-sensitive callers see what they passed),
            # Wire entries keep name and spec.
            if isinstance(t, Wire) or len(t) == 6:
                out.append(w._replace(n_seg=n_new))
            elif len(t) == 5:
                out.append((w.p0, w.p1, n_new, w.ex, w.name))
            else:
                out.append((w.p0, w.p1, n_new, w.ex))
            self._tup_authored.append(index)
        return out

    @abstractmethod
    def impedance(self): ...

    @abstractmethod
    def impedance_sweep(self, freqs): ...

    def far_field(self, *, n_theta, n_phi, del_theta, del_phi):
        raise NotImplementedError(
            f"{type(self).__name__} does not support far-field computation"
        )

    def current_distribution(self):
        """Return list[WireCurrents] at the builder's frequency."""
        raise NotImplementedError(f"{type(self).__name__} does not expose currents yet")
