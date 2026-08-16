"""momwire as a resident SimNEC engine — the ``nec2c`` portal daemon.

SimNEC (``nec2/NEC2Daemon``) starts one NEC-2 process and keeps it: decks
arrive on stdin framed by an ``NX`` card, printouts leave on stdout, and the
Java side blocks in ``readLine()`` until it sees the ``NX`` data-card echo.
This module is that process, with momwire behind it instead of nec2c.
Standalone use (a shell redirect instead of SimNEC) gets one extension the
Java side never exercises: ``EN`` — a stock deck's final card — also
terminates a frame, and ends the run the way genuine nec2c does (#901).

The contract is pinned in ``docs/status/2026-08-08-simnec-execute-grammar.md``
(issue #792 units 1-3) and in the 36 oracle deck/printout pairs under
``tests/fixtures/nec_portal/``. Everything here — column widths, header
strings, section order, the stderr discipline — is copied out
of those two sources. **Layout is the contract; the numbers are momwire's.**
A different basis and kernel will never reproduce nec2c digit for digit, and
SimNEC does not need it to: it reads exactly two numbers per
``ANTENNA INPUT PARAMETERS`` row (the CURRENT real/imaginary columns, fields 4
and 5 of an 11-token row) and builds its Y matrix from them.

The dialect is momwire's
------------------------
Since #846 phase II this module owns the PROTOCOL and momwire owns the
LANGUAGE. ``momwire.deck.parse(text, dialect="nec2")`` reads the deck against
the normative grammar published at
momwire.dev/reference/deck-grammar-nec2 — every card, every field, every
refusal message — and ``momwire.deck.build_solver`` maps the resulting
dialect-neutral ``DeckModel`` onto a solver family plus the ``PortPlan`` that
says what its ports mean. What is left here is what a solver has no vocabulary
for: NEC's tags and global segment numbers, the column-exact printout, the
resident stdin framing, and the port algebra that stamps a load onto a
solution the fill knows nothing about.

The dialect is **antenna-only**, which is what the restriction buys: a
structure of thin wires, driven by voltage sources, optionally over a ground.
``TL`` and ``NT`` are refused by name — solve the network outside the engine,
or import the deck with antennaknobs, which keeps NEC's full network grammar
(``nec_import.parse_nec``). Across the 44-deck reference corpus the two cards
appear in three hand-authored probe decks and nowhere else; SimNEC's own
``NECSource`` never writes them and its state machine never reads the sections
they would print.

Scope (units 2 and 3 — the whole portal dialect bar the long tail):

* the version probe, the resident stdin loop, the ``NX`` sentinel;
* ``CM``/``CE`` directives ``QQ`` (quiet) and ``FF`` (the one stderr line);
* geometry ``GW``/``GM``/``GS``/``GE``, environment ``GN 0/1/2`` and ``GD``,
  loading ``LD 0/1/4/5``, insulation ``IS``, excitation ``EX 0``, ``FR``,
  ``EK`` (the extended thin-wire kernel, honoured since #849 — every I1
  except -1 enables it, matching nec2c), and ``XQ``; (Ward's ``YY``
  report card was retired in #839 — abandoned upstream, its only sender
  a dev benchmark);
* unit 3: ``RP 0/2/3`` radiation patterns and ``NE``/``NH`` near-field grids
  — each of which is also an *execute* card in its own right (they run the
  pending group, so a bare ``XQ`` after one of them re-runs nothing);
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
  impedance loading, antenna environment, matrix timing, antenna input
  parameters, currents and location, power budget, radiation patterns,
  near electric/magnetic fields.

Refused by name, with the grammar's own message: ``TL``/``NT`` (networks),
``GA``/``GH``/``GX``/``GR``/``GC``/``GF`` (geometry out of dialect),
``SY``, ``SP``/``SM`` (surface patches), ``RP`` modes 1 and 4-6, spherical
``NE``/``NH`` grids, ``GN`` radial-wire ground screens, ``EX`` types other
than 0, ``LD`` types 2/3/6/7 and the ranges that cannot expand, and the four
``IS`` cases a lossless whole-wire jacket cannot express. Every one of them
takes the error path below rather than crashing the daemon — the printout says
which card and why, and the ``NX`` sentinel is still emitted.

Where the physics citations point
---------------------------------
Comments below that name a NEC routine — ``FFLD``, ``RDPAT``, ``DB10``, the
main program's card reader — cite the ORIGINAL NEC-2 FORTRAN, a US government
work in the public domain: ``nec2dx.f`` (NEC-2D, Lawrence Livermore National
Laboratory, "FILE CREATED 4/11/80", double-precision revision 6/4/85),
cross-checked against the single-precision ``nec2-1.2.1.2.f`` of the same
lineage, and the equations of the public Program Description (Burke & Poggio,
*NEC-2 Part I: Theory*, cited by equation number). No C translation is cited
anywhere in this file; ``tests/fixtures/nec_portal/README.md`` carries the
provenance record in full.

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

And the deck need not be the boundary either. The protocol is stateless — a
sweep arrives as N independent decks, each re-sending the whole geometry — but
the ENGINE may remember, so with ``--cache`` a solver is kept ACROSS decks
under a key that is the operator's own identity (``_operator_key``,
``_solver_for``). A knob returned to a value already probed, a restarted
sweep, a crew member handed the same structure at a different frequency:
geometry parse, mesh, port maps and every fill already paid are reused,
bounded by an LRU cap on estimated resident bytes. The printout is identical
either way — that is the whole correctness claim, and it is what the tests
assert.

That is OFF by default. The saving is real and measured on the bench, but the
workload it exploits is a live SimNEC session's re-probe rate, which nobody
has measured — so the shipped default stays the behaviour that has been
validated, and ``--cache-stats PATH`` answers the question first: it counts
what a cache WOULD have served while solving every deck fresh, and writes the
tally to a file after every deck. Nothing about either flag reaches stdout or
stderr; the protocol is byte-identical in all three modes.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from types import MappingProxyType

import numpy as np
from momwire import (
    ArrayBlockSolver,
    BSplineSolver,
    HMatrixSolver,
    SinusoidalGalerkinSolver,
    SinusoidalSolver,
)
from momwire.deck import Card, DeckError, build_solver
from momwire.deck import parse as parse_dialect
from momwire.deck import parse_card

# The NEC-level view of a deck's geometry: the flat wire list after every
# GM/GS transform and both connection passes, carrying the TAGS and the
# (tag, segment) resolver. ``momwire.deck``'s public surface deliberately
# stops at the dialect-neutral ``DeckModel``, whose vocabulary has no tags,
# no segment numbers and no card ordinals (spec ``#the-deckmodel``) — but
# every table in this printout is addressed in exactly those terms, so the
# portal needs the layer underneath the model as well. This is the one
# momwire-internal import in this file; #846 phase III (which moves this
# module into ``momwire/portal/``) turns it into an ordinary intra-package
# import, and the follow-up filed with it asks momwire to promote
# ``Nec2Structure`` to ``momwire.deck``'s public surface if the portal is
# ever a third-party consumer again.
from momwire.deck._nec2_geometry import build_geometry

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
# The same name, as ``momwire.deck.build_solver`` takes it. ``momwire.deck``'s
# own ``BASES`` roster is spelt to match this table exactly (momwire#359), so
# one string selects the same physics on either side of the portal; the class
# and kwargs above stay because the banner suffix and the operator key are the
# portal's business, not the dialect's.
_active_basis_name = "bspline"

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
# against the 5.1a0 bytecode (issue #828; grammar doc, 2026-08-09 addendum):
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

# NEC-2's two degenerate-value thresholds. They are both spelt 1e-20 and they
# are NOT the same test — a fact that hides completely while every pattern
# fixture is taken at one range and one wavelength, and stops hiding the
# moment an ``RFLD = 0`` deck arrives (issue #802).
#
# * ``_GAIN_FLOOR2`` is ``DB10``'s — ``nec2dx.f``, ``FUNCTION DB10``:
#   ``IF (X.LT.1.D-20) GO TO 2 ... 2 DB10=-999.99``. It clamps the LINEAR
#   POWER GAIN, the number about to be logged, so a direction below -200 dB
#   prints -999.99. Gain never depended on the range, so this floor is
#   range-free too.
# * ``_FIELD_FLOOR2`` is the polarisation block's — ``RDPAT``:
#   ``IF (ETHM2.GT.1.D-20.OR.EPHM2.GT.1.D-20) GO TO 11``, and the fall-through
#   sets ``ISENS=HBLK``. That blanks AXIAL/TILT/SENSE, and a blank SENSE is
#   exactly what makes a row 11 tokens instead of 12. It is applied to the
#   field as ``FFLD`` returns it — BEFORE the ``*WLAM`` and the ``*EXRM``
#   (``EXRM=1./RFLD``) that turn it into the volts-per-metre the table prints
#   — so it is a fixed bar on the antenna, not on the reading.
#   :func:`_pattern_lines` rescales the printed field back to that basis
#   before testing it.
#
# Read off ``dipole_rp_pattern.out`` (E_theta = 5.4196E-15 at theta = 180 ->
# -999.99 and blank) and confirmed against ``dipole_rp_crossed_quadrature.out``
# (E_theta = 2.7098E-15 -> VERTC -999.99 but SENSE still LINEAR, because
# E_phi is large). Grammar doc §4.14.
_FIELD_FLOOR2 = 1.0e-20
_GAIN_FLOOR2 = 1.0e-20
_GAIN_FLOOR_DB = -999.99

# The ``RP`` modes this engine computes: space wave, linear cliff, circular
# cliff. The dialect refuses the rest by name (spec ``#rp--radiation-
# pattern``); these two are the only modes whose table this module draws
# differently, through the FAR FIELD GROUND PARAMETERS block.
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

_PATTERN_HEADER = (
    "                             ---------- RADIATION PATTERNS -----------"
)
# Printed by ``RDPAT`` ahead of the pattern banner whenever the RP mode is > 1,
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


# What a caller catches to mean "the DECK is at fault, not the code". The
# dialect's own refusals arrive as ``momwire.deck.DeckError`` (a ValueError
# subclass carrying the spec's message verbatim); the portal's own — the
# handful of refusals that are about the PRINTOUT rather than the physics —
# arrive as :class:`PortalError`. Both take the same two-line error frame.
_DECK_REFUSALS = (PortalError, DeckError)


# --------------------------------------------------------------------------
# cards
# --------------------------------------------------------------------------
#
# Card TOKENIZATION and every dialect refusal now belong to ``momwire.deck``
# (#846 phase II): ``parse_card`` above is momwire's, and the refusal table —
# ``TL``/``NT`` by name, ``GA``/``GH``/``GX``/``GR``, ``SP``/``SM``, the ``EX``
# type gate, the ``RP`` mode gate, ``GN``'s radial screens, the ``LD`` types
# and ranges, ``IS``'s four cases — is the normative grammar's, published at
# momwire.dev/reference/deck-grammar-nec2. This module frames those messages;
# it no longer writes them.

# Cards echoed inside STRUCTURE SPECIFICATION rather than as DATA CARD lines.
# The dialect's geometry is GW with GM / GS transforms and the GE terminator;
# GA/GH/GX/GR are refused by name upstream, so nothing else reaches here.
_GEOMETRY_CARDS = frozenset({"GW", "GM", "GS", "GE"})

# Cards that RUN the pending excitation group. ``RP``/``NE``/``NH`` are not
# just report requests: nec2c executes on reading them and then prints their
# table after the power budget, which is why ``dipole_rp_pattern.out`` echoes
# EX / FR / RP, runs, and only then echoes the trailing ``XQ`` — an ``XQ`` with
# nothing new since the last execution produces no output at all.
_EXECUTE_CARDS = frozenset({"XQ", "RP", "NE", "NH"})

# Cards that end a deck body. The framing caller normally splits on them
# before this module sees anything, but a body that still carries one stops
# here exactly where the dialect parser stops.
_TERMINATORS = frozenset({"NX", "EN"})

# Cards that REBUILD THE OPERATOR when they arrive between two execute cards.
# The oracle then prints the LOADING / ENVIRONMENT / MATRIX TIMING part of the
# refill preamble but no FREQUENCY block — the ``refilled_partial`` shape
# ``dipole_ek_rearm`` pins for ``EK`` and ``dipole_gn_rearm`` for ``GN``.
#
# Measured on the oracle (probes ``XQ / <card> / XQ``, 2026-08-15): ``GN 1``
# prints the partial preamble and the impedance moves (issue #933, the bug
# this replaces — the old ``GN`` branch never reached the arming test at all),
# and ``EX`` prints no preamble at all, because moving the drive does not move
# the matrix.
#
# ``LD`` belongs here on the same measurement and is deliberately ABSENT: an
# ``LD`` between two execute cards makes the loading table itself per group
# (the oracle's first block reports THIS STRUCTURE IS NOT LOADED), and both
# the table and the stamped impedance are deck-level here — as they were
# before this rewire. Fixing it is a separate change with its own fixture;
# adding the flag alone would print a preamble around an unchanged table.
_OPERATOR_CARDS = frozenset({"EK", "GN"})


@dataclass(frozen=True)
class Ground:
    """The deck's ``GN`` card, reduced to what both the printout and momwire
    need. ``kind`` is one of free / pec / refl / sommerfeld."""

    kind: str = "free"
    eps_r: float = 0.0
    sigma: float = 0.0

    @classmethod
    def from_model(cls, ground) -> Ground:
        """The printout's view of ``DeckModel.ground``.

        The model speaks momwire's ground vocabulary — ``None`` / ``"pec"`` /
        ``("finite-fast" | "finite", eps_r, sigma)`` — and this record is the
        NEC-facing half: the four words the ANTENNA ENVIRONMENT block prints
        and the two constants that go with them. The ``GN`` card's own reading
        (which type means which model, and the radial-screen refusal) lives in
        the dialect now, not here.
        """
        if ground is None:
            return cls("free")
        if ground == "pec":
            return cls("pec")
        model, eps_r, sigma = ground
        return cls("refl" if model == "finite-fast" else "sommerfeld", eps_r, sigma)


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
    and NEC's card reader writes them into the same four ``/FPAT/`` slots
    (``nec2dx.f`` main program, the ``GN`` branch at label 23 vs the ``GD``
    branch at label 34), so a deck can state a whole cliff without ever
    sending a ``GD``. Both routes land here, and a
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
    moved from "we are never asked" to "we answer it the way ``FFLD`` does".
    """

    eps_r2: float = 0.0
    sigma2: float = 0.0
    edge_distance: float = 0.0  # CLT
    height: float = 0.0  # CHT

    @classmethod
    def from_model(cls, second) -> SecondMedium | None:
        """The printout's view of ``DeckModel.second_medium``.

        Which card carried it — ``GD``, or a ``GN`` whose ``NRADL`` is zero —
        is the dialect's business; by the time it reaches here it is four
        numbers and the question of which cliff mode reads them.
        """
        if second is None:
            return None
        return cls(second.eps_r, second.sigma, second.edge_distance, second.height)


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
        blank, both column-header lines and every row
        (fixture: ``dipole_pt_toggle``).
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
        # A fractional field is NEC's own integer-reader error and the
        # dialect refuses it before this card is ever echoed, so the two
        # fields are integers by the time they reach the printout.
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
    # EK in force when this group fired. HONOURED since issue #849 (momwire
    # 0.26.0): the solver this group is answered from is built with
    # `extended_kernel=True`, the same O(a²) on-axis tube expansion NEC's card
    # asks for. It was advisory before that — momwire had no extended kernel to
    # switch to — which is why it is per GROUP rather than per deck: the
    # printout always had to distinguish the two, and now the operator does
    # too (`DeckSolver.at` keys its per-frequency fill on the kernel as well).
    #
    # The refilled preamble must announce it exactly as the oracle does — and
    # only there: an EK between two XQs re-arms execution without a refill, and
    # the oracle prints no announcement for it (measured: XQ / EK / XQ shows
    # two AIP sections, one preamble, zero announcements).
    ek: bool = False
    # An operator card between two execute cards refills the matrix WITHOUT a
    # new FR: the oracle then prints the LOADING / ENVIRONMENT / MATRIX TIMING
    # part of the preamble but no FREQUENCY block and no kernel announcement
    # (fixtures dipole_ek_rearm, dipole_gn_rearm, dipole_ld_rearm). Advisory
    # refill for us — the cached factors are already momwire's — but the
    # printout must walk the same sections. See ``_OPERATOR_CARDS``.
    refilled_partial: bool = False
    # The ENVIRONMENT in force when this group fired — the ground the ANTENNA
    # ENVIRONMENT block names and the operator is filled over, plus the second
    # medium a cliff-mode pattern reads. Per group because ``GN`` re-arms
    # (#933): a deck may run once in free space and once over ground, and the
    # oracle answers each group over the ground the cards had reached.
    #
    # ``momwire.deck``'s ``DeckModel`` carries ONE deck-level ground even
    # though its own spec makes ``GN`` an arming card, so a per-group ground
    # cannot be read off the model; ``parse_deck`` recovers it by re-reading
    # the deck prefix that ends at this group's execute card, and
    # ``DeckSolver`` stamps it onto the model with ``dataclasses.replace``.
    # ``momwire_ground`` is that model-vocabulary value; ``ground`` and
    # ``second_medium`` are the printout's view of the same thing.
    ground: Ground = field(default_factory=Ground)
    second_medium: SecondMedium | None = None
    momwire_ground: object = None


@dataclass
class PortalDeck:
    """A deck body (everything up to, not including, its ``NX``).

    Two readings of the same cards live side by side here, and the split is
    deliberate (#846 phase II, design doc §7):

    * :attr:`model` is ``momwire.deck``'s — the dialect-neutral
      :class:`~momwire.deck.model.DeckModel` that decides what gets SOLVED:
      wires, feeds, loads, ground, and one entry per execute card saying
      whether it ran and at which frequencies. Every dialect refusal is its.
    * everything else is the PRINTOUT's — the cards as written, in the order
      the ``DATA CARD No:`` echo needs them, and the per-group print state
      (which report card fired, which ``MP``/``PT`` was in force) that the
      model deliberately does not carry, because a card ordinal is not part
      of a solver's vocabulary.

    The two readings must agree about arming, frequencies and drive, and
    ``test_nec_portal.py::test_the_portal_and_the_dialect_agree_*`` is the
    proof, run over every deck in the corpus.
    """

    comments: tuple[str, ...] = ()
    geometry: tuple[Card, ...] = ()
    data_cards: tuple[Card, ...] = ()
    # One entry per EXECUTE card in ``data_cards`` order; None marks an execute
    # card that ran nothing (a bare ``XQ`` trailing an ``RP``/``NE``/``NH``).
    groups: tuple[ExecuteGroup | None, ...] = ()
    loads: tuple[Card, ...] = ()
    ground: Ground = field(default_factory=Ground)
    # The deck's ``GD`` card, if it carried one. Kept so the deck is a full
    # record of what arrived; it moves no number here (see :class:`SecondMedium`).
    second_medium: SecondMedium | None = None
    ground_plane_flag: bool = False
    quiet: bool = False
    reduced_field: int | None = None
    # momwire's own reading of the same deck: what gets solved, and the
    # geometry underneath it (the flat NEC wire list, the tags, and the
    # ``(tag, segment)`` resolver every table in the printout is addressed by).
    model: object | None = None
    structure: object | None = None


def parse_deck(body: str) -> PortalDeck:
    """A deck body's cards, grouped the way the engine executes them.

    ``momwire.deck.parse`` reads the deck first and owns every refusal: this
    function only ever sees a deck the dialect will run, so it carries no
    error path of its own beyond the tokenizer's. What it adds is the
    printout's view — the card echo, the geometry rows, and the per-group
    report/MP/PT state — plus the two things the model cannot express:

    * the group's ``EX`` addresses as ``(tag, segment)`` pairs, because the
      ``ANTENNA INPUT PARAMETERS`` table is addressed in NEC's terms and
      because a source explicitly driven at 0 V is a printed row while an
      undriven port is not — a distinction a voltage vector cannot make;
    * ``refilled_partial``, the partial refill preamble an operator card
      between two execute cards produces (see ``_OPERATOR_CARDS``);
    * the ENVIRONMENT in force at each execute card, when a ``GN`` or ``GD``
      arrives after the first one (see :func:`_environments_per_group`).
    """
    model = parse_dialect(body, dialect="nec2")

    comments: list[str] = []
    geometry: list[Card] = []
    data_cards: list[Card] = []
    groups: list[ExecuteGroup | None] = []
    loads: list[Card] = []
    sources: list[tuple[int, int, complex]] = []
    executed = 0
    multiprocessing: Multiprocessing | None = None
    print_control: PrintControl | None = None
    second_medium = SecondMedium.from_model(model.second_medium)
    # True when a card that REBUILDS the operator has arrived since the last
    # execute card. It is the printout's half of arming: the dialect decides
    # whether the next execute card runs at all, this decides whether the run
    # reprints the loading / environment / matrix-timing preamble.
    operator_dirty = False
    sources_stale = False
    # The deck lines up to and including each execute card, kept only while a
    # GN or GD is still capable of arriving after one — which is the whole
    # reason a group's environment can differ from the deck's.
    prefix: list[str] = []
    prefixes: list[list[str]] = []
    env_moves = False

    for line in body.splitlines():
        card = parse_card(line)
        if card is None:
            continue
        if card.mnemonic in _TERMINATORS:
            break
        prefix.append(line)
        if card.mnemonic in ("CM", "CE"):
            comments.append(card.text)
            continue
        if card.mnemonic in _GEOMETRY_CARDS:
            geometry.append(card)
            continue
        data_cards.append(card)
        if card.mnemonic in _OPERATOR_CARDS and executed:
            operator_dirty = True
        if card.mnemonic in ("GN", "GD") and executed:
            env_moves = True
        if card.mnemonic == "LD":
            # The loading table echoes the cards in force, and ``LD -1``
            # nullifies every load read so far — the dialect's own rule, and
            # only loads: ``IS`` insulation is a wire property, not a load.
            if card.i(0) == -1:
                loads.clear()
            else:
                loads.append(card)
        elif card.mnemonic == "MP":
            multiprocessing = Multiprocessing.from_card(card)
        elif card.mnemonic == "PT":
            print_control = PrintControl.from_card(card)
        elif card.mnemonic == "EX":
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
            # The dialect decided which execute cards run; this walk only has
            # to stay in step with it, one entry per execute card in order.
            armed = (
                model.groups[len(groups)] if len(groups) < len(model.groups) else None
            )
            prefixes.append(list(prefix))
            if armed is None:
                groups.append(None)
                continue
            groups.append(
                ExecuteGroup(
                    tuple(sources),
                    armed.frequencies,
                    refilled=armed.refilled,
                    report=None if card.mnemonic == "XQ" else card,
                    mp=multiprocessing,
                    pt=print_control,
                    ek=armed.extended_kernel,
                    refilled_partial=(
                        (armed.refilled_partial or operator_dirty)
                        and not armed.refilled
                    ),
                    ground=Ground.from_model(model.ground),
                    second_medium=second_medium,
                    momwire_ground=model.ground,
                )
            )
            operator_dirty = False
            executed += 1
            sources_stale = True

    if env_moves:
        _environments_per_group(groups, prefixes)

    return PortalDeck(
        comments=tuple(comments),
        geometry=tuple(geometry),
        data_cards=tuple(data_cards),
        groups=tuple(groups),
        loads=tuple(loads),
        ground=Ground.from_model(model.ground),
        second_medium=second_medium,
        ground_plane_flag=model.ground_plane_flag,
        quiet=model.quiet,
        reduced_field=model.reduced_field,
        model=model,
        structure=build_geometry(geometry),
    )


def _environments_per_group(
    groups: list[ExecuteGroup | None], prefixes: list[list[str]]
) -> None:
    """Give each group the ground its own execute card ran under, in place.

    ``GN`` is an arming card (spec ``#arming``, oracle-verified for #933): a
    deck may execute once in free space and once over ground, and each group
    answers over the cards that had reached it. ``momwire.deck``'s ``DeckModel``
    carries ONE ground for the whole deck, so the per-group value has to be
    recovered — and the honest way to recover it is to ask the same reader
    again, on the deck PREFIX that ends at this group's execute card, rather
    than to grow a second ``GN``/``GD`` reader here that could disagree with
    the first.

    Only the ground and the second medium are taken from a prefix parse.
    Everything else it computes is wrong on purpose: a prefix has only the
    ``EX`` cards that arrived before it, so its port set is a subset of the
    deck's, and the union set is what the one fill serves (spec
    ``#one-geometry-one-port-set``). Called only when a ``GN``/``GD`` actually
    arrives after an execute card, which is no deck in the reference corpus
    but ``dipole_gn_rearm``.
    """
    for index, group in enumerate(groups):
        if group is None:
            continue
        try:
            prefix_model = parse_dialect("\n".join(prefixes[index]), dialect="nec2")
        except DeckError:
            # A prefix that does not stand on its own (an execute card ahead
            # of every EX in the deck). The deck-level environment already on
            # the group is the best available reading, and the full parse
            # accepted the deck, so nothing is being hidden.
            continue
        group.ground = Ground.from_model(prefix_model.ground)
        group.second_medium = SecondMedium.from_model(prefix_model.second_medium)
        group.momwire_ground = prefix_model.ground


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

    These are ``FFLD``'s ``RRH`` and ``-RRV``, not the textbook Fresnel pair:
    they multiply the geometric image (horizontal components already flipped
    by :func:`_image_moments`), which is why perfect ground is ``(-1, +1)``
    here and ``RRV=RRH=-(1.,0.)`` in NEC. Algebraically identical — NEC writes
    the ratio ``ZRATI = 1./SQRT(EPSC)`` (theory manual eq. 179's ``Z_R``)
    where this writes ``q = sqrt(eps_c - sin²θ)``, and ``ZRATI*ZRSIN`` reduces
    to ``q/eps_c`` — but the sign convention is ours, and the mapping is the
    thing to check first if a reflected field ever comes out inverted.

    The pair is applied the way theory-manual eq. 181 composes them,
    ``E_R = R_V·E_I + (R_H - R_V)(E_I·p̂)p̂`` with ``p̂`` normal to the plane of
    incidence — ``FFLD``'s ``CDP=(TIX*PHX+TIY*PHY)*(RRH-RRV)`` lines.

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

    The comparison is ``FFLD``'s exactly, including its tie-break:
    ``IF ((CL-D).LE.0.) GO TO 15`` takes medium 2, so ``(CL - D) > 0`` keeps
    medium 1 and a point landing precisely ON the edge takes medium 2. The
    specular-point construction ``DR=Z(I)*TTHET`` / ``D=DR*PHY+X(I)`` /
    ``D=SQRT(D*D+(Y(I)-DR*PHX)**2)`` is that routine's, with ``TTHET=TAN(THET)``,
    ``PHX=-SIN(PHI)`` and ``PHY=COS(PHI)`` set at its head.

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
    and weighted after. That is ``FFLD``'s inner loop, vectorised — split the
    image carrier by :func:`_cliff_medium_2`, give each half its own
    ``(rho_h, rho_v)``, add.

    The far side also carries an extra phase. Its surface is ``CHT`` below
    medium 1's (signed, negative = lower), so its image sits ``2·CHT`` further
    along the vertical and the ray to it is ``2·CHT·cos(theta)`` longer:
    ``FFLD`` spells that ``DARG=-TP*2.*CH*ROZ`` (``TP`` = 2π, ``CH`` = ``CHT``
    in wavelengths, ``ROZ`` = cos θ) and adds it to the image phase, which is
    the same ``exp(-2jk·CHT·cosθ)`` applied here.
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
    # FFLD does not run through the Fresnel formula at all, and the second
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

    ``floor_scale`` converts the PRINTED field back to the amplitude ``FFLD``
    returned, which is the basis NEC's blank-column test is written in (see
    ``_FIELD_FLOOR2``). It is 1 for a table read out at the wavelength's own
    scale and ``RFLD/lambda`` for one read out at a range; everything else
    here is scale-free, so it reaches the floor test and nothing more.

    With ``a = |E_theta|``, ``b = |E_phi|`` and ``δ = arg(E_phi) - arg(E_theta)``
    wrapped to ±180°, the ellipse semi-axes are
    ``0.5·[a²+b² ± sqrt(a⁴+b⁴+2a²b²cos2δ)]`` and the tilt is
    ``½·atan2(2ab·cosδ, a²-b²)`` — the same pair ``RDPAT`` forms as
    ``TILTA=.5*ATGN2(TSTOR2,TSTOR1)``.
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

    This is NEC's ``DB10``: ``X < 1.D-20 -> -999.99``, applied to the LINEAR POWER
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
    matrix and the per-port basis-coefficient columns behind it — momwire's
    public ``compute_port_solution()`` (momwire#232, momwire 0.24.0).

    Until 0.24.0 this function was a four-branch dispatch keyed on each
    family's private port algebra: verbatim copies of the Galerkin and
    point-matched Y paths, plus an instance-level dual spy on
    ``_solve_with_kcl_ports`` / ``_solve_hmatrix`` for the spline families —
    the private-API debt momwire#232 tracked. The public API returns the same
    ``(y, coeffs)`` pair from the same one-fill-all-ports solve; the swap was
    verified bit-identical on all four branches before landing (momwire
    PR #250's sufficiency check: dY = dX = 0 exactly, and this repo's
    420-test portal battery passed unchanged against it).

    Family refusals (the point-matched junction-port span rule, Galerkin
    junction ports over finite ground) surface from momwire with the same
    exception types and messages the branches raised — pinned momwire-side
    in ``tests/test_port_solution.py``.
    """
    sol = solver.compute_port_solution()
    return sol.y, sol.coeffs


def _union_ports(deck: PortalDeck) -> list[tuple[int, int]]:
    """Every ``(tag, segment)`` the deck drives, in discovery order: the union
    of every execute group's ``EX`` segments.

    This is the dialect's own union rule (spec ``#one-geometry-one-port-set``)
    read in NEC's vocabulary, and it is the bridge between the two: entry ``i``
    here is model feed ``i``, so ``PortPlan.feed_ports[i]`` is the solver port
    the ``ANTENNA INPUT PARAMETERS`` row for ``(tag, seg)`` reads.

    Lifted out of :class:`DeckSolver` so the cross-deck cache key is built from
    the SAME walk the solver's port columns come from.
    """
    ports: list[tuple[int, int]] = []
    for group in deck.groups:
        if group is None:
            continue
        for tag, seg, _v in group.sources:
            if (tag, seg) not in ports:
                ports.append((tag, seg))
    return ports


def _series_rlc_impedance(r, l, c, omega):  # noqa: E741 — NEC's own field name
    """Series R + jwL + 1/(jwC). Any of r/l/c may be None (omitted term).

    COPIED, not imported, from ``antennaknobs.network._series_rlc_impedance``
    (#846: the portal depends on momwire alone). Twenty-six lines with zero
    module dependencies, minus the finite-Q terms, which no NEC ``LD`` card can
    ask for: the card gives R, L and C and nothing else. The original stays
    where it is and serves the design library; this one serves ``LD 0``.
    """
    z = 0.0 + 0.0j
    if r is not None:
        z += r
    if l is not None:
        z += 1j * omega * l
    if c is not None:
        z += 1.0 / (1j * omega * c)
    return z


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


# "the deck's own ground", as a default distinct from None (free space).
_UNSET = object()


def _port_signs(built, model) -> np.ndarray:
    """``d_k = ±1`` per solver port: the deck's sign convention over momwire's.

    A delta-gap feed's polarity follows the direction the polyline WALK ran
    through its edge, and the walk is free to traverse a wire against the
    p1→p2 direction the ``GW`` card authored (a mid-structure feed on a chain
    assembled from both ends is the routine case — five of the reference
    corpus's decks hit it). NEC's convention is the card's, so every port is
    normalised back onto it by the diagonal congruence ``Y_deck = D·Y_walk·D``
    with the matching ``V_walk = D·V_deck`` on the applied voltages. Both are
    exactly what ``MomwireEngine._contract_y`` / ``_feed_W`` did before #846
    phase II; the difference is that this reads the sign off the built mesh
    rather than off a private engine attribute.

    ``momwire.deck``'s :class:`~momwire.deck._solver.PortPlan` does not carry
    the walk direction (``_polylines.py`` computes it and keeps it), so it is
    recovered here from the geometry: the polyline edge the port sits on
    against the model wire the plan says the port belongs to.
    """
    signs = np.ones(built.ports.n_ports)
    polylines = built.solver.wires_polylines
    for index, site in enumerate(built.ports.sites):
        polyline = np.asarray(polylines[built.solver.feeds[index][0]], dtype=float)
        arclength = built.solver.feeds[index][1]
        lengths = np.linalg.norm(np.diff(polyline, axis=0), axis=1)
        edge = int(np.searchsorted(np.cumsum(lengths), arclength, side="left"))
        edge = min(edge, len(lengths) - 1)
        walk = polyline[edge + 1] - polyline[edge]
        wire = model.wires[site.wire]
        authored = np.asarray(wire.vertices[-1], dtype=float) - np.asarray(
            wire.vertices[0], dtype=float
        )
        signs[index] = 1.0 if float(np.dot(walk, authored)) >= 0.0 else -1.0
    return signs


class DeckSolver:
    """momwire behind one deck: one geometry, one fill per frequency.

    The construction is ``momwire.deck``'s (#846 phase II): the dialect parsed
    the deck into a :class:`~momwire.deck.model.DeckModel`, and
    :func:`~momwire.deck.build_solver` maps that model onto a solver family
    plus the :class:`~momwire.deck._solver.PortPlan` that says what its ports
    MEAN. This class is what sits between that plan and the printout — the
    NEC-facing half nothing in momwire speaks: global segment numbers, tags,
    the deck's own current sign convention, and the port algebra that stamps a
    load.

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
        self.model = deck.model
        self.structure = deck.structure
        self.ports = _union_ports(deck)
        if not self.ports:
            raise PortalError("deck has no EX card — nothing drives the structure")

        # The flat NEC wire list after every GM/GS transform and both
        # connection passes: tags, segment counts, endpoints, radii. This is
        # the structure every table in the printout is addressed against.
        self.wires = self.structure.wires
        self.segments = _structure_segments(self.wires)
        self.n_segments = len(self.segments)

        self._group = next(
            (i for i, g in enumerate(self.model.groups) if g is not None), None
        )
        # The operating point the first real run asks for. Building the seed
        # solver here rather than lazily keeps the port plan available before
        # anything is printed, exactly as the engine's translation used to be.
        armed = next((g for g in deck.groups if g is not None), None)
        seed = armed.freqs_mhz[0] if armed else 0.0
        seed_ek = bool(armed.ek) if armed else False
        seed_ground = armed.momwire_ground if armed else self.model.ground
        self._smallest_radius = min(w.radius for w in self.wires)
        # (frequency, extended kernel, ground) -> one filled and factored
        # operator. The ground is in the key because GN arms (#933).
        self._cache: dict[tuple, dict] = {}

        built = self._build(seed, seed_ek, seed_ground)
        plan = built.ports
        self.plan = plan
        self.n_ports = plan.n_ports
        # Port index in the solver's ordering, per union EX port and per
        # translated LD port — the plan's own bridge, in the model's feed and
        # load order, which is this walk's order by construction.
        self.feed_index: list[int] = list(plan.feed_ports)
        self.load_ports: list[tuple[int, object]] = [
            (port, spec) for port, spec in plan.loaded_ports()
        ]
        # Global NEC segment number → solver port index, for every segment
        # that carries a gap. Lets a readout prefer the Galerkin port current
        # (what Y is built from) over the interpolated midpoint current.
        self.port_by_segment: dict[int, int] = {
            self.global_segment(*self.structure.locate(tag, seg)): port
            for (tag, seg), port in zip(self.ports, self.feed_index)
        }
        # Whether any wire carries a material at all — the gate on the wire
        # loss term of the power budget (``LD 5`` conductivity, ``IS``
        # insulation). ``momwire.deck`` folds both into the model's per-wire
        # material record.
        self._lossy = any(w.material is not None for w in self.model.wires)
        self._cache[(seed, seed_ek, seed_ground)] = self._entry(built)

    # -- construction ------------------------------------------------------

    def _build(self, freq_mhz: float, extended_kernel: bool, ground):
        """One constructed solver plus its port plan, at one operating point.

        ``ground`` is the group's, not the deck's — ``GN`` arms, so two groups
        of one deck may sit over two different half-spaces (#933). It is
        stamped onto the model with ``dataclasses.replace``, which is exactly
        what the frozen model is for: same wires, same feeds, same loads, same
        union port set, one different ground.
        """
        model = self.model
        if ground != model.ground:
            model = replace(model, ground=ground)
        return build_solver(
            model,
            basis=_active_basis_name,
            group=self._group,
            frequency_mhz=freq_mhz,
            extended_kernel=bool(extended_kernel),
        )

    def _entry(self, built) -> dict:
        """The cached ``(Y, X, solver)`` behind one constructed solver."""
        if _cache_serving or _cache_stats_path is not None:
            # Counted only when something asked to be measured: with the cache
            # off the instrument is off too, so its zeros are evidence rather
            # than an unread accumulator. Counted HERE rather than at `at()`'s
            # miss because the deck's first operating point is filled during
            # construction, and a fill is a fill wherever it is asked for.
            _cache_stats["fills"] += 1
        started = time.perf_counter()
        y_solver, coeffs = _y_and_port_coeffs(built.solver)
        fill_ms = int(round((time.perf_counter() - started) * 1000.0))
        signs = _port_signs(built, self.model)
        return {
            "solver": built.solver,
            "wavelength": built.wavelength,
            # Y in the DECK's sign convention (see ``_port_signs``): the
            # diagonal congruence D·Y·D that puts every port back on the
            # direction its NEC wire was authored in.
            "Y": y_solver * signs[:, None] * signs[None, :],
            "X": coeffs,
            "signs": signs,
            "fill_ms": fill_ms,
        }

    def global_segment(self, wire: int, local: int) -> int:
        """NEC's absolute segment number for 1-based local segment ``local``
        of ``self.wires[wire]``."""
        return sum(w.n_seg for w in self.wires[:wire]) + local

    # -- per-frequency operator -------------------------------------------

    def at(self, freq_mhz: float, extended_kernel: bool = False, ground=_UNSET) -> dict:
        """The cached (Y, X, solver) for a frequency — one fill, one factor.

        When this instance came out of the cross-deck cache (``_solver_for``)
        these entries came with it, so a re-probed deck answers with no fill at
        all, and the same structure at a NEW frequency pays one fill on top of
        a geometry parse and mesh it did not repeat.

        ``extended_kernel`` is the group's ``EK`` (issue #849) and is part of
        the cache key, not just of the fill: ``dipole_ek_rearm`` is one deck
        whose two execute groups ask for two different kernels at the SAME
        frequency, so keying on the frequency alone would answer the second
        from the first's operator. The key is written ``(freq, ek)`` rather
        than as two dicts so that adding a third operator axis later cannot
        forget one of them.
        """
        if ground is _UNSET:
            ground = self.model.ground
        key = (freq_mhz, bool(extended_kernel), ground)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        entry = self._entry(self._build(freq_mhz, extended_kernel, ground))
        self._cache[key] = entry
        return entry

    def _load_impedances(self, omega: float) -> np.ndarray:
        """The per-port load impedance vector at one angular frequency.

        The plan says which solver port each ``LD`` card landed on and hands
        over its :class:`~momwire.deck.model.LoadSpec`; stamping it is the
        consumer's job, because the load is an impedance in the port's own
        current path rather than anything the fill knows about.
        """
        z = np.zeros(self.n_ports, dtype=np.complex128)
        for idx, ld in self.load_ports:
            if ld.kind == "fixed":
                z[idx] += complex(ld.r, ld.x)
            elif ld.kind == "parallel":
                y = 0.0 + 0.0j
                if ld.r:
                    y += 1.0 / ld.r
                if ld.l:
                    y += 1.0 / (1j * omega * ld.l)
                if ld.c:
                    y += 1j * omega * ld.c
                z[idx] += (1.0 / y) if y != 0 else 0.0
            else:
                z[idx] += _series_rlc_impedance(
                    ld.r or None, ld.l or None, ld.c or None, omega
                )
        return z

    def solve_group(self, group: ExecuteGroup, freq_mhz: float) -> dict:
        """One execute group at one frequency: port currents, segment
        currents, and the power budget — all from the cached factorisation.

        The group's ``EK`` picks the operator (issue #849), so two groups of
        one deck under two kernels get two fills and two answers."""
        entry = self.at(freq_mhz, extended_kernel=group.ek, ground=group.momwire_ground)
        omega = 2.0 * math.pi * freq_mhz * 1e6
        y = entry["Y"]
        v_source = np.zeros(self.n_ports, dtype=np.complex128)
        driven: list[tuple[int, int, complex]] = []  # (port idx, global seg, V)
        for (tag, seg), port in zip(self.ports, self.feed_index):
            for s_tag, s_seg, volts in group.sources:
                if (s_tag, s_seg) == (tag, seg):
                    v_source[port] = volts
                    wire, local = self.structure.locate(tag, seg)
                    driven.append((port, self.global_segment(wire, local), volts))
        z_load = self._load_impedances(omega)
        system = np.eye(self.n_ports, dtype=np.complex128) + (z_load[:, None] * y)
        v_gap = np.linalg.solve(system, v_source)
        i_port = y @ v_gap
        # No network branch can reach this engine: ``TL`` and ``NT`` are
        # refused by name (the dialect is antenna-only), so the source current
        # IS the segment current and the network loss is identically zero.
        i_source = i_port

        coeffs = entry["X"] @ (entry["signs"] * v_gap)
        seg_currents = self._segment_currents(entry["solver"], coeffs)

        p_in = 0.5 * float(
            sum((volts * np.conj(i_source[p])).real for p, _s, volts in driven)
        )
        p_load = 0.5 * float(np.sum(np.real(z_load) * np.abs(i_port) ** 2))
        p_wire = 0.0
        if self._lossy:
            p_wire = float(entry["solver"].wire_loss_power(coeffs)[0])
        p_structure = p_load + p_wire
        p_rad = p_in - p_structure
        return {
            "driven": driven,
            "v_gap": v_gap,
            "i_port": i_port,
            "i_source": i_source,
            "segment_currents": seg_currents,
            "coeffs": coeffs,
            "solver": entry["solver"],
            "p_in": p_in,
            "p_structure": p_structure,
            "p_network": 0.0,
            "p_radiated": p_rad,
            "efficiency": (100.0 * p_rad / p_in) if p_in > 0 else 0.0,
            "fill_ms": entry["fill_ms"],
            "wavelength": entry["wavelength"],
            # The environment this group ran under, so every readout below the
            # solve reads the same half-space the fill did (#933).
            "ground": group.ground,
            "ground_z": self.model.ground_z if group.momwire_ground else None,
            "second_medium": group.second_medium,
        }

    # -- field sources -----------------------------------------------------

    def current_elements(self, result: dict, subdiv: int = 1):
        """``(mid, moment, nodes, delta)`` for the whole structure — momwire's
        own ``element_currents``.

        The portal carried a near-verbatim duplicate of this walk until #846
        phase II (same mesh walk, same moments, same steps); momwire ships it
        publicly, so the copy is gone and only the deck-direction re-signing
        below — which is NEC's convention, not momwire's — stays here.
        """
        return result["solver"].element_currents(result["coeffs"], subdiv=subdiv)

    def _segment_currents(self, solver, coeffs) -> np.ndarray:
        """Per NEC segment (global order), the midpoint current signed along
        the deck's own p1→p2 direction.

        momwire walks the translated polylines in its own direction, so a
        segment the walker traversed backwards carries the opposite current
        sign; the dot product against the deck wire's direction puts every
        segment back on NEC's convention.
        """
        knot_currents = solver.currents_at_knots(coeffs)
        mids, dirs, vals = [], [], []
        for w_idx, polyline in enumerate(solver.wires_polylines):
            parts = []
            for i, n_e in enumerate(solver.n_per_edge_per_wire[w_idx]):
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
        # fall back to pure distance if nothing does.
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
# the cross-deck solver cache
# --------------------------------------------------------------------------
#
# The protocol is stateless per deck — every deck re-sends its whole geometry
# and a sweep arrives as N independent decks — but nothing in it forbids the
# ENGINE remembering. ``DeckSolver`` already caches (geometry, frequency) →
# factors WITHIN a deck; this keeps the whole ``DeckSolver`` across decks, so a
# re-probed structure reuses the parse, the mesh, the port maps, the network
# rows AND the per-frequency fills, and the same structure at a new frequency
# pays only the new fill (issue #823).
#
# What a hit must guarantee is that the cached instance is the operator the
# arriving deck asks for. That makes the key the whole contract: it is built
# from the parsed deck rather than its text (so comments, whitespace and card
# formatting cannot split it) and it carries EVERYTHING that moves a number in
# the operator — see ``_operator_key``.
#
# Serving is opt-in (``--cache``) and off by default; ``--cache-stats PATH``
# measures the hit rate a live session would see without serving anything.
# ``_solver_for`` is where the three modes part company.

# A few hundred MB is inside the machine budget for a crew of four engines, and
# the cache degrades to exactly the pre-#823 behaviour when it is full (every
# arrival misses and re-solves). It is a SAFETY NET rather than a working
# limit: momwire drops the factored operator after its solve, so what an entry
# retains is X (n_basis × n_ports per cached frequency) and the solver's own
# geometry — the whole bench corpus MEASURES at 44 to 111 kB an entry, which is
# thousands of structures before the cap binds. It bites where it should, on
# array-scale meshes. Deliberately a constant and not a knob: a per-process
# daemon with a tunable memory cap is a support surface nobody asked for.
_CACHE_BYTES_CAP = 384 * 1024 * 1024

# operator key → the solver built for it, least-recently-used first.
_solver_cache: OrderedDict[tuple, DeckSolver] = OrderedDict()

# operator key → its last measured size in bytes. Kept alongside rather than
# recomputed per sweep because sizing an entry costs a graph walk (~1 ms) and
# only ONE entry can have grown since the last arrival: the one the previous
# deck rendered through. Re-walking the whole cache per deck would put the
# eviction pass in front of the physics it exists to save.
_cache_sizes: dict[tuple, int] = {}

# The instrument. Tests read these instead of parsing timing text — the point
# of the cache is that the printout is IDENTICAL either way, so the printout
# cannot be the evidence. Nothing here is ever printed to SimNEC.
_cache_stats = {"hits": 0, "misses": 0, "evictions": 0, "fills": 0, "bytes": 0}

# Serving is OFF unless the portal-dialog command line asks for it (``--cache``).
# The cache is an optimisation for a workload nobody has measured yet: a live
# SimNEC session's real re-probe rate is an empirical question, and until it is
# answered the default has to be the behaviour that has been shipped and
# validated. `--cache-stats PATH` answers it at zero risk — see `_solver_for`.
_cache_serving = False
_cache_stats_path: str | None = None

# The keys seen this invocation in DRY-RUN mode. A key-set, never solvers: the
# point of the dry run is to measure the hit rate without retaining a single
# byte of physics, so there is no memory growth and no way for a stale answer
# to be served by a mode that is only supposed to be counting.
_dry_run_keys: set[tuple] = set()

# Decks framed this invocation — the DENOMINATOR of the hit rate, and not a
# cache statistic: a refused deck moves nothing in `_cache_stats` but is still
# a deck the session sent.
_decks_rendered = 0


def _cache_mode() -> str:
    """``serving`` / ``dry-run`` / ``off`` — what the command line asked for."""
    if _cache_serving:
        return "serving"
    return "dry-run" if _cache_stats_path is not None else "off"


def _reset_solver_cache() -> None:
    """Empty the cache and zero the instrument. Called by ``main`` for the same
    reason it re-reads ``--basis``: engine state is per invocation, never
    sticky, and a fresh process must be indistinguishable from a fresh call."""
    global _decks_rendered
    _solver_cache.clear()
    _cache_sizes.clear()
    _dry_run_keys.clear()
    _decks_rendered = 0
    for key in _cache_stats:
        _cache_stats[key] = 0


def _write_cache_stats() -> None:
    """The measurement file, rewritten after EVERY deck.

    After every deck because SimNEC ends a session with ``Process.destroy()``
    — a kill, not an EOF — so an exit-time write is a write that never happens.
    The file is tiny (one flat object), so the cost is a few hundred bytes of
    I/O against seconds of physics, and it goes out through a temp file and a
    rename so a reader never catches a half-written object.

    Read it as: ``hits`` is the answer to "would a cache have helped" —
    decks whose operator had already been solved in this session. In dry-run
    mode ``fills`` is what the stock engine actually paid, so ``hits`` against
    ``decks_rendered`` is the saving on offer; ``entries`` and ``bytes`` are
    zero there because nothing is retained.

    Failures are swallowed on purpose. This engine may write NOTHING to stdout
    (it would corrupt the transcript) and nothing to stderr (NEC2Daemon never
    drains it, so a full pipe buffer deadlocks the UI — grammar doc §10.9), so
    an unwritable path can only be allowed to cost the measurement, never the
    session.
    """
    if _cache_stats_path is None:
        return
    payload = {
        "mode": _cache_mode(),
        "decks_rendered": _decks_rendered,
        "hits": _cache_stats["hits"],
        "misses": _cache_stats["misses"],
        "fills": _cache_stats["fills"],
        "evictions": _cache_stats["evictions"],
        "bytes": _cache_stats["bytes"],
        "entries": len(_solver_cache),
    }
    tmp = f"{_cache_stats_path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
            handle.write("\n")
        os.replace(tmp, _cache_stats_path)
    except OSError:
        pass


def _operator_key(deck: PortalDeck) -> tuple:
    """The identity of the linear operator this deck describes.

    Read off the parsed :class:`~momwire.deck.model.DeckModel` rather than off
    the cards, because the model IS the operator's statement: the wires the
    fill runs over (vertices, radii, per-edge element counts and each wire's
    material — a ``LD 5`` conductivity or an ``IS`` jacket lands in the fill),
    the ground, the port set in order, and the loads whose gaps the fill has
    to cut. Two decks that differ only in spelling produce the same model and
    therefore the same key.

    Everything that changes the matrix, the drive columns, or their ordering:

    * the wires — geometry after every ``GM``/``GS`` transform, both
      connection passes and the junction shatter;
    * the ground — kind and constants, and its ABSENCE (free space is a
      distinct value, not a missing one), plus the plane's height;
    * the loads — position and :class:`~momwire.deck.model.LoadSpec`, which is
      the set ``_load_impedances`` stamps and the set that cuts gaps;
    * the port set, in order — the model's own feed union;
    * the kernel flag, per execute group — see below;
    * the basis: solver class, solver kwargs and banner suffix. One process has
      one ``--basis``, so this can never differ between two live decks; it is in
      the key anyway because a self-contained key cannot be read wrong.

    Deliberately NOT in the key, because none of them move the operator:

    * ``FR`` — frequency is the key of ``DeckSolver.at``, one level down. Two
      decks alike but for their ``FR`` SHARE this entry and that is the point.
    * ``EX`` VOLTAGES — X's columns are per-1 V and the voltage applies at
      readout (``solve_group``). Only an EX's PLACEMENT is in the key, via the
      port set.
    * ``RP``/``NE``/``NH``/``PT``/``XQ``/``MP`` — readout and print
      control, computed from the result after the solve.
    * ``CM``/``CE`` comments, and card formatting — the key is built from the
      parsed deck, so a re-sent deck that differs only in whitespace hits.
    * ``GD`` — the second medium reaches NEC's far field only through ``RP``'s
      cliff modes and moves nothing in the operator (grammar doc §12.6). It is
      excluded so a GD knob-drag HITS, which is safe because a hit rebinds
      ``portal_deck`` to the arriving deck (``_solver_for``): no cached
      instance ever carries a stale ``GD``, whatever a later far-field path
      chooses to read. ``test_a_gd_card_change_hits_and_still_answers_fresh``
      is the proof, and it compares against a FRESH PROCESS rather than
      against itself, so it stays a proof if ``GD`` ever grows a far field.

    ``EK`` used to be the conservative entry — kept on the argument that a
    card whose whole meaning is "compute the operator differently" must never
    be answered from an entry built without it, even while momwire had no
    other kernel to build with. Since issue #849 it is an ordinary one: the
    flag IS the operator now (``DeckSolver.at`` fills per kernel), and a wrong
    hit here would serve a reduced-kernel answer to a deck that asked for the
    extended one. The tuple stays per GROUP, because that is the granularity
    the card has.
    """
    cls, kwargs, suffix = _active_basis
    model = deck.model
    return (
        model.wires,
        # The ground: kind, constants, the plane's height — and the GE flag,
        # which specifies no ground at all (the physics is GN's alone) and is
        # kept in the key for the same reason it was before the rewire: a deck
        # whose wire touches the plane would move both, and a self-contained
        # key cannot be read wrong. The PER-GROUP grounds ride alongside it,
        # because GN arms (#933) and a cached instance carries one filled
        # operator per (frequency, kernel, ground).
        (model.ground, model.ground_z, model.ground_plane_flag),
        tuple(g.momwire_ground for g in deck.groups if g is not None),
        model.loads,
        tuple((wire, arclength) for wire, arclength, _volts in model.feeds),
        tuple(g.ek for g in deck.groups if g is not None),
        (cls.__name__, tuple(sorted(kwargs.items())), suffix),
    )


def _resident_bytes(root: object, limit: int = 50_000) -> int:
    """A cache entry's honest size: every distinct object reachable from it,
    numpy arrays at their ``nbytes`` and everything else at ``getsizeof``.

    Walked rather than computed because the entry's cost is not one formula:
    ``X`` is ``n_basis × n_ports`` complex128 per cached frequency, ``Y`` is
    small, and whatever the momwire solver retains after its solve (geometry,
    basis polynomials, any factor it holds) is momwire's business and changes
    between releases. The per-object term is in there because it MEASURES as
    the bigger half — a mid-size fixture's entry is ~30 kB of array against
    ~900 Python objects — so an arrays-only estimate would let the cache hold
    several times the memory the cap names.

    Distinct objects only (id-keyed), and the object count is bounded: this is
    accounting, not a measurement, and it runs once per cached deck.
    """
    seen: set[int] = set()
    total = 0
    stack: list[object] = [root]
    while stack and len(seen) < limit:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        if isinstance(obj, np.ndarray):
            total += obj.nbytes
            continue
        total += sys.getsizeof(obj)
        if isinstance(obj, dict):
            stack += list(obj.values())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            stack += list(obj)
        elif hasattr(obj, "__dict__"):
            stack += list(vars(obj).values())
    return total


def _cache_measure(key: tuple) -> None:
    """(Re)size one entry. An entry GROWS after it is stored — every new
    frequency adds an ``at()`` fill to the instance the cache is holding — so
    the size taken at insertion drifts low exactly on the sweep the cache
    exists to serve, and the entry that just rendered is re-walked."""
    solver = _solver_cache.get(key)
    if solver is not None:
        _cache_sizes[key] = _resident_bytes(solver)


def _cache_evict() -> None:
    """Drop least-recently-used entries until the estimate is under the cap.

    The most recent entry is never evicted: one structure too big for the cap
    should still answer its own second execute group from its own factors,
    which is what a cache that "degrades to today's behaviour" means — a full
    cache costs a re-solve per arrival and nothing else.
    """
    total = sum(_cache_sizes.values())
    while total > _CACHE_BYTES_CAP and len(_solver_cache) > 1:
        key, _solver = _solver_cache.popitem(last=False)
        total -= _cache_sizes.pop(key, 0)
        _cache_stats["evictions"] += 1
    _cache_stats["bytes"] = total


def _solver_for(deck: PortalDeck) -> DeckSolver:
    """The :class:`DeckSolver` for this deck, in whichever of the three modes
    the command line asked for.

    **off** (the default). A fresh solver, and nothing else happens: no key is
    computed, no counter moves, no reference is kept. This branch is the
    pre-#823 code path to the byte, which is the point — the cache is opt-in
    until a live session says it earns its keep, and "opt-in" has to mean the
    default costs nothing rather than costs a little.

    **dry-run** (``--cache-stats PATH`` alone). The key IS computed and
    counted against the keys already seen, so the stats file answers "how many
    of this session's decks would a cache have served" — but the solver is
    built fresh every time and never retained. Nothing can be served from a
    mode that is only measuring, and the process grows no memory for it. This
    is the zero-risk live experiment.

    **serving** (``--cache``). The cached instance when its operator has been
    seen, a fresh one otherwise.

    A hit rebinds ``portal_deck`` to the ARRIVING deck. Everything the cached
    instance derived from the old one is in the key and therefore identical,
    but the attribute is a live reference the printout reads through
    (``_pattern_lines``, ``_near_field_lines``), and the arriving deck is the
    honest answer to "which deck is being rendered" for anything read from it
    later — the ``GD`` exclusion above rests on exactly this, and #842's cliff
    modes made it load-bearing.

    The cap is enforced in the serving branch, at deck arrival: the entry the
    PREVIOUS deck rendered through is re-sized (its fills are done now), the
    arriving deck's entry is sized or created, and the oldest go. So the deck
    about to be rendered is always resident, and the overshoot is one deck's
    worth of new frequencies.
    """
    if not _cache_serving:
        if _cache_stats_path is None:
            return DeckSolver(deck)
        key = _operator_key(deck)
        # Construction first here too, so a refused deck moves no statistic in
        # dry-run either — the counts stay comparable with serving mode's.
        solver = DeckSolver(deck)
        if key in _dry_run_keys:
            _cache_stats["hits"] += 1
        else:
            _cache_stats["misses"] += 1
            _dry_run_keys.add(key)
        return solver

    if _solver_cache:
        _cache_measure(next(reversed(_solver_cache)))
    key = _operator_key(deck)
    cached = _solver_cache.get(key)
    if cached is not None:
        _cache_stats["hits"] += 1
        _solver_cache.move_to_end(key)
        cached.portal_deck = deck
        _cache_evict()
        return cached
    # Construction first, and the counter after it: a deck this engine refuses
    # raises here and moves NOTHING — no entry, no statistic — so a refusal is
    # neither served from the cache nor recorded in it.
    solver = DeckSolver(deck)
    _cache_stats["misses"] += 1
    _solver_cache[key] = solver
    _cache_measure(key)
    _cache_evict()
    return solver


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
    second = result["second_medium"]
    mid, moment, _nodes, _delta = solver.current_elements(result)
    m_theta, m_phi = _far_moments(
        mid,
        moment,
        k,
        np.radians(thetas),
        np.radians(phis),
        result["ground"],
        result["ground_z"],
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
    # The printed field over the amplitude FFLD returns, which is the basis
    # NEC's blank-SENSE threshold is written in.
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

    ``RDPAT`` prints this for any mode above 1 (``IF (IFAR.LT.2) GO TO 2``),
    whether or not there is a
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
    ground = result["ground"]
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
        ground_z = result["ground_z"]
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
    first = solver.global_segment(*solver.structure.locate(pt.tag, pt.first))
    last = solver.global_segment(*solver.structure.locate(pt.tag, pt.last))
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
        out += _environment_lines(group.ground, freq_mhz)
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
    except _DECK_REFUSALS as exc:
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
        solver = _solver_for(deck)
    except PortalError as exc:
        _append_error(out, exc)
        return out, err
    except (ValueError, NotImplementedError, np.linalg.LinAlgError) as exc:
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
        except (
            PortalError,
            ValueError,
            # A basis that cannot serve this group's kernel (issue #849 —
            # since momwire 0.27.0 the only such combination is EK with
            # singular enrichment; the Galerkin refusal fell with
            # momwire#246/#287/#299). It is a refusal SimNEC must see as a NEC
            # ERROR, not as a daemon traceback that costs the deck its NX
            # sentinel.
            NotImplementedError,
            np.linalg.LinAlgError,
        ) as exc:
            _append_error(out, exc)
        out += ["", "", ""]
    return out, err


def deck_frame(body: str, terminator: str = "NX") -> tuple[list[str], list[str]]:
    """One deck's stdout frame: printout, the ``NX`` sentinel, trailing banner.

    Card numbering restarts at 1 inside every deck, so the sentinel's ordinal
    is the deck's own card count plus one (grammar doc §1).

    This is also the frame boundary the measurement file is written at (a deck
    is done, its fills are paid), and the boundary a REFUSED deck still counts
    at — it is a deck the session sent, so it belongs in the denominator.

    ``terminator="EN"`` is the standalone variant (#901): the echo names the
    card that actually arrived, and the trailing banner is omitted — genuine
    nec2c reprints its banner only at NX, in anticipation of a next deck that
    EN says will never come.
    """
    global _decks_rendered
    out, err = render_deck(body)
    echoed = sum(1 for line in out if line.startswith("  DATA CARD No:"))
    out.append(fmt_data_card(echoed + 1, Card(terminator, (), terminator)))
    if terminator == "NX":
        # The oracle reprints its banner right after consuming NX, in
        # anticipation of the next deck; SEEKING ignores it. Reproduced so a
        # resident transcript frames identically (grammar doc §1, §10.8).
        out += list(_banner_lines()[1:])
    _decks_rendered += 1
    _write_cache_stats()
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
    # A free-space dipole, the two-source Y probe, a loaded parasitic pair,
    # and a grounded vertical carrying GD — the four deck shapes a live SimNEC
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
    "GE 0\n"
    "EX 0 1 6 0 1.\nFR 0 1 0 0 14.0 1\nXQ\n"
    "EX 0 2 6 0 1.\nFR 0 1 0 0 14.0 1\nXQ\nNX\n",
    # Deck 3 carried a TL station until #930 made TL out of dialect (the
    # engine is antenna-only, and a network deck goes to antennaknobs'
    # importer). What it was really smoking out is a MULTI-WIRE deck with a
    # port on a parasitic element, so it keeps that and takes an LD load —
    # the other card whose port algebra runs outside the fill.
    "CE selftest 3\n"
    "GW 1 11 0. -5. 10. 0. 5. 10. 0.001\n"
    "GW 2 3 20. -0.5 10. 20. 0.5 10. 0.001\n"
    "GE 0\nLD 0 1 6 6 25. 0. 0.\n"
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
        "LD loading row present": "SERIES" in proc.stdout,
        "stderr quiet": proc.stderr.strip() == "",
    }

    # One deck per alternate basis: the point is that the entry is wired and
    # answers on THIS box, not that it is fast or converged. The selftest deck
    # is a single small dipole, which for `hmatrix`/`arrayblock` means a
    # near-field-only operator and (for arrayblock) a degenerate element
    # partition that degrades to the parent — the graceful-degradation path,
    # which is exactly the one a smoke test wants to prove never raises.
    def _alt(basis: str, deck: str):
        return subprocess.run(
            [sys.executable, "-m", "antennaknobs.nec_portal", "--basis", basis],
            input=deck,
            capture_output=True,
            text=True,
            timeout=120,
        )

    for basis, suffix in (
        ("sinusoidal", "+sin"),
        ("bspline-d1", "+bs1"),
        ("hmatrix", "+hm"),
        ("arrayblock", "+ab"),
    ):
        alt = _alt(basis, _SELFTEST_DECKS[0])
        checks[f"alt basis answers ({suffix})"] = (
            alt.returncode == 0
            and suffix in alt.stdout
            and "ANTENNA INPUT PARAMETERS" in alt.stdout
        )
    # The Galerkin entries used to be the exception: until momwire 0.27.0 the
    # Galerkin fill refused NEC's extended kernel, and deck 1 carries `EK`
    # precisely because the live NECSource path always sends it, so this check
    # gated the DOCUMENTED refusal frame. momwire#246/#287/#299 implemented
    # the kernel on the Galerkin family (every ground model, non-collinear
    # decks included), so the same two-deck, one-process probe now proves the
    # positive statement: the EK deck ANSWERS, the plain deck answers after it
    # from the same resident engine, and both sentinels survive. Keeping both
    # decks (with and without the card) preserves the session-survival half of
    # the old gate — a traceback on either would cost its NX sentinel.
    galerkin = _alt(
        "sinusoidal-galerkin-converged",
        _SELFTEST_DECKS[0] + _SELFTEST_DECKS[0].replace("EK\n", ""),
    )
    sentinels = sum(
        1
        for ln in galerkin.stdout.splitlines()
        if ln.lstrip().startswith("DATA CARD No:") and " NX " in ln
    )
    checks["galerkin serves EK, session survives"] = (
        galerkin.returncode == 0
        and not any(ln.split()[:1] == ["ERROR:"] for ln in galerkin.stdout.splitlines())
        and sentinels == 2
        and "+sgc" in galerkin.stdout
        and galerkin.stdout.count("ANTENNA INPUT PARAMETERS") == 2
    )
    for name, ok in checks.items():
        stdout.write(f"  {'ok  ' if ok else 'FAIL'} {name}\n")
    passed = all(checks.values())
    stdout.write("PASS\n" if passed else "FAIL\n")
    stdout.flush()
    return 0 if passed else 1


def main(argv: list[str] | None = None, stdin=None, stdout=None, stderr=None) -> int:
    """The daemon. ``-version`` probes; otherwise read decks until stdin ends.

    Decks are framed on stdin by an ``NX`` card — no length prefix, no
    sentinel of our own — and the process is never restarted between them
    (``NEC2Daemon.submit``). ``EN`` also terminates a frame but then ends the
    run, so an unmodified ``.nec`` file redirected in solves and exits (#901);
    SimNEC itself never sends it. A body left unterminated at EOF is discarded
    with a stderr warning naming the framing rule.
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
    global _active_basis, _active_basis_name, _cache_serving, _cache_stats_path
    _active_basis = _BASES["bspline"]  # per-invocation default, never sticky
    _active_basis_name = "bspline"
    # The cross-deck cache and its two flags are per invocation for the same
    # reason, and the cache also because entries built under one basis must not
    # outlive it (the key carries the basis, so they could not be served anyway
    # — this just stops them occupying the cap).
    _cache_serving = False
    _cache_stats_path = None
    _reset_solver_cache()
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
        _active_basis_name = name

    # --cache-stats PATH writes the measurement file (see `_write_cache_stats`)
    # and, on its own, turns the daemon into a COUNTER: every deck is solved
    # fresh exactly as today and the file records how many of them a cache
    # would have served. That is the live experiment the default-off decision
    # is waiting on, and it cannot change an answer because nothing is
    # retained. `--cache` on top of it serves as well as counts.
    #
    # A missing path fails fast and nonzero for the same reason an unknown
    # --basis does: the -version probe is the configure-time moment to catch
    # a malformed portal-dialog line, not the first deck of a live session.
    while "--cache-stats" in rest or any(a.startswith("--cache-stats=") for a in rest):
        if "--cache-stats" in rest:
            k = rest.index("--cache-stats")
            path = rest[k + 1] if k + 1 < len(rest) else ""
            del rest[k : k + 2]
        else:
            k = next(i for i, a in enumerate(rest) if a.startswith("--cache-stats="))
            path = rest.pop(k).split("=", 1)[1]
        if not path or path.startswith("-"):
            stdout.write("--cache-stats needs a file path\n")
            stdout.flush()
            return 3
        _cache_stats_path = path

    # --cache is a bare flag on purpose: it has no parameter to get wrong, and
    # the cap is a constant rather than a knob (see `_CACHE_BYTES_CAP`).
    _cache_serving = "--cache" in rest
    argv = [a for a in rest if a != "--cache"]

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
        head = line.strip().upper().split()[:1]
        if head not in (["NX"], ["EN"]):
            body.append(line.rstrip("\n"))
            continue
        out, err = deck_frame("\n".join(body), terminator=head[0])
        stdout.write("\n".join(out) + "\n")
        stdout.flush()
        if err:
            stderr.write("\n".join(err) + "\n")
            stderr.flush()
        if head == ["EN"]:
            return 0
        body = []
    if any(ln.strip() for ln in body):
        stderr.write(
            "WARNING: deck discarded — stdin ended before an NX or EN card. "
            "The portal solves a deck only at its frame terminator: SimNEC "
            "appends NX itself; a standalone .nec file must end with EN.\n"
        )
        stderr.flush()
    return 0


if __name__ == "__main__":  # pragma: no cover - console-script entry point
    raise SystemExit(main())
