"""antennaknobs#1404: `compare` read zero decks from every report and passed.

`_read_report` keyed rows on `rec["deck"]`; every writer in the tool writes
`rec["file"]`. So both dicts came back empty and `compare` printed

    decks: 0 vs 0; moved: 0

for any pair of reports — including two copies of one report — and exit 0. That
is in the published signed exe, so a working-group member comparing two NEC-5
builds has been getting a clean pass over nothing. It is also the exact failure
the report's own environment gate (#1344) exists to prevent, one level down.

Two halves to the fix and both are tested: read the key the writer writes, and
make an EMPTY comparison an error, because "moved: 0" over no decks is the most
convincing wrong answer this tool can give.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_cmp_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _report(path: Path, exe_name: str, rows, timing_valid=True):
    """A check report in the shape `cmd_check` writes: a `_meta` row then one
    row per deck keyed `file`."""
    meta = {
        "tool": "nec5_corpus.py",
        "step": "check",
        "exe": f"/x/{exe_name}",
        "timing_valid": timing_valid,
        "environment": {
            "env": {"OMP_NUM_THREADS": None},
            "platform": "linux-x",
            "machine": "x86_64",
            "jobs": 1,
            "binaries": {exe_name: {"bytes": 1, "sha256": "a" * 64}},
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"_meta": meta}) + "\n")
        for name, status, z in rows:
            f.write(
                json.dumps({"file": name, "status": status, "wall_s": 1.0, "z": z})
                + "\n"
            )


A_ROWS = [("a.nec", "ok", [[1, 3, 50.0, 1.0]]), ("b.nec", "timeout", [])]
B_ROWS = [("a.nec", "ok", [[1, 3, 50.0, 1.0]]), ("b.nec", "ok", [[1, 3, 51.0, 2.0]])]


def test_compare_reads_the_rows_the_writer_wrote(tool, tmp_path, capsys):
    """The bug itself: differing binaries plus --ignore-env, the A/B case the
    flag exists for. 2 decks each, and the one status move found."""
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _report(a, "nec5cl", A_ROWS)
    _report(b, "nec5cl-b5", B_ROWS)
    rc = tool.main(["compare", str(a), str(b), "--ignore-env"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "decks: 2 vs 2" in out, out
    assert "moved: 1" in out, out
    assert "b.nec: timeout -> ok" in out, out


def test_comparing_a_report_with_itself_finds_its_decks_and_no_movers(
    tool, tmp_path, capsys
):
    """The case that makes the old behaviour unmistakable: the same file twice
    reported `decks: 0 vs 0`. The environments match, so no --ignore-env."""
    a = tmp_path / "a.jsonl"
    _report(a, "nec5cl", A_ROWS)
    rc = tool.main(["compare", str(a), str(a)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "decks: 2 vs 2; moved: 0" in out, out


def test_an_empty_comparison_is_an_error_not_a_pass(tool, tmp_path, capsys):
    """The guard that makes this class of mistake loud next time. A report with
    a `_meta` row and no decks is a well-formed file and not a comparison."""
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _report(a, "nec5cl", [])
    _report(b, "nec5cl", A_ROWS)
    rc = tool.main(["compare", str(a), str(b)])
    out = capsys.readouterr().out
    assert rc != 0, out
    assert "no decks to compare" in out, out
    assert "has 0 deck rows" in out, out
    assert "moved" not in out, "a verdict must not be printed over no decks"


def test_a_row_keyed_deck_is_still_read(tool, tmp_path, capsys):
    """Accepting both keys, so a report written by some other producer (or an
    older one) is not silently empty either."""
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _report(a, "nec5cl", A_ROWS)
    lines = a.read_text().splitlines()
    with open(b, "w", encoding="utf-8") as f:
        for ln in lines:
            rec = json.loads(ln)
            if "file" in rec:
                rec["deck"] = rec.pop("file")
                rec["status"] = "ok"
            f.write(json.dumps(rec) + "\n")
    rc = tool.main(["compare", str(a), str(b)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "decks: 2 vs 2" in out, out
    assert "moved: 1" in out, out


# --------------------------------------------------------------------------
# and status alone was never the question a build A/B asks
# --------------------------------------------------------------------------

# One report against another over four decks, one per case:
#   same      identical impedance
#   below     a change under the default tolerance (printout last-digit noise)
#   above     a change over it
#   degen     |Z| under an ohm, where a percentage means nothing
#   nozrow    no impedance row on one side (a crash, a timeout, a plane wave)
Z_A = [
    ("same.nec", "ok", [[1, 3, 50.0, 1.0]]),
    ("below.nec", "ok", [[1, 3, 50.0, 1.0]]),
    ("above.nec", "ok", [[1, 3, 50.0, 1.0]]),
    ("degen.nec", "ok", [[1, 3, -0.53376, -0.27046]]),
    ("nozrow.nec", "crash", []),
]
Z_B = [
    ("same.nec", "ok", [[1, 3, 50.0, 1.0]]),
    ("below.nec", "ok", [[1, 3, 50.0005, 1.0]]),  # 1e-5 relative: noise
    ("above.nec", "timeout", [[1, 3, 55.0, 1.0]]),  # 1e-1 relative, and a status move
    ("degen.nec", "ok", [[1, 3, -0.51371, -0.24412]]),
    ("nozrow.nec", "ok", [[1, 3, 50.0, 1.0]]),
]


@pytest.fixture()
def z_out(tool, tmp_path, capsys):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _report(a, "nec5cl", Z_A)
    _report(b, "nec5cl", Z_B)
    rc = tool.main(["compare", str(a), str(b)])
    assert rc == 0
    return capsys.readouterr().out


def test_the_summary_counts_impedance_movers_beside_status_movers(z_out):
    assert "decks: 5 vs 5; moved: 2; impedance moved (> 0.0001): 1" in z_out, z_out


def test_a_mover_prints_both_impedances_verbatim_and_the_relative_size(z_out):
    assert "above.nec: 50+1j -> 55+1j" in z_out, z_out
    # |5| / |50+1j| = 9.998e-02, printed to three figures.
    assert "dZ/|Z| = 9.998e-02" in z_out, z_out


def test_a_change_below_the_tolerance_is_not_a_mover(z_out):
    """Last-digit printout noise sits near 1e-5, so a 1e-4 default keeps the list
    to the decks a reader should look at."""
    assert "below.nec" not in z_out.replace("impedance not compared", ""), z_out


def test_a_near_zero_impedance_is_degenerate_not_a_huge_mover(z_out):
    """The ga_pjw_1 lesson: -0.53 ohm to -0.51 ohm is 5 % of nothing, on a deck
    whose resistance is negative and unphysical before any build question. Put
    that at the top of a movers list and it displaces a real finding."""
    line = next(ln for ln in z_out.splitlines() if "degen.nec" in ln)
    assert "degenerate" in line and "percentage meaningless" in line, line
    assert "dZ/|Z|" not in line, line


def test_decks_with_no_impedance_row_are_counted_not_silently_dropped(z_out):
    assert "impedance not compared: 1 decks with no row on one side" in z_out, z_out


def test_the_tolerance_is_a_flag(tool, tmp_path, capsys):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _report(a, "nec5cl", Z_A)
    _report(b, "nec5cl", Z_B)
    tool.main(["compare", str(a), str(b), "--tol", "1e-6"])
    out = capsys.readouterr().out
    # At 1e-6 the noise deck joins the list; the degenerate one still does not.
    assert "impedance moved (> 1e-06): 2" in out, out
    assert "below.nec" in out, out


def test_only_the_first_impedance_row_is_compared(tool, tmp_path, capsys):
    """The sweep-row trap, as a test. A deck with a multi-point FR prints one row
    per frequency; comparing one report's LAST row against another's FIRST read a
    72 % disagreement into two builds that agree to the last digit (2026-09-11).
    """
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _report(a, "nec5cl", [("sweep.nec", "ok", [[1, 3, 50.0, 1.0], [1, 3, 900.0, 9.0]])])
    _report(b, "nec5cl", [("sweep.nec", "ok", [[1, 3, 50.0, 1.0], [1, 3, 111.0, 2.0]])])
    tool.main(["compare", str(a), str(b)])
    out = capsys.readouterr().out
    assert "impedance moved (> 0.0001): 0" in out, out
