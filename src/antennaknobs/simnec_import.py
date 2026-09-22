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

The solve frequency comes from the GENERATOR element's ``MHz`` — in SimNEC the
deck's ``FR`` card is advisory; the Generator drives the solve — and an armed
(``doSweep y``) Generator sweep surfaces as ``sweep=(lo, hi)``.

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
                                         coefficients — the same convention)
    SERIES_IND / SERIES_CAP           -> TwoPort  (H / F, Q -> ql / qc)
    SHUNT_IND / SHUNT_CAP             -> Shunt    (H / F, Q -> ql / qc)
    TRANSFORMER2 (Mdl ideal)          -> Transformer (n = 1/N: SimNEC's N is
                                         the antenna:generator voltage ratio,
                                         validated on 5.1a0 — see export)

The chain hangs between a virtual generator-side node (``"rig"``, the
``Driven`` source) and the deck's fed wire; trap ``Load``s ride in the deck as
LD cards and translate through ``parse_nec`` as usual. Semantics notes, shared
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
termination and the 50 Ohm GENERATOR) is recognised and not reported.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from . import network as _net
from .design_data import read_data
from .nec_import import NecDeck, parse_nec

__all__ = ["SsnCircuit", "SsnElement", "parse_ssn", "read_ssn"]


# The exporter's scaffold LOAD is a 1e9 Ohm open; treat anything this large as
# "no termination" rather than a circuit element worth reporting.
_OPEN_OHMS = 1e8

M_PER_FT = 0.3048

# Station chain elements network() can translate (issue #604's captured set).
_SHUNT_CHAIN = frozenset({"SHUNT_IND", "SHUNT_CAP"})
_SERIES_CHAIN = frozenset({"SERIES_TLINE", "SERIES_IND", "SERIES_CAP", "TRANSFORMER2"})
_CHAIN_TYPES = _SHUNT_CHAIN | _SERIES_CHAIN

_NEC2_LINE = re.compile(r"^NEC2\s*$")
_NECEND_LINE = re.compile(r"^NECEND\s*$")
_PORT_DECL = re.compile(r"^P\d+\s+\S", re.IGNORECASE)
_SOMMERFELD = re.compile(
    r"^SommerfeldGround\s*\(\s*([^\s,()]+)\s*,\s*([^\s,()]+)\s*\)$", re.IGNORECASE
)
_PERFECT = re.compile(r"^PerfectGround\s*\(\s*\)$", re.IGNORECASE)
_NECUNITS = re.compile(r"^NECUnits\s+(.+)$", re.IGNORECASE)
_NECOPTION = re.compile(r"^NECOptions\.(\w+)\s*=\s*(\S+)$", re.IGNORECASE)


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


def _shunt_branch(el: SsnElement, node: str):
    if el.typ == "SHUNT_IND":
        return _net.Shunt(port=node, l=_chain_f(el, "H"), ql=_chain_q(el))
    return _net.Shunt(port=node, c=_chain_f(el, "F"), qc=_chain_q(el))


def _series_branch(el: SsnElement, a: str, b: str):
    """The network branch for one series chain element, entered generator-side
    at ``a`` — the inverse of the station exporter's ``_series_elements``."""
    if el.typ == "SERIES_TLINE":
        k0 = _chain_f(el, "k0", default=0.0)
        if k0 != 0.0:
            raise ValueError(
                f"SERIES_TLINE {el.label or ''}: a constant k0 loss term has "
                f"no TL equivalent — TL matched loss is k1*sqrt(f) + k2*f "
                f"(dB/100 ft)"
            )
        return _net.TL(
            a=a,
            b=b,
            z0=_chain_f(el, "Zo"),
            length=_chain_f(el, "ft") * M_PER_FT,
            vf=_chain_f(el, "VFnom", default=1.0),
            k1=_chain_f(el, "k1", default=0.0),
            k2=_chain_f(el, "k2", default=0.0),
        )
    if el.typ == "SERIES_IND":
        return _net.TwoPort(a=a, b=b, l=_chain_f(el, "H"), ql=_chain_q(el))
    if el.typ == "SERIES_CAP":
        return _net.TwoPort(a=a, b=b, c=_chain_f(el, "F"), qc=_chain_q(el))
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
    # Armed (doSweep y) Generator frequency sweep, MHz. None = no sweep armed.
    sweep: tuple[float, float] | None
    # Ground translated from the daemon call, in export_ssn's own spec:
    # None (free space), "pec", or ("finite", eps_r, sigma).
    ground: None | str | tuple
    # NECOptions.mhosPerMeter, S/m — feed to WireSpec(conductivity=...).
    # None when absent or 0 (perfect wires).
    conductivity: float | None
    # NECOptions.segmentsPerWavelength — SimNEC's re-mesh density. Advisory
    # for antennaknobs (its engines keep the deck's segment counts).
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
        note = None
        if parts:
            body = "; ".join(parts)
            note = body[0].upper() + body[1:] + "."
        deck_note = self.deck.skipped_note()
        if note and deck_note:
            return f"{note} {deck_note}"
        return note or deck_note

    def network(self, *, rig_port: str = "rig"):
        """The full circuit as a ``network.Network``, ready to return from
        ``build_network()``: the deck's translated branches and feed (via
        ``NecDeck.network()``, so parse with ``network=True``), plus the
        station chain re-hung between a virtual generator-side ``rig_port``
        node — where the ``Driven`` source moves to — and the deck's fed
        wire. An antenna-only file returns the deck network unchanged.

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

        series_left = sum(1 for el in self.chain if el.typ in _SERIES_CHAIN)
        if series_left == 0:
            # Shunt-only chain: nothing separates the generator from the
            # feed, so the shunts hang straight across the feed terminals
            # and the source stays where the deck put it.
            branches.extend(_shunt_branch(el, feed_port) for el in self.chain)
            return _net.Network(ports=ports, branches=branches, sources=[src])

        if rig_port in ports:
            raise ValueError(
                f"rig_port {rig_port!r} collides with a deck port name — "
                f"pass a different rig_port"
            )
        node = rig_port
        ports[node] = _net.PortVirtual(node)
        k = 0
        for el in self.chain:
            if el.typ in _SHUNT_CHAIN:
                branches.append(_shunt_branch(el, node))
                continue
            series_left -= 1
            if series_left == 0:
                nxt = feed_port  # the last series element lands on the feed
            else:
                k += 1
                nxt = f"chain{k}"
                ports[nxt] = _net.PortVirtual(nxt)
            branches.append(_series_branch(el, node, nxt))
            node = nxt
        return _net.Network(
            ports=ports,
            branches=branches,
            sources=[_net.Driven(port=rig_port, voltage=src.voltage)],
        )


def _fnum(token: str, where: str, what: str) -> float:
    try:
        return float(token.rstrip(";"))
    except ValueError:
        raise ValueError(f"{where}: bad {what} value {token!r}") from None


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

    def _directive(self, stmt: str, where: str) -> None:
        if _PORT_DECL.match(stmt):
            return  # port declaration (P1 w1 gnd) — circuit structure only
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
                mhos = _fnum(value, where, f"NECOptions.{option}")
                self.conductivity = mhos if mhos > 0.0 else None
                return
            if key == "segmentsperwavelength":
                self.seg_per_wl = int(_fnum(value, where, f"NECOptions.{option}"))
                return
        self.ignored.append(stmt)


def _params(el) -> dict[str, str | None]:
    """An element's top-level ``<p><n>name</n><v>value</v></p>`` params."""
    return {p.findtext("n"): p.findtext("v") for p in el.findall("p")}


def _gen_sweep(gen) -> tuple[float, float] | None:
    """The Generator's armed frequency sweep, or None. SimNEC stores the range
    in a ``<sweepParam>`` under the MHz param; only ``doSweep`` = y is live."""
    for sp in gen.iter("sweepParam"):
        p = {q.findtext("n"): q.findtext("v") for q in sp.findall("p")}
        if p.get("doSweep") != "y":
            continue
        try:
            return float(p["from"]), float(p["to"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


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

    freq_mhz = None
    sweep = None
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
        sweep = _gen_sweep(generator)

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
