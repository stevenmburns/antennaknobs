"""AK#1469 amendment 1 (AK#1483) gates G2' and G8, from the PyNEC captures.

    python partB_gates_ld.py <before pynec.jsonl> <after pynec.jsonl> <native pynec.jsonl> <catalog dir>

G2': PyNEC Z changes only on the catalog-nec5 decks carrying a discrete LD.
G8: on those decks, the imported deck's PyNEC Z after the fix is closer to the
catalog design's own PyNEC Z (`partB_native_pynec.py`) than before it, on at
least 80 % of the decks that solve on both runs. The registration set the 4
short_dipole_loaded decks apart, so they are reported alone.
"""

import json
import os
import re
import sys

TOL = 1e-9


def _load(path, key):
    with open(path, encoding="utf-8") as fh:
        return {key(r): r for r in map(json.loads, fh)}


def _z(row):
    return complex(*row["z"][0])


def main(argv):
    before_path, after_path, native_path, catalog = argv
    before = _load(before_path, lambda r: (r["set"], r["deck"]))
    after = _load(after_path, lambda r: (r["set"], r["deck"]))
    native = _load(native_path, lambda r: r["deck"])
    ld_decks = set()
    for n in os.listdir(catalog):
        with open(os.path.join(catalog, n), encoding="utf-8", errors="replace") as fh:
            if n.endswith(".nec") and re.search(r"^LD [0146] ", fh.read(), re.M):
                ld_decks.add(n)

    moved, status = [], []
    for key in sorted(before):
        b, a = before[key], after.get(key)
        if a is None or b["status"] != a["status"]:
            status.append((key, b["status"], a and a["status"]))
            continue
        if b["status"] != "ok":
            continue
        rel = max(
            abs(complex(*zb) - complex(*za)) / max(abs(complex(*zb)), 1e-12)
            for zb, za in zip(b["z"], a["z"], strict=False)
        )
        if len(b["z"]) != len(a["z"]) or rel > TOL:
            moved.append((key[1], rel))
    outside = [m for m in moved if m[0] not in ld_decks]
    print(
        f"G2': {len(moved)} decks moved beyond {TOL:g}; {len(outside)} outside the {len(ld_decks)} LD decks; status changes {len(status)}"
    )
    for m in outside + status:
        print("   ", m)

    closer = total = 0
    print("G8 (|Z - native| / |native|, before -> after):")
    for name in sorted(ld_decks):
        nat, b, a = (
            native.get(name),
            before.get(("catalog-nec5", name)),
            after.get(("catalog-nec5", name)),
        )
        if (
            not (nat and b and a)
            or "ok" not in (nat["status"],)
            or b["status"] != "ok"
            or a["status"] != "ok"
        ):
            print(
                f"    {name}: not comparable ({nat and nat['status']}, {b and b['status']}, {a and a['status']})"
            )
            continue
        zn = _z(nat)
        db, da = abs(_z(b) - zn) / abs(zn), abs(_z(a) - zn) / abs(zn)
        alone = name.startswith("dipoles.short_dipole_loaded.")
        mark = "alone" if alone else ("closer" if da < db else "MISS")
        print(
            f"    {name}: {db:.4g} -> {da:.4g}  {mark}   native {zn:.4g}  after {_z(a):.4g}"
        )
        if not alone:
            total += 1
            closer += da < db
    if total:
        print(
            f"G8: closer on {closer}/{total} = {100 * closer / total:.0f} % (bar 80 %)"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
