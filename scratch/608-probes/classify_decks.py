"""momwire#608 — classify every one-segment polyline in the five decks.

The decisive question for the fix's shape: does the corpus contain case (c),
a one-segment wire junctioned at NEITHER end? Such a wire carries no basis
at all under razor, so it is inert geometry — silently zero current. If no
deck has one, the narrowed guard can keep refusing (c) and still serve all
five.

Classification is done on the mesh razor itself would be handed, via
`_serve.build_mesh` with `solver_class=RazorSolver`, and on `_find_junctions`
— razor's own grouping, not the deck's node structure (they disagree by
design: `razor._find_junctions` uses a 1e-9 first-match, the deck front end a
1e-6 grid).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[2] / "momwire" / "tests")
)

from momwire.deck._nec5 import parse_nec5  # noqa: E402
from momwire.eznec import _serve  # noqa: E402
from momwire.razor import RazorSolver  # noqa: E402
from test_eznec_printout import MANIFEST, deck_text  # noqa: E402

CAPTURE_IDS = tuple(entry["id"] for entry in MANIFEST["captures"])
FIVE = ("0011", "0029", "0030", "0034", "0035")


def classify(cid):
    deck = parse_nec5(deck_text(cid))
    structure = _serve.structure_of(deck)
    mesh = _serve.build_mesh(deck, structure, solver_class=RazorSolver)

    # Razor's OWN junction grouping, over the same polylines. Build a bare
    # instance far enough to call `_find_junctions` without tripping the guard:
    # the method only reads `wires_polylines`.
    probe = RazorSolver.__new__(RazorSolver)
    probe.wires_polylines = [p.points for p in mesh.pieces]
    ground = _serve._ground_kwargs(deck, _serve._medium(deck.ground, 1.0))
    probe.ground_z = ground.get("ground_z")
    probe._declared_junctions = None
    groups = probe._find_junctions()
    joined = {end for g in groups for end in g["ends"]}

    rows = []
    for i, piece in enumerate(mesh.pieces):
        if piece.n_elements != 1:
            continue
        ends = sum(((i, k) in joined) for k in ("start", "end"))
        rows.append((i, piece.tag, {2: "a", 1: "b", 0: "c"}[ends]))
    return len(mesh.pieces), rows


def main():
    print(
        f"{'deck':<8s} {'pieces':>7s} {'1-seg':>6s}   (a) both   (b) one   (c) NEITHER"
    )
    total = {"a": 0, "b": 0, "c": 0}
    for cid in CAPTURE_IDS:
        n_pieces, rows = classify(cid)
        if not rows:
            continue
        counts = {k: sum(r[2] == k for r in rows) for k in "abc"}
        for k in "abc":
            total[k] += counts[k]
        flag = "  <-- CASE (c) PRESENT" if counts["c"] else ""
        star = "*" if cid in FIVE else " "
        print(
            f"{cid}{star:<3s} {n_pieces:>7d} {len(rows):>6d}   "
            f"{counts['a']:>8d}  {counts['b']:>8d}  {counts['c']:>10d}{flag}"
        )
    print(f"\ntotal one-segment polylines across the corpus: {sum(total.values())}")
    print(f"  (a) junctioned at both ends : {total['a']}")
    print(f"  (b) junctioned at one end   : {total['b']}")
    print(f"  (c) junctioned at neither   : {total['c']}")


if __name__ == "__main__":
    main()
