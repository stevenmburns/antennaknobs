"""G3 and G6 for AK#1469 slice 1: before/after impedance on the catalog-nec5 decks.

    python compare_z.py baseline-f77b4fd.json after-d6ed501.json [bound]

G6 compares momwire Z on every deck that served on BOTH runs, port by port,
against the registered relative bound (default 1e-3), and lists status changes
separately. G3 prints AC6LA's NEC-5 Z and GW/EX cards from each run.
"""

import json
import sys


def _cards(deck):
    return [ln for ln in deck.splitlines() if ln.startswith(("GW", "EX"))]


def main(argv):
    before = json.load(open(argv[0], encoding="utf-8"))
    after = json.load(open(argv[1], encoding="utf-8"))
    bound = float(argv[2]) if len(argv) > 2 else 1e-3
    b, a = before["momwire"], after["momwire"]

    changed = sorted(
        (name, b[name]["status"], a[name]["status"])
        for name in sorted(set(b) & set(a))
        if b[name]["status"] != a[name]["status"]
    )
    rows = []
    for name in sorted(set(b) & set(a)):
        if b[name]["status"] != "ok" or a[name]["status"] != "ok":
            continue
        zb = [complex(*z) for z in b[name]["z"]]
        za = [complex(*z) for z in a[name]["z"]]
        if len(zb) != len(za):
            changed.append((name, f"{len(zb)} ports", f"{len(za)} ports"))
            continue
        rel = max(abs(x - y) / abs(x) for x, y in zip(zb, za, strict=True))
        rows.append((rel, name, zb[0], za[0]))
    rows.sort(reverse=True)
    over = [r for r in rows if r[0] > bound]
    identical = sum(r[0] == 0.0 for r in rows)
    print(f"G6: {len(rows)} decks served on both runs; bound {bound:g}")
    print(f"    {identical} identical, {len(over)} above the bound")
    for rel, name, zb, za in rows[:12]:
        flag = "OVER" if rel > bound else "    "
        print(f"  {flag} {rel:.3e}  {name}  {zb:.4f} -> {za:.4f}")
    print(f"status changes: {len(changed)}")
    for name, sb, sa in changed:
        detail = a[name].get("msg", "")[:120] if name in a else ""
        print(f"  {name}: {sb} -> {sa} {detail}")

    nb, na = before.get("nec5_ac6la"), after.get("nec5_ac6la")
    if nb and na:
        print("G3 NEC-5 on AC6LA's deck:")
        print(f"  before {nb['z']}  after {na['z']}")
        print("  before cards:", *_cards(nb["deck"]), sep="\n    ")
        print("  after cards:", *_cards(na["deck"]), sep="\n    ")


if __name__ == "__main__":
    main(sys.argv[1:])
