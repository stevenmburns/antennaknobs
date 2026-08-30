"""#567 re-derivation R5 — the ENGINE's own mesh ladder on the anchor decks.

The banked anchors (92.130-70.141j lone / 90.051-70.731j fan) are x1
prints — 15 segments on the monopole. The #706/#703 lesson is that the
engine's x1 print can sit many ohms from its own converged value (17.2 on
the reactive deck), so the re-derivation may only quote ladder tails.

This runs the two anchor decks at x1/x2/x3/x4 with the feed held at the
SAME PHYSICAL NODE (arc 4.6667 from the top): EX 4,1,k with k = 7N/15,
integral at every rung (N=15:7, 30:14, 45:21, 60:28). Radials scale
10 -> 20/30/40. Only PRINTED impedances are recorded (NEC-5
LLNL-CODE-746721, our licensed copy; conclusions only, no internals).

Run (antennaknobs venv, binary on NEC5_EXE):
  NEC5_EXE=~/antennas/NEC5-downloads/nec5-linux/nec5cl \
    .venv/bin/python scratch/567-phase3/proto/probe_r5_engine_ladder.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

RUNGS = (1, 2, 3, 4)


def lone_deck(m):
    n, k, r = 15 * m, 7 * m, 10 * m
    return (
        "CM momwire#567 R5 lone-radial x{}\nCE\n".format(m)
        + f"GW 1,{n},0.,0.,10.,0.,0.,0.,.001\n"
        + f"GW 2,{r},0.,0.,-0.15,5.,0.,-0.15,.001\n"
        + "GE 1,-1\nFR 0,1,0,0,7.\nGN 0,0,0,0,13.,.005\n"
        + f"EX 4,1,{k},0,1.,0.\nPQ 0\nXQ 0\nEN\n"
    )


def fan_deck(m):
    n, k, r = 15 * m, 7 * m, 10 * m
    dirs = ["5.,0.", "0.,5.", "-5.,0.", "0.,-5."]
    cards = "CM momwire#567 R5 four-radial x{}\nCE\n".format(m)
    cards += f"GW 1,{n},0.,0.,10.,0.,0.,0.,.001\n"
    for i, d in enumerate(dirs):
        x, y = d.split(",")
        cards += f"GW {i + 2},{r},0.,0.,-0.15,{x},{y},-0.15,.001\n"
    cards += "GE 1,-1\nFR 0,1,0,0,7.\nGN 0,0,0,0,13.,.005\n"
    cards += f"EX 4,1,{k},0,1.,0.\nPQ 0\nXQ 0\nEN\n"
    return cards


def main():
    from antennaknobs.engines.nec5 import NEC5Engine

    sys.path.insert(0, str(Path.home() / "antennas/antennaknobs/scripts"))
    from bench_nec5_walk_why import make_dipole

    captures = HERE.parent / "results" / "r5-captures"
    captures.mkdir(parents=True, exist_ok=True)
    eng = NEC5Engine(make_dipole(20), ground=None, capture_dir=captures)

    out = {}
    for name, build in (("lone", lone_deck), ("fan", fan_deck)):
        prev = None
        for m in RUNGS:
            z = complex(eng.run_deck(build(m))[0][0][2])
            step = f"   step {abs(z - prev):7.3f}" if prev is not None else ""
            print(f"{name} x{m}: engine prints {z:9.4f}{step}", flush=True)
            out[f"{name}-x{m}"] = f"{z:.4f}"
            prev = z

    fp = HERE.parent / "results" / "probe-r5-engine-ladder.json"
    fp.write_text(json.dumps(out, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
