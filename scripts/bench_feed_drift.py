"""Feed-drift census (issue #459).

Sweeps every catalog design's driving-point impedance across a mesh ladder and
flags the ones that FAIL to converge because the feed sits at a mesh-unstable
point — a near-open (high-|Z|) delta-gap or a TL/NT attachment port. Refining
such a feed shrinks the driven segment, and the delta-gap readout at a current
null diverges as the gap closes (the classic NEC end-fed sensitivity); a
fixed-length driven segment is the mesh-stable model of that feed (issue #435
closed the general refine-with-the-mesh rule, and #459 tracks the exemptions).

The census exists to answer #459's open question 3 — "are there other latent
members?" — beyond the two already carrying pinned-count exemptions
(``wire/terminated_longwire``, ``wire/sterba_tl``). A design is a suspect when
its impedance is still moving at the finest mesh AND its feed is either
high-|Z| (near a current null) or a network port. Those two already pin their
feeds, so they should read CONVERGED here — their presence in the suspect list
would mean an exemption regressed.

Method: PyNEC, free space (the feed-segment sensitivity is a local delta-gap
effect, independent of ground), so the sweep stays cheap. Per design the ladder
is solved bottom-up; a rung whose nominal segment total exceeds ``--seg-cap`` is
skipped (recorded, not silently dropped) so the few benchmark-scale designs
don't dominate the runtime.

    python scripts/bench_feed_drift.py
    python scripts/bench_feed_drift.py --ladder 21 61 161 --seg-cap 4000
    python scripts/bench_feed_drift.py --engine sin
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_converge as bc  # noqa: E402 — sibling script, reused ladder machinery

DEFAULT_LADDER = (21, 61, 161)
DEFAULT_SEG_CAP = 3000
# |Z| this far above the 50 Ω reference reads as a near-open feed (near a
# current null), where the delta-gap readout is segment-length sensitive.
NEAR_OPEN_OHMS = 500.0
CONVERGE_TOL = 0.02


def feed_is_network_port(cls) -> bool:
    """True when a driven port also anchors a TL / NT / transformer branch —
    the port-segment-size sensitivity #459 question 2 is about (a plain lumped
    ``Load``/``Shunt`` on the feed does not count)."""
    from antennaknobs.network import TL, Admittance, TwoPort, Transformer

    try:
        b = cls()
        net = b.build_network() if hasattr(b, "build_network") else None
    except Exception:  # noqa: BLE001 — a design that can't build a network can't qualify
        return False
    if net is None:
        return False
    feed_ports = {s.port for s in net.sources}
    for br in net.branches:
        if not isinstance(br, (TL, Admittance, TwoPort, Transformer)):
            continue
        refs = set()
        for attr in ("a", "b", "port"):
            if hasattr(br, attr):
                refs.add(getattr(br, attr))
        if getattr(br, "ports", None):
            refs |= set(br.ports)
        if refs & feed_ports:
            return True
    return False


def census_row(design: str, ladder, engine: str, ground: str, seg_cap: int) -> dict:
    """Solve one design up the ladder; return its drift/convergence summary."""
    cls = bc.load_design(design)
    series, skipped = [], []
    for nseg in ladder:
        tot = bc.total_nominal_segs(cls, nseg)
        if tot > seg_cap:
            skipped.append(nseg)
            continue
        try:
            res = bc.solve_design(cls, nseg, engine, ground)
            series.append((nseg, complex(*res["z"][0])))
        except Exception as e:  # noqa: BLE001 — one dud design must not sink the census
            skipped.append(nseg)
            if not series:
                # keep the first error to explain a fully-empty row
                skipped_err = f"{type(e).__name__}: {e}"
                return {
                    "design": design,
                    "series": [],
                    "skipped": skipped,
                    "error": skipped_err,
                    "net_port": False,
                }
    net_port = feed_is_network_port(cls)
    row = {
        "design": design,
        "series": series,
        "skipped": skipped,
        "error": None,
        "net_port": net_port,
    }
    if len(series) >= 2:
        z_fin = series[-1][1]
        z_coarse = series[0][1]
        row["z_fine"] = z_fin
        row["drift"] = abs(z_fin - z_coarse) / (abs(z_fin) or 1.0)
        row["converged_at"] = bc.nseg_to_converge(series, tol=CONVERGE_TOL)
    return row


def is_suspect(row: dict) -> bool:
    """Still moving at the finest mesh AND fed at a mesh-unstable point."""
    if row.get("error") or "drift" not in row:
        return False
    if row["converged_at"] is not None:
        return False  # plateaued on this ladder — not a feed-drift member
    z = row["z_fine"]
    return abs(z) > NEAR_OPEN_OHMS or row["net_port"]


def print_report(rows, ladder, engine, ground, seg_cap):
    print(
        f"\nFEED-DRIFT CENSUS (issue #459)  engine={engine}  ground={ground}  "
        f"ladder={list(ladder)}  seg-cap={seg_cap}"
    )
    print(
        "  suspect = still moving at the finest mesh (>|ΔZ| "
        f"{CONVERGE_TOL:.0%} vs finest) AND feed is near-open (|Z|>"
        f"{NEAR_OPEN_OHMS:.0f}Ω) or a TL/NT port"
    )
    ranked = sorted(
        (r for r in rows if "drift" in r), key=lambda r: r["drift"], reverse=True
    )
    print(
        f"\n{'design':34} {'|Z_fine|':>9} {'drift':>7} {'conv@N':>7} {'port':>5}  flag"
    )
    print("-" * 78)
    for r in ranked:
        z = r["z_fine"]
        conv = r["converged_at"]
        flag = "◄ SUSPECT" if is_suspect(r) else ""
        print(
            f"{r['design']:34} {abs(z):9.0f} {r['drift'] * 100:6.1f}% "
            f"{(str(conv) if conv else '—'):>7} {('yes' if r['net_port'] else ''):>5}  {flag}"
        )
    suspects = [r for r in ranked if is_suspect(r)]
    print(f"\n{len(suspects)} suspect(s):")
    for r in suspects:
        z = r["z_fine"]
        why = []
        if abs(z) > NEAR_OPEN_OHMS:
            why.append(f"near-open |Z|={abs(z):.0f}Ω")
        if r["net_port"]:
            why.append("TL/NT port")
        print(f"  {r['design']:34} {', '.join(why)}")
    incomplete = [r for r in rows if r.get("error") or len(r["series"]) < 2]
    if incomplete:
        print(f"\n{len(incomplete)} design(s) with <2 usable rungs (skipped/errored):")
        for r in incomplete:
            note = r["error"] or f"skipped rungs {r['skipped']}"
            print(f"  {r['design']:34} {note}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ladder", type=int, nargs="+", default=list(DEFAULT_LADDER))
    ap.add_argument("--engine", default="pynec", choices=bc.ENGINE_KEYS)
    ap.add_argument("--ground", default="free")
    ap.add_argument("--seg-cap", type=int, default=DEFAULT_SEG_CAP)
    ap.add_argument("--only", nargs="+", help="restrict to these dotted designs")
    args = ap.parse_args(argv)

    from antennaknobs.cli import list_builtin_designs

    designs = args.only or list_builtin_designs()
    rows = []
    for i, d in enumerate(designs, 1):
        print(f"[{i}/{len(designs)}] {d} ...", flush=True)
        rows.append(census_row(d, args.ladder, args.engine, args.ground, args.seg_cap))
    print_report(rows, args.ladder, args.engine, args.ground, args.seg_cap)


if __name__ == "__main__":
    main()
