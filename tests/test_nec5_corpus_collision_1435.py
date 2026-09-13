"""antennaknobs#1435: two sources that translate to one output path must not
overwrite each other silently.

`translate` names a deck's output by replacing its extension with `.nec`. So
`cebik-w4rnl/Moxon-Rectangle-Notes-Models/mox10-1al.inp` and `mox10-1al.nec`,
which are different antennas in different planes, both wrote `mox10-1al.nec`,
and the later one won. The only trace was the report saying `written: 3077`
over a tree of 3,076 files.

The rule now: the kept source is decided before anything is written. An exact
`.nec` source wins over a same-named `.inp`, because that is what the tree
already held and deck paths are the join key of every existing report.
Otherwise the first in sorted order wins, and every other source is reported as
`collision`, naming the one kept. An NX split's `_N` outputs can land on
another source's path too, which the stem rule cannot see, so a write-time
check catches that. Either way the invariant holds: what the report says was
written is exactly what is on disk.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_collision_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _deck(length: int) -> str:
    return (
        f"CM collision\nCE\nGW 1 11 0 0 0 0 0 {length} 0.001\nGE 0\n"
        "EX 0 1 6 0 1 0\nFR 0 1 0 0 7.1 0\nXQ\nEN\n"
    )


NX_DECK = (
    "CE\nGW 1 11 0 0 1 0 0 11 0.001\nGE 0\nEX 0 1 6 0 1 0\nFR 0 1 0 0 7.1 0\nXQ\n"
    "NX\nCE\nGW 1 11 0 0 1 0 0 12 0.001\nGE 0\nEX 0 1 6 0 1 0\nFR 0 1 0 0 7.1 0\nXQ\nEN\n"
)


def _run(tool, src: Path, out: Path) -> dict:
    args = argparse.Namespace(
        src=str(src),
        out=str(out),
        report=None,
        offcenter="double",
        nofile=False,
        only=None,
        limit=None,
    )
    assert tool.cmd_translate(args) == 0
    lines = (out / "translate-report.jsonl").read_text(encoding="utf-8").splitlines()
    return {r["file"]: r for r in map(json.loads, lines[1:])}


def _on_disk(out: Path) -> list[str]:
    return sorted(p.relative_to(out).as_posix() for p in out.rglob("*.nec"))


def _assert_report_matches_disk(recs: dict, out: Path):
    reported = sorted(w for r in recs.values() for w in r["written"])
    assert reported == _on_disk(out), (reported, _on_disk(out))


def test_an_inp_beside_a_nec_keeps_the_nec_source(tool, tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "mox.inp").write_text(_deck(11), encoding="utf-8")
    (src / "sub" / "mox.nec").write_text(_deck(7), encoding="utf-8")
    recs = _run(tool, src, out)

    assert _on_disk(out) == ["sub/mox.nec"]
    assert recs["sub/mox.nec"]["status"] == "translated"
    assert recs["sub/mox.nec"]["written"] == ["sub/mox.nec"]
    loser = recs["sub/mox.inp"]
    assert loser["status"] == "collision"
    assert "sub/mox.nec" in loser["reason"]
    assert loser["written"] == []
    assert "sub/mox.nec" in (out / "sub" / "mox.nec").read_text(encoding="ascii")
    _assert_report_matches_disk(recs, out)


def test_names_that_differ_only_in_case_collide(tool, tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    (src / "foo.NEC").write_text(_deck(11), encoding="utf-8")
    (src / "foo.nec").write_text(_deck(7), encoding="utf-8")
    recs = _run(tool, src, out)

    assert recs["foo.nec"]["status"] == "translated"
    assert recs["foo.NEC"]["status"] == "collision"
    assert "foo.nec" in recs["foo.NEC"]["reason"]
    _assert_report_matches_disk(recs, out)


def test_an_nx_split_output_is_not_overwritten_by_a_same_named_source(tool, tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    (src / "nx.nec").write_text(NX_DECK, encoding="utf-8")
    (src / "nx_1.nec").write_text(_deck(7), encoding="utf-8")
    recs = _run(tool, src, out)

    assert recs["nx.nec"]["status"] == "translated"
    assert recs["nx.nec"]["written"] == ["nx_1.nec", "nx_2.nec"]
    assert recs["nx_1.nec"]["status"] == "collision"
    assert "nx.nec" in recs["nx_1.nec"]["reason"]
    assert recs["nx_1.nec"]["written"] == []
    assert "translated from nx_1.nec" not in (out / "nx_1.nec").read_text(
        encoding="ascii"
    )
    _assert_report_matches_disk(recs, out)


@pytest.mark.parametrize("names", [["a.nec", "b.nec"], ["a.inp", "b.nec", "c.NEC"]])
def test_distinct_names_are_all_translated(tool, tmp_path, names):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    for n in names:
        (src / n).write_text(_deck(11), encoding="utf-8")
    recs = _run(tool, src, out)
    assert {r["status"] for r in recs.values()} == {"translated"}
    _assert_report_matches_disk(recs, out)
