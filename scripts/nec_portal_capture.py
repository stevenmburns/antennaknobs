#!/usr/bin/env python3
"""Capture NEC-2 printout from SimNEC's own oracle engine (issue #792, unit 1).

SimNEC drives its NEC engine as a *resident* child process: it writes a NEC-2
card deck to the child's stdin, terminates the deck with an ``NX`` card, and
parses classic NEC-2 printout back off the child's stdout.  The child stays
alive for the next deck.  We are going to reimplement that child on top of
momwire, so we first need byte-level ground truth for what the real engine
prints.

This script builds a small, deterministic corpus of decks in SimNEC's *portal
dialect* (the card subset ``nec2/NECSource`` actually emits — CM/CE, EK, GW,
GM, GS, GE, GN, GD, LD, IS, EX, NT, TL, FR, RP, NE, NH, PT, MP, XQ, plus
Ward's custom ``YY`` — terminated by ``NX``), runs each one through the oracle
binary, and
commits the deck/printout pairs as fixtures under
``tests/fixtures/nec_portal/``.

CI never has the oracle binary.  The fixtures are committed precisely so that
the fast tests (``tests/test_nec_portal_fixtures.py``) and the later units'
conformance tests can run without it.

Usage
-----
    python scripts/nec_portal_capture.py            # regenerate fixtures
    python scripts/nec_portal_capture.py --check    # verify committed fixtures

``--check`` regenerates into a temporary directory and diffs against the
committed tree, exiting non-zero on any drift.  That is the idempotency gate:
re-running the capture must produce byte-identical fixtures.

Determinism
-----------
The oracle prints wall-clock timings ("FILL: 1 msec", "Somnec Computation Time
30", "TOTAL RUN TIME: 0 msec") that genuinely vary run to run.  Those lines are
canonicalised to zero by :func:`canonicalize_timings` before the printout is
written.  Nothing else is touched: the fixtures are otherwise verbatim oracle
output, and the canonicalised lines keep their exact column layout so the
grammar they demonstrate stays valid.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "nec_portal"
MANIFEST_NAME = "manifest.json"

# SimNEC 2/3 ships this build; its banner reports VERSION:5b4az.ae6ty.1.17,
# which is what nec2/Execute.versionB ("5b4az\.ae6ty\.(.*)") matches.
DEFAULT_ORACLE = Path(
    "/home/smburns/.SimNEC/2/3/Examples/nec2c.ae6ty/bin/nec2c-ubuntu-x86"
)
ORACLE_ENV = "NEC_PORTAL_ORACLE"

# Per-deck wall-clock ceiling and the concurrency cap.  This box has 16 GB and
# the oracle is a dense-matrix solver: never run more than two at once.
DECK_TIMEOUT_S = 30.0
MAX_JOBS = 2


# ---------------------------------------------------------------------------
# corpus: the jar's own embedded test deck
# ---------------------------------------------------------------------------

# Verbatim from the ``testdeck`` string constant in nec2/NEC2Daemon (recovered
# with `javap -c -p -constants nec2/NEC2Daemon.class`).  Five wires forming one
# split dipole, a YY card naming three (tag, segment) report points, and three
# EX/FR/XQ groups — one 1 V run per source, which is how SimNEC builds an
# N-port Y matrix.
JAR_TESTDECK = (
    "CE QQ 1\n"
    "GW 1 7 1.250000 0.000000 11.648950 -1.250000 0.000000 11.648950 0.001000\n"
    "GW 2 7 -1.250000 0.000000 11.648950 -3.750000 0.000000 11.648950 0.001000\n"
    "GW 3 3 -3.750000 0.000000 11.648950 -5.000000 0.000000 11.648950 0.001000\n"
    "GW 4 3 5.000000 0.000000 11.648950 3.750000 0.000000 11.648950 0.001000\n"
    "GW 5 7 3.750000 0.000000 11.648950 1.250000 0.000000 11.648950 0.001000\n"
    "GE 0\n"
    "YY 1 4 2 4 5 4\n"
    "EX 0 1 4 0 1.\n"
    "FR 0 1 0 0 30.000000 1\n"
    "XQ\n"
    "EX 0 2 4 0 1.\n"
    "FR 0 1 0 0 30.000000 1\n"
    "XQ\n"
    "EX 0 5 4 0 1.\n"
    "FR 0 1 0 0 30.000000 1\n"
    "XQ\n"
)

# nec2/NEC2Daemon.submit() prepends "CM FF 2\n" (a Ward extension: reduced
# far-field detail) and, when a Sommerfeld cache file is in play, a
# "CM SOMNEC <file>\n" line, then appends the NX terminator.
DAEMON_PREFIX = "CM FF 2\n"


# ---------------------------------------------------------------------------
# corpus: hand-authored synthetic decks
# ---------------------------------------------------------------------------

_DIPOLE_GW = "GW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\n"


def _synthetic_decks() -> dict[str, str]:
    """Small hand-authored portal-dialect decks, one per feature under test."""
    decks: dict[str, str] = {}

    decks["dipole_free_space"] = (
        "CE dipole free space\n" + _DIPOLE_GW + "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # FR with npoints > 1 and a non-zero step: one full printout block per
    # frequency, all inside a single XQ.
    decks["dipole_fr_sweep"] = (
        "CE dipole fr sweep\n" + _DIPOLE_GW + "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 3 0 0 28. 1.\n"
        "XQ\n"
    )

    # Perfect ground.  GE 1 tells NEC the structure has a ground connection.
    decks["dipole_pec_ground"] = (
        "CE dipole over perfect ground\n"
        "GW 1 9 0. 0. 2.0 0. 0. 7.0 0.001\n"
        "GE -1\n"
        "GN 1\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 14.1 0\n"
        "XQ\n"
    )

    # Sommerfeld/Norton ground (GN 2) — exercises the SOMNEC table build and
    # its "Somnec Computation Time" timing line.
    decks["dipole_sommerfeld_ground"] = (
        "CE dipole over sommerfeld ground\n"
        "GW 1 9 0. 0. 5.0 0. 0. 10.0 0.001\n"
        "GE -1\n"
        "GN 2 0 0 0 13. 0.005\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 14.1 0\n"
        "XQ\n"
    )

    # GD — NEC-2's "additional ground parameters" card (issue #800's tail).
    # SimNEC's EZNEC-derived examples (`Cardioid (EZNEC).ssn`,
    # `4-square (EZNEC).ssn`) carry one and NECSource forwards it verbatim, so
    # refusing it failed every one of those decks live. This deck is
    # `dipole_pec_ground` plus the card, written in the COMMA-delimited form
    # SimNEC actually emits (`GD 2,0,0,0,13.,.005,0.,0.`) — measured identical
    # to the space-separated form on the oracle — so the pair is a clean
    # with/without diff of the card's entire observable effect.
    decks["dipole_gd_second_medium"] = (
        "CE dipole over perfect ground\n"
        "GW 1 9 0. 0. 2.0 0. 0. 7.0 0.001\n"
        "GE -1\n"
        "GN 1\n"
        "GD 2,0,0,0,13.,.005,0.,0.\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 14.1 0\n"
        "XQ\n"
    )

    # The same card with all four REAL fields non-zero, over the Sommerfeld
    # ground. The Cardioid's own card leaves CLT and CHT at zero, which would
    # leave the last two columns of the echo unpinned; this one is a genuine
    # linear cliff (edge 20 m out, second medium 2 m below) and is
    # `dipole_sommerfeld_ground` plus the card, for the second with/without
    # pair.
    decks["dipole_gd_cliff_sommerfeld"] = (
        "CE dipole over sommerfeld ground\n"
        "GW 1 9 0. 0. 5.0 0. 0. 10.0 0.001\n"
        "GE -1\n"
        "GN 2 0 0 0 13. 0.005\n"
        "GD 0 0 0 0 5. .001 20. -2.\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 14.1 0\n"
        "XQ\n"
    )

    # Reflection-coefficient finite ground (GN 0).
    decks["dipole_reflection_ground"] = (
        "CE dipole over reflection-coefficient ground\n"
        "GW 1 9 0. 0. 5.0 0. 0. 10.0 0.001\n"
        "GE -1\n"
        "GN 0 0 0 0 13. 0.005\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 14.1 0\n"
        "XQ\n"
    )

    # LD 0 — series RLC on one segment.
    decks["dipole_load_ld0"] = (
        "CE dipole with series RLC load\n" + _DIPOLE_GW + "GE 0\n"
        "LD 0 1 3 3 50. 1.e-6 0.\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # LD 4 — impedance directly on one segment.
    decks["dipole_load_ld4"] = (
        "CE dipole with impedance load\n" + _DIPOLE_GW + "GE 0\n"
        "LD 4 1 3 3 100. -75.\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # LD 5 — wire conductivity over the whole structure.
    decks["dipole_load_ld5_conductivity"] = (
        "CE dipole with finite wire conductivity\n" + _DIPOLE_GW + "GE 0\n"
        "LD 5 1 1 9 5.8e7\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # GS — structure scaling.  Wire is written in centimetres then scaled.
    decks["dipole_gs_scaled"] = (
        "CE dipole scaled by GS\n"
        "GW 1 9 0. 0. -250. 0. 0. 250. 0.1\n"
        "GS 0 0 0.01\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # GM — translate a copy of wire 1 to make a parasitic pair.
    decks["dipole_gm_translated_pair"] = (
        "CE dipole plus GM-translated copy\n"
        + _DIPOLE_GW
        + "GM 1 1 0. 0. 0. 2.0 0. 0. 1.\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # NT — a two-port network between two segments.
    decks["dipole_nt_network"] = (
        "CE two dipoles joined by an NT network\n"
        + _DIPOLE_GW
        + "GW 2 9 1.0 0. -2.5 1.0 0. 2.5 0.001\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "NT 1 5 2 5 0. 0.02 0. -0.02 0. 0.02\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # TL — a transmission line between two segments. nec2c prints it as an
    # EQUIVALENT NETWORK: the same NETWORK DATA banner an NT gets, a different
    # three-line column header describing the card's own fields, and a
    # trailing STRAIGHT/CROSSED word in the LINE TYPE column. 2.5 m at 30 MHz
    # is 0.2502 wavelengths, i.e. the quarter-wave transformer case (issue
    # #799).
    decks["dipole_tl_network"] = (
        "CE two dipoles joined by a TL\n"
        + _DIPOLE_GW
        + "GW 2 9 1.0 0. -2.5 1.0 0. 2.5 0.001\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "TL 1 5 2 5 600. 2.5 0. 0. 0. 0.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # The rest of the TL card's surface in one deck: a CROSSED line (NEC spells
    # that a NEGATIVE z0, and echoes |z0| with "CROSSED" in the type column),
    # non-zero COMPLEX shunt admittances at both ends — which is the only way
    # a TL contributes NETWORK LOSS — and an NT card alongside it, because the
    # header block is re-emitted every time the row KIND changes and a
    # TL-only deck cannot show that.
    #
    # The NT deliberately hangs on a THIRD dipole rather than back across the
    # same pair: two branches between one pair of gaps makes a resonant loop
    # whose port admittance is a 3:1 cancellation, and cross-basis noise comes
    # out of it multiplied. Chained (1 --TL-- 2 --NT-- 3) it does not, and the
    # layout under test is identical either way.
    decks["dipole_tl_shunt_crossed"] = (
        "CE crossed TL with shunt ends alongside an NT\n"
        + _DIPOLE_GW
        + "GW 2 9 1.0 0. -2.5 1.0 0. 2.5 0.001\n"
        "GW 3 9 2.0 0. -2.5 2.0 0. 2.5 0.001\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "TL 1 5 2 5 -450. 3.0 1.e-3 2.e-3 3.e-3 -4.e-3\n"
        "NT 2 5 3 5 0. 0.005 0. -0.005 0. 0.005\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # MP — the ae6ty multiprocessing hint (issue #800). SimNEC emits it
    # AUTOMATICALLY once a structure's segment count reaches
    # NEC2PortalDialog.getMPInfo()[0] (prefs `necMP #segs #Proc blockSize`,
    # default "256 16 32"), so it arrives on structure SIZE and not on user
    # intent — any big array trips it in normal use. The card is
    # `MP <#Proc> <blockSize>`, two integer fields, and the oracle honours it
    # at ANY segment count: this 9-segment dipole is the same geometry as
    # `dipole_free_space`, so the pair is a clean with/without diff of the
    # card's entire observable effect.
    decks["dipole_mp_multiprocessor"] = (
        "CE dipole free space\n" + _DIPOLE_GW + "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "MP 16 32\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # The same card asking for ONE processor. The DATA CARD echo is there, but
    # the `MP: multiProcessor` line is not — the oracle prints it only when it
    # is actually going parallel (#Proc >= 2), so a fixture that only carried
    # the 16-processor form would leave the threshold unpinned.
    decks["dipole_mp_single_process"] = (
        "CE dipole free space\n" + _DIPOLE_GW + "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "MP 1 32\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # PT — current print control (issue #800). SimNEC emits it only around a
    # plane-wave run (`EX 1 ...` / `PT -1` / `XQ` / `PT -2`, the
    # planeWaveExcitation branch of NECSource.constructNECFile), but the card
    # itself is independent of that sequence: it is a persistent toggle on the
    # CURRENTS AND LOCATION table alone. This deck shows both halves of the
    # toggle in one run — the first XQ suppressed, the second restored — and,
    # because it carries a YY card, that Ward's `-YY` report SURVIVES the
    # suppression and is printed where the table would have been.
    decks["dipole_ek_extended"] = (
        "CE ek extended thin-wire kernel, as the live NECSource path sends it\n"
        + _DIPOLE_GW
        + "GE 0\n"
        "EK\n"
        "FR 0 1 0 0 30. 1\n"
        "EX 0 1 5 0 1.\n"
        "XQ\n"
    )
    decks["dipole_ek_rearm"] = (
        "CE ek -1 echo form, and an EK between XQs re-arming without a refill\n"
        + _DIPOLE_GW
        + "GE 0\n"
        "EK -1\n"
        "FR 0 1 0 0 30. 1\n"
        "EX 0 1 5 0 1.\n"
        "XQ\n"
        "EK\n"
        "XQ\n"
    )
    decks["dipole_pt_toggle"] = (
        "CE pt suppresses then restores the currents table\n"
        + _DIPOLE_GW
        + "GW 2 9 1.0 0. -2.5 1.0 0. 2.5 0.001\n"
        "GE 0\n"
        "YY 1 5 2 5\n"
        "FR 0 1 0 0 30. 1\n"
        "EX 0 1 5 0 1.\n"
        "PT -1\n"
        "XQ\n"
        "PT -2\n"
        "EX 0 2 5 0 1.\n"
        "XQ\n"
    )

    # PT's other live form: `PT 0 <tag> <first> <last>` keeps the table but
    # prints only those segments. The addressing is EX's — tag-relative, with
    # tag 0 meaning absolute segment numbers — so tag 2 segments 1-3 are global
    # 10-12 here, which an absolute reading would get wrong.
    decks["dipole_pt_segment_range"] = (
        "CE pt limits the currents table to one tag\n"
        + _DIPOLE_GW
        + "GW 2 9 1.0 0. -2.5 1.0 0. 2.5 0.001\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "PT 0 2 1 3\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )

    # The Y-matrix probe SimNEC actually emits for a 2-source circuit: one XQ
    # per source, every source carrying an EX card — 1 V on the driven one and
    # 1e-10 V on the others so that every port shows up as a row of the
    # ANTENNA INPUT PARAMETERS table (nec2/NECSource.sensorLines).
    decks["two_source_sensor_lines"] = (
        "CE two source sensor lines\n"
        + _DIPOLE_GW
        + "GW 2 9 1.0 0. -2.5 1.0 0. 2.5 0.001\n"
        "GE 0\n"
        "FR 0 1 0 0 30. 1\n"
        "EX 0 1 5 0 1.000000e+00\n"
        "EX 0 2 5 0 1.000000e-10\n"
        "XQ\n"
        "EX 0 1 5 0 1.000000e-10\n"
        "EX 0 2 5 0 1.000000e+00\n"
        "XQ\n"
    )

    # The same 2-port structure driven through Ward's YY card instead: one EX
    # per XQ, and the engine reports the named (tag, segment) currents on a
    # "-YY" line.
    decks["two_source_yy_card"] = (
        "CE two source YY probe\n"
        + _DIPOLE_GW
        + "GW 2 9 1.0 0. -2.5 1.0 0. 2.5 0.001\n"
        "GE 0\n"
        "YY 1 5 2 5\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 1\n"
        "XQ\n"
        "EX 0 2 5 0 1.\n"
        "FR 0 1 0 0 30. 1\n"
        "XQ\n"
    )

    # RP exactly as nec2/NECSource formats it:
    #   "RP %d %d %d 1001 0 0 %d %d 1000" with numTheta = 180/res + 1 (90/res + 1
    # over ground) and numPhi = 360/res + 1.  res = 30 keeps the table small.
    decks["dipole_rp_pattern"] = (
        "CE dipole with radiation pattern\n" + _DIPOLE_GW + "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "RP 0 7 13 1001 0 0 30 30 1000\n"
        "XQ\n"
    )

    # RP again, but with a CIRCULARLY polarised pattern: two orthogonal
    # dipoles fed in quadrature.  dipole_rp_pattern only ever prints SENSE
    # "LINEAR" or blank, which leaves the 11-vs-12-token rule in
    # nec2/Execute's PROCESSINGPATTERN state half-pinned (grammar doc §4.14,
    # §10).  This deck forces the third form and shows what the column really
    # is: a fixed-width field, blank exactly when BOTH E components fall under
    # nec2c's 1e-20 threshold.
    decks["dipole_rp_crossed_quadrature"] = (
        "CE crossed dipoles in quadrature\n"
        "GW 1 9 -2.5 0. 0. 2.5 0. 0. 0.001\n"
        "GW 2 9 0. -2.5 0. 0. 2.5 0. 0.001\n"
        "GE 0\n"
        "EX 0 1 5 0 1. 0.\n"
        "EX 0 2 5 0 0. 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "RP 0 3 5 1001 0 0 45 90 1000\n"
        "XQ\n"
    )

    # ------------------------------------------------------------------
    # RP's cliff modes (issue #802) — the shapes a GD card is FOR
    # ------------------------------------------------------------------
    #
    # The cliff decks share one geometry: a 5 m vertical from z = 2 m to
    # z = 7 m at 14.1 MHz, over a cliff whose edge is 10 m out and whose far
    # side is 2 m lower, with a poor second medium (eps 5, sigma 0.001).
    #
    # The numbers are chosen so the pattern grid STRADDLES the edge three
    # different ways, which is the physics under test. NEC picks the medium
    # per SEGMENT, at that segment's own specular reflection point
    # `d = z*tan(theta)` measured out along the ray's azimuth, so with
    # segment heights running 2.28-6.72 m and CLT = 10 m:
    #
    #   theta <= 50    every segment reflects inside the edge  (medium 1)
    #   theta 60, 70   the low segments are inside and the high ones beyond
    #   theta = 80     every segment is beyond it              (medium 2)
    #
    # ...and, under the LINEAR cliff, the azimuth decides as well: the edge
    # is the line x = CLT, so phi = 0 crosses it, phi = 90 runs parallel to
    # it and never does, and phi = 180 walks away from it. Under the CIRCULAR
    # cliff the edge is a circle of radius CLT and every azimuth crosses it
    # alike, which is exactly the pair's diff.
    #
    # theta stops at 80 deliberately. At theta = 90 the selection is decided
    # by `tan(90 deg)` — 1.6e16 in double precision — against a `cos(phi)`
    # that is 6.1e-17 at phi = 90, so which medium a segment lands in is
    # settled by the last bits of two library functions rather than by any
    # physics. That is a fine thing for the oracle to do and a terrible one
    # to hold a second engine to.
    _CLIFF_VERTICAL = "GW 1 9 0. 0. 2.0 0. 0. 7.0 0.001\n"
    _CLIFF_GD = "GD 0 0 0 0 5. .001 10. -2.\n"
    _CLIFF_DRIVE = "EX 0 1 5 0 1.\nFR 0 1 0 0 14.1 0\n"

    # RP 2 — the linear cliff. Over PEC, so medium 1 is the ideal mirror and
    # every moved number is the second medium's alone.
    decks["dipole_rp2_linear_cliff"] = (
        "CE vertical over a linear cliff\n" + _CLIFF_VERTICAL + "GE -1\n"
        "GN 1\n" + _CLIFF_GD + _CLIFF_DRIVE + "RP 2 9 5 1001 0 0 10 45 1000\n"
        "XQ\n"
    )

    # RP 3 — the circular cliff, on the same deck. This is where Ward's
    # EZNEC-derived examples land their cliff parameters, and the pair with
    # the deck above is a clean diff of LINEAR against CIRCULAR: identical
    # geometry, identical ground, one digit of the RP card apart.
    decks["dipole_rp3_circular_cliff"] = (
        "CE vertical over a circular cliff\n" + _CLIFF_VERTICAL + "GE -1\n"
        "GN 1\n" + _CLIFF_GD + _CLIFF_DRIVE + "RP 3 9 5 1001 0 0 10 45 1000\n"
        "XQ\n"
    )

    # The circular cliff over a SOMMERFELD ground, which is the combination
    # an EZNEC import actually arrives in. Worth its own fixture because the
    # far field treats GN 2 as an ordinary reflection-coefficient medium —
    # ffld() only special-cases iperf == 1 — so medium 1 here is a Fresnel
    # coefficient rather than the mirror, and the two coefficients this deck
    # switches between are both finite.
    decks["dipole_rp3_cliff_sommerfeld"] = (
        "CE vertical over a circular cliff, sommerfeld ground\n"
        + _CLIFF_VERTICAL
        + "GE -1\n"
        "GN 2 0 0 0 13. 0.005\n"
        + _CLIFF_GD
        + _CLIFF_DRIVE
        + "RP 3 9 5 1001 0 0 10 45 1000\n"
        "XQ\n"
    )

    # The second medium and the cliff geometry do NOT have to arrive on a GD
    # card: a GN whose radial-wire count is zero carries the same four fields
    # in F3-F6, and main.c writes them into the same fpat slots the GD case
    # does. A deck that sets the cliff this way and never sends a GD is a
    # valid cliff deck, so an engine that only watched for GD would answer it
    # as flat ground.
    decks["dipole_rp2_cliff_on_the_gn_card"] = (
        "CE vertical over a linear cliff set on the gn card\n"
        + _CLIFF_VERTICAL
        + "GE -1\n"
        "GN 0 0 0 0 13. .005 5. .001 10. -2.\n"
        + _CLIFF_DRIVE
        + "RP 2 9 5 1001 0 0 10 45 1000\n"
        "XQ\n"
    )

    # RFLD = 0 — the gain-only form. The RP card's F5 is the range the E
    # columns are reported at; zero means "do not scale them", and the
    # printout changes shape as well as value: the RANGE / EXP(-JKR)/R pair
    # (and the blank line above it) is not printed at all, and the E columns
    # carry the raw far-field amplitude instead of the field at a range.
    # The GAIN columns are untouched — they never depended on the range —
    # which is what makes this deck a control on the pair as well as a
    # capture of the shape.
    decks["dipole_rp_gain_only"] = (
        "CE dipole with a gain-only radiation pattern\n" + _DIPOLE_GW + "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "RP 0 5 3 1001 0 0 45 45 0\n"
        "XQ\n"
    )

    # NE — rectangular near-field grid, the non-polar branch of
    # nec2/NECSource.generateNENH.
    decks["dipole_ne_nearfield"] = (
        "CE dipole with near electric field grid\n" + _DIPOLE_GW + "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "NE 0 3 1 3 -1. 0. -1. 1. 0. 1.\n"
        "XQ\n"
    )

    # NH — the magnetic twin.  Captured because its banner is NOT the electric
    # one with a word swapped: the indent and the trailing dash run both
    # differ, and the units row reads AMPS/M on a different column pitch.
    decks["dipole_nh_nearfield"] = (
        "CE dipole with near magnetic field grid\n" + _DIPOLE_GW + "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "NH 0 3 1 3 -1. 0. -1. 1. 0. 1.\n"
        "XQ\n"
    )

    # The jar's own deck, raw and as NEC2Daemon.submit() actually frames it.
    decks["jar_testdeck"] = JAR_TESTDECK
    decks["jar_testdeck_daemon_framed"] = DAEMON_PREFIX + JAR_TESTDECK

    return decks


# ---------------------------------------------------------------------------
# corpus: catalog designs exported through antennaknobs.nec_export
# ---------------------------------------------------------------------------

# (design name, ground spec passed to export_nec).  Kept small and fast: every
# one of these solves in well under a second.
CATALOG_DESIGNS: tuple[tuple[str, object], ...] = (
    ("beams.moxon", "pec"),
    ("broadband.t2fd", "pec"),
    ("dipoles.invvee", "pec"),
    ("dipoles.ocf_dipole", ("finite", 13.0, 0.005)),
    ("dipoles.short_dipole_loaded", None),
    ("loops.delta_loop", "pec"),
    ("multiband.trap_dipole", None),
    ("specialty.bowtie", None),
    ("verticals.vertical", "pec"),
    ("wire.w8jk", "pec"),
)

# Every card nec2/NECSource can write.  Anything else exported by nec_export
# (notably the EN terminator, which the portal replaces with NX) is dropped
# when massaging a catalog deck into the portal dialect.
PORTAL_CARDS = frozenset(
    {
        "CM",
        "CE",  # comments
        "EK",  # extended thin-wire kernel — the live NECSource path sends it
        "GW",
        "GM",
        "GS",
        "GE",  # geometry
        "GN",
        "GD",
        "LD",
        "IS",  # environment / second medium / loading / insulation
        "EX",
        "NT",
        "TL",
        "FR",  # excitation, networks, transmission lines, frequency
        "RP",
        "NE",
        "NH",  # far field, near E field, near H field
        "PT",
        "MP",  # print control, multiprocessing hint
        "YY",
        "XQ",  # Ward's Y-report card, execute
    }
)


def _to_portal_dialect(deck: str) -> str:
    """Strip non-portal cards from ``deck`` and terminate it with ``NX``."""
    lines = []
    for raw in deck.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        card = line.split()[0].upper()
        if card not in PORTAL_CARDS:
            # EN, RP, and anything else outside the portal subset.
            continue
        lines.append(line)
    if not any(ln.split()[0].upper() == "XQ" for ln in lines):
        lines.append("XQ")
    return "\n".join(lines) + "\n"


def _catalog_decks() -> dict[str, str]:
    """Export the catalog designs, massaged into the portal dialect.

    Designs whose export raises (TL / virtual-driver networks have no faithful
    single-deck NEC representation) are reported and skipped rather than
    fought with.
    """
    from antennaknobs.cli import resolve_class
    from antennaknobs.nec_export import export_nec

    decks: dict[str, str] = {}
    for name, ground in CATALOG_DESIGNS:
        try:
            builder = resolve_class(name)()
            raw = export_nec(builder, ground=ground, include_rp=False, title=name)
        except Exception as exc:  # noqa: BLE001 - report and move on
            print(
                f"  skip catalog design {name}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            continue
        key = "catalog_" + name.replace(".", "_")
        decks[key] = _to_portal_dialect(raw)
    return decks


# ---------------------------------------------------------------------------
# corpus assembly
# ---------------------------------------------------------------------------

RESIDENT_NAME = "resident_two_decks"


def _resident_deck() -> str:
    """Two decks down one stdin, each terminated by its own ``NX``.

    This is the residency framing nec2/NEC2Daemon uses: ``ps.println(deck)``
    then ``ps.println("NX\\n")``, over and over, on a process that is never
    restarted between decks.
    """
    first = (
        "CE resident deck one\n" + _DIPOLE_GW + "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
        "NX\n"
    )
    second = (
        "CE resident deck two\n"
        "GW 1 9 0. 0. -3.0 0. 0. 3.0 0.001\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "FR 0 1 0 0 25. 0\n"
        "XQ\n"
        "NX\n"
    )
    return first + second


def build_corpus() -> list[tuple[str, str]]:
    """Return the whole corpus as a name-sorted list of (name, deck) pairs.

    Every deck already carries its terminating ``NX`` card; the text returned
    here is exactly the bytes written to the oracle's stdin.
    """
    decks: dict[str, str] = {}
    for name, body in _synthetic_decks().items():
        decks[name] = body + "NX\n"
    for name, body in _catalog_decks().items():
        decks[name] = body + "NX\n"
    decks[RESIDENT_NAME] = _resident_deck()
    return sorted(decks.items())


# ---------------------------------------------------------------------------
# running the oracle
# ---------------------------------------------------------------------------


class OracleMissing(RuntimeError):
    """The SimNEC oracle binary is not available on this machine."""


def find_oracle(explicit: str | None = None) -> Path:
    """Locate the oracle binary, or raise :class:`OracleMissing` with advice."""
    candidate = Path(explicit or os.environ.get(ORACLE_ENV) or DEFAULT_ORACLE)
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise OracleMissing(
            f"SimNEC oracle binary not found or not executable: {candidate}\n"
            f"Set {ORACLE_ENV}=/path/to/nec2c-ubuntu-x86 (it ships with SimNEC\n"
            "under .SimNEC/<major>/<minor>/Examples/nec2c.ae6ty/bin/).\n"
            "The committed fixtures under tests/fixtures/nec_portal/ exist so\n"
            "that CI never needs this binary — only regeneration does."
        )
    return candidate


# Wall-clock values the oracle prints.  Canonicalised to zero so the capture is
# reproducible; the surrounding column layout is preserved verbatim.
_TIMING_SUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(FILL:\s*)\d+(\s*msec\s+FACTOR:\s*)\d+(\s*msec)"),
        r"\g<1>0\g<2>0\g<3>",
    ),
    (
        re.compile(r"(FILL=\s*)[\d.eE+-]+(\s*SEC\.,\s*FACTOR=\s*)[\d.eE+-]+"),
        r"\g<1>0\g<2>0",
    ),
    (re.compile(r"(TOTAL RUN TIME:\s*)\d+"), r"\g<1>0"),
    (re.compile(r"(RUN TIME\s*=\s*)[\d.eE+-]+"), r"\g<1>0"),
    (re.compile(r"(Somnec Computation Time\s+)[\d.eE+-]+"), r"\g<1>0"),
    (re.compile(r"(Radiation Compute Time\s+)[\d.eE+-]+"), r"\g<1>0"),
    (re.compile(r"(Near Field Compute Time\s+)[\d.eE+-]+"), r"\g<1>0"),
    (
        re.compile(
            r"(Time to generate Sommerfeld ground tables\s*=\s*)[\d.eE+-]+(\s*seconds)"
        ),
        r"\g<1>0\g<2>",
    ),
)


def canonicalize_timings(text: str) -> str:
    """Zero out the wall-clock numbers the oracle prints.

    These are the only non-deterministic fields in the printout.  Everything
    else in a fixture is verbatim oracle output.
    """
    for pattern, repl in _TIMING_SUBS:
        text = pattern.sub(repl, text)
    return text


def run_deck(oracle: Path, deck: str) -> tuple[int, str, str]:
    """Pipe ``deck`` to a fresh oracle process; return (rc, stdout, stderr).

    A deck terminated by ``NX`` leaves the engine resident and waiting; closing
    stdin then ends it.  The engine reacts to that EOF by re-printing its
    banner and exiting non-zero ("Error reading input file"), which is exactly
    what SimNEC's daemon sees at shutdown, so the tail is kept verbatim.
    """
    proc = subprocess.run(
        [str(oracle)],
        input=deck,
        capture_output=True,
        text=True,
        timeout=DECK_TIMEOUT_S,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------
# fixture writing
# ---------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def capture(oracle: Path, out_dir: Path, jobs: int = MAX_JOBS) -> dict:
    """Run the whole corpus and write the fixture tree into ``out_dir``."""
    corpus = build_corpus()
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = max(1, min(jobs, MAX_JOBS))
    results: dict[str, tuple[int, str, str]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run_deck, oracle, deck): name for name, deck in corpus}
        for future in concurrent.futures.as_completed(futures):
            results[futures[future]] = future.result()

    entries = []
    for name, deck in corpus:
        rc, stdout, stderr = results[name]
        printout = canonicalize_timings(stdout)
        (out_dir / f"{name}.deck").write_text(deck)
        (out_dir / f"{name}.out").write_text(printout)
        entries.append(
            {
                "name": name,
                "returncode": rc,
                "deck_sha256": _sha256(deck),
                "out_sha256": _sha256(printout),
                "stderr": canonicalize_timings(stderr),
            }
        )

    manifest = {
        "oracle_version": _banner_version(entries, out_dir),
        "timing_canonicalized": True,
        "decks": entries,
    }
    (out_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


_BANNER_RE = re.compile(r"^VERSION:(\S+)", re.MULTILINE)


def _banner_version(entries: list[dict], out_dir: Path) -> str:
    """Pull the engine version out of the first fixture that has a banner."""
    for entry in entries:
        text = (out_dir / f"{entry['name']}.out").read_text()
        match = _BANNER_RE.search(text)
        if match:
            return match.group(1)
    return "<unknown>"


def check(oracle: Path) -> int:
    """Regenerate into a temp dir and diff against the committed fixtures."""
    with tempfile.TemporaryDirectory(prefix="nec-portal-check-") as tmp:
        tmp_dir = Path(tmp)
        capture(oracle, tmp_dir)
        fresh = {p.name: p.read_text() for p in sorted(tmp_dir.iterdir())}
        # README.md documents the corpus' provenance (issue #805); it is
        # hand-written, not generated, so it is exempt from the drift diff.
        committed = {
            p.name: p.read_text()
            for p in sorted(FIXTURE_DIR.iterdir())
            if p.name != "README.md"
        }

    drift = []
    for name in sorted(set(fresh) | set(committed)):
        if name not in committed:
            drift.append(f"  missing from fixtures: {name}")
        elif name not in fresh:
            drift.append(f"  stale fixture (no longer generated): {name}")
        elif fresh[name] != committed[name]:
            drift.append(f"  content differs: {name}")

    if drift:
        print("nec_portal_capture --check: FIXTURE DRIFT", file=sys.stderr)
        print("\n".join(drift), file=sys.stderr)
        print(
            "Re-run `python scripts/nec_portal_capture.py` and commit the result.",
            file=sys.stderr,
        )
        return 1

    print(f"nec_portal_capture --check: OK ({len(committed)} files)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate to a temp dir and diff against committed fixtures",
    )
    parser.add_argument(
        "--oracle",
        default=None,
        help=f"path to the oracle binary (default: ${ORACLE_ENV} or {DEFAULT_ORACLE})",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help=f"where to write fixtures (default: {FIXTURE_DIR})",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=MAX_JOBS,
        help=f"concurrent oracle processes (capped at {MAX_JOBS})",
    )
    args = parser.parse_args(argv)

    try:
        oracle = find_oracle(args.oracle)
    except OracleMissing as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.check:
        return check(oracle)

    out_dir = Path(args.out_dir) if args.out_dir else FIXTURE_DIR
    manifest = capture(oracle, out_dir, jobs=args.jobs)
    print(
        f"captured {len(manifest['decks'])} decks from "
        f"{manifest['oracle_version']} into {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
