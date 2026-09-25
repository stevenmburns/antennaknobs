"""AK#1734 regression guard: snapshot every unique .ssn's import through the
production seam (``file_designs.builder_from_file``), to diff before/after.

For each file (deduplicated by content hash, first path wins): the refusal
text, or the repr of the wires and network built at the defaults, the
default params (notes included) and the knob symbols. One JSON line each.

    PYTHONPATH=<worktree>/src .venv/bin/python snapshot_ssn.py OUT.jsonl ROOT...

Diff two snapshots with ``diff_ssn.py BEFORE AFTER``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from antennaknobs.file_designs import builder_from_file


def snap(path: Path) -> dict:
    try:
        cls = builder_from_file(str(path))
    except (ValueError, SystemExit) as e:
        return {"import": f"refused: {e}"}
    out: dict = {
        "import": "ok",
        "params": repr(sorted(cls.default_params.items(), key=lambda kv: kv[0])),
    }
    knobs = cls.file_sy_knobs
    out["knobs"] = [s.param for s in knobs.symbols] if knobs else []
    try:
        b = cls()
        out["wires"] = repr(b.build_wires())
        out["network"] = repr(b.build_network())
    except ValueError as e:
        out["build"] = f"refused: {e}"
    return out


def main(out: str, roots: list[str]) -> None:
    seen: set[str] = set()
    with open(out, "w", encoding="utf-8") as f:
        for root in roots:
            for path in sorted(Path(root).expanduser().rglob("*.ssn")):
                h = hashlib.sha256(path.read_bytes()).hexdigest()
                if h in seen:
                    continue
                seen.add(h)
                row = {"path": str(path), "sha": h[:16], **snap(path)}
                f.write(json.dumps(row) + "\n")
                f.flush()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
