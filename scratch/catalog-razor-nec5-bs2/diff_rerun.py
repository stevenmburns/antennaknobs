"""Diff the published re-run against b9bc3e2f0's records and score R1-R4.

    python scratch/catalog-razor-nec5-bs2/diff_rerun.py

`RERUN-2026-09-15.md` registers the predicted-movement set (committed as
`predicted-movement-set.json`) before the run. This scores it.

MOVEMENT IS TESTED ON THE STORED [re, im] PAIRS, exactly. A tolerance would let a
row that moved in the twelfth digit read as unchanged, and the claim under test is
"this code path did not run differently" -- which is a claim about bits.

EVERY MOVER OUTSIDE THE PREDICTED SET IS PRINTED, with its design and engine. A
summary count would be the one shape in which a surprise disappears.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NEW = ROOT / "docs/status/data/2026-09-15-catalog-razor-nec5-bs2.jsonl"
BEFORE_REF = "b9bc3e2f0:scratch/catalog-razor-nec5-bs2/records.jsonl"
CONFIRM_REF = "d66c89967:scratch/catalog-razor-nec5-bs2/records-1532.jsonl"
GROUNDS = ("free", "somm")
ENGINES = ("razor", "nec5", "bs2")
JACKETED = ("dipoles.pota_invvee", "dipoles.invvee_catenary", "wire.efhw_sloper")


def load_text(text):
    out = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if "design" not in r:
            continue
        out[(r["design"], r["ground"], r["engine"])] = r
    return out


def load_git(ref):
    cp = subprocess.run(
        ["git", "show", ref], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return load_text(cp.stdout)


def main():
    new = load_text(NEW.read_text(encoding="utf-8"))
    old = load_git(BEFORE_REF)
    confirm = load_git(CONFIRM_REF)
    pred = json.loads((HERE / "predicted-movement-set.json").read_text())
    predicted = set(pred["union"])

    comparable = [k for k in new if k in old]
    moved, same = [], []
    for k in comparable:
        a, b = old[k], new[k]
        # A status change is movement too, and a pair where either side did not
        # solve has no z to compare -- so compare status first.
        if a["status"] != b["status"]:
            moved.append((k, "status", a["status"], b["status"]))
        elif a["status"] != "ok":
            same.append(k)
        elif a["z"] != b["z"]:
            moved.append((k, "z", a["z"], b["z"]))
        else:
            same.append(k)

    print(f"cells in the re-run      : {len(new)}")
    print(f"cells also at b9bc3e2f0  : {len(comparable)}")
    print(f"bit-identical            : {len(same)}")
    print(f"moved                    : {len(moved)}")
    print()

    inside = [m for m in moved if m[0][0] in predicted]
    outside = [m for m in moved if m[0][0] not in predicted]

    print(f"--- movers INSIDE the predicted set ({len(inside)}) ---")
    for (d, g, e), kind, a, b in sorted(inside):
        if kind == "status":
            print(f"  {d:34s} {g:5s} {e:6s} status {a} -> {b}")
        else:
            za, zb = complex(*a[0]), complex(*b[0])
            rel = abs(za - zb) / abs(za) if abs(za) else float("inf")
            print(
                f"  {d:34s} {g:5s} {e:6s} {100 * rel:8.4f}%  "
                f"{za.real:.4f}{za.imag:+.4f}j -> {zb.real:.4f}{zb.imag:+.4f}j"
            )
    print()
    print(f"--- movers OUTSIDE the predicted set ({len(outside)}) — FINDINGS ---")
    if not outside:
        print("  none")
    for (d, g, e), kind, a, b in sorted(outside):
        if kind == "status":
            print(f"  {d:34s} {g:5s} {e:6s} status {a} -> {b}")
        else:
            za, zb = complex(*a[0]), complex(*b[0])
            rel = abs(za - zb) / abs(za) if abs(za) else float("inf")
            print(
                f"  {d:34s} {g:5s} {e:6s} {100 * rel:8.4f}%  "
                f"{za.real:.4f}{za.imag:+.4f}j -> {zb.real:.4f}{zb.imag:+.4f}j"
            )
    print()

    # R2: the six jacketed NEC-5 rows equal CONFIRM-1532's values exactly.
    r2_rows = [(d, g, "nec5") for d in JACKETED for g in GROUNDS]
    r2_bad = [
        k
        for k in r2_rows
        if k in confirm and k in new and confirm[k]["z"] != new[k]["z"]
    ]
    r2_missing = [k for k in r2_rows if k not in confirm or k not in new]
    # R3: their bs2 and razor rows unchanged from b9bc3e2f0.
    r3_rows = [(d, g, e) for d in JACKETED for g in GROUNDS for e in ("razor", "bs2")]
    r3_bad = [
        k for k in r3_rows if k in old and k in new and old[k]["z"] != new[k]["z"]
    ]

    print("--- R1-R4 ---")
    print("| prediction | bar | measured | verdict |")
    print("|---|---|---|---|")
    r1 = not outside
    print(
        f"| **R1** | every cell outside the 7 predicted designs bit-identical | "
        f"{len(outside)} mover(s) outside the set | "
        f"{'**HIT**' if r1 else '**MISS**'} |"
    )
    r2 = None if r2_missing else not r2_bad
    print(
        f"| **R2** | the six jacketed NEC-5 rows equal CONFIRM-1532 exactly | "
        f"{'rows missing: ' + str(len(r2_missing)) if r2_missing else f'{len(r2_rows) - len(r2_bad)} of {len(r2_rows)} exact'} | "
        f"{'**UNSCORED**' if r2 is None else ('**HIT**' if r2 else '**MISS**')} |"
    )
    r3 = not r3_bad
    print(
        f"| **R3** | jacketed bs2 and razor rows unchanged from b9bc3e2f0 | "
        f"{len(r3_rows) - len(r3_bad)} of {len(r3_rows)} unchanged | "
        f"{'**HIT**' if r3 else '**MISS**'} |"
    )
    # R4 needs a populated comparison, or "nothing moved" would read as a pass
    # for the wrong reason -- a harness that silently re-ran the old code.
    r4 = None if not comparable else bool(inside)
    print(
        f"| **R4** | at least one predicted design actually moves | "
        f"{len(inside)} mover(s) inside the set, over {len(comparable)} comparable cells | "
        f"{'**UNSCORED**' if r4 is None else ('**HIT**' if r4 else '**MISS**')} |"
    )
    hits = sum(1 for v in (r1, r2, r3, r4) if v is True)
    print()
    print(f"Hit {hits} of 4.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
