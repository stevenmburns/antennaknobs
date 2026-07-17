"""Import a NEC2 card deck (``.nec``) as antennaknobs wire geometry.

The read-side twin of :mod:`antennaknobs.nec_export`: where ``export_nec``
emits a card deck for other NEC tools, ``parse_nec`` consumes one — so a deck
written by xnec2c, 4nec2, EZNEC, or found in an antenna handbook can be loaded
as a data-driven design (see ``read_nec``).

Geometry card semantics (GW/GA/GH/GM/GX/GR/GS) are transcribed from the
``nec2c`` 1.3.1 sources (``geometry.c``: ``wire``/``arc``/``helix``/``move``/
``reflc``) so transforms replicate what a NEC engine would build, including
the quirks: ``GM`` repetitions compound (each copy transforms the previous
copy), ``GX`` doubles the tag increment after every reflection plane, tag 0
never increments, and ``GS`` supports xnec2c's tag-range extension. Only the
*wire* model is translated; patches (SP/SM) and tapered wires (GC) raise.

A NEC deck also carries run configuration that antennaknobs manages itself —
ground (GN/GD), loading (LD), networks and transmission lines (TL/NT), sweep
and output requests (FR/RP/NE/NH/XQ/...). By default those cards are recorded
in ``NecDeck.ignored`` (and FR in ``NecDeck.freq_mhz``) rather than
translated, so a caller can tell the user what the deck asked for that the
app decides differently.

With ``network=True``, the LD/TL/NT cards that antennaknobs' port-network
system can express exactly are translated instead of ignored (issue #385):
lumped LD loads become ``Load`` branches on named 1-segment wires, LD 5 wire
conductivity surfaces as ``NecDeck.conductivity`` (feed it to ``WireSpec``),
TL cards become ``TL`` branches (crossed lines, zero-length = port
separation, conductance-only end shunts), and an NT card with an all-real Y
matrix becomes its exact resistive pi (``TwoPort`` + ``Shunt``). What cannot
be expressed exactly — frequency-independent reactance (LD 4 with X≠0,
susceptance in TL/NT admittances), distributed RLC (LD 2/3), range-limited
conductivity — stays in ``ignored`` with a per-card reason in
``ignored_detail``. ``wire_tuples()`` then emits *named* wires (no legacy
``ex`` markers) and ``network()`` returns the matching ``Network``, ready to
return from ``build_wires`` / ``build_network``.

Excitation: only voltage sources (EX type 0 and 5) can drive an antenna in
antennaknobs; plane-wave and current-source excitations raise. The engine
feeds a wire tuple at its middle segment, so ``NecDeck.wire_tuples`` splits a
wire whose EX segment is off-centre into colinear pieces that preserve the
deck's exact segment boundaries and put the feed on its own 1-segment wire.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property

from . import network as _net
from .design_data import read_data

__all__ = [
    "NecDeck",
    "NecFeed",
    "NecLoad",
    "NecNT",
    "NecTL",
    "NecWire",
    "parse_nec",
    "read_nec",
]

_DEG = math.pi / 180.0

# Cards that configure a NEC *run* rather than the wire list. antennaknobs has
# its own engine settings for these concerns (ground, loading, feedlines,
# sweeps, pattern output), so they are recorded, not translated.
_IGNORED_CARDS = {
    "GN": "ground parameters",
    "GD": "additional ground medium",
    "LD": "loading",
    "TL": "transmission line",
    "NT": "two-port network",
    "RP": "radiation-pattern request",
    "NE": "near-E-field request",
    "NH": "near-H-field request",
    "XQ": "execute request",
    "PT": "current print control",
    "PQ": "charge print control",
    "KH": "interaction limit",
    "CP": "coupling request",
    "PL": "plot request",
    "WG": "NGF write request",
    "ZO": "impedance normalisation (xnec2c)",
}

_UNSUPPORTED_CARDS = {
    "GC": "a tapered wire (GW with zero radius + GC continuation)",
    "SP": "a surface patch (SP)",
    "SM": "a multiple-patch surface (SM)",
    "GF": "a numerical Green's function file (GF)",
}


@dataclass(frozen=True)
class NecWire:
    """One straight wire after all geometry transforms: NEC's GW columns."""

    tag: int
    n_seg: int
    p1: tuple[float, float, float]
    p2: tuple[float, float, float]
    radius: float


@dataclass(frozen=True)
class NecFeed:
    """A voltage-source EX card resolved onto a wire: 1-based segment ``seg``
    of ``deck.wires[wire]`` is driven with ``voltage``."""

    wire: int
    seg: int
    voltage: complex


@dataclass(frozen=True)
class NecLoad:
    """One translated lumped LD element (``network=True``): an R/L/C in
    series with 1-based segment ``seg`` of ``deck.wires[wire]`` — exactly
    NEC's per-segment ld_card semantics, so a multi-segment LD range appears
    as one ``NecLoad`` per segment. ``parallel`` distinguishes LD type 1
    (parallel RLC, the trap idiom) from type 0/4 (series). Legs the card
    left at zero are ``None`` (omitted), matching ``network.Load``."""

    wire: int
    seg: int
    r: float | None
    l: float | None  # noqa: E741 — matches network.Load's field name
    c: float | None
    parallel: bool


@dataclass(frozen=True)
class NecTL:
    """One translated TL card (``network=True``), resolved onto its two
    segments. ``z0`` is positive — a negative card z0 (NEC's crossed line)
    becomes ``transposed=True``, matching the ``network.TL`` convention.
    ``length`` is resolved: the card's length, or the straight-line distance
    between the segment midpoints when the card says 0 (NEC semantics).
    ``shunt_r_*`` carry conductance-only end admittances as 1/G resistances
    (a card with susceptance in an end admittance is not translated)."""

    wire_a: int
    seg_a: int
    wire_b: int
    seg_b: int
    z0: float
    length: float
    transposed: bool
    shunt_r_a: float | None
    shunt_r_b: float | None


@dataclass(frozen=True)
class NecNT:
    """One translated NT card (``network=True``): an all-real Y matrix,
    decomposed into its exact resistive pi — a series resistance between the
    ports (from −Y12) plus a shunt resistance at each port (Y11+Y12,
    Y22+Y12). Real Y-parameters are frequency-independent, so the pi is
    exact at every frequency; an NT with susceptance anywhere is not
    translated (that needs a general YMatrix branch — future work).
    ``None`` legs are absent elements."""

    wire_a: int
    seg_a: int
    wire_b: int
    seg_b: int
    series_r: float | None
    shunt_r_a: float | None
    shunt_r_b: float | None


@dataclass(frozen=True)
class NecDeck:
    """A parsed NEC deck: final wire list, resolved feeds, and the run
    configuration the deck asked for (kept for reporting, not applied)."""

    wires: tuple[NecWire, ...]
    feeds: tuple[NecFeed, ...]
    freq_mhz: tuple[float, float] | None  # FR card sweep range (lo, hi)
    ground: bool  # deck requested a ground plane (GE flag or GN card)
    comments: tuple[str, ...]  # CM card text
    ignored: tuple[str, ...]  # run-config card mnemonics seen but not applied
    # network=True translation results (all empty in the default mode):
    loads: tuple[NecLoad, ...] = ()
    tls: tuple[NecTL, ...] = ()
    nts: tuple[NecNT, ...] = ()
    conductivity: float | None = None  # whole-structure LD 5, S/m
    # Ranged LD 5 (issue #388): (wire index, S/m) for every wire an LD 5
    # card covers in full. Baked into wire_tuples(specs=True) specs.
    wire_conductivity: tuple[tuple[int, float], ...] = ()
    # (mnemonic, reason) per card instance that network mode still could not
    # translate — skipped_note() prefers these over the generic descriptions.
    ignored_detail: tuple[tuple[str, str], ...] = ()
    network_mode: bool = False  # parsed with network=True
    # Deck asked for NEC's extended thin-wire kernel (EK card, #414). Applied
    # by the PyNEC engine (`extended_thin_wire_kernel=True`) so fat-wire
    # decks compare kernel-for-kernel against nec2c; momwire's kernels are
    # its own formulation, so this is reference fidelity, not a momwire knob.
    # Deck-level: True if any EK card other than `EK -1` (off) appears.
    extended_kernel: bool = False

    def dominant_radius(self) -> float:
        """The deck's wire radius, length-weighted where wires differ.

        ``build_wires()`` tuples carry no radius — the engines take one
        radius for the whole antenna via ``build_wire_material()`` — so a
        deck with mixed radii is approximated by the radius that makes up
        the greatest total wire length. Feed this to
        ``WireSpec(radius=...)`` so the import keeps the deck's reactance
        (the engines' 0.5 mm idealization is far off a typical 4-10 mm
        Yagi element).
        """
        length_by_radius: dict[float, float] = {}
        for w in self.wires:
            ln = math.dist(w.p1, w.p2)
            length_by_radius[w.radius] = length_by_radius.get(w.radius, 0.0) + ln
        return max(length_by_radius.items(), key=lambda kv: kv[1])[0]

    def skipped_note(self) -> str | None:
        """One human-readable sentence naming the run configuration the deck
        asked for that the app decides itself: the ``ignored`` cards with
        their descriptions, plus the deck's ground request (which can come
        from the GE flag alone, with no GN card). Deck-backed design stubs
        put this under ``ui_params["notes"]`` so the web UI can tell the
        user why readouts may differ from the deck's published numbers.
        None when the deck carries nothing the app overrides.
        """
        parts = []
        if self.ignored:
            why: dict[str, list[str]] = {}
            for m, reason in self.ignored_detail:
                if reason not in why.setdefault(m, []):
                    why[m].append(reason)

            def describe(m: str) -> str:
                if m in why:
                    return f"{m} ({'; '.join(why[m])})"
                if m in _IGNORED_CARDS:
                    return f"{m} ({_IGNORED_CARDS[m]})"
                return m

            cards = ", ".join(describe(m) for m in self.ignored)
            parts.append(f"deck cards not applied: {cards}")
        if self.ground:
            parts.append("the deck models a ground plane")
        if not parts:
            return None
        body = "; ".join(parts)
        return (
            body[0].upper()
            + body[1:]
            + " — the app's own ground/loading/sweep settings are used instead."
        )

    @cached_property
    def _port_plan(self) -> dict[tuple[int, int], str]:
        """(wire index, 1-based local segment) → port name, for every
        segment the network attaches to (network mode). Feeds claim names
        first — a single feed is ``"feed"``, matching the catalog
        convention — and later attachments to an already-claimed segment
        share its port: an LD on the fed segment becomes a ``Load`` and a
        ``Driven`` on one port (the Group-2 termination branch), a TL
        chain's shared element gets one port per segment however many
        lines land there."""
        plan: dict[tuple[int, int], str] = {}
        single = len(self.feeds) == 1
        for k, f in enumerate(self.feeds, 1):
            key = (f.wire, f.seg)
            if key in plan:
                raise ValueError(
                    f"NEC deck drives segment {f.seg} of wire {f.wire + 1} "
                    f"with more than one EX card"
                )
            plan[key] = "feed" if single else f"feed{k}"
        for k, ld in enumerate(self.loads, 1):
            plan.setdefault((ld.wire, ld.seg), f"load{k}")
        for k, tl in enumerate(self.tls, 1):
            plan.setdefault((tl.wire_a, tl.seg_a), f"tl{k}a")
            plan.setdefault((tl.wire_b, tl.seg_b), f"tl{k}b")
        for k, nt in enumerate(self.nts, 1):
            plan.setdefault((nt.wire_a, nt.seg_a), f"nt{k}a")
            plan.setdefault((nt.wire_b, nt.seg_b), f"nt{k}b")
        return plan

    @cached_property
    def _junction_cuts(self) -> dict[int, frozenset[int]]:
        """wire index → interior segment boundaries (1..n_seg−1) where some
        OTHER wire has a segment endpoint.

        NEC connects *segments* whose ends coincide — the grouping into GW
        wires is irrelevant to it — so a deck may run one long wire straight
        through another and rely on the crossing carrying current (the W8IO
        whip's matching straps cross the whip axis mid-wire). antennaknobs'
        engines junction wires at wire ENDS only, so ``wire_tuples()`` must
        shatter wires at these boundaries to reproduce the deck's electrical
        graph. The split is lossless: same segments, same boundaries, and
        the KCL junction at the shared node is exactly NEC's connection.
        """
        eps = 1e-9

        def key(p):
            return tuple(round(c / eps) for c in p)

        def boundary(w, k):
            # Must match wire_tuples' point() bitwise so the shattered
            # pieces land exactly on the detected nodes.
            t = k / w.n_seg
            return tuple(a + (b - a) * t for a, b in zip(w.p1, w.p2))

        owners: dict[tuple, set[int]] = {}
        for i, w in enumerate(self.wires):
            for k in range(w.n_seg + 1):
                owners.setdefault(key(boundary(w, k)), set()).add(i)
        cuts: dict[int, frozenset[int]] = {}
        for i, w in enumerate(self.wires):
            shared = {
                k for k in range(1, w.n_seg) if len(owners[key(boundary(w, k))]) > 1
            }
            if shared:
                cuts[i] = frozenset(shared)
        return cuts

    def wire_tuples(self, specs: bool = False):
        """The deck as ``build_wires()`` tuples.

        Default mode: ``(p1, p2, n_seg, ex)`` with the deck's EX voltages as
        legacy ``ex`` markers. Network mode (``network=True``): every segment
        the network attaches to — feeds, loads, TL/NT connections — becomes a
        *named* wire instead, ``(p1, p2, n_seg, None, name)``, and no tuple
        carries ``ex`` (the drive comes from ``network()``'s ``Driven``
        sources).

        ``specs=True`` (issue #388) emits ``Wire`` named tuples instead,
        each carrying a per-wire ``WireSpec`` with the deck wire's OWN
        radius — no ``dominant_radius()`` compromise — and its effective
        conductivity (a ranged LD 5 over the whole wire, else the deck's
        whole-structure LD 5). PyNEC honors both per wire; momwire honors
        both too since momwire#147 (complete in momwire 0.13.0 across all
        four solver bases, the H-matrix family included). With
        ``specs=True`` a ``build_wire_material()`` fallback is unnecessary
        (every wire carries its spec) — though a design may still define
        one for the weight readout of spec-less wires it adds itself.

        Wires are split into colinear pieces on the deck's exact segment
        boundaries in two situations: a marked (fed / port) segment that is
        not the wire's middle segment gets isolated on its own 1-segment
        wire so the delta gap lands exactly where the deck put it, and any
        boundary another wire touches is cut so the crossing becomes a
        wire-end junction (``_junction_cuts`` — NEC connects segment ends
        regardless of wire grouping; the engines junction wire ends only).
        Same geometry, same segmentation, same electrical graph as a NEC
        run of the original deck. A wire with no cuts whose only mark sits
        at the middle segment of an odd count stays whole.
        """
        if not self.feeds:
            raise ValueError(
                "NEC deck has no voltage-source EX card — nothing drives the antenna"
            )
        # (wire index) → {segment: (ex voltage | None, port name | None)}
        marks: dict[int, dict[int, tuple[complex | None, str | None]]] = {}
        if self.network_mode:
            for (wi, seg), pname in self._port_plan.items():
                marks.setdefault(wi, {})[seg] = (None, pname)
        else:
            for f in self.feeds:
                per = marks.setdefault(f.wire, {})
                if f.seg in per:
                    raise ValueError(
                        f"NEC deck drives segment {f.seg} of wire {f.wire + 1} "
                        f"with more than one EX card"
                    )
                per[f.seg] = (f.voltage, None)

        sigma_by_wire = dict(self.wire_conductivity)

        def spec_for(i, w):
            """Per-wire spec (issue #388): the deck wire's own radius, with
            its effective conductivity baked in — a ranged LD 5 on this wire
            wins over the whole-structure one. Baking is required: engines
            treat an explicit spec as complete (no field-level fallback to
            build_wire_material), so leaving conductivity None would turn a
            copper deck into PEC wire by wire."""
            if not specs:
                return None
            return _net.WireSpec(
                radius=w.radius,
                conductivity=sigma_by_wire.get(i, self.conductivity),
            )

        tups = []

        def emit(p0, p1, n, ex, pname=None, spec=None):
            if spec is not None:
                tups.append(_net.Wire(p0, p1, n, ex, pname, spec))
            elif pname:
                tups.append((p0, p1, n, ex, pname))
            else:
                tups.append((p0, p1, n, ex))

        for i, w in enumerate(self.wires):
            per = marks.get(i, {})
            cutset = self._junction_cuts.get(i, frozenset())
            n = w.n_seg
            spec = spec_for(i, w)
            if not per and not cutset:
                emit(w.p1, w.p2, n, None, spec=spec)
                continue
            if not cutset and len(per) == 1 and n % 2 == 1:
                (seg, (ex, pname)) = next(iter(per.items()))
                if seg == (n + 1) // 2:
                    # Marked at the wire's middle segment — the engine's
                    # native attachment position; keep the wire whole.
                    emit(w.p1, w.p2, n, ex, pname, spec)
                    continue

            def point(k, w=w, n=n):
                """Endpoint after ``k`` of the wire's ``n`` segments. The same
                expression for adjoining pieces yields bitwise-equal points,
                which is how wires are recognised as connected."""
                t = k / n
                return tuple(a + (b - a) * t for a, b in zip(w.p1, w.p2))

            # Cut at every junction boundary, and around every marked
            # segment so it sits alone on a 1-segment piece.
            bounds = set(cutset)
            for seg in per:
                bounds.update((seg - 1, seg))
            bounds -= {0, n}
            prev = 0
            for b in [*sorted(bounds), n]:
                count = b - prev
                mark = per.get(b) if count == 1 else None
                if mark is not None:
                    ex, pname = mark
                    emit(point(prev), point(b), 1, ex, pname, spec)
                else:
                    emit(point(prev), point(b), count, None, spec=spec)
                prev = b
        return tups

    def network(self):
        """The deck's translated LD/TL/NT cards as a ``network.Network``,
        with ports on the named wires ``wire_tuples()`` emits and one
        ``Driven`` per EX card — ready to return from ``build_network()``.
        A deck with no translatable cards still gets its ``Driven`` feeds,
        so a network-mode stub can always define ``build_network``. Only
        available when the deck was parsed with ``network=True``."""
        if not self.network_mode:
            raise ValueError(
                "deck was not parsed for network translation — call "
                "parse_nec/read_nec with network=True"
            )
        plan = self._port_plan
        ports = {pname: _net.PortOnWire(pname) for pname in plan.values()}
        branches: list = []
        for ld in self.loads:
            branches.append(
                _net.Load(
                    port=plan[(ld.wire, ld.seg)],
                    r=ld.r,
                    l=ld.l,
                    c=ld.c,
                    parallel=ld.parallel,
                )
            )
        for tl in self.tls:
            a = plan[(tl.wire_a, tl.seg_a)]
            b = plan[(tl.wire_b, tl.seg_b)]
            branches.append(
                _net.TL(a=a, b=b, z0=tl.z0, length=tl.length, transposed=tl.transposed)
            )
            if tl.shunt_r_a is not None:
                branches.append(_net.Shunt(port=a, r=tl.shunt_r_a))
            if tl.shunt_r_b is not None:
                branches.append(_net.Shunt(port=b, r=tl.shunt_r_b))
        for nt in self.nts:
            a = plan[(nt.wire_a, nt.seg_a)]
            b = plan[(nt.wire_b, nt.seg_b)]
            if nt.series_r is not None:
                branches.append(_net.TwoPort(a=a, b=b, r=nt.series_r))
            if nt.shunt_r_a is not None:
                branches.append(_net.Shunt(port=a, r=nt.shunt_r_a))
            if nt.shunt_r_b is not None:
                branches.append(_net.Shunt(port=b, r=nt.shunt_r_b))
        sources = [
            _net.Driven(port=plan[(f.wire, f.seg)], voltage=f.voltage)
            for f in self.feeds
        ]
        return _net.Network(ports=ports, branches=branches, sources=sources)


def read_nec(builder, name: str, *, network: bool = False) -> NecDeck:
    """``read_data`` followed by ``parse_nec`` — load a NEC card deck that
    ships next to ``builder``'s design, with the same folder confinement as
    ``read_json``. ``network=True`` translates the deck's expressible
    LD/TL/NT cards into ``deck.network()`` (see the module docstring)."""
    return parse_nec(read_data(builder, name), name=name, network=network)


def _float(token: str, where: str) -> float:
    try:
        return float(token)
    except ValueError:
        # Old Fortran decks write D exponents ("1.0D+03").
        try:
            return float(token.upper().replace("D", "E"))
        except ValueError:
            raise ValueError(f"{where}: bad number {token!r}") from None


# ---------------------------------------------------------------------------
# SY symbolic variables (4nec2 extension, issue #417)
# ---------------------------------------------------------------------------
# 4nec2's expression language is BASIC-flavored: `^` is power, trig works in
# DEGREES (the corpus is full of `sin(360*x)`), `sqr` is square root, `atn`
# arctangent (returning degrees), `int` truncates. Names are matched
# case-insensitively. Evaluation is a whitelisted ast walk — no eval().
_SY_FUNCS = {
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "atn": lambda x: math.degrees(math.atan(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "sqr": math.sqrt,
    "sqrt": math.sqrt,
    "abs": abs,
    "int": lambda x: float(int(x)),
    "log": math.log,
    "exp": math.exp,
}
_SY_CONSTANTS = {
    "pi": math.pi,
    # 4nec2 predefined unit-scale symbols (`SY r = 1.5 * mm`): factors to
    # metres. A deck's own SY definition of the same name wins (the symbol
    # table is consulted before these constants).
    "mm": 1e-3,
    "cm": 1e-2,
    "dm": 0.1,
    "m": 1.0,
    "in": 0.0254,
    "ft": 0.3048,
    # electrical component suffixes (`SY C=36.6pF`, `SY L=0.5uH`)
    "pf": 1e-12,
    "nf": 1e-9,
    "uf": 1e-6,
    "nh": 1e-9,
    "uh": 1e-6,
    "mh": 1e-3,
}


_SY_IDENT = None


def _eval_sy_expr(expr: str, syms: dict, where: str) -> float:
    """Evaluate one 4nec2 expression against the symbol table."""
    import ast
    import re

    global _SY_IDENT
    if _SY_IDENT is None:
        # An identifier not glued to a preceding digit/dot (so the exponent
        # in `1e3` / `.5E-2` is never mistaken for a symbol).
        _SY_IDENT = re.compile(r"(?<![\w.])[A-Za-z_]\w*")

    # Mangle every identifier before ast.parse: 4nec2 names are
    # case-insensitive and may be Python keywords (`lambda` is the most
    # idiomatic antenna symbol there is), which would be a SyntaxError.
    src = expr.strip().replace("^", "**")
    # Juxtaposed units — `135 ft`, `1.5 mm`, `61ft` — are implicit
    # multiplication, but ONLY for the predefined unit names (anything
    # wider would turn typos into silent products). Glued forms are safe
    # from exponent confusion: `1e3` stays a number because `e` is not a
    # unit name.
    src = re.sub(
        r"([0-9.])\s*(mm|cm|dm|mh|nh|uh|pf|nf|uf|in|ft|m)\b",
        r"\1*\2",
        src,
        flags=re.IGNORECASE,
    )
    src = _SY_IDENT.sub(lambda m: f"_v_{m.group(0).lower()}", src)
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError:
        raise ValueError(f"{where}: SY expression {expr!r} is not valid") from None

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = walk(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)
        ):
            a, b = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if isinstance(node.op, ast.Div):
                return a / b
            if isinstance(node.op, ast.Mod):
                return math.fmod(a, b)
            return a**b
        if isinstance(node, ast.Name):
            key = node.id.removeprefix("_v_")
            if key in syms:
                return syms[key]
            if key in _SY_CONSTANTS:
                return _SY_CONSTANTS[key]
            raise ValueError(f"{where}: undefined symbol {key!r}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and not node.keywords
            and len(node.args) == 1
        ):
            fn = _SY_FUNCS.get(node.func.id.removeprefix("_v_"))
            if fn is not None:
                return float(fn(walk(node.args[0])))
            raise ValueError(
                f"{where}: unknown function "
                f"{node.func.id.removeprefix('_v_')!r} in SY expression"
            )
        raise ValueError(f"{where}: SY expression {expr!r} is not valid")

    return float(walk(tree))


def _define_sy(rest: str, syms: dict, where: str) -> None:
    """Apply one SY card: ``name=expr[, name=expr...]['comment]``."""
    body = rest.split("'", 1)[0].strip()  # 4nec2 trailing comment
    if not body:
        raise ValueError(f"{where}: SY card without an assignment")
    # Split on top-level commas only (function args never contain commas in
    # the 4nec2 single-argument vocabulary, but stay paren-aware anyway).
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(body[start:i])
            start = i + 1
    parts.append(body[start:])
    for part in parts:
        if "=" not in part:
            raise ValueError(f"{where}: SY assignment {part.strip()!r} has no '='")
        name, expr = part.split("=", 1)
        name = name.strip()
        if not name.isidentifier():
            raise ValueError(f"{where}: SY name {name!r} is not a valid symbol")
        syms[name.lower()] = _eval_sy_expr(expr, syms, where)


def _value(token: str, where: str, syms: dict | None) -> float:
    """A card field: a plain number, or (when the deck defined SY symbols
    or the token contains a letter) a 4nec2 expression."""
    try:
        return _float(token, where)
    except ValueError:
        if syms is not None and any(c.isalpha() or c in "()*/+-^" for c in token):
            return _eval_sy_expr(token, syms, where)
        raise


class _Card:
    """One card line: mnemonic + zero-padded numeric field access."""

    def __init__(
        self,
        mnemonic: str,
        tokens: list[str],
        where: str,
        syms: dict | None = None,
    ):
        self.mnemonic = mnemonic
        self.where = where
        self.vals = [_value(t, where, syms) for t in tokens]

    def f(self, k: int) -> float:
        return self.vals[k] if k < len(self.vals) else 0.0

    def i(self, k: int) -> int:
        return int(round(self.f(k)))

    def error(self, msg: str) -> ValueError:
        return ValueError(f"{self.where}: {self.mnemonic} card: {msg}")


# Internal mutable wire: [tag, n_seg, [x,y,z], [x,y,z], radius].


def _gw(card, wires):
    tag, n_seg = card.i(0), card.i(1)
    if n_seg < 1:
        raise card.error(f"segment count must be >= 1, got {n_seg}")
    radius = card.f(8)
    if radius <= 0.0:
        raise card.error(
            "zero wire radius announces "
            + _UNSUPPORTED_CARDS["GC"]
            + ", which antennaknobs cannot model"
        )
    p1 = [card.f(2), card.f(3), card.f(4)]
    p2 = [card.f(5), card.f(6), card.f(7)]
    wires.append([tag, n_seg, p1, p2, radius])


def _ga(card, wires):
    """Wire arc in the XZ plane (nec2c ``arc``): ``n_seg`` 1-segment chords."""
    tag, n_seg = card.i(0), card.i(1)
    rada, ang1, ang2, radius = card.f(2), card.f(3), card.f(4), card.f(5)
    if n_seg < 1:
        raise card.error(f"segment count must be >= 1, got {n_seg}")
    if radius <= 0.0:
        raise card.error("wire radius must be > 0")
    if abs(ang2 - ang1) >= 360.00001:
        raise card.error("arc angle exceeds 360 degrees")
    ang = ang1 * _DEG
    dang = (ang2 - ang1) * _DEG / n_seg
    x1, z1 = rada * math.cos(ang), rada * math.sin(ang)
    for _ in range(n_seg):
        ang += dang
        x2, z2 = rada * math.cos(ang), rada * math.sin(ang)
        wires.append([tag, 1, [x1, 0.0, z1], [x2, 0.0, z2], radius])
        x1, z1 = x2, z2


def _gh(card, wires):
    """Helix/spiral about +Z (nec2c ``helix``): ``n_seg`` 1-segment chords."""
    tag, n_seg = card.i(0), card.i(1)
    s, hl = card.f(2), card.f(3)
    a1, b1, a2, b2 = card.f(4), card.f(5), card.f(6), card.f(7)
    radius = card.f(8)
    if n_seg < 1:
        raise card.error(f"segment count must be >= 1, got {n_seg}")
    if radius <= 0.0:
        raise card.error("wire radius must be > 0")
    if s == 0.0 or hl == 0.0:
        raise card.error("turn spacing and helix length must be nonzero")
    zinc = abs(hl / n_seg)
    if a2 == a1 and b1 == 0.0:
        b1 = a1
    if a2 != a1 and b2 == 0.0:
        b2 = a2

    def point(z):
        if a2 == a1:
            a, b = a1, b1
        else:
            a = a1 + (a2 - a1) * z / abs(hl)
            b = b1 + (b2 - b1) * z / abs(hl)
        x = a * math.cos(2.0 * math.pi * z / s)
        y = b * math.sin(2.0 * math.pi * z / s)
        # hl < 0 winds the helix left-handed (nec2c swaps x and y).
        return [y, x, z] if hl < 0.0 else [x, y, z]

    z1 = 0.0
    for _ in range(n_seg):
        z2 = z1 + zinc
        wires.append([tag, 1, point(z1), point(z2), radius])
        z1 = z2


def _first_wire_with_tag(wires, tag, card):
    if tag <= 0:
        return 0
    for i, w in enumerate(wires):
        if w[0] == tag:
            return i
    raise card.error(f"no wire has tag {tag}")


def _gm(card, wires):
    """Move / replicate (nec2c ``move``): rotate about X then Y then Z (deg),
    translate, optionally repeat cumulatively with a tag increment."""
    itgi, nrpt = card.i(0), card.i(1)
    rox, roy, roz = card.f(2) * _DEG, card.f(3) * _DEG, card.f(4) * _DEG
    xs, ys, zs = card.f(5), card.f(6), card.f(7)
    its = int(card.f(8) + 0.5)  # nec2c reads ITS as a float and rounds

    sps, cps = math.sin(rox), math.cos(rox)
    sth, cth = math.sin(roy), math.cos(roy)
    sph, cph = math.sin(roz), math.cos(roz)
    m = (
        (cph * cth, cph * sth * sps - sph * cps, cph * sth * cps + sph * sps),
        (sph * cth, sph * sth * sps + cph * cps, sph * sth * cps - cph * sps),
        (-sth, cth * sps, cth * cps),
    )

    def xf(p):
        return [
            p[0] * m[0][0] + p[1] * m[0][1] + p[2] * m[0][2] + xs,
            p[0] * m[1][0] + p[1] * m[1][1] + p[2] * m[1][2] + ys,
            p[0] * m[2][0] + p[1] * m[2][1] + p[2] * m[2][2] + zs,
        ]

    i1 = _first_wire_with_tag(wires, its, card)
    if nrpt == 0:
        for w in wires[i1:]:
            w[2], w[3] = xf(w[2]), xf(w[3])
        return
    block = wires[i1:]
    for _ in range(nrpt):
        # Each repetition transforms the *previous* copy, so rotations and
        # translations compound — that is how one loop side GM-replicates
        # into a square, or one bay into a stack.
        block = [
            [tag + itgi if tag != 0 else 0, ns, xf(p1), xf(p2), rad]
            for tag, ns, p1, p2, rad in block
        ]
        wires.extend(block)


def _reflect(card, wires, axis, iti, plane_name):
    new = []
    for tag, ns, p1, p2, rad in wires:
        e1, e2 = p1[axis], p2[axis]
        if abs(e1) + abs(e2) <= 1.0e-5 or e1 * e2 < -1.0e-6:
            raise card.error(
                f"a wire lies in or crosses the {plane_name} symmetry plane"
            )
        q1, q2 = list(p1), list(p2)
        q1[axis], q2[axis] = -e1, -e2
        new.append([tag + iti if tag != 0 else 0, ns, q1, q2, rad])
    wires.extend(new)


def _gx(card, wires):
    """Reflect in the Z=0, then Y=0, then X=0 planes (nec2c ``reflc``). The
    tag increment doubles after each reflection so every image stays unique."""
    iti = card.i(0)
    code = card.i(1)
    ix, iy, iz = (code // 100) % 10, (code // 10) % 10, code % 10
    for axis, flag, plane in ((2, iz, "Z=0"), (1, iy, "Y=0"), (0, ix, "X=0")):
        if flag:
            _reflect(card, wires, axis, iti, plane)
            iti *= 2


def _gr(card, wires):
    """Rotate about Z to form a cylindrical structure of ``nop`` copies."""
    itg, nop = card.i(0), card.i(1)
    if nop < 1:
        raise card.error(f"structure count must be >= 1, got {nop}")
    sam = 2.0 * math.pi / nop
    cs, ss = math.cos(sam), math.sin(sam)
    block = wires[:]
    for _ in range(nop - 1):
        block = [
            [
                tag + itg if tag != 0 else 0,
                ns,
                [p1[0] * cs - p1[1] * ss, p1[0] * ss + p1[1] * cs, p1[2]],
                [p2[0] * cs - p2[1] * ss, p2[0] * ss + p2[1] * cs, p2[2]],
                rad,
            ]
            for tag, ns, p1, p2, rad in block
        ]
        wires.extend(block)


def _gs(card, wires):
    """Scale all dimensions; xnec2c extension: nonzero I1..I2 scales only
    wires whose tag falls in that range."""
    lo, hi, factor = card.i(0), card.i(1), card.f(2)
    if factor <= 0.0:
        raise card.error(f"scale factor must be > 0, got {factor}")
    ranged = lo > 0 and hi >= lo
    for w in wires:
        if ranged and not (lo <= w[0] <= hi):
            continue
        w[2] = [c * factor for c in w[2]]
        w[3] = [c * factor for c in w[3]]
        w[4] *= factor


def _locate_segment(wires, tag, seg, card):
    """Resolve NEC's (tag, segment) addressing to (wire index, 1-based local
    segment): the ``seg``-th segment among wires with that tag, or the
    absolute ``seg``-th segment when ``tag`` is 0."""
    if seg <= 0:
        seg = 1
    acc = 0
    for i, w in enumerate(wires):
        if tag != 0 and w[0] != tag:
            continue
        if acc + w[1] >= seg:
            return i, seg - acc
        acc += w[1]
    if tag != 0 and acc == 0:
        raise card.error(f"no wire has tag {tag}")
    raise card.error(
        f"segment {seg} is out of range — "
        + (f"tag {tag} has" if tag != 0 else "the deck has")
        + f" only {acc} segments"
    )


# How many segments an LD 0/1/4 range may cover before the importer refuses
# to expand it into per-segment Load branches: each expanded segment becomes
# its own named 1-segment wire + MoM port + MNA row, so a wide range (which
# usually means "the whole element" — really distributed loading) would
# shred the mesh for no fidelity gain.
_LD_EXPAND_MAX = 8


def _seg_mid(w, seg: int):
    """Midpoint of 1-based local segment ``seg`` of a parse-time wire
    ``[tag, n_seg, p1, p2, radius]`` — NEC's connection point for a
    zero-length TL's straight-line-distance rule."""
    t = (seg - 0.5) / w[1]
    return [a + (b - a) * t for a, b in zip(w[2], w[3])]


def _segment_range(wires, tag, sf, st, card):
    """All (wire index, local segment) pairs an LD card's range covers:
    NEC's tag/range addressing — tag 0 + range 0 is the whole structure,
    tag 0 + a range is absolute segment numbers, a tag with range 0 is
    every segment of that tag, and a tag with a range is local segment
    numbers within the tag."""
    if tag == 0 and sf == 0:
        return [(i, s) for i, w in enumerate(wires) for s in range(1, w[1] + 1)]
    if sf == 0:
        pairs = [
            (i, s)
            for i, w in enumerate(wires)
            if w[0] == tag
            for s in range(1, w[1] + 1)
        ]
        if not pairs:
            raise card.error(f"no wire has tag {tag}")
        return pairs
    st = max(st, sf)
    return [_locate_segment(wires, tag, s, card) for s in range(sf, st + 1)]


def _translate_network_cards(wires, lds_raw, tls_raw, nts_raw):
    """Turn the collected LD/TL/NT cards into NecLoad/NecTL/NecNT records,
    plus (mnemonic, reason) detail for every card instance that stays
    unmodelled. TL/NT resolve first so loads can refuse to co-locate with a
    connection point — our ``Load`` is the port's termination branch, which
    would sit in *parallel* with a TL/NT attached to the same port, not in
    series inside the segment the way NEC composes them."""
    detail: list[tuple[str, str]] = []
    skipped: set[str] = set()

    def skip(mnemonic: str, reason: str) -> None:
        skipped.add(mnemonic)
        if (mnemonic, reason) not in detail:
            detail.append((mnemonic, reason))

    tls: list[NecTL] = []
    for card in tls_raw:
        wa, sa = _locate_segment(wires, card.i(0), card.i(1), card)
        wb, sb = _locate_segment(wires, card.i(2), card.i(3), card)
        if card.f(7) != 0.0 or card.f(9) != 0.0:
            skip(
                "TL",
                "an end admittance has susceptance — NEC's constant B is "
                "frequency-independent, which R/L/C cannot express",
            )
            continue
        z0 = card.f(4)
        if z0 == 0.0:
            raise card.error("characteristic impedance must be nonzero")
        length = card.f(5)
        if length == 0.0:
            # NEC: zero length means the straight-line distance between
            # the connection points.
            length = math.dist(_seg_mid(wires[wa], sa), _seg_mid(wires[wb], sb))
        ga, gb = card.f(6), card.f(8)
        tls.append(
            NecTL(
                wire_a=wa,
                seg_a=sa,
                wire_b=wb,
                seg_b=sb,
                z0=abs(z0),
                length=length,
                transposed=z0 < 0.0,
                shunt_r_a=1.0 / ga if ga else None,
                shunt_r_b=1.0 / gb if gb else None,
            )
        )

    nts: list[NecNT] = []
    for card in nts_raw:
        wa, sa = _locate_segment(wires, card.i(0), card.i(1), card)
        wb, sb = _locate_segment(wires, card.i(2), card.i(3), card)
        if any(card.f(k) != 0.0 for k in (5, 7, 9)):
            skip(
                "NT",
                "Y-parameters have susceptance — needs a general Y-matrix "
                "branch, which only a real (resistive) Y avoids",
            )
            continue
        y11, y12, y22 = card.f(4), card.f(6), card.f(8)
        if y11 == y12 == y22 == 0.0:
            skip("NT", "all-zero Y-parameters")
            continue
        # Exact resistive pi: series −Y12 between the ports, shunts
        # Y11+Y12 / Y22+Y12 at each. Real Y is frequency-independent, so
        # this holds at every frequency.
        ys, ya, yb = -y12, y11 + y12, y22 + y12
        nts.append(
            NecNT(
                wire_a=wa,
                seg_a=sa,
                wire_b=wb,
                seg_b=sb,
                series_r=1.0 / ys if ys else None,
                shunt_r_a=1.0 / ya if ya else None,
                shunt_r_b=1.0 / yb if yb else None,
            )
        )

    connected = {(t.wire_a, t.seg_a) for t in tls} | {(t.wire_b, t.seg_b) for t in tls}
    connected |= {(t.wire_a, t.seg_a) for t in nts} | {(t.wire_b, t.seg_b) for t in nts}

    loads: list[NecLoad] = []
    loaded: set[tuple[int, int]] = set()
    conductivity: float | None = None
    wire_conductivity: dict[int, float] = {}
    for card in lds_raw:
        ldtyp = card.i(0)
        tag, sf, st = card.i(1), card.i(2), card.i(3)
        if ldtyp in (0, 1, 4):
            if ldtyp == 4 and card.f(5) != 0.0:
                skip(
                    "LD",
                    "type 4 fixed reactance is frequency-independent — "
                    "not representable with R/L/C",
                )
                continue
            pairs = _segment_range(wires, tag, sf, st, card)
            if len(pairs) > _LD_EXPAND_MAX:
                skip(
                    "LD",
                    f"range spans {len(pairs)} segments — the importer "
                    f"expands at most {_LD_EXPAND_MAX} into per-segment loads",
                )
                continue
            r = card.f(4) or None
            le = None if ldtyp == 4 else (card.f(5) or None)
            c = None if ldtyp == 4 else (card.f(6) or None)
            if r is None and le is None and c is None:
                continue  # zero-valued load — a no-op
            for pair in pairs:
                if pair in connected:
                    skip(
                        "LD",
                        "load on a segment with a TL/NT connection — the "
                        "series-inside-the-segment composition is not modelled",
                    )
                    continue
                if pair in loaded:
                    skip("LD", "a second load on one segment is not merged")
                    continue
                loaded.add(pair)
                loads.append(NecLoad(pair[0], pair[1], r, le, c, ldtyp == 1))
        elif ldtyp in (2, 3):
            skip("LD", f"type {ldtyp} distributed per-metre loading is not translated")
        elif ldtyp == 5:
            if tag == 0 and sf == 0:
                conductivity = card.f(4)
            else:
                # Ranged conductivity (issue #388): whole wires can carry
                # their own WireSpec conductivity, so a range that covers
                # each touched wire in full translates per wire (NEC's
                # last-card-wins per segment becomes last-wins per wire).
                pairs = _segment_range(wires, tag, sf, st, card)
                by_wire: dict[int, set[int]] = {}
                for wi, s in pairs:
                    by_wire.setdefault(wi, set()).add(s)
                if all(
                    segs == set(range(1, wires[wi][1] + 1))
                    for wi, segs in by_wire.items()
                ):
                    for wi in by_wire:
                        wire_conductivity[wi] = card.f(4)
                else:
                    skip(
                        "LD",
                        "type 5 conductivity on a partial-wire segment "
                        "range — per-wire specs cover whole wires only",
                    )
        else:
            skip("LD", f"type {ldtyp} is not recognised")

    return (
        tuple(loads),
        tuple(tls),
        tuple(nts),
        conductivity,
        tuple(sorted(wire_conductivity.items())),
        detail,
        skipped,
    )


def parse_nec(text: str, *, name: str = "NEC deck", network: bool = False) -> NecDeck:
    """Parse the text of a NEC2 card deck into a :class:`NecDeck`.

    ``network=True`` additionally translates the deck's expressible LD/TL/NT
    cards into ``deck.network()`` branches instead of recording them in
    ``ignored`` — see the module docstring for exactly what translates.

    Raises ``ValueError`` (with ``name`` and the line number) on cards that
    are malformed or describe things antennaknobs cannot model — patches,
    tapered wires, plane-wave or current-source excitation.
    """
    wires: list[list] = []
    comments: list[str] = []
    ignored: set[str] = set()
    feeds_raw: list[tuple[int, int, complex, str]] = []
    lds_raw: list[_Card] = []
    tls_raw: list[_Card] = []
    nts_raw: list[_Card] = []
    freq_mhz: tuple[float, float] | None = None
    ground = False
    extended_kernel = False
    syms: dict[str, float] = {}  # SY symbol table (#417)
    in_comments = True

    geometry = {
        "GW": _gw,
        "GA": _ga,
        "GH": _gh,
        "GM": _gm,
        "GX": _gx,
        "GR": _gr,
        "GS": _gs,
    }

    for line_no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        where = f"{name}, line {line_no}"
        # Cards are free-format in practice: mnemonic, then numbers separated
        # by spaces and/or commas.
        tokens = stripped.replace(",", " ").split()
        mnemonic = tokens[0].upper()
        if len(mnemonic) != 2 or not mnemonic.isalpha():
            raise ValueError(
                f"{where}: expected a NEC card mnemonic, got {tokens[0]!r}"
            )

        if mnemonic == "CM":
            if not in_comments:
                raise ValueError(f"{where}: CM card after the CE end-of-comments card")
            comments.append(stripped[2:].strip())
            continue
        if mnemonic == "CE":
            in_comments = False
            continue
        in_comments = False

        if mnemonic == "EN":
            break
        if mnemonic == "SY":
            # 4nec2 symbolic variables (#417): bind name=expr (possibly
            # several per card, possibly with a trailing ' comment) into the
            # symbol table consulted by every later card field.
            _define_sy(stripped[2:], syms, where)
            continue
        if mnemonic in _UNSUPPORTED_CARDS:
            raise ValueError(
                f"{where}: this deck uses {_UNSUPPORTED_CARDS[mnemonic]}, "
                f"which antennaknobs cannot model"
            )
        if mnemonic == "GN":
            ground = True
            ignored.add(mnemonic)
            continue
        if network and mnemonic in ("LD", "TL", "NT"):
            # Collected raw and translated after the loop, once the wire
            # list is final (their tag/segment addressing resolves against
            # the transformed geometry, exactly like EX).
            card = _Card(mnemonic, tokens[1:], where, syms)
            if mnemonic == "LD":
                if card.i(0) == -1:
                    lds_raw.clear()  # NEC: nullify all previous loads
                else:
                    lds_raw.append(card)
            elif mnemonic == "TL":
                tls_raw.append(card)
            else:
                if card.i(0) == -1:
                    # NEC: an NT with I1 = -1 cancels all previous
                    # network AND transmission-line data.
                    nts_raw.clear()
                    tls_raw.clear()
                else:
                    nts_raw.append(card)
            continue
        if mnemonic == "EK":
            # Extended thin-wire kernel (#414): honored (via PyNEC), not
            # ignored. `EK -1` switches back to the standard kernel; any
            # other form turns it on. NEC scopes EK to subsequent geometry;
            # decks in the wild use it globally, so one deck-level flag.
            card = _Card(mnemonic, tokens[1:], where, syms)
            extended_kernel = card.i(0) != -1
            continue
        if mnemonic in _IGNORED_CARDS:
            ignored.add(mnemonic)
            continue

        card = _Card(mnemonic, tokens[1:], where, syms)

        if mnemonic in geometry:
            geometry[mnemonic](card, wires)
        elif mnemonic == "GE":
            ground = ground or card.i(0) != 0
        elif mnemonic == "FR":
            if freq_mhz is None:
                nfrq = max(card.i(1), 1)
                start, step = card.f(4), card.f(5)
                if card.i(0) == 0:  # linear sweep
                    end = start + (nfrq - 1) * step
                else:  # multiplicative sweep
                    end = start * step ** (nfrq - 1) if step > 0 else start
                freq_mhz = (min(start, end), max(start, end))
        elif mnemonic == "EX":
            ex_type = card.i(0)
            if ex_type in (1, 2, 3):
                raise ValueError(
                    f"{where}: EX card asks for plane-wave excitation, which "
                    f"is a scattering run, not a driven antenna"
                )
            if ex_type not in (0, 5):
                raise ValueError(
                    f"{where}: EX excitation type {ex_type} is not a voltage "
                    f"source; antennaknobs can only drive voltage feeds"
                )
            feeds_raw.append(
                (card.i(1), card.i(2), complex(card.f(4), card.f(5)), where)
            )
        else:
            raise ValueError(f"{where}: unrecognised NEC card {mnemonic!r}")

    if not wires:
        raise ValueError(f"{name}: deck defines no wires")

    feeds = []
    for tag, seg, voltage, where in feeds_raw:
        card = _Card("EX", [], where)
        idx, local = _locate_segment(wires, tag, seg, card)
        feeds.append(NecFeed(idx, local, voltage))

    loads: tuple[NecLoad, ...] = ()
    tls: tuple[NecTL, ...] = ()
    nts: tuple[NecNT, ...] = ()
    conductivity: float | None = None
    wire_conductivity: tuple[tuple[int, float], ...] = ()
    detail: list[tuple[str, str]] = []
    if network:
        (
            loads,
            tls,
            nts,
            conductivity,
            wire_conductivity,
            detail,
            skipped,
        ) = _translate_network_cards(wires, lds_raw, tls_raw, nts_raw)
        ignored |= skipped

    return NecDeck(
        wires=tuple(
            NecWire(tag, ns, tuple(p1), tuple(p2), rad)
            for tag, ns, p1, p2, rad in wires
        ),
        feeds=tuple(feeds),
        freq_mhz=freq_mhz,
        ground=ground,
        comments=tuple(comments),
        ignored=tuple(sorted(ignored)),
        loads=loads,
        tls=tls,
        nts=nts,
        conductivity=conductivity,
        wire_conductivity=wire_conductivity,
        ignored_detail=tuple(detail),
        network_mode=network,
        extended_kernel=extended_kernel,
    )
