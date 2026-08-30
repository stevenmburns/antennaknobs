"""#567 phase 3, round 3 — the SOLVED stub under the M-only omission
spelling.

Rounds 1-2 exhausted the prescribed-source family: the rod ghost has the
right family but the wrong angular distribution (beta* closes each deck
alone and does not transfer), and the derived Born electrode nulls out
(azimuthal dilution + profile phase rotation; machinery certified to the
digit against round 1). The synthesis: the engine's stake sink strength
is deck-SOLVED, not prescribed (probe30: its junction current is a
per-deck solve; beta* differing across decks is exactly that signature).

The fiction-consistent solved object in our frame: a REAL vertical stub
dof at the contact node, junction-declared (split node dofs, grounded, no
KCL row — probe27's structure), with the cross block filled M-ONLY (all
by-parts ends/corners stripped — the #151 omission extended to the node,
probe34's zoo cell M, the one mesh-STABLE engine-like spelling) and the
self blocks left shipped. No prescribed profile, no amplitude constant:
the stub current is solved. Stub length and mesh are CONVERGENCE
parameters (ladders below), never fitted to the anchors.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/567-phase3/proto/probe_r3_stub.py [lone|fan ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scratch" / "524-phase2" / "proto"))
sys.path.insert(0, str(ROOT / "momwire" / "tests"))

from momwire import _crossing_fill, _medium_spec  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe_p31_ghost import seeded  # noqa: E402
from test_buried_serve_553 import contact_deck, fan_deck  # noqa: E402

ANCHORS = {"lone": 92.130 - 70.141j, "fan": 90.051 - 70.731j}
M_ONLY_BANK = {"lone": 103.8272 - 75.5958j, "fan": 105.2020 - 78.7769j}


def stub_mesh(L, dens=1):
    grid = [(0.15, 3), (0.5, 4), (1.2, 4), (2.4, 4), (4.2, 6)]
    breaks, n_per = [], []
    for b, n in grid:
        if b >= L - 1e-9:
            breaks.append(L)
            n_per.append(n)
            break
        breaks.append(b)
        n_per.append(n)
    else:
        breaks.append(L)
        n_per.append(6)
    return breaks, [dens * n for n in n_per]


def stub_deck(name, L, dens=1):
    """The anchor deck + a vertical stub dof at the contact node,
    junction-declared (mono end + stub start at the origin)."""
    build = dict(contact_deck() if name == "lone" else fan_deck())
    breaks, n_per = stub_mesh(L, dens)
    stub = np.asarray([[0.0, 0.0, 0.0]] + [[0.0, 0.0, -b] for b in breaks], float)
    wires = list(build["wires"]) + [stub]
    npe = list(build["n_per_edge_per_wire"]) + [n_per]
    stub_w = len(wires) - 1
    juncs = [list(j) for j in build.get("junctions", [])]
    juncs.append([(0, "end"), (stub_w, "start")])
    build.update(wires=wires, n_per_edge_per_wire=npe, junctions=juncs)
    return build


def solve_m_only(build):
    """M-only cross block (all ends/corners stripped) + shipped self
    blocks, split node dofs — probe34's zoo cell M, on this deck."""
    n_wires = len(build["wires"])
    media = (_medium_spec.ABOVE,) + (_medium_spec.BELOW,) * (n_wires - 1)
    s = seeded(dict(build), media)
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])
    ax_a = _crossing_fill.axis_data(s, geom, a_seg)
    ax_b = _crossing_fill.axis_data(s, geom, b_seg)
    t_ab = _crossing_fill.cross_complete_block(
        s, geom, dict(ax_a, ends=[]), dict(ax_b, ends=[])
    )
    st = capture(seeded(dict(build), media), t_ab=t_ab, a_seg=a_seg, b_seg=b_seg)
    return st["z_in"]


def main():
    names = sys.argv[1:] or ["lone"]
    out = {}
    for name in names:
        base = dict(contact_deck() if name == "lone" else fan_deck())
        z0 = solve_m_only(base)
        drift = abs(z0 - M_ONLY_BANK[name])
        print(
            f"{name} no-stub M-only: Z = {z0:9.4f} (drift vs bank {drift:.4f})",
            flush=True,
        )
        assert drift < 0.001

        cells = [(0.5, 1), (1.0, 1), (2.0, 1), (4.2, 1), (2.0, 2)]
        for L, dens in cells:
            t0 = time.time()
            z = solve_m_only(stub_deck(name, L, dens))
            miss = abs(z - ANCHORS[name])
            print(
                f"  {name} stub L={L} d{dens}: Z = {z:9.4f}  "
                f"miss = {miss:7.3f} ohm  ({time.time() - t0:.0f}s)",
                flush=True,
            )
            out[f"{name} stub L={L} d{dens}"] = dict(
                z=f"{z:.4f}", miss_ohm=round(miss, 3)
            )

    fp = HERE.parent / "results" / "probe-r3-stub.json"
    fp.parent.mkdir(exist_ok=True)
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
