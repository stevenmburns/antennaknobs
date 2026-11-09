"""A stitched antenna + station network as ONE NEC-5 deck, at one frequency
(AK#2209).

`nec5_export.export_nec5` refuses any network with a line, a two-port or a
virtual node: the app solves those outside the field solve, one deck per
port. A station (`simnec_import.SsnStation.network` on any antenna's
network, AK#2200) is exactly such a network, and users build its deck by
hand. This writer spells the whole station with NEC cards instead, the way
EZNEC writes its own virtual segments, lossy lines and L networks:

=========================================  ==================================
part of the model                          card
=========================================  ==================================
antenna wires, ground, wire material,      GW / GE / GN / LD, written by
loads on wires                             `NEC5Engine.deck` as today
a virtual node (the generator's, one       a knot of ONE phantom wire parked
between chain blocks)                      far from the structure, pinned
                                           open by an ``LD 4`` of `PIN_OHMS`
a lossless line                            ``TL`` (length in NEC's c)
a lossy line (the Johnson line), an S      ``NT``: the two-port Y AK computes
block, a series R/L/C, a fixed Y           at the deck's frequency
a shunt element, a load on a node that     folded into the Y11/Y22 of an
also carries the network                   ``NT``, or a ``TL``'s end shunt
an ideal transformer (no Y exists)         two λ/4 ``TL`` cards through a
                                           phantom knot (`quarter_wave_pair`)
an ideal 1:1 through-connection            the two nodes become one knot
the generator                              ``EX 0`` on its node's knot
=========================================  ==================================

ONE FREQUENCY. ``NT`` and the λ/4 lines hold only at the frequency they
were computed for, so the deck has one ``FR`` point and says so in its
``CM`` header. A sweep is a deck per frequency (or one deck of blocks, the
follow-up), never this one with a wider ``FR``.

PHANTOM KNOTS ARE PINNED. A phantom knot is a real piece of wire to NEC-5,
and unpinned it sits in parallel with whatever the network connects there:
measured on the licensed binary, a 4-segment phantom of λ/200 reads
j2.6e-5 S per knot (EZNEC's own virtual wire read j3.88e-5 S in Dan #118),
which is 0.13 % on a 50 Ω node and 2.6 % on a 1 kΩ one. A knot
carrying an ``LD 4`` of R = `PIN_OHMS` instead reads 1/R: measured, two
pinned knots in series with nothing else read 2.0000e-10 S at R = 1e10 and
2.0001e-12 S at 1e12, and a source or a network card on a pinned knot still
sees the network, not the pin (an NT series 10 Ω from a pinned generator
knot read Z_ant + 10.000 Ω to the printout's five figures). EZNEC pins its
virtual segments the same way, with the same 1e10, and `nec_import` reads
such a wire back as circuit nodes (`_virtual_segment_wires`).

What is left is the pin's own conductance, `PIN_RESIDUAL_S` per knot, and
the writer measures what it does: `station_deck` solves the design once
(momwire by default), rebuilds the CARDS it wrote as a circuit on that
antenna Y, and re-solves with 1/R on each pinned knot in turn. A knot whose
residual moves the driving-point impedance by more than `NODE_EFFECT_LIMIT`
is refused by name. The same circuit, unperturbed, must reproduce the
composite solve; it is the writer's check on its own cards.

Addressing is NEC-5's: a source, load or network end sits on a KNOT, named
by tag, segment and end (`NEC5Engine._source_address`). On ``NT``/``TL`` the
end rides the segment field's sign, positive end 2 and negative end 1 (the
reading `nec_import._attach` pins). Measured on the licensed binary, a
vertex port (`PortAtVertex`, the knot where two wires meet) takes ``NT`` and
``TL`` cards exactly as a centre knot does: an inverted V fed through an NT
series 10 Ω read Z_vertex + 10.000 Ω addressed either as end 2 of wire 1's
last segment or end 1 of wire 2's first, so a knot-fed antenna is written,
not refused.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .card_text import card_text
from .network import (
    TL,
    Admittance,
    Driven,
    DrivenCurrent,
    Load,
    PortAtVertex,
    PortOnWire,
    PortOnWireFloating,
    PortVirtual,
    Shunt,
    TouchstoneLoad,
    TouchstoneTwoPort,
    Transformer,
    TwoPort,
    load_impedance,
)
from .network import Network as _Network

# NEC-5's metre-megahertz product for a line's phase. Measured on the
# licensed binary: a λ/4 pair (100 Ω then 50 Ω) into a dipole reads exactly
# 4·Z_ant (308.46 + j142.34 against 4 x 77.114 + j35.586) when λ = 299.8/f,
# and 308.40 + j142.38 when λ = 299.792458/f.
NEC5_C_LIGHT_MHZ_M = 299.8

# The open-circuit pin on every phantom knot, EZNEC's own value for its
# virtual segments. Measured residual: 1/R per knot (module docstring).
PIN_OHMS = 1e10
PIN_RESIDUAL_S = 1.0 / PIN_OHMS

# The most a phantom knot's residual may move the driving-point impedance,
# relative. NEC-5 prints five significant figures, so its own rounding of an
# impedance is at least half a unit in the fifth figure of a mantissa below
# 10: 5e-6 relative at the least. A knot under 1e-6 moves the answer by less
# than a fifth of the printout's smallest rounding, so it cannot be seen in
# the deck's output; above it, it can. At `PIN_RESIDUAL_S` that is a node
# whose effective impedance |V_k|²/|V·I|_in reaches 1e4 Ω — no 50 Ω station
# node comes near it, and a phantom node that does belongs on a real
# segment.
NODE_EFFECT_LIMIT = 1e-6

# NEC-5 refuses a real whose mantissa, sign included, runs past 17
# characters before an exponent (measured: `-1.23456789012345e-1` and
# `1.234567890123456e-1` read, `-1.234567890123456e-1` and
# `1.2345678901234567e-1` stop the run with "INVALID NUMBER"; a token with no
# exponent read at 26 characters). Fifteen significant figures fit always.
_DIGITS = 15
_MANTISSA_MAX = 17

# The phantom wire's geometry follows `nec_export._gyrator_cards`, whose
# constraints are the importer's: more than one segment, under 0.05 λ end to
# end, and parked 10x the structure's extent plus 200 λ away.
_PHANTOM_EXTENT_LAMBDA = 1.0 / 200.0
_PHANTOM_PARK_LAMBDA = 200.0

# Agreement of the writer's own cards, rebuilt as a circuit, with the
# composite solve: both are the same arithmetic on the same Y, so anything
# above rounding is a card the writer got wrong.
_SELF_CHECK_RTOL = 1e-9


class StationDeckRefusal(NotImplementedError):
    """A station this writer cannot spell faithfully as one NEC-5 deck."""


@dataclass(frozen=True)
class PhantomKnot:
    """One pinned knot of the phantom wire: the circuit node(s) it carries,
    its segment on the phantom wire (the knot is that segment's end 2), and
    the measured relative move of the driving-point impedance that its
    pin's residual conductance causes."""

    nodes: tuple[str, ...]
    segment: int
    effect: float


@dataclass(frozen=True)
class StationDeck:
    """`station_deck`'s result: the deck text and what was measured."""

    text: str
    freq_mhz: float
    knots: tuple[PhantomKnot, ...]
    # The network reduced on the engine's antenna Y (the composite) and the
    # writer's cards rebuilt as a circuit on the same antenna Y.
    z_composite: complex
    z_cards: complex

    @property
    def tolerance(self) -> float:
        """The derived bound on how far the deck's answer can sit from the
        composite's, relative, from the circuit alone: the sum of every
        pinned knot's measured effect (first order, so they add)."""
        return float(sum(k.effect for k in self.knots))


def _full(x: float) -> str:
    """A real at full precision inside NEC-5's token limit."""
    s = f"{float(x):.{_DIGITS}g}"
    if s in ("-0", "0"):
        return "0"
    if "e" in s and len(s.split("e")[0]) > _MANTISSA_MAX:
        raise ValueError(f"{x!r} cannot be written inside NEC-5's number token")
    return s


def quarter_wave_pair(n: float) -> tuple[tuple[float, bool], tuple[float, bool]]:
    """``((Z1, transposed1), (Z2, transposed2))``: the two λ/4 lossless lines
    whose cascade IS the ideal transformer ``Transformer(a, b, n)``
    (v_a = n·v_b, i_a = i_b/n).

    A λ/4 line of Z0 has the chain matrix [[0, jZ0], [j/Z0, 0]], an exact
    impedance inverter, so two in cascade give [[-Z1/Z2, 0], [0, -Z2/Z1]]:
    an ideal transformer of ratio -Z1/Z2. A transposed line negates its port
    b, which cancels the sign. So |n| = Z1/Z2, and the second line is
    transposed for n > 0. Z2 = 50·sqrt(|n|) puts the knot between them at
    Z2²/Z_b = 2500·|n|/Z_b: on a 50 Ω side, 50·|n| Ω, so the pinned knot
    there stays a low-impedance node."""
    n = float(n)
    if not math.isfinite(n) or n == 0.0:
        raise StationDeckRefusal(f"a transformer of ratio {n!r} has no λ/4 pair")
    z2 = 50.0 * math.sqrt(abs(n))
    return (abs(n) * z2, False), (z2, n > 0.0)


class _Nodes:
    """Union-find over network node names, for ideal through-connections."""

    def __init__(self, names):
        self.parent = {n: n for n in names}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _is_real(port) -> bool:
    return isinstance(port, PortAtVertex) or (
        isinstance(port, PortOnWire)
        and not isinstance(port, PortOnWireFloating)
        and not port.distributed
    )


def _refuse_ports(net):
    for name, port in net.ports.items():
        if _is_real(port) or isinstance(port, PortVirtual):
            continue
        raise StationDeckRefusal(
            f"port {name!r} ({type(port).__name__}) has no NEC-5 station-deck "
            "spelling: only a centre or positioned gap (PortOnWire), a vertex "
            "knot (PortAtVertex) and virtual nodes are written"
        )


@dataclass
class _Cards:
    """The network as card material, before addressing."""

    nt: dict  # (u, v) with u before v in node order -> 2x2 complex Y
    tl: list  # (u, v, z0, nec_length, transposed)
    shunt: dict  # node -> complex Y to datum
    ld4: list  # (real node, complex Z) loads written as a fixed LD 4


def _branch_cards(net, nodes: _Nodes, order, freq_mhz, wl, c_light, cl_reducer):
    """Every branch of ``net`` as card material on the merged ``nodes``."""
    omega = 2.0 * math.pi * freq_mhz * 1e6
    f_hz = freq_mhz * 1e6
    from .mw.networks import (  # noqa: PLC0415 — the layer's line math, on use
        magnetizing_impedance,
        tl_admittance_2x2,
    )

    # The RLC helpers through network.py's compatibility re-exports, the one
    # sanctioned path to them (tests/test_momwire_private_imports.py).
    from .network import (  # noqa: PLC0415 — on use
        _parallel_rlc_admittance,
        _series_rlc_impedance,
    )

    cards = _Cards(nt={}, tl=[], shunt={}, ld4=[])
    rank = {n: i for i, n in enumerate(order)}

    def add_shunt(node, y):
        if y:
            cards.shunt[node] = cards.shunt.get(node, 0j) + complex(y)

    def add_nt(a, b, y):
        y = np.asarray(y, dtype=complex)
        a, b = nodes.find(a), nodes.find(b)
        if a == b:
            add_shunt(a, y.sum())
            return
        if rank[a] > rank[b]:
            a, b = b, a
            y = y[::-1, ::-1]
        cards.nt[(a, b)] = cards.nt.get((a, b), np.zeros((2, 2), complex)) + y

    def add_line(a, b, z0, nec_length, transposed):
        a, b = nodes.find(a), nodes.find(b)
        if a == b:
            raise StationDeckRefusal(
                f"a line from node {a!r} back to itself has no TL spelling"
            )
        cards.tl.append((a, b, float(z0), float(nec_length), bool(transposed)))

    for k, br in enumerate(net.branches):
        if isinstance(br, Load):
            continue  # placed once every other card is known (below)
        if isinstance(br, Shunt):
            if br.parallel:
                y = _parallel_rlc_admittance(br.r, br.l, br.c, omega, br.ql, br.qc)
            else:
                z = _series_rlc_impedance(br.r, br.l, br.c, omega, br.ql, br.qc)
                if z == 0:
                    raise StationDeckRefusal(
                        f"Shunt on {br.port!r} is a dead short to ground, which "
                        "no NEC card spells"
                    )
                y = 1.0 / z if np.isfinite(z) else 0j
            add_shunt(nodes.find(br.port), y)
        elif isinstance(br, TouchstoneLoad):
            add_shunt(nodes.find(br.port), br.data.y_at(f_hz)[0, 0])
        elif isinstance(br, Admittance):
            y = np.asarray(br.y, dtype=complex)
            if len(br.ports) == 1:
                add_shunt(nodes.find(br.ports[0]), y[0, 0])
            elif len(br.ports) == 2:
                add_nt(*br.ports, y)
            else:
                raise StationDeckRefusal(
                    f"a {len(br.ports)}-port Admittance has no NT spelling (NT "
                    "is a two-port)"
                )
        elif isinstance(br, TouchstoneTwoPort):
            add_nt(br.a, br.b, br.data.y_at(f_hz))
        elif isinstance(br, TwoPort):
            z = _series_rlc_impedance(br.r, br.l, br.c, omega, br.ql, br.qc)
            if z == 0 or not np.isfinite(z):
                continue  # a short is merged into one node; an open is no card
            y = 1.0 / z
            add_nt(br.a, br.b, [[y, -y], [-y, y]])
        elif isinstance(br, TL):
            lossless = not (br.k0 or br.k1 or br.k2)
            if lossless and br.length == 0:
                continue  # merged into one node
            if lossless:
                # NEC's phase is 2π·f·len/299.8 at velocity c; AK's is
                # 2π·length/(vf·λ) with λ = c_design/f. Equal at this length.
                add_line(
                    br.a,
                    br.b,
                    br.z0,
                    br.length * NEC5_C_LIGHT_MHZ_M / (br.vf * c_light),
                    br.transposed,
                )
            else:
                add_nt(
                    br.a,
                    br.b,
                    tl_admittance_2x2(
                        br.z0,
                        br.length,
                        wl,
                        transposed=br.transposed,
                        vf=br.vf,
                        k1=br.k1,
                        k2=br.k2,
                        c_light_mhz_m=cl_reducer,
                        skin=br.skin,
                        k0=br.k0,
                    ),
                )
        elif isinstance(br, Transformer):
            zm = magnetizing_impedance(br, omega)
            if zm is not None:
                add_shunt(nodes.find(br.a), 1.0 / zm)
            n = complex(br.n)
            if n.imag:
                raise StationDeckRefusal(
                    f"Transformer {br.a!r}→{br.b!r} has a complex ratio {n!r}"
                )
            n = n.real
            if br.r:
                # v_a = n·v_b + r·i_a, i_b = n·i_a: Y = (1/r)[[1, -n], [-n, n²]].
                r = float(br.r)
                add_nt(br.a, br.b, np.array([[1.0, -n], [-n, n * n]]) / r)
                continue
            if n == 1.0:
                continue  # merged into one node, its magnetizing shunt on it
            (z1, t1), (z2, t2) = quarter_wave_pair(n)
            mid = f"{br.a}~{br.b}#{k}"
            nodes.parent[mid] = mid
            rank[mid] = len(rank)
            order.append(mid)
            quarter = NEC5_C_LIGHT_MHZ_M / freq_mhz / 4.0
            add_line(br.a, mid, z1, quarter, t1)
            add_line(mid, br.b, z2, quarter, t2)
        else:
            raise StationDeckRefusal(
                f"a {type(br).__name__} branch has no NEC-5 station-deck spelling"
            )
    return cards


def _merge_throughs(net, nodes: _Nodes, omega):
    """Fuse the nodes an ideal through-connection joins: a 1:1 lossless
    Transformer (SimNEC's bare wire between blocks, `simnec_import._THROUGH`),
    a zero series impedance and a zero-length lossless line. NEC has no
    zero-impedance card, and one knot is that connection exactly. A 1:1
    transformer's magnetizing branch, if it has one, is a shunt on that
    knot, which is where it sits on either winding."""
    from .network import _series_rlc_impedance  # noqa: PLC0415 — on use

    for br in net.branches:
        if isinstance(br, Transformer):
            if complex(br.n) == 1 and not br.r:
                nodes.union(br.a, br.b)
        elif isinstance(br, TwoPort):
            if _series_rlc_impedance(br.r, br.l, br.c, omega, br.ql, br.qc) == 0:
                nodes.union(br.a, br.b)
        elif isinstance(br, TL):
            if br.length == 0 and not (br.k0 or br.k1 or br.k2):
                nodes.union(br.a, br.b)


def _antenna_engine(builder, real, net, native, ground, wire_radius):
    """The deck-writing `NEC5Engine` over the antenna alone: the real ports,
    each driven (so the engine resolves its knot), and the loads it writes
    as its own LD cards. Never solved."""
    from .engines.nec5 import NEC5Engine  # noqa: PLC0415 — on use

    inner = _Network(
        ports={n: net.ports[n] for n in real},
        branches=list(native),
        sources=[Driven(port=n) for n in real],
    )
    # The same builder state behind a class whose network is the antenna's
    # (a builder's __getattr__ reads its params, so copy.copy recurses). The
    # subclass keeps the design's __module__: `design_data.read_data` finds a
    # design's folder from it, so a design that reads its .nec or .ssn from
    # beside itself reads it here too.
    cls = type(builder)
    sub = type(
        cls.__name__,
        (cls,),
        {"build_network": lambda _s: inner, "__module__": cls.__module__},
    )
    b = object.__new__(sub)
    b.__dict__.update(builder.__dict__)
    return NEC5Engine(b, ground=ground, require_exe=False, wire_radius=wire_radius)


def _solver_y(engine, freq_mhz):
    """``(Y, real port names in Y's order)``: the antenna's short-circuit Y
    at ``freq_mhz`` from an engine on the reducer route (momwire, NEC-5,
    NEC-2), which is all of an engine the measurement reads."""
    from .network_reduce import C_LIGHT  # noqa: PLC0415 — on use

    wl_for = getattr(engine, "_wavelength_for", None)
    wl = wl_for(freq_mhz) if wl_for is not None else C_LIGHT / (freq_mhz * 1e6)
    reducer = getattr(engine, "_reducer", None)
    if reducer is None:
        raise StationDeckRefusal(
            "the engine handed to the station writer does not solve this "
            "network by reduction, so it has no antenna Y to measure on"
        )
    Y = np.asarray(engine._compute_y_matrix(wl), dtype=complex)
    names = [n for n, _i in sorted(reducer.port_to_idx.items(), key=lambda t: t[1])]
    return Y, names[: Y.shape[0]]


def _driven_z(net, Y, real_names, wl, c_light_reducer):
    from .mw.networks import NetworkReducer  # noqa: PLC0415 — on use

    idx = {n: i for i, n in enumerate(real_names)}
    k = len(idx)
    for name, port in net.ports.items():
        if isinstance(port, PortVirtual):
            idx[name] = k
            k += 1
    red = NetworkReducer(net, idx, k, c_light_mhz_m=c_light_reducer)
    return np.atleast_1d(red.driven_impedance(Y, wl))


def station_deck(
    builder,
    *,
    freq=None,
    ground=None,
    title=None,
    wire_radius=None,
    engine=None,
) -> StationDeck:
    """The NEC-5 deck of ``builder``'s antenna and network at ONE frequency
    (MHz, default ``builder.freq``), with the per-knot measurement.

    ground      : NEC5Engine's spec — None/"free", "pec", ("finite", eps_r,
                  sigma), ("mininec", eps_r, sigma).
    title       : the header's name for the design.
    wire_radius : the web slot's radius field, as `export_nec5` takes it.
    engine      : an engine already built on ``builder`` that solves its
                  network by reduction (``_reducer`` and
                  ``_compute_y_matrix``), whose antenna Y the knots are
                  measured on. Default: momwire's ``bspline`` over
                  ``ground``. The measurement needs a node-voltage map, not
                  NEC-5's own digits, so another basis serves.

    Raises `StationDeckRefusal` for what no card spells (module docstring),
    by name, and for a phantom knot over `NODE_EFFECT_LIMIT`.
    """
    if freq is not None and np.ndim(freq) != 0:
        raise StationDeckRefusal(
            "a NEC-5 station deck holds ONE frequency: its NT cards and λ/4 "
            "lines are computed at that frequency and are wrong at any other, "
            "so a sweep is one deck per frequency"
        )
    freq_mhz = float(builder.freq if freq is None else freq)
    if builder.build_tls():
        raise StationDeckRefusal("legacy build_tls() lines are not written here")
    net = builder.build_network()
    if net is None or not net.sources:
        raise StationDeckRefusal("the design has no network source to drive")
    from .auto_match import find_tuners  # noqa: PLC0415 — on use

    if find_tuners(net):
        raise StationDeckRefusal(
            "a self-tuning tuner tunes from the solved load, so its parts are "
            "not known until a solve; tune it, then write its parts as fixed "
            "elements"
        )
    for src in net.sources:
        if isinstance(src, DrivenCurrent):
            raise StationDeckRefusal(
                f"the current source on {src.port!r} is not written into a "
                "station deck; drive the station with a voltage source"
            )
    _refuse_ports(net)

    c_light = float(builder.c_light_mhz_m)
    from .engines.momwire import C_LIGHT_MHZ_M  # noqa: PLC0415 — on use

    cl_reducer = None if c_light == C_LIGHT_MHZ_M else c_light
    wl = c_light / freq_mhz
    omega = 2.0 * math.pi * freq_mhz * 1e6

    nodes = _Nodes(net.ports)
    _merge_throughs(net, nodes, omega)
    for root in {nodes.find(n) for n in net.ports}:
        members = [n for n in net.ports if nodes.find(n) == root]
        real = [n for n in members if _is_real(net.ports[n])]
        if len(real) > 1:
            raise StationDeckRefusal(
                f"an ideal through-connection joins the real ports {real}: two "
                "places on the antenna cannot be one knot"
            )
        rep = real[0] if real else min(members, key=lambda n: (len(n), n))
        for n in members:
            nodes.parent[n] = n
        for n in members:
            nodes.parent[n] = rep
    order = [n for n in net.ports if nodes.find(n) == n]
    cards = _branch_cards(net, nodes, order, freq_mhz, wl, c_light, cl_reducer)

    real_nodes = [n for n in order if n in net.ports and _is_real(net.ports[n])]
    driven = {nodes.find(s.port): s for s in net.sources}
    if len(driven) != len(net.sources):
        raise StationDeckRefusal("two sources drive one node")
    touched = {u for u, _v in cards.nt} | {v for _u, v in cards.nt}
    touched |= {e for line in cards.tl for e in line[:2]}

    # A Load is a termination from the datum into its port, in parallel with
    # the antenna and the network there (the reducer's reading). On a knot
    # that carries only the antenna (and perhaps its source) that is NEC's
    # series LD; where the network also attaches it is a shunt, folded in.
    # (The reducer refuses a Load on a virtual node, so none reaches here.)
    native = []
    for br in net.branches:
        if not isinstance(br, Load):
            continue
        node = nodes.find(br.port)
        if node not in touched:
            if br.ql is None and br.qc is None:
                native.append(br)
            else:
                cards.ld4.append((node, load_impedance(br, omega)))
            continue
        if node in driven:
            raise StationDeckRefusal(
                f"the load on {br.port!r} sits behind a source that also "
                "drives the network there; NEC-5 puts an LD in series with "
                "the antenna, not with the source"
            )
        z = load_impedance(br, omega)
        if z == 0:
            raise StationDeckRefusal(
                f"the load on {br.port!r} is a dead short to ground, which no "
                "NEC card spells"
            )
        if np.isfinite(z):
            cards.shunt[node] = cards.shunt.get(node, 0j) + 1.0 / z
    for node in cards.shunt:
        if node not in touched:
            raise StationDeckRefusal(
                f"node {node!r} carries a shunt element and no line or "
                "two-port, so no card has an end there to carry it"
            )

    phantoms = [n for n in order if n not in real_nodes]
    loose = [
        n
        for n in real_nodes
        if n not in touched
        and n not in driven
        and not any(nodes.find(b.port) == n for b in native)
        and n not in {node for node, _z in cards.ld4}
    ]
    eng = _antenna_engine(builder, real_nodes, net, native, ground, wire_radius)
    addr = {}
    for name, (idx, _t, _v, knot) in zip(real_nodes, eng._sources, strict=True):
        seg, end = eng._source_address(idx, knot)
        addr[name] = (eng._tag_of(idx), seg, end)
    ptag = len(eng._cards) + 1
    for k, name in enumerate(phantoms, start=1):
        addr[name] = (ptag, k, 2)

    def field(name):
        tag, seg, end = addr[name]
        return f"{tag} {seg if end == 2 else -seg}"

    # Shunts ride a card end at their node: an NT's diagonal, else a TL's
    # end admittance. Exact either way, since a shunt to datum is in
    # parallel with every card at that knot.
    tl_shunt = [[0j, 0j] for _ in cards.tl]
    for node, y in cards.shunt.items():
        for (u, v), ymat in cards.nt.items():
            if node in (u, v):
                ymat[(0, 1)[node == v], (0, 1)[node == v]] += y
                break
        else:
            for i, line in enumerate(cards.tl):
                if node in line[:2]:
                    tl_shunt[i][line[:2].index(node)] += y
                    break

    # Every TL before every NT: momwire's NEC-5 drop-in refuses an NT read
    # before a TL (its NETWORK DATA printout follows the order every captured
    # mixed deck writes), and the licensed binary reads either order.
    net_lines = [
        f"TL {field(u)} {field(v)} {_full(-z0 if transposed else z0)} "
        f"{_full(length)} {_full(ya.real)} {_full(ya.imag)} "
        f"{_full(yb.real)} {_full(yb.imag)}"
        for (u, v, z0, length, transposed), (ya, yb) in zip(
            cards.tl, tl_shunt, strict=True
        )
    ]
    for (u, v), y in cards.nt.items():
        vals = (y[0, 0], y[0, 1], y[1, 1])
        if not np.allclose(y[0, 1], y[1, 0], rtol=1e-12, atol=0.0):
            raise StationDeckRefusal(
                f"the two-port between {u!r} and {v!r} is not reciprocal "
                "(Y12 ≠ Y21), and NT carries one transfer admittance"
            )
        net_lines.append(
            f"NT {field(u)} {field(v)} "
            + " ".join(f"{_full(c.real)} {_full(c.imag)}" for c in vals)
        )

    # --- the measurement: the cards as a circuit on the antenna's Y -------
    if engine is None:
        from .cli import make_engine_factory  # noqa: PLC0415 — on use

        engine = make_engine_factory("momwire:bspline", ground)(builder)
    Y, y_names = _solver_y(engine, freq_mhz)
    if sorted(y_names) != sorted(real_nodes):
        missing = set(real_nodes) ^ set(y_names)
        raise StationDeckRefusal(
            f"the engine's real ports differ from the network's: {sorted(missing)}"
        )
    # Both sides reduce in the DESIGN's c, the one the NT values were
    # computed in, whatever c the engine made its wavelengths with: Y is the
    # antenna at f either way.
    z_composite = complex(_driven_z(net, Y, y_names, wl, cl_reducer)[0])
    circuit_ports = {n: net.ports[n] for n in real_nodes}
    circuit_ports.update({n: PortVirtual(n) for n in phantoms})
    branches = list(native)
    branches += [Load(port=node, z=z) for node, z in cards.ld4]
    for (u, v), y in cards.nt.items():
        branches.append(Admittance(ports=(u, v), y=tuple(map(tuple, y))))
    for (u, v, z0, length, transposed), (ya, yb) in zip(
        cards.tl, tl_shunt, strict=True
    ):
        # The card's NEC phase 2π·f·len/299.8, at the design's wavelength.
        branches.append(
            TL(
                a=u,
                b=v,
                z0=z0,
                length=length * c_light / NEC5_C_LIGHT_MHZ_M,
                transposed=transposed,
            )
        )
        for node, y in ((u, ya), (v, yb)):
            if y:
                branches.append(Admittance(ports=(node,), y=((y,),)))
    sources = [Driven(port=n, voltage=s.voltage) for n, s in driven.items()]
    circuit = _Network(ports=circuit_ports, branches=branches, sources=sources)
    z_cards = complex(_driven_z(circuit, Y, y_names, wl, cl_reducer)[0])
    if abs(z_cards - z_composite) > _SELF_CHECK_RTOL * abs(z_composite):
        raise AssertionError(
            f"the station deck's cards solve to {z_cards} where the network "
            f"solves to {z_composite}: a card is wrong"
        )
    pinned = phantoms + loose
    knots = []
    for name in pinned:
        probe = _Network(
            ports=circuit_ports,
            branches=[*branches, Admittance(ports=(name,), y=((PIN_RESIDUAL_S,),))],
            sources=sources,
        )
        z = complex(_driven_z(probe, Y, y_names, wl, cl_reducer)[0])
        effect = abs(z - z_cards) / abs(z_cards)
        members = tuple(n for n in net.ports if nodes.find(n) == name) or (name,)
        if effect > NODE_EFFECT_LIMIT:
            raise StationDeckRefusal(
                f"node {name!r} is a high-impedance node: the open pin a "
                f"phantom knot needs moves the impedance by {effect:.2g} "
                f"relative, over the {NODE_EFFECT_LIMIT:g} below which a NEC-5 "
                "printout cannot show it. Put that node on a real antenna "
                "segment"
            )
        knots.append(
            PhantomKnot(
                nodes=members,
                segment=addr[name][1] if name in phantoms else 0,
                effect=effect,
            )
        )

    # --- the deck ------------------------------------------------------------
    lines = eng.deck([freq_mhz], sources=[]).splitlines()
    assert lines[0] == "CM antennaknobs NEC5Engine deck", lines[0]
    lam = NEC5_C_LIGHT_MHZ_M / freq_mhz
    gws = [ln.split() for ln in lines if ln.startswith("GW ")]
    extent = max((abs(float(c)) for g in gws for c in g[3:9]), default=0.0)
    zbase = 10.0 * extent + _PHANTOM_PARK_LAMBDA * lam
    # One segment more than knots: every knot interior, since NEC-5 refuses
    # a source at a free wire end's knot (`NEC5Engine._init_reducer`).
    nseg = len(phantoms) + 1
    total = _PHANTOM_EXTENT_LAMBDA * lam
    phantom_gw = (
        [
            f"GW {ptag} {nseg} 0 0 {_full(zbase)} {_full(total)} 0 "
            f"{_full(zbase)} {_full(total / nseg / 200.0)}"
        ]
        if phantoms
        else []
    )
    pins = [f"LD 4 {ptag} {k} 2 {_full(PIN_OHMS)} 0 0" for k in range(1, nseg)]
    for name in loose:
        tag, seg, end = addr[name]
        pins.append(f"LD 4 {tag} {seg} {end} {_full(PIN_OHMS)} 0 0")
    for node, z in cards.ld4:
        tag, seg, end = addr[node]
        pins.append(f"LD 4 {tag} {seg} {end} {_full(z.real)} {_full(z.imag)} 0")
    excite = []
    for node, src in driven.items():
        tag, seg, end = addr[node]
        v = complex(src.voltage)
        excite.append(f"EX 0 {tag} {seg} {end} {_full(v.real)} {_full(v.imag)}")

    name = title or f"{type(builder).__module__}.{type(builder).__qualname__}"
    header = [
        f"CM antennaknobs NEC-5 station deck: {card_text(name)}",
        f"CM NT/TL station cards valid at {freq_mhz:g} MHz only",
        "CM (NT values and the lambda/4 transformer lines are computed at it)",
    ]
    if phantoms:
        header.append(
            f"CM wire {ptag} is the phantom wire for virtual nodes, each knot "
            f"pinned open by LD 4 {PIN_OHMS:g} ohm"
        )
    for kn in knots:
        where = f"knot {ptag}/{kn.segment}" if kn.segment else "real knot"
        header.append(
            f"CM {where}: node {card_text(', '.join(kn.nodes))}, pin moves Z "
            f"{kn.effect:.1e}"
        )
    out = header + lines[1:]
    ge = next(i for i, ln in enumerate(out) if ln.startswith("GE "))
    out[ge:ge] = phantom_gw
    fr = next(i for i, ln in enumerate(out) if ln.startswith("FR "))
    # NEC drops a voltage source read before a network card, so every NT/TL
    # precedes every EX (`nec_export._deck_text`).
    out[fr:fr] = pins + net_lines + excite
    text = "\n".join(out) + "\n"
    return StationDeck(
        text=text,
        freq_mhz=freq_mhz,
        knots=tuple(knots),
        z_composite=z_composite,
        z_cards=z_cards,
    )


def export_nec5_station(builder, **kwargs) -> str:
    """The deck text of `station_deck` (same arguments)."""
    return station_deck(builder, **kwargs).text
