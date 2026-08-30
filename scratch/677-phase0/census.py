"""#677 phase 0: exhaustive census of module-level mutable state.

Runs the failing prefix (0015, 0009, 0001, 0117) in one process and, after
each deck, snapshots EVERY module-level dict/list/set and every functools
lru_cache across all loaded momwire modules. Reports what grew per deck —
i.e., every channel process history can flow through, known or not.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2] / "momwire"
DECKS = REPO / "tests" / "fixtures" / "eznec" / "decks"
PREFIX = [
    "0015_vertical-over-real-ground.nec",
    "0009_4-square-array-w-feed-system.nec",
    "0001_4-square-array-w-feed-system.nec",
    "0117_40-meter-four-square-array.nec",
]
OUT = Path(__file__).resolve().parent


def snapshot():
    state = {}
    for mod_name, mod in list(sys.modules.items()):
        if not mod_name.startswith("momwire") or mod is None:
            continue
        for attr, val in list(vars(mod).items()):
            tag = f"{mod_name}.{attr}"
            if isinstance(val, (dict, list, set)):
                state[tag] = len(val)
            elif hasattr(val, "cache_info"):  # functools lru/cache wrapper
                ci = val.cache_info()
                state[f"{tag}[lru]"] = ci.currsize
    return state


def main():
    from momwire.eznec._shell import main as shell_main

    prev = snapshot()
    for name in PREFIX:
        out = OUT / f"census-{name[:4]}.out"
        code = shell_main([str(DECKS / name), str(out)])
        cur = snapshot()
        grew = {
            k: (prev.get(k, "absent"), v) for k, v in cur.items() if v != prev.get(k)
        }
        print(f"\n[{name[:4]}] exit={code} — state that changed:")
        for k, (old, new) in sorted(grew.items()):
            print(f"  {k}: {old} -> {new}")
        prev = cur


if __name__ == "__main__":
    main()
