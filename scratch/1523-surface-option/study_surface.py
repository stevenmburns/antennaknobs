"""AK#1523 surface option: #1532's coated-wire pair on NEC-5 near ground, against
razor-2p and bs2 (measure only).

  PYTHONPATH=<momwire src>:src python scratch/1523-surface-option/study_surface.py --mesh
  NEC5_EXE=<nec5cl> PYTHONPATH=<momwire src>:src \\
      python scratch/1523-surface-option/study_surface.py --out <dir>/rows_main.jsonl
  NEC5_EXE=<nec5cl> PYTHONPATH=<momwire src>:<pre-#1532 tree>/src \\
      python scratch/1523-surface-option/study_surface.py --tree pre --out <dir>/rows_pre.jsonl

Decks, arms and cells are as PLAN.md registers them. NEC-5 arms run first
across every cell, then the momwire arms. A refusal is a recorded answer: the
exception type and its full sentence, verbatim. The harness refuses to run on
any antennaknobs or momwire commit other than the ones PLAN.md names.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import json
import math
import os
import re
import resource
import subprocess
import sys
import time
import warnings
from pathlib import Path
from types import MappingProxyType

import numpy as np

BASE, FINE = 21, 42
WIRE_TYPES = ("18-awg-pvc", "22-awg-pvc", "28-awg-pvc")
GROUND = ("finite", 13.0, 0.005)
FT = 0.3048
SEVERNS = {
    "freq": 7.2,
    "n": 16,
    "h": 1.6e-3,
    "a": 0.51e-3,
    "b": 0.9e-3,
    "eps_r": 3.0,
    "mast": 33.5 * FT,
    "radial": 33.0 * FT,
    "ground": ("finite", 30.0, 0.020),
}
HEADS = {
    "main": "97ca2b6b02e7937abe5797052efd171bdd834031",
    "pre": "e7317cb192f0278ae8866ab1027f9f4a26c12bdb",
    # Amendment 2: the surface-mast fix, PR #1534 (main is cf3618b93 past it).
    "post": "34f533bb468467e0638f8b53776205f376466bd1",
}
MOMWIRE_HEAD = "227491dc24b7b4f0cf0d51c85e65b647ecfeb463"


def cells():
    from antennaknobs.network import WIRES

    w18 = WIRES["18-awg-pvc"]
    q1_arms = (
        "nec5",
        "nec5_lonly",
        "nec5_pre",
        "razor",
        "bs2",
        "razor_lonly",
        "bs2_lonly",
    )
    q2_arms = ("nec5", "nec5_lonly", "nec5_pre", "razor", "bs2")
    out = [
        dict(
            cell=f"q1-{wt}",
            deck="surface",
            wire_type=wt,
            h=None,
            nsegs=BASE,
            arms=q1_arms,
        )
        for wt in WIRE_TYPES
    ]
    out.append(
        dict(
            cell="m0-18",
            deck="surface",
            wire_type="18-awg-pvc",
            h=None,
            nsegs=FINE,
            arms=("nec5", "razor", "bs2"),
        )
    )
    out.append(
        dict(
            cell="m1-28",
            deck="surface",
            wire_type="28-awg-pvc",
            h=None,
            nsegs=FINE,
            arms=("nec5", "nec5_lonly", "razor", "bs2"),
        )
    )
    for tag, h in (
        ("2b", 2 * w18.insulation_radius),
        ("5b", 5 * w18.insulation_radius),
        ("20a", 20 * w18.radius),
    ):
        out.append(
            dict(
                cell=f"q2-{tag}",
                deck="surface",
                wire_type="18-awg-pvc",
                h=h,
                nsegs=BASE,
                arms=q2_arms,
            )
        )
    out.append(
        dict(
            cell="m2-20a",
            deck="surface",
            wire_type="18-awg-pvc",
            h=20 * w18.radius,
            nsegs=FINE,
            arms=("nec5", "razor", "bs2"),
        )
    )
    out.append(
        dict(
            cell="severns",
            deck="severns",
            wire_type=None,
            h=SEVERNS["h"],
            nsegs=None,
            arms=q2_arms,
        )
    )
    return out


def surface_builder(cell):
    from antennaknobs import resolve_variant_params
    from antennaknobs.designs.verticals.buried_radial_vertical import Builder

    params = dict(resolve_variant_params(Builder, "surface"))
    params.update(wire_type=cell["wire_type"], nominal_nsegs=cell["nsegs"])
    if cell["h"] is not None:
        params["surface_h_m"] = cell["h"]
    return Builder(params=params)


def severns_builder():
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Wire, WireSpec

    s = SEVERNS
    h = s["h"]
    jacket = WireSpec(
        radius=s["a"], insulation_radius=s["b"], insulation_eps_r=s["eps_r"]
    )
    bare = WireSpec(radius=s["a"])
    wires = []
    for i in range(s["n"]):
        theta = 2 * math.pi * i / s["n"]
        c, sn = math.cos(theta), math.sin(theta)
        x = s["radial"] * (0.0 if abs(c) < 1e-15 else c)
        y = s["radial"] * (0.0 if abs(sn) < 1e-15 else sn)
        wires.append(Wire((0.0, 0.0, h), (x, y, h), n_seg=10, spec=jacket))
    wires.append(
        Wire((0.0, 0.0, h), (0.0, 0.0, h + 0.05), n_seg=2, spec=bare, ex=1 + 0j)
    )
    wires.append(Wire((0.0, 0.0, h + 0.05), (0.0, 0.0, h + 0.5), n_seg=2, spec=bare))
    wires.append(
        Wire((0.0, 0.0, h + 0.5), (0.0, 0.0, h + s["mast"]), n_seg=19, spec=bare)
    )

    class Severns(AntennaBuilder):
        default_params = MappingProxyType({"freq": s["freq"], "design_freq": s["freq"]})

        def build_wires(self):
            return list(wires)

    return Severns()


@contextlib.contextmanager
def patched(arm):
    """nec5_lonly: #1532's writer asked for the inductance-only spelling.
    razor_lonly / bs2_lonly: momwire's a' swap suppressed."""
    with contextlib.ExitStack() as stack:
        if arm == "nec5_lonly":
            import antennaknobs.engines.nec5 as nec5_mod

            orig = nec5_mod.nec_wire_material
            nec5_mod.nec_wire_material = functools.partial(orig, pair=False)
            stack.callback(setattr, nec5_mod, "nec_wire_material", orig)
        elif arm in ("razor_lonly", "bs2_lonly"):
            import momwire._wire_loading as wl

            orig = wl.equivalent_radius
            wl.equivalent_radius = lambda radius, ins_radius, eps_r: float(radius)
            stack.callback(setattr, wl, "equivalent_radius", orig)
        yield


def deck_cards(deck):
    lines = deck.splitlines()
    gw, ld = [], []
    for line in lines:
        f = line.split()
        if f[:1] == ["GW"]:
            gw.append(
                {
                    "tag": int(f[1]),
                    "nseg": int(f[2]),
                    "p0": f[3:6],
                    "p1": f[6:9],
                    "radius": f[9],
                }
            )
        elif f[:1] == ["LD"]:
            ld.append(f[1:])
    return {
        "gw": gw,
        "ld": ld,
        "ge_gn": [ln for ln in lines if ln.split()[:1] in (["GE"], ["GN"])],
        "ex": [ln for ln in lines if ln.split()[:1] == ["EX"]],
        "jacket_comment_cards": sum(1 for ln in lines if ln.startswith("CM jacketed")),
    }


def _plain(x):
    try:
        return json.loads(json.dumps(x, default=str))
    except (TypeError, ValueError):
        return str(x)


def _run(rec, cell, arm, solve):
    from momwire import BSplineSolver, RazorSolver

    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.engines.nec5 import NEC5Engine

    if cell["deck"] == "severns":
        builder, ground = severns_builder(), SEVERNS["ground"]
    else:
        builder, ground = surface_builder(cell), GROUND
    freq = float(builder.freq)
    if arm.startswith("nec5"):
        eng = NEC5Engine(builder, ground=ground, require_exe=solve)
        rec["meshed"] = int(sum(c[3] for c in eng._cards))
        if not solve:
            rec["deck_cards"] = deck_cards(eng.deck([freq]))
            return
        z = complex(np.atleast_1d(eng.impedance())[0])
        run = eng.io_runs[-1] if eng.io_runs else None
        if run is None:
            rec["deck_cards"] = {"error": "no deck captured"}
        else:
            rec["deck_cards"] = deck_cards(run["deck"])
            rec["printout_flags"] = [
                ln.strip()
                for ln in run["printout"].splitlines()
                if re.search(r"WARN|ERROR", ln, re.IGNORECASE)
            ][:10]
    else:
        if arm.startswith("razor"):
            eng = MomwireEngine(
                builder,
                solver=RazorSolver,
                solver_kwargs={"nec5_quadrature": True},
                ground=ground,
                ground_z=0.0,
            )
        else:
            eng = MomwireEngine(
                builder, solver=BSplineSolver, ground=ground, ground_z=0.0
            )
        rec["meshed"] = int(sum(sum(c) for c in eng._edge_segments))
        if not solve:
            return
        made = []
        make = eng._make_solver

        def spy(*args, **kwargs):
            solver = make(*args, **kwargs)
            made.append(solver)
            return solver

        eng._make_solver = spy
        z = complex(np.atleast_1d(eng.impedance())[0])
        if made:
            s = made[-1]
            rec["kernel_radius"] = [float(r) for r in np.atleast_1d(s._radius_per_wire)]
            rec["conductor_radius"] = [
                float(r)
                for r in np.atleast_1d(getattr(s, "_conductor_radius_per_wire", []))
            ]
            rec["solvers_made"] = len(made)
        else:
            rec["kernel_radius"] = None
        adv = getattr(eng, "advisories", None)
        items = adv() if callable(adv) else adv
        rec["advisories"] = [_plain(x) for x in (items or [])]
    rec["z"] = [z.real, z.imag]


def one(cell, arm, tree, solve):
    from antennaknobs.network import WIRES

    rec = {k: cell[k] for k in ("cell", "deck", "wire_type", "h", "nsegs")}
    rec.update(arm=arm, tree=tree)
    if cell["deck"] == "severns":
        s = SEVERNS
        rec.update(a=s["a"], b=s["b"], eps_r=s["eps_r"], sigma=None, h_eff=s["h"])
    else:
        w = WIRES[cell["wire_type"]]
        rec.update(
            a=w.radius,
            b=w.insulation_radius,
            eps_r=w.insulation_eps_r,
            sigma=w.conductivity,
            h_eff=cell["h"] if cell["h"] is not None else w.insulation_radius,
        )
    t0 = time.perf_counter()
    caught = []
    try:
        with warnings.catch_warnings(record=True) as caught, patched(arm):
            warnings.simplefilter("always")
            _run(rec, cell, arm, solve)
        rec["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 - a refusal is a recorded answer (Q0)
        rec["status"] = "refused"
        rec["error_type"] = type(exc).__name__
        rec["error"] = str(exc)
    rec["warnings"] = [f"{w.category.__name__}: {w.message}"[:600] for w in caught]
    rec["secs"] = round(time.perf_counter() - t0, 3)
    return rec


def _git(path, *args):
    try:
        return subprocess.run(
            ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _head(path):
    return _git(path, "rev-parse", "HEAD")


def _src_matches(path, commit):
    """The package tree's `src/` in the working tree is exactly `commit`'s. A
    records branch moves HEAD past the commit PLAN.md names without touching
    `src/`, so HEAD alone cannot be the check."""
    root = _git(path, "rev-parse", "--show-toplevel")
    if root is None:
        return False
    return (
        subprocess.run(
            ["git", "-C", root, "diff", "--quiet", commit, "--", "src"]
        ).returncode
        == 0
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mesh", action="store_true", help="build and write decks, no solve"
    )
    ap.add_argument("--tree", choices=("main", "pre", "post"), default="main")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--only", default="", help="comma list of cell names")
    args = ap.parse_args()
    import antennaknobs
    import momwire
    import scipy

    ak_dir = Path(antennaknobs.__file__).resolve().parent
    mw_dir = Path(momwire.__file__).resolve().parent
    ak_head, mw_head = _head(ak_dir), _head(mw_dir)
    if (
        not _src_matches(ak_dir, HEADS[args.tree])
        or mw_head != MOMWIRE_HEAD
        or not _src_matches(mw_dir, MOMWIRE_HEAD)
    ):
        raise SystemExit(
            f"wrong trees: antennaknobs src at {ak_head} is not {HEADS[args.tree]}, "
            f"or momwire {mw_head} is not a clean {MOMWIRE_HEAD}"
        )
    solve = not args.mesh
    exe = os.environ.get("NEC5_EXE", "")
    if solve and not exe:
        raise SystemExit("NEC5_EXE is unset")
    meta = {
        "_meta": True,
        "tree": args.tree,
        "antennaknobs": str(ak_dir),
        "antennaknobs_head": ak_head,
        "antennaknobs_src_commit": HEADS[args.tree],
        "momwire": str(mw_dir),
        "momwire_head": mw_head,
        "nec5_exe": exe,
        "nec5_sha256": hashlib.sha256(Path(exe).read_bytes()).hexdigest()
        if exe
        else None,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "python": sys.version.split()[0],
        "rlimit_as": list(resource.getrlimit(resource.RLIMIT_AS)),
        "solve": solve,
    }
    only = set(filter(None, args.only.split(",")))
    todo = []
    for kind in ("nec5", "momwire"):
        for cell in cells():
            if only and cell["cell"] not in only:
                continue
            for arm in cell["arms"]:
                if (args.tree == "pre") != (arm == "nec5_pre"):
                    continue
                if (kind == "nec5") != arm.startswith("nec5"):
                    continue
                todo.append((cell, arm))
    out = open(args.out, "w") if args.out else None  # noqa: SIM115
    if out:
        out.write(json.dumps(meta) + "\n")
        out.flush()
    for cell, arm in todo:
        rec = one(cell, arm, args.tree, solve)
        if out:
            out.write(json.dumps(rec) + "\n")
            out.flush()
        z = rec.get("z")
        radials = (
            [g["radius"] for g in rec["deck_cards"]["gw"] if g["p0"][2] == g["p1"][2]][
                :1
            ]
            if isinstance(rec.get("deck_cards"), dict) and "gw" in rec["deck_cards"]
            else None
        )
        print(
            f"{rec['cell']} {arm}: {rec['status']} segs={rec.get('meshed')} "
            + (f"Z={z[0]:.4f}{z[1]:+.4f}j " if z else "")
            + (f"radial_gw={radials} " if radials else "")
            + (
                f"advisories={len(rec.get('advisories', []))} "
                if "advisories" in rec
                else ""
            )
            + f"warnings={len(rec['warnings'])} {rec['secs']}s"
            + (
                f" {rec['error_type']}: {rec['error'][:300]}"
                if rec["status"] != "ok"
                else ""
            ),
            flush=True,
        )
    if out:
        out.close()


if __name__ == "__main__":
    main()
