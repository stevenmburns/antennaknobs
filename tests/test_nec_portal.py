"""The momwire SimNEC portal daemon (issue #792, unit 2).

Everything here runs in-process against the committed oracle fixtures — no
``nec2c`` binary, no subprocess. The oracle's *numbers* are not the contract
(a different basis and kernel will never match digit for digit); its *layout*
is, so the fixtures are compared structurally: same section sequence, same
column geometry, same token arity. Values are checked against momwire itself
(self-consistency and reciprocity), plus one loose cross-engine smoke bound on
the free-space dipole's impedance. Cross-engine value agreement is unit 3's
differential harness.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from antennaknobs import nec_portal
from antennaknobs.nec_portal import deck_frame, main, run_deck

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "nec_portal"

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
    "MATRIX TIMING",
    "ANTENNA INPUT PARAMETERS",
    "CURRENTS AND LOCATION",
    "POWER BUDGET",
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
