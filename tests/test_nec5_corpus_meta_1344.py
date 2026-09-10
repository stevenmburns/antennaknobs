"""antennaknobs#1344: a corpus `check` report records the environment that
produced it, and `compare` refuses two reports whose environments differ."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "nec5_corpus", ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"
)
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


def test_environment_meta_states_absent_keys_and_hashes_the_binary(
    tmp_path, monkeypatch
):
    exe = tmp_path / "engine.exe"
    exe.write_bytes(b"not really an engine")
    (tmp_path / "libiomp5md.dll").write_bytes(b"runtime")
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    monkeypatch.setenv("MKL_NUM_THREADS", "4")
    meta = tool._environment_meta(str(exe), jobs=4)
    assert meta["env"]["OMP_NUM_THREADS"] is None  # absent, and SAID to be absent
    assert meta["env"]["MKL_NUM_THREADS"] == "4"
    assert meta["jobs"] == 4 and meta["python"]["executable"]
    assert set(meta["binaries"]) == {"engine.exe", "libiomp5md.dll"}
    assert len(meta["binaries"]["engine.exe"]["sha256"]) == 64


def _report(path: Path, environment, rows):
    with open(path, "w", encoding="utf-8") as f:
        meta = {"tool": "nec5_corpus.py", "version": "1.2", "step": "check"}
        if environment is not None:
            meta["environment"] = environment
        f.write(json.dumps({"_meta": meta}) + "\n")
        for deck, status in rows.items():
            f.write(json.dumps({"deck": deck, "status": status}) + "\n")


def test_compare_refuses_differing_environments_and_diffs_matching_ones(
    tmp_path, capsys
):
    env = {
        "env": {"OMP_NUM_THREADS": "4"},
        "platform": "x",
        "machine": "AMD64",
        "binaries": {},
        "jobs": 4,
    }
    a, b, c = tmp_path / "a.jsonl", tmp_path / "b.jsonl", tmp_path / "c.jsonl"
    _report(a, env, {"d1": "ok", "d2": "crash"})
    _report(b, {**env, "env": {"OMP_NUM_THREADS": "1"}}, {"d1": "ok", "d2": "timeout"})
    _report(c, env, {"d1": "ok", "d2": "timeout"})
    assert tool.cmd_compare(SimpleNamespace(a=str(a), b=str(b), ignore_env=False)) == 2
    assert "refusing to compare" in capsys.readouterr().out
    assert tool.cmd_compare(SimpleNamespace(a=str(a), b=str(c), ignore_env=False)) == 0
    out = capsys.readouterr().out
    assert "moved: 1" in out and "d2: crash -> timeout" in out
    # a report with no recorded environment (pre-1.2) is refused too
    _report(b, None, {"d1": "ok"})
    assert tool.cmd_compare(SimpleNamespace(a=str(a), b=str(b), ignore_env=False)) == 2


def test_the_check_meta_row_carries_the_environment():
    row = json.loads(
        tool._meta_row("check", exe="x", environment=tool._environment_meta("x"))
    )
    assert row["_meta"]["environment"]["env"]["OMP_NUM_THREADS"] == os.environ.get(
        "OMP_NUM_THREADS"
    )
