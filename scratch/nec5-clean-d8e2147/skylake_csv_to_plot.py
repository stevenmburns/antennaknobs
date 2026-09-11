"""Skylake's pinned-4 speedup CSV (deck, status_a, status_b, wall_a, wall_b,
speedup, comparable) -> the a43 plot script's columns (deck, segments,
stock_wall_s, a43_wall_s, speedup, set). Segments counted from the deck files
under the corpus root, the way reports_to_speedup_csv.py does."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nec5-clean-b5"))
from reports_to_speedup_csv import _segments  # noqa: E402


def main(argv):
    src, root, out = argv[:3]
    n_ok = n_skip = 0
    with open(src, newline="") as fh, open(out, "w", newline="") as oh:
        w = csv.writer(oh)
        w.writerow(["deck", "segments", "stock_wall_s", "a43_wall_s", "speedup", "set"])
        for r in csv.DictReader(fh):
            if r["comparable"] != "1":
                n_skip += 1
                continue
            p = Path(root) / r["deck"]
            seg = _segments(p) if p.exists() else 0
            w.writerow(
                [r["deck"], seg, r["wall_a"], r["wall_b"], r["speedup"], "corpus"]
            )
            n_ok += 1
    print(f"{out}: {n_ok} comparable rows written, {n_skip} not comparable")


if __name__ == "__main__":
    main(sys.argv[1:])
