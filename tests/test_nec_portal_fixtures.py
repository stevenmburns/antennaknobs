"""Integrity of the SimNEC oracle fixtures (issue #792, unit 1).

``scripts/nec_portal_capture.py`` runs a corpus of NEC-2 decks through the real
engine SimNEC ships (``nec2c-ubuntu-x86``, VERSION:5b4az.ae6ty.1.17) and commits
the deck/printout pairs under ``tests/fixtures/nec_portal/``.  Later units
implement a momwire-backed replacement for that engine and are written against
these fixtures.

Everything here is fast and offline: the oracle binary is never needed.  The
one test that does shell out to it carries ``@pytest.mark.oracle_binary`` and
skips when the binary is absent, so the default lane is clean on CI.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "nec_portal"
CAPTURE_SCRIPT = REPO_ROOT / "scripts" / "nec_portal_capture.py"


def _load_capture_module():
    """Import the capture script by path — scripts/ is not on the package path."""
    spec = importlib.util.spec_from_file_location("nec_portal_capture", CAPTURE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CAPTURE = _load_capture_module()

MANIFEST = json.loads((FIXTURE_DIR / CAPTURE.MANIFEST_NAME).read_text())
NAMES = tuple(entry["name"] for entry in MANIFEST["decks"])

# nec2/Execute.versionB — the regex SimNEC applies to the engine's first line
# of output when it probes the command with `-version`.
VERSION_B = re.compile(r"5b4az\.ae6ty\.(.*)")
BANNER = re.compile(r"^VERSION:(\S+)$", re.MULTILINE)

# nec2/Execute.processResponse breaks out of the parse loop on this line —
# partsMatch(parts, "DATA", "CARD", "No:", "", "NX"), where "" is a wildcard.
NX_ECHO = re.compile(r"^\s*DATA CARD No:\s+\d+ NX\b", re.MULTILINE)

# `CM QQ 1` / `CE QQ 1` is an ae6ty extension: quiet mode, which suppresses the
# SEGMENTATION DATA block. The jar's own test deck used it (fixture successor:
# split_dipole_qq, #839).
QQ_QUIET = re.compile(r"^C[ME]\s+QQ\s+([1-9]\d*)\s*$", re.MULTILINE)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _out(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.out").read_text()


def _deck(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.deck").read_text()


def test_fixture_corpus_is_not_empty():
    assert len(NAMES) >= 20, f"suspiciously small corpus: {NAMES}"


def test_manifest_matches_files_on_disk():
    """The manifest is the corpus index: no strays, no missing pairs."""
    on_disk_decks = {p.stem for p in FIXTURE_DIR.glob("*.deck")}
    on_disk_outs = {p.stem for p in FIXTURE_DIR.glob("*.out")}
    assert on_disk_decks == set(NAMES)
    assert on_disk_outs == set(NAMES)

    extra = {
        p.name
        for p in FIXTURE_DIR.iterdir()
        if p.suffix not in (".deck", ".out")
        and p.name not in (CAPTURE.MANIFEST_NAME, "README.md")
    }
    assert not extra, f"unexpected files in the fixture dir: {sorted(extra)}"


def test_manifest_names_are_sorted():
    """Capture order is fixed so re-running never reshuffles the manifest."""
    assert list(NAMES) == sorted(NAMES)


@pytest.mark.parametrize("entry", MANIFEST["decks"], ids=lambda e: e["name"])
def test_manifest_hashes_match_the_committed_bytes(entry):
    assert _sha256(_deck(entry["name"])) == entry["deck_sha256"]
    assert _sha256(_out(entry["name"])) == entry["out_sha256"]


@pytest.mark.parametrize("name", NAMES)
def test_every_out_has_the_banner(name):
    """Every printout opens with the version banner SimNEC checks."""
    match = BANNER.search(_out(name))
    assert match is not None, f"{name}: no VERSION: banner"
    assert VERSION_B.fullmatch(match.group(1)), (
        f"{name}: banner {match.group(1)!r} does not match "
        "nec2/Execute.versionB (5b4az\\.ae6ty\\.(.*))"
    )


@pytest.mark.parametrize("name", NAMES)
def test_every_out_has_a_structure_section(name):
    text = _out(name)
    assert "STRUCTURE SPECIFICATION" in text
    # SEGMENTATION DATA is the one section the engine can legitimately drop:
    # `CM/CE QQ <n>` (n > 0) is ae6ty quiet mode and suppresses it.
    quiet = QQ_QUIET.search(_deck(name)) is not None
    assert ("SEGMENTATION DATA" in text) is not quiet


@pytest.mark.parametrize("name", NAMES)
def test_every_out_has_impedance_and_current_sections(name):
    text = _out(name)
    assert "ANTENNA INPUT PARAMETERS" in text, f"{name}: no impedance section"
    assert "CURRENTS AND LOCATION" in text, f"{name}: no current section"


@pytest.mark.parametrize("name", NAMES)
def test_every_out_ends_a_run_with_the_nx_echo(name):
    """The end-of-run sentinel: nec2/Execute stops at the NX card echo."""
    assert NX_ECHO.search(_out(name)), f"{name}: no 'DATA CARD No: n NX' echo"


@pytest.mark.parametrize("name", NAMES)
def test_every_deck_is_portal_dialect_and_ends_with_nx(name):
    """Decks use only cards nec2/NECSource emits, and terminate with NX."""
    deck = _deck(name)
    assert deck.endswith("NX\n")
    allowed = set(CAPTURE.PORTAL_CARDS) | {"NX"}
    for line in deck.splitlines():
        if not line.strip():
            continue
        card = line.split()[0].upper()
        assert card in allowed, f"{name}: non-portal card {card!r} in deck"


@pytest.mark.parametrize("name", NAMES)
def test_timings_are_canonicalised(name):
    """Wall-clock fields are zeroed so the capture is reproducible."""
    text = _out(name)
    for pattern, _ in CAPTURE._TIMING_SUBS:
        for match in pattern.finditer(text):
            assert CAPTURE.canonicalize_timings(match.group(0)) == match.group(0), (
                f"{name}: uncanonicalised timing {match.group(0)!r}"
            )


# --------------------------------------------------------------------------
# (Ward's YY report card was retired in #839.)


def _antenna_input_currents(text: str) -> list[list[tuple[float, float]]]:
    """Pull the CURRENT (REAL, IMAGINARY) columns out of each impedance table.

    Mirrors nec2/Execute's WAITINGFORSENSORS state for the NEC2C engine:
    a data row has exactly 11 whitespace-separated fields (samplesWidth) and
    the current sits at fields 4 and 5 (samplesOffset).
    """
    tables: list[list[tuple[float, float]]] = []
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
        tables[-1].append((float(parts[4]), float(parts[5])))
    return tables


# --------------------------------------------------------------------------
# residency
# --------------------------------------------------------------------------


def test_resident_transcript_frames_two_decks():
    """One process, two decks, each terminated by its own NX card.

    This is nec2/NEC2Daemon.submit's framing.  The engine echoes the NX card
    (SimNEC's end-of-run marker), then immediately reprints its banner for the
    deck it expects next — so the banner count is decks + 1.
    """
    deck = _deck("resident_two_decks")
    assert deck.count("\nNX\n") == 2

    text = _out("resident_two_decks")
    assert len(NX_ECHO.findall(text)) == 2
    assert len(BANNER.findall(text)) == 3
    assert text.count("STRUCTURE SPECIFICATION") == 2

    # Card numbering restarts at 1 inside each deck.
    first_cards = re.findall(r"DATA CARD No:\s+(\d+) (\w\w)", text)
    assert first_cards[:4] == [("1", "EX"), ("2", "FR"), ("3", "XQ"), ("4", "NX")]
    assert first_cards[4:8] == [("1", "EX"), ("2", "FR"), ("3", "XQ"), ("4", "NX")]


def test_resident_transcript_exits_on_stdin_eof():
    """Closing stdin after the last NX is what ends the resident process."""
    entry = next(e for e in MANIFEST["decks"] if e["name"] == "resident_two_decks")
    assert entry["returncode"] != 0
    assert "Error reading input file" in entry["stderr"]


# --------------------------------------------------------------------------
# the oracle itself (skipped unless the binary is installed)
# --------------------------------------------------------------------------

try:
    _ORACLE: Path | None = CAPTURE.find_oracle()
except CAPTURE.OracleMissing:
    _ORACLE = None

needs_oracle = pytest.mark.skipif(
    _ORACLE is None,
    reason="SimNEC oracle binary not installed (fixtures are committed instead)",
)


@pytest.mark.oracle_binary
@needs_oracle
def test_capture_is_idempotent():
    """`--check` regenerates the corpus and must find zero drift."""
    proc = subprocess.run(
        [sys.executable, str(CAPTURE_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr


def test_missing_oracle_fails_with_a_clear_message(tmp_path):
    """CI has no binary; regeneration must say so instead of crashing oddly."""
    with pytest.raises(CAPTURE.OracleMissing) as excinfo:
        CAPTURE.find_oracle(str(tmp_path / "no-such-nec2c"))
    message = str(excinfo.value)
    assert "oracle binary not found" in message
    assert CAPTURE.ORACLE_ENV in message
