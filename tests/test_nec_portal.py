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


def test_version_probe_matches_executes_versionA_regex():
    out = io.StringIO()
    assert main(["-version"], stdin=io.StringIO(""), stdout=out) == 0
    lines = out.getvalue().splitlines()
    assert len(lines) == 1, f"the probe must print exactly one line: {lines}"

    match = VERSION_A.fullmatch(lines[0].strip())
    assert match, f"{lines[0]!r} does not match nec2c\\.ae6ty\\.(.*)"

    # Execute.testCommand feeds group(1) straight to Double.valueOf. A greedy
    # (.*) means ANY non-numeric tail — "momwire.9.1" included — throws and is
    # reported as "nec2c version too old:". One dot, nothing else.
    tail = match.group(1)
    assert tail.count(".") == 1, f"version tail {tail!r} is not Double-parseable"
    assert float(tail) > 0


def test_printout_banner_carries_the_momwire_identity():
    """The banner is not version-checked (the regexes are anchored and it is
    prefixed ``VERSION:``), so it is where the engine says who it really is."""
    text, _err = run_deck(fixture_deck("dipole_free_space"))
    assert f"VERSION:{nec_portal.BANNER_VERSION}" in text
    assert "momwire" in nec_portal.BANNER_VERSION
    assert "momwire" not in nec_portal.PROBE_VERSION


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

    ``TL`` is the live example after unit 3: the portal dialect can carry it,
    ``nec_import`` can even translate it, but no fixture pins how nec2c lays
    its rows out inside NETWORK DATA — so it takes the error path rather than
    a guessed layout.
    """
    out, err = deck_frame(
        "CE transmission line\n"
        "GW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\n"
        "GW 2 9 1. 0. -2.5 1. 0. 2.5 0.001\n"
        "GE 0\n"
        "EX 0 1 5 0 1.\n"
        "TL 1 5 2 5 50. 2.\n"
        "FR 0 1 0 0 30. 0\n"
        "XQ\n"
    )
    text = "\n".join(out)
    assert NX_ECHO.search(text), "the NX sentinel is missing on the error path"
    assert "ERROR-NEC2C: TL" in text
    # `ERROR:` as token 0 is what trips Execute's warning frame; the oracle's
    # own prefix deliberately does not.
    assert not any(line.split()[:1] == ["ERROR:"] for line in text.splitlines())
    assert err == []


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
    """
    deck, marker = case
    out, err = deck_frame(deck)
    text = "\n".join(out)
    assert NX_ECHO.search(text), f"{label}: no NX sentinel"
    assert marker in text, f"{label}: error does not mention {marker!r}:\n{text[-500:]}"
    # `ERROR:` as token 0 is what trips Execute's warning frame; the oracle's
    # own prefix deliberately does not.
    assert not any(line.split()[:1] == ["ERROR:"] for line in text.splitlines())
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
