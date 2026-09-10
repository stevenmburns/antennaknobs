"""Smoke-gate the frozen NEC-5 corpus tool (issue #1376).

Usage::

    python scripts/freeze_nec5_corpus/smoke.py dist/nec5_corpus/nec5_corpus[.exe]

Every gate runs the FROZEN executable and compares it with the unfrozen
script run by THIS interpreter — a plain one, with nothing installed: the
script's promise is "one file, standard library only", and a frozen build
that needed more would have been built from a script that did.

1. ``--version`` prints ``nec5_corpus.py <VERSION>``, VERSION being the
   literal in the script the build was made from.
2. ``list`` exits 0 and names at least one source.
3. ``translate`` over the repo's NEC-2 and EZNEC-exported NEC-5 fixture
   decks, frozen and unfrozen, into two fresh directories: every written
   deck byte-equal, and the report line-equal once the ``started``
   timestamp in its ``_meta`` row is masked. Packaging may not move a card.
4. ``catalog-nec5/`` beside the exe carries the whole catalog: every deck
   the manifest names exists, is a NEC-5 deck, and none was skipped for
   want of an engine (the export's engine-free mode is what CI relies on).
5. ``check`` against a NEC-5 engine, ONLY when ``NEC5_EXE`` names one (CI
   runners have none): the frozen and unfrozen reports agree on every deck's
   status. Skipped with the sentence otherwise.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"
FIXTURE_DIRS = (ROOT / "tests" / "data", ROOT / "tests" / "fixtures" / "eznec_nec5")
# momwire's 65-deck NEC-2 portal corpus, reached through the submodule when
# it is checked out (the workflow checks it out for this; no build needed).
# Its decks carry a `.deck` suffix the tool does not match, so they are
# copied in as `.nec`. Without the submodule the gate runs on the repo's own
# five fixtures, four of which are EZNEC's NEC-5 exports that the tool
# refuses — a deterministic refusal is still a comparison.
PORTAL = ROOT / "momwire" / "tests" / "fixtures" / "nec_portal"

_STARTED = re.compile(r'"started": "[^"]*"')


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _tool_version() -> str:
    m = re.search(r'^VERSION = "([^"]+)"$', SCRIPT.read_text(encoding="utf-8"), re.M)
    assert m, f"no VERSION literal in {SCRIPT}"
    return m.group(1)


def _decks(src: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(src)): p.read_bytes()
        for p in sorted(src.rglob("*"))
        if p.is_file() and p.suffix.lower() in (".nec", ".inp")
    }


def _report(path: Path) -> list[str]:
    return [
        _STARTED.sub('"started": "<masked>"', line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _translate(runner: list[str], src: Path, out: Path) -> None:
    r = _run([*runner, "translate", "--src", str(src), "--out", str(out)])
    assert r.returncode == 0, f"translate exit {r.returncode}\n{r.stdout}\n{r.stderr}"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    exe = Path(argv[0]).resolve()
    assert exe.is_file(), exe
    frozen = [str(exe)]
    # -S: no site-packages, so the build environment's antennaknobs (installed
    # there for the catalog export) is invisible — the unfrozen side runs on
    # the standard library alone, which is the promise under test.
    unfrozen = [sys.executable, "-S", str(SCRIPT)]
    version = _tool_version()

    # 1. --version
    r = _run([*frozen, "--version"])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"nec5_corpus.py {version}", r.stdout
    print(f"gate 1: {r.stdout.strip()}")

    # 2. list
    r = _run([*frozen, "list"])
    assert r.returncode == 0 and r.stdout.strip(), r.stderr
    print(f"gate 2: list names {len(r.stdout.strip().splitlines())} line(s)")

    with tempfile.TemporaryDirectory(prefix="nec5_corpus_smoke_") as tmp:
        tmp = Path(tmp)
        src = tmp / "raw"
        for d in FIXTURE_DIRS:
            for p in d.glob("*.nec"):
                (src / d.name).mkdir(parents=True, exist_ok=True)
                shutil.copy(p, src / d.name / p.name)
        for p in PORTAL.glob("*.deck") if PORTAL.is_dir() else ():
            (src / "nec_portal").mkdir(parents=True, exist_ok=True)
            shutil.copy(p, src / "nec_portal" / p.with_suffix(".nec").name)
        inputs = _decks(src)
        assert len(inputs) >= 5, (
            f"only {len(inputs)} fixture decks under {FIXTURE_DIRS}"
        )

        # 3. translate, frozen vs unfrozen
        out_f, out_u = tmp / "frozen", tmp / "unfrozen"
        _translate(frozen, src, out_f)
        _translate(unfrozen, src, out_u)
        decks_f, decks_u = _decks(out_f), _decks(out_u)
        assert decks_f.keys() == decks_u.keys(), sorted(decks_f.keys() ^ decks_u.keys())
        differing = [k for k in decks_f if decks_f[k] != decks_u[k]]
        assert not differing, f"frozen translate differs on {differing}"
        rep_f = _report(out_f / "translate-report.jsonl")
        rep_u = _report(out_u / "translate-report.jsonl")
        assert rep_f == rep_u, "translate reports differ:\n" + "\n".join(
            f"- {a}\n+ {b}" for a, b in zip(rep_f, rep_u, strict=False) if a != b
        )
        statuses = _statuses(out_u / "translate-report.jsonl")
        assert "translated" in statuses.values(), "no deck translated"
        by_status = ", ".join(f"{v} {k}" for k, v in sorted(_counts(statuses).items()))
        print(
            f"gate 3: {len(inputs)} decks in, {len(decks_f)} out ({by_status}); "
            f"frozen == unfrozen byte for byte"
        )

        # 4. the catalog decks beside the exe: every deck the manifest names is
        # there and is a NEC-5 deck, and the count is the whole catalog.
        catalog = exe.parent / "catalog-nec5"
        manifest = json.loads((catalog / "manifest.json").read_text(encoding="utf-8"))
        names = [w["file"] for w in manifest["written"]]
        assert len(names) >= 400, f"only {len(names)} catalog decks written"
        missing = [n for n in names if not (catalog / n).is_file()]
        assert not missing, f"manifest names decks that are not there: {missing[:5]}"
        assert len(list(catalog.glob("*.nec"))) == len(names)
        for n in names[:50]:
            raw = (catalog / n).read_bytes()
            assert b"\r" not in raw, f"{n}: CRLF — the export must write LF everywhere"
            text = raw.decode("ascii", errors="replace")
            assert (
                text.startswith("CM antennaknobs catalog design") and "\nEN" in text
            ), n
        assert b"\r" not in (catalog / "manifest.json").read_bytes()
        no_engine = [
            s for s in manifest["skipped"] if "executable not found" in s["why"]
        ]
        assert not no_engine, "the export ran without its engine-free mode"
        print(
            f"gate 4: catalog-nec5 carries {len(names)} decks, "
            f"{len(manifest['skipped'])} designs skipped for cause"
        )

        # 5. check, only with an engine
        engine = os.environ.get("NEC5_EXE")
        if not engine:
            print("gate 5: skipped — NEC5_EXE is not set, no NEC-5 engine on this box")
            return 0
        for runner, out in ((frozen, out_f), (unfrozen, out_u)):
            r = _run(
                [*runner, "check", "--exe", engine, "--src", str(out), "--jobs", "2"]
            )
            assert r.returncode == 0, (
                f"check exit {r.returncode}\n{r.stdout}\n{r.stderr}"
            )
        status_f = _statuses(out_f / "check-report.jsonl")
        status_u = _statuses(out_u / "check-report.jsonl")
        assert status_f == status_u, f"check statuses differ: {status_f} vs {status_u}"
        print(f"gate 5: check agrees on {len(status_f)} deck(s) through {engine}")
    return 0


def _counts(statuses: dict[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in statuses.values():
        out[v] = out.get(v, 0) + 1
    return out


def _statuses(report: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in report.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "_meta" in row:
            continue
        out[row["file"]] = row["status"]
    return out


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
