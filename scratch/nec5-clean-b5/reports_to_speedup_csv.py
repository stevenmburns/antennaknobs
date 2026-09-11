"""Join two `nec5_corpus.py check` reports into the CSV the a43 runtime-vs-
speedup plot reads, so the clean-room build gets the same figure as the a43
beta did (scratch/nec5-beta-a43/plot_runtime_vs_speedup.py).

    python reports_to_speedup_csv.py check-base.jsonl check-new.jsonl nec5/ out.csv

Columns: deck, segments, stock_wall_s, a43_wall_s, speedup, set — "stock" is
the shipped -O2 build and "a43" the clean-room build, kept under the plot
script's column names so that script runs unchanged. Segments are summed
from the translated deck's GW cards. Only decks with a wall time in BOTH
reports and status ok/error/crash (not timeout, whose wall is the cap) are
written; the rest are counted on stderr.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def _rows(path):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "_meta" in row:
            continue
        out[row["file"]] = row
    return out


def _segments(deck: Path) -> int:
    n = 0
    for line in deck.read_text(encoding="ascii", errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].upper() == "GW":
            try:
                n += int(float(parts[2]))
            except ValueError:
                pass
    return n


def main(argv=None):
    base, new, src, out = (argv or sys.argv[1:])[:4]
    a, b = _rows(base), _rows(new)
    src = Path(src)
    skipped = {"missing": 0, "timeout": 0, "no_wall": 0}
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["deck", "segments", "stock_wall_s", "a43_wall_s", "speedup", "set"])
        for deck, ra in sorted(a.items()):
            rb = b.get(deck)
            if rb is None:
                skipped["missing"] += 1
                continue
            if "timeout" in (ra["status"], rb["status"]):
                skipped["timeout"] += 1
                continue
            sa, sb = ra.get("wall_s"), rb.get("wall_s")
            if not sa or not sb or sa <= 0 or sb <= 0:
                skipped["no_wall"] += 1
                continue
            w.writerow(
                [
                    deck,
                    _segments(src / deck),
                    f"{sa:.6f}",
                    f"{sb:.6f}",
                    f"{sa / sb:.6f}",
                    "corpus",
                ]
            )
            n += 1
    print(f"wrote {n} rows to {out}; skipped {skipped}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
