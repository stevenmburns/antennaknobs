"""Which catalog designs benefit from the singular-enrichment basis? (issue #565)

The follow-up to `bench_enrichment_probe.py`: that tool scored the #521 junction
cluster and found enrichment a driving-point no-op there. This one asks the
general question across the WHOLE catalog — *is there any design where the K≥3
junction bases earn their keep?* — and encodes the answer's two traps so the
next reader does not re-fall into them.

The working hypothesis (Steve): enrichment should help where there is a **K≥3
junction with appreciable current through at least 3 arms**. This tool tests it
directly. Per design it:

  1. finds the K≥3 junctions in the translated geometry and, from a bs2 current
     solve, measures each junction's **arm-current split** — how many arms carry
     ≥20% of the largest arm's current (the "live arms" count);
  2. measures the **driving-point enrichment shift** |Z_enr − Z_bs2| with BOTH
     the `raw` and `stable` variants, at two meshes.

Two traps, both learned the hard way (2026-07-25):

  * **`raw`'s coarse-mesh transient masquerades as benefit.** On the fan dipoles
    `raw` swings the driving point ~2.8 Ω at N=41–161 — but it is *wrong* (it
    disagrees with sin/bs2/PyNEC, which all agree) and washes out by N≈321. The
    `stable` / `tikhonov` variants do not do this. So a large `raw` |Δ| is NOT
    evidence of benefit; only a persistent **`stable`** shift is. This tool
    prints both side by side precisely so the artifact is visible, not hidden.
  * **"3 live arms" is necessary, not sufficient.** Every K≥3 design in the
    catalog has qualifying junctions (fan dipoles, T-match verticals, the
    hentenna/hourglass cluster, j-poles), yet `stable` enrichment is a ≤0.01 Ω
    no-op on all of them: bs2 already resolves the junction. Benefit also needs
    the feed current to flow *through* the junction singularity AND the junction
    to be the convergence bottleneck — conditions the purpose-built momwire test
    hentenna (feed stub at the junction, otherwise well-conditioned) meets but no
    catalog geometry does.

Incidental limitation surfaced here: momwire raises `NotImplementedError` for
`use_singular_enrichment` + distributed wire loading ("the enrichment bases
don't carry the loading overlap term"), so lossy-spec designs (e.g.
`verticals.pota_performer`) are recorded as skipped, not silently dropped.

    python scripts/bench_enrichment_scan.py
    python scripts/bench_enrichment_scan.py --meshes 41 81 --only multiband.trap_fan_dipole
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")
os.environ.setdefault("OPENBLAS_THREAD_TIMEOUT", "1")

import argparse
import importlib
import json
import resource
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

LIVE_ARM_FRACTION = 0.20  # an arm is "live" if it carries ≥ this × the max arm |I|
DEFAULT_MESHES = (41, 81)
DEFAULT_MEM_GB = 8.0
BASE_KW = {"degree": 2}


def _enr_kw(variant):
    return {"degree": 2, "use_singular_enrichment": True, "enrichment_variant": variant}


def load_design(dotted):
    return importlib.import_module(f"antennaknobs.designs.{dotted}").Builder


def kge3_junctions(builder_cls, nseg):
    """The K≥3 junctions in the translated geometry, plus the max junction
    degree (0 when the design has no multi-wire junctions at all)."""
    from antennaknobs.geometry import flat_wires_to_polylines

    b = builder_cls()
    b.nominal_nsegs = nseg
    tr = flat_wires_to_polylines(b.build_wires())
    juncs = tr["junctions"] or []
    kge3 = [j for j in juncs if len(j) >= 3]
    maxdeg = max((len(j) for j in juncs), default=0)
    return kge3, maxdeg


def arm_split(builder_cls, nseg, kge3):
    """For the most-populated K≥3 junction, the sorted arm-current magnitudes
    normalised to the largest (top arm = 1.0) and the count of live arms
    (≥ LIVE_ARM_FRACTION of that largest). Solved on the plain bs2 basis — the
    split is a geometry/excitation property, not an enrichment one."""
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver

    b = builder_cls()
    b.nominal_nsegs = nseg
    cur = MomwireEngine(
        b, solver=BSplineSolver, solver_kwargs=BASE_KW
    ).current_distribution()

    best_live, best_split = 0, None
    for j in kge3:
        mags = []
        for wire, end in j:
            kc = cur[wire].knot_currents
            mags.append(abs(kc[0] if end == "start" else kc[-1]))
        top = max(mags) or 1.0
        live = sum(1 for m in mags if m >= LIVE_ARM_FRACTION * top)
        if live > best_live:
            best_live = live
            best_split = [
                round(float(m) / float(top), 2) for m in sorted(mags, reverse=True)
            ]
    return best_live, best_split


def enr_shift(builder_cls, nseg, variant):
    """|Z_enr − Z_bs2| at feed 0 for one variant, and |Z_bs2|. Raises on a
    momwire refusal (e.g. enrichment + distributed loading) so the caller can
    record the reason."""
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver

    def z(kw):
        b = builder_cls()
        b.nominal_nsegs = nseg
        return complex(
            MomwireEngine(b, solver=BSplineSolver, solver_kwargs=kw).impedance()[0]
        )

    zb = z(BASE_KW)
    ze = z(_enr_kw(variant))
    return abs(ze - zb), abs(zb)


def scan_design(design, meshes):
    """One catalog design → its K≥3 junction profile and raw/stable enrichment
    shifts. Never raises; a refusal or dud is recorded as ``skip``."""
    row = {"design": design, "skip": None}
    try:
        cls = load_design(design)
    except Exception as e:  # noqa: BLE001
        row["skip"] = f"load: {type(e).__name__}: {e}"
        return row
    try:
        kge3, maxdeg = kge3_junctions(cls, meshes[-1])
    except Exception as e:  # noqa: BLE001
        row["skip"] = f"geom: {type(e).__name__}: {e}"
        return row
    row["maxdeg"] = maxdeg
    row["n_kge3"] = len(kge3)
    if not kge3:
        return row  # no junction to enrich — reported but not ranked
    try:
        row["live"], row["split"] = arm_split(cls, meshes[-1], kge3)
    except Exception as e:  # noqa: BLE001
        row["live"], row["split"] = None, None
        row["skip"] = f"current: {type(e).__name__}: {str(e)[:60]}"
        return row
    shifts = {}
    for n in meshes:
        cell = {}
        for variant in ("raw", "stable"):
            try:
                d, zb = enr_shift(cls, n, variant)
                cell[variant] = d
                cell["zb"] = zb
            except NotImplementedError as e:
                row["skip"] = f"enr: {str(e)[:70]}"
                return row
            except Exception as e:  # noqa: BLE001
                cell[variant] = None
                cell.setdefault("err", f"{type(e).__name__}: {str(e)[:40]}")
        shifts[n] = cell
    row["shifts"] = shifts
    return row


def _stable_at(row, mesh):
    """The stable-variant shift at the finest requested mesh, or -1 to sort
    junction-free / skipped rows last."""
    sh = row.get("shifts")
    if not sh:
        return -1.0
    cell = sh.get(mesh) or next(iter(sh.values()))
    v = cell.get("stable")
    return v if v is not None else -1.0


def print_report(rows, meshes):
    print(
        "\nENRICHMENT-BENEFIT SCAN (issue #565)  "
        f"meshes={list(meshes)}  live-arm fraction={LIVE_ARM_FRACTION:.0%}"
    )
    print(
        "  rawΔ / stblΔ = |Z_enr − Z_bs2| at feed 0 for the raw and stable\n"
        "  variants. A large rawΔ with a ~0 stblΔ is the raw coarse-mesh\n"
        "  ARTIFACT, not a benefit — only a persistent stblΔ is real. 'live' =\n"
        "  arms carrying ≥20% of the junction's largest arm current."
    )
    scored = [r for r in rows if r.get("shifts")]
    other = [r for r in rows if not r.get("shifts")]
    mf = meshes[-1]
    hdr = (
        f"\n{'design':32} {'deg':>3} {'#K3':>4} {'live':>4} "
        + "  ".join(f"raw@{n:>3} stbl@{n:>3}" for n in meshes)
        + "  split(top=1.0)"
    )
    print(hdr)
    print("-" * 96)
    for r in sorted(scored, key=lambda r: -_stable_at(r, mf)):
        cells = []
        for n in meshes:
            c = r["shifts"][n]
            cells.append(f"{_fmt(c.get('raw')):>7} {_fmt(c.get('stable')):>8}")
        split = str(r.get("split") or "")
        print(
            f"{r['design']:32} {r['maxdeg']:>3} {r['n_kge3']:>4} "
            f"{(r.get('live') if r.get('live') is not None else '?'):>4} "
            + "  ".join(cells)
            + f"  {split}"
        )

    skipped = [r for r in other if r.get("skip")]
    if skipped:
        print("\nSKIPPED (K≥3 present but not scored):")
        for r in skipped:
            print(f"  {r['design']:32} {r['skip']}")
    n_nojunc = sum(1 for r in other if not r.get("skip"))
    print(
        f"\n{len(scored)} K≥3 designs scored, {len(skipped)} skipped, "
        f"{n_nojunc} designs with no K≥3 junction (not shown)."
    )
    # headline verdict
    worst_stable = max((_stable_at(r, mf) for r in scored), default=0.0)
    print(
        f"\nLargest stable-variant driving-point shift across the catalog at "
        f"N={mf}: {worst_stable:.3f} Ω.\n"
        "A catalog-wide near-zero means bs2 already resolves every junction — "
        "no design\nbenefits from enrichment at the driving point (the raw "
        "column's large values are\ncoarse-mesh artifacts that wash out by "
        "N≈321; see the module docstring)."
    )


def _fmt(v):
    return f"{v:.3f}" if v is not None else "  ."


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--meshes", type=int, nargs="+", default=list(DEFAULT_MESHES))
    ap.add_argument("--only", nargs="+", help="restrict to these dotted designs")
    ap.add_argument("--mem-limit-gb", type=float, default=DEFAULT_MEM_GB)
    ap.add_argument("--out", type=Path, help="also write raw rows as JSON lines")
    args = ap.parse_args(argv)

    cap = int(args.mem_limit_gb * 1e9)
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))

    from antennaknobs.cli import list_builtin_designs

    meshes = sorted(set(args.meshes))
    designs = args.only or sorted(list_builtin_designs())
    rows = []
    out = args.out.open("w") if args.out else None
    for i, d in enumerate(designs, 1):
        print(f"[{i}/{len(designs)}] {d} ...", flush=True)
        row = scan_design(d, meshes)
        rows.append(row)
        if out:
            out.write(json.dumps(row) + "\n")
            out.flush()
    if out:
        out.close()
    print_report(rows, meshes)


if __name__ == "__main__":
    main()
