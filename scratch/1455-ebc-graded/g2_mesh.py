"""AK#1455's G2: the graded radiator's mesh at nominal_nsegs 21 / 42 / 84, read
from the built wires, with no solve.

  PYTHONPATH=<momwire src>:src python scratch/1455-ebc-graded/g2_mesh.py

Checks against PLAN.md's G2 row: adjacent radiator segments within 2x, none
above the stock radiator's segment, the first at 25 mm, the cap equal to the
stock segment, (fracs, counts) equal to AK#1454's `graded_schedule`, and the
fed wire unchanged. Also records each engine's fed segment and the step from
it into the radiator, which PLAN.md reports but does not gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "1443-counterpoise"))

from ladder import StockRadiator, radiator_segments
from step2_source import graded_schedule

from antennaknobs.designs.verticals.elevated_buried_counterpoise import Builder
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.geometry import flat_wires_to_polylines
from antennaknobs.network import as_wire


def nec5_fed(b):
    """NEC-5's fed GW card and the radiator card above it, from the deck."""
    deck = NEC5Engine(b, ground=("finite", b.design_eps_r, b.design_sigma)).deck(
        [b.freq]
    )
    gw = [
        ln.replace(",", " ").split() for ln in deck.splitlines() if ln.startswith("GW")
    ]
    ex = next(
        ln.replace(",", " ").split() for ln in deck.splitlines() if ln.startswith("EX")
    )
    tag, seg = int(ex[2]), int(ex[3])
    cards = {int(c[1]): c for c in gw}

    def seg_len(c):
        p = np.array([float(v) for v in c[3:9]])
        return float(np.linalg.norm(p[3:] - p[:3])) / int(c[2])

    fed = cards[tag]
    top = [float(v) for v in fed[3:9]][5]
    above = next(c for c in gw if abs(float(c[5]) - top) < 1e-9 and c is not fed)
    return dict(
        fed_tag=tag,
        fed_seg_index=seg,
        fed_segments=int(fed[2]),
        fed_seg_mm=1000 * seg_len(fed),
        radiator_first_card_seg_mm=1000 * seg_len(above),
    )


def check(nn):
    b = Builder()
    b.nominal_nsegs = nn
    s = StockRadiator()
    s.nominal_nsegs = nn
    ws = [as_wire(t) for t in b.auto_mesh(b.build_wires())]
    wss = [as_wire(t) for t in s.auto_mesh(s.build_wires())]
    segs = np.array(radiator_segments(b))
    stock_h = radiator_segments(s)[0]
    eps = 0.05
    length = 0.25 * b.design_wavelength * b.length_factor - eps
    cap = length / b.segs_for(length, 0.25 * b.design_wavelength)
    fracs, counts = graded_schedule(length, eps / 2, stock_h)
    steps = segs[1:] / segs[:-1]
    feeds_g = flat_wires_to_polylines(ws)["feeds"]
    feeds_s = flat_wires_to_polylines(wss)["feeds"]
    mw_fed_mm = (
        1000 * float(np.linalg.norm(np.subtract(ws[0].p1, ws[0].p0))) / int(ws[0].n_seg)
    )
    checks = {
        "adjacent_within_2x": bool(
            steps.max() <= 2 + 1e-9 and steps.min() >= 0.5 - 1e-9
        ),
        "max_le_stock_segment": bool(segs.max() <= stock_h * (1 + 1e-12)),
        "first_segment_25mm": bool(abs(segs[0] - 0.025) < 1e-12),
        "cap_equals_stock_segment": bool(abs(cap - stock_h) <= 1e-12 * stock_h),
        "schedule_equals_ak1454": bool(
            ws[1].n_seg.counts == counts
            and np.allclose(ws[1].n_seg.fracs, fracs, rtol=1e-12, atol=0)
        ),
        "fed_wire_unchanged": bool(
            ws[0] == wss[0]
            and abs(np.linalg.norm(np.subtract(ws[0].p1, ws[0].p0)) - eps) < 1e-12
            and ws[0].ex == 1
            and len(feeds_g) == 1
            and feeds_g[0][1] == feeds_s[0][1]
        ),
    }
    rec = dict(
        nn=nn,
        checks=checks,
        radiator_length_m=length,
        radiator_segments=len(segs),
        stock_radiator_segments=int(wss[1].n_seg),
        stock_seg_mm=1000 * stock_h,
        first_mm=1000 * segs[0],
        max_mm=1000 * segs.max(),
        step_max=float(steps.max()),
        step_min=float(steps.min()),
        fracs=list(ws[1].n_seg.fracs),
        counts=list(ws[1].n_seg.counts),
        momwire_feed_arclength_m=float(feeds_g[0][1]),
        momwire_fed_segments=int(ws[0].n_seg),
        momwire_fed_seg_mm=mw_fed_mm,
        nec5=nec5_fed(b),
    )
    print(
        f"nn={nn}: radiator {len(segs)} segs (stock {int(wss[1].n_seg)} at "
        f"{1000 * stock_h:.2f} mm), first {1000 * segs[0]:.3f} mm, max {1000 * segs.max():.2f} mm, "
        f"steps [{steps.min():.3f}, {steps.max():.3f}], momwire fed {int(ws[0].n_seg)} x "
        f"{mw_fed_mm:.1f} mm at s={feeds_g[0][1]:.4f} m, NEC-5 fed {rec['nec5']['fed_segments']} x "
        f"{rec['nec5']['fed_seg_mm']:.1f} mm -> radiator card {rec['nec5']['radiator_first_card_seg_mm']:.1f} mm"
    )
    for k, v in checks.items():
        print(f"    {k}: {'PASS' if v else 'FAIL'}")
    return rec


def main():
    rows = [check(nn) for nn in (21, 42, 84)]
    ok = all(all(r["checks"].values()) for r in rows)
    out = Path(__file__).resolve().parent / "g2_mesh.json"
    out.write_text(json.dumps(dict(pass_=ok, rows=rows), indent=1))
    print("G2", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
