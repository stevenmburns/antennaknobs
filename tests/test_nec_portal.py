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

    ``IS`` is the live example after issue #800 took ``PT`` and ``MP`` off
    this list (#799 took ``TL``): the portal dialect can carry it, but its
    semantics are NEC-4.2's insulated-wire model, which momwire does not have —
    so it takes the error path rather than silently solving a bare wire.
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
    assert "ERROR-NEC2C: IS" in text
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


def test_the_rp_modes_that_would_use_a_gd_are_still_refused():
    """The fidelity gate — why accepting ``GD`` is not a silent lie.

    NEC-2 reaches the second medium in the far field ALONE, and there only
    through ``RP``'s cliff and ground-screen modes. Measured on the oracle
    with the cliff card of ``dipole_gd_cliff_sommerfeld``: under ``RP 0`` the
    pattern table is byte-identical with and without it; under ``RP 2`` a
    ``FAR FIELD GROUND PARAMETERS`` block appears and every gain moves. So
    the deck shapes where ``GD`` is inert are the shapes this engine runs,
    and the shapes where it is not are refused by name (issue #802) — this
    engine can never be asked a cliff question and answer it as flat ground.
    """
    head = (
        "CE gd cliff pattern\nGW 1 9 0. 0. 0.5 0. 0. 5.0 0.001\nGE 1\n"
        "GN 0 0 0 0 13. .005\nGD 0 0 0 0 5. .001 20. -2.\n"
        "EX 0 1 1 0 1.\nFR 0 1 0 0 14.1 0\n"
    )
    for mode in (1, 2, 3, 4, 5, 6):
        text = run_deck(head + f"RP {mode} 3 3 1001 0 0 30 30 1000\nXQ\n")[0]
        assert f"RP mode {mode} is not supported" in text, mode
        assert NX_ECHO.search(text), mode
    # ...and the mode SimNEC actually writes runs, second medium or not.
    text = run_deck(head + "RP 0 3 3 1001 0 0 30 30 1000\nXQ\n")[0]
    assert "ERROR-NEC2C" not in text
    assert "RADIATION PATTERNS" in text


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
