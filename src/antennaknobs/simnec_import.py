"""Import a SimNEC (``.ssn``) circuit as antennaknobs wire geometry.

The read-side twin of :mod:`antennaknobs.simnec_export`: where ``export_ssn``
emits a SimNEC circuit for cross-validation, ``parse_ssn`` consumes one — so an
antenna modeled (or round-tripped) in SimNEC can be loaded as a data-driven
design, the same way ``read_nec`` loads a NEC card deck.

A ``.ssn`` is XML: a ``<CIRCUIT>`` of ``<element>``s. The antenna lives in a
NETWORK element's escape-hatch ``<equ>`` script — SimNEC's NEC-portal daemon
language — with the NEC cards between ``NEC2`` and ``NECEND``:

    P1 w1 gnd;                         // circuit ports (structural, skipped)
    P2 w2 gnd;
    NECUnits meters, meters;
    SommerfeldGround(0.0303, 20);      // (mhos, dielectric) == (sigma, eps_r)
    NECOptions.mhosPerMeter = 0;       // 0 = perfect wires
    NECOptions.segmentsPerWavelength = 120;
    NEC2
    GW 1 ...
    EX 0 1 6 0 1. 0.
    NECEND

``parse_ssn`` extracts that block, hands the cards to
:func:`antennaknobs.nec_import.parse_nec` (so everything the NEC importer can
model — geometry transforms, EX feeds, lumped LD loads with ``network=True`` —
works identically), and translates the daemon directives back into antennaknobs
terms: the ground call becomes an ``export_nec``-style ground spec, wire
conductivity and SimNEC's re-mesh density surface as fields. ``NECUnits`` is
read and NOT applied: in SimNEC it only sets the units wire dimensions are
DISPLAYED in, and the NEC cards in the block are metres whatever it says
(AK#1625). AC6LA's `NECUnits inches, inches;` Yagi, read as a scale, was solved
as a 1/80-wave stub: 0.19 - j13972 ohms against SimNEC's 13.26 - j7.385.

Segment counts are the deck's GW counts, and a ``$GW_<tag>.JamSegments(N)``
sets that wire's count to exactly N (AK#1679). SimNEC's own re-mesh
(``NECOptions.segmentsPerWavelength`` and its segmentation pass) is not
emulated, and ``SsnCircuit.mesh_note()`` says so.

The solve frequency comes from the GENERATOR element's ``MHz`` — in SimNEC the
deck's ``FR`` card is advisory; the Generator drives the solve — and an armed
(``doSweep y``) Generator sweep surfaces as ``sweep=(lo, hi)``, with the
frequencies it visits in ``sweep_points``: ``points`` values over from..to for
``lin`` / ``log`` spacing, or the values of its sweep expression for ``expr``
(``14 : 14.35 : 0.025``, AK#1679).

Station circuits (issue #604's element set)
-------------------------------------------
A station ``.ssn`` carries circuit elements between the antenna NETWORK block
and the GENERATOR — SimNEC's cascade, saved right-to-left (LOAD … antenna …
chain … GENERATOR). Those elements land in ``SsnCircuit.chain`` in
generator→antenna order, and ``SsnCircuit.network()`` translates them back
into the app's port-network branches — the inverse of the station exporter's
branch→element mapping, element for element:

    SERIES_TLINE                      -> TL       (Zo / VFnom / ft, and the
                                         k1·sqrt(f) + k2·f dB/100 ft matched-loss
                                         coefficients — the same convention;
                                         Mdl simplified's one /100f @frq point
                                         becomes k1, exact at @frq, AK#1679)
    SERIES_IND / SERIES_CAP           -> TwoPort  (H / F, Q -> ql / qc)
    SERIES_Z                          -> Admittance (2-port, y = 1/(R + jX),
                                         frequency-independent; AK#1679)
    SHUNT_IND / SHUNT_CAP             -> Shunt    (H / F, Q -> ql / qc)
    TRANSFORMER2 (Mdl ideal)          -> Transformer (n = 1/N: SimNEC's N is
                                         the antenna:generator voltage ratio,
                                         validated on 5.1a0 — see export)
    XMATCH (mode auto)                -> station.l_network_tuner(tune_to=...),
                                         the L tuner that tunes itself (AK#1646):
                                         R/X or the generator Zo, MHz (else the
                                         generator's), pass -> mode, the side
                                         "auto" (SimNEC picks it), Qc / Ql

The chain hangs between a virtual generator-side node (``"rig"``, the
``Driven`` source: SimNEC's GENERATOR) and the deck's fed wire (``"feed"``,
the antenna's own terminals), and each block sits on a node of its own named
after its label (AK#1679, AK#1681), so every block SimNEC reports an impedance
at is a measurement plane here too. A lumped load on a wire is SimNEC's
``R<k> (<impedance>) a b;`` component attached by ``NECSource({a,b},
$GW_<tag>, <percent>)`` (the exporter's spelling since AK#1683: SimNEC ignores
LD cards in the block); one with constant values at a segment centre reads as
the LD card it stands for and translates through ``parse_nec`` as usual. An LD
card inside the block is still read, although SimNEC itself ignores it.
Semantics notes, shared
with the exporter: SimNEC quotes component ``Q`` at a frequency (``@MHz``)
while ``ql``/``qc`` are frequency-independent, so the import is exact at the
quoted frequency and Q-model-approximate across a sweep; ``Q = 0`` reads as
the ideal (lossless) component; ``VFnom`` is taken at face value (SimNEC's
"simplified" line model can compute a different effective vf from its
dielectric params — the handoff doc's gotcha 2).

A chain element outside that set is recorded in ``other_elements`` (see
``skipped_note()``), and ``network()`` refuses to build a station around it —
importing the antenna while silently dropping a tuner element would be a
confidently-wrong circuit. Elements outside the generator→antenna span, and
daemon statements the importer does not understand (``ignored_directives``),
are recorded the same way. The exporter's own scaffold (the open LOAD
termination and the 50 Ohm GENERATOR) is recognised and not reported, and so
is SimNEC's own unused 0 Ohm ``NotUsed`` LOAD on the antenna block (AK#1679).
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace

from . import network as _net
from .design_data import read_data
from .nec_import import NecDeck, parse_nec
from .network import Composite
from .schematic import series

__all__ = ["SsnCircuit", "SsnElement", "parse_ssn", "read_ssn"]


# The exporter's scaffold LOAD is a 1e9 Ohm open; treat anything this large as
# "no termination" rather than a circuit element worth reporting.
_OPEN_OHMS = 1e8

M_PER_FT = 0.3048

# Station chain elements network() can translate (issue #604's captured set).
_SHUNT_CHAIN = frozenset({"SHUNT_IND", "SHUNT_CAP"})
_SERIES_CHAIN = frozenset(
    {"SERIES_TLINE", "SERIES_IND", "SERIES_CAP", "SERIES_Z", "TRANSFORMER2"}
)
# SimNEC's LC matching component. A series-position element: its generator
# side and load side are two nodes, like a series element's (AK#1646).
_MATCH_CHAIN = frozenset({"XMATCH"})
_CHAIN_TYPES = _SHUNT_CHAIN | _SERIES_CHAIN | _MATCH_CHAIN

_NEC2_LINE = re.compile(r"^NEC2\s*$")
_NECEND_LINE = re.compile(r"^NECEND\s*$")
_PORT_DECL = re.compile(r"^P\d+\s+\S", re.IGNORECASE)
_SOMMERFELD = re.compile(
    r"^SommerfeldGround\s*\(\s*([^\s,()]+)\s*,\s*([^\s,()]+)\s*\)$", re.IGNORECASE
)
_PERFECT = re.compile(r"^PerfectGround\s*\(\s*\)$", re.IGNORECASE)
# SimNEC's own MININEC ground (its NECPortal manual, "NECGrounds"), with the
# SommerfeldGround argument order: (mhos, dielectric).
_MININEC = re.compile(
    r"^MiniNECGround\s*\(\s*([^\s,()]+)\s*,\s*([^\s,()]+)\s*\)$", re.IGNORECASE
)
_NECUNITS = re.compile(r"^NECUnits\s+(.+)$", re.IGNORECASE)
_NECOPTION = re.compile(r"^NECOptions\.(\w+)\s*=\s*(\S+)$", re.IGNORECASE)
# `$GW_<tag>.JamSegments(N)`: SimNEC names each NEC2-block GW wire `$GW_<tag>`,
# and JamSegments fixes that wire's count (the NECPortal manual, "Suggesting
# Wire Segmentation"). Applied exactly (AK#1679).
_JAM = re.compile(r"^\$GW_(\d+)\s*\.\s*JamSegments\s*\(\s*(\d+)\s*\)$", re.IGNORECASE)
# A lumped load on a GW wire, the way SimNEC places one (AK#1683): an N-block
# `R` component carrying the impedance between two nodes, and a NECSource
# attaching those nodes to `$GW_<tag>` at a percentage of its length.
_R_COMPONENT = re.compile(r"^R\d+\s*\((.*)\)\s+(\w+)\s+(\w+)$")
_LOAD_SOURCE = re.compile(
    r"^(?:dcl\s+\w+\s*=\s*)?NECSource\s*\(\s*\{\s*(\w+)\s*,\s*(\w+)\s*\}\s*,"
    r"\s*\$GW_(\d+)\s*,\s*([^\s,()]+)\s*\)$",
    re.IGNORECASE,
)
# SimNEC's W7EL (EZNEC) insulation, the circuit default, as the exporter writes
# it (AK#1683) under Ward's own engine guard, whose `if` / `else` /
# `errorOutln` lines are structure, not directives.
_W7EL = re.compile(
    r'^NECOptions\.Insulation\s*\(\s*"W7EL"\s*,\s*([^\s,()]+)\s*,'
    r"\s*([^\s,()]+)\s*,\s*([^\s,()]+)\s*\)$",
    re.IGNORECASE,
)
_ENGINE_GUARD = re.compile(
    r"^(?:if\s*\(\s*NECOptions\.Engine\s*==\s*2\s*\)|else|errorOutln\s*\(.*\))$"
)
_NUM = r"[0-9.]+(?:[eE][-+]?\d+)?[a-zA-Z\u00b5]?"
_Z_EXPR = re.compile(rf"^({_NUM})\s*([+-])\s*j\s*\*\s*({_NUM})$")
_LC_TERM = re.compile(rf"^([LC])\(\s*({_NUM})\s*\)$")


@dataclass(frozen=True)
class SsnElement:
    """One circuit element from the station chain: its SimNEC ``<type>``,
    ``<sweeperLabel>``, and top-level params as (name, value) text pairs."""

    typ: str
    label: str | None
    params: tuple[tuple[str, str | None], ...]

    def get(self, key: str, default: str | None = None) -> str | None:
        for n, v in self.params:
            if n == key:
                return v
        return default


# SimNEC writes component values with SI suffixes ("37.52p", "731.9n", "2K":
# AC6LA's C1-L1 circuit, AK#1645). The set is SimNEC's own, from the SimNEC
# Manual's "Setting Parameter Values" table (December 2025): a f p n u m k/K M G
# T P, as SI, so `m` is milli and `M` mega (not SPICE's M = milli). The same
# table's `g` is "AWG in inches", a wire GAUGE, not giga; wire diameters are a
# different path from these element values, and a `g` here is refused.
_SI_SUFFIX = {
    "a": 1e-18,
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "\u00b5": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
    "P": 1e15,
}


def _chain_f(el: SsnElement, key: str, default: float | None = None) -> float:
    """A chain element's numeric parameter; ``default`` for an absent one
    (None = required). A trailing SI suffix scales it (see `_SI_SUFFIX`)."""
    raw = el.get(key)
    where = f"{el.typ} element" + (f" {el.label}" if el.label else "")
    if raw is None:
        if default is None:
            raise ValueError(f"{where}: missing its {key!r} parameter")
        return default
    text = raw.strip()
    scale = 1.0
    if text and text[-1] in _SI_SUFFIX:
        scale, text = _SI_SUFFIX[text[-1]], text[:-1]
    try:
        return float(text) * scale
    except ValueError:
        raise ValueError(f"{where}: bad {key!r} value {raw!r}") from None


def _chain_q(el: SsnElement) -> float | None:
    """SimNEC's component ``Q`` (quoted at ``@MHz``) as ``ql``/``qc``:
    frequency-independent, so exact at the quoted frequency. ``Q = 0`` (or
    absent) is the ideal component -> None, the SimSmith convention the
    exporter also uses."""
    q = _chain_f(el, "Q", default=0.0)
    return q if q > 0.0 else None


def _si_float(token: str) -> float:
    """A number with an optional trailing SI suffix (`_SI_SUFFIX`)."""
    text = token.strip()
    scale = 1.0
    if text and text[-1] in _SI_SUFFIX:
        scale, text = _SI_SUFFIX[text[-1]], text[:-1]
    return float(text) * scale


def _load_card_values(expr: str) -> tuple[int, float, float, float] | None:
    """An N-block impedance expression as LD card values ``(type, F1, F2,
    F3)``: type 0 series R/L/C, 1 parallel, 4 a fixed R + jX (AK#1683). Only
    the spellings the exporter writes and constant values are read — a bare
    number (ohms), ``L(henries)``, ``C(farads)``, joined all by ``+`` or all
    by ``|||``, or ``R + j*X`` / ``R - j*X``; None for anything else
    (variables, a Q argument), which the caller leaves unapplied."""
    expr = expr.strip()
    m = _Z_EXPR.match(expr)
    if m:
        x = _si_float(m.group(3))
        return 4, _si_float(m.group(1)), -x if m.group(2) == "-" else x, 0.0
    parallel = "|||" in expr
    terms = [t.strip() for t in expr.split("|||" if parallel else " + ")]
    legs: dict[str, float] = {}
    for t in terms:
        m = _LC_TERM.match(t)
        kind, token = (m.group(1), m.group(2)) if m else ("R", t)
        if kind in legs or not re.fullmatch(_NUM, token):
            return None
        legs[kind] = _si_float(token)
    return (
        1 if parallel else 0,
        legs.get("R", 0.0),
        legs.get("L", 0.0),
        legs.get("C", 0.0),
    )


def _shunt_branch(el: SsnElement, node: str):
    if el.typ == "SHUNT_IND":
        return _net.Shunt(port=node, l=_chain_f(el, "H"), ql=_chain_q(el))
    return _net.Shunt(port=node, c=_chain_f(el, "F"), qc=_chain_q(el))


# SimNEC's `/100<unit>` loss key: dB per 100 of the unit, as feet per unit.
_LOSS_PER_100 = {"f": 1.0, "m": 1.0 / M_PER_FT}


def _tline_loss(el: SsnElement) -> tuple[float, float]:
    """A SERIES_TLINE's matched loss as TL's ``(k1, k2)``, dB/100 ft at
    ``k1*sqrt(f_MHz) + k2*f_MHz`` (AK#1679).

    SimNEC's ``Mdl`` picks the loss model (its manual, "The Simplified Model"
    and "The K0K1K2 Model"):

    - ``simplified`` (SimNEC's default) takes ONE loss point, ``/100f`` dB per
      100 ft at ``@frq`` MHz, and scales it with the square root of
      frequency: "SimSmith uses these parameters to compute a 'k1' ... K0 and
      K2 are assumed 0" (SimSmith Primer). So ``k1 = loss / sqrt(@frq)``,
      exact at ``@frq``, and the stored k0/k1/k2 are not what it solves. A
      line given per 100 m (``/100m``) is converted to per 100 ft.
    - ``k0k1k2`` takes the three coefficients as written (the station
      exporter pins this model). k0, a constant dB term, has no TL
      equivalent and is refused.
    - No ``Mdl`` at all reads as ``k0k1k2``, as older station exports did.

    Any other model (a named commercial line from SimNEC's database) is
    refused by name rather than imported lossless. SimNEC runs even the
    simplified loss through AC6LA's line model, which also bends the
    effective Zo and velocity factor at low frequency; TL keeps ``Zo`` and
    ``VFnom`` at face value, so the import is exact in loss at ``@frq`` and
    approximate in Zo off it."""
    where = "SERIES_TLINE" + (f" {el.label}" if el.label else "")
    mdl = (el.get("Mdl") or "k0k1k2").strip()
    if mdl.lower() == "simplified":
        keys = [n for n, _v in el.params if n and n.startswith("/100")]
        if len(keys) != 1:
            raise ValueError(
                f"{where}: the simplified line model needs one '/100<unit>' "
                f"loss, found {keys or 'none'}"
            )
        unit = keys[0][4:]
        if unit not in _LOSS_PER_100:
            raise ValueError(
                f"{where}: loss {keys[0]!r} is per 100 {unit!r}; only per 100 "
                "feet ('/100f') or metres ('/100m') are read"
            )
        loss = _chain_f(el, keys[0], default=0.0) / _LOSS_PER_100[unit]
        if loss == 0.0:
            return 0.0, 0.0
        frq = _chain_f(el, "@frq", default=0.0)
        if frq <= 0.0:
            raise ValueError(
                f"{where}: a {loss:g} dB/100 ft loss needs the frequency it "
                "is quoted at, and '@frq' is missing or zero"
            )
        return loss / frq**0.5, 0.0
    if mdl.lower() != "k0k1k2":
        raise ValueError(
            f"{where}: line model {mdl!r} is not translated; only 'simplified' "
            "and 'k0k1k2' are. Switch the line to one of those in SimNEC "
            "(k0k1k2 keeps a database line's coefficients)"
        )
    if _chain_f(el, "k0", default=0.0) != 0.0:
        raise ValueError(
            f"{where}: a constant k0 loss term has no TL equivalent — TL "
            f"matched loss is k1*sqrt(f) + k2*f (dB/100 ft)"
        )
    return _chain_f(el, "k1", default=0.0), _chain_f(el, "k2", default=0.0)


def _series_z(el: SsnElement, a: str, b: str):
    """A SERIES_Z — SimNEC's fixed complex impedance, ``ohms`` + j``johms``,
    in series — as the 2-port ``Admittance`` of a series element,
    y = 1/(R + jX) (AK#1679). Both hold that R + jX at every frequency. A
    ``file`` (measured data) and R = X = 0 (an ideal short,
    with no admittance) are refused by name."""
    where = "SERIES_Z" + (f" {el.label}" if el.label else "")
    src = (el.get("file") or "").strip()
    if src and src != "<none>":
        raise ValueError(
            f"{where}: takes its impedance from the file {src!r}, which is not "
            "imported; give it ohms and johms instead"
        )
    z = complex(_chain_f(el, "ohms", default=0.0), _chain_f(el, "johms", default=0.0))
    if z == 0:
        raise ValueError(
            f"{where}: R = X = 0 is an ideal short with no admittance; delete "
            "the element instead"
        )
    y = 1.0 / z
    return _net.Admittance(ports=(a, b), y=((y, -y), (-y, y)))


def _series_branch(el: SsnElement, a: str, b: str):
    """The network branch for one series chain element, entered generator-side
    at ``a`` — the inverse of the station exporter's ``_series_elements``."""
    if el.typ == "SERIES_TLINE":
        k1, k2 = _tline_loss(el)
        return _net.TL(
            a=a,
            b=b,
            z0=_chain_f(el, "Zo"),
            length=_chain_f(el, "ft") * M_PER_FT,
            vf=_chain_f(el, "VFnom", default=1.0),
            k1=k1,
            k2=k2,
        )
    if el.typ == "SERIES_IND":
        return _net.TwoPort(a=a, b=b, l=_chain_f(el, "H"), ql=_chain_q(el))
    if el.typ == "SERIES_CAP":
        return _net.TwoPort(a=a, b=b, c=_chain_f(el, "F"), qc=_chain_q(el))
    if el.typ == "SERIES_Z":
        return _series_z(el, a, b)
    # TRANSFORMER2 — only the ideal ratio maps onto Transformer, exactly as
    # only the ideal Transformer maps onto TRANSFORMER2 on export.
    mdl = (el.get("Mdl") or "").strip().lower()
    if mdl != "ideal":
        raise ValueError(
            f"TRANSFORMER2 {el.label or ''}: model {el.get('Mdl')!r} is not "
            f"the ideal ratio; only 'Mdl ideal' translates to Transformer"
        )
    # SimNEC's N is the ANTENNA:generator ratio — validated live on 5.1a0
    # (2026-08-07, PR #696 signoff: an n=2 step-up emitted as N=2 read Z/4
    # at the generator), and the exporter emits the reciprocal accordingly.
    # Our Transformer(a, b, n) has v_a = n*v_b entered generator-side, so
    # n = 1/N.
    n = _chain_f(el, "N")
    if n == 0:
        raise ValueError(
            f"TRANSFORMER2 {el.label or ''}: N = 0 has no impedance mapping"
        )
    return _net.Transformer(a=a, b=b, n=1.0 / n)


@dataclass(frozen=True)
class SsnCircuit:
    """A parsed ``.ssn``: the antenna block's NEC deck plus the circuit-level
    settings SimNEC keeps outside the deck (solve frequency, ground, mesh)."""

    deck: NecDeck
    # GENERATOR MHz — the authoritative solve frequency (the deck's FR card is
    # advisory in SimNEC; it is still exposed as ``deck.freq_mhz``).
    freq_mhz: float | None
    # Armed (doSweep y) Generator frequency sweep, MHz: (lowest, highest)
    # frequency the sweep visits. None = no sweep armed (or one not read —
    # see ``sweep_note``).
    sweep: tuple[float, float] | None
    # Ground translated from the daemon call, in export_ssn's own spec:
    # None (free space), "pec", ("finite", eps_r, sigma), or
    # ("mininec", eps_r, sigma) for MiniNECGround (AK#1655).
    ground: None | str | tuple
    # NECOptions.mhosPerMeter, S/m — feed to WireSpec(conductivity=...).
    # None when absent or 0 (perfect wires).
    conductivity: float | None
    # NECOptions.segmentsPerWavelength — SimNEC's re-mesh density. Not
    # emulated (AK#1679): the engines keep the deck's segment counts, and
    # `mesh_note()` says so.
    seg_per_wl: int | None
    # GENERATOR reference impedance (Zo), ohms.
    gen_zo: float | None
    # The block display name — the script's first // comment.
    name: str | None
    # The station chain: circuit elements between the GENERATOR and the
    # antenna NETWORK block, in generator→antenna order. Translated into
    # port-network branches by network(); empty for an antenna-only file.
    chain: tuple[SsnElement, ...] = ()
    # Circuit element types the import cannot translate (chain elements
    # outside the captured set, extra blocks — anything beyond the antenna,
    # the station chain, and the exporter scaffold).
    other_elements: tuple[str, ...] = ()
    # Daemon statements not understood, verbatim.
    ignored_directives: tuple[str, ...] = ()
    # The frequencies the armed sweep evaluates, MHz, in SimNEC's order: its
    # lin / log spacing of `points` over from..to, or the values its `expr`
    # names (AK#1679). None with no sweep, or a lin/log sweep with no count.
    sweep_points: tuple[float, ...] | None = None
    # Why an armed sweep was not read, when it was not (AK#1679).
    sweep_note: str | None = None
    # The armed sweep's grid (AK#1682), for the app's sweep: ``("lin", step
    # MHz)`` or ``("log", total points)``, the shape ``NecDeck.freq_grid``
    # uses. An ``expr`` sweep has one only when it is a single ``from:to:step``
    # range; several ranges or listed values have no one spacing, and leave
    # the density to the app.
    sweep_grid: tuple[str, float] | None = None

    def skipped_note(self) -> str | None:
        """One human-readable sentence naming what the file carries that the
        import leaves behind — untranslated circuit elements and daemon
        directives, plus the deck-level record from ``NecDeck.skipped_note``.
        Same use as the NEC importer's: put it under ``ui_params["notes"]``.
        None when nothing was left behind."""
        parts = []
        if self.other_elements:
            parts.append(
                "SimNEC circuit elements not imported: "
                + ", ".join(self.other_elements)
            )
        if self.ignored_directives:
            parts.append(
                "NEC-portal directives not applied: "
                + "; ".join(self.ignored_directives)
            )
        if self.sweep_note:
            parts.append(self.sweep_note)
        for el in self.chain:
            if el.typ in _MATCH_CHAIN and _chain_f(el, "MHz", default=0.0) <= 0.0:
                # AK#1646: SimNEC retunes an MHz = 0 XMATCH at every
                # frequency; the app's tuner tunes once and holds.
                at = (
                    f"{self.freq_mhz:g} MHz"
                    if self.freq_mhz
                    else "the design frequency"
                )
                parts.append(
                    f"XMATCH {el.label or ''} retunes at every frequency in "
                    f"SimNEC; here the tuner tunes once, at {at}, and holds"
                )
        note = None
        if parts:
            body = "; ".join(parts)
            note = body[0].upper() + body[1:] + "."
        deck_note = self.deck.skipped_note()
        if note and deck_note:
            return f"{note} {deck_note}"
        return note or deck_note

    def mesh_note(self) -> str:
        """Why SimNEC's numbers for this file differ from ours by mesh, and
        how to compare on one mesh (AK#1679). Always given: SimNEC re-meshes
        every wire before it solves (its own segmentation pass, not a density
        formula), and antennaknobs does not emulate that — it solves the GW
        counts as written, and each ``JamSegments(N)`` as exactly N."""
        spw = (
            f" (NECOptions.segmentsPerWavelength = {self.seg_per_wl})"
            if self.seg_per_wl
            else ""
        )
        jammed = (
            f", and the {len(self.deck.pinned_wires)} JamSegments "
            f"wire{'s' if len(self.deck.pinned_wires) != 1 else ''} at "
            "exactly the jammed count"
            if self.deck.pinned_wires
            else ""
        )
        return (
            f"SimNEC re-meshes the wires before it solves{spw}; this import "
            f"solves the file's own segment counts{jammed}, so SimNEC's "
            "numbers differ from these by mesh. For a same-mesh comparison, "
            "import lastConstructedNEC.nec from ~/.SimNEC/<version>/ — the "
            "deck SimNEC actually solved."
        )

    def network(self, *, rig_port: str = "rig"):
        """The full circuit as a ``network.Network``, ready to return from
        ``build_network()``: the deck's translated branches and feed (via
        ``NecDeck.network()``, so parse with ``network=True``), plus the
        station chain re-hung between a virtual generator-side ``rig_port``
        node — where the ``Driven`` source moves to — and the deck's fed
        wire. An antenna-only file returns the deck network unchanged.

        The measurement planes follow SimNEC's blocks (AK#1679, AK#1681):
        ``rig`` is the GENERATOR, ``feed`` (the deck's fed port) is the
        antenna's own terminals, and every chain block gets a node of its
        own, named after its label, at the block's GENERATOR side — the
        point SimNEC reports under that block, the impedance looking into it
        and everything antenna-ward. A series block runs from its node to
        the next block's; a shunt block hangs on its node, which ideal
        pass-throughs join to its neighbours (`_through`). So a trailing
        shunt (C1 after L1, generator→antenna) sits upstream of ``feed``,
        and ``feed`` reads the antenna alone.

        Raises ``ValueError`` for a chain the app cannot faithfully rebuild:
        an element outside the captured set (see ``other_elements``), a
        non-ideal TRANSFORMER2, a k0 loss term, or a deck without exactly
        one voltage feed to attach the chain to."""
        net = self.deck.network()
        if not self.chain:
            return net
        bad = sorted({el.typ for el in self.chain if el.typ not in _CHAIN_TYPES})
        if bad:
            raise ValueError(
                f"station chain carries element(s) with no network "
                f"translation: {', '.join(bad)} — importing the antenna "
                f"while dropping them would misrepresent the circuit"
            )
        if len(net.sources) != 1 or not isinstance(net.sources[0], _net.Driven):
            raise ValueError(
                "a station chain attaches between the generator and one "
                "voltage-driven feed; this deck does not have exactly one "
                "EX voltage source"
            )
        src = net.sources[0]
        feed_port = src.port
        ports = dict(net.ports)
        branches = list(net.branches)
        if rig_port in ports:
            raise ValueError(
                f"rig_port {rig_port!r} collides with a deck port name — "
                f"pass a different rig_port"
            )
        ports[rig_port] = _net.PortVirtual(rig_port)

        nodes = _block_nodes(self.chain, taken=set(ports))
        # `at` is the node the next block attaches to. `pending` is a series
        # block whose antenna side is not wired yet: the next node closes it,
        # so two series blocks in a row meet with no pass-through between.
        at, pending, n_thru = rig_port, None, 0

        def attach(node):
            nonlocal pending, n_thru
            if pending is None:
                n_thru += 1
                branches.append(_through(at, node, n_thru))
                return
            el, a, index = pending
            pending = None
            if el.typ in _MATCH_CHAIN:
                branches.append(self._tuner(el, a, node, index))
            else:
                branches.append(_series_branch(el, a, node))

        for index, (el, node) in enumerate(zip(self.chain, nodes, strict=True), 1):
            ports[node] = _net.PortVirtual(node)
            attach(node)
            if el.typ in _SHUNT_CHAIN:
                branches.append(_shunt_branch(el, node))
            else:
                pending = (el, node, index)
            at = node
        attach(feed_port)
        return _net.Network(
            ports=ports,
            branches=branches,
            sources=[_net.Driven(port=rig_port, voltage=src.voltage)],
        )

    def _tuner(self, el: SsnElement, rig: str, out: str, k: int):
        """An XMATCH as antennaknobs' own self-tuning L tuner (AK#1646):
        `station.l_network_tuner(tune_to=...)`, from SimNEC's parameters
        (its manual, "The LC Matching Component")."""
        from .station import l_network_tuner

        where = "XMATCH element" + (f" {el.label}" if el.label else "")
        mode = (el.get("mode") or "auto").strip()
        if mode != "auto":
            raise ValueError(
                f"{where}: {mode!r} mode is not translated, only 'auto'. "
                "Replace it with the explicit SERIES_IND / SHUNT_CAP (or "
                "SERIES_CAP / SHUNT_IND) elements it stands for"
            )
        pass_ = (el.get("pass") or "low").strip().lower()
        if pass_ not in ("low", "high"):
            raise ValueError(f"{where}: pass {pass_!r} is not 'low' or 'high'")
        r = _chain_f(el, "R", default=0.0)
        x = _chain_f(el, "X", default=0.0)
        if x != 0.0:
            raise ValueError(
                f"{where}: a complex target (R {r:g}, X {x:g}) is not translated; "
                "SimNEC's manual does not say whether it presents R + jX or its "
                "conjugate"
            )
        if r == 0.0:
            if self.gen_zo is None:
                raise ValueError(
                    f"{where}: matches to the generator's Zo, and this file's "
                    "GENERATOR carries none"
                )
            r = self.gen_zo
        mhz = _chain_f(el, "MHz", default=0.0)
        if mhz <= 0.0:
            # SimNEC's MHz = 0 retunes at every generator frequency; the app's
            # tuner holds its tune (skipped_note says so), so it tunes at the
            # generator's own frequency, where SimNEC's would be at the start.
            mhz = self.freq_mhz or 0.0
        qc = _chain_f(el, "Qc", default=0.0)
        ql = _chain_f(el, "Ql", default=0.0)
        comp = l_network_tuner(
            tune_to=r,
            tune_at_mhz=mhz if mhz > 0.0 else None,
            mode=pass_,
            # SimNEC picks the side itself, by the same rule as "auto".
            shunt_at="auto",
            qc=qc if qc > 0.0 else None,
            ql=ql if ql > 0.0 else None,
        )
        name = (el.label or f"tuner{k}").replace(".", "_")
        return _net.Instance(name, comp, rig=rig, out=out)


def _block_nodes(chain, taken: set[str]) -> list[str]:
    """One node name per chain block, generator→antenna: its SimNEC label
    (AK#1679), made a usable port name — dots (the network's namespace
    separator) and spaces become ``_`` — or ``<type><index>`` for a block
    with none. A name another port already has gets ``_2``, ``_3``, ... ."""
    out: list[str] = []
    for index, el in enumerate(chain, 1):
        base = re.sub(r"[.\s]+", "_", (el.label or "").strip()).strip("_")
        base = base or f"{el.typ.lower()}{index}"
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base}_{n}"
        taken.add(name)
        out.append(name)
    return out


# An ideal pass-through between two block nodes (AK#1679): SimNEC draws its
# blocks joined by bare wire, and a shunt block's node must still be a node of
# its own, or a plane on one side would carry the shunt on the other. The
# ideal 1:1 `Transformer` is the network's zero-impedance through-connection
# (its docstring: "n = 1 (with no loss) is an ideal through-connection"); an
# alias would MERGE the nodes, which is the defect. It draws as a wire.
_THROUGH = Composite(
    ports=("a", "b"),
    branches=(_net.Transformer(a="a", b="b", n=1.0),),
    schematic=(series("short"),),
)


def _through(a: str, b: str, k: int):
    return _net.Instance(f"through{k}", _THROUGH, a=a, b=b)


def _fnum(token: str, where: str, what: str) -> float:
    try:
        return float(token.rstrip(";"))
    except ValueError:
        raise ValueError(f"{where}: bad {what} value {token!r}") from None


# SimNEC's `Conductivities.<metal>` names (AK#1647), as SimNEC defines them:
# each is 1/resistivity in S/m, from these resistivities in ohm-metres, and
# `perfect` is 0, which `mhosPerMeter` reads as a perfect wire. SimNEC's release
# notes say the table was "set to match EZNEC's", and copper's 5.7471e7 is
# EZNEC's own figure (WA7ARK's EZNEC deck writes `LD 5 ... 5.7471E+7`).
_RESISTIVITY_OHM_M = {
    "silver": 1.59e-8,
    "copper": 1.74e-8,
    "gold": 2.44e-8,
    "aluminum": 4.0e-8,
    "zinc": 6.0e-8,
    "tin": 1.14e-7,
    "chromium": 1.25e-7,
    "lowcarbonsteel": 1.43e-7,
    "lead": 2.2e-7,
    "stainless": 6.9e-7,
}
_CONDUCTIVITY_NAME = re.compile(r"^Conductivities\.(\w+)$", re.IGNORECASE)


def _mhos(token: str, where: str, what: str) -> float:
    """A wire conductivity in S/m: a number, or a SimNEC `Conductivities.<name>`
    (0 = a perfect wire either way)."""
    m = _CONDUCTIVITY_NAME.match(token.rstrip(";"))
    if not m:
        return _fnum(token, where, what)
    name = m.group(1).lower()
    if name == "perfect":
        return 0.0
    if name not in _RESISTIVITY_OHM_M:
        known = ", ".join(["perfect", *_RESISTIVITY_OHM_M])
        raise ValueError(
            f"{where}: {what} names Conductivities.{m.group(1)}, which SimNEC "
            f"does not define (it has {known})"
        )
    return 1.0 / _RESISTIVITY_OHM_M[name]


class _Script:
    """The NEC-portal ``<equ>`` script pulled apart: NEC cards, translated
    directives, the block name, and whatever was not understood."""

    def __init__(self, text: str, where: str):
        self.cards: list[str] = []
        self.ground: None | str | tuple = None
        self.conductivity: float | None = None
        self.seg_per_wl: int | None = None
        # `NECUnits`, as written: SimNEC's DISPLAY units, never a scale on the
        # cards (AK#1625). Kept for what the file said, not for the geometry.
        self.display_units: tuple[str, ...] = ()
        self.name: str | None = None
        self.ignored: list[str] = []
        # `$GW_<tag>.JamSegments(N)`: GW tag -> (segment count, the statement
        # as written) (AK#1679).
        self.jam: dict[int, tuple[int, str]] = {}
        # Lumped loads on GW wires (AK#1683): the `R` components by their
        # node pair, and the NECSource statements attaching them.
        self._r_components: dict[tuple[str, str], tuple[str, str]] = {}
        self._load_sources: list[tuple[re.Match, str]] = []
        # NECOptions.Insulation("W7EL", ...): (radial thickness m, eps_r).
        self.insulation: tuple[float, float] | None = None
        in_cards = False
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if in_cards:
                if _NECEND_LINE.match(line):
                    in_cards = False
                elif not line.startswith("//") and line.split()[0].upper() != "EN":
                    # A stray EN inside the block would make parse_nec stop
                    # before the appended GS (units) / GE (ground) cards; the
                    # importer supplies its own EN.
                    self.cards.append(line)
                continue
            if line.startswith("//"):
                if self.name is None:
                    self.name = line[2:].strip() or None
                continue
            if _NEC2_LINE.match(line):
                in_cards = True
                continue
            # Directive line: drop a trailing // comment, then take the
            # ;-separated statements (the exporter writes one per line, but
            # the daemon language does not require that).
            for stmt in line.split("//", 1)[0].split(";"):
                stmt = stmt.strip()
                if stmt:
                    self._directive(stmt, where)
        if in_cards:
            raise ValueError(f"{where}: NEC2 block is missing its NECEND")
        self._apply_loads(where)

    def _apply_loads(self, where: str) -> None:
        """Each NECSource load (an `R` component on a `$GW_<tag>` wire,
        AK#1683) as the LD card it stands for, appended to the cards. SimNEC
        places the load at the percentage itself; here it must be a segment
        centre of the GW count, which is where the exporter puts it. A load
        between two centres is refused by name, never moved to the nearest;
        one whose value or wire cannot be read is left unapplied (and so
        reported), as is an `R` component no NECSource attaches."""
        counts: dict[int, list[int]] = {}
        for card in self.cards:
            parts = re.split(r"[\s,]+", card.strip())
            if parts[0].upper() == "GW" and len(parts) > 2:
                try:
                    counts.setdefault(int(parts[1]), []).append(int(parts[2]))
                except ValueError:
                    continue
        used: set[tuple[str, str]] = set()
        for m, stmt in self._load_sources:
            a, b, tag, pct_text = m.group(1), m.group(2), int(m.group(3)), m.group(4)
            key = (a, b) if (a, b) in self._r_components else (b, a)
            comp = self._r_components.get(key)
            values = _load_card_values(comp[0]) if comp else None
            n = counts.get(tag, [])
            try:
                pct = _si_float(pct_text)
            except ValueError:
                pct = None
            if values is None or len(n) != 1 or pct is None:
                self.ignored.append(stmt)
                continue
            used.add(key)
            seg_f = pct / 100.0 * n[0] + 0.5
            seg = round(seg_f)
            if not (1 <= seg <= n[0] and math.isclose(seg_f, seg, abs_tol=1e-6)):
                raise ValueError(
                    f"{where}: the load {comp[1]!r} sits at {pct_text}% of "
                    f"$GW_{tag}, which is not a segment centre of its "
                    f"{n[0]}-segment GW card; this import places a load on a "
                    "segment and does not re-mesh a wire to put one there"
                )
            ldtyp, f1, f2, f3 = values
            self.cards.append(f"LD {ldtyp} {tag} {seg} {seg} {f1!r} {f2!r} {f3!r}")
        for key, (_expr, stmt) in self._r_components.items():
            if key not in used:
                self.ignored.append(stmt)

    def _directive(self, stmt: str, where: str) -> None:
        if _PORT_DECL.match(stmt):
            return  # port declaration (P1 w1 gnd) — circuit structure only
        m = _JAM.match(stmt)
        if m:
            self.jam[int(m.group(1))] = (int(m.group(2)), stmt)
            return
        m = _W7EL.match(stmt)
        if m:
            thick = _fnum(m.group(1), where, "Insulation thickness")
            eps_r = _fnum(m.group(2), where, "Insulation permittivity")
            if _fnum(m.group(3), where, "Insulation loss tangent") != 0.0:
                raise ValueError(
                    f"{where}: {stmt!r} gives the insulation a loss tangent, "
                    "which the insulated-wire model here does not carry"
                )
            self.insulation = (thick, eps_r) if thick > 0.0 else None
            return
        if _ENGINE_GUARD.match(stmt):
            return
        m = _R_COMPONENT.match(stmt)
        if m:
            self._r_components[(m.group(2), m.group(3))] = (m.group(1), stmt)
            return
        m = _LOAD_SOURCE.match(stmt)
        if m:
            self._load_sources.append((m, stmt))
            return
        if _PERFECT.match(stmt):
            self.ground = "pec"
            return
        m = _SOMMERFELD.match(stmt)
        if m:
            # SommerfeldGround(mhos, dielectric) == (sigma, eps_r) — the
            # reverse of the ("finite", eps_r, sigma) spec, as on export.
            sigma = _fnum(m.group(1), where, "SommerfeldGround")
            eps_r = _fnum(m.group(2), where, "SommerfeldGround")
            self.ground = ("finite", eps_r, sigma)
            return
        m = _MININEC.match(stmt)
        if m:
            # Perfect-ground currents, the soil for the pattern alone: the
            # same ground as EZNEC's MININEC type (AK#1655).
            sigma = _fnum(m.group(1), where, "MiniNECGround")
            eps_r = _fnum(m.group(2), where, "MiniNECGround")
            self.ground = ("mininec", eps_r, sigma)
            return
        m = _NECUNITS.match(stmt)
        if m:
            units = [u for u in m.group(1).split(",") if u.strip()]
            if not 1 <= len(units) <= 2:
                raise ValueError(f"{where}: bad NECUnits directive {stmt!r}")
            self.display_units = tuple(u.strip() for u in units)
            return
        m = _NECOPTION.match(stmt)
        if m:
            option, value = m.group(1), m.group(2)
            key = option.lower()
            if key == "mhospermeter":
                mhos = _mhos(value, where, f"NECOptions.{option}")
                self.conductivity = mhos if mhos > 0.0 else None
                return
            if key == "segmentsperwavelength":
                self.seg_per_wl = int(_fnum(value, where, f"NECOptions.{option}"))
                return
            if key == "fieldstep":
                # SimNEC's far-field step in degrees ("the step used when
                # computing and displaying the far field", 2 by default): a
                # display resolution, not part of the model. Our far field
                # has its own grid and refines the peak (AK#1669), so no
                # solved number depends on it and it is not a directive we
                # failed to apply. Still parsed, so a malformed one refuses.
                _fnum(value, where, f"NECOptions.{option}")
                return
        self.ignored.append(stmt)


def _jam_segments(
    deck: NecDeck, jam: dict[int, tuple[int, str]], where: str
) -> tuple[NecDeck, list[str]]:
    """The deck with each ``$GW_<tag>.JamSegments(N)`` applied (AK#1679), and
    the statements that could not be, for the not-applied note.

    SimNEC re-meshes every wire by its own density before it solves;
    ``JamSegments(N)`` is how a file fixes one wire at N segments instead.
    Here the file's N is the count, exactly: it replaces the GW count, and the
    wire is PINNED there (`NecDeck.resegmented`), so no engine's parity rule
    moves it — the even-count rule is for counts the app chooses, not ones the
    file sets. Each attachment keeps the place the GW count gave it. One that
    is then not on a site of N (a centre feed on an odd count, on a knot
    engine) is fed where it is by splitting the wire at the feed (AK#1511),
    never snapped to a neighbouring site.

    ``JamSegments(0)`` is SimNEC's "auto-segment as usual", which here means
    the GW count stands, unpinned. A tag no GW card declares, or one several
    wires carry after the deck's transforms, names no one wire: that
    statement is returned unapplied rather than guessed at."""
    counts: dict[int, int] = {}
    unapplied: list[str] = []
    for tag, (n, stmt) in jam.items():
        hits = [i for i, w in enumerate(deck.wires) if w.tag == tag]
        if len(hits) != 1:
            unapplied.append(stmt)
        elif n > 0:
            counts[hits[0]] = n
    try:
        return deck.resegmented(counts), unapplied
    except ValueError as e:
        raise ValueError(f"{where}: JamSegments: {e}") from None


def _is_unused_termination(label: str | None, params: dict) -> bool:
    """SimNEC's own terminating LOAD on a NEC-portal circuit: labelled
    ``NotUsed``, 0 + j0 ohm, no file. The antenna block's P1 port it closes
    carries nothing the NEC cards use, so every SimNEC circuit has one and
    reporting it as "not imported" on every file was noise (AK#1679). Only
    that exact element qualifies; any other LOAD is still reported."""
    if (label or "").strip() != "NotUsed":
        return False
    try:
        z = complex(float(params.get("ohms") or 0), float(params.get("johms") or 0))
    except ValueError:
        return False
    return z == 0 and (params.get("file") or "<none>").strip() == "<none>"


def _params(el) -> dict[str, str | None]:
    """An element's top-level ``<p><n>name</n><v>value</v></p>`` params."""
    return {p.findtext("n"): p.findtext("v") for p in el.findall("p")}


# The most points a sweep may ask for. SimNEC prunes a sweep that is too
# dense; a 0.0001 MHz step over 1-30 MHz is an unreadable sweep here, not a
# reason to allocate hundreds of thousands of floats.
_SWEEP_MAX_POINTS = 100_000


def _sweep_number(token: str) -> float:
    text = token.strip()
    scale = 1.0
    if text and text[-1] in _SI_SUFFIX:
        scale, text = _SI_SUFFIX[text[-1]], text[:-1]
    return float(text) * scale


def _sweep_range(item: str) -> list[float]:
    """The values of one ``from:to:step`` (or ``from:to:logStep s``) triple."""
    parts = item.split(":")
    if len(parts) != 3:
        raise ValueError(f"{item!r} is not from:to:step")
    lo, hi = _sweep_number(parts[0]), _sweep_number(parts[1])
    log = parts[2].lower().startswith("logstep")
    step = _sweep_number(parts[2][7:] if log else parts[2])
    if not 0.0 < lo <= hi or step <= 0.0:
        raise ValueError(f"{item!r} is not an increasing positive range")
    if log:
        # SimNEC: the start and finish, and between them every value whose
        # log10 is a whole multiple of the step.
        k0 = math.floor(math.log10(lo) / step + 1e-9) + 1
        k1 = math.ceil(math.log10(hi) / step - 1e-9) - 1
        if k1 - k0 > _SWEEP_MAX_POINTS:
            raise ValueError(f"{item!r} asks for more than {_SWEEP_MAX_POINTS} points")
        inner = (10.0 ** (k * step) for k in range(k0, k1 + 1))
        return [lo, *(v for v in inner if lo < v < hi), hi]
    count = math.floor((hi - lo) / step + 1e-9) + 1
    if count > _SWEEP_MAX_POINTS:
        raise ValueError(f"{item!r} asks for {count} points")
    return [lo + i * step for i in range(count)]


def _expr_items(expr: str) -> list[str]:
    """A sweep expression's items, one token each: ``{}`` dropped, spaces
    around ``:`` closed up, and ``logStep s`` fused to ``logSteps``."""
    text = expr.replace("{", " ").replace("}", " ")
    text = re.sub(r"\s*:\s*", ":", text)
    text = re.sub(r"(?i)logstep\s+", "logStep", text)
    return text.split()


def _sweep_expr(expr: str) -> tuple[float, ...]:
    """The values a SimNEC sweep expression names (AK#1679), in its order.

    The grammar is the SimNEC Manual's "Sweep Expressions": whitespace-
    separated items, each a single value or a colon triple ``from:to:step``,
    where the step may be ``logStep s`` for steps whose log10 values are whole
    multiples of ``s``. A range may be wrapped in ``{}``, which only changes
    how SimNEC plots it. Raises ``ValueError`` for anything else, ``Vary``
    included: its span comes from a SimNEC preference the file does not
    carry."""
    out: list[float] = []
    for item in _expr_items(expr):
        if ":" in item:
            out.extend(_sweep_range(item))
        else:
            out.append(_sweep_number(item))
        if len(out) > _SWEEP_MAX_POINTS:
            raise ValueError(f"it asks for more than {_SWEEP_MAX_POINTS} points")
    if not out:
        raise ValueError("it names no frequencies")
    return tuple(out)


def _expr_grid(expr: str, pts: tuple[float, ...]) -> tuple[str, float] | None:
    """The grid of a sweep expression that is exactly one ``from:to:step``
    range (AK#1682): ``("lin", step)`` or, for ``logStep s``, ``("log", n)``
    where ``n`` is the actual count of values that range produced (``pts``,
    from ``_sweep_expr`` -- the same list, not recomputed). None for anything
    else -- several items have no one spacing."""
    items = _expr_items(expr)
    if len(items) != 1 or items[0].count(":") != 2:
        return None
    step = items[0].split(":")[2]
    if step.lower().startswith("logstep"):
        return "log", len(pts)
    return "lin", _sweep_number(step)


def _gen_sweep(gen):
    """``(sweep, points, grid, note)`` for the Generator's frequency sweep.

    SimNEC stores it in a ``<sweepParam>`` under the MHz param, and only
    ``doSweep`` = y is live. Its ``log`` field picks the spacing: ``lin`` and
    ``log`` space ``points`` values over ``from``..``to``; ``expr`` ignores
    those two and evaluates the ``expr`` text instead (AK#1679: AC6LA's
    ``14 : 14.35 : 0.025`` was read as the stale 1-30 MHz ``from``/``to``).
    ``sweep`` is the (lowest, highest) frequency visited, ``points`` the
    frequencies themselves (None for a lin/log sweep with no usable count),
    ``grid`` the spacing as ``SsnCircuit.sweep_grid`` records it (AK#1682),
    and ``note`` says why an armed sweep was not read, for the user."""
    for p in gen.findall("p"):
        if p.findtext("n") != "MHz":
            continue
        for sp in p.findall("sweepParam"):
            q = {e.findtext("n"): e.findtext("v") for e in sp.findall("p")}
            if q.get("doSweep") != "y":
                continue
            mode = (q.get("log") or "lin").strip().lower()
            if mode == "expr":
                expr = (q.get("expr") or "").strip()
                try:
                    pts = _sweep_expr(expr)
                except ValueError as e:
                    return (
                        None,
                        None,
                        None,
                        f"the Generator's sweep expression {expr!r} was not read ({e})",
                    )
                grid = _expr_grid(expr, pts) if max(pts) > min(pts) else None
                return (min(pts), max(pts)), pts, grid, None
            if mode not in ("lin", "log"):
                return (
                    None,
                    None,
                    None,
                    f"the Generator's sweep spacing {q.get('log')!r} is not "
                    "lin, log or expr",
                )
            try:
                lo, hi = float(q["from"]), float(q["to"])
            except (KeyError, TypeError, ValueError):
                return None, None, None, "the Generator's sweep range was not read"
            lo, hi = min(lo, hi), max(lo, hi)
            try:
                n = int(float(q.get("points") or "nan"))
            except ValueError:
                n = 0
            pts = grid = None
            if 2 <= n <= _SWEEP_MAX_POINTS and 0.0 < lo < hi:
                if mode == "log":
                    r = (hi / lo) ** (1.0 / (n - 1))
                    pts = tuple(lo * r**i for i in range(n))
                    # n is already the exact point count SimNEC asked for.
                    grid = ("log", n)
                else:
                    pts = tuple(lo + (hi - lo) * i / (n - 1) for i in range(n))
                    grid = ("lin", (hi - lo) / (n - 1))
            return (lo, hi), pts, grid, None
    return None, None, None, None


# The call-style portal dialect: a NETWORK script that BUILDS the antenna by
# calling SimNEC, instead of carrying NEC cards for it (AK#1538). These two
# calls are the tell. Neither appears in a card block — antennaknobs' own
# export writes GW and EX cards — so seeing one in a file with no NEC2 line
# says the antenna is there and is written the other way, which is a different
# thing to tell the reader than "no antenna here".
_CALL_STYLE = re.compile(r"\bNEC(?:Wire|Source)\s*\(")

# The one spelling the importer reads, named in both refusals. SimNEC's NEC
# portal accepts it and antennaknobs' own .ssn export writes it, so it is both
# a format and a way to get one.
_THE_SPELLING = (
    "NEC cards between a NEC2 line and a NECEND line, inside a NETWORK "
    "element's <equ> script"
)


def _no_block_message(*, scripted: bool) -> str:
    """Why this circuit has no deck to read, and what to do about it."""
    if not scripted:
        return (
            f"no NEC-portal antenna block. antennaknobs reads {_THE_SPELLING} "
            f"— the spelling SimNEC's NEC portal accepts and antennaknobs' own "
            f"'python -m antennaknobs.simnec_export' writes. This circuit has "
            f"no such script."
        )
    return (
        f"this circuit's antenna is a SimNEC script — NECWire/NECSource calls "
        f"that SimNEC evaluates itself — and the saved file keeps no cards "
        f"from it. antennaknobs does not evaluate SimNEC's scripting language; "
        f"it reads {_THE_SPELLING}. Two ways to get there: write this "
        f"antenna's cards into a NEC2 ... NECEND block in the NETWORK script, "
        f"or export a design from antennaknobs to .ssn "
        f"('python -m antennaknobs.simnec_export') and edit that. Reading the "
        f"deck SimNEC itself generates from the script would be the faithful "
        f"third way, and is not available yet."
    )


def parse_ssn(
    text: str,
    *,
    name: str = "SimNEC circuit",
    network: bool = False,
    virtualize_anchors: bool = True,
) -> SsnCircuit:
    """Parse the text of a SimNEC ``.ssn`` file into an :class:`SsnCircuit`.

    ``network`` and ``virtualize_anchors`` forward to :func:`parse_nec` for the
    embedded NEC cards — ``network=True`` makes ``circuit.deck.wire_tuples()``
    and ``circuit.network()`` ready to return from ``build_wires`` /
    ``build_network``, with the deck's lumped LD loads and the file's station
    chain (see the module note) translated.

    Raises ``ValueError`` (prefixed with ``name``) on malformed XML, on a file
    with no NEC-portal antenna block or more than one, and on anything
    ``parse_nec`` refuses in the embedded cards.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"{name}: not well-formed .ssn XML ({e})") from None

    elements = root.findall(".//CIRCUIT/element")
    if not elements:
        raise ValueError(f"{name}: no <CIRCUIT> elements — is this a .ssn file?")
    infos = [((el.findtext("type") or "?").strip(), _params(el), el) for el in elements]

    nec_positions = [
        i
        for i, (typ, params, _) in enumerate(infos)
        if typ == "NETWORK"
        and "equ" in params
        and re.search(r"(?m)^\s*NEC2\s*$", params["equ"] or "")
    ]
    if not nec_positions:
        scripted = [
            i
            for i, (typ, params, _) in enumerate(infos)
            if typ == "NETWORK" and _CALL_STYLE.search(params.get("equ") or "")
        ]
        raise ValueError(f"{name}: {_no_block_message(scripted=bool(scripted))}")
    if len(nec_positions) > 1:
        raise ValueError(
            f"{name}: {len(nec_positions)} NEC-portal blocks — antennaknobs "
            f"imports a single-antenna circuit"
        )
    nec_pos = nec_positions[0]
    gen_pos = next(
        (i for i, (typ, _, _) in enumerate(infos) if typ == "GENERATOR"), None
    )
    generator = elements[gen_pos] if gen_pos is not None else None

    # The station chain is whatever sits between the antenna block and the
    # Generator (SimNEC saves the cascade right-to-left: LOAD … antenna …
    # chain … GENERATOR, so that document span reads antenna→generator).
    if gen_pos is not None:
        lo, hi = sorted((nec_pos, gen_pos))
        span = range(lo + 1, hi)
    else:
        span = range(0)

    chain_doc: list[SsnElement] = []
    other: list[str] = []
    for i, (typ, params, el) in enumerate(infos):
        if i == nec_pos or i == gen_pos:
            continue
        if typ == "NETWORK" and "equ" in params:
            other.append("NETWORK (non-NEC script)")
            continue
        if typ == "LOAD":
            try:
                is_open = float(params.get("ohms") or 0) >= _OPEN_OHMS
            except ValueError:
                is_open = False
            if is_open:
                continue  # the exporter's scaffold open termination
            if i not in span and _is_unused_termination(
                el.findtext("sweeperLabel"), params
            ):
                continue  # SimNEC's own "NotUsed" 0 ohm termination
        if i in span:
            chain_doc.append(
                SsnElement(
                    typ=typ,
                    label=el.findtext("sweeperLabel"),
                    params=tuple(
                        (p.findtext("n"), p.findtext("v")) for p in el.findall("p")
                    ),
                )
            )
            if typ not in _CHAIN_TYPES:
                # In the cascade but not translatable: report it, and
                # network() will refuse to build a station around it.
                other.append(typ)
            continue
        other.append(typ)
    # Orient the chain generator→antenna, whichever way the file ran.
    if gen_pos is not None and nec_pos < gen_pos:
        chain_doc.reverse()
    chain = tuple(chain_doc)

    script = _Script(infos[nec_pos][1]["equ"] or "", name)

    deck_lines = list(script.cards)
    if script.ground is not None:
        deck_lines.append("GE 1")  # so deck.ground reflects the ground call
    deck_lines.append("EN")
    deck = parse_nec(
        "\n".join(deck_lines) + "\n",
        name=f"{name} NEC block",
        network=network,
        virtualize_anchors=virtualize_anchors,
    )
    deck, unapplied = _jam_segments(deck, script.jam, name)
    script.ignored.extend(unapplied)
    if script.insulation is not None:
        # The circuit's default insulation covers every wire (AK#1683): a
        # jacket of that radial thickness over each GW conductor radius.
        thick, eps_r = script.insulation
        deck = replace(
            deck,
            wire_insulation=tuple(
                (i, (w.radius + thick, eps_r)) for i, w in enumerate(deck.wires)
            ),
        )

    freq_mhz = None
    sweep = sweep_points = sweep_grid = sweep_note = None
    gen_zo = None
    if generator is not None:
        p = _params(generator)
        try:
            freq_mhz = float(p["MHz"]) if p.get("MHz") else None
        except ValueError:
            raise ValueError(f"{name}: bad GENERATOR MHz {p['MHz']!r}") from None
        try:
            gen_zo = float(p["Zo"]) if p.get("Zo") else None
        except ValueError:
            gen_zo = None
        sweep, sweep_points, sweep_grid, sweep_note = _gen_sweep(generator)

    return SsnCircuit(
        deck=deck,
        freq_mhz=freq_mhz,
        sweep=sweep,
        ground=script.ground,
        conductivity=script.conductivity,
        seg_per_wl=script.seg_per_wl,
        gen_zo=gen_zo,
        name=script.name,
        chain=chain,
        other_elements=tuple(other),
        ignored_directives=tuple(script.ignored),
        sweep_points=sweep_points,
        sweep_note=sweep_note,
        sweep_grid=sweep_grid,
    )


def read_ssn(
    builder, name: str, *, network: bool = False, virtualize_anchors: bool = True
) -> SsnCircuit:
    """``read_data`` followed by ``parse_ssn`` — load a SimNEC circuit that
    ships next to ``builder``'s design, with the same folder confinement as
    ``read_json`` / ``read_nec``."""
    return parse_ssn(
        read_data(builder, name),
        name=name,
        network=network,
        virtualize_anchors=virtualize_anchors,
    )
