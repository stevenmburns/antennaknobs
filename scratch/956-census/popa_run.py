"""Population A: the catalog's buried-conductor cases, momwire shipped vs main vs NEC-5.

    NEC5_EXE=~/nec5-timing/nec5cl-x13 \
    MOMWIRE_MAIN=/home/smburns/momwire-ad3cb9f/src \
        python scratch/956-census/popa_run.py --out scratch/956-census/popa-rows.csv

Membership and the four-way classification come from
`enumerate_population_a.py` -- re-derived here rather than pasted, so the census
cannot drift from the enumeration.

WHAT IS BEING COMPARED, precisely. Not "#1043 versus not-#1043": the shipped
pointer and momwire main differ by TWO separate changes, so the census runs
THREE momwire columns and each leg isolates one of them:

    pointer  23d81e5  v0.53.0, the submodule pointer antennaknobs ships
    mid      0e72ab4  + momwire#1004, separation-aware quadrature for the cross
                      block (`_below_interface.py`, `bspline.py`,
                      `sinusoidal_galerkin.py`)
    main     ad3cb9f  + momwire#1043, the W terms: the zz kernel is k2 V + dz'W
                      and the test axis's ends carry TW (`_crossing_fill.py`)

pointer -> mid is #1004's effect alone; mid -> main is the W terms' alone. The
file hashes make that checkable per row rather than trusted: `_below_interface.py`
moves on the first leg only, `_crossing_fill.py` on the second only, and each
row records both.

`git diff` over `*.cpp *.hpp *.h setup.py` is EMPTY across both legs, so one set
of compiled accelerators serves all three checkouts, and no meshing code differs
either -- which is what makes the three momwire columns the same mesh by
construction rather than by hope.

Two rungs -- the catalog mesh and nominal_nsegs x2 -- because a before/after at
one mesh cannot tell a physics change from a discretisation one.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKER = HERE / "popa_worker.py"
PY_EXE = str(ROOT / ".venv" / "bin" / "python")

PINNED = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "PYTHONUTF8": "1",
}


def cell(
    design: str, variant: str, nn: int, engine: str, *, momwire_src=None, exe=""
) -> dict:
    env = dict(os.environ)
    env.update(PINNED)
    if momwire_src:
        env["PYTHONPATH"] = momwire_src
    else:
        env.pop("PYTHONPATH", None)
    cmd = [
        PY_EXE,
        str(WORKER),
        "--design",
        design,
        "--variant",
        variant,
        "--nn",
        str(nn),
        "--engine",
        engine,
    ]
    if engine == "nec5":
        cmd += ["--exe", exe]
    p = subprocess.run(
        cmd, capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=7200
    )
    line = (p.stdout or "").strip().splitlines()
    if not line:
        return {
            "design": design,
            "variant": variant,
            "nn": nn,
            "engine": engine,
            "status": "worker-died",
            "error": (p.stderr or "")[-300:],
        }
    return json.loads(line[-1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "popa-rows.csv"))
    ap.add_argument("--raw", default=str(HERE / "popa-rows.jsonl"))
    a = ap.parse_args(argv)

    exe = os.environ.get("NEC5_EXE", "")
    main_src = os.environ.get("MOMWIRE_MAIN", "")
    mid_src = os.environ.get("MOMWIRE_MID", "")
    if not exe or not Path(exe).is_file():
        print("NEC5_EXE must name the NEC-5 executable", file=sys.stderr)
        return 2
    for name, p in (("MOMWIRE_MAIN", main_src), ("MOMWIRE_MID", mid_src)):
        if not p or not (Path(p) / "momwire").is_dir():
            print(f"{name} must name that checkout's src/", file=sys.stderr)
            return 2

    sys.path.insert(0, str(HERE))
    from enumerate_population_a import classify  # the enumeration's own classifier

    sys.path.insert(0, str(ROOT / "src"))
    import antennaknobs.web.examples  # noqa: F401
    import importlib

    from antennaknobs.geometry import flat_wires_to_polylines
    from antennaknobs.web.adapter import _build_builder, _discover_variants
    from antennaknobs.cli import list_builtin_designs

    members = []
    for dotted in list_builtin_designs():
        cls = importlib.import_module(f"antennaknobs.designs.{dotted}").Builder
        for variant in _discover_variants(cls):
            try:
                b = _build_builder(cls, {"variant": variant})
                polys = flat_wires_to_polylines(b.build_wires())["polylines"]
            except Exception:  # noqa: BLE001 -- reported by the enumerator, not here
                continue
            kind, zmin, zmax, nodes = classify(polys)
            if kind != "not-buried":
                members.append(
                    (
                        dotted,
                        variant,
                        kind,
                        zmin,
                        zmax,
                        nodes,
                        int(b.nominal_nsegs),
                        float(b.freq),
                    )
                )
    print(f"Population A: {len(members)} (design, variant) pairs\n")

    raw = open(a.raw, "w", encoding="utf-8")
    rows = []
    for dotted, variant, kind, zmin, zmax, nodes, base_nn, freq in members:
        for rung, factor in (("default", 1), ("refined", 2)):
            nn = base_nn * factor
            cells = {
                "shipped": cell(dotted, variant, nn, "momwire"),
                "mid": cell(dotted, variant, nn, "momwire", momwire_src=mid_src),
                "main": cell(dotted, variant, nn, "momwire", momwire_src=main_src),
                "nec5": cell(dotted, variant, nn, "nec5", exe=exe),
            }
            for k, v in cells.items():
                raw.write(json.dumps({"column": k, **v}) + "\n")
            raw.flush()

            def z(c):
                return (
                    complex(c["z_re"], c["z_im"]) if c.get("status") == "ok" else None
                )

            zs, zq, zm, z5 = (
                z(cells["shipped"]),
                z(cells["mid"]),
                z(cells["main"]),
                z(cells["nec5"]),
            )
            row = {
                "design": dotted,
                "variant": variant,
                "class": kind,
                "rung": rung,
                "nominal_nsegs": nn,
                "freq_mhz": freq,
                "zmin": zmin,
                "zmax": zmax,
                "crossing_nodes": nodes,
                "nec5_segs": cells["nec5"].get("nsegs", ""),
                "deck_sha": cells["nec5"].get("deck_sha256", ""),
                "ge_card": cells["nec5"].get("ge_card", ""),
                "shipped_status": cells["shipped"]["status"],
                "mid_status": cells["mid"]["status"],
                "main_status": cells["main"]["status"],
                "nec5_status": cells["nec5"]["status"],
                "R_shipped": f"{zs.real:.4f}" if zs else "",
                "X_shipped": f"{zs.imag:.4f}" if zs else "",
                "R_mid": f"{zq.real:.4f}" if zq else "",
                "X_mid": f"{zq.imag:.4f}" if zq else "",
                "R_main": f"{zm.real:.4f}" if zm else "",
                "X_main": f"{zm.imag:.4f}" if zm else "",
                "R_nec5": f"{z5.real:.4f}" if z5 else "",
                "X_nec5": f"{z5.imag:.4f}" if z5 else "",
                "dR_shipped": f"{zs.real - z5.real:+.4f}" if (zs and z5) else "",
                "dX_shipped": f"{zs.imag - z5.imag:+.4f}" if (zs and z5) else "",
                "dR_mid": f"{zq.real - z5.real:+.4f}" if (zq and z5) else "",
                "dX_mid": f"{zq.imag - z5.imag:+.4f}" if (zq and z5) else "",
                "dR_main": f"{zm.real - z5.real:+.4f}" if (zm and z5) else "",
                "dX_main": f"{zm.imag - z5.imag:+.4f}" if (zm and z5) else "",
                # the two legs, isolated
                "dR_1004": f"{zq.real - zs.real:+.6f}" if (zs and zq) else "",
                "dX_1004": f"{zq.imag - zs.imag:+.6f}" if (zs and zq) else "",
                "dR_wterms": f"{zm.real - zq.real:+.6f}" if (zq and zm) else "",
                "dX_wterms": f"{zm.imag - zq.imag:+.6f}" if (zq and zm) else "",
                "shipped_commit": cells["shipped"]
                .get("momwire_provenance", {})
                .get("commit", ""),
                "main_commit": cells["main"]
                .get("momwire_provenance", {})
                .get("commit", ""),
                "mid_commit": cells["mid"]
                .get("momwire_provenance", {})
                .get("commit", ""),
                "shipped_fill_sha": cells["shipped"]
                .get("momwire_provenance", {})
                .get("crossing_fill_sha256", ""),
                "mid_fill_sha": cells["mid"]
                .get("momwire_provenance", {})
                .get("crossing_fill_sha256", ""),
                "shipped_below_sha": cells["shipped"]
                .get("momwire_provenance", {})
                .get("below_interface_sha256", ""),
                "mid_below_sha": cells["mid"]
                .get("momwire_provenance", {})
                .get("below_interface_sha256", ""),
                "main_below_sha": cells["main"]
                .get("momwire_provenance", {})
                .get("below_interface_sha256", ""),
                "main_fill_sha": cells["main"]
                .get("momwire_provenance", {})
                .get("crossing_fill_sha256", ""),
                "shipped_TW": cells["shipped"]
                .get("momwire_provenance", {})
                .get("TW", ""),
                "main_TW": cells["main"].get("momwire_provenance", {}).get("TW", ""),
                "exe_sha": cells["nec5"].get("exe_sha256", ""),
                "refusals": " | ".join(
                    f"{k}: {v['error']}" for k, v in cells.items() if v.get("error")
                )[:400],
            }
            rows.append(row)
            print(
                f"{dotted:38s} {variant:9s} {rung:8s} nn={nn:3d} {kind:14s} "
                f"ptr {row['R_shipped'] or '—':>9s}{row['X_shipped'] or '':>10s} "
                f"mid {row['R_mid'] or '—':>9s}{row['X_mid'] or '':>10s} "
                f"main {row['R_main'] or '—':>9s}{row['X_main'] or '':>10s} "
                f"nec5 {row['R_nec5'] or '—':>9s}{row['X_nec5'] or '':>10s}"
            )
    raw.close()
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {len(rows)} rows -> {a.out} (raw cells in {a.raw})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
