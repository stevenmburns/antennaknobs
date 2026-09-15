import copy
import logging
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import ClassVar, Literal, NamedTuple

import numpy as np

from .network import GradedSegments, PortAtVertex, PortOnWire, Wire, as_wire
from .wire_catalog import gap_knot, gap_segment, port_at, port_wire, site_count

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


def _positioned_ports(builder):
    """[(port name, wire name, at)] for every non-distributed gap port that
    names a position (AK#1469). No builder, or no network, means none."""
    build = getattr(builder, "build_network", None)
    net = build() if callable(build) else None
    if net is None:
        return []
    return [
        (name, port_wire(port), port_at(port))
        for name, port in net.ports.items()
        if isinstance(port, PortOnWire)
        and not getattr(port, "distributed", False)
        and port_at(port) is not None
    ]


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


def _grid_placement_notes(tups, ports, parity):
    """The placement advisories for an engine that places a port on the
    segment centres (odd parity) or knots (even parity) of its final count."""
    family = {"odd": "centre", "even": "knot"}.get(parity)
    if family is None or not ports:
        return []
    wires = {}
    for t in tups:
        w = as_wire(t)
        if w.name is not None and not isinstance(w.n_seg, GradedSegments):
            wires[w.name] = w
    notes = []
    for port, wire, at in ports:
        w = wires.get(wire)
        if w is None:
            continue
        n = int(w.n_seg)
        if family == "centre":
            placed, site = (gap_segment(n, at) - 0.5) / n, "segment centre"
        else:
            placed, site = gap_knot(n, at) / n, "knot"
        if abs(placed - at) <= 1e-9:
            continue
        length = float(np.linalg.norm(np.subtract(w.p1, w.p0)))
        notes.append(
            placement_note(port, wire, at, placed, (placed - at) * length, site)
        )
    return notes


def split_note(port, wire, at, cuts, site):
    """AK's advisory for a positioned port whose wire an engine split at the
    feed (AK#1510): where it was asked for, that no count up to the cap has a
    site there, and where the wire was cut. The feed is exact, so there is no
    offset to report."""
    where = " and ".join(f"{c:.4g}" for c in cuts)
    if site == "knot":
        how = (
            f"so the wire is split in two at {where} and the port is fed at the "
            "knot the two pieces share"
        )
    else:
        pieces = "two" if len(cuts) == 1 else "three"
        how = (
            f"so the wire is split in {pieces} at {where} of its length and the "
            "port is fed exactly, at the middle of its piece"
        )
    return {
        "category": "FeedPlacement",
        "text": (
            f"Port {port!r} asks for {at:.4g} of the way along wire {wire!r}. "
            f"No segment count up to {SITE_COUNT_CAP}× the wire's own puts a "
            f"{site} there, {how} (AK#1510)."
        ),
    }


def _nearest_odd_count(segments):
    """The odd count, at least 1, nearest `segments`: its middle is a segment
    centre."""
    return max(1, 2 * round((segments - 1) / 2) + 1)


def _split_at_feed(t, at, parity):
    """Wire entry `t` cut so a port at `at` sits exactly on a site (AK#1510):
    ``(pieces in p0 -> p1 order, cuts as fractions)``.

    A knot engine (even parity) feeds a knot at a piece's END, so the wire is
    broken at the port itself: [0, at] keeps the wire's name, ex and spec,
    [at, 1] is unnamed with the same spec, each takes its own share of the
    authored count, at least 1, and the port is fed at the knot they share.
    No parity applies, since that knot is an end of both pieces.

    A segment-centre engine (odd parity) needs the port at a piece's MIDDLE.
    Two pieces: the carrying piece is [0, 2*at] for at < 1/2 and [2*at - 1, 1]
    above it, so its middle is `at`. It takes its share of the authored count
    raised to odd, so its middle is a segment centre; the other piece takes
    its own share, at least 1.

    That other piece is |1 - 2*at| of the wire, shorter than half an authored
    segment h = 1/n when |1 - 2*at| * n < 1/2: a sliver at the far end. Then
    the carrying piece is [at - w, at + w] between two fillers. With d the
    distance to the nearer end, the nearer filler is d - w = h, or h/2 when h
    leaves w < h/2, and the far filler is 1 - d - w >= h/2. Near the middle
    d > 1/2 - h/4, so h serves n >= 4 and h/2 serves n = 3. A wire of one or
    two segments keeps the two-piece split. The carrying piece takes the odd
    count nearest its length in authored segments, each filler its own, at
    least 1.

    Every piece but the carrying one is unnamed with the same spec, and all
    keep the wire's orientation and meet at the cuts."""
    wire = as_wire(t)
    n = int(wire.n_seg)
    h = 1 / n
    spans = None
    if parity == "even":
        spans = [
            (0.0, at, max(1, round(at * n)), True),
            (at, 1.0, max(1, round((1 - at) * n)), False),
        ]
    elif abs(1 - 2 * at) * n < 0.5:
        d = min(at, 1 - at)
        half = next((d - near for near in (h, h / 2) if d - near >= h / 2), None)
        if half is None:
            _logger.warning(
                "wire %r has %d segment(s): a port at %.6g leaves a piece of "
                "%.3g of the wire at its far end",
                wire.name,
                n,
                at,
                abs(1 - 2 * at),
            )
        else:
            lo, hi = at - half, at + half
            spans = [
                (0.0, lo, max(1, round(lo * n)), False),
                (lo, hi, _nearest_odd_count(2 * half * n), True),
                (hi, 1.0, max(1, round((1 - hi) * n)), False),
            ]
    if spans is None:
        share = 2 * at if at < 0.5 else 2 * (1 - at)
        cut = 2 * at if at < 0.5 else 2 * at - 1
        carrying = SimulationEngine.coerce_n_seg(max(1, round(share * n)), parity)
        rest = max(1, round((1 - share) * n))
        spans = (
            [(0.0, cut, carrying, True), (cut, 1.0, rest, False)]
            if at < 0.5
            else [(0.0, cut, rest, False), (cut, 1.0, carrying, True)]
        )

    def point(frac):
        if frac == 0.0:
            return wire.p0
        if frac == 1.0:
            return wire.p1
        return tuple(
            float(a + frac * (b - a)) for a, b in zip(wire.p0, wire.p1, strict=True)
        )

    pieces = []
    for lo, hi, count, carries in spans:
        ex, name = (wire.ex, wire.name) if carries else (None, None)
        if isinstance(t, Wire) or len(t) == 6:
            pieces.append(
                wire._replace(p0=point(lo), p1=point(hi), n_seg=count, ex=ex, name=name)
            )
        else:
            pieces.append((point(lo), point(hi), count, ex, name))
    return pieces, tuple(hi for _lo, hi, _n, _c in spans[:-1])


def _fed_record(port, index, wire, site):
    """One `SimulationEngine.fed_segments` record for a straight wire."""
    n = int(wire.n_seg)
    length = float(np.linalg.norm(np.subtract(wire.p1, wire.p0)))
    return {
        "port": port,
        "wire": index,
        "segments": n,
        "length_m": length / n,
        "site": site,
    }


def fed_records(wires, builder, parity):
    """`SimulationEngine.fed_segments` over an engine's COERCED wire list: the
    legacy ``ex`` wires, then every gap or end port the builder's network
    declares, each on the wire it names (AK#1456)."""
    from .network import PortAtEnd, PortAtVertex

    wires = [as_wire(t) for t in wires]
    site = "knot" if parity == "even" else "centre"
    out = [
        _fed_record(None, i, w, site)
        for i, w in enumerate(wires)
        if w.ex is not None and not isinstance(w.n_seg, GradedSegments)
    ]
    build = getattr(builder, "build_network", None)
    net = build() if callable(build) else None
    if net is None:
        return out
    by_name = {w.name: i for i, w in enumerate(wires) if w.name is not None}
    for name, port in net.ports.items():
        if isinstance(port, PortOnWire):
            index, where = by_name.get(port_wire(port)), site
        elif isinstance(port, (PortAtVertex, PortAtEnd)):
            index, where = by_name.get(port.wire), "end"
        else:
            continue
        if index is None or isinstance(wires[index].n_seg, GradedSegments):
            continue
        out.append(_fed_record(name, index, wires[index], where))
    return out


def _port_positions(builder):
    """{wire name: [(port name, at), ...]} for every wire carrying a gap port
    with an explicit position (AK#1469), read from the builder's network.

    A wire whose ports all sit at the middle is absent: the parity rule already
    serves it, and the old counts must not move. No builder (a stub borrowing
    the coercion) means no positions."""
    build = getattr(builder, "build_network", None)
    net = build() if callable(build) else None
    if net is None:
        return {}
    by_wire: dict = {}
    for name, port in net.ports.items():
        if isinstance(port, PortOnWire) and not getattr(port, "distributed", False):
            by_wire.setdefault(port_wire(port), []).append((name, port_at(port)))
    return {
        w: ports
        for w, ports in by_wire.items()
        if any(at is not None for _name, at in ports)
    }


class SimulationEngine(ABC):
    supports_far_field: ClassVar[bool] = False
    # Engines that demand a specific basis parity override this. The
    # geometry loader bumps a FED or NAMED wire's n_seg up to the next
    # valid value so the attachment lands on a middle segment (we never
    # bump down — n=0 is invalid); unmarked wires keep their exact count
    # (issue #450). "any" disables coercion.
    segment_parity: ClassVar[SegmentParity] = "any"
    # An engine whose gap can only sit on a site of its own grid sets this: a
    # wire carrying ONE positioned port that no count up to the cap puts on a
    # site is split so the port sits exactly on one (AK#1510), at the middle
    # of a piece for a segment-centre engine and at the knot two pieces share
    # for a knot engine. momwire never splits.
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
        ``{"category", "text"}``: a positioned port it fed through a split
        wire (AK#1510), or one it could not place exactly (AK#1469). Empty for
        an ordinary design, whose ports all sit at a wire's middle."""
        splits = getattr(self, "_split_feeds", None) or {}
        site = {"odd": "segment centre", "even": "knot"}.get(self.segment_parity)
        notes = [
            split_note(port, wire, at, cuts, site)
            for port, (wire, at, cuts) in splits.items()
        ]
        return notes + _grid_placement_notes(
            getattr(self, "tups", None) or (),
            [
                p
                for p in _positioned_ports(getattr(self, "builder", None))
                if p[0] not in splits
            ],
            self.segment_parity,
        )

    def _network_as_meshed(self, net):
        """`net` as this engine meshes it (AK#1510), so every reader of a split
        port's position (segment, knot, card or drive point) feeds the site the
        split made, never `at` re-applied to a piece. A shallow copy: the
        builder's network is untouched.

        On a segment-centre engine the port sits at the MIDDLE of the piece
        carrying the wire's name. On a knot engine it is the series source at
        that piece's p1 end, the knot it shares with the next piece: the
        `PortAtVertex` NEC-5 serves natively (issue #898), whose source and
        loads sit at that knot as they would at an interior one."""
        splits = getattr(self, "_split_feeds", None)
        if net is None or not splits:
            return net

        def meshed_port(name, port):
            if name not in splits:
                return port
            if self.segment_parity == "even":
                return PortAtVertex(wire=port_wire(port), end="p1")
            return replace(port, at=None)

        meshed = copy.copy(net)
        meshed.ports = {name: meshed_port(name, p) for name, p in net.ports.items()}
        return meshed

    def _authored_currents(self, currents):
        """One `WireCurrents` per authored ``build_wires()`` entry (AK#1510).
        The two pieces of a wire split at its feed join back into that wire,
        so a caller indexing currents by the design's own wires finds each one
        where the design wrote it. The knot at the cut takes the mean of the
        two pieces' end currents, the rule every interior knot follows."""
        owners = getattr(self, "_tup_authored", None)
        if not getattr(self, "_split_feeds", None) or owners is None:
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
        Read from the engine's own coerced wires, so it reports what the
        engine solves, and it needs no solve."""
        tups = getattr(self, "tups", None)
        if tups is None:
            return []
        return fed_records(tups, self.builder, self.segment_parity)

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
        positions = _port_positions(getattr(self, "builder", None))
        family = {"odd": "centre", "even": "knot"}.get(parity)
        splits = getattr(self, "splits_wire_at_feed", False)
        # Port name -> (wire, at, cuts) for each wire split at its feed, and the
        # authored entry each output entry came from (AK#1510).
        self._split_feeds = {}
        self._tup_authored = []
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
            # up to SITE_COUNT_CAP times the authored count. Past that, an engine
            # that splits cuts a wire carrying that ONE port so the port sits on
            # a site (AK#1510). A wire carrying several keeps the parity count,
            # and the engine places each on its nearest site.
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
                elif splits and len(at_here) == 1:
                    ((port, at),) = at_here
                    pieces, cuts = _split_at_feed(t, at, parity)
                    self._split_feeds[port] = (w.name, at, cuts)
                    self._tup_authored += [index] * len(pieces)
                    out.extend(pieces)
                    _logger.info(
                        "%s split wire %r into %d at %s of its length so port "
                        "%r sits at %.6g exactly",
                        type(self).__name__,
                        w.name,
                        len(pieces),
                        ", ".join(f"{c:.6g}" for c in cuts),
                        port,
                        at,
                    )
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
