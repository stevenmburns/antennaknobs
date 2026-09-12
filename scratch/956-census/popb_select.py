"""Population B: the corpus decks with a Sommerfeld ground and a BURIED wire.

    python scratch/956-census/popb_select.py --src ~/nec5-timing/nec5-1430 \
        --out scratch/956-census/popb-members.json

TWO THINGS HERE ARE NOT WHAT THE BRIEF SAID, and both are measurements.

**`GN 2` does not appear in the translated corpus at all.** It is the NEC-2
spelling: 1,058 RAW decks carry it, and `translate` rewrites it, because in
NEC-5 `GN 0` and `GN 2` are the same Sommerfeld ground (the corpus tool's own
header says so, and it notes the rewrite per deck). The translated tree's GN
types are 0 (1,176 decks), -1 (701), 1 (205) and 3 (42) -- no 2. So the filter
is `GN 0` or `GN 2`, and on this tree that means GN 0. Filtering on `GN 2`
literally returns ZERO decks, which is the shape of an empty result that looks
like a finding.

**The geometry is read from the RAW deck, not the translated one.** The importer
is a NEC-2 reader and the translated tree is NEC-5 dialect: it declines 1,175 of
the 1,176 Sommerfeld decks on the `EX` edge-source form alone. The antenna is the
same antenna either way -- `translate` remeshes and rewrites cards, it does not
move wires -- so classification reads the author's deck through the importer and
carries the raw -> translated mapping from the translate report, which is also
what lets a row name both files.

**The geometry must come from a PARSER, not from the GW columns.** 384 of these
decks carry a transform card (GS/GM/GX/GR), and `GS 0 0 .3048` -- feet to metres
-- is common in the 4nec2 collections. A first cut of this script read the GW
columns directly and mis-indexed them, reading y as z: it classified
`4nec2-models/HFbeams/2lyagi20.nec` (a 20 m Yagi at z = 70 ft) as WHOLLY BURIED
at "zmin -8.67", which was its y offset. So geometry is read through
`antennaknobs.nec_import.parse_nec`, whose `NecWire` is documented as "one
straight wire AFTER all geometry transforms" and which the #1299 corpus tests
exercise over this same tree.

CLASSES, on the parsed wires (z == 0 exactly is the plane):

    crossing       an endpoint at z == 0 with conductor both above and below
    contact+split  an endpoint at z == 0, conductor above, buried wire elsewhere
    split          conductor above and below, nothing at z == 0
    wholly buried  no conductor above z == 0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from antennaknobs.nec_import import parse_nec  # noqa: E402

SOMMERFELD_GN = {0, 2}


def gn_types(text: str) -> set[int]:
    out = set()
    for line in text.splitlines():
        if line.upper().startswith("GN"):
            tk = re.split(r"[\s,]+", line.strip())
            if len(tk) > 1:
                try:
                    out.add(int(float(tk[1])))
                except ValueError:
                    pass
    return out


def classify(wires) -> tuple[str, float, float, int]:
    zs = [p[2] for w in wires for p in (w.p1, w.p2)]
    zmin, zmax = min(zs), max(zs)
    up, dn, at0 = set(), set(), set()
    for w in wires:
        for a, b in ((w.p1, w.p2), (w.p2, w.p1)):
            if a[2] == 0.0:
                k = (round(a[0], 9), round(a[1], 9))
                at0.add(k)
                if b[2] > 0:
                    up.add(k)
                elif b[2] < 0:
                    dn.add(k)
    if up & dn:
        return "crossing", zmin, zmax, len(up & dn)
    if at0 and zmax > 0:
        return "contact+split", zmin, zmax, len(at0)
    if zmax > 0:
        return "split", zmin, zmax, 0
    return "wholly-buried", zmin, zmax, 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--src",
        required=True,
        help="the TRANSLATED tree (for the mapping and the report)",
    )
    ap.add_argument(
        "--raw", required=True, help="the raw tree the corpus was fetched into"
    )
    ap.add_argument(
        "--out", default=str(Path(__file__).resolve().parent / "popb-members.json")
    )
    a = ap.parse_args(argv)
    src = Path(a.src).expanduser()
    raw_root = Path(a.raw).expanduser()

    # translated path -> the raw source it came from
    origin = {}
    for line in (src / "translate-report.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        if "_meta" in rec:
            continue
        for w in rec.get("written") or []:
            origin[w] = rec["file"]

    rows, unreadable, seen = [], [], 0
    for p in sorted(src.rglob("*.nec")):
        seen += 1
        rel = str(p.relative_to(src))
        text = p.read_text(encoding="latin-1", errors="replace")
        if not (gn_types(text) & SOMMERFELD_GN):
            continue
        raw_rel = origin.get(rel)
        raw_path = (raw_root / raw_rel) if raw_rel else None
        if raw_path is None or not raw_path.is_file():
            unreadable.append(
                {"file": rel, "error": "no raw source recorded in the translate report"}
            )
            continue
        try:
            deck = parse_nec(
                raw_path.read_text(encoding="latin-1", errors="replace"),
                name=raw_path.name,
                network=True,
            )
        except Exception as e:  # noqa: BLE001 -- a deck the importer declines is reported, never silently dropped
            unreadable.append(
                {"file": rel, "raw": raw_rel, "error": f"{type(e).__name__}: {e}"[:160]}
            )
            continue
        wires = list(deck.wires)
        if not wires:
            unreadable.append(
                {"file": rel, "raw": raw_rel, "error": "parsed to zero wires"}
            )
            continue
        kind, zmin, zmax, nodes = classify(wires)
        if zmin >= 0.0:
            continue
        rows.append(
            {
                "file": rel,
                "raw": raw_rel,
                "class": kind,
                "zmin": zmin,
                "zmax": zmax,
                "nodes": nodes,
                "wires": len(wires),
                "segs": sum(int(w.n_seg) for w in wires),
                "gn": sorted(gn_types(text)),
            }
        )

    from collections import Counter

    print(f"decks scanned: {seen}")
    print(f"Sommerfeld ground + a wire below z = 0: {len(rows)}")
    for k, n in sorted(Counter(r["class"] for r in rows).items()):
        print(f"   {k:14s} {n}")
    print(
        f"decks the importer could not read (reported, not dropped): {len(unreadable)}"
    )
    for u in unreadable[:8]:
        print(f"   {u['file']}: {u['error']}")
    Path(a.out).write_text(
        json.dumps({"members": rows, "unreadable": unreadable}, indent=1)
    )
    print(f"\n-> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
