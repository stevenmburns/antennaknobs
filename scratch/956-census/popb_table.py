"""Population B's table: the corpus's buried decks, and what stops each one.

    python scratch/956-census/popb_table.py --out scratch/956-census/popb-rows.csv

Reads the four reports the census wrote (NEC-5 x13, and momwire at the three
commits) over the two deck trees -- as published, and with the two TRANSLATE-side
blockers lifted (`GN 0` -> `GN 2`, `GE -1` -> `GE 1`) -- and prints one row per
deck with the refusal sentence that ends it.

Every momwire cell in this population is a refusal, so the interesting column is
WHY, and the sentences are quoted rather than summarised: each names a different
declared scope limit, and a reader has to be able to tell "not served" from
"broken".
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

H = Path.home() / "nec5-timing"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "nec5_corpus"))

from nec5_corpus import _first_z  # noqa: E402


def load(p: Path) -> dict:
    rows = {}
    if not p.is_file():
        return rows
    for line in p.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("file"):
            rows[r["file"]] = r
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out", default=str(Path(__file__).resolve().parent / "popb-rows.csv")
    )
    a = ap.parse_args(argv)

    members = json.loads(
        (Path(__file__).resolve().parent / "popb-members.json").read_text()
    )["members"]
    published_nec5 = load(H / "check-1430-nec5.jsonl")
    published_mw = load(
        ROOT / "docs/status/data/2026-09-11-corpus-census-momwire.jsonl"
    )
    lifted_nec5 = load(H / "popb-somm-nec5.jsonl")
    lifted = {
        t: load(H / f"popb-somm-momwire-{t}.jsonl") for t in ("pointer", "mid", "main")
    }

    def zof(rec):
        z = _first_z(rec or {})
        return complex(z) if z is not None else None

    rows = []
    for m in members:
        f = m["file"]
        row = {
            "file": f,
            "class": m["class"],
            "zmin_m": f"{m['zmin']:.4f}",
            "zmax_m": f"{m['zmax']:.3f}",
            "wires": m["wires"],
            "segs": m["segs"],
            "gn_translated": ",".join(str(g) for g in m["gn"]),
        }
        z5 = zof(published_nec5.get(f))
        row["R_nec5_published"] = f"{z5.real:.4f}" if z5 else ""
        row["X_nec5_published"] = f"{z5.imag:.4f}" if z5 else ""
        row["momwire_published_status"] = (published_mw.get(f) or {}).get(
            "status", "absent"
        )
        row["momwire_published_refusal"] = (
            (published_mw.get(f) or {}).get("error") or ""
        )[:220]
        z5l = zof(lifted_nec5.get(f))
        row["R_nec5_lifted"] = f"{z5l.real:.4f}" if z5l else ""
        row["X_nec5_lifted"] = f"{z5l.imag:.4f}" if z5l else ""
        for t in ("pointer", "mid", "main"):
            rec = lifted[t].get(f) or {}
            z = zof(rec)
            row[f"R_{t}_lifted"] = f"{z.real:.4f}" if z else ""
            row[f"X_{t}_lifted"] = f"{z.imag:.4f}" if z else ""
            row[f"{t}_lifted_status"] = rec.get("status", "absent")
        row["lifted_refusal"] = ((lifted["main"].get(f) or {}).get("error") or "")[:260]
        rows.append(row)

    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(
        f"{'deck':46s} {'class':14s} {'NEC-5 Z (lifted)':>26s}  momwire, all three commits"
    )
    print("-" * 128)
    for r in rows:
        z = (
            f"{r['R_nec5_lifted']} + {r['X_nec5_lifted']}j"
            if r["R_nec5_lifted"]
            else "—"
        )
        same = len({r[f"{t}_lifted_status"] for t in ("pointer", "mid", "main")}) == 1
        st = r["pointer_lifted_status"] if same else "DIFFER"
        print(f"{r['file'][-46:]:46s} {r['class']:14s} {z:>26s}  {st}")
        if r["lifted_refusal"]:
            print(f"{'':62s}  {r['lifted_refusal'][:120]}")
    print(f"\nwrote {len(rows)} rows -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
