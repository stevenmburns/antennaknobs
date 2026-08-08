"""momwire as a resident SimNEC engine — the ``nec2c`` portal daemon.

SimNEC (``nec2/NEC2Daemon``) starts one NEC-2 process and keeps it: decks
arrive on stdin framed by an ``NX`` card, printouts leave on stdout, and the
Java side blocks in ``readLine()`` until it sees the ``NX`` data-card echo.
This module is that process, with momwire behind it instead of nec2c.

The contract is pinned in ``docs/status/2026-08-08-simnec-execute-grammar.md``
(issue #792 unit 1) and in the 28 oracle deck/printout pairs under
``tests/fixtures/nec_portal/``. Everything here — column widths, header
strings, section order, the ``-YY`` row, the stderr discipline — is copied out
of those two sources. **Layout is the contract; the numbers are momwire's.**
A different basis and kernel will never reproduce nec2c digit for digit, and
SimNEC does not need it to: it reads exactly two numbers per
``ANTENNA INPUT PARAMETERS`` row (the CURRENT real/imaginary columns, fields 4
and 5 of an 11-token row) and builds its Y matrix from them.

Scope (unit 2 — the load-bearing core):

* the version probe, the resident stdin loop, the ``NX`` sentinel;
* ``CM``/``CE`` directives ``QQ`` (quiet) and ``FF`` (the one stderr line);
* geometry ``GW``/``GM``/``GS``/``GX``/``GR``/``GA``/``GH``/``GE``, environment
  ``GN 0/1/2``, loading ``LD 0/1/4/5``, excitation ``EX 0``, ``FR``, ``XQ``,
  and Ward's ``YY`` report card;
* the printout sections SimNEC's state machine walks: banner, comments, data
  cards, structure specification, segmentation data, frequency, structure
  impedance loading, antenna environment, matrix timing, antenna input
  parameters, currents and location, power budget.

Deferred to unit 3: ``RP`` patterns, ``NE``/``NH`` near fields, ``NT``/``TL``
networks, ``PT``/``MP``, surface patches, and the cross-engine differential
harness. Those cards take the error path below rather than crashing the
daemon.

The architectural win over the oracle
-------------------------------------
SimNEC probes an N-port antenna by writing N ``XQ`` groups, one ``EX`` per
port per group (``nec2/NECSource.sensorLines``), and the oracle re-runs the
whole MoM solve — fill, factor, solve — once per group. It pays N fills for
one matrix.

We do not. A deck's execute groups all share one geometry, so this module
takes the UNION of every group's ``EX`` segment (plus every ``LD`` segment) as
the momwire port set, fills and factors ONCE per (geometry, frequency), and
gets the per-port basis-coefficient columns X out of the same LU
back-substitution that produces the short-circuit Y matrix. Every execute
group after that is linear algebra on cached factors: the group's port
voltages give ``coeffs = X @ V`` and its currents ``I = Y @ V``. N sources
cost one fill, not N.
"""

from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass, field
from types import MappingProxyType

import numpy as np
from momwire import BSplineSolver

from .builder import AntennaBuilder
from .engines.momwire import MomwireEngine
from .nec_import import parse_nec
from .network import _series_rlc_impedance

__all__ = [
    "BANNER_VERSION",
    "PROBE_VERSION",
    "deck_frame",
    "main",
    "render_deck",
    "run_deck",
]

# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

# ``Execute.testCommand()`` matches the FIRST LINE of `<cmd> -version`, trimmed,
# against ``versionA = nec2c\.ae6ty\.(.*)`` and then feeds group(1) to
# ``Double.valueOf``.  The group is greedy, so ANY non-numeric text after
# ``nec2c.ae6ty.`` — including the word "momwire" — makes the parse throw and
# SimNEC reports "nec2c version too old:".  The probe string therefore has to
# end in a bare one-dot number.  (Grammar doc §1 "Version probe"; issue #792
# unit 1 flagged the same trap for ``1.17.2``.)
PROBE_VERSION = "nec2c.ae6ty.9.1"

# The banner inside a printout is NOT version-checked: the four regexes are
# ``lookingAt()``, i.e. anchored, and the banner line is prefixed ``VERSION:``
# so none of them can match it.  That makes it the safe place to say who we
# actually are.
BANNER_VERSION = "nec2c.ae6ty.momwire.9.1"

C_LIGHT = 299_792_458.0
EPS0 = 8.854_187_817e-12

# --------------------------------------------------------------------------
# fixed printout chrome (verbatim from tests/fixtures/nec_portal/*.out)
# --------------------------------------------------------------------------

_BANNER = (
    "",
    "",
    "",
    "                               __________________________________________",
    "                              |                                          |",
    "                              |  NUMERICAL ELECTROMAGNETICS CODE (nec2c) |",
    "                              |   Translated to 'C' in Double Precision  |",
    "                              |__________________________________________|",
    "",
    f"VERSION:{BANNER_VERSION}",
)

_COMMENTS_HEADER = (
    "                               ---------------- COMMENTS ----------------"
)
# nec2c echoes the card body from column 3 on, after a 30-space indent — so a
# bare `CE` prints 30 spaces and `CE dipole` prints 31 then the text.
_COMMENT_INDENT = " " * 30

_STRUCTURE_HEADER = (
    "                               -------- STRUCTURE SPECIFICATION --------"
)
_STRUCTURE_NOTES = (
    "                                     COORDINATES MUST BE INPUT IN",
    "                                     METERS OR BE SCALED TO METERS",
    "                                     BEFORE STRUCTURE INPUT IS ENDED",
)
_WIRE_TABLE_HEADER = (
    "  WIRE                                                                     "
    "            SEG FIRST  LAST  TAG",
    "   No:        X1         Y1         Z1         X2         Y2         Z2   "
    "    RADIUS   No:   SEG   SEG  No:",
)

_JUNCTIONS_HEADER = (
    "    ---------- MULTIPLE WIRE JUNCTIONS ----------",
    "    JUNCTION  SEGMENTS (- FOR END 1, + FOR END 2)",
)

_SEGMENTATION_HEADER = (
    "                               ---------- SEGMENTATION DATA ----------"
)
_SEGMENTATION_NOTES = (
    "                                        COORDINATES IN METERS",
    "                            I+ AND I- INDICATE THE SEGMENTS BEFORE AND AFTER I",
)
_SEGMENTATION_TABLE_HEADER = (
    "   SEG    COORDINATES OF SEGM CENTER     SEGM    ORIENTATION ANGLES    WIRE"
    "    CONNECTION DATA   TAG",
    "   No:       X         Y         Z      LENGTH     ALPHA      BETA    RADIUS"
    "    I-     I    I+   No:",
)

_FREQUENCY_HEADER = "                               --------- FREQUENCY --------"
_APPROX_INTEGRATION = (
    "                        APPROXIMATE INTEGRATION EMPLOYED FOR SEGMENTS ",
    "                        THAT ARE MORE THAN 1.000 WAVELENGTHS APART",
)

_LOADING_HEADER = "                          ------ STRUCTURE IMPEDANCE LOADING ------"
_LOADING_NONE = "                                 THIS STRUCTURE IS NOT LOADED"
_LOADING_TABLE_HEADER = (
    "  LOCATION        RESISTANCE  INDUCTANCE  CAPACITANCE     IMPEDANCE (OHMS)"
    "   CONDUCTIVITY  CIRCUIT",
    "  ITAG FROM THRU     OHMS       HENRYS      FARADS       REAL     IMAGINARY"
    "   MHOS/METER      TYPE",
)
# The oracle's per-type tail, byte for byte (the pad is baked into the string
# — it is not a uniform %Ns field; see the fixtures).
_LOADING_TYPE_TAIL = MappingProxyType(
    {
        "SERIES": "    SERIES ",
        "PARALLEL": "   PARALLEL",
        "FIXED IMPEDANCE": "   FIXED IMPEDANCE ",
        "WIRE": "     WIRE  ",
    }
)

_ENVIRONMENT_HEADER = (
    "                            -------- ANTENNA ENVIRONMENT --------"
)
_MATRIX_TIMING_HEADER = (
    "                             ---------- MATRIX TIMING ----------"
)

_AIP_HEADER = "                        --------- ANTENNA INPUT PARAMETERS ---------"
_AIP_TABLE_HEADER = (
    "  TAG   SEG       VOLTAGE (VOLTS)         CURRENT (AMPS)         IMPEDANCE"
    " (OHMS)        ADMITTANCE (MHOS)     POWER",
    "  No:   No:     REAL      IMAGINARY     REAL      IMAGINARY     REAL     "
    " IMAGINARY    REAL       IMAGINARY   (WATTS)",
)

_CURRENTS_HEADER = "                           -------- CURRENTS AND LOCATION --------"
_CURRENTS_NOTE = "                                  DISTANCES IN WAVELENGTHS"
_CURRENTS_TABLE_HEADER = (
    "   SEG  TAG    COORDINATES OF SEGM CENTER     SEGM    ------------- CURRENT"
    " (AMPS) -------------",
    "   No:  No:       X         Y         Z      LENGTH     REAL      IMAGINARY"
    "    MAGN        PHASE",
)

_POWER_HEADER = "                               ---------- POWER BUDGET ---------"

# The oracle writes this to both stdout and stderr when its input ends; the
# grammar doc's error table (§8) makes it the one error shape SimNEC tolerates
# without tripping the `ERROR:` warning frame (that test is on token 0 alone).
_ERROR_PREFIX = "ERROR-NEC2C: "


class PortalError(Exception):
    """A deck this build cannot run. Reported on the error path, never fatal:
    the daemon still emits the NX sentinel so the Java side does not block."""


# --------------------------------------------------------------------------
# cards
# --------------------------------------------------------------------------

# Cards echoed inside STRUCTURE SPECIFICATION rather than as DATA CARD lines.
_GEOMETRY_CARDS = frozenset({"GW", "GA", "GH", "GM", "GX", "GR", "GS", "GE"})

# Cards the portal dialect can carry that unit 2 does not model yet. They are
# named so the error path can say WHICH card, instead of "unrecognised".
_DEFERRED_CARDS = MappingProxyType(
    {
        "RP": "radiation-pattern request",
        "NE": "near-electric-field request",
        "NH": "near-magnetic-field request",
        "NT": "two-port network",
        "TL": "transmission line",
        "PT": "current print control",
        "MP": "multiprocessing hint",
        "IS": "NEC-4.2 wire insulation",
        "SP": "surface patch",
        "SM": "multiple-patch surface",
    }
)


@dataclass(frozen=True)
class Card:
    """One data card: mnemonic plus its numeric fields, in card order.

    NEC's echo splits those fields into four integers and six reals whatever
    the card means — a ``YY 1 4 2 4 5 4`` report card echoes ``1 4 2 4`` as
    integers and ``5.0 4.0`` as reals — so one accessor pair serves them all.
    """

    mnemonic: str
    values: tuple[float, ...]
    raw: str

    def f(self, k: int) -> float:
        return self.values[k] if k < len(self.values) else 0.0

    def i(self, k: int) -> int:
        return int(round(self.f(k)))


def parse_card(line: str) -> Card | None:
    """One deck line as a :class:`Card`, or None for a blank line.

    Free-format, comma-or-space separated, mnemonic taken from the first two
    characters — the same tolerance ``nec_import.parse_nec`` applies, because
    the same decks reach both.
    """
    stripped = line.strip()
    if not stripped:
        return None
    tokens = stripped.replace(",", " ").split()
    head = tokens[0]
    if len(head) > 2 and head[:2].isalpha() and head[2] in "0123456789.+-":
        tokens = [head[:2], head[2:], *tokens[1:]]
    mnemonic = tokens[0].upper()
    if len(mnemonic) != 2 or not mnemonic.isalpha():
        raise PortalError(f"CARD'S MNEMONIC CODE TOO SHORT OR MISSING: {stripped!r}")
    if mnemonic in ("CM", "CE"):
        return Card(mnemonic, (), line.rstrip("\n"))
    values = []
    for token in tokens[1:]:
        try:
            values.append(float(token.replace("D", "E").replace("d", "e")))
        except ValueError:
            raise PortalError(
                f"NON-NUMERICAL CHARACTER IN FIELD: {token!r} on {stripped!r}"
            ) from None
    return Card(mnemonic, tuple(values), line.rstrip("\n"))


@dataclass(frozen=True)
class Ground:
    """The deck's ``GN`` card, reduced to what both the printout and momwire
    need. ``kind`` is one of free / pec / refl / sommerfeld."""

    kind: str = "free"
    eps_r: float = 0.0
    sigma: float = 0.0

    @classmethod
    def from_card(cls, card: Card) -> Ground:
        code = card.i(0)
        if code == 1:
            return cls("pec")
        if code == -1:
            return cls("free")
        if code in (0, 2):
            kind = "refl" if code == 0 else "sommerfeld"
            return cls(kind, card.f(4), card.f(5))
        raise PortalError(f"GN type {code} is not supported by this engine")

    def momwire_spec(self):
        if self.kind == "free":
            return None
        if self.kind == "pec":
            return "pec"
        # NEC gn 0 is the reflection-coefficient approximation, gn 2 the
        # Sommerfeld solution; momwire spells them "finite-fast" / "finite".
        return (
            "finite-fast" if self.kind == "refl" else "finite",
            self.eps_r,
            self.sigma,
        )


@dataclass
class ExecuteGroup:
    """One ``XQ``'s worth of state: the sources armed when it fired, and the
    frequency card in force. NEC clears the source list at every ``XQ``, which
    is why ``two_source_sensor_lines`` drives the same segment twice with
    different voltages and ``jar_testdeck``'s second group shows one row."""

    sources: tuple[tuple[int, int, complex], ...]  # (tag, seg, voltage)
    freqs_mhz: tuple[float, ...]
    # True when an FR card was read since the previous XQ. The oracle prints
    # the FREQUENCY / STRUCTURE IMPEDANCE LOADING / ANTENNA ENVIRONMENT /
    # MATRIX TIMING preamble only when it rebuilds the matrix, so a second XQ
    # under the same FR emits ANTENNA INPUT PARAMETERS straight away
    # (fixture: two_source_sensor_lines, two XQs under one FR card). Our
    # cached factorisation makes that the honest report as well.
    refilled: bool = True


@dataclass
class PortalDeck:
    """A deck body (everything up to, not including, its ``NX``)."""

    comments: tuple[str, ...] = ()
    geometry: tuple[Card, ...] = ()
    data_cards: tuple[Card, ...] = ()
    groups: tuple[ExecuteGroup, ...] = ()
    loads: tuple[Card, ...] = ()
    ground: Ground = field(default_factory=Ground)
    ground_plane_flag: bool = False
    yy_points: tuple[tuple[int, int], ...] = ()
    quiet: bool = False
    reduced_field: int | None = None


def _fr_frequencies(card: Card) -> tuple[float, ...]:
    """The frequency list an ``FR`` card asks for (linear or multiplicative)."""
    n = max(card.i(1), 1)
    start, step = card.f(4), card.f(5)
    if card.i(0) == 0:
        return tuple(start + i * step for i in range(n))
    return tuple(start * step**i if step > 0 else start for i in range(n))


def _directive(text: str, keyword: str) -> int | None:
    """``QQ n`` / ``FF n`` out of a CM/CE body (the oracle's processCMLine)."""
    parts = text.split()
    for i, token in enumerate(parts):
        if token.upper() == keyword and i + 1 < len(parts):
            try:
                return int(float(parts[i + 1]))
            except ValueError:
                return None
    return None


def parse_deck(body: str) -> PortalDeck:
    """A deck body's cards, grouped the way the engine executes them."""
    comments: list[str] = []
    geometry: list[Card] = []
    data_cards: list[Card] = []
    groups: list[ExecuteGroup] = []
    loads: list[Card] = []
    sources: list[tuple[int, int, complex]] = []
    yy_points: list[tuple[int, int]] = []
    freqs: tuple[float, ...] = (0.0,)
    fresh_fr = False
    ground = Ground()
    ground_plane_flag = False
    quiet = False
    reduced_field: int | None = None

    for line in body.splitlines():
        card = parse_card(line)
        if card is None:
            continue
        if card.mnemonic in ("CM", "CE"):
            text = card.raw[2:]
            comments.append(text)
            if (qq := _directive(text, "QQ")) and qq > 0:
                quiet = True
            if (ff := _directive(text, "FF")) is not None:
                reduced_field = ff
            continue
        if card.mnemonic in _GEOMETRY_CARDS:
            geometry.append(card)
            if card.mnemonic == "GE" and card.i(0) != 0:
                ground_plane_flag = True
            continue
        if card.mnemonic == "GN":
            # NOTE the ground *annotation* in STRUCTURE SPECIFICATION comes
            # from the GE flag alone: the catalog decks carry `GE 0` + `GN 1`
            # and the oracle prints no "GROUND PLANE SPECIFIED." for them.
            ground = Ground.from_card(card)
            data_cards.append(card)
            continue
        if card.mnemonic in _DEFERRED_CARDS:
            raise PortalError(
                f"{card.mnemonic} ({_DEFERRED_CARDS[card.mnemonic]}) is not "
                f"supported by this engine yet"
            )
        data_cards.append(card)
        if card.mnemonic == "LD":
            if card.i(0) == -1:
                loads.clear()
            else:
                loads.append(card)
        elif card.mnemonic == "FR":
            freqs = _fr_frequencies(card)
            fresh_fr = True
        elif card.mnemonic == "YY":
            vals = card.values
            yy_points = [
                (int(round(vals[i])), int(round(vals[i + 1])))
                for i in range(0, len(vals) - 1, 2)
            ]
        elif card.mnemonic == "EX":
            if card.i(0) != 0:
                raise PortalError(
                    f"EX type {card.i(0)} is not a voltage source; this engine "
                    f"drives EX 0 only"
                )
            sources.append((card.i(1), card.i(2), complex(card.f(4), card.f(5))))
        elif card.mnemonic == "XQ":
            groups.append(
                ExecuteGroup(
                    tuple(sources),
                    freqs if fresh_fr else freqs[-1:],
                    refilled=fresh_fr or not groups,
                )
            )
            sources.clear()
            fresh_fr = False
        else:
            raise PortalError(f"unrecognised NEC card {card.mnemonic!r}")

    return PortalDeck(
        comments=tuple(comments),
        geometry=tuple(geometry),
        data_cards=tuple(data_cards),
        groups=tuple(groups),
        loads=tuple(loads),
        ground=ground,
        ground_plane_flag=ground_plane_flag,
        yy_points=tuple(yy_points),
        quiet=quiet,
        reduced_field=reduced_field,
    )


# --------------------------------------------------------------------------
# row formatting — the column layout IS the contract
# --------------------------------------------------------------------------


def fmt_data_card(number: int, card: Card) -> str:
    """The ``DATA CARD No:`` echo. The ``NX`` form of this line is SimNEC's
    end-of-run sentinel (grammar doc §2): ``partsMatch(parts, "DATA", "CARD",
    "No:", "", "NX")``. Two spaces, the literal, the ordinal, the mnemonic,
    four integer fields, six ``%13.5E`` reals."""
    ints = "".join(f"{card.i(k):4d}" if k == 0 else f"{card.i(k):6d}" for k in range(4))
    reals = "".join(f"{card.f(4 + k):13.5E}" for k in range(6))
    return f"  DATA CARD No:{number:4d} {card.mnemonic}{ints}{reals}"


def fmt_wire_row(n: int, p1, p2, radius, n_seg, first, last, tag) -> str:
    return (
        f" {n:5d} {p1[0]:11.5f} {p1[1]:10.5f} {p1[2]:10.5f}"
        f" {p2[0]:10.5f} {p2[1]:10.5f} {p2[2]:10.5f}"
        f" {radius:10.5f} {n_seg:5d} {first:5d} {last:5d} {tag:4d}"
    )


def fmt_segmentation_row(
    n, centre, length, alpha, beta, radius, i_minus, i_plus, tag
) -> str:
    return (
        f" {n:5d} {centre[0]:9.4f} {centre[1]:9.4f} {centre[2]:9.4f}"
        f" {length:9.4f} {alpha:9.4f} {beta:9.4f} {radius:9.4f}"
        f" {i_minus:5d} {n:5d} {i_plus:5d} {tag:5d}"
    )


def fmt_aip_row(tag, seg, voltage, current, impedance, admittance, power) -> str:
    """The 11-token row SimNEC's ``WAITINGFORSENSORS`` state reads. Fields 4
    and 5 — the CURRENT real and imaginary parts — are the only two numbers it
    keeps, and they become one entry of its Y matrix."""
    return (
        f" {tag:4d} {seg:5d}"
        f" {voltage.real:11.4E} {voltage.imag:11.4E}"
        f" {current.real:11.4E} {current.imag:11.4E}"
        f" {impedance.real:11.4E} {impedance.imag:11.4E}"
        f" {admittance.real:11.4E} {admittance.imag:11.4E}"
        f" {power:11.4E}"
    )


def fmt_current_row(seg, tag, centre, length, current) -> str:
    """A 10-token CURRENTS AND LOCATION row. The ``%6d%5d`` seg/tag widths are
    load-bearing: past ~99999 segments the two run together and SimNEC's
    ``repairRunTogether`` splits ``parts[0]`` at ``len-6`` to recover them."""
    mag = abs(current)
    phase = math.degrees(math.atan2(current.imag, current.real)) if mag else 0.0
    return (
        f" {seg:5d} {tag:4d}"
        f" {centre[0]:9.4f} {centre[1]:9.4f} {centre[2]:9.4f} {length:9.5f}"
        f" {current.real:11.4E} {current.imag:11.4E} {mag:11.4E} {phase:8.3f}"
    )


def fmt_yy_row(currents) -> str:
    """Ward's ``-YY`` report: the currents at the YY card's report points, one
    ``%11.4E`` pair per point. SimNEC's ``addYYLine`` parses it and this build
    of the jar then discards it (grammar doc §6) — we emit it anyway because
    it is four lines of code and the only forward-compatible Y path."""
    body = "".join(f" {v:11.4E}" for c in currents for v in (c.real, c.imag))
    return f"    -YY{body}"


def _loading_cell(value: float | None) -> str:
    """A loading-table numeric cell — 12 blank columns when the leg is absent
    or zero, which is how the oracle prints an omitted R/L/C."""
    if value is None or value == 0.0:
        return " " * 12
    return f"{value:12.4E}"


# --------------------------------------------------------------------------
# solving
# --------------------------------------------------------------------------


def _y_and_port_coeffs(solver):
    """``(Y, X)`` from ONE momwire fill: the short-circuit port admittance
    matrix and the per-port basis-coefficient columns behind it.

    ``compute_y_matrix`` already computes ``X = solve(Z, B)`` — one LU of the
    KCL-augmented operator, one back-substitution per port — and then throws X
    away, returning only ``Y = Bᵀ·X``. Column j of X is the solution for a 1 V
    drive at port j, so keeping it turns ANY later excitation into
    ``coeffs = X @ V`` with no second fill. That is the whole single-fill
    architecture: the alternative (``compute_impedance`` once per execute
    group) refills and refactors per source, which is exactly what the oracle
    does and what this daemon exists to avoid.

    The capture is an instance-level shim rather than a subclass on purpose:
    ``engines/momwire.py`` gates ground models and distributed wire loading on
    the solver class NAME, so a subclass would silently drop a Sommerfeld deck
    back onto a PEC image.
    """
    captured: dict[str, np.ndarray] = {}
    original = solver._solve_with_kcl_ports

    def spy(z, v, kcl_a, overwrite=False):
        x = original(z, v, kcl_a, overwrite=overwrite)
        captured["X"] = x
        return x

    solver._solve_with_kcl_ports = spy
    try:
        y = np.asarray(solver.compute_y_matrix(), dtype=np.complex128)
    finally:
        del solver._solve_with_kcl_ports
    if "X" not in captured:  # pragma: no cover - momwire internals moved
        raise PortalError("momwire did not expose the per-port solution")
    return y, captured["X"]


def _synthesize_union_deck(deck: PortalDeck, ports: list[tuple[int, int]]) -> str:
    """A NEC deck text carrying the geometry, the loading, and ONE ``EX`` per
    distinct port across every execute group.

    Handing this to ``nec_import.parse_nec`` reuses the repo's only card
    parser — GW/GM/GS/GX/GR transforms, LD translation, tag/segment
    addressing, per-wire specs — and gives one geometry translation for the
    whole deck, which is what lets a single fill serve every group.
    """
    lines = [c.raw for c in deck.geometry]
    lines += [c.raw for c in deck.loads]
    lines += [f"EX 0 {tag} {seg} 0 1." for tag, seg in ports]
    return "\n".join(lines) + "\n"


def _locate(wires, tag: int, seg: int) -> tuple[int, int]:
    """NEC (tag, segment) → (wire index, 1-based local segment); ``tag`` 0
    means an absolute segment number. Mirrors ``nec_import._locate_segment``
    against the parsed ``NecWire`` list."""
    seg = max(seg, 1)
    acc = 0
    for i, w in enumerate(wires):
        if tag != 0 and w.tag != tag:
            continue
        if acc + w.n_seg >= seg:
            return i, seg - acc
        acc += w.n_seg
    raise PortalError(
        f"segment {seg} is out of range for "
        + (f"tag {tag}" if tag else "the structure")
    )


@dataclass
class _Segment:
    """One NEC segment of the final structure, in NEC's global numbering."""

    number: int
    tag: int
    wire: int
    local: int
    centre: np.ndarray
    direction: np.ndarray  # p1 -> p2, unnormalised (one segment long)
    radius: float


def _structure_segments(wires) -> list[_Segment]:
    segments: list[_Segment] = []
    n = 0
    for wi, w in enumerate(wires):
        p1 = np.asarray(w.p1, dtype=float)
        p2 = np.asarray(w.p2, dtype=float)
        step = (p2 - p1) / w.n_seg
        for k in range(1, w.n_seg + 1):
            n += 1
            segments.append(
                _Segment(n, w.tag, wi, k, p1 + (k - 0.5) * step, step, w.radius)
            )
    return segments


def _segment_end_nodes(wires):
    """(node key → [signed segment number]) for every segment end.

    NEC's sign convention, used by both the junction table and the
    connection-data columns: negative when the node is the segment's END 1
    (its start), positive when it is END 2.
    """
    eps = 1e-9
    ends: dict[tuple, list[int]] = {}
    order: list[tuple] = []
    n = 0
    for w in wires:
        p1 = np.asarray(w.p1, dtype=float)
        p2 = np.asarray(w.p2, dtype=float)
        step = (p2 - p1) / w.n_seg
        for k in range(w.n_seg):
            n += 1
            for point, sign in ((p1 + k * step, -1), (p1 + (k + 1) * step, 1)):
                key = tuple(int(round(float(c) / eps)) for c in point)
                if key not in ends:
                    ends[key] = []
                    order.append(key)
                ends[key].append(sign * n)
    return ends, order


def _junction_rows(wires) -> list[str]:
    """The MULTIPLE WIRE JUNCTIONS table: one row per node where three or
    more segment ends meet (a plain two-segment joint is not a junction)."""
    ends, order = _segment_end_nodes(wires)
    rows = []
    for key in order:
        members = ends[key]
        if len(members) < 3:
            continue
        members = sorted(members, key=abs)
        body = f"{members[0]:11d}" + "".join(f"{m:5d}" for m in members[1:])
        rows.append(f"{len(rows) + 1:8d}{body}")
    return rows


def _connection_data(wires) -> list[tuple[int, int]]:
    """Per global segment, NEC's ``(I-, I+)`` connection columns.

    Inside a wire the neighbours are the adjacent segments. At a wire end the
    engine names whatever other segment touches the node, signed by which of
    that segment's ends lands there — so a chain reads ``k-1, k, k+1`` and a
    closed loop wraps.
    """
    ends, _order = _segment_end_nodes(wires)
    eps = 1e-9

    def key(p):
        return tuple(int(round(float(c) / eps)) for c in p)

    out = []
    idx = 0
    for w in wires:
        p1 = np.asarray(w.p1, dtype=float)
        p2 = np.asarray(w.p2, dtype=float)
        step = (p2 - p1) / w.n_seg
        for k in range(w.n_seg):
            idx += 1
            here = ends[key(p1 + k * step)]
            there = ends[key(p1 + (k + 1) * step)]
            # An entry m is +seg when the node is that segment's END 2 and
            # -seg when it is END 1, which is already NEC's I- convention;
            # I+ is the same reading from the other side, hence the flip.
            i_minus = next((m for m in here if abs(m) != idx), 0)
            i_plus = -next((m for m in there if abs(m) != idx), 0)
            out.append((i_minus, i_plus))
    return out


class DeckSolver:
    """momwire behind one deck: one geometry, one fill per frequency.

    Ports are the union of every execute group's ``EX`` segments and every
    ``LD`` segment, so a group is just a voltage vector over a port set that
    never changes. A series load is NEC's ld_card semantics exactly — an
    impedance in the segment's current path — which in port algebra is
    ``V_source = V_gap + Z·I``, i.e. ``V_gap = (E + Z·Y)⁻¹·V_source`` and
    ``I = Y·V_gap``. An unloaded, undriven port has ``z = 0`` and ``V = 0``,
    so it collapses to a plain shorted gap: present in the matrix, invisible
    to the physics. That is what lets one port set serve every group.
    """

    def __init__(self, deck: PortalDeck):
        self.portal_deck = deck
        ports: list[tuple[int, int]] = []
        for group in deck.groups:
            for tag, seg, _v in group.sources:
                if (tag, seg) not in ports:
                    ports.append((tag, seg))
        if not ports:
            raise PortalError("deck has no EX card — nothing drives the structure")
        self.ports = ports

        text = _synthesize_union_deck(deck, ports)
        self.deck = parse_nec(text, name="portal deck", network=True)
        self.wires = self.deck.wires
        self.segments = _structure_segments(self.wires)
        self.n_segments = len(self.segments)

        freq_seed = deck.groups[0].freqs_mhz[0] if deck.groups else 0.0
        self.engine = self._build_engine(freq_seed)

        plan = self.deck._port_plan
        names = self.engine._feed_names
        # Port index in the momwire feed ordering, per union EX port and per
        # translated LD port.
        self.feed_index: list[int] = []
        for feed in self.deck.feeds:
            self.feed_index.append(names.index(plan[(feed.wire, feed.seg)]))
        self.load_ports: list[tuple[int, object]] = [
            (names.index(plan[(ld.wire, ld.seg)]), ld) for ld in self.deck.loads
        ]
        self.n_ports = len(names)
        # Global NEC segment number → momwire port index, for every segment
        # that carries a gap. Lets a readout prefer the Galerkin port current
        # (what Y is built from) over the interpolated midpoint current.
        self.port_by_segment: dict[int, int] = {
            self.global_segment(feed.wire, feed.seg): port
            for feed, port in zip(self.deck.feeds, self.feed_index)
        }
        self._cache: dict[float, dict] = {}

    def global_segment(self, wire: int, local: int) -> int:
        """NEC's absolute segment number for 1-based local segment ``local``
        of ``self.wires[wire]``."""
        return sum(w.n_seg for w in self.wires[:wire]) + local

    def report_current(self, tag: int, seg: int, result: dict) -> complex:
        """The current at a ``YY`` report point.

        A point that carries a gap reads its Galerkin port current — the same
        number the ANTENNA INPUT PARAMETERS table prints, so the two Y paths
        agree exactly. A point with no gap has no port, so the interpolated
        segment-midpoint current is the only reading available (and is what
        the oracle prints for every point, its pulse basis making the two
        identical).
        """
        wire, local = _locate(self.wires, tag, seg)
        number = self.global_segment(wire, local)
        port = self.port_by_segment.get(number)
        if port is not None:
            return complex(result["i_port"][port])
        return complex(result["segment_currents"][number - 1])

    # -- construction ------------------------------------------------------

    def _build_engine(self, freq_mhz: float) -> MomwireEngine:
        deck = self.deck
        wires = deck.wire_tuples(specs=True)
        network = deck.network()

        class _DeckBuilder(AntennaBuilder):
            label = "nec_portal"
            default_params = MappingProxyType(
                {"freq": freq_mhz or 1.0, "design_freq": freq_mhz or 1.0}
            )

            def build_wires(self):
                return wires

            def build_network(self):
                return network

        ground = self.portal_deck.ground.momwire_spec()
        return MomwireEngine(
            _DeckBuilder(), solver=BSplineSolver, ground=ground, ground_z=0.0
        )

    # -- per-frequency operator -------------------------------------------

    def at(self, freq_mhz: float) -> dict:
        """The cached (Y, X, solver) for a frequency — one fill, one factor."""
        cached = self._cache.get(freq_mhz)
        if cached is not None:
            return cached
        wavelength = C_LIGHT / (freq_mhz * 1e6)
        started = time.perf_counter()
        solver = self.engine._make_solver(wavelength=wavelength)
        y_sub, coeffs = _y_and_port_coeffs(solver)
        fill_ms = int(round((time.perf_counter() - started) * 1000.0))
        entry = {
            "solver": solver,
            "wavelength": wavelength,
            "Y": self.engine._contract_y(y_sub),
            "X": coeffs,
            "fill_ms": fill_ms,
        }
        self._cache[freq_mhz] = entry
        return entry

    def _load_impedances(self, omega: float) -> np.ndarray:
        z = np.zeros(self.n_ports, dtype=np.complex128)
        for idx, ld in self.load_ports:
            if ld.z is not None:
                z[idx] += complex(ld.z)
            elif ld.parallel:
                y = 0.0 + 0.0j
                if ld.r:
                    y += 1.0 / ld.r
                if ld.l:
                    y += 1.0 / (1j * omega * ld.l)
                if ld.c:
                    y += 1j * omega * ld.c
                z[idx] += (1.0 / y) if y != 0 else 0.0
            else:
                z[idx] += _series_rlc_impedance(ld.r, ld.l, ld.c, omega)
        return z

    def solve_group(self, group: ExecuteGroup, freq_mhz: float) -> dict:
        """One execute group at one frequency: port currents, segment
        currents, and the power budget — all from the cached factorisation."""
        entry = self.at(freq_mhz)
        omega = 2.0 * math.pi * freq_mhz * 1e6
        y = entry["Y"]
        v_source = np.zeros(self.n_ports, dtype=np.complex128)
        driven: list[tuple[int, int, complex]] = []  # (port idx, global seg, V)
        for (tag, seg), port in zip(self.ports, self.feed_index):
            for s_tag, s_seg, volts in group.sources:
                if (s_tag, s_seg) == (tag, seg):
                    v_source[port] = volts
                    wire, local = _locate(self.wires, tag, seg)
                    driven.append((port, self.global_segment(wire, local), volts))
        z_load = self._load_impedances(omega)
        system = np.eye(self.n_ports, dtype=np.complex128) + (z_load[:, None] * y)
        v_gap = np.linalg.solve(system, v_source)
        i_port = y @ v_gap

        w_matrix = self.engine._feed_W
        v_sub = v_gap if w_matrix is None else w_matrix @ v_gap
        coeffs = entry["X"] @ v_sub
        seg_currents = self._segment_currents(entry["solver"], coeffs)

        p_in = 0.5 * float(
            sum((volts * np.conj(i_port[p])).real for p, _s, volts in driven)
        )
        p_load = 0.5 * float(np.sum(np.real(z_load) * np.abs(i_port) ** 2))
        p_wire = 0.0
        if self.engine._loading_kwargs:
            p_wire = float(entry["solver"].wire_loss_power(coeffs)[0])
        p_structure = p_load + p_wire
        p_rad = p_in - p_structure
        return {
            "driven": driven,
            "i_port": i_port,
            "segment_currents": seg_currents,
            "p_in": p_in,
            "p_structure": p_structure,
            "p_radiated": p_rad,
            "efficiency": (100.0 * p_rad / p_in) if p_in > 0 else 0.0,
            "fill_ms": entry["fill_ms"],
            "wavelength": entry["wavelength"],
        }

    def _segment_currents(self, solver, coeffs) -> np.ndarray:
        """Per NEC segment (global order), the midpoint current signed along
        the deck's own p1→p2 direction.

        momwire walks the translated polylines in its own direction, so a
        segment the walker traversed backwards carries the opposite current
        sign; the dot product against the deck wire's direction puts every
        segment back on NEC's convention.
        """
        engine = self.engine
        knot_currents = solver.currents_at_knots(coeffs)
        mids, dirs, vals = [], [], []
        for w_idx, polyline in enumerate(engine._polylines):
            parts = []
            for i, n_e in enumerate(engine._edge_segments[w_idx]):
                seg = np.linspace(polyline[i], polyline[i + 1], n_e + 1)
                parts.append(seg if i == 0 else seg[1:])
            knots = np.vstack(parts)
            cur = np.asarray(knot_currents[w_idx])
            mids.append(0.5 * (knots[1:] + knots[:-1]))
            dirs.append(knots[1:] - knots[:-1])
            vals.append(0.5 * (cur[1:] + cur[:-1]))
        mids = np.concatenate(mids, axis=0)
        dirs = np.concatenate(dirs, axis=0)
        vals = np.concatenate(vals, axis=0)

        wanted = np.array([s.centre for s in self.segments])
        d2 = ((wanted[:, None, :] - mids[None, :, :]) ** 2).sum(axis=2)
        nearest = np.argmin(d2, axis=1)
        out = np.empty(len(self.segments), dtype=np.complex128)
        for i, seg in enumerate(self.segments):
            j = nearest[i]
            sign = 1.0 if float(np.dot(dirs[j], seg.direction)) >= 0 else -1.0
            out[i] = sign * vals[j]
        return out


# --------------------------------------------------------------------------
# the printout
# --------------------------------------------------------------------------


def _structure_rows(deck: PortalDeck, solver: DeckSolver) -> list[str]:
    """The STRUCTURE SPECIFICATION body: the geometry cards as the deck wrote
    them, with the transform annotations the oracle interleaves."""
    rows: list[str] = []
    wire_no = 0
    first_seg = 1
    for card in deck.geometry:
        if card.mnemonic == "GW":
            wire_no += 1
            n_seg = card.i(1)
            rows.append(
                fmt_wire_row(
                    wire_no,
                    (card.f(2), card.f(3), card.f(4)),
                    (card.f(5), card.f(6), card.f(7)),
                    card.f(8),
                    n_seg,
                    first_seg,
                    first_seg + n_seg - 1,
                    card.i(0),
                )
            )
            first_seg += n_seg
        elif card.mnemonic == "GS":
            rows.append(f"     STRUCTURE SCALED BY FACTOR: {card.f(2):10.5f}")
        elif card.mnemonic == "GM":
            rows.append("     THE STRUCTURE HAS BEEN MOVED, MOVE DATA CARD IS:")
            rows.append(
                f" {card.i(0):5d} {card.i(1):5d}"
                + "".join(f" {card.f(2 + k):10.5f}" for k in range(7))
            )
    if deck.ground_plane_flag:
        rows.append("")
        rows.append("     GROUND PLANE SPECIFIED.")
    total = solver.n_segments
    rows.append("")
    rows.append(
        f"     TOTAL SEGMENTS USED: {total}   "
        f"SEGMENTS IN A SYMMETRIC CELL: {total}   SYMMETRY FLAG: 0"
    )
    return rows


def _segmentation_rows(solver: DeckSolver) -> list[str]:
    rows = []
    connections = _connection_data(solver.wires)
    for seg, (i_minus, i_plus) in zip(solver.segments, connections):
        d = seg.direction
        length = float(np.linalg.norm(d))
        alpha = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
        beta = math.degrees(math.atan2(d[1], d[0]))
        rows.append(
            fmt_segmentation_row(
                seg.number,
                seg.centre,
                length,
                alpha,
                beta,
                seg.radius,
                i_minus,
                i_plus,
                seg.tag,
            )
        )
    return rows


def _loading_rows(deck: PortalDeck) -> list[str]:
    rows = []
    for card in deck.loads:
        kind = card.i(0)
        tag, first, last = card.i(1), card.i(2), card.i(3)
        cells = [None] * 6
        if kind in (0, 1, 2, 3):
            cells[0], cells[1], cells[2] = card.f(4), card.f(5), card.f(6)
            name = "PARALLEL" if kind in (1, 3) else "SERIES"
        elif kind == 4:
            cells[3], cells[4] = card.f(4), card.f(5)
            name = "FIXED IMPEDANCE"
        elif kind == 5:
            cells[5] = card.f(4)
            name = "WIRE"
        else:
            raise PortalError(f"LD type {kind} is not supported by this engine")
        rows.append(
            f" {tag:5d} {first:4d} {last:4d}"
            + "".join(_loading_cell(v) for v in cells)
            + _LOADING_TYPE_TAIL[name]
        )
    return rows


def _environment_lines(ground: Ground, freq_mhz: float) -> list[str]:
    pad = " " * 28
    if ground.kind == "free":
        return [_ENVIRONMENT_HEADER, f"{pad}FREE SPACE"]
    if ground.kind == "pec":
        return [_ENVIRONMENT_HEADER, f"{pad}PERFECT GROUND"]
    omega = 2.0 * math.pi * freq_mhz * 1e6
    eps_c = complex(ground.eps_r, -ground.sigma / (omega * EPS0))
    label = (
        "FINITE GROUND - REFLECTION COEFFICIENT APPROXIMATION"
        if ground.kind == "refl"
        else "FINITE GROUND - SOMMERFELD SOLUTION"
    )
    lines = [_ENVIRONMENT_HEADER]
    if ground.kind == "sommerfeld":
        # Column 0, between the header and the label: Execute reads parts[3]
        # into necRun.timings (grammar doc §4.8). We build no ground tables,
        # so the figure is honestly zero.
        lines.append("Somnec Computation Time 0")
    lines += [
        f"{pad}{label}",
        f"{pad}RELATIVE DIELECTRIC CONST:{ground.eps_r:7.3f}",
        f"{pad}CONDUCTIVITY:{ground.sigma:11.3E} MHOS/METER",
        f"{pad}COMPLEX DIELECTRIC CONSTANT:{eps_c.real:12.4E}{eps_c.imag:11.4E}j",
    ]
    return lines


def _run_block(
    deck: PortalDeck, solver: DeckSolver, group: ExecuteGroup, freq_mhz: float
) -> list[str]:
    result = solver.solve_group(group, freq_mhz)
    wavelength = result["wavelength"]
    out: list[str] = []
    if group.refilled:
        out += [
            _FREQUENCY_HEADER,
            f"                                FREQUENCY : {freq_mhz:10.4E} MHz",
            f"                                WAVELENGTH: {wavelength:10.4E} Mtr",
            "",
            *_APPROX_INTEGRATION,
            "",
            "",
            _LOADING_HEADER,
        ]
        rows = _loading_rows(deck)
        if rows:
            out += [*_LOADING_TABLE_HEADER, *rows]
        else:
            out.append(_LOADING_NONE)
        out += ["", ""]
        out += _environment_lines(deck.ground, freq_mhz)
        out += ["", ""]
        out += [
            _MATRIX_TIMING_HEADER,
            f"                               FILL: {result['fill_ms']} msec"
            f"  FACTOR: 0 msec",
            "",
            "",
        ]
    out += [_AIP_HEADER, *_AIP_TABLE_HEADER]
    i_port = result["i_port"]
    for port, global_seg, volts in result["driven"]:
        current = i_port[port]
        impedance = volts / current if current != 0 else complex(0.0, 0.0)
        admittance = current / volts if volts != 0 else complex(0.0, 0.0)
        power = 0.5 * (volts * np.conj(current)).real
        out.append(
            fmt_aip_row(
                solver.segments[global_seg - 1].tag,
                global_seg,
                volts,
                complex(current),
                impedance,
                admittance,
                float(power),
            )
        )
    out += ["", "", _CURRENTS_HEADER, _CURRENTS_NOTE, "", *_CURRENTS_TABLE_HEADER]
    currents = result["segment_currents"]
    if deck.yy_points:
        out.append(
            fmt_yy_row(
                [solver.report_current(tag, seg, result) for tag, seg in deck.yy_points]
            )
        )
    for seg in solver.segments:
        out.append(
            fmt_current_row(
                seg.number,
                seg.tag,
                seg.centre / wavelength,
                float(np.linalg.norm(seg.direction)) / wavelength,
                complex(currents[seg.number - 1]),
            )
        )
    pad = " " * 31
    out += [
        "",
        "",
        _POWER_HEADER,
        f"{pad}INPUT POWER   ={result['p_in']:12.4E} Watts",
        f"{pad}RADIATED POWER={result['p_radiated']:12.4E} Watts",
        f"{pad}STRUCTURE LOSS={result['p_structure']:12.4E} Watts",
        f"{pad}NETWORK LOSS  ={0.0:12.4E} Watts",
        f"{pad}EFFICIENCY    ={result['efficiency']:8.2f} Percent",
    ]
    return out


def render_deck(body: str) -> tuple[list[str], list[str]]:
    """(stdout lines, stderr lines) for one deck body — no banner, no ``NX``.

    The banner belongs to the *process*, not the deck: the oracle prints it
    once at start-up and once again right after consuming each ``NX``, in
    anticipation of the next deck (three banners for two decks). ``run_deck``
    and ``main`` add those; this function is the deck's own printout.

    The caller also appends the ``NX`` echo — the sentinel must be emitted
    whether the run succeeded or failed, or SimNEC blocks in ``readLine()``
    forever (grammar doc §2 and §10.1).
    """
    out: list[str] = ["", "", ""]
    err: list[str] = []
    try:
        deck = parse_deck(body)
    except PortalError as exc:
        out.append(f"{_ERROR_PREFIX}{exc}")
        return out, err

    if deck.reduced_field is not None:
        # The ONLY thing this engine may ever write to stderr: NEC2Daemon
        # never drains the child's stderr, so anything more can fill the pipe
        # buffer and deadlock the UI (grammar doc §10.9).
        err.append(f"reducedField:{deck.reduced_field}")

    out.append(_COMMENTS_HEADER)
    out += [f"{_COMMENT_INDENT}{text}" for text in deck.comments]
    out += ["", "", ""]

    try:
        solver = DeckSolver(deck)
    except PortalError as exc:
        out.append(f"{_ERROR_PREFIX}{exc}")
        return out, err
    except (ValueError, np.linalg.LinAlgError) as exc:
        out.append(f"{_ERROR_PREFIX}{exc}")
        return out, err

    out.append(_STRUCTURE_HEADER)
    out += _STRUCTURE_NOTES
    out.append("")
    out += _WIRE_TABLE_HEADER
    out += _structure_rows(deck, solver)
    out.append("")
    junctions = _junction_rows(solver.wires)
    if junctions:
        out += [*_JUNCTIONS_HEADER, *junctions, ""]
    out.append("")
    if not deck.quiet:
        out.append(_SEGMENTATION_HEADER)
        out += _SEGMENTATION_NOTES
        out.append("")
        out += _SEGMENTATION_TABLE_HEADER
        out += _segmentation_rows(solver)
        out += ["", ""]
    out.append("")

    group_index = 0
    number = 0
    for card in deck.data_cards:
        number += 1
        out.append(fmt_data_card(number, card))
        if card.mnemonic != "XQ":
            continue
        group = deck.groups[group_index]
        group_index += 1
        out += ["", ""]
        try:
            for i, freq in enumerate(group.freqs_mhz):
                if i:
                    out += ["", ""]
                out += _run_block(deck, solver, group, freq)
        except (PortalError, ValueError, np.linalg.LinAlgError) as exc:
            out.append(f"{_ERROR_PREFIX}{exc}")
        out += ["", "", ""]
    return out, err


def deck_frame(body: str) -> tuple[list[str], list[str]]:
    """One deck's stdout frame: printout, the ``NX`` sentinel, trailing banner.

    Card numbering restarts at 1 inside every deck, so the sentinel's ordinal
    is the deck's own card count plus one (grammar doc §1).
    """
    out, err = render_deck(body)
    echoed = sum(1 for line in out if line.startswith("  DATA CARD No:"))
    out.append(fmt_data_card(echoed + 1, Card("NX", (), "NX")))
    # The oracle reprints its banner right after consuming NX, in anticipation
    # of the next deck; SEEKING ignores it. Reproduced so a resident
    # transcript frames identically (grammar doc §1, §10.8).
    out += list(_BANNER[1:])
    return out, err


def run_deck(body: str) -> tuple[str, str]:
    """(stdout, stderr) for a single deck run against a fresh process: the
    start-up banner, the deck's frame, and whatever went to stderr."""
    out, err = deck_frame(body)
    return (
        "\n".join([*_BANNER, *out]) + "\n",
        ("\n".join(err) + "\n" if err else ""),
    )


# --------------------------------------------------------------------------
# the resident protocol
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None, stdin=None, stdout=None, stderr=None) -> int:
    """The daemon. ``-version`` probes; otherwise read decks until stdin ends.

    Decks are framed on stdin by an ``NX`` card and by nothing else — no
    length prefix, no sentinel of our own — and the process is never restarted
    between them (``NEC2Daemon.submit``).
    """
    argv = sys.argv[1:] if argv is None else argv
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr

    if any(a.lstrip("-").lower() == "version" for a in argv):
        stdout.write(f"{PROBE_VERSION}\n")
        stdout.flush()
        return 0

    # The banner belongs to process start-up; every later one trails an NX.
    stdout.write("\n".join(_BANNER) + "\n")
    stdout.flush()

    body: list[str] = []
    for line in stdin:
        if line.strip().upper().split()[:1] != ["NX"]:
            body.append(line.rstrip("\n"))
            continue
        out, err = deck_frame("\n".join(body))
        stdout.write("\n".join(out) + "\n")
        stdout.flush()
        if err:
            stderr.write("\n".join(err) + "\n")
            stderr.flush()
        body = []
    return 0


if __name__ == "__main__":  # pragma: no cover - console-script entry point
    raise SystemExit(main())
