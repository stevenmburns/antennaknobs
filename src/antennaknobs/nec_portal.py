"""momwire as a resident SimNEC engine — the ``nec2c`` portal daemon.

SimNEC (``nec2/NEC2Daemon``) starts one NEC-2 process and keeps it: decks
arrive on stdin framed by an ``NX`` card, printouts leave on stdout, and the
Java side blocks in ``readLine()`` until it sees the ``NX`` data-card echo.
This module is that process, with momwire behind it instead of nec2c.

The contract is pinned in ``docs/status/2026-08-08-simnec-execute-grammar.md``
(issue #792 units 1-3) and in the 36 oracle deck/printout pairs under
``tests/fixtures/nec_portal/``. Everything here — column widths, header
strings, section order, the ``-YY`` row, the stderr discipline — is copied out
of those two sources. **Layout is the contract; the numbers are momwire's.**
A different basis and kernel will never reproduce nec2c digit for digit, and
SimNEC does not need it to: it reads exactly two numbers per
``ANTENNA INPUT PARAMETERS`` row (the CURRENT real/imaginary columns, fields 4
and 5 of an 11-token row) and builds its Y matrix from them.

Scope (units 2 and 3 — the whole portal dialect bar the long tail):

* the version probe, the resident stdin loop, the ``NX`` sentinel;
* ``CM``/``CE`` directives ``QQ`` (quiet) and ``FF`` (the one stderr line);
* geometry ``GW``/``GM``/``GS``/``GX``/``GR``/``GA``/``GH``/``GE``, environment
  ``GN 0/1/2``, loading ``LD 0/1/4/5``, excitation ``EX 0``, ``FR``, ``XQ``,
  and Ward's ``YY`` report card;
* unit 3: ``RP 0`` radiation patterns, ``NE``/``NH`` near-field grids, and
  ``NT`` two-port networks — each of which is also an *execute* card in its
  own right (``RP``/``NE``/``NH`` run the pending group, so a bare ``XQ``
  after one of them re-runs nothing);
* issue #799: ``TL`` transmission lines, which nec2c prints as an equivalent
  network — same ``NETWORK DATA`` banner as ``NT``, a different three-line
  column header, and a trailing ``STRAIGHT``/``CROSSED`` type word;
* issue #800: ``MP``, the ae6ty multicore hint SimNEC emits automatically past
  256 segments — parsed, echoed, and its one advisory line reproduced, with the
  ``#Proc``/``blockSize`` numbers deliberately not acted on (see
  :class:`Multiprocessing`) — and ``PT``, which turned out to be a plain
  toggle on the ``CURRENTS AND LOCATION`` table rather than anything entangled
  with the plane-wave excitation SimNEC wraps it in (see
  :class:`PrintControl`);
* issue #800 (tail): ``GD``, NEC-2's additional-ground-parameters card, which
  SimNEC's EZNEC-derived examples carry and forward — parsed, echoed, and
  otherwise inert. **Fidelity note:** ``GD``'s second medium reaches NEC only
  through the far field, and only through the ``RP`` card's cliff and
  ground-screen modes (``RP 1``-``RP 6``); it never enters the matrix, so
  every impedance and current is unchanged by it, and the ``RP 0`` pattern
  this engine computes is byte-identical with and without the card (measured
  both ways on the oracle). The modes where it WOULD move the pattern are
  already refused by name at the ``RP`` card, so nothing here answers a
  second-medium question by pretending the medium is not there
  (see :class:`SecondMedium`);
* the printout sections SimNEC's state machine walks: banner, comments, data
  cards, structure specification, segmentation data, frequency, structure
  impedance loading, antenna environment, network data, matrix timing, antenna
  input parameters, currents and location, power budget, radiation patterns,
  near electric/magnetic fields.

Still deferred (unit 4 / out of scope): ``IS``, surface
patches, ``RP`` modes other than 0, spherical
``NE``/``NH`` grids, and ``GN`` radial-wire ground screens. Those cards take
the error path below rather than crashing the daemon — the printout says which
card and why, and the ``NX`` sentinel is still emitted.

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
from momwire import (
    ArrayBlockSolver,
    BSplineSolver,
    HMatrixSolver,
    SinusoidalGalerkinSolver,
    SinusoidalSolver,
)


from .builder import AntennaBuilder
from .engines.momwire import MomwireEngine
from .nec_import import parse_nec
from .network import _series_rlc_impedance
from .network_reduce import SingularNetworkError, tl_admittance_2x2

# --basis choices (mirrors the CLI's MOMWIRE_BASES/VARIANTS subset that makes
# sense behind SimNEC): name -> (solver class, solver kwargs, banner suffix).
# Two portal-dialog entries differing only in --basis give a SimNEC user
# cross-basis validation inside SimNEC itself; `-converged` is the
# recommended setting for near-open high-Q feeds (momwire#213), the class
# where the live session measured the largest cross-engine gap.
# `sinusoidal` is the NEC-closest rung of that ladder — three-term basis,
# collocation testing, Eq-187 delta gap — so it answers "does momwire
# reproduce NEC-2's behaviour, mesh walk and all" rather than "what does a
# better-converged basis say". It has no `-converged` twin on purpose: the
# zero-width point gap has no collocation RHS (momwire#212) and the solver
# refuses it rather than silently serving the segment gap, which is the same
# constraint the CLI's MOMWIRE_BASIS_VARIANTS records.
# `bspline-d1` (issue #821) is the degree axis instead: same BSplineSolver
# class as `bspline`, degree=1 bound — a d1-vs-d2 convergence check a SimNEC
# user can run as two portal entries, zero new physics.
# `hmatrix` and `arrayblock` (issue #830, on Ward's ask for large arrays) are
# a third axis again: the SAME B-spline physics as `bspline`, solved by an
# accelerated operator instead of a dense fill — hierarchical ACA compression
# for `hmatrix`, and for `arrayblock` the element-aware block decomposition
# that becomes an FFT convolution over a regular same-shape lattice. Neither
# is a fidelity choice, so neither has a `-converged` twin and neither can be
# read against `bspline` as a physics A/B: they answer "can this deck be
# solved at array scale", and their answers must AGREE with `bspline` to the
# iterative solve tolerance. `arrayblock` degrades to the parent H-matrix on
# a deck with no repeated-block structure (momwire#143 `_degenerate_partition`)
# rather than refusing, so both entries are safe on arbitrary decks.
_BASES = {
    "bspline": (BSplineSolver, {}, ""),
    "bspline-d1": (BSplineSolver, {"degree": 1}, "+bs1"),
    "hmatrix": (HMatrixSolver, {}, "+hm"),
    "arrayblock": (ArrayBlockSolver, {}, "+ab"),
    "sinusoidal": (SinusoidalSolver, {}, "+sin"),
    "sinusoidal-galerkin": (SinusoidalGalerkinSolver, {}, "+sg"),
    "sinusoidal-galerkin-converged": (
        SinusoidalGalerkinSolver,
        {"feed_model": "point"},
        "+sgc",
    ),
}
_active_basis = _BASES["bspline"]

__all__ = [
    "BANNER_VERSION",
    "LEGACY_PROBE_VERSION",
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
# against four anchored regexes. We answer the FOURTH, ``versionNECd =
# (NEC\d+\D.*)`` — honest identity, sanctioned by Ward (2026-08-08: "If you
# respond with something like NEC2text#.# things will work") and verified
# against the 6p4d6 bytecode (issue #828; grammar doc, 2026-08-09 addendum):
# a versionNECd match calls ``setVersion(line)`` and returns success — group(1)
# is never read, nothing is Double-parsed, there is no version floor, and NO
# engine state is set. The engine enum (and with it the daemon class, the
# sensor-row offsets, and every dialect switch) comes from the EXECUTABLE
# FILENAME alone, so the binary must keep ``nec2c`` in its name (and its path
# must not contain the substring ``out``). The string SimNEC stores is shown
# in the portal dialog's NECVersion row, echoed back to us as a ``CM version``
# card on every deck, and re-read once by ``Options.getEngine()``, whose
# ``[a-zA-Z]*([0-9])+?(.*)`` must extract "2" (the W7EL insulation gate tests
# it) — which is why the identity must start with ``NEC2`` (exact case, and a
# non-digit right after the 2) and why the tail after it is genuinely free.
# The #.# tail is genuinely free on the NECd path, so it carries the real
# package version. installed-metadata caveat: an editable install reports the
# version recorded at `pip install -e` time, so a dev box that skipped the
# reinstall after a bump probes the stale number — cosmetic there, and always
# correct on a wheel install.
try:
    from importlib.metadata import version as _pkg_version

    _MAJ, _MIN = _pkg_version("antennaknobs").split(".")[:2]
except Exception:  # pragma: no cover - no installed metadata (source tree)
    _MAJ, _MIN = "0", "0"
PROBE_VERSION = f"NEC2momwire.{_MAJ}.{_MIN}"

# The masquerade this build used through v0.46 — versionA's shape, whose tail
# rides ``Double.valueOf`` against the 1.23 floor. Kept behind ``--legacy-probe``
# for SimNEC builds old enough to predate versionNECd, until one is confirmed
# not to exist; the flag rides the portal-dialog command line like --basis.
LEGACY_PROBE_VERSION = "nec2c.ae6ty.9.1"

# The banner inside a printout is NOT version-checked: the four regexes are
# ``lookingAt()``, i.e. anchored, and the banner line is prefixed ``VERSION:``
# so none of them can match it.  That makes it the safe place to say who we
# actually are.
BANNER_VERSION = "nec2c.ae6ty.momwire.9.1"

C_LIGHT = 299_792_458.0
EPS0 = 8.854_187_817e-12
ETA0 = 376.730_313_668

# nec2c's two degenerate-value thresholds. They are both spelt 1e-20 and they
# are NOT the same test — a fact that hides completely while every pattern
# fixture is taken at one range and one wavelength, and stops hiding the
# moment an ``RFLD = 0`` deck arrives (issue #802).
#
# * ``_GAIN_FLOOR2`` is ``db10()``'s: it clamps the LINEAR POWER GAIN, the
#   number about to be logged, so a direction below -200 dB prints -999.99.
#   Gain never depended on the range, so this floor is range-free too.
# * ``_FIELD_FLOOR2`` is the polarisation block's: ``(ethm2 <= 1e-20) &&
#   (ephm2 <= 1e-20)`` blanks AXIAL/TILT/SENSE, and a blank SENSE is exactly
#   what makes a row 11 tokens instead of 12. It is applied to the field as
#   ``ffld`` returns it — BEFORE the ``*wlam`` and the ``*1/RFLD`` that turn
#   it into the volts-per-metre the table prints — so it is a fixed bar on
#   the antenna, not on the reading. :func:`_pattern_lines` rescales the
#   printed field back to that basis before testing it.
#
# Read off ``dipole_rp_pattern.out`` (E_theta = 5.4196E-15 at theta = 180 ->
# -999.99 and blank) and confirmed against ``dipole_rp_crossed_quadrature.out``
# (E_theta = 2.7098E-15 -> VERTC -999.99 but SENSE still LINEAR, because
# E_phi is large). Grammar doc §4.14.
_FIELD_FLOOR2 = 1.0e-20
_GAIN_FLOOR2 = 1.0e-20
_GAIN_FLOOR_DB = -999.99

# The ``RP`` modes this engine computes: space wave, linear cliff, circular
# cliff. See :func:`_validate_rp` for what the rest ask for and why they are
# refused rather than approximated.
_RP_MODES = frozenset({0, 2, 3})
# ...and the two that consume a second medium, keyed to the word nec2c prints
# in the FAR FIELD GROUND PARAMETERS block.
_CLIFF_KIND = {2: "LINEAR", 3: "CIRCULAR"}

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


def _banner_lines() -> tuple:
    """The process banner, with the basis recorded in the version tail.

    The default basis keeps the exact historical banner (fixture-pinned);
    a non-default one appends its suffix (`+sg` / `+sgc`) so a session
    transcript records which physics answered. Only the PRINTOUT banner —
    the `-version` probe line never changes, since SimNEC Double-parses it.
    """
    suffix = _active_basis[2]
    if not suffix:
        return _BANNER
    return tuple(
        line if not line.startswith("VERSION:") else line + suffix for line in _BANNER
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

# ---------------------------------------------------------------------------
# unit 3 chrome — copied byte for byte out of dipole_nt_network.out,
# dipole_rp_pattern.out, dipole_ne_nearfield.out and dipole_nh_nearfield.out.
# ---------------------------------------------------------------------------

_NETWORK_HEADER = (
    "                                            ---------- NETWORK DATA ----------"
)
_NETWORK_TABLE_HEADER = (
    "  -- FROM -  --- TO --            -------- ADMITTANCE MATRIX ELEMENTS"
    " (MHOS) ---------",
    "  TAG   SEG  TAG   SEG   ----- (ONE,ONE) ------   ----- (ONE,TWO) -----"
    "   ----- (TWO,TWO) -------",
    "  No:   No:  No:   No:      REAL      IMAGINARY      REAL     IMAGINARY"
    "       REAL      IMAGINARY",
)
# issue #799 — copied byte for byte out of dipole_tl_network.out. nec2c prints
# a TL card as an *equivalent network*: same NETWORK DATA banner, but the three
# column-header lines describe the card's own fields (Z0, length, the two end
# shunt admittances) instead of a Y matrix, and the row carries a trailing LINE
# TYPE word. nec2c re-emits whichever header block matches the row it is about
# to print whenever the KIND changes, so a deck mixing TL and NT shows two
# header blocks under one banner — in card order, straight and crossed lines
# sharing one block (fixture: dipole_tl_shunt_crossed.out).
_LINE_TABLE_HEADER = (
    "  -- FROM -  --- TO --      TRANSMISSION LINE        --------- SHUNT"
    " ADMITTANCES (MHOS) ---------   LINE",
    "  TAG   SEG  TAG   SEG    IMPEDANCE      LENGTH     ----- END ONE -----"
    "      ----- END TWO -----   TYPE",
    "  No:   No:  No:   No:         OHMS      METERS      REAL      IMAGINARY"
    "      REAL      IMAGINARY",
)

_NETWORK_EXCITATION_HEADER = (
    "                          --------- STRUCTURE EXCITATION DATA AT NETWORK"
    " CONNECTION POINTS --------"
)
# Same 11-token row shape as ANTENNA INPUT PARAMETERS, but the oracle's header
# spacing differs by a column here and there — copy it, do not reuse.
_NETWORK_EXCITATION_TABLE_HEADER = (
    "  TAG   SEG       VOLTAGE (VOLTS)          CURRENT (AMPS)         IMPEDANCE"
    " (OHMS)       ADMITTANCE (MHOS)     POWER",
    "  No:   No:     REAL      IMAGINARY     REAL      IMAGINARY     REAL     "
    " IMAGINARY     REAL      IMAGINARY   (WATTS)",
)

_PATTERN_HEADER = (
    "                             ---------- RADIATION PATTERNS -----------"
)
# Printed by ``rdpat`` ahead of the pattern banner whenever the RP mode is > 1,
# on the POWER BUDGET block's 31-column indent rather than the pattern's 29.
_FAR_FIELD_GROUND_HEADER = (
    "                               ------ FAR FIELD GROUND PARAMETERS ------"
)
_PATTERN_TABLE_HEADER = (
    " ---- ANGLES -----     ----- POWER GAINS -----       ---- POLARIZATION ----"
    "   ---- E(THETA) ----    ----- E(PHI) ------",
    "  THETA      PHI       VERTC    HORIZ    TOTAL       AXIAL      TILT  SENSE"
    "   MAGNITUDE    PHASE    MAGNITUDE     PHASE",
    " DEGREES   DEGREES        DB       DB       DB       RATIO   DEGREES        "
    "    VOLTS/M   DEGREES     VOLTS/M   DEGREES",
)
_PATTERN_TIME = "    Radiation Compute Time 0"

_NEAR_E_HEADER = "                             -------- NEAR ELECTRIC FIELDS --------"
# NOTE the magnetic banner is NOT the electric one with a word swapped: the
# indent and the trailing dash run both differ. Both arm the same
# WAITINGFORMETERSMETERSMETERS state, so the difference is cosmetic — but it is
# still bytes, and bytes are the contract.
_NEAR_H_HEADER = (
    "                                   -------- NEAR MAGNETIC FIELDS ---------"
)
_NEAR_E_TABLE_HEADER = (
    "     ------- LOCATION -------     ------- EX ------    ------- EY ------"
    "    ------- EZ ------",
    "      X         Y         Z       MAGNITUDE   PHASE    MAGNITUDE   PHASE"
    "    MAGNITUDE   PHASE",
    "    METERS    METERS    METERS     VOLTS/M  DEGREES    VOLTS/M   DEGREES"
    "     VOLTS/M  DEGREES",
)
_NEAR_H_TABLE_HEADER = (
    "     ------- LOCATION -------     ------- HX ------    ------- HY ------"
    "    ------- HZ ------",
    "      X         Y         Z       MAGNITUDE   PHASE    MAGNITUDE   PHASE"
    "    MAGNITUDE   PHASE",
    "    METERS    METERS    METERS      AMPS/M  DEGREES      AMPS/M  DEGREES"
    "      AMPS/M  DEGREES",
)
_NEAR_FIELD_TIME = "    Near Field Compute Time 0"

# Elements per momwire mesh segment when evaluating a near field. The far-field
# sum needs one dipole per segment because only the radiation-zone limit
# matters; a near field a metre from a half-metre segment does not, so each
# segment is resampled through ``currents_at_knots(coeffs, s_array=...)`` and
# summed as a finer chain of Hertzian elements.
_NEAR_FIELD_SUBDIV = 8

# Reversed by issue #829 on Ward's explicit sanction (his 2026-08-08 reply):
# refusals used to hide behind this prefix specifically to AVOID tripping
# Execute's `"NEC ERROR (1)"` warning frame (grammar doc §8 — the frame fires
# on token 0 being exactly `ERROR:`, an equality test, not a substring one).
# Ward said the frame "should be fine" and that he intends to make the reader
# bail on it, so every refusal now leads with an `_ERROR_TOKEN` line to fire
# that frame today and anchor his future bail-fix tomorrow. This prefix stays
# as the line right after it: it is not our own invention but the oracle's
# own genuine stdin-EOF string (§8, "Oracle-side error strings observed"),
# so keeping it gives grep a byte-identical, oracle-shaped needle for "this
# was our engine's refusal" without colliding with the new warning token.
_ERROR_TOKEN = "ERROR: "
_ERROR_PREFIX = "ERROR-NEC2C: "


def _append_error(out: list[str], exc: BaseException) -> None:
    """Append the two-line refusal frame and nothing else.

    Line 1 is what SimNEC's ``Execute.processResponse`` keys on — token 0
    exactly ``ERROR:`` trips the ``"NEC ERROR (1)"`` warning and (today)
    keeps parsing; Ward's planned reader fix anchors to the same token.
    Line 2 repeats the message under the oracle's own ``ERROR-NEC2C:``
    shape for our tests/logs to grep. Every caller still appends the ``NX``
    echo itself — that sentinel is mandatory on every path, see
    ``PortalError``'s docstring, or SimNEC blocks in ``readLine()`` forever.
    """
    detail = str(exc)
    out.append(f"{_ERROR_TOKEN}{detail}")
    out.append(f"{_ERROR_PREFIX}{detail}")


class PortalError(Exception):
    """A deck this build cannot run. Reported on the error path, never fatal:
    the daemon still emits the NX sentinel so the Java side does not block."""


# --------------------------------------------------------------------------
# cards
# --------------------------------------------------------------------------

# Cards echoed inside STRUCTURE SPECIFICATION rather than as DATA CARD lines.
_GEOMETRY_CARDS = frozenset({"GW", "GA", "GH", "GM", "GX", "GR", "GS", "GE"})

# Cards the portal dialect can carry that this build does not model. They are
# named so the error path can say WHICH card, instead of "unrecognised".
_DEFERRED_CARDS = MappingProxyType(
    {
        "IS": "NEC-4.2 wire insulation",
        "SP": "surface patch",
        "SM": "multiple-patch surface",
    }
)

# Cards that RUN the pending excitation group. ``RP``/``NE``/``NH`` are not
# just report requests: nec2c executes on reading them and then prints their
# table after the power budget, which is why ``dipole_rp_pattern.out`` echoes
# EX / FR / RP, runs, and only then echoes the trailing ``XQ`` — an ``XQ`` with
# nothing new since the last execution produces no output at all.
_EXECUTE_CARDS = frozenset({"XQ", "RP", "NE", "NH"})

# Cards that make the next execute card a real run rather than a no-op.
_ARMING_CARDS = frozenset({"EX", "FR", "LD", "GN", "NT", "TL", "YY", "EK"})


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
            # I2 is NRADL, the radial-wire ground-screen count. nec2c models a
            # screen as a surface impedance on the reflection-coefficient
            # ground only; momwire has no screen model at all, so ignoring the
            # field would silently change the physics. Reject it by name.
            # (For GN 2 the oracle refuses it too, with
            # "RADIAL WIRE G.S. APPROXIMATION MAY NOT BE USED WITH SOMMERFELD
            # GROUND OPTION" — and then aborts WITHOUT the NX echo. Grammar
            # doc §11.)
            if card.i(1) != 0:
                raise PortalError(
                    f"GN {code} with a {card.i(1)}-wire radial ground screen is "
                    f"not supported by this engine"
                )
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


@dataclass(frozen=True)
class SecondMedium:
    """NEC-2's *additional ground parameters*: a SECOND ground medium and the
    edge where medium 1 stops.

    **What the card is.** Four real fields, and — measured against the oracle
    — nothing else. The four integer columns of the echo are read as integers
    and used by nothing; a bare ``GD`` echoes four zero integers and six zero
    reals and runs the deck exactly as a fully populated one does.

    **Which card carries it.** ``GD`` is the obvious one, and the only one
    ``nec2/NECSource`` writes. It is not the only one that works: a ``GN``
    whose ``NRADL`` count is zero carries the same four values in ``F3``-``F6``
    and ``main.c`` writes them into the same four slots, so a deck can state a
    whole cliff without ever sending a ``GD``. Both routes land here, and a
    later card overwrites an earlier one exactly as it does in the oracle.

    ==========  =========================================================
    field       meaning
    ==========  =========================================================
    ``F1``      ``EPSR2`` — relative dielectric constant of medium 2
    ``F2``      ``SIG2`` — conductivity of medium 2, mhos/metre
    ``F3``      ``CLT`` — distance from the origin to the edge where the
                two media join (the cliff's EDGE DISTANCE)
    ``F4``      ``CHT`` — height of medium 2's surface relative to
                medium 1's, signed (negative = the far side is lower)
    ==========  =========================================================

    The readings come from the oracle's own printout, not from a manual: a
    deck carrying ``GD 0 0 0 0 5. .001 20. -2.`` under ``RP 2`` prints

    .. code-block:: text

                                       --- LINEAR CLIFF ---
                                       EDGE DISTANCE=     20.00 METERS
                                              HEIGHT=     -2.00 METERS
                                       --- SECOND MEDIUM ---
                                       RELATIVE DIELECTRIC CONST=      5.000
                                             GROUND CONDUCTIVITY=      0.001 MHOS

    which names all four fields in card order.

    **Why it had to land.** SimNEC's EZNEC-derived examples — ``Cardioid
    (EZNEC).ssn``, ``4-square (EZNEC).ssn`` — carry a ``GD`` and ``NECSource``
    forwards it verbatim, so refusing the card failed those decks outright and
    SimNEC fabricated readouts from the failure (R = 0, X = 0; the same shape
    of live failure the ``EK`` card caused, grammar doc §17).

    **What it changes outside the far field: nothing.** No ``DATA CARD`` line
    beyond its own echo, no line in the ``ANTENNA ENVIRONMENT`` block — not
    even under ``GN 2``, where a second medium might plausibly have announced
    itself — and no change to any number in the matrix path. Fixtures
    ``dipole_gd_second_medium`` and ``dipole_gd_cliff_sommerfeld`` are
    ``dipole_pec_ground`` and ``dipole_sommerfeld_ground`` plus one card, and
    the only differences in either printout are the echo itself and the
    ordinals it shifts. NEC-2 uses the second medium in the FAR FIELD alone;
    the moment method never sees it, so every impedance and every segment
    current is the flat-ground one.

    It is also **not an arming card**: measured on the oracle, ``... XQ / GD
    2 0 0 0 13. .005 0. 0. / XQ`` prints one block, not two. A ``GD`` alone
    does not make the next execute card a real run.

    **Where it does bite: the ``RP`` card's cliff modes.** The far field
    reaches this record only through ``RP 2`` and ``RP 3`` (and the screen
    combinations 5 and 6, which this engine refuses for the screen's sake, not
    the cliff's). Measured both ways on the oracle:

    * under ``RP 0`` the ``RADIATION PATTERNS`` table is byte-identical with
      and without the card — the property ``dipole_gd_*`` still pins;
    * under ``RP 2`` and ``RP 3`` it is not: a ``FAR FIELD GROUND PARAMETERS``
      block appears and the gains move by several dB at grazing angles.

    Those two modes were refused outright until issue #802, which is what made
    accepting the card safe in the first place. They now run —
    :func:`_cliff_image_moments` implements the medium selection — so this
    record is load-bearing rather than a receipt, and the honesty argument has
    moved from "we are never asked" to "we answer it the way ``ffld`` does".
    """

    eps_r2: float = 0.0
    sigma2: float = 0.0
    edge_distance: float = 0.0  # CLT
    height: float = 0.0  # CHT

    @classmethod
    def from_card(cls, card: Card) -> SecondMedium:
        return cls(card.f(4), card.f(5), card.f(6), card.f(7))


@dataclass(frozen=True)
class NetworkBranch:
    """One ``NT`` card: a reciprocal two-port admittance across two segments.

    NEC's card gives ``Y11``, ``Y12`` and ``Y22`` (real + imaginary each) and
    takes ``Y21 = Y12``. The branch hangs off the two segments' gaps, in
    parallel with the structure, so its current adds to the segment current at
    the same node — which is why the driven port's ANTENNA INPUT PARAMETERS
    current is the SOURCE current (segment + network) and not the segment
    current the CURRENTS AND LOCATION table prints.
    """

    a: tuple[int, int]  # (tag, segment) of port one
    b: tuple[int, int]  # (tag, segment) of port two
    y11: complex
    y12: complex
    y22: complex

    @classmethod
    def from_card(cls, card: Card) -> NetworkBranch:
        return cls(
            (card.i(0), card.i(1)),
            (card.i(2), card.i(3)),
            complex(card.f(4), card.f(5)),
            complex(card.f(6), card.f(7)),
            complex(card.f(8), card.f(9)),
        )


@dataclass(frozen=True)
class LineBranch:
    """One ``TL`` card: an ideal transmission line across two segments.

    NEC solves a ``TL`` by substituting the line's *equivalent network* — the
    same 2×2 short-circuit admittance an ``NT`` card states directly — so
    everything unit 3 pinned about ``NT`` (the gap cut, the floating undriven
    port, the source-vs-segment current split, ``NETWORK LOSS``) holds here
    unchanged. Only three things are the card's own:

    * **crossed lines are a NEGATIVE z0.** The printout echoes ``|z0|`` and
      says ``CROSSED`` in the LINE TYPE column; the physics is port B's
      polarity inverted, which flips the sign of the off-diagonal transfer
      terms ONLY — not a negative z0 in the formula, which would wrongly
      negate the diagonal self terms too.
    * **length 0 means the straight-line distance** between the two
      connection points (the segment centres). The printout echoes the
      RESOLVED length, so a zero-length card never prints a zero.
    * **the two end admittances shunt onto the diagonal**, Y11 += y_a and
      Y22 += y_b, which is what makes a lossy line's ``NETWORK LOSS``
      non-zero.

    Those three rules are ``nec_import.NecTL``'s as well — the same card read
    by the same repo's other translator — and
    ``tests/test_nec_portal.py::test_the_portal_and_nec_import_translate_tl_the_same_way``
    holds the two readings against each other. The admittance itself comes
    from ``network_reduce.tl_admittance_2x2``: antennaknobs' own TL branch,
    the closed form the reducer's composition oracles are written against.
    """

    a: tuple[int, int]  # (tag, segment) of end one
    b: tuple[int, int]  # (tag, segment) of end two
    z0: float  # |z0|, as the printout echoes it
    length: float  # card length; 0.0 means "the straight-line distance"
    crossed: bool
    y_a: complex  # shunt admittance at end one
    y_b: complex  # shunt admittance at end two

    @classmethod
    def from_card(cls, card: Card) -> LineBranch:
        z0 = card.f(4)
        if z0 == 0.0:
            raise PortalError("TL characteristic impedance must be non-zero")
        return cls(
            (card.i(0), card.i(1)),
            (card.i(2), card.i(3)),
            abs(z0),
            card.f(5),
            z0 < 0.0,
            complex(card.f(6), card.f(7)),
            complex(card.f(8), card.f(9)),
        )


@dataclass(frozen=True)
class PrintControl:
    """One ``PT`` card: which ``CURRENTS AND LOCATION`` rows get printed.

    SimNEC only ever emits ``PT`` around a plane-wave run — the
    ``planeWaveExcitation`` branch of ``nec2/NECSource.constructNECFile``
    writes ``EX 1 …``, ``PT -1``, ``XQ``, ``PT -2`` — which made it look
    entangled with an excitation this engine does not model. It is not. The
    card is a persistent toggle on ONE table, and every other section is
    untouched. Measured against the oracle, form by form:

    ``PT -1``
        the whole ``CURRENTS AND LOCATION`` section disappears — banner, note,
        blank, both column-header lines and every row. What is left in its
        place is Ward's ``-YY`` report, printed immediately after the last
        ``ANTENNA INPUT PARAMETERS`` row with no blank between them
        (fixture: ``dipole_pt_toggle``). That the ``-YY`` line survives is the
        load-bearing detail: it is the row SimNEC's ``addYYLine`` parses, so a
        suppression that swallowed it would break the Y path.
    ``PT -2``
        restores the table. It is a state change, not a per-run flag: the
        toggle holds across execute cards until another ``PT`` moves it.
    ``PT 0 <tag> <first> <last>``
        keeps the table and prints only those segments, addressed exactly as
        an ``EX`` card addresses one — tag-relative, ``tag = 0`` meaning
        absolute segment numbers. ``PT 0 1 0 0`` and ``PT 0 2 0 0`` both print
        everything, so an all-zero range is "no restriction" rather than "no
        rows" (fixture: ``dipole_pt_segment_range``).
    ``PT 1`` / ``PT 2`` / ``PT 3``
        stock NEC-2's receiving-pattern and normalised-current formats. This
        ae6ty build prints the ordinary full table for all three — diffed
        against the same deck without the card, byte for byte — so they are
        read here as "no restriction" too.
    """

    flag: int
    tag: int = 0
    first: int = 0
    last: int = 0

    @classmethod
    def from_card(cls, card: Card) -> PrintControl:
        return cls(card.i(0), card.i(1), card.i(2), card.i(3))

    @property
    def suppressed(self) -> bool:
        return self.flag == -1

    @property
    def restricted(self) -> bool:
        """True for the ``PT 0`` form with a real range on it."""
        return self.flag == 0 and bool(self.first or self.last)


@dataclass(frozen=True)
class Multiprocessing:
    """One ``MP`` card: the ae6ty engine's multicore hint. Echoed, then ignored.

    **What the card is.** ``MP <#Proc> <blockSize>`` — two INTEGER fields, and
    nothing else; a fractional one is refused by the oracle
    (``NON-NUMERICAL CHARACTER '.' IN INTEGER FIELD``) and is refused here.
    ``nec2/NECSource.constructNECFile`` writes it as ``"MP %d %d\\n"`` from
    ``NEC2PortalDialog.getMPInfo()[1:]`` — the last two fields of the
    ``necMP #segs #Proc blockSize`` preference, default ``256 16 32``.

    **When SimNEC emits it.** Automatically, and on structure SIZE alone:
    ``constructNECFile`` accumulates ``Wire.numSegments`` over
    ``Task.allWiresForNEC()`` and appends the card — immediately before the
    ``FR`` — when that total reaches ``getMPInfo()[0]`` and the selected engine
    is ``NECEngine.NEC2C``. No user ever asks for it, so any array past 256
    segments simply arrives carrying one. That is why refusing it was not
    tenable: it made the portal fail on exactly the decks worth running.

    **What it changes in the printout.** One line, at column 0, straight after
    the ``ANTENNA ENVIRONMENT`` block and followed by one extra blank —
    ``MP: multiProcessor <#Proc> <blockSize>`` — printed only when the card
    actually asks for parallelism (``MP 1 32`` and ``MP 0 0`` echo and say
    nothing; see :meth:`parallel` for the exact, slightly odd, test).
    It reprints in every block that rebuilds the matrix,
    so an ``FR`` sweep shows it once per frequency. Everything else in the
    printout is byte identical: the fixtures ``dipole_mp_multiprocessor`` and
    ``dipole_mp_single_process`` are ``dipole_free_space``'s geometry, and the
    only other differences are the card echo and the ordinals after it.

    **Why ignoring #Proc and blockSize is correct.** The card describes how the
    ORACLE fills and factors its matrix; it is not physics, and it cannot be —
    the printed numbers are identical with and without it. momwire's
    parallelism is decided elsewhere and earlier: the BLAS/OpenMP pools behind
    numpy, scipy and pynec_accel are configured once per process at import time
    via ``threadpoolctl`` (see ``web/server.py``'s thread-policy block and
    issue #377 — env pins set after the package ``__init__`` are already too
    late, because every pool snapshots its environment at load). A per-deck
    card arriving on stdin cannot reach back into that decision, and honouring
    it would mean re-limiting live pools mid-solve for a hint the sender did
    not mean as a request. It is advisory: we say we saw it, and solve the way
    the process was configured to solve.

    A hostile field is still harmless here. ``MP -3 -9`` makes the oracle
    itself hang forever (measured: SIGTERM at 25 s); this engine just echoes it
    and carries on, which is the difference between a stalled SimNEC and a
    printout.
    """

    processors: int
    block_size: int

    @classmethod
    def from_card(cls, card: Card) -> Multiprocessing:
        for k in (0, 1):
            if card.f(k) != float(card.i(k)):
                raise PortalError(
                    f"MP field {k + 1} must be an integer, not {card.f(k)!r}"
                )
        return cls(card.i(0), card.i(1))

    @property
    def parallel(self) -> bool:
        """The exact condition under which the oracle prints its advisory.

        Not ``>= 2``: ``MP -1 32`` and ``MP -3 -9`` print it too. The measured
        set is ``{0, 1} -> silent, everything else -> printed``, which is what
        a C ``if (nproc > 1)`` on an UNSIGNED field does — and the same
        unsigned reading is the likeliest cause of the infinite spin a negative
        field sends the oracle into.
        """
        return self.processors not in (0, 1)

    def line(self) -> str:
        return f"MP: multiProcessor {self.processors} {self.block_size}"


@dataclass
class ExecuteGroup:
    """One execute card's worth of state: the sources armed when it fired, and
    the frequency card in force. NEC clears the source list at every execute
    card, which is why ``two_source_sensor_lines`` drives the same segment
    twice with different voltages and ``jar_testdeck``'s second group shows one
    row."""

    sources: tuple[tuple[int, int, complex], ...]  # (tag, seg, voltage)
    freqs_mhz: tuple[float, ...]
    # True when an FR card was read since the previous XQ. The oracle prints
    # the FREQUENCY / STRUCTURE IMPEDANCE LOADING / ANTENNA ENVIRONMENT /
    # MATRIX TIMING preamble only when it rebuilds the matrix, so a second XQ
    # under the same FR emits ANTENNA INPUT PARAMETERS straight away
    # (fixture: two_source_sensor_lines, two XQs under one FR card). Our
    # cached factorisation makes that the honest report as well.
    refilled: bool = True
    # The ``RP``/``NE``/``NH`` card that fired this group, if any. Its table is
    # printed after the power budget; a plain ``XQ`` leaves it None.
    report: Card | None = None
    # The ``MP`` card in force when this group fired. Carried per group rather
    # than per deck because the advisory line is printed inside the refill
    # preamble: an ``MP`` read after an execute card must not retro-annotate
    # the block before it.
    mp: Multiprocessing | None = None
    # The ``PT`` card in force when this group fired — per group for the same
    # reason, and because ``PT`` is a TOGGLE: ``dipole_pt_toggle`` suppresses
    # the first run's table and restores the second's from one deck.
    pt: PrintControl | None = None
    # EK in force when this group fired. Advisory for momwire (our kernel is
    # our kernel), but the refilled preamble must announce it exactly as the
    # oracle does — and only there: an EK between two XQs re-arms execution
    # without a refill, and the oracle prints no announcement for it
    # (measured: XQ / EK / XQ shows two AIP sections, one preamble, zero
    # announcements).
    ek: bool = False
    # A kernel change between execute cards refills the matrix WITHOUT a new
    # FR: the oracle then prints the LOADING / ENVIRONMENT / MATRIX TIMING
    # part of the preamble but no FREQUENCY block and no kernel announcement
    # (fixture dipole_ek_rearm). Advisory refill for us — the cached factors
    # are already momwire's — but the printout must walk the same sections.
    refilled_partial: bool = False


@dataclass
class PortalDeck:
    """A deck body (everything up to, not including, its ``NX``)."""

    comments: tuple[str, ...] = ()
    geometry: tuple[Card, ...] = ()
    data_cards: tuple[Card, ...] = ()
    # One entry per EXECUTE card in ``data_cards`` order; None marks an execute
    # card that ran nothing (a bare ``XQ`` trailing an ``RP``/``NE``/``NH``).
    groups: tuple[ExecuteGroup | None, ...] = ()
    # Every ``NT`` and ``TL`` card, in CARD ORDER — which is the order nec2c
    # prints NETWORK DATA rows in, and the order that decides where it
    # re-emits a column header (see ``_network_lines``).
    networks: tuple[NetworkBranch | LineBranch, ...] = ()
    loads: tuple[Card, ...] = ()
    ground: Ground = field(default_factory=Ground)
    # The deck's ``GD`` card, if it carried one. Kept so the deck is a full
    # record of what arrived; it moves no number here (see :class:`SecondMedium`).
    second_medium: SecondMedium | None = None
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


def _validate_rp(card: Card) -> None:
    """Reject the ``RP`` shapes this engine does not compute.

    ``nec2/NECSource`` only ever writes ``RP 0 <nth> <nph> 1001 0 0 <dth>
    <dph> 1000``, but a user-pasted deck reaches the portal too, so the mode
    field is a real input. Modes 0, 2 and 3 run (issue #802); the rest are
    refused by name, because their tables are a different shape and guessing
    one is worse than saying no.

    ==========  ================================================  ========
    ``I1``      what it asks for                                  here
    ==========  ================================================  ========
    ``0``       space wave over the ground plane                  runs
    ``1``       surface wave — ``RADIATED FIELDS NEAR GROUND``,   refused
                a different banner and a different row shape
                (nine columns including ``E(RADIAL)``), reached
                through ``gfld`` rather than ``ffld``
    ``2``       linear cliff: second medium beyond ``x = CLT``    runs
    ``3``       circular cliff: second medium beyond ``r = CLT``  runs
    ``4``       radial wire ground screen                         refused
    ``5``       screen inside, then a LINEAR cliff beyond it      refused
    ``6``       screen inside, then a CIRCULAR cliff beyond it    refused
    ==========  ================================================  ========

    4-6 stay refused for the reason ``GN``'s ``NRADL`` field is: the screen is
    a surface impedance ``Z = t1·d·ln(d/t2)`` folded into the reflection
    coefficient, momwire has no screen model at all, and running the deck as
    bare ground would be a wrong answer rather than a refusal. 1 stays refused
    because nothing here computes a surface wave.
    """
    if card.i(0) not in _RP_MODES:
        raise PortalError(
            f"RP mode {card.i(0)} is not supported by this engine "
            f"(modes {', '.join(str(m) for m in sorted(_RP_MODES))} only)"
        )


def _validate_near_field(card: Card) -> None:
    """``NE``/``NH`` in rectangular coordinates only (``I1 = 0``)."""
    if card.i(0) != 0:
        raise PortalError(
            f"{card.mnemonic} coordinate system {card.i(0)} (spherical) is not "
            f"supported by this engine; rectangular (0) only"
        )


def parse_deck(body: str) -> PortalDeck:
    """A deck body's cards, grouped the way the engine executes them."""
    comments: list[str] = []
    geometry: list[Card] = []
    data_cards: list[Card] = []
    groups: list[ExecuteGroup | None] = []
    networks: list[NetworkBranch | LineBranch] = []
    loads: list[Card] = []
    sources: list[tuple[int, int, complex]] = []
    yy_points: list[tuple[int, int]] = []
    freqs: tuple[float, ...] = (0.0,)
    fresh_fr = False
    # True when something has changed since the last execution, so the next
    # execute card is a real run rather than a no-op echo.
    armed = True
    executed = 0
    ground = Ground()
    second_medium: SecondMedium | None = None
    ground_plane_flag = False
    quiet = False
    reduced_field: int | None = None
    multiprocessing: Multiprocessing | None = None
    print_control: PrintControl | None = None
    extended_kernel = False
    kernel_dirty = False
    sources_stale = False

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
            # ...and, when no radial screen claims F3-F6, the card carries a
            # whole second medium in them — the same four values a GD would
            # set, written to the same four slots by main.c. A GN that reaches
            # here always rewrites them, so a bare `GN 1` clears an earlier
            # cliff exactly as the oracle does; a screen count keeps them,
            # because the oracle takes the F3/F4 pair as the screen's geometry
            # and returns before the assignment.
            if card.i(1) == 0:
                second_medium = SecondMedium(card.f(6), card.f(7), card.f(8), card.f(9))
            data_cards.append(card)
            continue
        if card.mnemonic in _DEFERRED_CARDS:
            raise PortalError(
                f"{card.mnemonic} ({_DEFERRED_CARDS[card.mnemonic]}) is not "
                f"supported by this engine yet"
            )
        data_cards.append(card)
        if card.mnemonic in _ARMING_CARDS:
            armed = True
        if card.mnemonic == "LD":
            if card.i(0) == -1:
                loads.clear()
            else:
                loads.append(card)
        elif card.mnemonic == "NT":
            networks.append(NetworkBranch.from_card(card))
        elif card.mnemonic == "TL":
            networks.append(LineBranch.from_card(card))
        elif card.mnemonic == "GD":
            # Also not an arming card (measured: `... XQ / GD ... / XQ` prints
            # one block). The second medium reaches NEC's far field only
            # through RP's cliff modes, so this moves nothing until an RP 2 or
            # RP 3 asks for it — see SecondMedium.
            second_medium = SecondMedium.from_card(card)
        elif card.mnemonic == "MP":
            # Not an arming card: the oracle runs nothing for an XQ whose only
            # new card is an MP (measured — the second XQ of `... XQ / MP 4 8 /
            # XQ` prints no block at all).
            multiprocessing = Multiprocessing.from_card(card)
        elif card.mnemonic == "EK":
            if card.i(0) not in (0, -1):
                raise PortalError(
                    f"EK {card.i(0)} is neither 0 (extended kernel) nor -1 "
                    f"(standard kernel)"
                )
            if (
                card.i(0) == 0
                and not extended_kernel
                or card.i(0) == -1
                and extended_kernel
            ):
                kernel_dirty = executed > 0
            extended_kernel = card.i(0) == 0
        elif card.mnemonic == "PT":
            # Also not an arming card: it changes what a run PRINTS, not what
            # a run computes, so it cannot make an XQ into a fresh execution.
            print_control = PrintControl.from_card(card)
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
            # NEC RETAINS the excitation across an execute card: a re-run
            # with no new EX re-drives the previous set (dipole_ek_rearm's
            # second AIP repeats tag 1 seg 5), while the first EX after an
            # execution replaces it (every multi-group fixture). So the list
            # is cleared lazily here, not at the execute card.
            if sources_stale:
                sources.clear()
                sources_stale = False
            sources.append((card.i(1), card.i(2), complex(card.f(4), card.f(5))))
        elif card.mnemonic in _EXECUTE_CARDS:
            if not armed and executed:
                groups.append(None)
                continue
            if card.mnemonic == "RP":
                _validate_rp(card)
            elif card.mnemonic in ("NE", "NH"):
                _validate_near_field(card)
            groups.append(
                ExecuteGroup(
                    tuple(sources),
                    freqs if fresh_fr else freqs[-1:],
                    refilled=fresh_fr or not executed,
                    report=None if card.mnemonic == "XQ" else card,
                    mp=multiprocessing,
                    pt=print_control,
                    ek=extended_kernel,
                    refilled_partial=kernel_dirty and not (fresh_fr or not executed),
                )
            )
            kernel_dirty = False
            executed += 1
            sources_stale = True
            fresh_fr = False
            armed = False
        else:
            raise PortalError(f"unrecognised NEC card {card.mnemonic!r}")

    return PortalDeck(
        comments=tuple(comments),
        geometry=tuple(geometry),
        data_cards=tuple(data_cards),
        groups=tuple(groups),
        networks=tuple(networks),
        loads=tuple(loads),
        ground=ground,
        second_medium=second_medium,
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


def fmt_network_row(tag_a, seg_a, tag_b, seg_b, values, tail: str = "") -> str:
    """A NETWORK DATA row: the two connection points, six numbers, a tail word.

    ``NT`` and ``TL`` rows share this layout EXACTLY — six alternating
    ``%12.4E``/``%11.4E`` fields and a nine-column right-aligned tail — and
    only the meaning of the six changes: an ``NT`` row is
    ``Re/Im(Y11), Re/Im(Y12), Re/Im(Y22)`` under an empty tail, a ``TL`` row is
    ``|z0|, length, Re/Im(y_end1), Re/Im(y_end2)`` under ``STRAIGHT`` or
    ``CROSSED``. The oracle pads the ``NT`` form out to 106 columns with nine
    trailing spaces, which is the same nine columns ``STRAIGHT`` occupies —
    reproduced, because ``layout_signature`` compares token END columns and a
    reader diffing bytes should see none.
    """
    v1, v2, v3, v4, v5, v6 = values
    return (
        f" {tag_a:4d} {seg_a:5d} {tag_b:4d} {seg_b:5d}"
        f" {v1:12.4E} {v2:11.4E}"
        f" {v3:12.4E} {v4:11.4E}"
        f" {v5:12.4E} {v6:11.4E}"
        f"{tail:>9s}"
    )


def fmt_pattern_row(
    theta, phi, vertc_db, horiz_db, total_db, axial, tilt, sense, e_theta, e_phi
) -> str:
    """One RADIATION PATTERNS row.

    ``Execute.processResponse``'s ``PROCESSINGPATTERN`` state reads ``theta =
    parts[0]``, ``phi = parts[1]`` and the four E-field fields at ``ptr`` —
    ``ptr = 8`` for a 12-token row, ``7`` for an 11-token one. **The SENSE
    column is the whole difference**: it is a fixed-width field holding
    ``LINEAR`` / ``LEFT`` / ``RIGHT`` when the direction carries a field and
    six blanks when it does not, so a blank one vanishes under
    ``split("\\s+")`` and the row loses a token. Both forms address the same
    columns; an engine that always printed a word, or never did, would still
    parse — but it would stop matching the oracle line for line.

    VERTC is ``%10.2g``, not ``%.2f``: this ae6ty build prints the vertical
    gain to two SIGNIFICANT figures, which is why the floor shows as
    ``-1e+03`` while TOTAL on the same row shows ``-999.99``.
    """
    return (
        f"{theta:8.2f}{phi:10.2f}{vertc_db:10.2g}{horiz_db:9.2f}{total_db:9.2f}"
        f"{axial:12.4f}{tilt:10.2f} {sense:<6s}"
        f"{abs(e_theta):12.4E}{_phase_deg(e_theta):10.2f}"
        f"{abs(e_phi):12.4E}{_phase_deg(e_phi):10.2f}"
    )


def fmt_near_field_row(point, fx, fy, fz) -> str:
    """One NEAR ELECTRIC/MAGNETIC FIELDS row: location then magnitude/phase per
    Cartesian component. Exactly nine tokens — anything else ends the table for
    ``Execute``'s ``PROCESSINGNEARFIELD`` state."""
    return (
        f"{point[0]:10.4f}{point[1]:10.4f}{point[2]:10.4f}"
        f"{abs(fx):13.4E}{_phase_deg(fx):8.2f}"
        f"{abs(fy):13.4E}{_phase_deg(fy):8.2f}"
        f"{abs(fz):13.4E}{_phase_deg(fz):8.2f}"
    )


def _phase_deg(value: complex) -> float:
    return math.degrees(math.atan2(value.imag, value.real))


def _loading_cell(value: float | None) -> str:
    """A loading-table numeric cell — 12 blank columns when the leg is absent
    or zero, which is how the oracle prints an omitted R/L/C."""
    if value is None or value == 0.0:
        return " " * 12
    return f"{value:12.4E}"


# --------------------------------------------------------------------------
# fields — the same segment-dipole decomposition, near zone and far zone
# --------------------------------------------------------------------------


def _image_moments(mid, moment, ground_z):
    """The geometric PEC image of a set of current moments across ``z = z0``.

    Horizontal components flip, the vertical one does not — the standard
    image, and the same convention ``engines/momwire.py::_evaluate_M_perp``
    uses, so the finite-ground Fresnel step below can be written as a
    correction to it.
    """
    mid_img = mid.copy()
    mid_img[:, 2] = 2.0 * ground_z - mid[:, 2]
    return mid_img, moment * np.array([-1.0, -1.0, 1.0])


def _image_coeffs(eps_r, sigma, freq_hz, rx, ry, rz):
    """``(rho_h, rho_v)`` — the IMAGE-CURRENT multipliers for one medium.

    These are ``ffld``'s ``rrh`` and ``-rrv``, not the textbook Fresnel pair:
    they multiply the geometric image (horizontal components already flipped
    by :func:`_image_moments`), which is why perfect ground is ``(-1, +1)``
    here and ``(-1, -1)`` in the C. Algebraically identical — nec2c writes the
    ratio ``zrati = 1/sqrt(eps_c)`` where this writes ``q = sqrt(eps_c -
    sin²θ)``, and ``zrati·zrsin`` reduces to ``q/eps_c`` — but the sign
    convention is ours, and the mapping is the thing to check first if a
    reflected field ever comes out inverted.

    Passing ``eps_r = sigma = 0`` (a ``GD`` with an empty second medium) makes
    ``q`` collapse to ``j·sinθ`` and the vertical ratio a 0/0 at the zenith.
    The oracle does the same thing from the other side — ``zrati2`` goes to
    infinity and its whole pattern table prints ``nan`` — so nothing here
    tries to rescue a deck that asks for a cliff into vacuum.
    """
    omega = 2.0 * math.pi * freq_hz
    eps_c = eps_r - 1j * sigma / (omega * EPS0)
    q = np.sqrt(eps_c - rx * rx - ry * ry)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (rz - q) / (rz + q), (eps_c * rz - q) / (eps_c * rz + q)


def _cliff_medium_2(mid, theta, phi, ground_z, mode, edge_distance):
    """``(n_theta, n_phi, n_element)`` mask: is this element's reflection point
    on the FAR side of the cliff?

    NEC picks the medium per SEGMENT and per DIRECTION, at that segment's own
    specular point on the ground. For an element at height ``z`` radiating
    towards ``theta``, the reflection point is ``dr = z·tan(theta)`` out along
    the azimuth, so its ground coordinates are ``(x + dr·cosφ, y + dr·sinφ)``
    — and the edge it is compared against is

    * ``RP 2``, LINEAR cliff: the line ``x = CLT``, so only the x coordinate
      counts. An azimuth parallel to the edge never crosses it and an azimuth
      pointing away from it never does either (``d`` goes negative).
    * ``RP 3``, CIRCULAR cliff: the circle ``r = CLT``, so the radius counts
      and every azimuth crosses alike.

    The comparison is ``ffld``'s exactly, including its tie-break: ``(cl - d) >
    0`` keeps medium 1, so a point landing precisely ON the edge takes medium
    2.

    **Validity.** This is NEC-2's own cliff model, and it is a geometric-optics
    one: a single specular bounce off whichever flat half-plane the reflection
    point happens to sit on, with no diffraction at the edge and no shadowing
    by the step. It is trustworthy where the edge is many wavelengths from
    both the antenna and the reflection point, and it is visibly discontinuous
    across the angle where the reflection point crosses — which is a property
    of the model, not of this implementation, and shows up identically in the
    oracle's own table.
    """
    height = mid[:, 2] - ground_z
    dr = np.tan(theta)[:, None] * height[None, :]  # (n_theta, n_element)
    along = dr[:, None, :] * np.cos(phi)[None, :, None] + mid[None, None, :, 0]
    if mode == 3:
        across = mid[None, None, :, 1] + dr[:, None, :] * np.sin(phi)[None, :, None]
        along = np.hypot(along, across)
    return along >= edge_distance


def _cliff_image_moments(
    mid, moment, k, theta, phi, basis, ground, ground_z, freq_hz, mode, cliff
):
    """The reflected far-field moment under ``RP 2`` / ``RP 3``.

    The flat-ground path applies one reflection coefficient to the whole image
    sum. A cliff cannot: two elements of the same antenna can reflect off
    different media in the same direction, so the sum has to be split first
    and weighted after. That is ``ffld``'s inner loop, vectorised — split the
    image carrier by :func:`_cliff_medium_2`, give each half its own
    ``(rho_h, rho_v)``, add.

    The far side also carries an extra phase. Its surface is ``CHT`` below
    medium 1's (signed, negative = lower), so its image sits ``2·CHT`` further
    along the vertical and the ray to it is ``2·CHT·cos(theta)`` longer:
    nec2c spells that ``darg = -2π·2·ch·roz`` on the image phase, which is the
    same ``exp(-2jk·CHT·cosθ)`` applied here.
    """
    rhat, h_hat, v_hat = basis
    rx, ry, rz = rhat[..., 0], rhat[..., 1], rhat[..., 2]
    mid_img, moment_img = _image_moments(mid, moment, ground_z)
    carrier = np.exp(1j * k * np.einsum("ijc,nc->ijn", rhat, mid_img))

    beyond = _cliff_medium_2(mid, theta, phi, ground_z, mode, cliff.edge_distance)
    step = np.exp(-2j * k * cliff.height * np.cos(theta))
    far = np.einsum(
        "ijn,nc->ijc", carrier * np.where(beyond, step[:, None, None], 0.0), moment_img
    )
    carrier *= ~beyond
    near = np.einsum("ijn,nc->ijc", carrier, moment_img)

    # Medium 1 is whatever the GN card said. Perfect ground is the one case
    # ffld does not run through the Fresnel formula at all, and the second
    # medium never gets that shortcut: a GD states eps/sigma and nothing else,
    # so it is always a reflection coefficient even under GN 1.
    if ground.kind == "pec":
        near_coeffs = (-1.0, 1.0)
    else:
        near_coeffs = _image_coeffs(ground.eps_r, ground.sigma, freq_hz, rx, ry, rz)
    far_coeffs = _image_coeffs(cliff.eps_r2, cliff.sigma2, freq_hz, rx, ry, rz)

    total = np.zeros_like(near)
    for half, (rho_h, rho_v) in ((near, near_coeffs), (far, far_coeffs)):
        half_h = np.sum(half * h_hat, axis=-1)
        half_v = np.sum(half * v_hat, axis=-1)
        total += (rho_v * half_v)[..., None] * v_hat
        total -= (rho_h * half_h)[..., None] * h_hat
    return total


def _far_moments(mid, moment, k, theta, phi, ground, ground_z, freq_hz, cliff=None):
    """Complex ``(M_theta, M_phi)`` on the ``theta`` x ``phi`` grids (radians).

    ``M = Σ I_n dl_n exp(+j k r̂·r_n)`` is the far-field current moment; the
    radiated field is ``E = -j η k /(4π) · e^(-jkr)/r · M_perp``. The engine's
    ``_evaluate_M_perp`` computes ``|M_perp|²`` for the gain plot and throws
    the components away; a NEC printout needs them, because it reports
    E(THETA) and E(PHI) magnitude AND phase and splits the gain into VERTC
    (theta) and HORIZ (phi). Same physics, same ground handling, components
    kept.

    ``cliff`` is ``(mode, SecondMedium)`` when the ``RP`` card asked for one of
    the cliff modes, and ``None`` otherwise. It only ever reaches the image
    term — a cliff with no ground image is not a cliff, which is why NEC still
    prints the FAR FIELD GROUND PARAMETERS block for an ``RP 2`` in free space
    and still moves no number.
    """
    sin_t, cos_t = np.sin(theta), np.cos(theta)
    cos_p, sin_p = np.cos(phi), np.sin(phi)
    rx = sin_t[:, None] * cos_p[None, :]
    ry = sin_t[:, None] * sin_p[None, :]
    rz = np.broadcast_to(cos_t[:, None], rx.shape)
    rhat = np.stack([rx, ry, rz], axis=-1)

    cos_p_g = np.broadcast_to(cos_p[None, :], rx.shape)
    sin_p_g = np.broadcast_to(sin_p[None, :], rx.shape)
    cos_t_g = np.broadcast_to(cos_t[:, None], rx.shape)
    sin_t_g = np.broadcast_to(sin_t[:, None], rx.shape)
    # NEC's spherical basis: theta_hat points away from +z, phi_hat is
    # azimuthal. Both are already perpendicular to rhat, so projecting M onto
    # them IS projecting M_perp onto them.
    theta_hat = np.stack([cos_t_g * cos_p_g, cos_t_g * sin_p_g, -sin_t_g], axis=-1)
    phi_hat = np.stack([-sin_p_g, cos_p_g, np.zeros_like(rx)], axis=-1)

    def moments_of(centres, weights):
        phase = k * np.einsum("ijc,nc->ijn", rhat, centres)
        return np.einsum("ijn,nc->ijc", np.exp(1j * phase), weights)

    # The reflected wave's own polarisation basis: h along phi_hat, v the
    # in-plane partner. PEC is rho_h = -1, rho_v = +1, so the Fresnel step
    # below is written as a correction to the PEC image exactly as the engine
    # does.
    h_hat = phi_hat
    v_hat = np.stack([-cos_p_g * cos_t_g, -sin_p_g * cos_t_g, sin_t_g], axis=-1)

    m_direct = moments_of(mid, moment)
    if ground is None or ground.kind == "free":
        total = m_direct
    elif cliff is not None:
        mode, second = cliff
        total = m_direct + _cliff_image_moments(
            mid,
            moment,
            k,
            theta,
            phi,
            (rhat, h_hat, v_hat),
            ground,
            ground_z,
            freq_hz,
            mode,
            second,
        )
    else:
        mid_img, moment_img = _image_moments(mid, moment, ground_z)
        m_img = moments_of(mid_img, moment_img)
        if ground.kind == "pec":
            total = m_direct + m_img
        else:
            m_img_h = np.sum(m_img * h_hat, axis=-1)
            m_img_v = np.sum(m_img * v_hat, axis=-1)
            rho_h, rho_v = _image_coeffs(
                ground.eps_r, ground.sigma, freq_hz, rx, ry, rz
            )
            m_refl = (rho_v * m_img_v)[..., None] * v_hat - (rho_h * m_img_h)[
                ..., None
            ] * h_hat
            total = m_direct + m_refl
    return np.sum(total * theta_hat, axis=-1), np.sum(total * phi_hat, axis=-1)


def _element_fields(points, elements, k, radius, magnetic):
    """E (or H) at ``points`` from the solved current, in MIXED-POTENTIAL form.

    ``elements`` is ``(mid, moment, nodes, delta)``: element midpoints, their
    current moments ``p = I·dl``, the mesh NODES between them, and the current
    STEP ``ΔI = I_in - I_out`` at each node — the discrete continuity charge
    ``q = ΔI/(jω)``. With ``G = e^{-jkR}/R``,

        E = -j·ηk/(4π)·Σ p_n G_n  -  j·η/(4πk)·Σ ΔI_m (1+jkR_m)/R_m² · G_m·R̂_m
        H = 1/(4π)·Σ (p_n × R̂_n)·(jk/R_n + 1/R_n²)·G_n

    the first E term being ``-jωA`` and the second ``-∇Φ``. In the radiation
    zone the pair collapses to ``-j·ηk/(4πr)·e^(-jkr)·M_perp``, the same
    prefactor :func:`_far_moments` is normalised against, so the near-field and
    pattern tables are one physics.

    **Why not a chain of Hertzian point dipoles.** That form is algebraically
    simpler and agrees with this one everywhere off the structure — but each
    element carries its own ±q pair separated by dl, and a sample point a
    fraction of an element away sees that pair's 1/R³ term with nothing to
    cancel it: an observation point ON the wire came out at 1.7E+05 V/m
    against nec2c's 1.2E-02. Splitting current and charge puts the charge
    where it physically is (the nodes) and makes ΔI small wherever the current
    is smooth, so adjacent nodes cancel the way the continuous integral does.

    ``R`` is still the thin-wire regularised ``sqrt(|R|² + a²)``: the sample is
    taken on the conductor SURFACE rather than its axis, momwire's own
    convention (``rho_eval`` in the sinusoidal kernel). Grammar doc §11.
    """
    mid, moment, nodes, delta = elements

    def geometry(sources):
        rvec = points[:, None, :] - sources[None, :, :]
        r = np.sqrt(np.sum(rvec * rvec, axis=-1) + radius * radius)
        return rvec / r[..., None], r, np.exp(-1j * k * r) / (4.0 * math.pi * r)

    rhat, r, green = geometry(mid)
    if magnetic:
        cross = np.cross(np.broadcast_to(moment, (len(points),) + moment.shape), rhat)
        weight = (1j * k + 1.0 / r) * green
        return np.sum(weight[..., None] * cross, axis=1)

    e_vector = -1j * ETA0 * k * np.sum(green[..., None] * moment[None, :, :], axis=1)
    q_rhat, q_r, q_green = geometry(nodes)
    scalar = -1j * ETA0 / k * (delta[None, :] * (1.0 + 1j * k * q_r) / q_r * q_green)
    return e_vector + np.sum(scalar[..., None] * q_rhat, axis=1)


def _polarisation(
    e_theta: complex, e_phi: complex, floor_scale: float = 1.0
) -> tuple[float, float, str]:
    """``(axial_ratio, tilt_deg, sense)`` for one direction's polarisation
    ellipse — the AXIAL RATIO / TILT / SENSE columns.

    ``floor_scale`` converts the PRINTED field back to the amplitude ``ffld``
    returned, which is the basis nec2c's blank-column test is written in (see
    ``_FIELD_FLOOR2``). It is 1 for a table read out at the wavelength's own
    scale and ``RFLD/lambda`` for one read out at a range; everything else
    here is scale-free, so it reaches the floor test and nothing more.

    With ``a = |E_theta|``, ``b = |E_phi|`` and ``δ = arg(E_phi) - arg(E_theta)``
    wrapped to ±180°, the ellipse semi-axes are
    ``0.5·[a²+b² ± sqrt(a⁴+b⁴+2a²b²cos2δ)]`` and the tilt is
    ``½·atan2(2ab·cosδ, a²-b²)`` — the same ``atan2`` pair nec2c forms.
    The axial ratio is minor/major, signed by ``sinδ``, so linear
    polarisation prints 0.0000 and circular ±1.0000.

    Sense is calibrated against the oracle, not derived: a crossed pair fed
    ``EX ... 1. 0.`` / ``EX ... 0. 1.`` gives ``δ = +90°`` at the zenith and
    nec2c prints ``AXIAL RATIO 1.0000 ... LEFT``
    (``dipole_rp_crossed_quadrature``), so positive ``sinδ`` is LEFT here.
    """
    a, b = abs(e_theta), abs(e_phi)
    raw2 = floor_scale * floor_scale
    if a * a * raw2 <= _FIELD_FLOOR2 and b * b * raw2 <= _FIELD_FLOOR2:
        return 0.0, 0.0, ""
    delta = _phase_deg(e_phi) - _phase_deg(e_theta)
    delta = (delta + 180.0) % 360.0 - 180.0
    a2, b2 = a * a, b * b
    root = math.sqrt(
        max(
            a2 * a2 + b2 * b2 + 2.0 * a2 * b2 * math.cos(math.radians(2.0 * delta)), 0.0
        )
    )
    major2 = 0.5 * (a2 + b2 + root)
    minor2 = max(0.5 * (a2 + b2 - root), 0.0)
    tilt = 0.5 * math.degrees(
        math.atan2(2.0 * a * b * math.cos(math.radians(delta)), a2 - b2)
    )
    if major2 <= 0.0:
        return 0.0, tilt, "LINEAR"
    ratio = math.sqrt(minor2 / major2)
    sin_d = math.sin(math.radians(delta))
    if ratio < 1e-8:
        return 0.0, tilt, "LINEAR"
    return (
        ratio if sin_d >= 0 else -ratio,
        tilt,
        "LEFT" if sin_d >= 0 else "RIGHT",
    )


def _gain_db(power_gain: float) -> float:
    """A gain column in dB, with nec2c's degenerate floor.

    This is ``db10()``: ``x < 1e-20 -> -999.99``, applied to the LINEAR POWER
    GAIN about to be logged rather than to the field. ``dipole_rp_pattern``
    prints the floor for a direction whose E(THETA) is 5.4196E-15 because that
    direction's gain is around -220 dB, not because the field is small — a
    distinction the fixtures could not show while every pattern was taken at
    one range, and one that ``dipole_rp_gain_only`` now pins: the gain columns
    of an ``RFLD = 0`` table are identical to the same deck's at 1000 m, while
    every E column moves by three decades (issue #802).
    """
    if power_gain < _GAIN_FLOOR2:
        return _GAIN_FLOOR_DB
    return 10.0 * math.log10(power_gain)


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

    The three branches are keyed on the port algebra each family owns, not on
    the class: ``_assemble_Z_ported`` exists only on the Galerkin subclass and
    ``_solve_with_kcl_ports`` only on the B-spline family, so a basis added to
    ``_BASES`` lands on the branch whose algebra it actually has. Inside the
    B-spline branch the same rule picks the SOLVE: the accelerated subclasses
    own ``_solve_hmatrix``, so that is what gets spied for them.
    """
    if hasattr(solver, "_assemble_Z_ported"):
        # Sinusoidal-Galerkin family: no KCL-port solve to spy on, but
        # compute_y_matrix's own algebra IS the (Y, X) pair — alphas is the
        # per-port coefficient matrix it computes and throws away. Kept
        # verbatim from momwire's compute_y_matrix so the two can never
        # disagree; the private reach is the same momwire#232 debt as the
        # shim below.
        import scipy.linalg

        solver._refuse_junction_port_solve()
        geom = solver._build_geometry()
        G, seg_view = solver._assemble_Z_ported(geom, solver.k)
        U = solver._drive_columns(geom, seg_view, solver.k)
        alphas = scipy.linalg.solve(G, U)
        y = np.stack(
            [
                solver._port_currents(alphas[:, j], geom, seg_view, U)
                for j in range(solver.n_ports)
            ],
            axis=1,
        )
        return y, alphas

    if not hasattr(solver, "_solve_with_kcl_ports"):
        # Point-matched sinusoidal: neither a KCL-port solve to spy on nor the
        # Galerkin port algebra — its ports ARE the Eq-187 delta gaps, so the
        # RHS is -1/h at each feed segment and column j of the solution is
        # already the 1 V drive at port j (``compute_impedance`` builds the
        # same column, scaled by V). Kept verbatim from momwire's
        # ``compute_y_matrix``, same momwire#232 debt as the branches around
        # it. No junction-port refusal belongs here: this solver rejects
        # ``junction_ports=`` at CONSTRUCTION (momwire#177 — the basis
        # enforces KCL identically, so a node-current port is outside its
        # span), and a deck's ports are all EX segment gaps anyway.
        import scipy.linalg

        geom = solver._build_geometry()
        G, seg_view = solver._assemble_Z(geom, solver.k)
        feed_segs = geom["feed_segs"]
        B = np.zeros((geom["n_segs"], len(feed_segs)), dtype=np.complex128)
        for j, fi in enumerate(feed_segs):
            B[fi, j] = -1.0 / geom["seg_h"][fi]
        alphas = scipy.linalg.solve(G, B)
        y = np.array(
            [
                [
                    solver._feed_segment_current(alphas[:, j], seg_view, fi)
                    for j in range(len(feed_segs))
                ]
                for fi in feed_segs
            ],
            dtype=np.complex128,
        )
        return y, alphas

    # B-spline family, and TWO solve routes to spy on (issue #830). The dense
    # path back-substitutes in `_solve_with_kcl_ports`. The accelerated
    # subclasses — HMatrixSolver and ArrayBlockSolver, both `_BASES` entries —
    # never reach it: their `compute_y_matrix` builds the same source columns
    # B and runs the constrained block-GMRES in `_solve_hmatrix`, returning
    # ``Bᵀ·X`` and dropping X on the floor exactly as the dense path does.
    # ``_solve_hmatrix``'s X is the same object under the same convention —
    # (n_basis, n_ports), Lagrange rows already stripped — so the two captures
    # are interchangeable downstream.
    #
    # Which route runs is `_hmatrix_unsupported()`, i.e. singular enrichment
    # ONLY (momwire hmatrix.py / array_block.py): mesh size does not select it,
    # and every ground model the portal can emit — PEC image, reflection
    # coefficient, Sommerfeld — is carried on the accelerated path. The portal
    # never asks for enrichment, so in practice the accelerated bases always
    # take `_solve_hmatrix`; the dense capture stays wired anyway so a momwire
    # that grows a new fallback degrades to a slower answer, not an error.
    captured: dict[str, np.ndarray] = {}
    dense = solver._solve_with_kcl_ports

    def spy_dense(z, v, kcl_a, overwrite=False):
        x = dense(z, v, kcl_a, overwrite=overwrite)
        captured["dense"] = x
        return x

    solver._solve_with_kcl_ports = spy_dense
    accel = getattr(solver, "_solve_hmatrix", None)
    if accel is not None:

        def spy_accel(h, kcl_a, b):
            x = accel(h, kcl_a, b)
            captured["accel"] = x
            return x

        solver._solve_hmatrix = spy_accel
    try:
        y = np.asarray(solver.compute_y_matrix(), dtype=np.complex128)
    finally:
        del solver._solve_with_kcl_ports
        if accel is not None:
            del solver._solve_hmatrix
    # Accelerated first: a solve that reached `_solve_hmatrix` never touched
    # the dense route, so the two keys are mutually exclusive in practice and
    # the preference only decides a hypothetical future hybrid.
    x = captured.get("accel", captured.get("dense"))
    if x is None:  # pragma: no cover - momwire internals moved
        raise PortalError("momwire did not expose the per-port solution")
    return y, x


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
            if group is None:
                continue
            for tag, seg, _v in group.sources:
                if (tag, seg) not in ports:
                    ports.append((tag, seg))
        # An NT or TL endpoint is a port too: NEC cuts the segment to hang the
        # network off it, so it needs a gap in the momwire model whether or not
        # anything drives it.
        for branch in deck.networks:
            for point in (branch.a, branch.b):
                if point not in ports:
                    ports.append(point)
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

        # NT and TL branches, stamped onto the port index set, in card order.
        # An NT matrix is frequency-independent (the card gives constant
        # admittances) so it is accumulated once here; a TL's is not — its
        # electrical length is βl — so the line rows are kept and stamped per
        # frequency by ``y_network_at``.
        lookup = {point: self.feed_index[i] for i, point in enumerate(self.ports)}
        self.y_constant = np.zeros((self.n_ports, self.n_ports), dtype=np.complex128)
        self.network_ports: set[int] = set()
        # (port a, port b, branch, resolved TL length or None for an NT).
        self.network_rows: list[
            tuple[int, int, NetworkBranch | LineBranch, float | None]
        ] = []
        self.line_rows: list[tuple[int, int, LineBranch, float]] = []
        for branch in deck.networks:
            a, b = lookup[branch.a], lookup[branch.b]
            length: float | None = None
            if isinstance(branch, LineBranch):
                length = self._line_length(branch, a, b)
                self.line_rows.append((a, b, branch, length))
            else:
                self.y_constant[a, a] += branch.y11
                self.y_constant[a, b] += branch.y12
                self.y_constant[b, a] += branch.y12
                self.y_constant[b, b] += branch.y22
            self.network_ports.update((a, b))
            self.network_rows.append((a, b, branch, length))

        self._smallest_radius = min(w.radius for w in self.wires)
        self._cache: dict[float, dict] = {}

    def _line_length(self, branch: LineBranch, a: int, b: int) -> float:
        """A ``TL`` card's resolved length: its own, or — when the card says
        zero — the straight-line distance between the two connection points,
        which NEC takes to be the segment CENTRES. The printout echoes THIS
        number, so a zero-length card never prints a zero."""
        if branch.length:
            return branch.length
        centre_a = self.segments[self.segment_of_port(a) - 1].centre
        centre_b = self.segments[self.segment_of_port(b) - 1].centre
        return float(np.linalg.norm(centre_a - centre_b))

    def y_network_at(self, wavelength: float) -> np.ndarray:
        """The whole deck's network admittance at one wavelength.

        The constant ``NT`` part plus every ``TL``'s equivalent network:
        ``tl_admittance_2x2`` — antennaknobs' own TL branch — with the card's
        end admittances added onto the diagonal, which is where a lossy line's
        ``NETWORK LOSS`` comes from.
        """
        y = self.y_constant.copy()
        for a, b, branch, length in self.line_rows:
            try:
                block = tl_admittance_2x2(
                    branch.z0, length, wavelength, transposed=branch.crossed
                )
            except SingularNetworkError as exc:
                # An exactly-lossless k·λ/2 line HAS no admittance matrix, and
                # nec2c's netwk() divides by the same sinh. Refuse it by name
                # rather than emit a table of infinities.
                raise PortalError(f"TL {branch.a} -> {branch.b}: {exc}") from None
            y[a, a] += block[0, 0] + branch.y_a
            y[a, b] += block[0, 1]
            y[b, a] += block[1, 0]
            y[b, b] += block[1, 1] + branch.y_b
        return y

    def network_report_order(self, driven_ports: set[int]) -> list[int]:
        """Row order for STRUCTURE EXCITATION DATA AT NETWORK CONNECTION POINTS.

        NEC's ``netwk()`` sorts the connection points into two lists as it
        walks the cards — the ones that are NOT also excitation segments, then
        the ones that are — and prints the first list followed by the second.
        Within each list the order is discovery: card by card, end one before
        end two. So ``dipole_nt_network`` (``NT 1 5 2 5``, driven on 1/5)
        prints ``(2, 14)`` then ``(1, 5)``, and the mixed
        ``dipole_tl_shunt_crossed`` prints the TL's far end, then both NT ends,
        then the driven TL end last.
        """
        undriven: list[int] = []
        driven: list[int] = []
        for a, b, _branch, _length in self.network_rows:
            for port in (a, b):
                if port in undriven or port in driven:
                    continue
                (driven if port in driven_ports else undriven).append(port)
        return undriven + driven

    def segment_of_port(self, port: int) -> int:
        """The global NEC segment number carrying momwire port ``port``."""
        for number, idx in self.port_by_segment.items():
            if idx == port:
                return number
        raise PortalError(f"port {port} has no segment")

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
        cls, kwargs, _ = _active_basis
        return MomwireEngine(
            _DeckBuilder(),
            solver=cls,
            solver_kwargs=dict(kwargs) or None,
            ground=ground,
            ground_z=0.0,
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
        y_network = self.y_network_at(entry["wavelength"])
        system = np.eye(self.n_ports, dtype=np.complex128) + (z_load[:, None] * y)
        rhs = v_source.copy()
        # A network port that nothing drives is not a shorted gap: its voltage
        # floats to whatever makes the node's currents balance, so its row
        # becomes KCL — antenna current plus network current is zero. A network
        # port that IS driven keeps the ideal-source row (V = V_ex) and the
        # source supplies the difference. Grammar doc §11.
        driven_ports = {port for port, _seg, _v in driven}
        for port in sorted(self.network_ports - driven_ports):
            system[port, :] = y[port, :] + y_network[port, :]
            rhs[port] = 0.0
        v_gap = np.linalg.solve(system, rhs)
        i_port = y @ v_gap
        i_network = y_network @ v_gap
        # What the source delivers: the segment current plus whatever the
        # network draws at the same node. With no NT card the second term is
        # zero and this is the unit-2 reading unchanged.
        i_source = i_port + i_network

        w_matrix = self.engine._feed_W
        v_sub = v_gap if w_matrix is None else w_matrix @ v_gap
        coeffs = entry["X"] @ v_sub
        seg_currents = self._segment_currents(entry["solver"], coeffs)

        p_in = 0.5 * float(
            sum((volts * np.conj(i_source[p])).real for p, _s, volts in driven)
        )
        p_load = 0.5 * float(np.sum(np.real(z_load) * np.abs(i_port) ** 2))
        p_wire = 0.0
        if self.engine._loading_kwargs:
            p_wire = float(entry["solver"].wire_loss_power(coeffs)[0])
        p_structure = p_load + p_wire
        p_network = 0.5 * float(np.sum(np.real(v_gap * np.conj(i_network))))
        p_rad = p_in - p_structure - p_network
        return {
            "driven": driven,
            "v_gap": v_gap,
            "i_port": i_port,
            "i_network": i_network,
            "i_source": i_source,
            "segment_currents": seg_currents,
            "coeffs": coeffs,
            "solver": entry["solver"],
            "p_in": p_in,
            "p_structure": p_structure,
            "p_network": p_network,
            "p_radiated": p_rad,
            "efficiency": (100.0 * p_rad / p_in) if p_in > 0 else 0.0,
            "fill_ms": entry["fill_ms"],
            "wavelength": entry["wavelength"],
        }

    # -- field sources -----------------------------------------------------

    def current_elements(self, result: dict, subdiv: int = 1):
        """``(mid, moment, nodes, delta)`` for the whole structure.

        ``mid``/``moment`` are the element midpoints and their complex current
        moments ``I·dl`` — the far-field sum's terms. ``nodes``/``delta`` are
        the mesh knots and the current STEP across each, which is the discrete
        continuity charge the near-field scalar potential needs. Wire ends get
        the full element current as their step (nothing carries current past
        them), and knots two wires share coincide, so their steps simply add.

        ``subdiv > 1`` resamples the solved B-spline current at intermediate
        arc positions (``currents_at_knots(coeffs, s_array=...)``) instead of
        only at the mesh knots. The far field does not need it — every element
        is electrically small and only the radiation-zone limit matters — but a
        near field a metre from a half-metre segment does.
        """
        solver, coeffs = result["solver"], result["coeffs"]
        engine = self.engine
        fine: list[np.ndarray] = []
        arcs: list[np.ndarray] = []
        for w_idx, polyline in enumerate(engine._polylines):
            parts = []
            for i, n_e in enumerate(engine._edge_segments[w_idx]):
                seg = np.linspace(polyline[i], polyline[i + 1], n_e * subdiv + 1)
                parts.append(seg if i == 0 else seg[1:])
            knots = np.vstack(parts)
            fine.append(knots)
            step = np.linalg.norm(knots[1:] - knots[:-1], axis=1)
            arcs.append(np.concatenate([[0.0], np.cumsum(step)]))
        currents = solver.currents_at_knots(coeffs, None if subdiv == 1 else arcs)
        mids, moments, nodes, deltas = [], [], [], []
        for knots, cur in zip(fine, currents, strict=True):
            cur = np.asarray(cur)
            element = 0.5 * (cur[1:] + cur[:-1])
            mids.append(0.5 * (knots[1:] + knots[:-1]))
            moments.append(element[:, None] * (knots[1:] - knots[:-1]))
            nodes.append(knots)
            zero = np.zeros(1, dtype=np.complex128)
            deltas.append(
                np.concatenate([zero, element]) - np.concatenate([element, zero])
            )
        return (
            np.concatenate(mids, axis=0),
            np.concatenate(moments, axis=0),
            np.concatenate(nodes, axis=0),
            np.concatenate(deltas, axis=0),
        )

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
        wanted_dir = np.array([s.direction for s in self.segments])
        d2 = ((wanted[:, None, :] - mids[None, :, :]) ** 2).sum(axis=2)
        # Position alone is not enough to name an element: two wires that CROSS
        # share a segment midpoint exactly, and a plain nearest-midpoint search
        # then reads both NEC segments off whichever polyline came first —
        # dipole_rp_crossed_quadrature printed wire 1's port current on wire
        # 2's segment 14, a 90-degree error hidden behind a perfectly plausible
        # magnitude. Require the element to run along the NEC segment too, and
        # fall back to pure distance if nothing does (a curved GA arc, where
        # momwire's chord may sit at an angle to the card's).
        unit_e = dirs / np.maximum(np.linalg.norm(dirs, axis=1, keepdims=True), 1e-30)
        unit_s = wanted_dir / np.maximum(
            np.linalg.norm(wanted_dir, axis=1, keepdims=True), 1e-30
        )
        aligned = np.abs(unit_s @ unit_e.T) >= 0.5
        cost = np.where(aligned, d2, np.inf)
        fallback = ~np.isfinite(cost).any(axis=1)
        cost[fallback] = d2[fallback]
        nearest = np.argmin(cost, axis=1)
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


def _network_lines(solver: DeckSolver, result: dict) -> list[str]:
    """NETWORK DATA plus STRUCTURE EXCITATION DATA AT NETWORK CONNECTION POINTS.

    Both are *(ignored)* by ``Execute`` — its state machine only arms on the
    ``ANTENNA INPUT PARAMETERS`` banner, and the excitation table's rows have
    the same 11-token shape but are never reached. They are printed because the
    layout is the contract and a reader diffing against the oracle would
    otherwise see a missing section.
    """
    out = [_NETWORK_HEADER]
    # nec2c carries the PREVIOUS row's kind and re-emits the matching column
    # header whenever it changes, so a deck mixing TL and NT cards shows two
    # header blocks under one banner, interleaved in card order. Straight and
    # crossed lines are one kind and share a block.
    kind: type | None = None
    for a, b, branch, length in solver.network_rows:
        seg_a, seg_b = solver.segment_of_port(a), solver.segment_of_port(b)
        if isinstance(branch, LineBranch):
            values = (
                branch.z0,
                length,
                branch.y_a.real,
                branch.y_a.imag,
                branch.y_b.real,
                branch.y_b.imag,
            )
            tail = "CROSSED" if branch.crossed else "STRAIGHT"
            header = _LINE_TABLE_HEADER
        else:
            values = (
                branch.y11.real,
                branch.y11.imag,
                branch.y12.real,
                branch.y12.imag,
                branch.y22.real,
                branch.y22.imag,
            )
            tail = ""
            header = _NETWORK_TABLE_HEADER
        if kind is not type(branch):
            kind = type(branch)
            out += list(header)
        out.append(
            fmt_network_row(
                solver.segments[seg_a - 1].tag,
                seg_a,
                solver.segments[seg_b - 1].tag,
                seg_b,
                values,
                tail,
            )
        )
    out += ["", "", _NETWORK_EXCITATION_HEADER, *_NETWORK_EXCITATION_TABLE_HEADER]
    driven_ports = {port for port, _seg, _v in result["driven"]}
    for port in solver.network_report_order(driven_ports):
        number = solver.segment_of_port(port)
        volts = complex(result["v_gap"][port])
        current = complex(result["i_port"][port])
        out.append(
            fmt_aip_row(
                solver.segments[number - 1].tag,
                number,
                volts,
                current,
                volts / current if current != 0 else 0j,
                current / volts if volts != 0 else 0j,
                0.5 * (volts * np.conj(current)).real,
            )
        )
    return out


def _pattern_lines(
    card: Card, solver: DeckSolver, result: dict, freq_mhz: float
) -> list[str]:
    """The RADIATION PATTERNS table for one ``RP 0`` / ``RP 2`` / ``RP 3``.

    Two of the card's fields change the table's SHAPE rather than its values,
    and both are issue #802's:

    * ``I1 > 1`` (a cliff mode) prepends the FAR FIELD GROUND PARAMETERS
      block. It is printed whenever the mode asks for one, even in free space
      where it can move nothing;
    * ``F5 = RFLD = 0`` is the gain-only form. The two-line RANGE /
      EXP(-JKR)/R header is not printed at all, and the E columns carry the
      far-field amplitude itself instead of the field at a range — the same
      numbers scaled by ``RFLD/lambda``. The GAIN columns never depended on
      the range and do not move.
    """
    mode = card.i(0)
    n_theta, n_phi = max(card.i(1), 1), max(card.i(2), 1)
    theta0, phi0, d_theta, d_phi = card.f(4), card.f(5), card.f(6), card.f(7)
    rng = card.f(8)
    at_range = rng >= _FIELD_FLOOR2

    thetas = theta0 + d_theta * np.arange(n_theta)
    phis = phi0 + d_phi * np.arange(n_phi)
    wavelength = result["wavelength"]
    k = 2.0 * math.pi / wavelength
    second = solver.portal_deck.second_medium
    mid, moment, _nodes, _delta = solver.current_elements(result)
    m_theta, m_phi = _far_moments(
        mid,
        moment,
        k,
        np.radians(thetas),
        np.radians(phis),
        solver.portal_deck.ground,
        solver.engine._ground_z,
        freq_mhz * 1e6,
        cliff=(mode, second) if mode in _CLIFF_KIND and second is not None else None,
    )
    # E = -j·ηk/(4π)·e^(-jkr)/r·M_perp. The gain that follows is
    # 4π·U/P_in = ηk²/(8π·P_in)·|M|², the same normaliser the web solve and
    # MomwireEngine.far_field use — so a pattern read out of this printout and
    # one read off the workbench are the same number.
    prop = np.exp(-1j * k * rng) / rng if at_range else complex(1.0)
    e_theta = -1j * ETA0 * k / (4.0 * math.pi) * prop * m_theta
    e_phi = -1j * ETA0 * k / (4.0 * math.pi) * prop * m_phi
    p_in = result["p_in"]
    norm = ETA0 * k * k / (8.0 * math.pi * p_in) if p_in > 0 else 0.0
    g_v = norm * np.abs(m_theta) ** 2
    g_h = norm * np.abs(m_phi) ** 2
    # The printed field over the amplitude ffld returns, which is the basis
    # nec2c's blank-SENSE threshold is written in.
    floor_scale = 1.0 / (wavelength * abs(prop))

    out = []
    if mode in _CLIFF_KIND:
        out += _far_field_ground_lines(mode, second)
    out += [_PATTERN_HEADER]
    if at_range:
        out += [
            "",
            f"                             RANGE:{rng:14.6E} METERS",
            f"                             EXP(-JKR)/R:{1.0 / rng:13.5E} AT PHASE:"
            f"{math.degrees(math.atan2(prop.imag, prop.real)):8.2f} DEGREES",
        ]
    out += ["", *_PATTERN_TABLE_HEADER]
    for j in range(n_phi):
        for i in range(n_theta):
            et, ep = complex(e_theta[i, j]), complex(e_phi[i, j])
            axial, tilt, sense = _polarisation(et, ep, floor_scale)
            out.append(
                fmt_pattern_row(
                    thetas[i],
                    phis[j],
                    _gain_db(float(g_v[i, j])),
                    _gain_db(float(g_h[i, j])),
                    _gain_db(float(g_v[i, j] + g_h[i, j])),
                    axial,
                    tilt,
                    sense,
                    et,
                    ep,
                )
            )
    out += ["", ""]
    if card.i(3) % 10:  # XNDA's A digit: 1 asks for the average power gain
        out.append(_average_gain_line(g_v + g_h, thetas, d_theta, d_phi, n_phi))
    out.append(_PATTERN_TIME)
    return out


def _far_field_ground_lines(mode: int, second: SecondMedium | None) -> list[str]:
    """The FAR FIELD GROUND PARAMETERS block, plus the two blanks under it.

    ``rdpat`` prints this for any mode above 1, whether or not there is a
    ground for it to describe and whether or not the deck ever sent a card to
    fill it in — a cliff mode with no ``GD`` and no second medium on the ``GN``
    prints the block with four zeros in it, which is what a missing ``second``
    renders here.
    """
    pad = " " * 31
    fields = second or SecondMedium()
    return [
        _FAR_FIELD_GROUND_HEADER,
        "",
        "",
        f"{pad}--- {_CLIFF_KIND[mode]} CLIFF ---",
        f"{pad}EDGE DISTANCE= {fields.edge_distance:9.2f} METERS",
        f"{pad}       HEIGHT= {fields.height:9.2f} METERS",
        f"{pad}--- SECOND MEDIUM ---",
        f"{pad}RELATIVE DIELECTRIC CONST= {fields.eps_r2:10.3f}",
        f"{pad}      GROUND CONDUCTIVITY= {fields.sigma2:10.3f} MHOS",
        "",
        "",
    ]


def _average_gain_line(gain, thetas, d_theta, d_phi, n_phi) -> str:
    """``AVERAGE POWER GAIN`` over the sampled solid angle.

    The quadrature is nec2c's, recovered from two fixtures: each theta sample
    owns the solid-angle band between its half-step neighbours, CLIPPED to the
    requested theta range, so the bands telescope to exactly
    ``(cosθ_start - cosθ_end)·Δφ`` and the printed solid angle comes out at a
    round ``(+4.0000)*PI`` for a full sphere and ``(+2.0000)*PI`` for a
    hemisphere. Phi contributes ``n_phi - 1`` columns — the last sample of a
    0..360 sweep is the first one again and must not be counted twice.
    """
    lo = np.radians(np.maximum(thetas - 0.5 * d_theta, thetas[0]))
    hi = np.radians(np.minimum(thetas + 0.5 * d_theta, thetas[-1]))
    band = np.cos(lo) - np.cos(hi)
    columns = max(n_phi - 1, 1)
    step = math.radians(d_phi) if d_phi else 2.0 * math.pi
    total = float(np.sum(gain[:, :columns] * band[:, None])) * step
    solid = float(np.sum(band)) * columns * step
    average = total / solid if solid else 0.0
    return (
        f"  AVERAGE POWER GAIN:{average:12.4E} - SOLID ANGLE USED IN AVERAGING: "
        f"({solid / math.pi:+7.4f})*PI STERADIANS"
    )


def _near_field_lines(card: Card, solver: DeckSolver, result: dict) -> list[str]:
    """The NEAR ELECTRIC / MAGNETIC FIELDS table for one ``NE``/``NH`` grid."""
    magnetic = card.mnemonic == "NH"
    n_x, n_y, n_z = (max(card.i(k), 1) for k in (1, 2, 3))
    start = np.array([card.f(4), card.f(5), card.f(6)])
    step = np.array([card.f(7), card.f(8), card.f(9)])
    # NEC varies X fastest, then Y, then Z (dipole_ne_nearfield.out).
    points = np.array(
        [
            start + np.array([ix, iy, iz]) * step
            for iz in range(n_z)
            for iy in range(n_y)
            for ix in range(n_x)
        ]
    )
    ground = solver.portal_deck.ground
    if ground.kind in ("refl", "sommerfeld"):
        raise PortalError(
            f"{card.mnemonic} over a finite ground is not supported by this "
            f"engine (the near field of a Sommerfeld half-space is not an image)"
        )
    k = 2.0 * math.pi / result["wavelength"]
    radius = solver._smallest_radius
    mid, moment, nodes, delta = solver.current_elements(
        result, subdiv=_NEAR_FIELD_SUBDIV
    )
    field = _element_fields(points, (mid, moment, nodes, delta), k, radius, magnetic)
    if ground.kind == "pec":
        # The PEC image mirrors the current moments (horizontal components
        # flip) and NEGATES the charge, which is the same statement: reversing
        # a horizontal current reverses dI/ds, and mirroring a vertical one
        # reverses the arc direction.
        ground_z = solver.engine._ground_z
        mid_img, moment_img = _image_moments(mid, moment, ground_z)
        nodes_img = nodes.copy()
        nodes_img[:, 2] = 2.0 * ground_z - nodes[:, 2]
        field = field + _element_fields(
            points,
            (mid_img, moment_img, nodes_img, -delta),
            k,
            radius,
            magnetic,
        )

    header = _NEAR_H_HEADER if magnetic else _NEAR_E_HEADER
    table = _NEAR_H_TABLE_HEADER if magnetic else _NEAR_E_TABLE_HEADER
    out = [header, "", *table] if magnetic else [header, *table]
    for point, value in zip(points, field, strict=True):
        out.append(
            fmt_near_field_row(
                point, complex(value[0]), complex(value[1]), complex(value[2])
            )
        )
    out.append(_NEAR_FIELD_TIME)
    return out


def _printed_segments(pt: PrintControl | None, solver: DeckSolver) -> list[_Segment]:
    """The CURRENTS AND LOCATION rows a ``PT`` card leaves standing.

    Only the ``PT 0 <tag> <first> <last>`` form restricts anything, and its
    range is addressed the way an ``EX`` card addresses a segment: relative to
    the tag, with ``tag = 0`` meaning absolute segment numbers. ``PT 0 <tag> 0
    0`` prints everything (measured), so an all-zero range is "no restriction".
    """
    if pt is None or not pt.restricted:
        return solver.segments
    first = solver.global_segment(*_locate(solver.wires, pt.tag, pt.first))
    last = solver.global_segment(*_locate(solver.wires, pt.tag, pt.last))
    return [s for s in solver.segments if first <= s.number <= last]


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
            *(
                ["                        THE EXTENDED THIN WIRE KERNEL WILL BE USED"]
                if group.ek
                else []
            ),
            "",
            "",
        ]
    if group.refilled or group.refilled_partial:
        out += [_LOADING_HEADER]
        rows = _loading_rows(deck)
        if rows:
            out += [*_LOADING_TABLE_HEADER, *rows]
        else:
            out.append(_LOADING_NONE)
        out += ["", ""]
        out += _environment_lines(deck.ground, freq_mhz)
        # The MP advisory sits at column 0 between the environment block and
        # the blanks before MATRIX TIMING, and carries one blank of its own —
        # so a multiprocessing deck shows THREE blanks there and a plain one
        # shows two (fixtures dipole_mp_multiprocessor / dipole_free_space).
        if group.mp is not None and group.mp.parallel:
            out += [group.mp.line(), ""]
        out += ["", ""]
        out += [
            _MATRIX_TIMING_HEADER,
            f"                               FILL: {result['fill_ms']} msec"
            f"  FACTOR: 0 msec",
            "",
            "",
        ]
    if solver.network_rows:
        out += _network_lines(solver, result)
        out += ["", ""]
    out += [_AIP_HEADER, *_AIP_TABLE_HEADER]
    i_source = result["i_source"]
    for port, global_seg, volts in result["driven"]:
        current = i_source[port]
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
    suppressed = group.pt is not None and group.pt.suppressed
    if not suppressed:
        out += ["", "", _CURRENTS_HEADER, _CURRENTS_NOTE, "", *_CURRENTS_TABLE_HEADER]
    currents = result["segment_currents"]
    # The ``-YY`` report is printed either way — under ``PT -1`` it lands
    # directly after the last ANTENNA INPUT PARAMETERS row, with no blank and
    # no table around it (fixture: dipole_pt_toggle). It is the row SimNEC's
    # addYYLine parses, so suppression must not take it with the table.
    if deck.yy_points:
        out.append(
            fmt_yy_row(
                [solver.report_current(tag, seg, result) for tag, seg in deck.yy_points]
            )
        )
    if not suppressed:
        for seg in _printed_segments(group.pt, solver):
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
        f"{pad}NETWORK LOSS  ={result['p_network']:12.4E} Watts",
        f"{pad}EFFICIENCY    ={result['efficiency']:8.2f} Percent",
    ]
    if group.report is not None:
        report = group.report
        if report.mnemonic == "RP":
            body = _pattern_lines(report, solver, result, freq_mhz)
        else:
            body = _near_field_lines(report, solver, result)
        # Two blanks before the report, and one MORE after it than a plain XQ
        # block carries — render_deck's own three make the four the oracle
        # prints between the compute-time line and the trailing XQ echo.
        out += ["", "", *body, ""]
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
        _append_error(out, exc)
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
        _append_error(out, exc)
        return out, err
    except (ValueError, np.linalg.LinAlgError) as exc:
        _append_error(out, exc)
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
        if card.mnemonic not in _EXECUTE_CARDS:
            continue
        group = deck.groups[group_index]
        group_index += 1
        if group is None:
            # A bare XQ trailing an RP/NE/NH: echoed, runs nothing, prints
            # nothing — not even the blank lines a real run is wrapped in.
            continue
        out += ["", ""]
        try:
            for i, freq in enumerate(group.freqs_mhz):
                if i:
                    out += ["", ""]
                out += _run_block(deck, solver, group, freq)
        except (PortalError, ValueError, np.linalg.LinAlgError) as exc:
            _append_error(out, exc)
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
    out += list(_banner_lines()[1:])
    return out, err


def run_deck(body: str) -> tuple[str, str]:
    """(stdout, stderr) for a single deck run against a fresh process: the
    start-up banner, the deck's frame, and whatever went to stderr."""
    out, err = deck_frame(body)
    return (
        "\n".join([*_banner_lines(), *out]) + "\n",
        ("\n".join(err) + "\n" if err else ""),
    )


# --------------------------------------------------------------------------
# the resident protocol
# --------------------------------------------------------------------------


_SELFTEST_DECKS = (
    # A free-space dipole, the two-source Y probe, a TL station, and a
    # grounded vertical carrying GD — the four deck shapes a live SimNEC
    # session leans on hardest.
    # EK rides in deck 1 because the live NECSource path ALWAYS sends it —
    # the card whose absence from the bench corpus caused the first live
    # failure (Windows session, 2026-08-08).
    "CE selftest 1\n"
    "GW 1 11 0. -5. 10. 0. 5. 10. 0.001\n"
    "GE 0\nEK\nEX 0 1 6 0 1.\nFR 0 1 0 0 14.0 1\nXQ\nNX\n",
    "CE selftest 2\n"
    "GW 1 11 0. -5. 10. 0. 5. 10. 0.001\n"
    "GW 2 11 3. -5. 10. 3. 5. 10. 0.001\n"
    "GE 0\nYY 1 6 2 6\n"
    "EX 0 1 6 0 1.\nFR 0 1 0 0 14.0 1\nXQ\n"
    "EX 0 2 6 0 1.\nFR 0 1 0 0 14.0 1\nXQ\nNX\n",
    "CE selftest 3\n"
    "GW 1 11 0. -5. 10. 0. 5. 10. 0.001\n"
    "GW 2 3 20. -0.5 10. 20. 0.5 10. 0.001\n"
    "GE 0\nTL 2 2 1 6 600. 20.\n"
    "EX 0 2 2 0 1.\nFR 0 1 0 0 14.0 1\nXQ\nNX\n",
    # Deck 4 is the EZNEC-example shape, comma-delimited exactly as
    # NECSource writes it: a ground card followed by GD, the second card
    # whose refusal broke a live session (see SecondMedium). It rides here
    # for the same reason EK rides in deck 1 — so a deployment gate can never
    # pass while a card the live path sends is being refused.
    "CE selftest 4\n"
    "GW 1 11 0. 0. 0.5 0. 0. 10.5 0.001\n"
    "GE -1\nGN 1\nGD 2,0,0,0,13.,.005,0.,0.\n"
    "EX 0 1 1 0 1.\nFR 0 1 0 0 14.0 1\nXQ\nNX\n",
)


def _selftest(stdout) -> int:
    """Deployment smoke with no files needed (``momwire-nec2c --selftest``).

    The unit suite proves the printout; this proves the PROCESS on the box it
    will actually run on — the resident loop under a real OS pipe, which is
    what a SimNEC session depends on and what matters when the install is a
    bare ``pip install`` with no checkout (e.g. the Windows box, where SimNEC
    launches engines through ``cmd.exe`` and text I/O is CRLF). It spawns
    itself exactly once, feeds four embedded decks down the one process, and
    requires per deck: the banner (first deck only), an ANTENNA INPUT
    PARAMETERS section, and the NX data-card echo sentinel — miss that and a
    live SimNEC hangs forever, which is the failure this exists to catch.
    """
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m", "antennaknobs.nec_portal"],
        input="".join(_SELFTEST_DECKS),
        capture_output=True,
        text=True,
        timeout=120,
    )
    checks = {
        "process exited 0": proc.returncode == 0,
        "banner present": "VERSION:" in proc.stdout,
        "EK accepted": "EXTENDED THIN WIRE KERNEL" in proc.stdout,
        "GD accepted": any(
            ln.lstrip().startswith("DATA CARD No:") and " GD " in ln
            for ln in proc.stdout.splitlines()
        ),
        "5 solve groups answered": proc.stdout.count("ANTENNA INPUT PARAMETERS") == 5,
        "4 NX sentinels": sum(
            1
            for ln in proc.stdout.splitlines()
            if ln.lstrip().startswith("DATA CARD No:") and " NX " in ln
        )
        == 4,
        "-YY row present": "    -YY " in proc.stdout,
        "TL network row present": "STRAIGHT" in proc.stdout,
        "stderr quiet": proc.stderr.strip() == "",
    }
    # One deck per alternate basis: the point is that the entry is wired and
    # answers on THIS box, not that it is fast or converged. The selftest deck
    # is a single small dipole, which for `hmatrix`/`arrayblock` means a
    # near-field-only operator and (for arrayblock) a degenerate element
    # partition that degrades to the parent — the graceful-degradation path,
    # which is exactly the one a smoke test wants to prove never raises.
    for basis, suffix in (
        ("sinusoidal-galerkin-converged", "+sgc"),
        ("sinusoidal", "+sin"),
        ("bspline-d1", "+bs1"),
        ("hmatrix", "+hm"),
        ("arrayblock", "+ab"),
    ):
        alt = subprocess.run(
            [sys.executable, "-m", "antennaknobs.nec_portal", "--basis", basis],
            input=_SELFTEST_DECKS[0],
            capture_output=True,
            text=True,
            timeout=120,
        )
        checks[f"alt basis answers ({suffix})"] = (
            alt.returncode == 0
            and suffix in alt.stdout
            and "ANTENNA INPUT PARAMETERS" in alt.stdout
        )
    for name, ok in checks.items():
        stdout.write(f"  {'ok  ' if ok else 'FAIL'} {name}\n")
    passed = all(checks.values())
    stdout.write("PASS\n" if passed else "FAIL\n")
    stdout.flush()
    return 0 if passed else 1


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

    # --basis rides the necCommand line itself: SimNEC launches engines via
    # `sh -c <command>` / `cmd.exe /c`, so the portal-dialog string can carry
    # arguments — two entries differing only in --basis are two engines. An
    # unknown basis fails FAST and nonzero so the -version probe surfaces the
    # mistake at configure time instead of a silent wrong default.
    global _active_basis
    _active_basis = _BASES["bspline"]  # per-invocation default, never sticky
    rest = list(argv)
    while "--basis" in rest or any(a.startswith("--basis=") for a in rest):
        if "--basis" in rest:
            k = rest.index("--basis")
            name = rest[k + 1] if k + 1 < len(rest) else ""
            del rest[k : k + 2]
        else:
            k = next(i for i, a in enumerate(rest) if a.startswith("--basis="))
            name = rest.pop(k).split("=", 1)[1]
        if name not in _BASES:
            stdout.write(
                f"unknown --basis {name!r}; choices: {', '.join(sorted(_BASES))}\n"
            )
            stdout.flush()
            return 3
        _active_basis = _BASES[name]
    argv = rest

    # --legacy-probe swaps the honest versionNECd identity for the pre-#828
    # versionA masquerade — for a SimNEC build old enough to predate
    # versionNECd, should one surface. Deck behavior is identical either way
    # (the probe response sets no engine state; see PROBE_VERSION).
    legacy_probe = "--legacy-probe" in argv
    argv = [a for a in argv if a != "--legacy-probe"]

    if any(a.lstrip("-").lower() == "version" for a in argv):
        stdout.write(f"{LEGACY_PROBE_VERSION if legacy_probe else PROBE_VERSION}\n")
        stdout.flush()
        return 0

    if any(a.lstrip("-").lower() == "selftest" for a in argv):
        return _selftest(stdout)

    # The banner belongs to process start-up; every later one trails an NX.
    stdout.write("\n".join(_banner_lines()) + "\n")
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
