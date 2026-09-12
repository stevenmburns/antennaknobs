"""Per-deck card census for the large decks d8e2147 did not speed up (#1430-adjacent).

    python deck_features.py --src ~/nec5-timing/nec5 --out large-deck-features.csv

Joins the three pinned-4 speedup CSVs with a card census of each deck, for every
deck the x13 reference took at least `--min-wall` seconds on.

THE TREE MUST BE THE ONE THAT WAS TIMED. The pinned-4 reports ran over
`~/nec5-timing/nec5`, the translation as it stood before #1416 and #1430. Reading
features from a later tree would silently pair a deck's timing with a different
deck's cards — the same class of mistake as joining two engines on mismatched
rows.

Card census only: no printout is read, no engine is run, no binary is touched.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def load_speedups(d: Path) -> dict:
    """deck -> {pair: (wall_a, wall_b, speedup, status_a, status_b)}"""
    out: dict[str, dict] = {}
    for pair, name in (
        ("d8_vs_x13", "speedup-d8e2147-vs-x13-t4.csv"),
        ("d8_vs_63", "speedup-d8e2147-vs-63d0f93-t4.csv"),
        ("63_vs_x13", "speedup-63d0f93-vs-x13-t4.csv"),
    ):
        p = d / name
        if not p.is_file():
            continue
        with open(p, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                out.setdefault(r["deck"], {})[pair] = r
    return out


def census(text: str) -> dict:
    """What the deck asks for, from its cards."""
    c = Counter()
    segs = wires = 0
    fr_steps = 0
    rp_points = 0
    gn_types: list[str] = []
    ex_types: list[str] = []
    ld_types: list[str] = []
    nofile = False
    for line in text.splitlines():
        t = line.replace(",", " ").split()
        if not t:
            continue
        mn = t[0].upper()
        c[mn] += 1
        if mn in ("GW", "CW") and len(t) > 2:
            wires += 1
            try:
                segs += int(float(t[2]))
            except ValueError:
                pass
        elif mn == "FR" and len(t) > 2:
            try:
                fr_steps += max(int(float(t[2])), 1)
            except ValueError:
                fr_steps += 1
        elif mn == "RP" and len(t) > 3:
            try:
                rp_points += max(int(float(t[2])), 1) * max(int(float(t[3])), 1)
            except ValueError:
                pass
        elif mn == "GN":
            try:
                gn_types.append(str(int(float(t[1]))))
            except (ValueError, IndexError):
                gn_types.append("?")
            if "NOFILE" in line.upper():
                nofile = True
        elif mn == "EX" and len(t) > 1:
            try:
                ex_types.append(str(int(float(t[1]))))
            except ValueError:
                ex_types.append("?")
        elif mn == "LD" and len(t) > 1:
            try:
                ld_types.append(str(int(float(t[1]))))
            except ValueError:
                ld_types.append("?")
    ground = "none" if not gn_types else "/".join(sorted(set(gn_types)))
    return {
        "segments": segs,
        "wires": wires,
        "gn": ground,
        "gn_nofile": int(nofile),
        "fr_cards": c["FR"],
        "fr_steps": fr_steps or (1 if c["FR"] else 0),
        "rp_cards": c["RP"],
        "rp_points": rp_points,
        "ne_nh": c["NE"] + c["NH"],
        "ex_cards": c["EX"],
        "ex_types": "/".join(sorted(set(ex_types))) or "-",
        "ld_cards": c["LD"],
        "ld_types": "/".join(sorted(set(ld_types))) or "-",
        "nt_cards": c["NT"],
        "tl_cards": c["TL"],
        "gm_cards": c["GM"],
        "gx_gr_cards": c["GX"] + c["GR"],
    }


def main(argv=None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(Path.home() / "nec5-timing" / "nec5"))
    ap.add_argument("--csvdir", default=str(here))
    ap.add_argument("--out", default=str(here / "large-deck-features.csv"))
    ap.add_argument("--min-wall", type=float, default=2.0)
    a = ap.parse_args(argv)

    src = Path(a.src).expanduser()
    sp = load_speedups(Path(a.csvdir).expanduser())
    rows = []
    for deck, pairs in sp.items():
        base = pairs.get("d8_vs_x13")
        if not base or base["comparable"] != "1":
            continue
        try:
            wall_x13 = float(base["wall_a"])
        except (TypeError, ValueError):
            continue
        if wall_x13 < a.min_wall:
            continue
        p = src / deck
        if not p.is_file():
            continue
        f = census(p.read_text(encoding="latin-1", errors="replace"))
        f["deck"] = deck
        f["wall_x13"] = round(wall_x13, 3)
        f["wall_d8"] = round(float(base["wall_b"]), 3)
        f["sp_d8_vs_x13"] = round(float(base["speedup"]), 4)
        for key, col in (("d8_vs_63", "sp_d8_vs_63"), ("63_vs_x13", "sp_63_vs_x13")):
            r = pairs.get(key)
            f[col] = round(float(r["speedup"]), 4) if r and r.get("speedup") else ""
        f["wall_63"] = (
            round(float(pairs["d8_vs_63"]["wall_a"]), 3)
            if pairs.get("d8_vs_63")
            else ""
        )
        rows.append(f)

    rows.sort(key=lambda r: r["sp_d8_vs_x13"])
    cols = [
        "deck",
        "wall_x13",
        "wall_63",
        "wall_d8",
        "sp_d8_vs_x13",
        "sp_63_vs_x13",
        "sp_d8_vs_63",
        "segments",
        "wires",
        "gn",
        "gn_nofile",
        "fr_cards",
        "fr_steps",
        "rp_cards",
        "rp_points",
        "ne_nh",
        "ex_cards",
        "ex_types",
        "ld_cards",
        "ld_types",
        "nt_cards",
        "tl_cards",
        "gm_cards",
        "gx_gr_cards",
    ]
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} decks with wall_x13 >= {a.min_wall:g} s -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
