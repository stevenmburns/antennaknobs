"""Emit a SimNEC (``.ssn``) circuit for a design (issues #600 / #604).

SimNEC (AE6TY) is a Java Smith-chart / station tool that embeds NEC2 behind an
in-house MNA solver. Its native circuit file is ``.ssn`` (XML). This module
lets an antennaknobs design — antenna-only, or a differential-only *station*
(antenna + feedline + tuner + transformer chain) — be round-tripped into
SimNEC for cross-validation, without the fiddly UI step of hand-entering
geometry or circuit values.

How it works — the escape-hatch route
-------------------------------------
A SimNEC ``.ssn`` is a list of circuit ``<element>``s. For an antenna model the
canonical shape is three elements — ``LOAD`` / ``NETWORK`` / ``GENERATOR`` —
where the antenna lives inside the ``NETWORK`` element's escape-hatch ``<equ>``
script, expressed in SimNEC's NEC-portal daemon language:

    P1 w1 gnd;                         // the two circuit ports; EX drives P2
    P2 w2 gnd;
    NECUnits meters, meters;
    SommerfeldGround(0.0303, 20);      // (mhos, dielectric) == (sigma, eps_r)
    NECOptions.mhosPerMeter = 0;       // 0 = PEC
    NECOptions.segmentsPerWavelength = 120;
    NEC2                               // NEC cards go between NEC2 and NECEND
    GW 1 ...
    EX 0 1 6 0 1. 0.
    NECEND

We reuse :func:`antennaknobs.nec_export.export_nec` for the geometry, then keep
the ``GW`` / ``FR`` / ``EX`` / lumped-``LD`` cards and translate the rest into
daemon directives: the Generator's ``MHz`` carries the (sweepable) solve
frequency; ``GN`` → the ground call; the deck's segment counts are *advisory
only* — SimNEC re-meshes at ``NECOptions.segmentsPerWavelength``, which is why
that knob is exposed. ``FR`` is left in the deck too: a SimNEC 5.1a1-saved
``.ssn`` carries ``FR`` alongside a live ``G.MHz`` sweep, so it is harmless
(advisory) and matches SimNEC's own output.

Scope
-----
Two export shapes:

**Antenna-only** designs (no ``build_network`` TL/virtual-driver station) —
issue #600, the original scope: the three-element LOAD / NETWORK / GENERATOR
cascade above.

**Differential-only stations** (issue #604, phase 2): designs whose
``build_network`` is a single generator→antenna ladder of transmission lines,
lumped L/C tuner arms, and ideal transformers. Each reducer branch maps to a
SimNEC circuit element in cascade order — ``TL`` → ``SERIES_TLINE``,
``TwoPort``/``Shunt`` L/C legs → ``SERIES_IND`` / ``SERIES_CAP`` /
``SHUNT_IND`` / ``SHUNT_CAP``, ideal ``Transformer`` → ``TRANSFORMER2`` —
and the antenna keeps the NEC-portal NETWORK block, driven at the station's
``PortOnWire`` feed.

**The fundamental limitation — enforced, not papered over.** SimNEC's
``SERIES_TLINE`` is purely differential: there is no common-mode (``zcomm``)
knob. Any design whose physics lives in the common mode — a
``BalancedLine`` with ``zcomm`` (issue #576), a ``FloatingBalun``
(issue #589), the balanced tuners built from them — **cannot be faithfully
represented in SimNEC circuit elements**, and this module raises
:class:`SsnUnsupported` (naming the offending branch) rather than silently
dropping the common mode and emitting a confidently-wrong ``.ssn``. The
Track-2 comparison (docs/status/2026-07-28-simnec-comparison-handoff.md) is
the proof: breaking symmetry fans AntennaKNoBs across ``zcomm`` while SimNEC
is stuck on one value.

.. note::
   The station element XML (parameter names ``Zo``/``VFnom``/``ft``/``k0``…,
   ``F``/``H``/``Q``/``@MHz``, ``Mdl``/``N``) is authored from the schema
   survey of a SimNEC 5.1a1-saved ``lastCircuit.ssn`` (issue #604), and
   load-validated in SimNEC 6p4d6 (2026-08-07): the ladder-tuner cascade
   loads with correct element values and reproduces the Track-1 rig-side
   impedance at 7.1 MHz. ``TRANSFORMER2``'s ``N`` was found to read
   antenna-side:generator-side — the inverse of our ``Transformer`` ``n`` —
   so the exporter emits the reciprocal (see the emission comment).
   Remaining caveats: (1) ``Q = 0`` is assumed to mean "ideal / no loss"
   (the SimSmith convention); (2) the ``SERIES_TLINE`` ``material`` param is
   omitted on the assumption SimNEC then honours the explicit
   ``k0``/``k1``/``k2`` loss coefficients.

Licensing
---------
SimNEC is proprietary freeware. This module emits SimNEC's *open file format*
for interoperability (like emitting a NEC deck or a Touchstone file); it does
**not** copy SimNEC's bundled circuit files or assets. The daemon directives are
the documented NEC-portal API. The surrounding XML scaffold in
:data:`_SSN_TEMPLATE` is authored here (clean-room) from the format's structure.

.. note::
   Reconciled against a SimNEC 5.1a1-saved ``.ssn``: the root ``SimNEC1p0``,
   the ``SimNEC:<version>`` ``XMLVersionControl`` string, the Generator's ``Zo``
   impedance tag, and the retained ``FR`` card all match SimNEC's own output.
   The scaffold here is deliberately *minimal* (it omits SimNEC's display state
   — ``SPREADSHEET`` / charts / band menus — which SimNEC regenerates on load);
   a Windows load-test confirms SimNEC accepts that minimal subset. The Generator
   frequency sweep is off by default (SimNEC supplies its own range); pass
   ``sweep=(lo, hi)`` / ``--sweep`` to emit an enabled band.
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape as _xml_escape

from .engines.pynec import DEFAULT_GROUND, PyNECEngine
from .nec_export import _gw, _num, export_nec
from .network import (
    TL,
    Admittance,
    Autotransformer,
    BalancedLine,
    Driven,
    FloatingBalun,
    Load,
    PortOnWire,
    Shunt,
    TouchstoneLoad,
    TouchstoneTwoPort,
    Transformer,
    TwoPort,
    _branch_port_refs,
    as_wire,
)

__all__ = ["export_ssn", "build_nec_portal_script", "SsnUnsupported"]


class SsnUnsupported(NotImplementedError):
    """The design (or one of its network branches) has no faithful SimNEC
    representation — most importantly the common-mode constructs
    (``BalancedLine.zcomm``, ``FloatingBalun``), which SimNEC's purely
    differential elements cannot express (issue #604). Subclasses
    ``NotImplementedError`` so phase-1 callers that treated "networked
    design" errors as a capability probe keep working unchanged. The
    message always names the offending construct and what to do about it."""


def _fmt(x: float) -> str:
    """Compact real for daemon directives (trim trailing zeros)."""
    return f"{float(x):g}"


def _ground_directive(ground) -> tuple[str | None, float]:
    """Map an antennaknobs ground spec to a SimNEC daemon ground call and the
    wire conductivity (mhos/m) to set on ``NECOptions.mhosPerMeter``.

    Returns ``(call_or_None, mhos_per_meter)``. Free space → no ground call.
    Note SimNEC's ``SommerfeldGround(mhos, dielectric)`` takes (sigma, eps_r) —
    the reverse of our ``("finite", eps_r, sigma)`` tuple.
    """
    if ground is None or ground == "free":
        return None, 0.0
    if ground == "pec":
        return "PerfectGround();", 0.0
    if (
        isinstance(ground, tuple)
        and len(ground) == 3
        and ground[0] in ("finite", "finite-fast")
    ):
        _, eps_r, sigma = ground
        # SimNEC has no distinct reflection-coefficient ("finite-fast") ground;
        # both map to its Sommerfeld solve — the accurate model — which is also
        # what a validation run should compare against.
        return f"SommerfeldGround({_fmt(sigma)}, {_fmt(eps_r)});", 0.0
    raise ValueError(f"unrecognised ground spec: {ground!r}")


def _nec_cards_for_portal(deck: str) -> list[str]:
    """Keep the cards SimNEC's NEC block wants: geometry (``GW``), frequency
    (``FR``), excitation (``EX``), and lumped loads (``LD 0`` / ``LD 1``).

    ``FR`` is kept because SimNEC's own NEC-portal decks carry it — even while
    the Generator sweeps ``G.MHz`` (the deck's ``FR`` is advisory; the solve
    frequency comes from the Generator). Confirmed against a SimNEC 5.1a1-saved
    ``.ssn`` (``FR 0 1 0 0 <f> 0`` present alongside a live G.MHz sweep).

    Dropped: ``CM``/``CE``/``GE``/``RP``/``XQ``/``EN`` (structural), ``GN`` (→
    ground call), ``LD 5`` global conductivity (→ ``NECOptions.mhosPerMeter``)
    and ``LD 2`` insulation (not representable in the NEC block).
    """
    # Group into canonical NEC order — geometry+loads, then FR, then EX — to
    # match a SimNEC 5.1a1-saved deck (GW … FR … EX) rather than export_nec's
    # emission order, which puts EX before FR.
    geom: list[str] = []
    fr: list[str] = []
    ex: list[str] = []
    for raw in deck.splitlines():
        s = raw.strip()
        if s.startswith("GW "):
            geom.append(s)
        elif s.startswith("FR "):
            fr.append(s)
        elif s.startswith("EX "):
            ex.append(s)
        elif s.startswith("LD "):
            parts = s.split()
            ldtyp = parts[1] if len(parts) > 1 else ""
            if ldtyp in ("0", "1"):  # series / parallel lumped RLC load
                geom.append(s)
            # LD 5 (conductivity) and LD 2 (insulation) are handled elsewhere
            # or unsupported; skip here.
    return geom + fr + ex


def _default_block_name(builder) -> str:
    """SimNEC shows the script's first //comment as the block's display name,
    which only fits ~12 chars before the font shrinks to unreadable. So use
    the SHORT leaf name: the design's module leaf (e.g. "invvee") for a real
    design, or the class qualname for a script-defined (__main__) builder."""
    mod = type(builder).__module__
    qual = type(builder).__qualname__
    if mod != "__main__" and qual == "Builder":
        return mod.rsplit(".", 1)[-1]
    return qual


def _portal_wrap(cards, *, name, ground, seg_per_wl) -> str:
    """The NEC-portal daemon script (the ``<equ>`` body): comment header,
    ports/units/ground/mesh directives, then ``cards`` between NEC2/NECEND."""
    ground_call, mhos = _ground_directive(ground)
    lines = [
        f"//{name}",
        "// generated by antennaknobs.simnec_export",
        "P1 w1 gnd;",
        "P2 w2 gnd;",
        "NECUnits meters, meters;",
    ]
    if ground_call:
        lines.append(ground_call)
    lines.append(f"NECOptions.mhosPerMeter = {_fmt(mhos)};")
    if seg_per_wl is not None:
        lines.append(f"NECOptions.segmentsPerWavelength = {int(seg_per_wl)};")
    lines.append("NEC2")
    lines.extend(cards)
    lines.append("NECEND")
    return "\n".join(lines)


def build_nec_portal_script(
    builder,
    *,
    freq_mhz: float,
    ground=DEFAULT_GROUND,
    seg_per_wl: int | None = None,
    name: str | None = None,
) -> str:
    """Build the SimNEC NEC-portal daemon script (the ``<equ>`` body) for an
    antenna-only ``builder``. Reuses :func:`export_nec` for the geometry.
    """
    deck = export_nec(builder, ground=ground, freq=freq_mhz, include_rp=False)
    cards = _nec_cards_for_portal(deck)
    if name is None:
        name = _default_block_name(builder)
    return _portal_wrap(cards, name=name, ground=ground, seg_per_wl=seg_per_wl)


# --- phase 2: networked (station) export — issue #604 -----------------------

C_MHZ_M = 299.792458  # c in MHz·m: λ[m] = C_MHZ_M / f[MHz]
M_PER_FT = 0.3048


def _brname(br, path: str) -> str:
    """Actionable branch name for rejection messages: instance path + type +
    the ports it spans, e.g. ``tuner.FloatingBalun(rig, sL, sR)``."""
    return f"{path}{type(br).__name__}({', '.join(_branch_port_refs(br))})"


def _element_factory():
    """Returns ``mk(typ, prefix, params)`` building one ``<element>`` XML
    fragment at the scaffold's indentation, with per-prefix numbered
    ``sweeperLabel``s (T1, C1, C2, L1, X1 …) in emission order. The LOAD /
    NETWORK / GENERATOR labels are single letters (L/A/G), so numbered chain
    labels can never collide with them."""
    counts: dict[str, int] = {}

    def mk(typ: str, prefix: str, params) -> str:
        counts[prefix] = counts.get(prefix, 0) + 1
        label = f"{prefix}{counts[prefix]}"
        body = "".join(
            f"\n                <p><n>{_xml_escape(str(n))}</n>"
            f"<v>{_xml_escape(str(v))}</v></p>"
            for n, v in params
        )
        return (
            "            <element>\n"
            f"                <type>{typ}</type>\n"
            f"                <sweeperLabel>{label}</sweeperLabel>"
            f"{body}\n"
            "            </element>"
        )

    return mk


def _q_params(q: float | None, freq_mhz: float):
    """SimNEC quotes component Q at a frequency (``Q`` / ``@MHz``). Our
    ``ql``/``qc`` are frequency-independent, so at the export frequency the
    two models agree exactly. ``Q = 0`` is emitted for the ideal component
    (no ``ql``/``qc``) — the SimSmith "loss model off" convention (see the
    module-note validation caveats)."""
    return [("Q", _fmt(q if q else 0.0)), ("@MHz", _fmt(freq_mhz))]


def _series_elements(br, entered_at: str, freq_mhz: float, mk, name: str):
    """SimNEC element(s) for one series (two-node) branch, in cascade order.
    A branch may emit several elements (a TwoPort with both L and C legs is a
    series pair — order between them is electrically irrelevant) or none (an
    all-omitted TwoPort is an ideal short: a plain wire-through)."""
    if isinstance(br, TL):
        if br.transposed:
            raise SsnUnsupported(
                f"{name}: a transposed (half-twist) line has no SimNEC "
                "cascade element — SERIES_TLINE cannot flip polarity"
            )
        # SimNEC's loss convention matches the cable-table one ours uses:
        # dB/100 ft = k0 + k1·√f + k2·f, displayed as `/100f` at `@frq`.
        # `~deg`/`@MHz` are the displayed electrical length, advisory (SimNEC
        # recomputes them from Zo/VFnom/ft).
        loss_100ft = br.k1 * math.sqrt(freq_mhz) + br.k2 * freq_mhz
        deg = 360.0 * br.length * freq_mhz / (br.vf * C_MHZ_M)
        return [
            mk(
                "SERIES_TLINE",
                "T",
                [
                    ("Zo", _fmt(br.z0)),
                    ("VFnom", _fmt(br.vf)),
                    ("ft", _fmt(br.length / M_PER_FT)),
                    ("~deg", _fmt(deg)),
                    ("@MHz", _fmt(freq_mhz)),
                    ("/100f", _fmt(loss_100ft)),
                    ("@frq", _fmt(freq_mhz)),
                    ("k0", "0"),
                    ("k1", _fmt(br.k1)),
                    ("k2", _fmt(br.k2)),
                ],
            )
        ]
    if isinstance(br, TwoPort):
        if br.r is not None:
            raise SsnUnsupported(
                f"{name}: a plain series R is not in the captured SimNEC "
                "element set; express the loss as a component Q (ql/qc)"
            )
        out = []
        if br.l is not None:
            out.append(
                mk("SERIES_IND", "L", [("H", _fmt(br.l)), *_q_params(br.ql, freq_mhz)])
            )
        if br.c is not None:
            out.append(
                mk("SERIES_CAP", "C", [("F", _fmt(br.c)), *_q_params(br.qc, freq_mhz)])
            )
        return out
    if isinstance(br, Transformer):
        if br.r is not None or br.lmag is not None or br.core is not None:
            raise SsnUnsupported(
                f"{name}: only the IDEAL transformer maps to TRANSFORMER2 "
                "(Mdl ideal); winding loss / magnetizing branches are not "
                "exported — drop r/lmag/core or model them explicitly in "
                "SimNEC after loading"
            )
        # Orientation: our Transformer(a, b, n) has v_a = n·v_b, so the
        # impedance at a is n²·Z_b; n_eff is that generator-side:antenna-side
        # ratio — entering the branch at `a` keeps n, entering at `b` inverts
        # it. SimNEC's TRANSFORMER2 N reads the OTHER way (measured on 6p4d6,
        # 2026-08-07: an n=2 step-up emitted as N=2 read Z/4 at the generator
        # instead of 4Z), so the emitted value is 1/n_eff.
        n_eff = br.n if entered_at == br.a else 1.0 / br.n
        return [mk("TRANSFORMER2", "X", [("Mdl", "ideal"), ("N", _fmt(1.0 / n_eff))])]
    raise SsnUnsupported(f"{name}: no SimNEC mapping for this branch type")


def _shunt_elements(br: Shunt, freq_mhz: float, mk, name: str):
    """SimNEC element(s) for a Shunt-to-common. Adjacent shunt elements at
    one node are electrically parallel, so a parallel-form L+C emits both;
    a series-form L+C (a shunt series-LC trap) has no captured element."""
    if br.r is not None:
        raise SsnUnsupported(
            f"{name}: a plain shunt R is not in the captured SimNEC element "
            "set; express the loss as a component Q (ql/qc)"
        )
    if br.l is not None and br.c is not None and not br.parallel:
        raise SsnUnsupported(
            f"{name}: a series-LC shunt (trap to common) has no single "
            "SimNEC element, and two stacked shunts would be parallel"
        )
    out = []
    if br.l is not None:
        out.append(
            mk("SHUNT_IND", "L", [("H", _fmt(br.l)), *_q_params(br.ql, freq_mhz)])
        )
    if br.c is not None:
        out.append(
            mk("SHUNT_CAP", "C", [("F", _fmt(br.c)), *_q_params(br.qc, freq_mhz)])
        )
    return out


def _station_chain(net, freq_mhz: float):
    """Map the network's branches onto SimNEC's linear cascade.

    Returns ``(feed_port, elements, deck_loads)``: the antenna-side
    ``PortOnWire`` the walk terminates on, the chain's element XML fragments
    in generator→antenna walk order, and the ``Load`` branches that belong in
    the NEC deck (as LD cards) rather than the circuit.

    Raises :class:`SsnUnsupported` for anything that is not a single
    generator→antenna ladder of representable elements — most importantly
    the common-mode constructs (see the module note)."""
    # --- per-branch vetting; index the representable ones -------------------
    series_at: dict[str, list] = {}
    shunts_at: dict[str, list] = {}
    deck_loads: list[Load] = []
    for bi, br in enumerate(net.branches):
        path = net.branch_paths[bi] if bi < len(net.branch_paths) else ""
        name = _brname(br, path)
        if isinstance(br, BalancedLine):
            if br.zcomm is not None:
                raise SsnUnsupported(
                    f"{name}: this design's physics lives in the line's "
                    f"common mode (zcomm={br.zcomm:g} Ω, issue #576), and "
                    "SimNEC's SERIES_TLINE is purely differential — there is "
                    "no zcomm knob, so no .ssn can represent it faithfully "
                    "(the Track-2 divergence). Not exported."
                )
            raise SsnUnsupported(
                f"{name}: a BalancedLine is a four-terminal conductor pair; "
                "SimNEC's cascade elements are two-terminal, so there is no "
                "faithful single-ended equivalent. Not exported."
            )
        if isinstance(br, FloatingBalun):
            raise SsnUnsupported(
                f"{name}: a FloatingBalun's secondary is a genuinely floating "
                "differential pair (issue #589); SimNEC's datum-referenced "
                "cascade cannot represent it (the balanced-tuner common-mode "
                "limitation, issue #604). Not exported."
            )
        if isinstance(br, Autotransformer):
            raise SsnUnsupported(
                f"{name}: the autotransformer is a coupled-inductor model "
                "(issue #594), not an ideal ratio — mapping it onto "
                "TRANSFORMER2 (Mdl ideal) would misrepresent the common-"
                "section current. Not exported."
            )
        if isinstance(br, (Admittance, TouchstoneLoad, TouchstoneTwoPort)):
            raise SsnUnsupported(f"{name}: no SimNEC element mapping (yet)")
        if isinstance(br, Load):
            if br.z is not None:
                raise SsnUnsupported(
                    f"{name}: the fixed-Z load form (LD 4) is not exported"
                )
            if br.ql is not None or br.qc is not None:
                raise SsnUnsupported(
                    f"{name}: a finite-Q Load needs R = ωL/Q re-derived per "
                    "frequency, which a deck LD card cannot express"
                )
            if not isinstance(net.ports.get(br.port), PortOnWire):
                raise SsnUnsupported(
                    f"{name}: a series Load on a virtual node has no SimNEC "
                    "cascade element (use a TwoPort for an in-line series "
                    "impedance)"
                )
            deck_loads.append(br)
        elif isinstance(br, Shunt):
            shunts_at.setdefault(br.port, []).append((bi, br, name))
        elif isinstance(br, (TL, TwoPort, Transformer)):
            series_at.setdefault(br.a, []).append((bi, br, name))
            series_at.setdefault(br.b, []).append((bi, br, name))
        else:
            raise SsnUnsupported(f"{name}: no SimNEC mapping for this branch type")

    # --- the generator end --------------------------------------------------
    if len(net.sources) != 1:
        raise SsnUnsupported(
            f"{len(net.sources)} sources; SimNEC's cascade has exactly one "
            "GENERATOR — multi-feed stations are not exported"
        )
    src = net.sources[0]
    if not isinstance(src, Driven):
        raise SsnUnsupported(
            f"source {type(src).__name__} on {src.port!r}: SimNEC's GENERATOR "
            "is a voltage source; current-forced feeds are not exported"
        )

    # --- walk the ladder from the generator to the antenna ------------------
    mk = _element_factory()
    elements: list[str] = []
    visited: set[int] = set()
    seen_nodes: set[str] = set()
    node = src.port
    while True:
        seen_nodes.add(node)
        for bi, br, name in shunts_at.pop(node, []):
            visited.add(bi)
            elements.extend(_shunt_elements(br, freq_mhz, mk, name))
        if isinstance(net.ports.get(node), PortOnWire):
            feed_port = node
            break
        avail = [
            (bi, br, name)
            for bi, br, name in series_at.get(node, [])
            if bi not in visited
        ]
        if len(avail) != 1:
            raise SsnUnsupported(
                f"node {node!r} has {len(avail)} onward series branches; "
                "SimNEC's circuit is a single generator→antenna cascade, so "
                "only a simple ladder (series elements plus shunts to "
                "common) is exported"
            )
        bi, br, name = avail[0]
        visited.add(bi)
        elements.extend(_series_elements(br, node, freq_mhz, mk, name))
        node = br.b if br.a == node else br.a
        if node in seen_nodes:
            raise SsnUnsupported(
                f"branch {name} loops back to {node!r}; the cascade must be "
                "a simple generator→antenna path"
            )

    leftover = [
        name
        for lst in (*series_at.values(), *shunts_at.values())
        for bi, _br, name in lst
        if bi not in visited
    ]
    if leftover:
        raise SsnUnsupported(
            "branch(es) hang off the generator→antenna cascade: "
            f"{sorted(set(leftover))}; SimNEC's circuit is a single ladder"
        )
    if getattr(net.ports[feed_port], "distributed", False):
        raise SsnUnsupported(
            f"feed port {feed_port!r} is a distributed (finite-gap) port "
            "(issue #477); the NEC block's EX card is a single-segment delta "
            "gap, which is a different feed model — not exported"
        )
    return feed_port, elements, deck_loads


def _station_cards(eng, feed_port: str, deck_loads, freq_mhz: float):
    """The station's NEC-block cards: geometry, trap/lumped LD loads on real
    ports, FR, and an EX delta gap at the station's feed port (which the
    portal wires to the block's circuit port — the cascade attaches there).
    Same canonical GW → LD → FR → EX grouping as the antenna-only path."""
    name_to_loc: dict[str, tuple[int, int]] = {}
    geom: list[str] = []
    for tag, t in enumerate(eng.tups, start=1):
        geom.append(_gw(tag, t[2], t[0], t[1], eng._radius_for(t)))
        w = as_wire(t)
        if w.name is not None:
            # PyNEC's delta-gap placement for a named wire (pynec.py):
            # the middle segment.
            name_to_loc[w.name] = (tag, (t[2] + 1) // 2)
    for br in deck_loads:
        r = float(br.r) if br.r is not None else 0.0
        l = float(br.l) if br.l is not None else 0.0
        c = float(br.c) if br.c is not None else 0.0
        if r == 0.0 and l == 0.0 and c == 0.0:
            continue
        tag, seg = name_to_loc[br.port]
        ldtyp = 1 if br.parallel else 0
        geom.append(f"LD {ldtyp} {tag} {seg} {seg} {_num(r)} {_num(l)} {_num(c)}")
    tag, seg = name_to_loc[feed_port]
    return geom + [
        f"FR 0 1 0 0 {_num(freq_mhz)} {_num(0.0)}",
        f"EX 0 {tag} {seg} 0 {_num(1.0)} {_num(0.0)}",
    ]


# --- minimal .ssn XML scaffold (see module note) ----------------------------
# Cascade, listed right-to-left the way SimNEC saves it: LOAD (open, right
# end) — NETWORK (the antenna, in the escape-hatch script) — {chain} (the
# station's circuit elements, antenna side first; "" for antenna-only) —
# GENERATOR (50 Ohm source, left end). Deliberately minimal — SimNEC
# regenerates the display state (SPREADSHEET / charts / band menus) it
# omits. The Generator's MHz carries an optional {gen_sweep} <sweepParam>.
_SSN_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<SimNEC1p0>
    <SmithChartCircuit>
        <XMLVersionControl>SimNEC:5.1a1</XMLVersionControl>
        <CIRCUIT>
            <element>
                <type>LOAD</type>
                <sweeperLabel>L</sweeperLabel>
                <p><n>ohms</n><v>1000000000</v></p>
            </element>
            <element>
                <type>NETWORK</type>
                <sweeperLabel>A</sweeperLabel>
                <escapeHatch/>
                <p><n>equ</n><v>{equ}</v></p>
            </element>{chain}
            <element>
                <type>GENERATOR</type>
                <sweeperLabel>G</sweeperLabel>
                <showInSmith>true</showInSmith>
                <p><n>MHz</n><v>{mhz}</v>{gen_sweep}</p>
                <p><n>Zo</n><v>50</v></p>
            </element>
        </CIRCUIT>{sweep_state}
    </SmithChartCircuit>
</SimNEC1p0>
"""

# When a sweep is requested, arm it: SCATTERGUN names the swept parameter (without
# it, doSweep=y on the param does nothing) and ROUNDCHART puts the chart in
# swept-trace mode. Confirmed against a SimNEC 5.1a1-saved, actively-sweeping file.
_SWEEP_STATE = (
    "\n        <SCATTERGUN><n>G.MHz</n></SCATTERGUN>"
    "\n        <ROUNDCHART><displayMode>Sweep</displayMode></ROUNDCHART>"
)


def _gen_sweep_block(lo: float, hi: float) -> str:
    """SimNEC ``<sweepParam>`` for the Generator's ``MHz``, enabled (``doSweep
    y``). Mirrors the structure of a SimNEC 5.1a1-saved file (confirmed to load);
    without it SimNEC falls back to its default (disabled) sweep range."""
    return (
        "<sweepParam><name>G.MHz</name><listed>true</listed>"
        "<p><n>points</n><v>100</v></p>"
        f"<p><n>from</n><v>{_fmt(lo)}</v></p>"
        f"<p><n>to</n><v>{_fmt(hi)}</v></p>"
        "<p><n>log</n><v>lin</v></p>"
        "<p><n>doSweep</n><v>y</v></p>"
        "<p><n>expr</n><v>Vary</v><fontScale>1</fontScale><w>640</w><h>360</h>"
        "<relx>0</relx><rely>360</rely><ProgrammingDialog><ThreeSplitPane>"
        "<errDiv>0.3</errDiv><outDiv>0.7</outDiv></ThreeSplitPane>"
        "</ProgrammingDialog></p></sweepParam>"
    )


def export_ssn(
    builder,
    *,
    freq_mhz: float | None = None,
    ground=DEFAULT_GROUND,
    seg_per_wl: int | None = None,
    sweep: tuple[float, float] | None = None,
    name: str | None = None,
) -> str:
    """Return a SimNEC ``.ssn`` (str) for ``builder`` — antenna-only, or a
    differential-only station (issue #604; see the module Scope note).

    freq_mhz   : Generator frequency in MHz; defaults to ``builder.freq``.
    ground     : same spec as ``export_nec`` / PyNECEngine — None/"free",
                 "pec", ("finite", eps_r, sigma), ("finite-fast", eps_r, sigma).
    seg_per_wl : SimNEC auto-mesh density (segments per wavelength). None leaves
                 SimNEC's default; set it to pin SimNEC's mesh for a convergence
                 comparison (SimNEC re-segments regardless of the deck).
    sweep      : ``(lo_mhz, hi_mhz)`` to enable the Generator's frequency sweep
                 over that band. ``None`` (default) leaves it minimal, so SimNEC
                 uses its own default (disabled) range — the single-point solve
                 at ``freq_mhz`` is still correct.
    name       : block display name (SimNEC's first ``//`` comment). Defaults to
                 the design's short leaf name; keep it ≤ ~12 chars — SimNEC
                 shrinks the font for longer names.

    Raises :class:`SsnUnsupported` (a ``NotImplementedError``) for networked
    designs SimNEC cannot faithfully represent — common-mode constructs
    (``BalancedLine.zcomm``, ``FloatingBalun``, balanced tuners), non-ladder
    topologies, and unmapped branch types. Component ``Q`` values are quoted
    at ``freq_mhz`` (SimNEC's ``Q``/``@MHz`` convention), so a station export
    is exact at that frequency and Q-model-approximate across a sweep.
    """
    freq_mhz = builder.freq if freq_mhz is None else float(freq_mhz)
    # PyNECEngine raises ValueError here for PortAtEnd (momwire-only) designs —
    # NEC-2 (and therefore SimNEC's NEC block) has no junction-node port.
    eng = PyNECEngine(builder, ground=ground)
    if eng._use_reducer:
        # Station path (issue #604): circuit elements from the reducer
        # branches, the antenna alone in the NEC block, driven at the
        # station's feed port.
        feed_port, walk_elements, deck_loads = _station_chain(eng._network, freq_mhz)
        cards = _station_cards(eng, feed_port, deck_loads, freq_mhz)
        script = _portal_wrap(
            cards,
            name=name if name is not None else _default_block_name(builder),
            ground=ground,
            seg_per_wl=seg_per_wl,
        )
        # File order is right-to-left (LOAD … GENERATOR), so the chain lands
        # after the antenna NETWORK element in antenna→generator order.
        chain = "".join("\n" + el for el in reversed(walk_elements))
    else:
        script = build_nec_portal_script(
            builder, freq_mhz=freq_mhz, ground=ground, seg_per_wl=seg_per_wl, name=name
        )
        chain = ""
    gen_sweep = (
        "" if sweep is None else _gen_sweep_block(float(sweep[0]), float(sweep[1]))
    )
    sweep_state = "" if sweep is None else _SWEEP_STATE
    return _SSN_TEMPLATE.format(
        equ=_xml_escape(script),
        chain=chain,
        mhz=_fmt(freq_mhz),
        gen_sweep=gen_sweep,
        sweep_state=sweep_state,
    )


def main(argv=None):
    """CLI: ``python -m antennaknobs.simnec_export <design> [opts]``."""
    import argparse

    from .cli import get_builder, parse_ground

    ap = argparse.ArgumentParser(
        prog="antennaknobs.simnec_export",
        description="Emit a SimNEC (.ssn) circuit for a design — antenna-only,"
        " or a differential-only station (antenna + feedline + tuner chain).",
    )
    ap.add_argument(
        "builder",
        help="Design name, e.g. dipoles.invvee[:variant] — or @file.nec to "
        "convert a NEC card deck straight to a SimNEC circuit",
    )
    ap.add_argument(
        "--freq", type=float, default=None, help="MHz (default: builder.freq)"
    )
    ap.add_argument(
        "--ground",
        default="free",
        help="free | pec | finite | finite:<eps_r>,<sigma> (default: free)",
    )
    ap.add_argument(
        "--seg-per-wl",
        type=int,
        default=None,
        help="SimNEC auto-mesh density (segments/wavelength)",
    )
    ap.add_argument(
        "--sweep",
        nargs="?",
        const="auto",
        default=None,
        metavar="LO,HI",
        help="Enable the Generator frequency sweep: bare '--sweep' for an auto "
        "band (+/-10%% around --freq), or '--sweep LO,HI' for an explicit MHz range.",
    )
    ap.add_argument(
        "--name",
        default=None,
        help="Block display name (default: design's short leaf name). SimNEC "
        "shrinks the font past ~12 chars, so keep it short.",
    )
    ap.add_argument("--out", default=None, help="Write here (default: stdout)")
    args = ap.parse_args(argv)

    builder = get_builder(args.builder)()
    freq = builder.freq if args.freq is None else args.freq
    sweep = None
    if args.sweep is not None:
        if args.sweep == "auto":
            sweep = (round(freq * 0.9, 6), round(freq * 1.1, 6))
        else:
            parts = args.sweep.split(",")
            if len(parts) != 2:
                ap.error("--sweep expects LO,HI (two MHz values), or bare for auto")
            sweep = (float(parts[0]), float(parts[1]))
    ssn = export_ssn(
        builder,
        freq_mhz=args.freq,
        ground=parse_ground(args.ground),
        seg_per_wl=args.seg_per_wl,
        sweep=sweep,
        name=args.name,
    )
    if args.out:
        # --name is echoed verbatim into the script's first //comment; pin
        # the encoding rather than trust the platform default (issue #772).
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(ssn)
        print(f"wrote {args.out}")
    else:
        print(ssn, end="")


if __name__ == "__main__":
    main()
