"""A-2 session 7, probe 35 — P3: the contact anchors under the crossing
machinery's spellings.

The two momwire#567 anchor decks (10 m contact monopole over one / four
DETACHED radials 15 cm down): engine prints 92.130-70.141j (lone) and
90.051-70.731j (fan), pre-adjudication misses 12.91 / 17.16 ohm.

First run's finding (2026-08-27, this file's v1): the COMPLETE contact
spelling (cross M + contact-end BT column on designed kernels) WRECKS the
lone anchor - 58.5178-15.2504j, miss 64.36 ohm - which is probe28's mono
lesson holding in the cross block too: the shipped contact serve's
end-charge omission IS the continuation model, and completion belongs
only where a real below-conductor exists. The fan also taught: the four
radials' shared hub is an auto-detected junction, so the below axis
carries value-1 hub ends whose by-parts terms are legitimate (they cancel
via the hub KCL row), unlike the contact end's.

Cells scored here (via ends-stripped axes through the production
`cross_complete_block` - stripping ends removes BT/SW/SQ/corner):

  shipped   - no swap: the grid field-form cross fill as shipped
  M         - designed MP cross, ALL end terms omitted (the
              continuation-consistent spelling)
  M+hub     - fan only: hub SW/SQ carried (real junction), contact BT
              still omitted (mono lesson)
  M+bnd     - lone only, the wreck re-banked for the record

Scoring caveat: on these decks BOTH conventions serve the contact node
the same #151 way, so the engine anchors remain a legitimate
convention-matched score (unlike the crossing deck's prints).

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe35_contact_anchors.py [lone|fan ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire import _crossing_fill, _medium_spec  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from probe9_sense import capture  # noqa: E402
from test_buried_serve_553 import contact_deck, fan_deck  # noqa: E402

ANCHORS = {
    "lone": 92.130 - 70.141j,
    "fan": 90.051 - 70.731j,
}
PRE_ADJ_MISS = {"lone": 12.91, "fan": 17.16}

# v2 of this probe improvised the deck and fed at arclength 5.667 (wrong
# height): the canonical builders ARE the provenance — feed arclength
# 4.3333 = the engine's EX 4,1,7 on the 10 -> 0 monopole. Numbers from the
# wrong-feed runs (lone shipped 58.51-15.24j etc.) are void.


def deck(name):
    return contact_deck() if name == "lone" else fan_deck()


def seeded(build):
    s = BSplineSolver(**build)
    n_wires = len(build["wires"])
    s._cached_wire_media = (_medium_spec.ABOVE,) + (_medium_spec.BELOW,) * (n_wires - 1)
    # momwire#698's exemption audit fires on seeded junction-carrying
    # contact decks (production refuses earlier, at wire_media, which the
    # seeding bypasses on purpose): stub the crossing-junction reading.
    s._crossing_junctions = lambda: ()
    return s


def main():
    names = sys.argv[1:] or ["lone", "fan"]
    out = {}
    for name in names:
        s = seeded(deck(name))
        geom = s._build_geometry()
        below = s._below_segments(geom)
        b_seg = np.sort(np.nonzero(below)[0])
        a_seg = np.sort(np.nonzero(~below)[0])

        ax_a = _crossing_fill.axis_data(s, geom, a_seg)
        ax_b = _crossing_fill.axis_data(s, geom, b_seg)
        print(
            f"{name}: A ends {len(ax_a['ends'])}, B (hub) ends {len(ax_b['ends'])}",
            flush=True,
        )

        cells = [("shipped", None)]
        strip = dict
        cells.append(("M", (strip(ax_a, ends=[]), strip(ax_b, ends=[]))))
        if len(ax_b["ends"]):
            cells.append(("M+hub", (strip(ax_a, ends=[]), ax_b)))
        if name == "lone":
            cells.append(("M+bnd", (ax_a, ax_b)))

        for cname, axes in cells:
            t0 = time.time()
            if axes is None:
                st = capture(seeded(deck(name)))
            else:
                t_ab = _crossing_fill.cross_complete_block(s, geom, axes[0], axes[1])
                st = capture(seeded(deck(name)), t_ab=t_ab, a_seg=a_seg, b_seg=b_seg)
            z = st["z_in"]
            miss = abs(z - ANCHORS[name])
            print(
                f"  {name} {cname:>8}: Z = {z:9.4f}   engine = "
                f"{ANCHORS[name]:.4f}   miss = {miss:7.3f} ohm   "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )
            out[f"{name}+{cname}"] = dict(
                z=f"{z:.4f}",
                anchor=f"{ANCHORS[name]:.4f}",
                miss_ohm=round(float(miss), 3),
            )

    fp = HERE.parent / "results" / "probe35-contact-anchors.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
