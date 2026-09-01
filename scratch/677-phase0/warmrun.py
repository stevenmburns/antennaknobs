"""#677 phase 0: map cross-deck module-cache traffic on the failing prefix.

Runs forward[0..3] of the residency order (0015, 0009, 0001, 0117) through
one resident process, spying on every module-level cache momwire owns.
Reports, for 0117: which cache entries it CONSUMED that an earlier deck
created — the candidate leak channels — and whether its warm printout
matches a cold (fresh-process) printout on this machine.
"""

import itertools
import subprocess
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


class SpyDict(dict):
    """Dict that logs which keys .get() finds, tagged by the current deck."""

    def __init__(self, name, log, *a):
        super().__init__(*a)
        self._name = name
        self._log = log
        self.creator = {}  # key -> deck that inserted it
        self.current_deck = "?"

    def get(self, key, default=None):
        hit = super().get(key, default)
        if hit is not None and not isinstance(hit, type(default)):
            self._log.append(
                (self._name, self.current_deck, self.creator.get(key, "?"), key)
            )
        return hit

    def __setitem__(self, key, value):
        if key not in self:
            self.creator[key] = self.current_deck
        super().__setitem__(key, value)


def main():
    import momwire._sommerfeld as somm
    import momwire.array_block as ab
    import momwire.bspline as bs
    from momwire.eznec._shell import main as shell_main

    log = []
    spies = []
    for mod, attr in [
        (somm, "_GRID_CACHE"),
        (somm, "_NORM_CACHE"),
        (ab, "_ARRAY_OP_CACHE"),
        (ab, "_SELF_BLOCK_CACHE"),
        (bs, "_GEOMETRY_CACHE"),
        (bs, "_BASIS_POLY_CACHE"),
    ]:
        spy = SpyDict(f"{mod.__name__}.{attr}", log, getattr(mod, attr))
        setattr(mod, attr, spy)
        spies.append(spy)

    for name in PREFIX:
        for spy in spies:
            spy.current_deck = name[:4]
        deck = DECKS / name
        out = OUT / f"warm-{name[:4]}.out"
        code = shell_main([str(deck), str(out)])
        sizes = {s._name.split(".")[-1]: len(s) for s in spies}
        print(f"[warm] {name[:4]} exit={code} cache sizes={sizes}")

    print("\n== cross-deck GETs during 0117 (cache, consumer, creator) ==")
    cross = [
        (n, c, cr) for n, c, cr, _k in log if c == "0117" and cr not in ("0117", "?")
    ]
    for n, c, cr in cross:
        print(f"  {n}: {c} consumed entry created by {cr}")
    if not cross:
        print("  (none — 0117 touched no entry created by an earlier deck)")

    # Cold oracle: fresh process, same deck.
    cold_out = OUT / "cold-0117.out"
    deck = DECKS / PREFIX[-1]
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from momwire.eznec._shell import main; sys.exit(main(sys.argv[1:]))",
            str(deck),
            str(cold_out),
        ],
        check=False,
    )
    warm = (OUT / "warm-0117.out").read_text(errors="replace")
    cold = cold_out.read_text(errors="replace")
    strip = lambda t: [  # noqa: E731 — kept: the probe reads as the algebra it is checking
        l for l in t.split("\n") if "FILL=" not in l and not l.startswith(" RUN TIME =")
    ]
    # zip_longest, not zip: this is a DIFF, so a line present in one run and
    # absent from the other is exactly the finding. Plain zip truncates to the
    # shorter side and would report "0 differing lines" over a tail it never
    # looked at — a false negative in the tool you are using to find
    # differences. strict=True is no better here: it raises instead of
    # reporting, destroying the diff. The None shows up as the difference.
    diff = [
        (i, a, b)
        for i, (a, b) in enumerate(itertools.zip_longest(strip(warm), strip(cold)))
        if a != b
    ]
    print(f"\n== warm-vs-cold 0117 on this machine: {len(diff)} differing lines ==")
    for i, a, b in diff[:10]:
        print(f"  line {i}:\n    warm: {a}\n    cold: {b}")


if __name__ == "__main__":
    main()
