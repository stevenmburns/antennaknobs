"""AK#896: the instrument's own caveat, measured.

The census runs momwire over the TRANSLATED corpus. That choice is worth a
number rather than an assertion, and it cuts both ways: translation wins decks
back from 4nec2's `SY` symbols, and loses a few to a defect in our own
translator. Both counts belong in the status page.

    python scratch/896-census/probe_translated_gain.py [N]

Pairs each translated deck with the raw file it came from, runs momwire over
both, and reports what changed. Sampled rather than exhaustive because the point
is the RATIO, and the full corpus is the census's own job.
"""

from __future__ import annotations

import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from momwire.portal import run_deck  # noqa: E402

HOME = Path.home() / "nec5-timing"
SEED = 896


def answered(body: str) -> tuple[bool, str]:
    try:
        out, err = run_deck(body)
    except Exception as e:  # noqa: BLE001 — a census survives any deck
        return False, f"raise:{type(e).__name__}"
    if "ANTENNA INPUT PARAMETERS" in out:
        return True, ""
    m = re.search(r"ERROR:?\s*(.{0,80})", out + "\n" + (err or ""))
    return False, re.sub(r"\d+", "N", m.group(1).strip())[:70] if m else "no-aip"


def main(argv=None) -> int:
    n = int(argv[0]) if argv else 150
    trans = {p.stem: p for p in (HOME / "nec5").rglob("*.nec") if p.is_file()}
    raws = {p.stem: p for p in (HOME / "raw").rglob("*") if p.is_file()}
    both = sorted(set(trans) & set(raws))
    random.Random(SEED).shuffle(both)
    sample = both[:n]
    print(f"translated {len(trans)}, raw {len(raws)}, joinable by stem {len(both)}")
    print(f"sampling {len(sample)} (seed {SEED})\n")

    tally = {"raw": Counter(), "translated": Counter()}
    why = {"raw": Counter(), "translated": Counter()}
    gained, lost = [], []
    t0 = time.perf_counter()
    for stem in sample:
        got = {}
        for tag, path in (("raw", raws[stem]), ("translated", trans[stem])):
            ok, reason = answered(path.read_text(encoding="latin-1", errors="replace"))
            tally[tag]["answered" if ok else "declined"] += 1
            if not ok:
                why[tag][reason] += 1
            got[tag] = ok
        if got["translated"] and not got["raw"]:
            gained.append(stem)
        if got["raw"] and not got["translated"]:
            lost.append(stem)

    for tag in ("raw", "translated"):
        a = tally[tag]["answered"]
        print(f"{tag:11s} answered {a}/{len(sample)} ({100 * a / len(sample):.0f} %)")
        for k, v in why[tag].most_common(5):
            print(f"              {v:4d}  {k}")
    print(f"\ngained by translation: {len(gained)}   lost: {len(lost)}")
    print("lost decks (our translator's defect, not momwire's limit):")
    for s in lost:
        print(f"   {s}")
    print(f"\n{time.perf_counter() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
