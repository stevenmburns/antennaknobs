"""C1-kink study, probe 4 — the #449 decider: slope freedom at the fed
knot only.

Attribution state (from the ladder construction + today's ground truth):
the ward deck's nine radius-step boundaries are separate wires with
declared junctions — C0 ALREADY. The feed sits at a mid-section mesh
knot — C1, curvature freedom only. So the fed knot is the ONLY
C1-constrained non-smooth feature bs2 faces, and the one candidate left
for the ~0.5 ohm tail stall (#449).

The experiment: split the fed section AT the feed into two wires and
drive the new 2-member junction as a junction port (series node source,
the machinery #172 built) — local C0 at the feed, everything else
identical. Run the ward ladder, compare tails against the banked bs2-ek
rows and the NEC-5 Richardson anchor. Feed-model caveat: a junction
port is a node source, the banked rows are a delta gap at the same
knot — NEC-5's own EX is an end-code (node) source, so the split rows
are, if anything, feed-matched CLOSER to the anchor.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/c1-kink-study/probe4_449_feed_split.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MW = Path(__file__).resolve().parents[2] / "momwire"
sys.path.insert(0, str(MW / "scripts"))
sys.path.insert(0, str(MW / "tests"))

from capture_taper_nec5_lane import GEOMS, WL, wires_of  # noqa: E402
from golden_taper_nec5 import TAPER_LADDERS  # noqa: E402
from momwire import BSplineSolver  # noqa: E402

DECK = "ward"
sections, fed_tag = GEOMS[DECK]["sections"], GEOMS[DECK]["fed"]


def split_solver(n_per_sec):
    wires, radii, junctions = wires_of(sections)
    fed = fed_tag - 1
    a, b = wires[fed][0], wires[fed][1]
    mid = 0.5 * (np.asarray(a, dtype=float) + np.asarray(b, dtype=float))
    lo = np.stack([np.asarray(a, dtype=float), mid])
    hi = np.stack([mid, np.asarray(b, dtype=float)])
    new_wires = list(wires[:fed]) + [lo, hi] + list(wires[fed + 1 :])
    new_radii = list(radii[:fed]) + [radii[fed], radii[fed]] + list(radii[fed + 1 :])

    def remap(w):
        return w if w < fed else w + 1  # old fed -> lo; wires after shift by 1

    new_junctions = []
    for j in junctions:
        grp = []
        for w, end in j:
            if w == fed:
                grp.append((fed, end) if end == "start" else (fed + 1, end))
            else:
                grp.append((remap(w), end))
        new_junctions.append(grp)
    new_junctions.append([(fed, "end"), (fed + 1, "start")])
    half = n_per_sec // 2
    npe = (
        [[n_per_sec]] * fed + [[half], [half]] + [[n_per_sec]] * (len(wires) - fed - 1)
    )
    return BSplineSolver(
        degree=2,
        extended_kernel=True,
        wires=new_wires,
        n_per_edge_per_wire=npe,
        wire_radius=new_radii,
        wavelength=WL,
        feeds=[],  # explicit — omitting it engages the legacy default feed
        junctions=new_junctions,
        # Series EMF at the split knot between the lo half and the rest of
        # the group — "the shape NEC's EX card writes" (#898/#315), i.e.
        # feed-matched to the NEC-5 anchor's own end-code source.
        node_gaps=[(fed, "end", 1 + 0j)],
    )


def main():
    rows = {r[0]: r for r in TAPER_LADDERS[DECK]}
    ns = sorted(rows)
    # NEC-5 Richardson anchor from its two densest rungs (first order-ish;
    # #449's own anchor recipe)
    z1, z2 = rows[ns[-2]][1], rows[ns[-1]][1]
    r = ns[-1] / ns[-2]
    zstar = z2 + (z2 - z1) / (r - 1.0)
    print(f"NEC-5 anchor Z* = {zstar:.4f} (from N={ns[-2]},{ns[-1]})", flush=True)

    out = {"anchor": f"{zstar:.4f}", "rows": {}}
    n_sections = len(sections)
    for n_total in ns:
        n_per_sec = n_total // n_sections
        banked = rows[n_total][5]  # bs2-ek column
        t0 = time.time()
        z, _ = split_solver(n_per_sec).compute_impedance()
        z = complex(np.ravel(z)[0])
        dt = time.time() - t0
        print(
            f"N={n_total:4d}: bs2-ek banked |d|={abs(banked - zstar):7.4f}   "
            f"SPLIT-fed |d|={abs(z - zstar):7.4f}   Z={z:.4f}  ({dt:.0f}s)",
            flush=True,
        )
        out["rows"][str(n_total)] = dict(
            banked=f"{banked:.4f}",
            split=f"{z:.4f}",
            d_banked=round(float(abs(banked - zstar)), 4),
            d_split=round(float(abs(z - zstar)), 4),
        )
    (HERE / "results-probe4.json").write_text(json.dumps(out, indent=2))
    print("saved", flush=True)


if __name__ == "__main__":
    main()
