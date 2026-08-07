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
conductivity and SimNEC's re-mesh density surface as fields, and ``NECUnits``
scales the geometry to metres (via a native ``GS`` card, so NEC's own scaling
semantics apply; the second ``NECUnits`` argument is taken as the wire-radius
unit, matching the export's ``NECUnits meters, meters``).

The solve frequency comes from the GENERATOR element's ``MHz`` — in SimNEC the
deck's ``FR`` card is advisory; the Generator drives the solve — and an armed
(``doSweep y``) Generator sweep surfaces as ``sweep=(lo, hi)``.

Scope mirrors the exporter: **the antenna block only**. A full-station ``.ssn``
(tuner elements, transmission lines, transformers between the Generator and the
antenna) is not translated into the app's port-network system; those elements
are recorded in ``SsnCircuit.other_elements`` — and daemon statements the
importer does not understand in ``ignored_directives`` — so a caller can tell
the user what the file carries that the import leaves behind (see
``skipped_note()``). The exporter's own scaffold (the open LOAD termination and
the 50 Ohm GENERATOR) is recognised and not reported.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace

from .design_data import read_data
from .nec_import import NecDeck, parse_nec

__all__ = ["SsnCircuit", "parse_ssn", "read_ssn"]

# NECUnits values, in metres. The directive names a unit per argument:
# (coordinates, wire radius) — the exporter writes "NECUnits meters, meters".
_UNIT_M = {
    "meters": 1.0,
    "meter": 1.0,
    "m": 1.0,
    "centimeters": 0.01,
    "centimeter": 0.01,
    "cm": 0.01,
    "millimeters": 0.001,
    "millimeter": 0.001,
    "mm": 0.001,
    "feet": 0.3048,
    "foot": 0.3048,
    "ft": 0.3048,
    "inches": 0.0254,
    "inch": 0.0254,
    "in": 0.0254,
}

# The exporter's scaffold LOAD is a 1e9 Ohm open; treat anything this large as
# "no termination" rather than a circuit element worth reporting.
_OPEN_OHMS = 1e8

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
    # Circuit element types the import leaves behind (tuner elements,
    # extra blocks — anything beyond the antenna + exporter scaffold).
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
                "SimNEC circuit elements not imported (antenna block only): "
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


def _unit_scale(token: str, where: str) -> float:
    try:
        return _UNIT_M[token.strip().lower()]
    except KeyError:
        raise ValueError(f"{where}: unrecognised NECUnits unit {token!r}") from None


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
        self.coord_scale = 1.0
        self.radius_scale = 1.0
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
            self.coord_scale = _unit_scale(units[0], where)
            self.radius_scale = (
                _unit_scale(units[1], where) if len(units) == 2 else self.coord_scale
            )
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
    and ``circuit.deck.network()`` ready to return from ``build_wires`` /
    ``build_network``, with the deck's lumped LD loads translated.

    Raises ``ValueError`` (prefixed with ``name``) on malformed XML, on a file
    with no NEC-portal antenna block or more than one, and on anything
    ``parse_nec`` refuses in the embedded cards.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"{name}: not well-formed .ssn XML ({e})") from None

    nec_blocks: list[str] = []
    generator = None
    other: list[str] = []
    elements = root.findall(".//CIRCUIT/element")
    if not elements:
        raise ValueError(f"{name}: no <CIRCUIT> elements — is this a .ssn file?")
    for el in elements:
        typ = (el.findtext("type") or "?").strip()
        params = _params(el)
        if typ == "NETWORK" and "equ" in params:
            equ = params["equ"] or ""
            if re.search(r"(?m)^\s*NEC2\s*$", equ):
                nec_blocks.append(equ)
            else:
                other.append("NETWORK (non-NEC script)")
            continue
        if typ == "GENERATOR" and generator is None:
            generator = el
            continue
        if typ == "LOAD":
            try:
                is_open = float(params.get("ohms") or 0) >= _OPEN_OHMS
            except ValueError:
                is_open = False
            if is_open:
                continue  # the exporter's scaffold open termination
        other.append(typ)

    if not nec_blocks:
        raise ValueError(
            f"{name}: no NEC-portal antenna block (a NETWORK element whose "
            f"<equ> script carries NEC2 cards)"
        )
    if len(nec_blocks) > 1:
        raise ValueError(
            f"{name}: {len(nec_blocks)} NEC-portal blocks — antennaknobs "
            f"imports a single-antenna circuit"
        )

    script = _Script(nec_blocks[0], name)

    deck_lines = list(script.cards)
    if script.coord_scale != 1.0:
        # NEC's own whole-structure scale card, appended after the geometry so
        # transforms and TL-length resolution all see metres.
        deck_lines.append(f"GS 0 0 {script.coord_scale!r}")
    if script.ground is not None:
        deck_lines.append("GE 1")  # so deck.ground reflects the ground call
    deck_lines.append("EN")
    deck = parse_nec(
        "\n".join(deck_lines) + "\n",
        name=f"{name} NEC block",
        network=network,
        virtualize_anchors=virtualize_anchors,
    )
    if script.radius_scale != script.coord_scale:
        # GS scaled radii along with coordinates; correct to the radius unit.
        fix = script.radius_scale / script.coord_scale
        deck = replace(
            deck,
            wires=tuple(replace(w, radius=w.radius * fix) for w in deck.wires),
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
