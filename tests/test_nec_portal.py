"""The momwire SimNEC portal daemon (issue #792, units 2 to 4).

Everything here runs against the committed oracle fixtures — no ``nec2c``
binary — and, bar the one cwd-independence test at the foot of the file, in
process. The oracle's *numbers* are not the contract
(a different basis and kernel will never match digit for digit); its *layout*
is, so the fixtures are compared structurally: same section sequence, same
column geometry, same token arity — for every deck in the corpus, not just a
representative handful. Values are checked against momwire itself
(self-consistency and reciprocity), plus one loose cross-engine smoke bound on
the free-space dipole's impedance. Cross-engine value agreement is
``test_nec_portal_differential.py``.

Unit 3 adds, below the unit-2 sections: the whole-corpus layout gate, the
execute-card semantics of ``RP``/``NE``/``NH``, the pattern and near-field
tables, ``NT`` port algebra, and the robustness contract — a malformed deck
must be REPORTED and stepped over, never swallowed and never fatal, because
``Execute.processResponse`` blocks in ``readLine()`` with no timeout.

Unit 4 adds the packaging contract: the ``momwire-nec2c`` console script whose
NAME is what SimNEC's portal dialog accepts an engine on, and the fact that the
daemon runs from any working directory (SimNEC launches it via ``sh -c`` with
cwd=$HOME).
"""

from __future__ import annotations

import importlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from antennaknobs import nec_portal
from antennaknobs.nec_portal import deck_frame, main, run_deck

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "nec_portal"
ALL_NAMES = tuple(
    entry["name"]
    for entry in json.loads((FIXTURE_DIR / "manifest.json").read_text())["decks"]
)

# nec2/Execute.versionA — the regex SimNEC applies to `<cmd> -version`.
VERSION_A = re.compile(r"nec2c\.ae6ty\.(.*)")

# nec2/Execute.processResponse's daemon sentinel.
NX_ECHO = re.compile(r"^\s*DATA CARD No:\s+(\d+) NX\b.*$", re.MULTILINE)

_NUMBER = re.compile(r"^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$")

# The section banners SimNEC's state machine arms on, plus the ones a reader
# uses to find its way. Order is part of the contract.
_SECTION_MARKERS = (
    "COMMENTS",
    "STRUCTURE SPECIFICATION",
    "MULTIPLE WIRE JUNCTIONS",
    "SEGMENTATION DATA",
    "FREQUENCY",
    "STRUCTURE IMPEDANCE LOADING",
    "ANTENNA ENVIRONMENT",
    "NETWORK DATA",
    "STRUCTURE EXCITATION DATA AT NETWORK CONNECTION POINTS",
    "MATRIX TIMING",
    "ANTENNA INPUT PARAMETERS",
    "CURRENTS AND LOCATION",
    "POWER BUDGET",
    "FAR FIELD GROUND PARAMETERS",
    "RADIATION PATTERNS",
    "NEAR ELECTRIC FIELDS",
    "NEAR MAGNETIC FIELDS",
)

# Small decks only — the whole file has to stay in the fast lane.
REPRESENTATIVE = (
    "dipole_free_space",
    "dipole_pec_ground",
    "dipole_load_ld0",
    "dipole_gs_scaled",
    "dipole_rp2_linear_cliff",
    "jar_testdeck",
    "two_source_yy_card",
    "two_source_sensor_lines",
)


def fixture_deck(name: str) -> str:
    """The deck body: the fixture minus its framing ``NX`` card."""
    return (FIXTURE_DIR / f"{name}.deck").read_text().split("\nNX")[0]


def printout(name: str) -> str:
    """Our printout for a fixture, through the daemon loop when the fixture is
    a multi-deck residency transcript."""
    deck = (FIXTURE_DIR / f"{name}.deck").read_text()
    if deck.count("\nNX") > 1:
        buffer = io.StringIO()
        assert (
            main([], stdin=io.StringIO(deck), stdout=buffer, stderr=io.StringIO()) == 0
        )
        return buffer.getvalue()
    return run_deck(deck.split("\nNX")[0])[0]


def fixture_out(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.out").read_text()


def section_walk(text: str) -> list[str]:
    """The section banners in printout order."""
    walk = []
    for line in text.splitlines():
        stripped = line.strip(" -")
        for marker in _SECTION_MARKERS:
            if stripped == marker:
                walk.append(marker)
                break
    return walk


def layout_signature(line: str) -> tuple:
    """A line's format-determined shape: each token's END column plus whether
    it is a number.

    Right-aligned fixed-width fields put every token's end at a
    format-determined column no matter what the value is, so this compares
    ``%11.4E``-against-``%11.4E`` while letting momwire's numbers differ from
    the oracle's.
    """
    return tuple(
        (m.end(), "N" if _NUMBER.match(m.group()) else m.group())
        for m in re.finditer(r"\S+", line)
    )


def body_lines(text: str) -> list[str]:
    """Non-blank printout lines, minus the ones that legitimately differ:
    the version banner (ours says momwire) and the wall-clock timings the
    capture script canonicalises to zero."""
    return [
        line
        for line in text.splitlines()
        if line.strip()
        and "VERSION:" not in line
        and "FILL:" not in line
        and "ERROR-NEC2C" not in line
    ]


def aip_tables(text: str) -> list[list[list[str]]]:
    """The ANTENNA INPUT PARAMETERS rows, tokenised.

    Mirrors nec2/Execute's WAITINGFORSENSORS state for the NEC2C engine: a
    data row is exactly 11 whitespace tokens (``samplesWidth``) and the
    current sits at fields 4 and 5 (``samplesOffset``).
    """
    tables: list[list[list[str]]] = []
    collecting = False
    for line in text.splitlines():
        parts = line.split()
        if parts[:3] == ["No:", "No:", "REAL"]:
            collecting = True
            tables.append([])
            continue
        if not collecting:
            continue
        if len(parts) != 11:
            collecting = False
            continue
        tables[-1].append(parts)
    return tables


def yy_rows(text: str) -> list[list[float]]:
    return [
        [float(v) for v in line.split()[1:]]
        for line in text.splitlines()
        if line.split()[:1] == ["-YY"]
    ]


# --------------------------------------------------------------------------
# the version probe
# --------------------------------------------------------------------------


# Execute.testCommand's four probe regexes, verbatim from the 6p4d6 bytecode
# (issue #828 research; grammar doc 2026-08-09 addendum). A/B/C Double-parse
# group(1) against the 1.23 floor; NECd reads no group and sets no state.
VERSION_B = re.compile(r"5b4az\.ae6ty\.(.*)")
VERSION_C = re.compile(r"necpp\.nec2c\.(.*)")
VERSION_NECD = re.compile(r"(NEC\d+\D.*)")
# Options.getEngine()'s re-read of the stored version text: group(1) must be
# "2" or SimNEC's scripting layer reclassifies the engine (W7EL insulation
# refuses anything but Complex.TWO).
OPTIONS_ENGINE_PIECE = re.compile(r"[a-zA-Z]*([0-9])+?(.*)")


def test_version_probe_matches_executes_versionNECd_regex():
    """The honest identity (issue #828, Ward-sanctioned): the probe answers
    the versionNECd path, whose match sets no engine state — the engine enum,
    daemon class, and parse offsets all come from the executable FILENAME.
    The gates below replicate every constraint the bytecode research found
    load-bearing, so a probe edit that would break a live SimNEC fails here.
    """
    out = io.StringIO()
    assert main(["-version"], stdin=io.StringIO(""), stdout=out) == 0
    lines = out.getvalue().splitlines()
    assert len(lines) == 1, f"the probe must print exactly one line: {lines}"
    probe = lines[0].strip()

    # lookingAt() semantics = re.match, anchored at the start only.
    assert VERSION_NECD.match(probe), f"{probe!r} does not match (NEC\\d+\\D.*)"
    # Must NOT match A/B/C: those branches Double-parse the tail and a
    # non-numeric tail there is rejected as "nec2c version too old".
    for pat in (VERSION_A, VERSION_B, VERSION_C):
        assert not pat.match(probe), f"{probe!r} would take the {pat.pattern} path"
    # Case-sensitive NEC2 at position 0, non-digit right after the 2 (the
    # regex needs \D after the digit run), and Options.getEngine must read 2.
    assert probe.startswith("NEC2") and not probe[4].isdigit(), probe
    assert OPTIONS_ENGINE_PIECE.match(probe).group(1) == "2", probe
    assert probe.startswith("NEC2momwire.")


def test_legacy_probe_flag_answers_the_versionA_masquerade():
    """``--legacy-probe`` keeps the pre-#828 identity available for a SimNEC
    build that might predate versionNECd. That path Double-parses the tail
    against the 1.23 floor, so the shape constraints are the old ones: one
    dot, a bare number above the floor."""
    out = io.StringIO()
    assert main(["--legacy-probe", "-version"], stdin=io.StringIO(""), stdout=out) == 0
    probe = out.getvalue().strip()
    assert probe == nec_portal.LEGACY_PROBE_VERSION
    tail = VERSION_A.match(probe).group(1)
    assert tail.count(".") == 1 and float(tail) >= 1.23, tail


def test_printout_banner_carries_the_momwire_identity():
    """The banner is not version-checked (the regexes are anchored and it is
    prefixed ``VERSION:``), so it stays fixture-pinned while the PROBE now
    carries the honest identity too (#828). The banner keeps its historical
    shape on purpose: 40 committed fixtures pin it, and the offline .out
    import path (``ae6ty/FileStuff``) greps the ``(nec2c)`` box line."""
    text, _err = run_deck(fixture_deck("dipole_free_space"))
    assert f"VERSION:{nec_portal.BANNER_VERSION}" in text
    assert "momwire" in nec_portal.BANNER_VERSION
    assert "momwire" in nec_portal.PROBE_VERSION


# --------------------------------------------------------------------------
# structural interchangeability with the oracle
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", REPRESENTATIVE)
def test_section_walk_matches_the_oracle(name):
    ours, _err = run_deck(fixture_deck(name))
    assert section_walk(ours) == section_walk(fixture_out(name))


@pytest.mark.parametrize("name", REPRESENTATIVE)
def test_column_layout_matches_the_oracle(name):
    """Same lines, same columns — only the values inside them differ."""
    ours = body_lines(run_deck(fixture_deck(name))[0])
    theirs = body_lines(fixture_out(name))
    assert len(ours) == len(theirs)
    for i, (a, b) in enumerate(zip(ours, theirs, strict=True)):
        if "DIELECTRIC CONSTANT" in b:
            # The oracle glues the real and imaginary parts into one token,
            # so this line's "shape" is its value. It is an ignored section.
            continue
        assert layout_signature(a) == layout_signature(b), (
            f"{name} line {i}\n  ours   {a!r}\n  oracle {b!r}"
        )


@pytest.mark.parametrize("name", REPRESENTATIVE)
def test_nx_sentinel_is_byte_identical_modulo_the_card_ordinal(name):
    """The one line the Java side blocks on. Everything but the ordinal must
    match the oracle byte for byte (grammar doc §2)."""
    ours = NX_ECHO.search(run_deck(fixture_deck(name))[0])
    theirs = NX_ECHO.search(fixture_out(name))
    assert ours and theirs
    assert ours.group(1) == theirs.group(1)
    blank = re.compile(r"No:\s+\d+ NX")
    assert blank.sub("No: NX", ours.group(0)) == blank.sub("No: NX", theirs.group(0))


@pytest.mark.parametrize("name", REPRESENTATIVE)
def test_antenna_input_rows_are_eleven_tokens_with_the_current_at_4_and_5(name):
    ours = aip_tables(run_deck(fixture_deck(name))[0])
    theirs = aip_tables(fixture_out(name))
    assert [len(t) for t in ours] == [len(t) for t in theirs]
    assert ours, f"{name}: no ANTENNA INPUT PARAMETERS table"
    for table in ours:
        for row in table:
            assert len(row) == 11
            float(row[4])
            float(row[5])


def test_quiet_mode_suppresses_the_segmentation_block():
    """`CE QQ 1` is ae6ty's quiet directive; the jar's own test deck uses it."""
    quiet, _err = run_deck(fixture_deck("jar_testdeck"))
    loud, _err = run_deck(fixture_deck("dipole_free_space"))
    assert "SEGMENTATION DATA" not in quiet
    assert "SEGMENTATION DATA" in loud
    assert "STRUCTURE SPECIFICATION" in quiet


def test_reduced_field_is_the_only_thing_written_to_stderr():
    """NEC2Daemon never drains the child's stderr, so anything beyond the
    `CM FF` line risks filling the pipe buffer and deadlocking the UI."""
    _out, err = run_deck(fixture_deck("jar_testdeck_daemon_framed"))
    assert err == "reducedField:2\n"
    _out, err = run_deck(fixture_deck("dipole_free_space"))
    assert err == ""


# --------------------------------------------------------------------------
# the YY report
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "n_ports"), [("two_source_yy_card", 2), ("jar_testdeck", 3)]
)
def test_yy_rows_have_the_oracles_arity(name, n_ports):
    ours = yy_rows(run_deck(fixture_deck(name))[0])
    theirs = yy_rows(fixture_out(name))
    assert len(ours) == len(theirs) == n_ports
    for row in ours:
        assert len(row) == 2 * n_ports


def test_yy_row_agrees_with_the_antenna_input_current():
    """The two Y mechanisms must not disagree.

    ``-YY`` reports the current at each report point and ANTENNA INPUT
    PARAMETERS reports it at each driven port; where a report point IS a port
    they are the same number, so a deck that carries both must print both the
    same way. (The oracle gets this for free — its pulse basis makes the
    segment current and the driving-point current one quantity.)
    """
    text, _err = run_deck(fixture_deck("two_source_yy_card"))
    rows = yy_rows(text)
    tables = aip_tables(text)
    assert len(rows) == len(tables) == 2
    for row, table in zip(rows, tables, strict=True):
        driven = complex(float(table[0][4]), float(table[0][5]))
        # The YY card lists port 1 then port 2; each group drives one of them,
        # so the driven port's own entry appears in the row.
        entries = [complex(row[i], row[i + 1]) for i in range(0, len(row), 2)]
        assert min(abs(e - driven) for e in entries) <= 1e-4 * abs(driven)


def test_yy_matrix_is_reciprocal():
    """The N '-YY' rows of an N-port deck are the N columns of one Y matrix,
    so the off-diagonals must mirror."""
    rows = yy_rows(run_deck(fixture_deck("jar_testdeck"))[0])
    y = [[complex(r[i], r[i + 1]) for i in range(0, len(r), 2)] for r in rows]
    for i in range(3):
        for j in range(i + 1, 3):
            scale = max(abs(y[i][j]), abs(y[j][i]))
            assert abs(y[i][j] - y[j][i]) <= 1e-6 * scale


def test_two_source_y_matrix_is_reciprocal():
    """Y12 == Y21 out of the multi-EX probe SimNEC actually writes. momwire's
    Galerkin operator is symmetric, so this is a self-consistency pin on the
    whole port-algebra path, not an approximation."""
    tables = aip_tables(run_deck(fixture_deck("two_source_sensor_lines"))[0])
    assert len(tables) == 2 and all(len(t) == 2 for t in tables)
    y12 = complex(float(tables[0][1][4]), float(tables[0][1][5]))
    y21 = complex(float(tables[1][0][4]), float(tables[1][0][5]))
    assert abs(y12 - y21) <= 1e-6 * max(abs(y12), abs(y21))


# --------------------------------------------------------------------------
# residency
# --------------------------------------------------------------------------


def test_two_decks_through_one_loop_produce_two_frames():
    """NEC2Daemon.submit frames decks on stdin with NX and never restarts the
    process; the engine reprints its banner after each NX for the deck it
    expects next, so two decks show three banners."""
    text = io.StringIO()
    stdin = io.StringIO((FIXTURE_DIR / "resident_two_decks.deck").read_text())
    assert main([], stdin=stdin, stdout=text, stderr=io.StringIO()) == 0
    ours = text.getvalue()

    assert len(NX_ECHO.findall(ours)) == 2
    assert ours.count("VERSION:") == 3
    assert ours.count("STRUCTURE SPECIFICATION") == 2
    # Card numbering restarts inside each deck.
    assert re.findall(r"DATA CARD No:\s+(\d+) (\w\w)", ours) == [
        ("1", "EX"),
        ("2", "FR"),
        ("3", "XQ"),
        ("4", "NX"),
        ("1", "EX"),
        ("2", "FR"),
        ("3", "XQ"),
        ("4", "NX"),
    ]
    assert section_walk(ours) == section_walk(fixture_out("resident_two_decks"))


def test_an_unsupported_card_still_emits_the_sentinel():
    """A deck we cannot run must not leave SimNEC blocked in readLine().

    ``IS`` is the live example after issue #800 took ``PT`` and ``MP`` off
    this list (#799 took ``TL``): the portal dialect can carry it, but its
    semantics are NEC-4.2's insulated-wire model, which momwire does not have —
    so it takes the error path rather than silently solving a bare wire.

    Issue #829 (Ward's 2026-08-08 reply): the refusal now leads with an
    ``ERROR:`` line — token 0 exactly, which is what trips Execute's
    ``"NEC ERROR (1)"`` warning frame — with the oracle-shaped
    ``ERROR-NEC2C:`` line kept right after it for grep. Before #829 the
    prefix was chosen specifically to dodge that frame; Ward has since said
    the frame "should be fine" and that he intends to make the reader bail
    on it, so this test now pins the opposite of what it used to.
    """
    out, err = deck_frame(
        "CE insulation\n"
        "GW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\n"
        "GW 2 9 1. 0. -2.5 1. 0. 2.5 0.001\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "IS 0 1 1 9 2.3 0.001\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )
    text = "\n".join(out)
    assert NX_ECHO.search(text), "the NX sentinel is missing on the error path"
    assert "ERROR: IS" in text
    assert "ERROR-NEC2C: IS" in text
    assert any(line.split()[:1] == ["ERROR:"] for line in text.splitlines()), (
        "no line trips Execute's token-0 `ERROR:` warning frame"
    )
    assert err == []


# --------------------------------------------------------------------------
# issue #829: the `ERROR:` line must trip and ONLY trip on a real refusal
# --------------------------------------------------------------------------


def _first_tokens(text: str) -> list[str]:
    return [line.split()[0] for line in text.splitlines() if line.split()]


@pytest.mark.parametrize("name", ALL_NAMES)
def test_no_clean_fixture_carries_a_token_0_error_line(name):
    """The corpus-wide half of the token-0 pin: a healthy deck must never
    show Execute's warning frame — a stray ``ERROR:`` on a clean run would be
    a false alarm in the SimNEC UI.

    Walked against the committed oracle ``.out`` bytes themselves, not our
    own printout, because that is the file most exposed to accidental
    real-string drift (e.g. a future oracle capture, a hand edit) and the one
    a corpus-wide gate is for. The oracle's own literal ``ERROR-NEC2C:``
    stdin-EOF string (grammar doc §8) is a DIFFERENT token — it never
    collides with ``ERROR:`` — which is exactly why that shape was safe to
    reuse here.
    """
    assert "ERROR:" not in _first_tokens(fixture_out(name)), (
        f"{name}: a clean oracle fixture carries a token-0 `ERROR:` line"
    )


@pytest.mark.parametrize("name", REPRESENTATIVE)
def test_no_clean_regenerated_printout_carries_a_token_0_error_line(name):
    """Same pin, our side: a handful of clean decks run back through this
    engine must not produce the warning frame either."""
    assert "ERROR:" not in _first_tokens(printout(name)), (
        f"{name}: our own clean printout carries a token-0 `ERROR:` line"
    )


def test_patch_antenna_refusal_shows_why_nothing_loaded():
    """Stand-in for the issue's live-session gate (no SimNEC on this box).

    The live case (issue #829) was an EZNEC patch-antenna design: SimNEC
    forwarded an ``SP``/``SM`` surface-patch deck, the daemon refused it
    silently under the pre-#829 ``ERROR-NEC2C:``-only shape, and the user was
    left staring at an empty session with no indication why. This synthesizes
    the same refusal class — ``SP`` — through ``main`` exactly as the daemon
    receives it on stdin, and pins the three things that scenario needs:
    the deck exits cleanly (rc 0, daemon stays resident — no reason for a
    live session to die over one bad deck), the refusal names the offending
    card, and the ``ERROR:`` token-0 line is present to trip SimNEC's own
    warning frame instead of leaving the UI blank.
    """
    deck = (
        "CE patch antenna\n"
        "GW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "SP 0 0 0. 0. 0. 0. 0. 1.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\nNX\n"
    )
    rc, out, err = _run_main([], deck=deck)
    assert rc == 0, "the daemon must exit cleanly, not die on the bad deck"
    assert err == ""
    error_lines = [ln for ln in out.splitlines() if ln.split()[:1] == ["ERROR:"]]
    assert error_lines, "no token-0 `ERROR:` line — the user sees nothing again"
    assert "SP" in error_lines[0], f"the refusal does not name SP: {error_lines[0]!r}"
    assert NX_ECHO.search(out), "no NX sentinel on the error path"
    # Follow-up: re-run this scenario against a live SimNEC session on the
    # Windows box once Ward ships his reader bail-fix, to confirm the frame
    # actually surfaces to the user end to end (tracked as a note in #829,
    # not re-testable here — no SimNEC install on this machine).


# --------------------------------------------------------------------------
# numbers: momwire against itself, and one loose bound against the oracle
# --------------------------------------------------------------------------


def test_antenna_input_row_is_internally_consistent():
    """V = I·Z and Y = I/V and P = ½·Re(V·I*), read off the row's own columns.

    This is the identity a transposed real/imaginary pair breaks: the row
    still has 11 tokens and still parses, but the numbers stop agreeing.
    """
    for table in aip_tables(run_deck(fixture_deck("dipole_free_space"))[0]):
        for row in table:
            v = complex(float(row[2]), float(row[3]))
            i = complex(float(row[4]), float(row[5]))
            z = complex(float(row[6]), float(row[7]))
            y = complex(float(row[8]), float(row[9]))
            p = float(row[10])
            assert abs(i * z - v) <= 1e-3 * abs(v)
            assert abs(y - i / v) <= 1e-3 * abs(y)
            assert p == pytest.approx(0.5 * (v * i.conjugate()).real, rel=1e-3)


def test_swapping_the_current_columns_is_caught():
    """A mutation reviewers will try. Transposing fields 4 and 5 keeps the row
    shape and keeps every token parseable — only the identities above notice.
    """
    original = nec_portal.fmt_aip_row

    def transposed(tag, seg, voltage, current, impedance, admittance, power):
        return original(
            tag,
            seg,
            voltage,
            complex(current.imag, current.real),
            impedance,
            admittance,
            power,
        )

    nec_portal.fmt_aip_row = transposed
    try:
        table = aip_tables(run_deck(fixture_deck("dipole_free_space"))[0])[0]
    finally:
        nec_portal.fmt_aip_row = original
    row = table[0]
    v = complex(float(row[2]), float(row[3]))
    i = complex(float(row[4]), float(row[5]))
    z = complex(float(row[6]), float(row[7]))
    assert len(row) == 11  # still well-formed...
    assert abs(i * z - v) > 1e-3 * abs(v)  # ...and still wrong


def test_changing_a_section_header_is_caught():
    """The banner strings are what Execute's state machine arms on, so they
    are contract, not decoration."""
    original = nec_portal._AIP_HEADER
    nec_portal._AIP_HEADER = "                        --------- INPUT PARAMS ---------"
    try:
        ours, _err = run_deck(fixture_deck("dipole_free_space"))
    finally:
        nec_portal._AIP_HEADER = original
    assert section_walk(ours) != section_walk(fixture_out("dipole_free_space"))


def test_free_space_dipole_impedance_is_in_the_oracles_neighbourhood():
    """A smoke bound, not the differential harness: momwire's B-spline basis
    and nec2c's pulse basis disagree by a few percent on a 9-segment dipole
    and that is expected. 15% catches a wrong port, a wrong frequency, a
    missing ground, or a sign error."""
    ours = aip_tables(run_deck(fixture_deck("dipole_free_space"))[0])[0][0]
    theirs = aip_tables(fixture_out("dipole_free_space"))[0][0]
    z_ours = complex(float(ours[6]), float(ours[7]))
    z_theirs = complex(float(theirs[6]), float(theirs[7]))
    assert abs(z_ours - z_theirs) <= 0.15 * abs(z_theirs), (
        f"ours {z_ours} vs oracle {z_theirs}"
    )


def test_loaded_deck_spends_power_in_the_load():
    """LD 0 is a series R+L in the segment's current path, so the budget must
    show a structure loss and an efficiency below 100%."""
    text, _err = run_deck(fixture_deck("dipole_load_ld0"))
    budget = {
        line.split("=")[0].strip(): float(line.split("=")[1].split()[0])
        for line in text.splitlines()
        if "=" in line and ("POWER" in line or "LOSS" in line or "EFFICIENCY" in line)
    }
    assert budget["STRUCTURE LOSS"] > 0
    assert budget["INPUT POWER"] > budget["RADIATED POWER"] > 0
    assert 0 < budget["EFFICIENCY"] < 100
    assert budget["RADIATED POWER"] == pytest.approx(
        budget["INPUT POWER"] - budget["STRUCTURE LOSS"], rel=1e-3
    )


# --------------------------------------------------------------------------
# unit 3: the whole corpus, byte layout
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_NAMES)
def test_every_fixture_matches_the_oracle_column_layout(name):
    """The score the unit reports: every committed oracle printout, line for
    line and column for column.

    ``REPRESENTATIVE`` above keeps the diagnostics readable for the decks a
    reader is likely to be debugging; this one is the gate. Both are cheap —
    the whole corpus solves in about a second and a half.
    """
    ours = body_lines(printout(name))
    theirs = body_lines(fixture_out(name))
    assert len(ours) == len(theirs), (
        f"{name}: {len(ours)} body lines against the oracle's {len(theirs)}"
    )
    for i, (a, b) in enumerate(zip(ours, theirs, strict=True)):
        if "DIELECTRIC CONSTANT" in b:
            # The oracle glues the real and imaginary parts into one token, so
            # this line's "shape" is its value. It is an ignored section.
            continue
        assert layout_signature(a) == layout_signature(b), (
            f"{name} line {i}\n  ours   {a!r}\n  oracle {b!r}"
        )


@pytest.mark.parametrize("name", ALL_NAMES)
def test_every_fixture_walks_the_oracle_section_order(name):
    assert section_walk(printout(name)) == section_walk(fixture_out(name))


# --------------------------------------------------------------------------
# unit 3: RP / NE / NH are execute cards
# --------------------------------------------------------------------------


def test_rp_runs_the_group_and_the_trailing_xq_runs_nothing():
    """nec2c executes on reading RP, so the deck's own ``XQ`` is a bare echo.

    ``dipole_rp_pattern`` is EX / FR / RP / XQ and the oracle prints ONE run:
    the RP echo, the whole solve, the pattern, then the XQ echo immediately
    followed by NX. An engine that ran the XQ too would print a second
    ANTENNA INPUT PARAMETERS table and a second pattern, and SimNEC would read
    a 2x1 sensor matrix where it expected 1x1.
    """
    text = run_deck(fixture_deck("dipole_rp_pattern"))[0]
    assert text.count("ANTENNA INPUT PARAMETERS") == 1
    assert text.count("RADIATION PATTERNS") == 1
    echoes = re.findall(r"DATA CARD No:\s+\d+ (\w\w)", text)
    assert echoes == ["EX", "FR", "RP", "XQ", "NX"]
    # The XQ echo is followed straight away by the NX echo — no blank-line
    # wrapper, because nothing ran.
    lines = [ln for ln in text.splitlines() if "DATA CARD No:" in ln]
    body = text.splitlines()
    xq = next(i for i, ln in enumerate(body) if ln == lines[-2])
    assert body[xq + 1] == lines[-1]


@pytest.mark.parametrize(
    ("name", "cards"),
    [
        ("dipole_ne_nearfield", ["EX", "FR", "NE", "XQ", "NX"]),
        ("dipole_nh_nearfield", ["EX", "FR", "NH", "XQ", "NX"]),
    ],
)
def test_near_field_cards_execute_too(name, cards):
    text = run_deck(fixture_deck(name))[0]
    assert re.findall(r"DATA CARD No:\s+\d+ (\w\w)", text) == cards
    assert text.count("ANTENNA INPUT PARAMETERS") == 1


def test_a_second_xq_after_a_fresh_ex_still_runs():
    """The no-op rule must not swallow a legitimate second group."""
    text = run_deck(fixture_deck("two_source_sensor_lines"))[0]
    assert text.count("ANTENNA INPUT PARAMETERS") == 2


# --------------------------------------------------------------------------
# unit 3: patterns
# --------------------------------------------------------------------------


def pattern_rows(text: str) -> list[list[str]]:
    rows, armed = [], False
    for line in text.splitlines():
        parts = line.split()
        if parts[:2] == ["DEGREES", "DEGREES"]:
            armed = True
            continue
        if not armed:
            continue
        if len(parts) not in (11, 12):
            armed = False
            continue
        rows.append(parts)
    return rows


def test_pattern_grid_follows_the_rp_card():
    """``RP 0 7 13 1001 0 0 30 30 1000``: 7 thetas x 13 phis, theta fastest."""
    rows = pattern_rows(run_deck(fixture_deck("dipole_rp_pattern"))[0])
    assert len(rows) == 7 * 13
    assert [float(r[0]) for r in rows[:7]] == [0, 30, 60, 90, 120, 150, 180]
    assert {float(r[1]) for r in rows} == {30.0 * i for i in range(13)}
    assert float(rows[7][1]) == 30.0 and float(rows[7][0]) == 0.0


def test_pattern_peak_gain_matches_the_engines_far_field():
    """The printout's gain is the workbench's gain.

    ``MomwireEngine.far_field`` normalises by source input power —
    ``eta0*k^2/(8*pi*P_in)`` — and so does this printout. If the two ever
    drift apart, a user comparing a SimNEC pattern against the antennaknobs
    plot for the same design sees two different antennas.
    """
    rows = pattern_rows(run_deck(fixture_deck("dipole_rp_pattern"))[0])
    peak = max(float(r[4]) for r in rows)
    # A half-wave dipole in free space: 2.15 dBi, and momwire's 9-segment
    # B-spline reads a shade under.
    assert 1.9 <= peak <= 2.3, peak


def test_a_pattern_null_prints_the_floor_and_blanks_the_sense_column():
    """Both come from nec2c's |E|^2 <= 1e-20 test, and both must agree.

    A row that keeps its SENSE word but floors its gain (or the reverse) means
    the two thresholds have drifted apart, and ``Execute``'s ptr arithmetic
    then reads the E-field columns off by one on exactly the rows where the
    field is real.
    """
    for name in ("dipole_rp_pattern", "dipole_rp_crossed_quadrature"):
        for row in pattern_rows(run_deck(fixture_deck(name))[0]):
            floored = float(row[4]) <= -900.0
            assert floored == (len(row) == 11), f"{name}: {row}"


def test_average_power_gain_is_about_unity_for_a_lossless_antenna():
    """A free-space dipole radiates everything it is fed, so the pattern
    averaged over 4*pi steradians has to come out near 1 — which is only true
    if the gain normaliser, the solid-angle quadrature and the E-field
    prefactor all agree with each other."""
    for name in ("dipole_rp_pattern", "dipole_rp_crossed_quadrature"):
        line = next(
            ln
            for ln in run_deck(fixture_deck(name))[0].splitlines()
            if "AVERAGE POWER GAIN" in ln
        )
        average = float(line.split(":")[1].split()[0])
        solid = float(line.split("(")[1].split(")")[0])
        assert 0.9 <= average <= 1.1, line
        # A full sphere is 4*PI; the crossed deck only sweeps the upper
        # hemisphere, so 2*PI.
        assert solid == (4.0 if name == "dipole_rp_pattern" else 2.0)


def test_pattern_e_field_scales_with_the_requested_range():
    """RFLD is a real range, not decoration: doubling it halves every E field
    and moves the EXP(-JKR)/R line with it."""
    deck = fixture_deck("dipole_rp_pattern")
    near = pattern_rows(run_deck(deck)[0])
    far = pattern_rows(run_deck(deck.replace("30 30 1000", "30 30 2000"))[0])
    for a, b in zip(near, far, strict=True):
        if float(a[4]) <= -900.0:
            continue
        assert float(b[-4]) == pytest.approx(0.5 * float(a[-4]), rel=1e-3)
        # ...while the GAIN, which is range-independent, does not move.
        assert float(b[4]) == pytest.approx(float(a[4]), abs=0.01)


# --------------------------------------------------------------------------
# unit 3: near fields
# --------------------------------------------------------------------------


def near_field_rows(text: str) -> list[list[str]]:
    rows, armed = [], False
    for line in text.splitlines():
        parts = line.split()
        if parts[:3] == ["METERS", "METERS", "METERS"]:
            armed = True
            continue
        if not armed:
            continue
        if len(parts) != 9:
            armed = False
            continue
        rows.append(parts)
    return rows


def test_near_field_grid_varies_x_fastest_then_y_then_z():
    rows = near_field_rows(run_deck(fixture_deck("dipole_ne_nearfield"))[0])
    points = [(float(r[0]), float(r[1]), float(r[2])) for r in rows]
    assert points == [(x, 0.0, z) for z in (-1.0, 0.0, 1.0) for x in (-1.0, 0.0, 1.0)]


def test_near_field_off_the_conductor_tracks_the_oracle():
    """The claim the mixed-potential form is here to support.

    Every grid point a metre off the wire must match nec2c to a few percent in
    magnitude and a degree in phase — that is a real cross-engine near-field
    agreement, not a layout check. Points ON the conductor are excluded and
    documented (grammar doc §11): a point-source quadrature has no business
    being evaluated inside the source.
    """
    for name in ("dipole_ne_nearfield", "dipole_nh_nearfield"):
        ours = near_field_rows(run_deck(fixture_deck(name))[0])
        theirs = near_field_rows(fixture_out(name))
        assert len(ours) == len(theirs)
        checked = 0
        for a, b in zip(ours, theirs, strict=True):
            if float(a[0]) == 0.0:  # on the wire (the dipole lies on the z axis)
                continue
            live = max(float(b[3 + 2 * c]) for c in range(3))
            for component in range(3):
                magnitude = 3 + 2 * component
                mine, oracle = float(a[magnitude]), float(b[magnitude])
                if oracle <= 1e-4 * live:
                    # A component the symmetry kills. Both engines print their
                    # own numerical zero there (nec2c 2.4E-09 against our
                    # 1.1E-16) and neither number means anything; all that is
                    # testable is that the component IS dead.
                    assert mine <= 1e-4 * live, f"{name}: {a} / {b}"
                    continue
                assert mine == pytest.approx(oracle, rel=0.02), f"{name}: {a} / {b}"
                assert float(a[magnitude + 1]) == pytest.approx(
                    float(b[magnitude + 1]), abs=1.0
                ), f"{name} phase: {a} / {b}"
                checked += 1
        assert checked >= 6, f"{name}: only {checked} components compared"


def test_near_field_on_the_conductor_is_documented_not_trusted():
    """The one place the near field does NOT track the oracle.

    nec2c prints the impressed source field on a driven segment (1.8 V/m =
    1 V over a 0.5559 m segment). We evaluate the same integral the rest of
    the table uses, at a point inside the source. It lands in the same decade
    and with the same sign, which is as much as a regularised point-source sum
    can claim — pinned here so the limitation stays visible rather than
    drifting silently.
    """
    row = next(
        r
        for r in near_field_rows(run_deck(fixture_deck("dipole_ne_nearfield"))[0])
        if (float(r[0]), float(r[2])) == (0.0, 0.0)
    )
    assert 0.5 <= float(row[7]) <= 5.0, row  # oracle prints 1.8000E+00
    assert abs(float(row[8])) > 150.0  # ...at -180 degrees


def test_a_pec_ground_doubles_the_near_field_sources():
    """A near-field grid over PEC ground must see the image, and it can only
    do that if the image's CHARGE is negated along with its current."""
    deck = (
        "CE dipole over pec ground with a near field grid\n"
        "GW 1 9 0. 0. 2.0 0. 0. 7.0 0.001\n"
        "GE -1\nGN 1\nEX 0 1 5 0 1.\nFR 0 1 0 0 14.1 0\n"
        "NE 0 1 1 1 5. 0. 4.5 0. 0. 0.\n"
        "XQ\n"
    )
    with_ground = near_field_rows(run_deck(deck)[0])
    free = near_field_rows(run_deck(deck.replace("GE -1\nGN 1\n", "GE 0\n"))[0])
    assert len(with_ground) == len(free) == 1
    assert float(with_ground[0][7]) != pytest.approx(float(free[0][7]), rel=1e-3)


# --------------------------------------------------------------------------
# unit 3: NT networks
# --------------------------------------------------------------------------


def test_nt_source_current_is_the_segment_current_plus_the_network_current():
    """The identity the NT fixture exists to pin.

    ANTENNA INPUT PARAMETERS reports what the SOURCE delivers; CURRENTS AND
    LOCATION reports what flows in the segment; the difference is exactly what
    the NT branch draws. Reading the segment current into the impedance table
    (the obvious mistake) makes the driven-point impedance come out negative,
    which is what the oracle's own -1.0284E+02 network row looks like — and
    that row is a DIFFERENT table.
    """
    text = run_deck(fixture_deck("dipole_nt_network"))[0]
    # STRUCTURE EXCITATION DATA repeats the "No: No: REAL" header, so it is
    # ALSO an "aip table" to a header-only reader — and it comes first. The
    # deck has one execute group, so the real one is last. (Execute itself is
    # not fooled: it arms on the ANTENNA INPUT PARAMETERS banner, and the
    # differential harness's reader does the same.)
    source = complex(*(float(v) for v in aip_tables(text)[-1][0][4:6]))
    port_row = aip_tables(text)[0][1]  # STRUCTURE EXCITATION DATA, port one
    segment = complex(float(port_row[4]), float(port_row[5]))
    # NT 1 5 2 5 with Y11 = Y22 = j0.02 and Y12 = -j0.02, so the branch current
    # at port one is j0.02*(V1 - V2).
    v1, v2 = 1.0 + 0j, _network_port_voltage(text)
    branch = 0.02j * (v1 - v2)
    # 1e-4 is the printout's own resolution: five significant digits.
    assert source == pytest.approx(segment + branch, rel=1e-4)

    # The same current read off CURRENTS AND LOCATION is the INTERPOLATED
    # midpoint of the B-spline, not the Galerkin port unknown, so it agrees
    # only to about a percent (grammar doc §11.8). nec2c's pulse basis makes
    # the two one number and hides the distinction entirely.
    midpoint = next(
        complex(float(p[6]), float(p[7]))
        for p in (ln.split() for ln in text.splitlines())
        if len(p) == 10 and p[:2] == ["5", "1"]
    )
    assert abs(midpoint - segment) <= 0.01 * abs(source)


def _network_port_voltage(text: str) -> complex:
    """The gap voltage of the undriven NT port, off the network table."""
    rows = []
    armed = False
    for line in text.splitlines():
        if "STRUCTURE EXCITATION DATA" in line:
            armed = True
            continue
        if not armed:
            continue
        parts = line.split()
        # The header row is also 11 tokens ("TAG SEG VOLTAGE (VOLTS) ..."), so
        # arity alone does not identify a data row here.
        if len(parts) != 11 or not parts[0].isdigit():
            if rows:
                break
            continue
        rows.append(complex(float(parts[2]), float(parts[3])))
    return rows[0]


def test_nt_network_loss_is_zero_for_a_lossless_branch():
    """``NT`` with a purely imaginary Y absorbs nothing, so NETWORK LOSS must
    be zero and the whole input power must radiate."""
    text = run_deck(fixture_deck("dipole_nt_network"))[0]
    budget = {
        line.split("=")[0].strip(): float(line.split("=")[1].split()[0])
        for line in text.splitlines()
        if "=" in line and ("POWER" in line or "LOSS" in line or "EFFICIENCY" in line)
    }
    assert abs(budget["NETWORK LOSS"]) < 1e-9 * budget["INPUT POWER"]
    assert budget["EFFICIENCY"] == pytest.approx(100.0, abs=0.01)


def test_a_lossy_nt_branch_shows_up_as_network_loss():
    """The sign convention: a real Y in the branch absorbs power, and the
    budget must say so rather than crediting it to radiation."""
    deck = fixture_deck("dipole_nt_network").replace(
        "NT 1 5 2 5 0. 0.02 0. -0.02 0. 0.02",
        "NT 1 5 2 5 0.02 0. -0.02 0. 0.02 0.",
    )
    budget = {
        line.split("=")[0].strip(): float(line.split("=")[1].split()[0])
        for line in run_deck(deck)[0].splitlines()
        if "=" in line and ("POWER" in line or "LOSS" in line or "EFFICIENCY" in line)
    }
    assert budget["NETWORK LOSS"] > 0
    assert budget["EFFICIENCY"] < 100.0
    assert budget["RADIATED POWER"] == pytest.approx(
        budget["INPUT POWER"] - budget["STRUCTURE LOSS"] - budget["NETWORK LOSS"],
        rel=1e-3,
    )


def test_an_undriven_nt_port_floats_instead_of_shorting():
    """A segment with a network on it is CUT: its gap voltage is whatever
    balances the node, not zero. Shorting it (the unit-2 behaviour for any
    undriven port) would make the whole branch invisible."""
    text = run_deck(fixture_deck("dipole_nt_network"))[0]
    assert abs(_network_port_voltage(text)) > 0.1


# --------------------------------------------------------------------------
# issue #799: TL transmission lines
# --------------------------------------------------------------------------


def _network_data_rows(text: str) -> list[str]:
    """The NETWORK DATA block: every line between the banner and the blank
    run that ends it, headers included."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if "NETWORK DATA" in ln)
    out = []
    for line in lines[start + 1 :]:
        if not line.strip():
            break
        out.append(line)
    return out


def test_tl_prints_its_own_column_header_and_line_type():
    """The TL row is NOT an NT row: nec2c describes the CARD (z0, length, the
    two end shunts) under a header of its own, and closes the row with the
    LINE TYPE word. Both are checked against the committed oracle bytes rather
    than against a copy of our own constants."""
    ours = _network_data_rows(run_deck(fixture_deck("dipole_tl_network"))[0])
    theirs = _network_data_rows(fixture_out("dipole_tl_network"))
    assert ours[:3] == theirs[:3], "TL column header differs from the oracle's"
    assert "TRANSMISSION LINE" in ours[0]
    assert ours[3].endswith(" STRAIGHT")
    # The card's own numbers are echoed verbatim, so this row IS byte-equal.
    assert ours[3] == theirs[3]


def test_a_crossed_tl_is_a_negative_z0_echoed_as_its_magnitude():
    """``TL … -450. …`` prints ``4.5000E+02`` and ``CROSSED`` — the sign is a
    polarity inversion, not part of the impedance."""
    rows = _network_data_rows(run_deck(fixture_deck("dipole_tl_shunt_crossed"))[0])
    line = next(r for r in rows if r.rstrip().endswith("CROSSED"))
    assert line == next(
        r
        for r in _network_data_rows(fixture_out("dipole_tl_shunt_crossed"))
        if r.rstrip().endswith("CROSSED")
    )
    assert "4.5000E+02" in line and "-4.5" not in line


def test_a_mixed_deck_re_emits_the_header_when_the_row_kind_changes():
    """One NETWORK DATA banner, two header blocks, interleaved in CARD order.

    ``dipole_tl_shunt_crossed`` is TL then NT; nec2c carries the previous
    row's kind and re-prints the matching header whenever it changes.
    """
    ours = _network_data_rows(run_deck(fixture_deck("dipole_tl_shunt_crossed"))[0])
    assert ours == _network_data_rows(fixture_out("dipole_tl_shunt_crossed"))
    assert [i for i, r in enumerate(ours) if "-- FROM -" in r] == [0, 4]
    assert "TRANSMISSION LINE" in ours[0]
    assert "ADMITTANCE MATRIX ELEMENTS" in ours[4]


def test_a_zero_length_tl_echoes_the_distance_between_its_connection_points():
    """NEC reads length 0 as "the straight-line distance", and the printout
    echoes the RESOLVED number — probed against the oracle, whose row for this
    deck reads ``6.0000E+02  1.0000E+00`` for wires 1 m apart."""
    deck = fixture_deck("dipole_tl_network").replace(
        "TL 1 5 2 5 600. 2.5 0. 0. 0. 0.", "TL 1 5 2 5 600. 0. 0. 0. 0. 0."
    )
    row = _network_data_rows(run_deck(deck)[0])[3]
    assert row.split()[4:6] == ["6.0000E+02", "1.0000E+00"]


def test_the_portal_and_nec_import_translate_tl_the_same_way():
    """Two readers of the same card in one repo, held against each other.

    ``nec_import.NecTL`` is the network-mode translation the workbench uses;
    ``nec_portal.LineBranch`` is the daemon's. Crossed-means-negative-z0,
    zero-length-means-distance, and the end admittances have to mean the same
    thing in both or a deck imported one way and run the other silently
    disagrees.
    """
    from antennaknobs.nec_import import parse_nec
    from antennaknobs.nec_portal import DeckSolver, parse_deck

    body = (
        "GW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\n"
        "GW 2 9 1.0 0. -2.5 1.0 0. 2.5 0.001\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "TL 1 5 2 5 -450. 0. 1.e-3 0. 3.e-3 0.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )
    solver = DeckSolver(parse_deck("CE tl\n" + body))
    (_a, _b, branch, length) = solver.line_rows[0]
    imported = parse_nec(body, name="tl", network=True).tls[0]
    assert branch.z0 == imported.z0 == 450.0
    assert branch.crossed is imported.transposed is True
    assert length == pytest.approx(imported.length)
    assert length == pytest.approx(1.0)  # the wire spacing, not the card's 0
    assert (1.0 / branch.y_a.real, 1.0 / branch.y_b.real) == pytest.approx(
        (imported.shunt_r_a, imported.shunt_r_b)
    )


def test_tl_source_current_is_the_segment_current_plus_the_line_current():
    """The NT identity again, this time through a line's equivalent network.

    ANTENNA INPUT PARAMETERS reports what the SOURCE delivers, CURRENTS AND
    LOCATION what flows in the segment, and the difference is exactly what the
    line draws at that node — ``Y11·V1 + Y12·V2`` for the card's own 2×2. This
    is where the electrical length of the line has to be right: a
    quarter-wave 600 Ω line at 30 MHz has ``Y11 ≈ 0`` (cot βl ≈ 0) and
    ``|Y12| ≈ 1.7 mS``, so essentially the whole difference is the FAR end's
    voltage coming back through the line.
    """
    from antennaknobs.network_reduce import tl_admittance_2x2

    text = run_deck(fixture_deck("dipole_tl_network"))[0]
    source = complex(*(float(v) for v in aip_tables(text)[-1][0][4:6]))
    excitation = aip_tables(text)[0]
    v_far = complex(float(excitation[0][2]), float(excitation[0][3]))
    near = excitation[1]
    v_near = complex(float(near[2]), float(near[3]))
    segment = complex(float(near[4]), float(near[5]))

    wavelength = 299_792_458.0 / 30e6
    y = tl_admittance_2x2(600.0, 2.5, wavelength)
    assert abs(y[0, 0]) < 0.02 * abs(y[0, 1]), "not the quarter-wave case any more"
    branch = y[0, 0] * v_near + y[0, 1] * v_far
    # 1e-4 is the printout's own resolution: five significant digits.
    assert source == pytest.approx(segment + branch, rel=1e-4)


def test_a_lossless_tl_absorbs_nothing_but_shunt_conductance_does():
    """NETWORK LOSS is the whole TL power identity: an ideal line is a pure
    reactance chain and cannot absorb, while the card's end admittances can —
    and the budget must charge them rather than crediting radiation."""
    lossless = _power_budget(run_deck(fixture_deck("dipole_tl_network"))[0])
    assert abs(lossless["NETWORK LOSS"]) < 1e-9 * lossless["INPUT POWER"]
    assert lossless["EFFICIENCY"] == pytest.approx(100.0, abs=0.01)

    lossy = _power_budget(run_deck(fixture_deck("dipole_tl_shunt_crossed"))[0])
    assert lossy["NETWORK LOSS"] > 0
    assert lossy["RADIATED POWER"] == pytest.approx(
        lossy["INPUT POWER"] - lossy["STRUCTURE LOSS"] - lossy["NETWORK LOSS"],
        rel=1e-3,
    )


def _power_budget(text: str) -> dict[str, float]:
    return {
        line.split("=")[0].strip(): float(line.split("=")[1].split()[0])
        for line in text.splitlines()
        if "=" in line and ("POWER" in line or "LOSS" in line or "EFFICIENCY" in line)
    }


def test_a_half_wave_lossless_tl_is_refused_by_name():
    """The one TL shape that has no admittance matrix at all: at k·λ/2 the
    line is a through-connection its nodal description cannot spell (sinh γl =
    0), and nec2c's netwk() divides by the same sinh. Refusing it names the
    card; guessing would print a table of infinities.

    The bar is deliberately at machine zero, not at "near a half wave": a line
    a part in 10^7 off length has a large but perfectly finite admittance, and
    printing it is the honest answer.
    """
    half_wave = 299_792_458.0 / 30e6 / 2  # 4.996540966666666 m
    deck = fixture_deck("dipole_tl_network").replace(
        "TL 1 5 2 5 600. 2.5 0. 0. 0. 0.",
        f"TL 1 5 2 5 600. {half_wave!r} 0. 0. 0. 0.",
    )
    text = run_deck(deck)[0]
    assert "ERROR-NEC2C: " in text
    assert "TL" in text
    assert NX_ECHO.search(text), "no NX sentinel on the error path"


# --------------------------------------------------------------------------
# issue #800: MP, the multicore hint SimNEC emits by itself
# --------------------------------------------------------------------------

MP_ADVISORY = "MP: multiProcessor 16 32"


def test_mp_deck_runs_instead_of_being_refused():
    """The reason the card had to land: SimNEC appends MP on structure SIZE
    alone (``NECSource.constructNECFile``, once ``sum(Wire.numSegments)``
    reaches ``getMPInfo()[0]``, default 256), so a big array arrives carrying
    one whether or not anybody asked. Refusing it refused the deck."""
    text = printout("dipole_mp_multiprocessor")
    assert "ERROR-NEC2C" not in text
    assert "ANTENNA INPUT PARAMETERS" in text


def test_mp_echo_and_advisory_are_the_oracles_bytes():
    """Both lines the card produces, against the committed oracle printout.

    The echo is layout — four integer fields, ``16`` and ``32`` in the first
    two — and the advisory is a literal, at column 0, so both can be compared
    verbatim rather than structurally.
    """
    ours = printout("dipole_mp_multiprocessor")
    theirs = fixture_out("dipole_mp_multiprocessor")

    echo = next(ln for ln in theirs.splitlines() if " MP" in ln.split("No:")[-1])
    assert echo in ours, f"our echo differs from the oracle's:\n  {echo!r}"
    assert echo.split()[4:6] == ["MP", "16"], echo

    assert MP_ADVISORY in theirs.splitlines(), "the fixture lost its advisory"
    assert MP_ADVISORY in ours.splitlines()


def test_mp_advisory_sits_between_the_environment_and_matrix_timing():
    """Its position — and the extra blank it carries — are the contract.

    nec2c prints the line straight after the ANTENNA ENVIRONMENT block with
    one blank of its own, so a multiprocessing run shows THREE blanks before
    MATRIX TIMING where a plain one shows two. Checked on both sides.
    """
    for text in (
        printout("dipole_mp_multiprocessor"),
        fixture_out("dipole_mp_multiprocessor"),
    ):
        lines = text.splitlines()
        index = lines.index(MP_ADVISORY)
        assert lines[index - 1].strip() == "FREE SPACE"
        assert lines[index + 1 : index + 4] == ["", "", ""]
        assert "MATRIX TIMING" in lines[index + 4]


def test_a_single_processor_mp_echoes_but_says_nothing():
    """``MP 1 32`` is still a card: it echoes, and prints no advisory. That
    threshold is why the corpus carries both forms."""
    ours = printout("dipole_mp_single_process")
    theirs = fixture_out("dipole_mp_single_process")
    assert "multiProcessor" not in ours
    assert "multiProcessor" not in theirs
    assert any(" MP" in ln and "DATA CARD No:" in ln for ln in ours.splitlines())


def test_mp_changes_nothing_but_the_card_lines():
    """The whole point of treating it as advisory, asserted rather than
    assumed: ``dipole_mp_multiprocessor`` IS ``dipole_free_space`` plus one
    card, and once the echo, the advisory and the shifted card ordinals are
    removed the two printouts are identical — ours and the oracle's alike.
    """

    def stripped(text: str) -> list[str]:
        """``body_lines`` — so the live FILL timing goes with the blanks and
        the banner — minus the MP card's own two lines and the card ordinals."""
        out = []
        for line in body_lines(text):
            if "multiProcessor" in line:
                continue
            if "DATA CARD No:" in line:
                # Inserting a card renumbers every echo after it, so the
                # ordinal goes; the MP echo itself goes with it.
                _ordinal, rest = line.split("No:")[1].strip().split(maxsplit=1)
                if rest.split()[0] != "MP":
                    out.append(rest)
                continue
            out.append(line)
        return out

    for plain, with_mp in (
        (printout("dipole_free_space"), printout("dipole_mp_multiprocessor")),
        (fixture_out("dipole_free_space"), fixture_out("dipole_mp_multiprocessor")),
    ):
        assert stripped(with_mp) == stripped(plain)


def test_mp_reprints_once_per_matrix_rebuild():
    """An FR sweep rebuilds per frequency, and the advisory goes with it."""
    deck = fixture_deck("dipole_fr_sweep").replace(
        "FR 0 3 0 0 28. 1.", "MP 16 32\nFR 0 3 0 0 28. 1."
    )
    text = run_deck(deck)[0]
    assert text.count("MATRIX TIMING") == 3
    assert text.count(MP_ADVISORY) == 3


def test_mp_is_not_an_arming_card():
    """Measured on the oracle: ``... XQ / MP 4 8 / XQ`` prints one block, not
    two. An MP alone does not make the next execute card a real run."""
    text = run_deck(
        "CE mp arming\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        "EX 0 1 5 0 1.\nFR 0 1 0 0 30. 0\nXQ\nMP 4 8\nXQ\n"
    )[0]
    assert text.count("ANTENNA INPUT PARAMETERS") == 1
    assert text.count("MATRIX TIMING") == 1
    # ...and both execute cards are still echoed.
    assert len(re.findall(r"DATA CARD No:\s+\d+ XQ", text)) == 2


@pytest.mark.parametrize(
    ("card", "advisory"),
    [
        ("MP -3 -9", "MP: multiProcessor -3 -9"),
        # Measured on the oracle: -1 is NOT the silent single-processor case.
        # Its advisory test reads the field unsigned, so every negative prints
        # (and every negative also hangs it).
        ("MP -1 32", "MP: multiProcessor -1 32"),
    ],
)
def test_a_hostile_mp_never_hangs_the_daemon(card, advisory):
    """``MP -3 -9`` makes the ORACLE spin forever (measured: killed at 25 s).

    ``Execute.processResponse`` has no timeout, so an engine that inherited
    that behaviour would hang the SimNEC UI. This one echoes the card, prints
    its advisory with the numbers as given, finishes the run, and emits the
    sentinel.
    """
    out, err = deck_frame(
        "CE hostile mp\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        f"EX 0 1 5 0 1.\n{card}\nFR 0 1 0 0 30. 0\nXQ\n"
    )
    text = "\n".join(out)
    assert "ERROR-NEC2C" not in text
    assert advisory in text
    assert "ANTENNA INPUT PARAMETERS" in text
    assert NX_ECHO.search(text)
    assert err == []


# --------------------------------------------------------------------------
# issue #800: PT, the current-print toggle
# --------------------------------------------------------------------------


def currents_tables(text: str) -> list[list[list[str]]]:
    """The CURRENTS AND LOCATION rows, tokenised, one list per table.

    Ten tokens per row, which is what ends the table for a reader; the seg and
    tag numbers are fields 0 and 1. A ``YY`` deck puts its ``-YY`` row inside
    this table, ahead of the segments, so that one line is stepped over rather
    than read as the end of it.
    """
    tables: list[list[list[str]]] = []
    collecting = False
    for line in text.splitlines():
        parts = line.split()
        if parts[:1] == ["-YY"]:
            continue
        if parts[1:4] == ["CURRENTS", "AND", "LOCATION"]:
            tables.append([])
            collecting = False
            continue
        if parts[:3] == ["No:", "No:", "X"]:
            collecting = True
            continue
        if not collecting:
            continue
        if len(parts) != 10:
            collecting = False
            continue
        tables[-1].append(parts)
    return tables


def test_pt_minus_one_removes_the_whole_currents_section():
    """Not just the rows: the banner, the note, the blank and both column
    headers go too — which is why ``dipole_pt_toggle`` has one CURRENTS AND
    LOCATION section for its two runs, on both engines."""
    for text in (printout("dipole_pt_toggle"), fixture_out("dipole_pt_toggle")):
        assert text.count("CURRENTS AND LOCATION") == 1
        assert text.count("ANTENNA INPUT PARAMETERS") == 2


def test_the_yy_report_survives_pt_minus_one():
    """The load-bearing detail. ``-YY`` is the row ``addYYLine`` parses, so a
    suppression that swallowed it would break SimNEC's Y path — and the oracle
    does not swallow it: the line lands directly after the last ANTENNA INPUT
    PARAMETERS row, with no blank and no table around it."""
    for text in (printout("dipole_pt_toggle"), fixture_out("dipole_pt_toggle")):
        lines = text.splitlines()
        index = next(i for i, ln in enumerate(lines) if ln.split()[:1] == ["-YY"])
        # The row above is an 11-token ANTENNA INPUT PARAMETERS row, not a
        # currents-table header.
        assert len(lines[index - 1].split()) == 11
        assert lines[index + 1] == ""
        assert len(yy_rows(text)) == 2, "one -YY row per run, suppressed or not"


def test_pt_minus_two_restores_the_table():
    """``PT`` is a toggle held across execute cards, not a per-run flag: the
    second run of ``dipole_pt_toggle`` prints the full 18-segment table."""
    ours = currents_tables(printout("dipole_pt_toggle"))
    theirs = currents_tables(fixture_out("dipole_pt_toggle"))
    assert [len(t) for t in ours] == [len(t) for t in theirs] == [18]


def test_pt_zero_limits_the_table_to_the_named_tags_segments():
    """``PT 0 2 1 3`` prints tag 2's segments 1-3 — global 10 to 12. The
    addressing is EX's, so an absolute reading would print 1-3 instead and
    still look perfectly plausible."""
    ours = currents_tables(printout("dipole_pt_segment_range"))
    theirs = currents_tables(fixture_out("dipole_pt_segment_range"))
    assert len(ours) == len(theirs) == 1
    for rows in (ours[0], theirs[0]):
        assert [(r[0], r[1]) for r in rows] == [("10", "2"), ("11", "2"), ("12", "2")]


def test_an_all_zero_pt_range_prints_everything():
    """Measured on the oracle: ``PT 0 1 0 0`` and ``PT 0 2 0 0`` both print the
    whole table, so an empty range is "no restriction", not "no rows"."""
    for tag in (1, 2):
        deck = fixture_deck("dipole_pt_segment_range").replace(
            "PT 0 2 1 3", f"PT 0 {tag} 0 0"
        )
        assert len(currents_tables(run_deck(deck)[0])[0]) == 18


@pytest.mark.parametrize("flag", [-2, 1, 2, 3])
def test_the_other_pt_flags_print_the_ordinary_table(flag):
    """Stock NEC-2's receiving-pattern and normalised-current formats. This
    ae6ty build prints the plain full table for all of them — diffed against
    the same deck with no PT card at all — so they are read as no restriction
    rather than as a layout nobody has seen."""
    base = fixture_deck("dipole_pt_segment_range").replace("PT 0 2 1 3\n", "")
    deck = fixture_deck("dipole_pt_segment_range").replace("PT 0 2 1 3", f"PT {flag}")
    plain = [ln for ln in body_lines(run_deck(base)[0]) if "DATA CARD" not in ln]
    ours = [ln for ln in body_lines(run_deck(deck)[0]) if "DATA CARD" not in ln]
    assert ours == plain


def test_pt_is_not_an_arming_card():
    """It changes what a run prints, not what a run computes, so it cannot
    make a spent ``XQ`` into a fresh execution."""
    text = run_deck(
        "CE pt arming\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        "EX 0 1 5 0 1.\nFR 0 1 0 0 30. 0\nXQ\nPT -1\nXQ\n"
    )[0]
    assert text.count("ANTENNA INPUT PARAMETERS") == 1
    assert text.count("CURRENTS AND LOCATION") == 1


# --------------------------------------------------------------------------
# issue #800 (tail): GD, the additional-ground-parameters card
# --------------------------------------------------------------------------

# The two committed pairs: (with the card, the identical deck without it).
GD_PAIRS = (
    ("dipole_gd_second_medium", "dipole_pec_ground"),
    ("dipole_gd_cliff_sommerfeld", "dipole_sommerfeld_ground"),
)


def test_gd_deck_runs_instead_of_being_refused():
    """The reason the card had to land: SimNEC's EZNEC-derived examples
    (``Cardioid (EZNEC).ssn``, ``4-square (EZNEC).ssn``) carry a ``GD`` and
    ``NECSource`` forwards it, so refusing it failed those decks outright and
    the live session read back fabricated R = 0 / X = 0."""
    for name, _base in GD_PAIRS:
        text = printout(name)
        assert "ERROR-NEC2C" not in text, name
        assert "ANTENNA INPUT PARAMETERS" in text, name


@pytest.mark.parametrize(("name", "_base"), GD_PAIRS)
def test_gd_echo_is_the_oracles_bytes(name, _base):
    """The whole of the card's printed output, verbatim.

    ``dipole_gd_cliff_sommerfeld`` is the one that matters here: its card
    carries all four reals (``5. .001 20. -2.``), so the echo pins EPSR2,
    SIG2, CLT *and* CHT in their card-order columns. The Cardioid's own form
    leaves the last two at zero and would not.
    """
    ours = printout(name)
    theirs = fixture_out(name)
    echo = next(ln for ln in theirs.splitlines() if " GD" in ln.split("No:")[-1])
    assert echo in ours, f"our echo differs from the oracle's:\n  {echo!r}"
    assert echo.split()[4] == "GD"


def test_the_cliff_gd_echo_carries_all_four_reals_in_card_order():
    """``GD 0 0 0 0 5. .001 20. -2.`` -> EPSR2, SIG2, CLT, CHT, then zeros.

    Read off the oracle's own ``RP 2`` printout, which names them:
    ``EDGE DISTANCE= 20.00 METERS`` / ``HEIGHT= -2.00 METERS`` /
    ``RELATIVE DIELECTRIC CONST= 5.000`` / ``GROUND CONDUCTIVITY= 0.001``.
    """
    for text in (
        printout("dipole_gd_cliff_sommerfeld"),
        fixture_out("dipole_gd_cliff_sommerfeld"),
    ):
        echo = next(ln for ln in text.splitlines() if " GD" in ln.split("No:")[-1])
        reals = [float(v) for v in echo.split()[9:]]
        assert reals == [5.0, 0.001, 20.0, -2.0, 0.0, 0.0], echo
        assert [int(v) for v in echo.split()[5:9]] == [0, 0, 0, 0], echo


@pytest.mark.parametrize(("name", "_base"), GD_PAIRS)
def test_gd_adds_no_line_to_the_antenna_environment_block(name, _base):
    """Probed for and not there — including under ``GN 2``, where a second
    medium is the likeliest place an announcement would have appeared."""
    for text in (printout(name), fixture_out(name)):
        lines = text.splitlines()
        start = next(i for i, ln in enumerate(lines) if "ANTENNA ENVIRONMENT" in ln)
        end = next(i for i, ln in enumerate(lines) if "MATRIX TIMING" in ln)
        block = " ".join(lines[start:end]).upper()
        assert "SECOND MEDIUM" not in block, block
        assert "CLIFF" not in block, block
        assert "MEDIUM 2" not in block, block


@pytest.mark.parametrize(("name", "base"), GD_PAIRS)
def test_gd_changes_nothing_but_its_own_echo(name, base):
    """Asserted rather than assumed, exactly as ``MP`` is.

    Each fixture IS its base deck plus one card. Strip the ``GD`` echo and
    the ordinals it shifts and the two printouts are identical — ours and the
    oracle's alike. If that ever stops being true, ``GD`` has become physics
    and this engine is wrong to record it and move on.
    """

    def stripped(text: str) -> list[str]:
        out = []
        for line in body_lines(text):
            if "DATA CARD No:" in line:
                _ordinal, rest = line.split("No:")[1].strip().split(maxsplit=1)
                if rest.split()[0] != "GD":
                    out.append(rest)
                continue
            out.append(line)
        return out

    for plain, with_gd in (
        (printout(base), printout(name)),
        (fixture_out(base), fixture_out(name)),
    ):
        assert stripped(with_gd) == stripped(plain)


def test_gd_is_not_an_arming_card():
    """Measured on the oracle: ``... XQ / GD 2 0 0 0 13. .005 0. 0. / XQ``
    prints one block, not two."""
    text = run_deck(
        "CE gd arming\nGW 1 9 0. 0. 0.5 0. 0. 5.0 0.001\nGE 1\nGN 1\n"
        "EX 0 1 1 0 1.\nFR 0 1 0 0 14.1 0\nXQ\nGD 2 0 0 0 13. .005 0. 0.\nXQ\n"
    )[0]
    assert text.count("ANTENNA INPUT PARAMETERS") == 1
    assert text.count("MATRIX TIMING") == 1
    # ...and both execute cards are still echoed.
    assert len(re.findall(r"DATA CARD No:\s+\d+ XQ", text)) == 2


def test_the_comma_delimited_gd_simnec_sends_parses_like_the_spaced_form():
    """``NECSource`` writes the card comma-delimited — ``GD
    2,0,0,0,13.,.005,0.,0.`` is the literal Cardioid line. Measured identical
    to the spaced form on the oracle; identical here too."""
    head = "CE gd commas\nGW 1 9 0. 0. 0.5 0. 0. 5.0 0.001\nGE 1\nGN 1\n"
    tail = "EX 0 1 1 0 1.\nFR 0 1 0 0 14.1 0\nXQ\n"
    commas = run_deck(head + "GD 2,0,0,0,13.,.005,0.,0.\n" + tail)[0]
    spaces = run_deck(head + "GD 2 0 0 0 13. .005 0. 0.\n" + tail)[0]
    assert body_lines(commas) == body_lines(spaces)
    assert "ERROR-NEC2C" not in commas


def test_a_bare_gd_is_a_card_like_any_other():
    """The oracle echoes ``GD`` with four zero integers and six zero reals and
    runs the deck; nothing here may trip over the missing fields."""
    text = run_deck(
        "CE bare gd\nGW 1 9 0. 0. 0.5 0. 0. 5.0 0.001\nGE 1\nGN 1\nGD\n"
        "EX 0 1 1 0 1.\nFR 0 1 0 0 14.1 0\nXQ\n"
    )[0]
    assert "ERROR-NEC2C" not in text
    echo = next(ln for ln in text.splitlines() if " GD" in ln.split("No:")[-1])
    assert [float(v) for v in echo.split()[5:]] == [0.0] * 10, echo


_CLIFF_HEAD = (
    "CE gd cliff pattern\nGW 1 9 0. 0. 0.5 0. 0. 5.0 0.001\nGE 1\n"
    "GN 0 0 0 0 13. .005\nGD 0 0 0 0 5. .001 20. -2.\n"
    "EX 0 1 1 0 1.\nFR 0 1 0 0 14.1 0\n"
)


def test_the_rp_modes_that_would_use_a_gd_are_still_refused():
    """The fidelity gate, narrowed by issue #802 to the modes still out.

    NEC-2 reaches the second medium in the far field ALONE, and there only
    through ``RP``'s cliff and ground-screen modes. Two of those five now run
    (see the tests below); these four do not, and for reasons that are not the
    cliff's:

    * ``RP 1`` is the surface wave — a different banner (``RADIATED FIELDS
      NEAR GROUND``), a different row shape carrying ``E(RADIAL)``, and a
      ``GFLD`` this engine has no equivalent of;
    * ``RP 4``-``6`` all want a radial wire ground screen, which momwire
      cannot model. That is the same reason ``GN``'s ``NRADL`` field is
      refused, and running one as bare ground would be a wrong answer rather
      than a refusal. 5 and 6 carry a cliff too, but the screen is what stops
      them.

    Issue #829: every refused mode must also lead with a token-0 ``ERROR:``
    line so SimNEC's ``"NEC ERROR (1)"`` warning frame fires.
    """
    for mode in (1, 4, 5, 6):
        text = run_deck(_CLIFF_HEAD + f"RP {mode} 3 3 1001 0 0 30 30 1000\nXQ\n")[0]
        assert f"RP mode {mode} is not supported" in text, mode
        assert NX_ECHO.search(text), mode
        error_lines = [ln for ln in text.splitlines() if ln.split()[:1] == ["ERROR:"]]
        assert error_lines, mode
        assert f"RP mode {mode}" in error_lines[0], mode
        # A refusal must not leave half a report behind it either.
        assert "FAR FIELD GROUND PARAMETERS" not in text, mode
    # ...and the mode SimNEC actually writes runs, second medium or not.
    text = run_deck(_CLIFF_HEAD + "RP 0 3 3 1001 0 0 30 30 1000\nXQ\n")[0]
    assert "ERROR-NEC2C" not in text
    assert "RADIATION PATTERNS" in text
    assert "FAR FIELD GROUND PARAMETERS" not in text


def test_the_rp_cliff_modes_consume_the_gd_instead_of_refusing_it():
    """Issue #802: the two modes a ``GD`` is FOR now run.

    They were refused with 1 and 4-6 until #802, which was honest but left
    Ward's EZNEC-derived examples — whose cliff parameters land on ``RP 3`` —
    with no answer at all. Each must now print the block the oracle prints,
    name the right cliff in it, and echo the card's own four numbers into it
    in card order.
    """
    for mode, word in ((2, "LINEAR"), (3, "CIRCULAR")):
        text = run_deck(_CLIFF_HEAD + f"RP {mode} 3 3 1001 0 0 30 30 1000\nXQ\n")[0]
        assert "ERROR-NEC2C" not in text, mode
        assert "FAR FIELD GROUND PARAMETERS" in text, mode
        assert f"--- {word} CLIFF ---" in text, mode
        assert "RADIATION PATTERNS" in text, mode
        assert "EDGE DISTANCE=     20.00 METERS" in text, mode
        assert "HEIGHT=     -2.00 METERS" in text, mode
        assert "RELATIVE DIELECTRIC CONST=      5.000" in text, mode
        assert "GROUND CONDUCTIVITY=      0.001 MHOS" in text, mode


def test_the_second_medium_actually_moves_the_cliff_modes_gains():
    """Lifting the refusal is only worth it if the card now changes an answer.

    Same deck, same geometry, same ground — one digit of the ``RP`` card
    apart. ``RP 0`` cannot see the second medium at all, so its table is the
    control; ``RP 2`` and ``RP 3`` must both differ from it, and from EACH
    OTHER, because a straight edge and a circular one only agree along the
    azimuth that crosses both.

    The theta grid has to reach grazing to say anything. The reflection point
    of a segment at height ``z`` is ``z·tan(theta)`` out, so this 5 m vertical
    does not reach a 20 m edge until about 76 degrees — a 0/30/60 sweep sees a
    flat world and would pass this test with the card ignored.
    """

    def gains(mode):
        text = run_deck(_CLIFF_HEAD + f"RP {mode} 4 3 1001 0 0 28 30 1000\nXQ\n")[0]
        rows, armed = {}, False
        for line in text.splitlines():
            parts = line.split()
            if parts[:2] == ["DEGREES", "DEGREES"]:
                armed = True
            elif armed and len(parts) in (11, 12):
                rows[(float(parts[0]), float(parts[1]))] = float(parts[4])
            elif armed:
                armed = False
        return rows

    flat, linear, circular = gains(0), gains(2), gains(3)
    assert set(flat) == set(linear) == set(circular)
    assert linear != flat, "RP 2 read the second medium and nothing moved"
    assert circular != flat, "RP 3 read the second medium and nothing moved"
    assert linear != circular, "a linear and a circular cliff cannot agree everywhere"


def test_a_cliff_mode_with_no_second_medium_still_prints_the_block():
    """``RDPAT`` prints FAR FIELD GROUND PARAMETERS on the MODE, not on the
    card. A cliff mode whose deck never sent a ``GD`` and never put the
    fields on its ``GN`` gets the block with four zeros in it — measured on
    the oracle, and the reason :func:`_far_field_ground_lines` renders a
    missing record rather than skipping the block."""
    text = run_deck(
        "CE cliff mode with no gd\nGW 1 9 0. 0. 0.5 0. 0. 5.0 0.001\nGE 1\nGN 1\n"
        "EX 0 1 1 0 1.\nFR 0 1 0 0 14.1 0\nRP 2 3 2 1001 0 0 30 90 1000\nXQ\n"
    )[0]
    assert "ERROR-NEC2C" not in text
    assert "--- LINEAR CLIFF ---" in text
    assert "EDGE DISTANCE=      0.00 METERS" in text
    assert "RELATIVE DIELECTRIC CONST=      0.000" in text


# --------------------------------------------------------------------------
# issue #802: RFLD = 0, the gain-only form
# --------------------------------------------------------------------------


def _pattern_rows(text: str) -> list[list[str]]:
    """Every RADIATION PATTERNS data row, as raw token lists."""
    rows, armed = [], False
    for line in text.splitlines():
        parts = line.split()
        if parts[:2] == ["DEGREES", "DEGREES"]:
            armed = True
        elif armed and len(parts) in (11, 12):
            rows.append(parts)
        elif armed:
            armed = False
    return rows


def test_rfld_zero_drops_the_range_header_and_keeps_the_gain():
    """The gain-only form, against the same deck read out at 1000 m.

    Two NEC-2 thresholds are both spelt ``1e-20`` and only come apart here.
    ``DB10`` clamps the LINEAR POWER GAIN, which never depended on the
    range — so the three gain columns must be identical between the two runs,
    to the printed digit. The blank-SENSE test clamps the field as ``FFLD``
    returns it, BEFORE the range scaling — so it must reach the same verdict
    on both runs even though the printed E columns differ by a factor of
    ``RFLD``, three decades here.

    An engine that floored on the printed field instead would pass at 1000 m
    and quietly grow lobes in its own nulls at ``RFLD = 0``.
    """
    head = (
        "CE gain only\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        "EX 0 1 5 0 1.\nFR 0 1 0 0 30. 0\n"
    )
    at_range = run_deck(head + "RP 0 5 3 1001 0 0 45 45 1000\nXQ\n")[0]
    gain_only = run_deck(head + "RP 0 5 3 1001 0 0 45 45 0\nXQ\n")[0]

    # Shape: the RANGE / EXP(-JKR)/R pair is printed at a range and not at all
    # without one, and it is the ONLY line that leaves.
    assert "RANGE:" in at_range and "EXP(-JKR)/R:" in at_range
    assert "RANGE:" not in gain_only and "EXP(-JKR)/R:" not in gain_only
    assert "RADIATION PATTERNS" in gain_only
    assert len(at_range.splitlines()) - len(gain_only.splitlines()) == 3

    ranged, bare = _pattern_rows(at_range), _pattern_rows(gain_only)
    assert len(ranged) == len(bare) == 15
    for a, b in zip(ranged, bare, strict=True):
        assert len(a) == len(b), f"the SENSE column changed with the range: {a} / {b}"
        # theta, phi, VERTC, HORIZ, TOTAL — none of them see the range.
        assert a[:5] == b[:5], f"a gain column moved with the range: {a} / {b}"
        # ...and E goes up by exactly RFLD, the 1/r the range header carried.
        e_at, e_bare = float(a[-4]), float(b[-4])
        if e_at:
            assert e_bare / e_at == pytest.approx(1000.0, rel=1e-3), (a, b)


# --------------------------------------------------------------------------
# unit 3: robustness — the daemon must survive anything on stdin
# --------------------------------------------------------------------------

BAD_DECKS = {
    "a card nobody has ever seen": (
        "CE bogus\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        "ZZ 1 2 3\nEX 0 1 5 0 1.\nFR 0 1 0 0 30. 0\nXQ\n",
        "ZZ",
    ),
    "a non-numeric field": (
        "CE malformed\nGW 1 9 0. 0. -2.5 0. 0. banana 0.001\nGE 0\n"
        "EX 0 1 5 0 1.\nFR 0 1 0 0 30. 0\nXQ\n",
        "banana",
    ),
    "a one-letter mnemonic": (
        "CE short mnemonic\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        "G\nEX 0 1 5 0 1.\nFR 0 1 0 0 30. 0\nXQ\n",
        "MNEMONIC",
    ),
    "a zero-segment wire": (
        "CE zero segments\nGW 1 0 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        "EX 0 1 5 0 1.\nFR 0 1 0 0 30. 0\nXQ\n",
        "ERROR-NEC2C",
    ),
    "a segment that does not exist": (
        "CE bad segment\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        "EX 0 1 99 0 1.\nFR 0 1 0 0 30. 0\nXQ\n",
        "out of range",
    ),
    "no excitation at all": (
        "CE undriven\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\nFR 0 1 0 0 30. 0\nXQ\n",
        "no EX card",
    ),
    "a fractional MP field": (
        # The oracle refuses this one too, with NON-NUMERICAL CHARACTER '.' IN
        # INTEGER FIELD — MP's two fields are #Proc and blockSize and neither
        # has a fractional reading.
        "CE bad mp\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        "EX 0 1 5 0 1.\nMP 2.7 8.3\nFR 0 1 0 0 30. 0\nXQ\n",
        "MP field",
    ),
    "an MP with a word in it": (
        "CE worded mp\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        "EX 0 1 5 0 1.\nMP lots fast\nFR 0 1 0 0 30. 0\nXQ\n",
        "lots",
    ),
    "a GD with a word in it": (
        # The ORACLE's free-format reader silently SKIPS a non-numeric token
        # and shifts the rest left, so `GD 2 0 0 0 marsh .005 0. 0.` echoes
        # .005 as EPSR2 — a wrong answer dressed as a right one. This engine
        # names the token instead, on the same error path every other card
        # uses, and still emits the sentinel.
        "CE worded gd\nGW 1 9 0. 0. 0.5 0. 0. 5.0 0.001\nGE 1\nGN 1\n"
        "GD 2 0 0 0 marsh .005 0. 0.\nEX 0 1 1 0 1.\nFR 0 1 0 0 14.1 0\nXQ\n",
        "marsh",
    ),
    "a current source we do not model": (
        "CE ex type 6\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\n"
        "EX 6 1 5 0 1.\nFR 0 1 0 0 30. 0\nXQ\n",
        "EX type 6",
    ),
}


@pytest.mark.parametrize(("label", "case"), sorted(BAD_DECKS.items()))
def test_a_bad_deck_reports_and_still_emits_the_sentinel(label, case):
    """Whatever is wrong, the NX echo goes out.

    ``Execute.processResponse`` blocks in ``readLine()`` with no timeout
    (grammar doc §2, §10.1). A replacement engine that dies, or that reports
    an error and forgets the sentinel, hangs the SimNEC UI rather than showing
    a message — which is strictly worse than a wrong answer.

    Issue #829 (Ward's 2026-08-08 reply): every refusal now also trips
    Execute's ``"NEC ERROR (1)"`` warning frame on purpose (token 0 exactly
    ``ERROR:``), so the user sees *why* nothing loaded instead of staring at
    a session that looks like it just did nothing. That used to be exactly
    what this test forbade; #829 reverses the call.
    """
    deck, marker = case
    out, err = deck_frame(deck)
    text = "\n".join(out)
    assert NX_ECHO.search(text), f"{label}: no NX sentinel"
    assert marker in text, f"{label}: error does not mention {marker!r}:\n{text[-500:]}"
    assert any(line.split()[:1] == ["ERROR:"] for line in text.splitlines()), (
        f"{label}: no line trips Execute's token-0 `ERROR:` warning frame"
    )
    assert err == []


def test_the_daemon_survives_a_bad_deck_and_runs_the_next_one():
    """Residency is the whole point: one broken deck must not end the process.

    SimNEC never restarts the engine between decks (``NEC2Daemon.destroy()``
    is the only teardown), so a deck that raises has to be reported and
    stepped over, leaving the loop ready for the next ``NX``.
    """
    stdin = io.StringIO(
        "CE bogus\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\nZZ 1\nNX\n"
        + fixture_deck("dipole_free_space")
        + "\nNX\n"
        + fixture_deck("dipole_rp_pattern")
        + "\nNX\n"
    )
    out = io.StringIO()
    assert main([], stdin=stdin, stdout=out, stderr=io.StringIO()) == 0
    text = out.getvalue()
    assert len(NX_ECHO.findall(text)) == 3, "one sentinel per deck, bad ones included"
    assert text.count("ERROR-NEC2C") == 1
    # ...and the decks after the bad one really ran.
    assert text.count("ANTENNA INPUT PARAMETERS") == 2
    assert text.count("RADIATION PATTERNS") == 1


def test_a_blank_deck_still_frames():
    """An empty body between two NX cards is legal input and must not hang."""
    out, err = deck_frame("")
    assert NX_ECHO.search("\n".join(out))
    assert err == []


# --------------------------------------------------------------------------
# packaging: the console script SimNEC is pointed at (unit 4)
# --------------------------------------------------------------------------

ENTRY_POINT_NAME = "momwire-nec2c"


def _console_scripts() -> dict[str, str]:
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    return tomllib.loads(text)["project"]["scripts"]


def test_the_console_script_name_passes_simnecs_filename_check():
    """``nec2/NEC2PortalDialog`` accepts an engine on its FILENAME alone.

    The check is a lowercased substring test for ``nec2c`` on the configured
    command's file name — nothing inside the file is consulted until the
    ``-version`` probe. Renaming the entry point to something tidier
    (``momwire-portal``) makes SimNEC refuse it outright, so the name is
    contract, not cosmetics.
    """
    scripts = _console_scripts()
    assert ENTRY_POINT_NAME in scripts, (
        f"pyproject [project.scripts] must ship {ENTRY_POINT_NAME!r}; has {sorted(scripts)}"
    )
    assert "nec2c" in ENTRY_POINT_NAME.lower()
    # The sibling dialect prefixes select a DIFFERENT column layout
    # (checkNEC42Fields, samplesWidth 12) that this engine does not emit.
    assert "nec5" not in ENTRY_POINT_NAME.lower()
    assert "nec42" not in ENTRY_POINT_NAME.lower()


def test_the_console_script_target_resolves():
    """The ``module:attr`` string must actually import — a typo here is only
    discovered by a user whose SimNEC session dies at the version probe."""
    target = _console_scripts()[ENTRY_POINT_NAME]
    module_name, _, attr = target.partition(":")
    assert attr, f"{target!r} names no callable"
    entry = getattr(importlib.import_module(module_name), attr)
    assert entry is nec_portal.main
    assert callable(entry)


def test_the_entry_point_runs_from_an_unrelated_cwd(tmp_path):
    """SimNEC launches the engine via ``sh -c`` with cwd=$HOME.

    Nothing in the daemon may resolve a relative path — not the fixtures, not
    the momwire import, not a config file. Both halves of the protocol are
    exercised out of a directory that has no relationship to the checkout: the
    ``-version`` probe SimNEC gates on, and one real deck framed by ``NX``.
    """
    src_root = str(Path(nec_portal.__file__).resolve().parents[2])
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([src_root, os.environ.get("PYTHONPATH", "")]),
    }
    argv = [sys.executable, "-m", "antennaknobs.nec_portal"]

    probe = subprocess.run(
        [*argv, "-version"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.splitlines() == [nec_portal.PROBE_VERSION]

    solve = subprocess.run(
        argv,
        cwd=tmp_path,
        env=env,
        input=fixture_deck("dipole_free_space") + "\nNX\n",
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert solve.returncode == 0, solve.stderr
    assert NX_ECHO.search(solve.stdout), "no sentinel — SimNEC would block forever"
    assert "ANTENNA INPUT PARAMETERS" in solve.stdout
    assert f"VERSION:{nec_portal.BANNER_VERSION}" in solve.stdout


def test_selftest_passes_and_reports(tmp_path, monkeypatch):
    """`momwire-nec2c --selftest` is the deployment smoke for boxes with no
    checkout (the Windows live-session path): it must pass here, from an
    unrelated cwd, and print the PASS verdict on its own line."""
    import io

    from antennaknobs.nec_portal import main

    monkeypatch.chdir(tmp_path)
    out = io.StringIO()
    rc = main(["--selftest"], stdout=out)
    text = out.getvalue()
    assert rc == 0
    assert text.rstrip().endswith("PASS")
    assert "FAIL" not in text


# --- the --basis flag --------------------------------------------------------


def _run_main(argv, deck=""):
    import io

    from antennaknobs import nec_portal

    out = io.StringIO()
    err = io.StringIO()
    rc = nec_portal.main(argv, stdin=io.StringIO(deck), stdout=out, stderr=err)
    return rc, out.getvalue(), err.getvalue()


def test_basis_flag_unknown_name_fails_fast_and_nonzero():
    """A typo'd basis must fail the -version probe at configure time, not
    silently serve the default."""
    rc, out, _ = _run_main(["--basis", "nope", "-version"])
    assert rc == 3 and "choices:" in out


def test_basis_flag_rides_the_version_probe():
    """SimNEC probes `<full command line> -version`; the probe line must be
    unchanged (Double-parsed by Execute) with any valid --basis present."""
    from antennaknobs.nec_portal import PROBE_VERSION

    rc, out, _ = _run_main(["--basis", "sinusoidal-galerkin-converged", "-version"])
    assert rc == 0 and out == f"{PROBE_VERSION}\n"


def test_basis_flag_solves_and_stamps_the_banner():
    """The alternate basis answers a deck, and the PRINTOUT banner records
    which physics answered (+sgc) — the -version line never does."""
    deck = (
        "CE basis\n"
        "GW 1 11 0. -5. 10. 0. 5. 10. 0.001\n"
        "GE 0\nEX 0 1 6 0 1.\nFR 0 1 0 0 14.0 1\nXQ\nNX\n"
    )
    rc, out, err = _run_main(["--basis=sinusoidal-galerkin-converged"], deck=deck)
    assert rc == 0 and err == ""
    assert "VERSION:nec2c.ae6ty.momwire.9.1+sgc" in out
    assert "ANTENNA INPUT PARAMETERS" in out
    rows = [
        ln
        for ln in out.splitlines()
        if ln.startswith("    1 ") and len(ln.split()) == 11
    ]
    assert rows, "no AIP data row under the alternate basis"


def test_default_basis_banner_is_unchanged():
    deck = (
        "CE basis\n"
        "GW 1 11 0. -5. 10. 0. 5. 10. 0.001\n"
        "GE 0\nEX 0 1 6 0 1.\nFR 0 1 0 0 14.0 1\nXQ\nNX\n"
    )
    rc, out, _ = _run_main([], deck=deck)
    assert rc == 0
    assert "VERSION:nec2c.ae6ty.momwire.9.1\n" in out and "+sg" not in out


# --- --basis sinusoidal: the NEC-closest rung (issue #822) -------------------

# Point-matched sinusoidal has neither the B-spline family's KCL-port solve nor
# the Galerkin family's ported operator, so `_y_and_port_coeffs` grows a third
# branch that reproduces `compute_y_matrix`'s algebra. These pin the copy to
# momwire's own: if either drifts, the daemon's single fill and the library's
# per-source refill stop being the same solve.


def _sin_solver(**kwargs):
    """A 9-segment 5 m dipole on plain SinusoidalSolver, fed at its centre."""
    import numpy as np
    from momwire import SinusoidalSolver

    return SinusoidalSolver(
        wires=[np.array([[0.0, 0.0, -2.5], [0.0, 0.0, 2.5]])],
        n_per_edge_per_wire=[[9]],
        feeds=[(0, 2.5, 1.0)],
        wavelength=nec_portal.C_LIGHT / 14.0e6,
        wire_radius=0.001,
        **kwargs,
    )


def test_the_sinusoidal_shim_reproduces_momwires_own_y_matrix():
    import numpy as np

    y_shim, _x = nec_portal._y_and_port_coeffs(_sin_solver())
    y_lib = np.asarray(_sin_solver().compute_y_matrix(), dtype=np.complex128)
    assert np.allclose(y_shim, y_lib, rtol=1e-10, atol=0.0)


def test_the_sinusoidal_shim_columns_are_the_one_volt_drive_coefficients():
    """Column j of X must be the solve momwire would do for a 1 V drive at
    port j — that identity is what lets `solve_group` reuse one fill for
    every excitation (``coeffs = X @ V``)."""
    import numpy as np

    _y, x = nec_portal._y_and_port_coeffs(_sin_solver())
    _z, alpha = _sin_solver().compute_impedance()
    driven = x @ np.array([1.0 + 0.0j])
    assert np.allclose(driven, alpha, rtol=1e-10, atol=0.0)


# The classes that exercise everything the shim's coefficients feed: a
# Sommerfeld and a two-medium ground (solver-name-gated in engines/momwire.py),
# both network branch types, a lumped load (power budget), the PT/YY readout,
# and a pattern (which resamples the solved current through
# `currents_at_knots`).
_SIN_HARD_FIXTURES = (
    "dipole_sommerfeld_ground",
    "dipole_gd_second_medium",
    "dipole_tl_network",
    "dipole_nt_network",
    "dipole_load_ld4",
    "dipole_pt_toggle",
    "dipole_rp_pattern",
)


def _aip_rows(text: str) -> list[list[float]]:
    """Every ANTENNA INPUT PARAMETERS data row, as floats past the tag/seg
    pair."""
    rows, inside = [], False
    for line in text.splitlines():
        if line.strip(" -") == "ANTENNA INPUT PARAMETERS":
            inside = True
            continue
        if not inside:
            continue
        tokens = line.split()
        if len(tokens) == 11 and tokens[0].isdigit() and tokens[1].isdigit():
            rows.append([float(t) for t in tokens[2:]])
        elif rows and not line.strip():
            inside = False
    return rows


@pytest.mark.parametrize("name", _SIN_HARD_FIXTURES)
def test_sinusoidal_basis_answers_the_hard_fixture_classes(name):
    import math

    deck = (FIXTURE_DIR / f"{name}.deck").read_text()
    rc, out, err = _run_main(["--basis", "sinusoidal"], deck=deck)
    assert rc == 0 and err == ""
    assert "ERROR-NEC2C" not in out, f"{name} took the error path under +sin"
    missing = set(section_walk(fixture_out(name))) - set(section_walk(out))
    assert not missing, f"{name} lost sections under +sin: {sorted(missing)}"
    rows = _aip_rows(out)
    assert rows, f"no AIP data row for {name} under +sin"
    assert all(math.isfinite(v) for row in rows for v in row), (
        f"non-finite AIP value for {name} under +sin"
    )


def test_sinusoidal_basis_impedance_tracks_the_nec2c_fixture():
    """The point-matched sinusoidal basis is the closest of the roster to
    NEC-2's own formulation, so the free-space dipole's driving-point
    impedance has to sit near the oracle's — a looser bound than a digit
    match, but tight enough to catch a wrong RHS scaling or a dropped
    ``-1/h``."""
    deck = (FIXTURE_DIR / "dipole_free_space.deck").read_text()
    rc, out, err = _run_main(["--basis", "sinusoidal"], deck=deck)
    assert rc == 0 and err == ""
    ours = complex(*_aip_rows(out)[0][4:6])
    theirs = complex(*_aip_rows(fixture_out("dipole_free_space"))[0][4:6])
    assert abs(ours - theirs) / abs(theirs) < 0.05, f"{ours} vs {theirs}"


def test_sinusoidal_basis_answer_differs_from_the_default_basis():
    """Disabled-path probe: every other +sin test would still pass if the
    ``_BASES`` entry silently served the default B-spline solver (its answer
    is inside the 5% oracle bound too, and the banner stamps regardless of
    what solved). The two bases genuinely disagree on this deck — measured
    79.205+45.150j (+sin) vs 79.524+46.003j (default), 1.0% apart — so a
    collapse to the default is detectable."""
    deck = (FIXTURE_DIR / "dipole_free_space.deck").read_text()
    _rc, out_sin, _err = _run_main(["--basis", "sinusoidal"], deck=deck)
    _rc, out_default, _err = _run_main([], deck=deck)
    z_sin = complex(*_aip_rows(out_sin)[0][4:6])
    z_default = complex(*_aip_rows(out_default)[0][4:6])
    assert abs(z_sin - z_default) / abs(z_default) > 0.003, (z_sin, z_default)


def test_sinusoidal_basis_stamps_the_banner():
    deck = (
        "CE basis\n"
        "GW 1 11 0. -5. 10. 0. 5. 10. 0.001\n"
        "GE 0\nEX 0 1 6 0 1.\nFR 0 1 0 0 14.0 1\nXQ\nNX\n"
    )
    rc, out, err = _run_main(["--basis", "sinusoidal"], deck=deck)
    assert rc == 0 and err == ""
    assert "VERSION:nec2c.ae6ty.momwire.9.1+sin" in out
    assert _aip_rows(out)


def test_sinusoidal_has_no_converged_variant():
    """The zero-width point gap has no collocation RHS (momwire#212), so the
    flag must not offer a name the solver would refuse — same constraint the
    CLI's MOMWIRE_BASIS_VARIANTS records."""
    rc, out, _ = _run_main(["--basis", "sinusoidal-converged", "-version"])
    assert rc == 3 and "sinusoidal-converged" not in out.split("choices:")[1]


# --- bspline-d1 (issue #821): the degree axis, same solver class -----------


def test_bspline_d1_basis_flag_solves_and_stamps_the_banner():
    """`bspline-d1` is BSplineSolver with degree=1 bound — same one-fill shim
    as plain `bspline` (dispatch is on `hasattr(solver, "_solve_with_kcl_ports")`,
    not on degree), so it answers a deck and stamps +bs1 in the banner."""
    deck = (
        "CE basis\n"
        "GW 1 11 0. -5. 10. 0. 5. 10. 0.001\n"
        "GE 0\nEX 0 1 6 0 1.\nFR 0 1 0 0 14.0 1\nXQ\nNX\n"
    )
    rc, out, err = _run_main(["--basis=bspline-d1"], deck=deck)
    assert rc == 0 and err == ""
    assert "VERSION:nec2c.ae6ty.momwire.9.1+bs1" in out
    assert "ANTENNA INPUT PARAMETERS" in out
    rows = [
        ln
        for ln in out.splitlines()
        if ln.startswith("    1 ") and len(ln.split()) == 11
    ]
    assert rows, "no AIP data row under the bspline-d1 basis"


@pytest.mark.parametrize(
    "name",
    [
        "dipole_sommerfeld_ground",
        "dipole_gd_second_medium",
        "dipole_tl_network",
        "dipole_nt_network",
        "dipole_load_ld4",
        "dipole_pt_toggle",
        "dipole_rp_pattern",
    ],
)
def test_bspline_d1_basis_solves_hard_fixture_classes(name):
    """bs1 is degree=1 on the exact same BSplineSolver class the default
    basis uses (engines/momwire.py:_parity_for_solver changes the mesh
    parity, not the code path), so it must clear every hard fixture class the
    default `bspline` basis clears: Sommerfeld ground, GD second medium, TL
    and NT networks, LD4 loading, PT toggling, RP patterns."""
    rc, out, err = _run_main(
        ["--basis", "bspline-d1"], deck=fixture_deck(name) + "\nNX\n"
    )
    assert rc == 0
    assert err == ""
    assert "ANTENNA INPUT PARAMETERS" in out
    tables = aip_tables(out)
    assert tables and tables[0], f"no AIP data rows for {name}"
    for table in tables:
        for row in table:
            for tok in row:
                assert math.isfinite(float(tok)), f"{name}: non-finite token {tok!r}"


def test_bspline_d1_free_space_impedance_within_loose_bound_of_committed_oracle():
    """The oracle fixture is nec2c's own answer (not ours) — the same "loose
    cross-engine smoke bound" style as the default-basis test at the top of
    this file, applied to the alternate degree.

    Measured (issue #821 build): R=78.06 vs oracle 79.24 (1.5% off — inside
    5%); X=40.27 vs oracle 45.36 (11.2% off). The coarser tent basis (bs1,
    degree=1) is a full segmentation-order coarser than the oracle's own
    basis, so 5% was optimistic for X on a 2-segment-mesh-equivalent free
    dipole; 15% is the bound this measurement actually supports. R stays at
    the tighter 5% since it tracks a shallower dependency on basis order."""
    _rc, out, _err = _run_main(
        ["--basis", "bspline-d1"],
        deck=fixture_deck("dipole_free_space") + "\nNX\n",
    )
    ours = aip_tables(out)[0][0]
    theirs = aip_tables(fixture_out("dipole_free_space"))[0][0]
    r_ours, x_ours = float(ours[6]), float(ours[7])
    r_theirs, x_theirs = float(theirs[6]), float(theirs[7])
    assert abs(r_ours - r_theirs) / r_theirs < 0.05, (r_ours, r_theirs)
    assert abs(x_ours - x_theirs) / abs(x_theirs) < 0.15, (x_ours, x_theirs)


def test_bspline_d1_answer_differs_from_the_default_degree():
    """Disabled-path probe: if `_build_engine` dropped the `{"degree": 1}`
    kwargs and served the default degree-2 solver, every other +bs1 test
    would still pass — the d2 answer is inside both oracle bounds and the
    banner stamps regardless of what solved. The two degrees genuinely
    disagree here — measured X=40.27 (d1) vs X=46.00 (d2), 12% apart — so a
    silently-ignored kwarg is detectable."""
    deck = fixture_deck("dipole_free_space") + "\nNX\n"
    _rc, out_d1, _err = _run_main(["--basis", "bspline-d1"], deck=deck)
    _rc, out_d2, _err = _run_main([], deck=deck)
    x_d1 = float(aip_tables(out_d1)[0][0][7])
    x_d2 = float(aip_tables(out_d2)[0][0][7])
    assert abs(x_d1 - x_d2) / abs(x_d2) > 0.05, (x_d1, x_d2)


# --- hmatrix / arrayblock (issue #830): the large-array accelerators --------

# These two entries are NOT a physics axis: HMatrixSolver and ArrayBlockSolver
# are BSplineSolver subclasses that solve the SAME operator with a compressed
# representation and GMRES instead of a dense fill and an LU. That makes the
# roster's usual disabled-path probe (differ-from-default) useless — a silent
# collapse to plain `bspline` would print the same digits — so the armour here
# is two-sided: the printout must AGREE with the default basis, and a spy must
# see the accelerated solve actually run.


def _accel_pair(cls, volts=(1.0, 0.0), **kwargs):
    """Two 9-segment 5 m dipoles 3 m apart, both centre-fed — a two-port
    structure small enough to solve densely for comparison."""
    import numpy as np

    return cls(
        wires=[
            np.array([[0.0, 0.0, -2.5], [0.0, 0.0, 2.5]]),
            np.array([[3.0, 0.0, -2.5], [3.0, 0.0, 2.5]]),
        ],
        n_per_edge_per_wire=[[9], [9]],
        feeds=[(0, 2.5, volts[0]), (1, 2.5, volts[1])],
        wavelength=nec_portal.C_LIGHT / 14.0e6,
        wire_radius=0.001,
        **kwargs,
    )


def _route_spy(solver):
    """Record which of the two B-spline solve routes momwire takes, without
    disturbing either. Installed BEFORE the shim, so the shim wraps these and
    its own ``del`` on the instance attribute tidies them away."""
    routes: list[str] = []
    dense = solver._solve_with_kcl_ports

    def spy_dense(z, v, kcl_a, overwrite=False):
        routes.append("dense")
        return dense(z, v, kcl_a, overwrite=overwrite)

    solver._solve_with_kcl_ports = spy_dense
    accel = getattr(solver, "_solve_hmatrix", None)
    if accel is not None:

        def spy_accel(h, kcl_a, b):
            routes.append(f"accel:{type(h).__name__}")
            return accel(h, kcl_a, b)

        solver._solve_hmatrix = spy_accel
    return routes


def _accel_classes():
    from momwire import ArrayBlockSolver, HMatrixSolver

    return {"hmatrix": HMatrixSolver, "arrayblock": ArrayBlockSolver}


@pytest.mark.parametrize("basis", ["hmatrix", "arrayblock"])
def test_the_accelerated_shim_reproduces_momwires_own_y_matrix(basis):
    """The accelerated subclasses never reach `_solve_with_kcl_ports` — their
    `compute_y_matrix` runs the constrained GMRES in `_solve_hmatrix` — so the
    shim spies that instead, and the Y it hands back has to be the library's
    own to the iterative tolerance."""
    import numpy as np

    cls = _accel_classes()[basis]
    y_shim, _x = nec_portal._y_and_port_coeffs(_accel_pair(cls))
    y_lib = np.asarray(_accel_pair(cls).compute_y_matrix(), dtype=np.complex128)
    assert np.allclose(y_shim, y_lib, rtol=1e-8, atol=0.0)


@pytest.mark.parametrize("basis", ["hmatrix", "arrayblock"])
def test_the_accelerated_shim_captures_the_gmres_solve_not_a_dense_fallback(basis):
    """The one thing no printout test can see: WHICH solve answered. Without
    it, `_BASES` could name the accelerated class while every deck quietly
    took the dense path (`_hmatrix_unsupported`) and nothing would fail."""
    cls = _accel_classes()[basis]
    solver = _accel_pair(cls)
    assert not solver._hmatrix_unsupported()
    routes = _route_spy(solver)
    _y, x = nec_portal._y_and_port_coeffs(solver)
    assert routes and all(r.startswith("accel:") for r in routes), routes
    assert x.shape[1] == 2


@pytest.mark.parametrize("basis", ["hmatrix", "arrayblock"])
def test_the_accelerated_shim_columns_are_the_one_volt_drive_coefficients(basis):
    """Column j of X must be the coefficients momwire would solve for a 1 V
    drive at port j and nothing else on — the identity `solve_group` leans on
    when it turns one fill into every excitation (``coeffs = X @ V``). Checked
    against the DENSE B-spline solve of the same mesh, which is the answer the
    accelerator approximates (measured max relative deviation 8e-16 for
    hmatrix, 2e-11 for arrayblock, both far inside the 1e-6 solve_tol)."""
    import numpy as np
    from momwire import BSplineSolver

    cls = _accel_classes()[basis]
    _y, x = nec_portal._y_and_port_coeffs(_accel_pair(cls))
    for j, volts in enumerate([(1.0, 0.0), (0.0, 1.0)]):
        _z, alpha = _accel_pair(BSplineSolver, volts=volts).compute_impedance()
        assert np.allclose(x[:, j], alpha, rtol=1e-6, atol=1e-9 * np.abs(alpha).max())


def test_the_dense_fallback_route_is_still_captured():
    """`_hmatrix_unsupported()` is singular enrichment and nothing else — not
    mesh size, not ground — so this is the ONLY way to reach the dense path on
    an accelerated class. The portal never asks for enrichment, but the shim
    keeps the dense spy wired so a momwire that grows a new fallback degrades
    to a slower answer rather than a `PortalError`."""
    import numpy as np
    from momwire import HMatrixSolver

    solver = _accel_pair(HMatrixSolver, use_singular_enrichment=True)
    assert solver._hmatrix_unsupported()
    routes = _route_spy(solver)
    y_shim, x = nec_portal._y_and_port_coeffs(solver)
    assert routes == ["dense"], routes
    y_lib = np.asarray(
        _accel_pair(HMatrixSolver, use_singular_enrichment=True).compute_y_matrix(),
        dtype=np.complex128,
    )
    assert np.allclose(y_shim, y_lib, rtol=1e-8, atol=0.0)
    assert x.shape == (18, 2)


# The seven classes the roster gates on (#826/#827): a Sommerfeld and a
# two-medium ground, both network branch types, a lumped load, the PT/YY
# readout, and a pattern. MEASURED: all seven take the ACCELERATED route under
# both bases — the ground decks included, because `_hmatrix_unsupported()`
# tests only `use_singular_enrichment` and every ground model the portal emits
# (PEC image, reflection coefficient, Sommerfeld) is carried on the fast path.
# No fixture class reaches the dense fallback.
_ACCEL_HARD_FIXTURES = (
    "dipole_sommerfeld_ground",
    "dipole_gd_second_medium",
    "dipole_tl_network",
    "dipole_nt_network",
    "dipole_load_ld4",
    "dipole_pt_toggle",
    "dipole_rp_pattern",
)


@pytest.mark.parametrize("basis", ["hmatrix", "arrayblock"])
@pytest.mark.parametrize("name", _ACCEL_HARD_FIXTURES)
def test_the_accelerators_answer_the_hard_fixture_classes(name, basis):
    rc, out, err = _run_main(["--basis", basis], deck=fixture_deck(name) + "\nNX\n")
    assert rc == 0 and err == ""
    assert "ERROR-NEC2C" not in out, f"{name} took the error path under {basis}"
    missing = set(section_walk(fixture_out(name))) - set(section_walk(out))
    assert not missing, f"{name} lost sections under {basis}: {sorted(missing)}"
    tables = aip_tables(out)
    assert tables and tables[0], f"no AIP data rows for {name} under {basis}"
    for table in tables:
        for row in table:
            for tok in row:
                assert math.isfinite(float(tok)), f"{name}: non-finite token {tok!r}"


@pytest.mark.parametrize("basis", ["hmatrix", "arrayblock"])
def test_the_accelerators_agree_with_the_default_basis_and_the_oracle(basis):
    """Agreement, not difference, is the probe here: same physics as
    `bspline`, so the accelerated answer must land on the default's to the
    iterative solve tolerance (measured: identical to every printed digit,
    79.524+46.003j) while still clearing the 5% oracle bound (measured 0.77%
    from nec2c's 79.240+45.364j). A collapse to a DIFFERENT basis is what this
    catches; a collapse to dense `bspline` is caught by the spy test above."""
    deck = fixture_deck("dipole_free_space") + "\nNX\n"
    rc, out, err = _run_main(["--basis", basis], deck=deck)
    assert rc == 0 and err == ""
    _rc, out_default, _err = _run_main([], deck=deck)
    ours = aip_tables(out)[0][0]
    theirs = aip_tables(out_default)[0][0]
    oracle = aip_tables(fixture_out("dipole_free_space"))[0][0]
    z_ours = complex(float(ours[6]), float(ours[7]))
    z_default = complex(float(theirs[6]), float(theirs[7]))
    z_oracle = complex(float(oracle[6]), float(oracle[7]))
    assert abs(z_ours - z_default) / abs(z_default) < 0.005, (z_ours, z_default)
    assert abs(z_ours - z_oracle) / abs(z_oracle) < 0.05, (z_ours, z_oracle)


@pytest.mark.parametrize("basis,suffix", [("hmatrix", "+hm"), ("arrayblock", "+ab")])
def test_the_accelerators_stamp_the_banner(basis, suffix):
    deck = (
        "CE basis\n"
        "GW 1 11 0. -5. 10. 0. 5. 10. 0.001\n"
        "GE 0\nEX 0 1 6 0 1.\nFR 0 1 0 0 14.0 1\nXQ\nNX\n"
    )
    rc, out, err = _run_main(["--basis", basis], deck=deck)
    assert rc == 0 and err == ""
    assert f"VERSION:nec2c.ae6ty.momwire.9.1{suffix}" in out
    assert aip_tables(out)[0]


@pytest.mark.parametrize("basis", ["hmatrix", "arrayblock"])
def test_the_accelerators_ride_the_version_probe_unchanged(basis):
    from antennaknobs.nec_portal import PROBE_VERSION

    rc, out, _err = _run_main(["--basis", basis, "-version"])
    assert rc == 0 and out == f"{PROBE_VERSION}\n"


def test_the_lattice_fft_path_engages_and_the_shim_still_agrees():
    """The engaged-path probe for `arrayblock`'s reason to exist. A 4x4 grid
    of identical 3-segment half-wave dipoles meets every FFT gate (one block
    shape, a regular lattice, P >= 16), and `require_lattice_fft=True` turns a
    miss into `LatticeFFTUnavailable` naming the unmet gate rather than a
    silent degradation to the parent H-matrix. The spy then pins that the
    operator the shim's X came out of really is the spectral one, and the
    answer is checked against the dense solve of the same mesh.

    Runtime ~0.4 s (48 bases): the lattice gate is about the FFT bookkeeping,
    not about size, so 16 three-segment elements engage it and this stays a
    normal-suite test rather than a `heavy_mesh` one."""
    import numpy as np
    from momwire import ArrayBlockSolver, BSplineSolver

    wavelength = nec_portal.C_LIGHT / 14.0e6
    arm = 0.25 * wavelength
    pitch = 0.5 * wavelength
    wires = [
        np.array([[ix * pitch, iy * pitch, -arm], [ix * pitch, iy * pitch, arm]])
        for ix in range(4)
        for iy in range(4)
    ]

    def build(cls, **kwargs):
        return cls(
            wires=wires,
            n_per_edge_per_wire=[[3]] * len(wires),
            feeds=[(0, arm, 1.0), (5, arm, 0.0)],
            wavelength=wavelength,
            wire_radius=0.001,
            **kwargs,
        )

    solver = build(ArrayBlockSolver, require_lattice_fft=True)
    routes = _route_spy(solver)
    y_fft, x_fft = nec_portal._y_and_port_coeffs(solver)
    assert routes == ["accel:LatticeArrayBlock"], routes

    y_dense, x_dense = nec_portal._y_and_port_coeffs(build(BSplineSolver))
    assert np.allclose(y_fft, y_dense, rtol=1e-6, atol=0.0)
    assert np.allclose(x_fft, x_dense, rtol=1e-5, atol=1e-8 * np.abs(x_dense).max())


def test_require_lattice_fft_names_the_unmet_gate_on_a_single_pair():
    """The other half of the engaged-path proof: on a deck with nothing to
    exploit the FFT gate is genuinely unmet and momwire says which one — so
    the passing case above cannot be a vacuous assertion."""
    from momwire import ArrayBlockSolver, LatticeFFTUnavailable

    solver = _accel_pair(ArrayBlockSolver, require_lattice_fft=True)
    with pytest.raises(LatticeFFTUnavailable):
        nec_portal._y_and_port_coeffs(solver)


# --- the cross-deck solver cache (issue #823) --------------------------------
#
# The cache's whole claim is that the printout is IDENTICAL whether a deck was
# solved or served — so the printout cannot be the evidence that it WAS served.
# These tests read `nec_portal._cache_stats` for that half and hold the
# printout to the other half: that a served answer is the answer the arriving
# deck asked for, byte for byte against the same deck rendered from an empty
# cache. Nothing here parses a timing line.
#
# A stale factor would be silent and wrong, so the battery below is the point
# of the feature: one mutation per class of card that moves the operator, each
# asserting a MISS, and one per class that does not, each asserting a HIT.
#
# Serving is OFF in the shipped default and opted into with `--cache`, so a
# test OF the cache has to ask for it: `cache_reset` is the state every test
# here starts from, and the `main()`-driven ones pass the flag. The default-off
# and dry-run modes get their own tests further down.


def cache_reset(serving: bool = True) -> None:
    """Empty cache, default basis, no stats file, serving as asked.

    The basis pin is not decoration: ``main()`` resets ``_active_basis`` at the
    START of its next invocation, not on exit, so a ``--basis`` probe test
    leaves its basis behind for every direct ``deck_frame`` render that
    follows. A fresh-subprocess comparison after such a test would then diff
    two different physics — an ordering hazard, not a cache bug (it predates
    the cache; the subprocess-identity tests are just the first to be sensitive
    to it)."""
    nec_portal._active_basis = nec_portal._BASES["bspline"]
    nec_portal._cache_serving = serving
    nec_portal._cache_stats_path = None
    nec_portal._reset_solver_cache()


def cache_render(body: str) -> str:
    """One deck through the daemon's own per-deck path, cache as it stands."""
    return "\n".join(deck_frame(body)[0])


def cold_render(body: str) -> str:
    """The same deck from an EMPTY cache — what a fresh process prints."""
    cache_reset()
    return cache_render(body)


def cache_counts() -> dict:
    return dict(nec_portal._cache_stats)


def deck_chunks(transcript: str) -> list[str]:
    """A daemon transcript split after each ``NX`` echo — one chunk per deck."""
    chunks: list[str] = []
    current: list[str] = []
    for line in transcript.splitlines():
        current.append(line)
        if NX_ECHO.match(line):
            chunks.append("\n".join(current))
            current = []
    return chunks


def fill_lines(text: str) -> list[str]:
    """The MATRIX TIMING lines `body_lines` drops. A hit reuses the cached
    entry's measured fill, so between two passes of one process even these
    repeat to the digit — the token arity never moves either way."""
    return [line for line in text.splitlines() if "FILL:" in line]


def frame_lines(text: str) -> list[str]:
    """`body_lines` minus the ASCII banner box, so ONE deck's in-process frame
    and a whole process's transcript of the same deck compare."""
    return [
        line
        for line in body_lines(text)
        if "|" not in line and set(line.strip()) != {"_"}
    ]


def aip_impedances(text: str) -> list[tuple[str, str]]:
    """The impedance columns of every ANTENNA INPUT PARAMETERS row."""
    return [(row[6], row[7]) for table in aip_tables(text) for row in table]


@pytest.mark.parametrize("name", ALL_NAMES)
def test_a_second_pass_of_every_fixture_prints_what_the_first_did(name):
    """The identity gate, over the whole corpus: every fixture sent TWICE down
    one process, compared under the harness's own canonicalisation.

    Fixtures that are multi-deck residency transcripts are compared deck for
    deck, first half against second. `misses` may not grow on the second pass —
    that is the assertion that the second half was SERVED rather than re-solved
    into an identical answer, which is what makes the identity meaningful.
    """
    text = (FIXTURE_DIR / f"{name}.deck").read_text()
    if not text.endswith("\n"):
        text += "\n"
    buffer = io.StringIO()
    rc = main(
        ["--cache"], stdin=io.StringIO(text * 2), stdout=buffer, stderr=io.StringIO()
    )
    assert rc == 0
    chunks = deck_chunks(buffer.getvalue())
    half = len(chunks) // 2
    assert half >= 1 and len(chunks) == 2 * half
    for first, second in zip(chunks[:half], chunks[half:]):
        assert body_lines(second) == body_lines(first)
        assert fill_lines(second) == fill_lines(first)
    assert nec_portal._cache_stats["hits"] >= half
    assert nec_portal._cache_stats["misses"] <= half


@pytest.mark.parametrize("name", ("dipole_free_space", "dipole_rp_pattern"))
def test_a_served_deck_matches_a_genuinely_fresh_process(name):
    """And the served printout is not merely self-consistent: it is what a
    process that never saw the deck before prints. `dipole_rp_pattern` carries
    the far-field path, where a stale solver would show up as a wrong pattern
    table rather than a wrong impedance."""
    text = fixture_deck(name) + "\nNX\n"
    proc = subprocess.run(
        [sys.executable, "-m", "antennaknobs.nec_portal"],
        input=text,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0 and proc.stderr == ""
    buffer = io.StringIO()
    # The subprocess is deliberately STOCK — no `--cache` — so this compares a
    # served answer against the shipped default's, not against itself.
    assert (
        main(
            ["--cache"],
            stdin=io.StringIO(text * 2),
            stdout=buffer,
            stderr=io.StringIO(),
        )
        == 0
    )
    chunks = deck_chunks(buffer.getvalue())
    assert len(chunks) == 2 and nec_portal._cache_stats["hits"] == 1
    assert frame_lines(chunks[1]) == frame_lines(proc.stdout)


# A deck carrying one of everything the key has to watch, so each mutation
# below is a single-token edit against the same base: a wire over a
# reflection-coefficient ground, scaled, loaded, driven off-centre.
CACHE_BASE = (
    "CM cross-deck cache probe\n"
    "CE\n"
    "GW 1 9 0. 0. 5.0 0. 0. 10.0 0.001\n"
    "GS 0 0 1.0\n"
    "GE -1\n"
    "GN 0 0 0 0 13. 0.005\n"
    "LD 0 1 3 3 50. 1.e-6 0.\n"
    "EX 0 1 5 0 1.\n"
    "FR 0 1 0 0 14.1 0\n"
    "XQ\n"
)


def mutate(old: str, new: str, base: str = CACHE_BASE) -> str:
    """A deck with one substring replaced — asserted unique, so a mutant can
    never silently edit a card it did not mean to."""
    assert base.count(old) == 1, old
    return base.replace(old, new)


# The same base with both network branch types hung across the same pair of
# segments, so a branch's VALUES can be mutated without moving the port set —
# the case the port component of the key cannot catch.
CACHE_NET_BASE = mutate(
    "EX 0 1 5 0 1.\n",
    "EX 0 1 5 0 1.\nTL 1 3 1 7 600. 2.5 0. 0. 0. 0.\nNT 1 3 1 7 0. 0.02 0. 0. 0. 0.02\n",
)


# (label, base deck, mutant deck, does this move the printed numbers?)
_OPERATOR_MUTATIONS = (
    ("GW endpoint", CACHE_BASE, mutate("0. 0. 10.0 0.001", "0. 0. 10.4 0.001"), True),
    ("wire radius", CACHE_BASE, mutate("0.001", "0.0025"), True),
    ("segment count", CACHE_BASE, mutate("GW 1 9", "GW 1 11"), True),
    ("GS scale", CACHE_BASE, mutate("GS 0 0 1.0", "GS 0 0 1.1"), True),
    # The GE flag is the ground-plane ANNOTATION on this deck (the wire is well
    # clear of z = 0, and GN carries the physics), so it moves the printout
    # without moving a number. It is in the key because on a deck whose wire
    # touches the plane it moves both.
    ("GE flag", CACHE_BASE, mutate("GE -1", "GE 0"), False),
    ("GN parameter", CACHE_BASE, mutate("13. 0.005", "20. 0.005"), True),
    ("GN removed", CACHE_BASE, mutate("GN 0 0 0 0 13. 0.005\n", ""), True),
    ("LD value", CACHE_BASE, mutate("50. 1.e-6", "150. 1.e-6"), True),
    ("LD removed", CACHE_BASE, mutate("LD 0 1 3 3 50. 1.e-6 0.\n", ""), True),
    ("EX moved", CACHE_BASE, mutate("EX 0 1 5", "EX 0 1 4"), True),
    (
        "NT added",
        CACHE_BASE,
        mutate("EX 0 1 5 0 1.\n", "EX 0 1 5 0 1.\nNT 1 3 1 7 0. 0.02 0. 0. 0. 0.02\n"),
        True,
    ),
    (
        "TL added",
        CACHE_BASE,
        mutate("EX 0 1 5 0 1.\n", "EX 0 1 5 0 1.\nTL 1 3 1 7 600. 2.5 0. 0. 0. 0.\n"),
        True,
    ),
    # Branch VALUES across an unchanged pair of segments: the port set is
    # identical, so only the `networks` component of the key can catch these.
    (
        "NT admittance",
        CACHE_NET_BASE,
        mutate("0. 0.02 0. 0. 0. 0.02", "0. 0.03 0. 0. 0. 0.03", CACHE_NET_BASE),
        True,
    ),
    (
        "TL impedance",
        CACHE_NET_BASE,
        mutate("600. 2.5", "450. 2.5", CACHE_NET_BASE),
        True,
    ),
    ("TL length", CACHE_NET_BASE, mutate("600. 2.5", "600. 3.5", CACHE_NET_BASE), True),
    (
        "TL crossed",
        CACHE_NET_BASE,
        mutate("600. 2.5", "-600. 2.5", CACHE_NET_BASE),
        True,
    ),
    # EK is the conservative key entry: momwire's kernel is momwire's kernel, so
    # the flag moves no number here — the gate is that it still MISSES, because
    # a card whose meaning is "compute the operator differently" must never be
    # answered from an entry built without it.
    ("EK toggled", CACHE_BASE, mutate("EX 0 1 5 0 1.\n", "EK\nEX 0 1 5 0 1.\n"), False),
)


@pytest.mark.parametrize(
    "base,mutant,moves_numbers",
    [(m[1], m[2], m[3]) for m in _OPERATOR_MUTATIONS],
    ids=[m[0] for m in _OPERATOR_MUTATIONS],
)
def test_an_operator_change_misses_the_cross_deck_cache(base, mutant, moves_numbers):
    """The care point. One mutation per class of card that moves the operator;
    each must be a MISS and each must answer with its own physics, checked
    against the same deck rendered from an empty cache."""
    baseline = cold_render(base)
    assert "ERROR-NEC2C" not in baseline, baseline
    before = cache_counts()
    served = cache_render(mutant)
    after = cache_counts()
    assert after["hits"] == before["hits"], "served a stale operator"
    assert after["misses"] == before["misses"] + 1
    assert "ERROR-NEC2C" not in served, served
    assert body_lines(served) == body_lines(cold_render(mutant))
    if moves_numbers:
        assert aip_impedances(served) != aip_impedances(baseline)


# Cards that change what is PRINTED or how the answer is read out, never the
# operator behind it. Each must be served from the base's entry.
_READOUT_MUTATIONS = (
    ("CM text", mutate("CM cross-deck cache probe", "CM something else entirely")),
    (
        "card formatting",
        mutate(
            "GW 1 9 0. 0. 5.0 0. 0. 10.0 0.001",
            "GW,1,9,0.,0.,5.,0.,0.,10.,.001",
        ),
    ),
    ("EX voltage", mutate("EX 0 1 5 0 1.", "EX 0 1 5 0 2.5")),
    ("RP grid", mutate("XQ\n", "RP 0 7 13 1001 0 0 30 30 1000\nXQ\n")),
    ("YY card", mutate("EX 0 1 5 0 1.\n", "YY 1 3 1 7\nEX 0 1 5 0 1.\n")),
    ("PT card", mutate("XQ\n", "PT -1\nXQ\n")),
    ("MP card", mutate("XQ\n", "MP 16 32\nXQ\n")),
)


@pytest.mark.parametrize(
    "mutant",
    [m[1] for m in _READOUT_MUTATIONS],
    ids=[m[0] for m in _READOUT_MUTATIONS],
)
def test_a_readout_change_hits_the_cross_deck_cache_and_answers_fresh(mutant):
    """The other half of the care point: a deck that differs only in what it
    prints must be SERVED — no parse, no mesh, no fill — and must still print
    exactly what a cold cache prints for it."""
    cold_render(CACHE_BASE)
    before = cache_counts()
    served = cache_render(mutant)
    after = cache_counts()
    assert after["hits"] == before["hits"] + 1, "re-solved an operator it had"
    assert after["misses"] == before["misses"]
    assert after["fills"] == before["fills"], "a hit at one frequency must not fill"
    assert "ERROR-NEC2C" not in served, served
    assert body_lines(served) == body_lines(cold_render(mutant))


def test_a_new_frequency_reuses_the_geometry_and_pays_only_the_fill():
    """The issue's third bullet: a crew member handed the same structure at
    another frequency skips the parse and the mesh — a solver-level HIT — and
    pays exactly one new fill inside it."""
    mutant = mutate("14.1", "21.1")
    cold_render(CACHE_BASE)
    before = cache_counts()
    served = cache_render(mutant)
    after = cache_counts()
    assert after["hits"] == before["hits"] + 1
    assert after["misses"] == before["misses"]
    assert after["fills"] == before["fills"] + 1
    assert body_lines(served) == body_lines(cold_render(mutant))


# The GD proof. The second medium reaches NEC's far field only through RP's
# cliff modes, so it is deliberately OUT of the key and a GD knob-drag HITS.
# What makes that safe is that a hit rebinds `portal_deck` to the arriving
# deck, and the comparison here is against a FRESH PROCESS rather than against
# the served run itself — so this stays a proof if GD ever grows a far field.
GD_BASE = (
    "CE gd probe\n"
    "GW 1 9 0. 0. 2.0 0. 0. 7.0 0.001\n"
    "GE -1\nGN 1\nGD 2,0,0,0,13.,.005,0.,0.\n"
    "EX 0 1 5 0 1.\nFR 0 1 0 0 14.1 0\nXQ\n"
)


def test_a_gd_card_change_hits_the_cache_and_still_answers_fresh():
    moved = GD_BASE.replace("13.,.005", "80.,.01")
    assert moved != GD_BASE
    cold_render(GD_BASE)
    before = cache_counts()
    served = cache_render(moved)
    assert cache_counts()["hits"] == before["hits"] + 1
    assert "ERROR-NEC2C" not in served, served
    proc = subprocess.run(
        [sys.executable, "-m", "antennaknobs.nec_portal"],
        input=moved + "NX\n",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0 and proc.stderr == ""
    assert frame_lines(served) == frame_lines(proc.stdout)


def test_a_hit_rebinds_the_arriving_deck_onto_the_cached_solver():
    """The invariant the GD exclusion rests on. Everything a cached instance
    derived from its original deck is in the key and therefore identical, but
    `portal_deck` is a live reference the printout reads through — so a hit
    hands it the deck actually being rendered, and no cached instance can carry
    a stale card that the key deliberately does not watch."""
    cold_render(GD_BASE)
    solver = next(iter(nec_portal._solver_cache.values()))
    assert (
        solver.portal_deck.second_medium == nec_portal.parse_deck(GD_BASE).second_medium
    )
    moved = GD_BASE.replace("13.,.005", "80.,.01")
    cache_render(moved)
    assert (
        solver.portal_deck.second_medium == nec_portal.parse_deck(moved).second_medium
    )


def test_a_second_medium_change_through_a_warm_cache_moves_the_cliff_pattern():
    """The combined pin for #823 × #842. The cliff modes made the second
    medium load-bearing in the far field, and it is read through
    ``solver.portal_deck.second_medium`` — exactly the attribute a cache hit
    rebinds. So a GD edit through a WARM cache must (a) hit, (b) move the
    RADIATION PATTERNS rows, and (c) match a fresh process byte for byte. A
    stale second medium would pass (a) and fail (b) or (c)."""
    base = fixture_deck("dipole_rp2_linear_cliff")
    moved = base.replace("GD 0 0 0 0 5. .001 10. -2.", "GD 0 0 0 0 80. .04 10. -2.")
    assert moved != base
    first = cold_render(base)
    before = cache_counts()
    served = cache_render(moved)
    assert cache_counts()["hits"] == before["hits"] + 1
    pattern_rows = lambda text: [  # noqa: E731 - two-line local helper
        ln for ln in text.splitlines() if len(ln.split()) == 12 and "." in ln
    ]
    assert pattern_rows(served) != pattern_rows(first), (
        "the warm-cache answer ignored the new second medium"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "antennaknobs.nec_portal"],
        # fixture_deck strips the framing NX AND the trailing newline.
        input=moved + "\nNX\n",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0 and proc.stderr == ""
    fresh = frame_lines(proc.stdout)
    assert fresh, "the fresh process rendered nothing — deck framing bug"
    assert frame_lines(served) == fresh


def test_a_cached_entry_is_re_sized_by_the_fills_it_grew():
    """An entry GROWS after it is stored — a sweep adds an `at()` fill per
    frequency — so the size taken at insertion drifts low exactly on the deck
    the cache exists to serve. The entry that just rendered is re-walked when
    the next deck arrives, which is what keeps the cap honest."""
    cache_reset()
    cache_render(CACHE_BASE)
    key = next(iter(nec_portal._solver_cache))
    at_insert = nec_portal._cache_sizes[key]
    for mhz in ("18.1", "21.1", "24.1", "28.1", "50.1"):
        cache_render(mutate("14.1", mhz))
    cache_render(_bound_deck(99.0))
    # Six frequencies through one geometry, plus the arrival that re-sized it.
    counts = cache_counts()
    assert (counts["hits"], counts["misses"], counts["fills"]) == (5, 2, 7)
    assert nec_portal._cache_sizes[key] > at_insert


def test_a_repeated_probe_skips_the_solve_it_paid_for():
    """The reason the feature exists. Measured at authoring time on
    `catalog_wire_w8jk`, the biggest committed deck (106 segments): 154 ms cold
    against 11 ms served, a factor of fourteen — what is left in the served
    pass is the readout algebra and the printout itself, which no cache can
    skip. The ASSERT is on the counters, not the clock: even a "deliberately
    loose" wall-clock ratio proved flaky under full-suite load (warm BLAS
    shrinks the cold fill, a GC pause inflates the served one), and the
    deterministic form of "costs less than the solve it skips" is that the
    second pass performs zero geometry parses and zero fills."""
    body = fixture_deck("catalog_wire_w8jk")
    cache_reset()
    cache_render(body)
    after_cold = dict(nec_portal._cache_stats)
    assert (after_cold["misses"], after_cold["fills"]) == (1, 1)
    cache_render(body)
    after_served = nec_portal._cache_stats
    assert after_served["hits"] == 1
    assert after_served["misses"] == after_cold["misses"], "second pass re-parsed"
    assert after_served["fills"] == after_cold["fills"], "second pass re-filled"


def _bound_deck(z: float) -> str:
    return (
        "CE bound probe\n"
        f"GW 1 9 0. 0. {z} 0. 0. {z + 5.0} 0.001\n"
        "GE 0\nEX 0 1 5 0 1.\nFR 0 1 0 0 14.1 0\nXQ\n"
    )


def test_the_cache_evicts_by_bytes_and_an_evicted_geometry_re_solves(monkeypatch):
    """The bound. The cap is patched to about two and a half entries rather
    than filling the shipped few hundred MB, because what needs proving is the
    eviction ORDER and that an evicted structure comes back correct — not the
    value of a constant."""
    cache_reset()
    assert "ERROR-NEC2C" not in cache_render(_bound_deck(10.0))
    first_key = next(iter(nec_portal._solver_cache))
    # The second arrival re-sizes the first entry now that its fill is done, so
    # this is a grown entry's size and not an empty one's.
    cache_render(_bound_deck(20.0))
    monkeypatch.setattr(
        nec_portal, "_CACHE_BYTES_CAP", int(nec_portal._cache_sizes[first_key] * 2.5)
    )
    for z in (30.0, 40.0, 50.0, 60.0):
        cache_render(_bound_deck(z))
    assert nec_portal._cache_stats["evictions"] >= 2
    assert nec_portal._cache_stats["bytes"] <= nec_portal._CACHE_BYTES_CAP
    assert len(nec_portal._solver_cache) <= 3
    assert first_key not in nec_portal._solver_cache
    assert first_key not in nec_portal._cache_sizes

    # Newest still resident.
    before = cache_counts()
    cache_render(_bound_deck(60.0))
    assert cache_counts()["hits"] == before["hits"] + 1

    # Oldest gone — and it re-solves to the same printout it gave when it was
    # resident, which is what "degrades to today's behaviour" has to mean.
    before = cache_counts()
    served = cache_render(_bound_deck(10.0))
    assert cache_counts()["misses"] == before["misses"] + 1
    assert body_lines(served) == body_lines(cold_render(_bound_deck(10.0)))


def test_the_cache_evicts_the_least_RECENTLY_used_not_the_oldest(monkeypatch):
    """A knob returned to a value probed long ago is the hit this feature is
    for, so a re-used entry has to be young again. Without the reorder on a
    hit this is a FIFO and the entry just served would be the next to go."""
    cache_reset()
    for z in (10.0, 20.0, 30.0):
        cache_render(_bound_deck(z))
    oldest, middle, _newest = list(nec_portal._solver_cache)
    monkeypatch.setattr(
        nec_portal, "_CACHE_BYTES_CAP", int(nec_portal._cache_sizes[oldest] * 2.5)
    )
    before = cache_counts()
    cache_render(_bound_deck(10.0))  # touched: the oldest becomes the newest
    assert cache_counts()["hits"] == before["hits"] + 1
    cache_render(_bound_deck(40.0))
    assert oldest in nec_portal._solver_cache
    assert middle not in nec_portal._solver_cache


@pytest.mark.parametrize(
    "refused",
    [
        # Refused while PARSING — never reaches the cache at all.
        CACHE_BASE.replace("EX 0 1 5 0 1.\n", "SP 0 0 0. 0. 0. 0. 0.\n"),
        # Refused while BUILDING the solver: tag 2 does not exist, and a deck
        # with no EX has no ports. Both raise out of `DeckSolver.__init__`,
        # after the key has been computed and before anything is stored.
        CACHE_BASE.replace("EX 0 1 5", "EX 0 2 5"),
        CACHE_BASE.replace("EX 0 1 5 0 1.\n", ""),
    ],
    ids=["parse refusal", "unknown tag", "no EX card"],
)
def test_a_refused_deck_neither_poisons_nor_consults_the_cache(refused):
    """#829's error path against #823's cache. A refusal must move nothing —
    no entry, no statistic — and the same structure sent valid afterwards must
    solve fresh and print what a cold cache prints for it."""
    cache_reset()
    before = cache_counts()
    out = cache_render(refused)
    assert "ERROR-NEC2C" in out, out
    assert cache_counts() == before
    assert not nec_portal._solver_cache
    assert not nec_portal._cache_sizes

    served = cache_render(CACHE_BASE)
    assert "ERROR-NEC2C" not in served, served
    assert cache_counts()["misses"] == before["misses"] + 1
    assert body_lines(served) == body_lines(cold_render(CACHE_BASE))


def test_a_refusal_after_a_hit_leaves_the_hit_entry_intact():
    """The other order: a good deck, a refused one, then the good deck again —
    the refusal must not have disturbed the entry standing behind it."""
    cold_render(CACHE_BASE)
    cache_render(CACHE_BASE.replace("EX 0 1 5", "EX 0 2 5"))
    before = cache_counts()
    served = cache_render(CACHE_BASE)
    assert cache_counts()["hits"] == before["hits"] + 1
    assert body_lines(served) == body_lines(cold_render(CACHE_BASE))


def test_the_cache_is_per_invocation_like_the_basis():
    """`main` empties the cache exactly where it re-reads `--basis`: engine
    state is per invocation, so a second call cannot be served from the
    first's — which is also what keeps entries built under one basis from
    occupying the cap under another."""
    deck = fixture_deck("dipole_free_space") + "\nNX\n"
    for _ in range(2):
        _rc, _out, _err = _run_main(["--cache"], deck=deck)
        counts = cache_counts()
        assert (counts["hits"], counts["misses"], counts["fills"]) == (0, 1, 1)
        assert len(nec_portal._solver_cache) == 1


def test_the_operator_key_carries_the_basis():
    """One process has one `--basis`, so this can never differ between two live
    decks — the key carries it anyway so it cannot be read wrong, and so a
    future in-process basis switch cannot serve the wrong physics."""
    deck = nec_portal.parse_deck(CACHE_BASE)
    default = nec_portal._operator_key(deck)
    original = nec_portal._active_basis
    try:
        nec_portal._active_basis = nec_portal._BASES["sinusoidal"]
        assert nec_portal._operator_key(deck) != default
    finally:
        nec_portal._active_basis = original
    assert nec_portal._operator_key(deck) == default


# --- the three cache modes: off, dry-run, serving -----------------------------
#
# Serving is opt-in and the shipped default is OFF, because the workload the
# cache exploits is a live SimNEC session's re-probe rate and nobody has
# measured one. So the default path has to be provably the pre-#823 path — not
# "the cache with nothing in it" — and there has to be a way to measure the
# session without serving anything, which is what `--cache-stats` alone is.
#
# The evidence here is a spy on the two things the off path may not do:
# construct fewer solvers than there are decks, and compute an operator key.


def _spy_cache_machinery(monkeypatch) -> tuple[list, list]:
    """(solver constructions, operator-key computations) for one test.

    A counter cannot prove the off path, because the off path does not count —
    that is the property under test. These do, from outside."""
    built: list[str] = []
    keyed: list[str] = []
    real_init = nec_portal.DeckSolver.__init__
    real_key = nec_portal._operator_key

    def init_spy(self, deck):
        built.append("build")
        real_init(self, deck)

    def key_spy(deck):
        keyed.append("key")
        return real_key(deck)

    monkeypatch.setattr(nec_portal.DeckSolver, "__init__", init_spy)
    monkeypatch.setattr(nec_portal, "_operator_key", key_spy)
    return built, keyed


def _twice(name: str = "dipole_free_space") -> str:
    """One fixture deck, framed and sent twice — the repeat probe in miniature."""
    text = fixture_deck(name) + "\nNX\n"
    return text * 2


def _stream_main(argv: list[str], stdin_text: str) -> list[str]:
    """`main` over a stdin stream, returning one chunk per deck."""
    buffer = io.StringIO()
    rc = main(argv, stdin=io.StringIO(stdin_text), stdout=buffer, stderr=io.StringIO())
    assert rc == 0
    return deck_chunks(buffer.getvalue())


def test_the_cache_is_off_unless_the_command_line_asks(monkeypatch):
    """The shipped default. Two identical decks, and the second is genuinely
    re-solved: two constructions, and NO key computed — the off branch is the
    pre-#823 path to the byte, not a cache that happens to be empty."""
    built, keyed = _spy_cache_machinery(monkeypatch)
    chunks = _stream_main([], _twice())
    assert len(chunks) == 2
    assert body_lines(chunks[1]) == body_lines(chunks[0])
    assert len(built) == 2, "the second deck was served rather than re-solved"
    assert keyed == [], "the off path computed a cache key"
    assert nec_portal._cache_mode() == "off"
    assert not nec_portal._solver_cache and not nec_portal._cache_sizes
    assert set(nec_portal._cache_stats.values()) == {0}


def test_the_cache_flag_turns_serving_on(monkeypatch):
    """And `--cache` is all it takes: one construction for two decks, the
    second answered from the first's factors, same printout."""
    built, keyed = _spy_cache_machinery(monkeypatch)
    chunks = _stream_main(["--cache"], _twice())
    assert len(chunks) == 2
    assert body_lines(chunks[1]) == body_lines(chunks[0])
    assert len(built) == 1 and len(keyed) == 2
    assert nec_portal._cache_mode() == "serving"
    counts = cache_counts()
    assert (counts["hits"], counts["misses"], counts["fills"]) == (1, 1, 1)


def test_cache_stats_alone_counts_the_hits_without_serving(monkeypatch, tmp_path):
    """The zero-risk live experiment. `--cache-stats` on its own solves every
    deck fresh — stock behaviour, stock answers, nothing retained — and records
    how many of them a cache WOULD have served. That is the number the
    default-off decision is waiting on, obtainable from a real session without
    putting a served answer anywhere near it."""
    path = tmp_path / "stats.json"
    built, keyed = _spy_cache_machinery(monkeypatch)
    chunks = _stream_main(["--cache-stats", str(path)], _twice())
    assert len(chunks) == 2
    assert body_lines(chunks[1]) == body_lines(chunks[0])
    assert nec_portal._cache_mode() == "dry-run"
    assert len(built) == 2, "a dry run served a deck"
    assert len(keyed) == 2, "a dry run has to key every deck to count it"
    assert not nec_portal._solver_cache and not nec_portal._cache_sizes

    stats = json.loads(path.read_text())
    assert stats["mode"] == "dry-run"
    assert (stats["hits"], stats["misses"]) == (1, 1)
    assert stats["decks_rendered"] == 2
    assert stats["fills"] == 2, "a dry run still pays every fill — that is the point"
    assert (stats["entries"], stats["bytes"], stats["evictions"]) == (0, 0, 0)


def test_a_dry_run_answers_exactly_what_a_stock_process_answers(tmp_path):
    """Counting may not perturb the physics: a dry-run deck is compared to the
    same deck through a process carrying no flags at all."""
    path = tmp_path / "stats.json"
    text = fixture_deck("dipole_rp_pattern") + "\nNX\n"
    proc = subprocess.run(
        [sys.executable, "-m", "antennaknobs.nec_portal"],
        input=text,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0 and proc.stderr == ""
    chunks = _stream_main(["--cache-stats", str(path)], text)
    assert len(chunks) == 1
    assert frame_lines(chunks[0]) == frame_lines(proc.stdout)


def test_both_flags_together_count_the_real_cache(tmp_path):
    """`--cache --cache-stats PATH` is serve AND measure — the mode to run once
    the dry run says the hit rate is worth having."""
    path = tmp_path / "stats.json"
    chunks = _stream_main(["--cache", "--cache-stats", str(path)], _twice())
    assert len(chunks) == 2
    stats = json.loads(path.read_text())
    assert stats["mode"] == "serving"
    assert (stats["hits"], stats["misses"], stats["fills"]) == (1, 1, 1)
    assert stats["entries"] == 1 and stats["bytes"] > 0


def test_the_stats_file_is_rewritten_after_every_deck(tmp_path):
    """SimNEC ends a session with `Process.destroy()` — a kill, not an EOF — so
    a file written at exit is a file that never appears. It is written at every
    deck boundary instead, which this reads BETWEEN the two decks by holding up
    the stdin stream."""
    path = tmp_path / "stats.json"
    text = fixture_deck("dipole_free_space") + "\nNX\n"
    midway: list[dict] = []

    def stream():
        yield from io.StringIO(text)
        # `main` asks for this line only after deck one has been framed.
        midway.append(json.loads(path.read_text()))
        yield from io.StringIO(text)

    buffer = io.StringIO()
    rc = main(
        [f"--cache-stats={path}"],
        stdin=stream(),
        stdout=buffer,
        stderr=io.StringIO(),
    )
    assert rc == 0
    assert midway and midway[0]["decks_rendered"] == 1
    assert midway[0]["mode"] == "dry-run"
    assert json.loads(path.read_text())["decks_rendered"] == 2
    # And the transcript is untouched by any of it.
    assert len(deck_chunks(buffer.getvalue())) == 2


def test_a_refused_deck_still_counts_in_the_stats_denominator(tmp_path):
    """The hit rate needs an honest denominator, and a refused deck is a deck
    the session sent. It moves no cache statistic — that is the #829 contract —
    but it is counted as rendered."""
    path = tmp_path / "stats.json"
    good = fixture_deck("dipole_free_space") + "\nNX\n"
    bad = "CE refused\nGW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGE 0\nSP 0 0\nNX\n"
    chunks = _stream_main(["--cache-stats", str(path)], good + bad)
    assert len(chunks) == 2 and "ERROR-NEC2C" in chunks[1]
    stats = json.loads(path.read_text())
    assert stats["decks_rendered"] == 2
    assert (stats["hits"], stats["misses"]) == (0, 1)


def test_the_cache_flags_ride_the_version_probe_unchanged():
    """SimNEC probes `<full command line> -version`, so every flag the portal
    dialog can carry has to leave that line alone."""
    for argv in (
        ["--cache", "-version"],
        ["--cache-stats", "/nonexistent/dir/stats.json", "-version"],
        ["--cache", "--cache-stats=/nonexistent/dir/stats.json", "-version"],
        ["--basis", "sinusoidal", "--cache", "-version"],
    ):
        rc, out, _err = _run_main(argv)
        assert (rc, out) == (0, f"{nec_portal.PROBE_VERSION}\n"), argv


def test_cache_stats_without_a_path_fails_fast_and_nonzero():
    """Same contract as an unknown `--basis`: a malformed portal-dialog line is
    caught by the configure-time probe, not by the first deck of a session."""
    for argv in (["--cache-stats"], ["--cache-stats", "--cache"], ["--cache-stats="]):
        rc, out, _err = _run_main([*argv, "-version"])
        assert rc == 3 and "--cache-stats" in out, argv


def test_an_unwritable_stats_path_costs_the_measurement_not_the_session(tmp_path):
    """This engine may write NOTHING to stdout or stderr, so a bad path can
    only be allowed to lose the file. The decks still answer."""
    path = tmp_path / "no-such-dir" / "stats.json"
    buffer = io.StringIO()
    errors = io.StringIO()
    rc = main(
        ["--cache-stats", str(path)],
        stdin=io.StringIO(_twice()),
        stdout=buffer,
        stderr=errors,
    )
    assert rc == 0 and errors.getvalue() == ""
    assert not path.exists()
    chunks = deck_chunks(buffer.getvalue())
    assert len(chunks) == 2 and "ERROR-NEC2C" not in buffer.getvalue()
