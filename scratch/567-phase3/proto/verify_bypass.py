"""#567 phase 3 pre-work: independently verify the one-member-junction
bypass of _REFUSE_CONTACT_WITH_BURIED found by the 2026-08-28 code map.

Claim: on a contact+buried deck, declaring junctions=[[(0, "end")]] (a
one-member group at the contact end, legal per momwire#172) lands the
contact end in crossing_ends, escapes the contact+buried refusal, fails
_crossing_junctions' two-media test, and routes to the OLD field-form
transmitted-grid cross block — the exact configuration the refusal
exists to prevent, served silently.

Run: .venv/bin/python scratch/567-phase3/proto/verify_bypass.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver
from test_buried_serve_553 import contact_deck


def main():
    build = contact_deck()

    # Control: the canonical deck refuses at construction/label time.
    s0 = BSplineSolver(**build)
    try:
        s0._wire_media()
        print("CONTROL: no refusal (UNEXPECTED)")
    except ValueError as e:
        print(f"CONTROL refused as designed: {str(e)[:110]}...")

    # The bypass: one-member junction at the contact end (wire 0's zmin end).
    import numpy as np

    for i, w in enumerate(build["wires"]):
        arr = np.asarray(w, dtype=float)
        print(f"  wire {i}: z {arr[:, 2].min():+.3f}..{arr[:, 2].max():+.3f}")

    for end in ("start", "end"):
        b = dict(build)
        b["junctions"] = [[(0, end)]]
        s = BSplineSolver(**b)
        try:
            media = s._wire_media()
        except ValueError as e:
            print(f"junctions=[[(0,'{end}')]]: refused ({str(e)[:60]}...)")
            continue
        print(
            f"junctions=[[(0,'{end}')]]: media={media} "
            f"crossing_ends={s._grounded_junction_ends()} "
            f"crossing_junctions={s._crossing_junctions()}"
        )


if __name__ == "__main__":
    main()
