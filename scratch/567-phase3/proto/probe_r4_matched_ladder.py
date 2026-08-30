"""#567 re-derivation R4 — the matched-feed MESH LADDER (momwire side).

The #706 erratum: the anchor builders fed at 4.3333 where the engine's
`EX 4,1,7` drives the node at 4.6667. PR #707 corrected the builders;
probe35 re-run at the matched feed gives (15/10 mesh, x1):

  lone  shipped 51.43   M-only 3.474   M+bnd 51.38
  fan   shipped ?       M-only 4.976 (banked 2026-08-28)

Those are ONE COARSE RUNG. This probe ladders the momwire side at the
matched feed — n_per_edge scaled x1/x2/x3(/x4 lone) with the feed held at
the 4.6667 node (a mesh node at every multiple of 15) — for the two
decision cells: `shipped` (the field-form fill, for the record) and `M`
(designed MP cross, all end terms omitted — the continuation-consistent
spelling, the serve candidate). Fan additionally re-verifies M+hub ≡ M at
x1 (the hub's by-parts terms cancel through its KCL row).

The engine anchors are x1 prints; probe_r5 ladders the engine itself.
Converged-vs-converged is the only comparison the re-derivation may quote
(the #706 lesson: quote LADDERS, never single rungs).

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/567-phase3/proto/probe_r4_matched_ladder.py [lone|fan ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "524-phase2" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire import _crossing_fill, _medium_spec  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from probe9_sense import capture  # noqa: E402
from test_buried_serve_553 import contact_deck, fan_deck  # noqa: E402

# The engine's x1 prints (golden_buried_anchor_nec5, EX 4,1,7 = node
# 4.6667). Quoted per rung for orientation ONLY — the decision compares
# ladder tails, and probe_r5 supplies the engine's own tail.
ANCHOR_X1 = {"lone": 92.130 - 70.141j, "fan": 90.051 - 70.731j}

RUNGS = {"lone": (1, 2, 3, 4), "fan": (1, 2, 3)}


def deck(name, m):
    b = contact_deck() if name == "lone" else fan_deck()
    b["n_per_edge_per_wire"] = [
        [n * m for n in edge] for edge in b["n_per_edge_per_wire"]
    ]
    return b


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
    fp = HERE.parent / "results" / "probe-r4-matched-ladder.json"
    out = json.loads(fp.read_text()) if fp.exists() else {}
    for name in names:
        for m in RUNGS[name]:
            s = seeded(deck(name, m))
            geom = s._build_geometry()
            below = s._below_segments(geom)
            b_seg = np.sort(np.nonzero(below)[0])
            a_seg = np.sort(np.nonzero(~below)[0])
            ax_a = _crossing_fill.axis_data(s, geom, a_seg)
            ax_b = _crossing_fill.axis_data(s, geom, b_seg)

            cells = [
                ("shipped", None),
                ("M", (dict(ax_a, ends=[]), dict(ax_b, ends=[]))),
            ]
            if name == "fan" and m == 1:
                cells.append(("M+hub", (dict(ax_a, ends=[]), ax_b)))

            for cname, axes in cells:
                t0 = time.time()
                if axes is None:
                    st = capture(seeded(deck(name, m)))
                else:
                    t_ab = _crossing_fill.cross_complete_block(
                        s, geom, axes[0], axes[1]
                    )
                    st = capture(
                        seeded(deck(name, m)), t_ab=t_ab, a_seg=a_seg, b_seg=b_seg
                    )
                z = st["z_in"]
                d_x1 = abs(z - ANCHOR_X1[name])
                print(
                    f"{name} x{m} {cname:>7}: Z = {z:9.4f}   "
                    f"|Z - engine_x1| = {d_x1:7.3f}   "
                    f"({time.time() - t0:.0f}s)",
                    flush=True,
                )
                out[f"{name}-x{m}+{cname}"] = dict(
                    z=f"{z:.4f}",
                    vs_engine_x1_ohm=round(float(d_x1), 3),
                )
            fp.write_text(json.dumps(out, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
