"""Diff two ``snapshot_ssn.py`` snapshots by content hash (AK#1734): every
file whose import, knobs, params, wires or network changed, and a count of
the files that imported before and are unchanged."""

from __future__ import annotations

import json
import sys


def load(p: str) -> dict:
    with open(p, encoding="utf-8") as f:
        return {r["sha"]: r for r in map(json.loads, f)}


def main(a: str, b: str) -> int:
    before, after = load(a), load(b)
    same = changed = 0
    regress = 0
    for sha, r0 in before.items():
        r1 = after.get(sha)
        if r1 == r0:
            same += 1
            continue
        changed += 1
        was_ok = r0["import"] == "ok" and "build" not in r0
        if was_ok:
            regress += 1
        print(f"== {r0['path']}{'  [IMPORTED BEFORE]' if was_ok else ''}")
        for k in sorted(set(r0) | set(r1 or {})):
            if k in ("path", "sha"):
                continue
            v0, v1 = r0.get(k), (r1 or {}).get(k)
            if v0 != v1:
                print(
                    f"  {k}:\n    before: {str(v0)[:400]}\n    after:  {str(v1)[:400]}"
                )
    print(
        f"{len(before)} files; {same} unchanged; {changed} changed; "
        f"{regress} of the changed imported and built before"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
