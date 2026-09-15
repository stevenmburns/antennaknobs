"""AK#1456 survey, mesh only (no solve): every catalog design's fed wires and
the fed-segment length each engine family meshes them to at the defaults.

  PYTHONPATH=<momwire src>:src python scratch/1456-fed-segments/survey_catalog.py

A fed wire is one carrying `ex` or a port name (the parity coercion's own
"marked" rule). Each family's count is `SimulationEngine.coerce_n_seg` at its
parity: odd for momwire bs2 / PyNEC / NEC-2 (gap mid-segment), even for NEC-5
(source at the centre knot, one segment of that length on each side).
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from antennaknobs.cli import list_builtin_designs
from antennaknobs.engine import SimulationEngine
from antennaknobs.network import GradedSegments, as_wire
import importlib

C = 299792458.0


def survey(name):
    b = importlib.import_module(f"antennaknobs.designs.{name}").Builder()
    lam = C / (b.freq * 1e6)
    rows = []
    for i, t in enumerate(b.build_wires()):
        w = as_wire(t)
        if w.ex is None and w.name is None:
            continue
        if isinstance(w.n_seg, GradedSegments):
            continue
        length = math.dist(w.p0, w.p1)
        n = int(w.n_seg)
        odd = SimulationEngine.coerce_n_seg(n, "odd")
        even = SimulationEngine.coerce_n_seg(n, "even")
        rows.append(
            dict(
                wire=i,
                name=w.name,
                ex=w.ex is not None,
                length_m=length,
                length_lam=length / lam,
                n_authored=n,
                n_odd=odd,
                n_even=even,
                seg_odd_mm=1000 * length / odd,
                seg_even_mm=1000 * length / even,
                ratio=(length / odd) / (length / even),
            )
        )
    return dict(design=name, freq_mhz=b.freq, fed=rows)


def main():
    out, errs = [], {}
    for name in sorted(list_builtin_designs()):
        try:
            out.append(survey(name))
        except Exception as exc:  # noqa: BLE001 - a survey records every design's failure and moves on
            errs[name] = f"{type(exc).__name__}: {exc}"[:200]
    here = Path(__file__).resolve().parent
    (here / "survey_catalog.json").write_text(
        json.dumps(dict(rows=out, errors=errs), indent=1)
    )
    fed = [r for d in out for r in d["fed"]]
    print(f"{len(out)} designs, {len(errs)} errors, {len(fed)} fed wires")
    print(
        "designs by fed-wire count:",
        sorted(Counter(len(d["fed"]) for d in out).items()),
    )
    ratios = sorted(round(r["ratio"], 3) for r in fed)
    print(
        "odd/even fed-segment ratio: min",
        ratios[0],
        "median",
        ratios[len(ratios) // 2],
        "max",
        ratios[-1],
    )
    print(
        "fed wires authored n=1:",
        sum(r["n_authored"] == 1 for r in fed),
        " n even:",
        sum(r["n_authored"] % 2 == 0 for r in fed),
        " n odd>1:",
        sum(r["n_authored"] % 2 == 1 and r["n_authored"] > 1 for r in fed),
    )
    short = [r for r in fed if r["length_lam"] < 0.01]
    print(
        f"short fed wires (< 0.01 lambda): {len(short)}; long (> 0.1 lambda): {sum(r['length_lam'] > 0.1 for r in fed)}"
    )
    for k, v in list(errs.items())[:8]:
        print("  ERR", k, v)


if __name__ == "__main__":
    main()
