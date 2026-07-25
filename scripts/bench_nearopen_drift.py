"""Near-open high-Q convergence probe: bs2 vs sin vs PyNEC, Z and Y (issue #478).

The #478 near-open class (`docs/status/2026-07-20-feed-drift-census.md`) is the
set of very-high-|Z| designs whose driving-point impedance never plateaus on the
PyNEC convergence ladder — `wire.lazy_h`, `wire.vbeam`,
`arrays.delta_looparray_with_tls`. #478 asks whether that is inherent or whether
a remedy applies: a higher-order basis (bs2), or reporting admittance (small and
well-conditioned near an open) instead of impedance.

This tool answers both by solving each design up a ladder on **sin**, **bs2**,
and **PyNEC**, and reporting the convergence drift in **both impedance and
admittance**:

  * **Z-drift / Y-drift** — relative change of |Z| and |Y|=1/|Z| from the
    coarsest to the finest rung, plus the last-doubling step. If Y-drift ≪
    Z-drift, admittance reporting is the remedy; if they track, it is not (the
    error is in the current distribution and survives the reciprocal).
  * **basis comparison** — sin/PyNEC vs bs2 side by side. If bs2 drifts far less,
    the higher-order basis is the remedy; if it only shaves the drift, the
    slowness is inherent whole-structure mesh sensitivity, not a basis defect.
  * **PyNEC-vs-momwire divergence** — the two momwire bases (sin, bs2) cross-check
    PyNEC. A design where PyNEC swings wildly at isolated meshes while BOTH
    momwire bases sit flat is a PyNEC numerical artifact, not a real convergence
    problem (`delta_looparray_with_tls`: momwire stable at 55 Ω across the whole
    ladder, PyNEC spuriously spikes to ~−18 kΩ at N=61/81/161/241 — a NEC
    transmission-line internal resonance at unlucky segmentations).

2026-07-25 findings (issue #478 comment):
  * `delta_looparray_with_tls` is a **PyNEC artifact** — reclassify off the
    near-open list; momwire (both bases) is stable at 55 −3.5 j.
  * `lazy_h` / `vbeam` are genuine slow whole-structure convergence: bs2 shaves
    lazy_h's drift 16.7 %→12.1 % but does not resolve it, and admittance
    reporting does not help (Y-drift ≈ Z-drift; |Z| ~3.5–5 kΩ is finite, not a
    true near-open). Neither listed remedy applies — label as expected.

    python scripts/bench_nearopen_drift.py
    python scripts/bench_nearopen_drift.py --only wire.lazy_h --ladder 21 41 81 161 321 641
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")

import argparse  # noqa: E402
import json  # noqa: E402
import resource  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_converge as bc  # noqa: E402 — load_design / solve_design

# The #478 near-open suspects, from the feed-drift census.
DEFAULT_DESIGNS = (
    "wire.lazy_h",
    "wire.vbeam",
    "arrays.delta_looparray_with_tls",
)
DEFAULT_LADDER = (21, 41, 81, 161, 321)
DEFAULT_MEM_GB = 8.0
ENGINES = ("sin", "bs2", "pynec")


def solve_z(builder_cls, nseg, engine):
    """Feed-0 complex Z for one basis, free space. PyNEC goes through its own
    engine (bench_converge.solve_design routes it too, but calling it directly
    keeps the momwire/pynec split explicit)."""
    if engine == "pynec":
        from antennaknobs.engines.pynec import PyNECEngine

        b = builder_cls()
        b.nominal_nsegs = nseg
        return complex(PyNECEngine(b, ground=None).impedance()[0])
    return complex(*bc.solve_design(builder_cls, nseg, engine, "free")["z"][0])


def drift(vals):
    """(full, step) relative drift of a complex sequence: |last−first|/|last|
    and |last−prev|/|last|, using COMPLEX differences so a change in either R or
    X counts (a design whose |Z| holds while R↔X swap is still not converged).
    Feeding ``[1/z ...]`` gives the admittance drift."""
    denom = abs(vals[-1]) or 1.0
    full = abs(vals[-1] - vals[0]) / denom
    step = abs(vals[-1] - vals[-2]) / denom
    return full, step


def probe_row(design, ladder):
    """Solve one design up the ladder on every basis; record Z per rung. Never
    raises — a dud rung is recorded as null."""
    row = {"design": design, "series": {e: [] for e in ENGINES}, "error": None}
    try:
        cls = bc.load_design(design)
    except Exception as e:  # noqa: BLE001
        row["error"] = f"load: {type(e).__name__}: {e}"
        return row
    for nseg in ladder:
        for e in ENGINES:
            try:
                z = solve_z(cls, nseg, e)
                row["series"][e].append([nseg, z.real, z.imag])
            except MemoryError:
                row["series"][e].append([nseg, None, None])
            except Exception:  # noqa: BLE001 — one dud rung must not sink the sweep
                row["series"][e].append([nseg, None, None])
    return row


def _zlist(series):
    return [complex(re, im) for _n, re, im in series if re is not None]


def print_report(rows, ladder):
    for row in rows:
        print("\n" + "=" * 84)
        print(f"NEAR-OPEN DRIFT — {row['design']}   (issue #478, free space)")
        print("=" * 84)
        if row.get("error"):
            print(f"  {row['error']}")
            continue

        # per-mesh |Z| table across bases, to expose PyNEC-vs-momwire divergence
        print(f"{'N':>5} " + " ".join(f"{e + '_|Z|':>12}" for e in ENGINES))
        by_n = {}
        for e in ENGINES:
            for n, re, im in row["series"][e]:
                by_n.setdefault(n, {})[e] = None if re is None else complex(re, im)
        for n in ladder:
            cells = []
            for e in ENGINES:
                z = by_n.get(n, {}).get(e)
                cells.append(f"{abs(z):12.1f}" if z is not None else f"{'--':>12}")
            print(f"{n:>5} " + " ".join(cells))

        # Z and Y drift per basis
        print(f"\n  {'basis':>6} {'Zdrift':>8} {'Zstep':>7} {'Ydrift':>8} {'Ystep':>7}")
        for e in ENGINES:
            zs = _zlist(row["series"][e])
            if len(zs) < 2:
                print(f"  {e:>6}   insufficient rungs")
                continue
            zf, zst = drift(zs)
            yf, yst = drift([1 / z for z in zs])
            print(
                f"  {e:>6} {zf * 100:7.1f}% {zst * 100:6.1f}% "
                f"{yf * 100:7.1f}% {yst * 100:6.1f}%"
            )

        # artifact / remedy read
        sin_z = _zlist(row["series"]["sin"])
        bs2_z = _zlist(row["series"]["bs2"])
        pyn_z = _zlist(row["series"]["pynec"])
        notes = []
        if sin_z and bs2_z and pyn_z:
            # momwire bases agree tightly but PyNEC swings → PyNEC artifact
            mw_spread = max(abs(a - b) / (abs(b) or 1) for a, b in zip(sin_z, bs2_z))
            pyn_vs_mw = max(abs(p - s) / (abs(s) or 1) for p, s in zip(pyn_z, sin_z))
            if mw_spread < 0.05 and pyn_vs_mw > 0.5:
                notes.append(
                    "PyNEC swings hard where BOTH momwire bases sit flat → likely "
                    "a PyNEC numerical artifact, not a real convergence problem."
                )
            zf_bs2, _ = drift(bs2_z)
            zf_sin, _ = drift(sin_z)
            if zf_sin > 0.02 and zf_bs2 > 0.5 * zf_sin:
                notes.append(
                    "bs2 only shaves the drift (not << sin) → inherent "
                    "whole-structure slowness, not a basis defect."
                )
            yf_bs2, _ = drift([1 / z for z in bs2_z])
            if zf_bs2 > 0.02 and yf_bs2 > 0.5 * zf_bs2:
                notes.append(
                    "Y-drift ≈ Z-drift → admittance reporting does not recondition "
                    "this (error is in the current, not the reciprocal)."
                )
        for n in notes:
            print(f"\n  * {n}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="+", help="restrict to these dotted designs")
    ap.add_argument("--ladder", type=int, nargs="+", default=list(DEFAULT_LADDER))
    ap.add_argument("--mem-limit-gb", type=float, default=DEFAULT_MEM_GB)
    ap.add_argument("--out", type=Path, help="also write raw rows as JSON lines")
    args = ap.parse_args(argv)

    cap = int(args.mem_limit_gb * 1e9)
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))

    designs = args.only or list(DEFAULT_DESIGNS)
    ladder = sorted(set(args.ladder))
    print(f"designs: {', '.join(designs)}   ladder: {ladder}   engines: sin/bs2/pynec")

    rows = []
    out = args.out.open("w") if args.out else None
    for i, d in enumerate(designs, 1):
        print(f"[{i}/{len(designs)}] {d} ...", flush=True)
        row = probe_row(d, ladder)
        rows.append(row)
        if out:
            out.write(json.dumps(row) + "\n")
            out.flush()
    if out:
        out.close()
    print_report(rows, ladder)


if __name__ == "__main__":
    main()
