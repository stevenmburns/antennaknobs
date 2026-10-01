"""The M0AGP reproduction tables (README.md) from reproduce.py's JSON."""

import json
import sys

from reproduce import MODES, TABLE

for path in sys.argv[1:]:
    d = json.load(open(path))
    print(
        f"\n{d['engine']} at {d['freq_mhz']} MHz, vertical resonant at {d['vertical_ft']:.2f} ft\n"
    )
    print(
        "| vertical section (ft) | top wire (ft) | M0AGP | " + " | ".join(MODES) + " |"
    )
    print("|---|---|---|" + "---|" * len(MODES))
    for r in d["rows"]:
        print(
            f"| {r['vert_ft']} | {r['horiz_ft']:.2f} | {TABLE[r['vert_ft']]:+.2f} | "
            + " | ".join(f"{r['rel'][m]:+.2f}" for m in MODES)
            + " |"
        )
    worst = {
        m: max(abs(r["rel"][m] - TABLE[r["vert_ft"]]) for r in d["rows"]) for m in MODES
    }
    print("\nworst |miss| (dB): " + ", ".join(f"{m} {v:.2f}" for m, v in worst.items()))
