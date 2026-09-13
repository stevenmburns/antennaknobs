"""Average a build's two pinned-4 passes into one report, per deck.

    python merge_passes.py <pass A> <pass B> <out.jsonl>

The map is built from the MEAN of each build's two passes rather than from one
of them, so all four passes carry into the answer and neither round decides it
alone. With the two x13 passes 0.09 % apart the choice barely matters, which is
itself the finding -- but the rule should not depend on that being true.

A deck is carried only when both passes agree on its status; a deck that
disagrees is written with the FIRST pass's row and flagged, because a status that
moved between two identical runs is a fact about the deck and must not be
averaged away.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(p):
    meta, rows = None, {}
    for line in Path(p).open(encoding="utf-8"):
        r = json.loads(line)
        if "_meta" in r:
            meta = r
        elif r.get("file"):
            rows[r["file"]] = r
    return meta, rows


def main(argv):
    a, b, out = argv[:3]
    meta, ra = load(a)
    _, rb = load(b)
    flapped = []
    with Path(out).open("w", encoding="utf-8") as fh:
        m = dict(meta)
        m["_meta"] = {**m["_meta"], "merged_from": [str(a), str(b)]}
        fh.write(json.dumps(m) + "\n")
        for f in sorted(ra):
            x, y = ra[f], rb.get(f)
            row = dict(x)
            if y is not None and x["status"] == y["status"]:
                wa, wb = x.get("wall_s"), y.get("wall_s")
                if wa is not None and wb is not None:
                    row["wall_s"] = (wa + wb) / 2.0
            elif y is not None:
                flapped.append((f, x["status"], y["status"]))
            fh.write(json.dumps(row) + "\n")
    print(
        f"{out}: {len(ra)} decks; status differed between the two passes on {len(flapped)}"
    )
    for f, s1, s2 in flapped[:10]:
        print(f"   {f}: {s1} / {s2}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
