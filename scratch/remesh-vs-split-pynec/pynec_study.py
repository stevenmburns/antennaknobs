"""Re-mesh-first against split-always for positioned ports on PyNEC (measure only).

  PYTHONPATH=<momwire src>:src python scratch/remesh-vs-split-pynec/pynec_study.py --mesh
  PYTHONPATH=<momwire src>:src \\
      python scratch/remesh-vs-split-pynec/pynec_study.py --out rows.jsonl

The 10.5 m dipole, radius 1 mm, 14.2 MHz, of the split study
(`study.py`, copied from scratch/1511-bs2-split-study at 4bcf7b2 for its
builders and #1511's split rule). Two paths on antennaknobs main's PyNECEngine:

  R  re-mesh first: the whole wire with PortOnWire ports at their positions, as
     main's engine serves it. It re-meshes the wire within 2x when a count puts
     every port on a segment centre; otherwise it splits a wire carrying ONE
     port (#1512); and a wire carrying several with no fitting count keeps its
     parity count and snaps each port to the nearest centre (#1511 has not
     landed).
  S  split always: #1511's centre rule built by hand (`study.split_b`), each
     port a PortOnWire at the middle of its own fed piece, even when a count
     would fit.

Each row records the engine's meshed counts, whether the engine split, the snap
offsets main reports (a port is placed exactly when none is reported), and Z at
the feed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import study

study.CASES.setdefault("k1_031", (("feed", 0.31),))

WINDOW_BASES = (41, 81, 161)
TRANSITIONS = (range(45, 56), range(70, 81))
_SNAP = re.compile(r"([0-9.]+(?:e[-+]?[0-9]+)?) mm away")


def configs():
    seen = []

    def add(*cfg):
        if cfg not in seen:
            seen.append(cfg)

    for case in ("k1_031", "k2", "k3"):
        for base in WINDOW_BASES:
            for n in range(base - 5, base + 6):
                for path in ("R", "S"):
                    add(case, "free", n, path)
            for path in ("R", "S"):
                add(case, "free", 2 * base - 1, path)
    for n in range(76, 87):
        for path in ("R", "S"):
            add("k2", "somm13", n, path)
    for path in ("R", "S"):
        add("k2", "somm13", 161, path)
    for case in ("k1_031", "k2"):
        for rng in TRANSITIONS:
            for n in rng:
                for path in ("R", "S"):
                    add(case, "free", n, path)
    return seen


def one(case, ground, n, path, solve):
    from antennaknobs.engines.pynec import PyNECEngine
    from antennaknobs.network import as_wire

    gnd = study.GROUND if ground == "somm13" else None
    b, _pieces = study.builder(case, "A" if path == "R" else "B", n)
    rec = dict(case=case, ground=ground, n=n, path=path)
    t0 = time.perf_counter()
    try:
        eng = PyNECEngine(b, ground=gnd)
        wires = [as_wire(t) for t in eng.tups]
        rec["counts"] = [int(w.n_seg) for w in wires]
        rec["segments"] = sum(rec["counts"])
        rec["pieces"] = len(wires)
        notes = [a for a in eng.advisories if a.get("category") == "FeedPlacement"]
        rec["notes"] = [a["text"] for a in notes]
        rec["snap_mm"] = [
            float(m.group(1)) for a in notes if (m := _SNAP.search(a["text"]))
        ]
        rec["split"] = bool(getattr(eng, "_split_feeds", None))
        rec["exact"] = not rec["snap_mm"]
        if solve:
            z = complex(np.atleast_1d(eng.impedance())[0])
            rec["z"] = [z.real, z.imag]
        rec["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 - one refused run is a recorded row
        rec["status"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"[:400]
    rec["secs"] = round(time.perf_counter() - t0, 3)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", action="store_true", help="mesh only, no solve")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    import PyNEC

    import antennaknobs

    meta = dict(
        _meta=True,
        pynec=str(Path(PyNEC.__file__).resolve()),
        antennaknobs=str(Path(antennaknobs.__file__).resolve().parent),
        solve=not args.mesh,
    )
    out = open(args.out, "w") if args.out else None  # noqa: SIM115
    if out:
        out.write(json.dumps(meta) + "\n")
    for case, ground, n, path in configs():
        rec = one(case, ground, n, path, solve=not args.mesh)
        if out:
            out.write(json.dumps(rec) + "\n")
            out.flush()
        z = rec.get("z")
        print(
            f"{case} {ground} n={n} {path}: {rec['status']} segs={rec.get('segments')} "
            f"pieces={rec.get('pieces')} split={rec.get('split')} snap={rec.get('snap_mm')} "
            + (f"Z={z[0]:.4f}{z[1]:+.4f}j" if z else "")
            + rec.get("error", ""),
            flush=True,
        )
    if out:
        out.close()


if __name__ == "__main__":
    main()
