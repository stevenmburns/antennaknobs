"""antennaknobs#1403: `--jobs N` oversubscribed the engine and said nothing.

`check --jobs N` runs N engine processes at once and left the thread counts to
the environment. With an OpenMP engine and `--jobs 4` on a 4-core box that is 16
threads contending: measured on the laptop 2026-09-11, the clean-room build took
1,651 s for the corpus under `--jobs 4` against a single-threaded reference's
1,447 s, while one deck at a time on an idle box the same binary is 1.8-2.3x
FASTER. The per-deck `wall_s` in such a report is not a speed measurement, and
nothing in the report used to say so.

Two halves, and the second is the one that protects a reader who was not there:
pin the counts to 1 per worker (unless the user set them, because someone who
asks for a thread count has a reason), and record `timing_valid` so a report
whose wall times cannot be compared SAYS it. `compare` warns on such a report.

The environment the engine actually receives is asserted with a stub that echoes
its own environment into the printout — reading the code cannot tell you what
`subprocess.run` was handed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"

DECK = "CM x\nCE\nGW 1 5 0 0 0 0 0 1 .001\nGE 0\nEX 0 1 3 0 1 0\nXQ\nEN\n"

# A "NEC-5" that reports its own environment into the printout, and NOTHING
# else. No ANTENNA INPUT PARAMETERS block on purpose: `run_exe` keeps the
# printout under `--keep-dir` only for a deck that is NOT ok, and the printout is
# the only channel through which this test can see the environment the
# subprocess received. So the deck lands `no-impedance`, which is what a
# printout-free stub should land, and the file survives to be read.
_ECHO_ENGINE = """
import os, sys
from pathlib import Path
sys.stdin.readline()
outp = sys.stdin.readline().strip()
keys = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
Path(outp).write_text(
    "\\n".join(f"ENVECHO {k}={os.environ.get(k, '<unset>')}" for k in keys) + "\\n"
)
"""


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_jobs_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def engine(tmp_path):
    script = tmp_path / "echo_engine.py"
    script.write_text(_ECHO_ENGINE)
    exe = tmp_path / "nec5cl-echo"
    exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}"\n')
    exe.chmod(0o755)
    return exe


def _run_check(tool, exe, tmp_path, jobs, name="out"):
    src = tmp_path / f"src-{name}"
    src.mkdir(exist_ok=True)
    (src / "d.nec").write_text(DECK)
    keep = tmp_path / f"keep-{name}"
    report = tmp_path / f"{name}.jsonl"
    rc = tool.main(
        [
            "check",
            "--exe",
            str(exe),
            "--src",
            str(src),
            "--jobs",
            str(jobs),
            "--timeout",
            "60",
            "--report",
            str(report),
            "--keep-dir",
            str(keep),
        ]
    )
    assert rc == 0
    rows = [json.loads(ln) for ln in report.read_text().splitlines() if ln.strip()]
    meta = next(r["_meta"] for r in rows if "_meta" in r)
    return meta, [r for r in rows if "_meta" not in r], keep


def _echoed(keep: Path) -> dict:
    """What the engine saw, read back out of the printout it wrote."""
    outs = list(keep.rglob("*.out"))
    assert outs, f"no printout kept under {keep}"
    got = {}
    for ln in outs[0].read_text().splitlines():
        if ln.startswith("ENVECHO "):
            k, _, v = ln[len("ENVECHO ") :].partition("=")
            got[k] = v
    return got


def test_one_job_leaves_the_environment_alone(tool, engine, tmp_path, monkeypatch):
    """With `--jobs 1` there is no contention to prevent, so the tool must not
    overrule whatever the box is set to."""
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.delenv(k, raising=False)
    meta, rows, keep = _run_check(tool, engine, tmp_path, 1, "j1")
    assert rows[0]["status"] == "no-impedance", rows
    assert _echoed(keep) == {
        "OMP_NUM_THREADS": "<unset>",
        "OPENBLAS_NUM_THREADS": "<unset>",
        "MKL_NUM_THREADS": "<unset>",
    }
    assert meta["timing_valid"] is True


def test_more_than_one_job_pins_every_thread_count_to_one(
    tool, engine, tmp_path, monkeypatch
):
    """The fix, asserted on what the SUBPROCESS received."""
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.delenv(k, raising=False)
    meta, _rows, keep = _run_check(tool, engine, tmp_path, 2, "j2")
    assert _echoed(keep) == {
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    assert meta["environment"]["engine_threads"]["effective"] == {
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    # 2 jobs x 1 thread fits on any box this runs on.
    assert meta["timing_valid"] is True


def test_a_thread_count_the_user_set_is_not_overruled(
    tool, engine, tmp_path, monkeypatch
):
    """Someone who asks for 2 threads per worker has a reason, and the report
    records that they asked rather than that the tool chose."""
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    monkeypatch.delenv("OPENBLAS_NUM_THREADS", raising=False)
    monkeypatch.delenv("MKL_NUM_THREADS", raising=False)
    meta, _rows, keep = _run_check(tool, engine, tmp_path, 2, "user")
    got = _echoed(keep)
    assert got["OMP_NUM_THREADS"] == "2", got
    assert got["OPENBLAS_NUM_THREADS"] == "1", got
    assert meta["environment"]["engine_threads"]["user_set"] == ["OMP_NUM_THREADS"]


def test_timing_valid_is_false_when_jobs_times_threads_exceeds_the_cpus(
    tool, engine, tmp_path, monkeypatch
):
    """The flag a reader needs when nobody tells them how the run was made."""
    cpus = os.cpu_count() or 1
    monkeypatch.setenv("OMP_NUM_THREADS", str(cpus))
    meta, _rows, _keep = _run_check(tool, engine, tmp_path, cpus + 1, "over")
    assert meta["timing_valid"] is False, meta["environment"]["engine_threads"]


def test_compare_warns_once_per_report_that_cannot_be_timed(tool, tmp_path, capsys):
    """A flagged report is still worth comparing — statuses and impedances are
    unaffected — so this is a warning and not a refusal."""
    from test_nec5_corpus_compare_1404 import _report  # the same writer shape

    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    rows = [("a.nec", "ok", [[1, 3, 50.0, 1.0]])]
    _report(a, "nec5cl", rows, timing_valid=False)
    _report(b, "nec5cl", rows, timing_valid=True)
    rc = tool.main(["compare", str(a), str(b)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert out.count("timing_valid: false") == 1, out
    assert "not a speed measurement" in out
    assert "decks: 1 vs 1; moved: 0" in out, out
