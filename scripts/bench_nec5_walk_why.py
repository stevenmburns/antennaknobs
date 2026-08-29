"""Why NEC-5 needs Richardson pairs (#890): harness or formulation?

The #872 study made (N, 2N) pair extrapolation the census-grade NEC-5
recipe without establishing WHY the raw ladder walks ~O(1/N). A clean
first-order systematic is exactly what a half-segment harness offset
would produce (feeding or reading the source half a segment wrong), so
this instrument discriminates the harness-side hypotheses of #890 before
the walk may be pronounced intrinsic:

A. **Same-knot spelling (H1)** — every probe deck × rung solved with the
   engine's spelling (end 2 of segment N/2) and the same physical knot
   from the other side (end 1 of segment N/2+1). Any split is a spelling
   artifact; phase 1 saw bit-identity on one wire, this extends it to
   the three named decks.
B. **Feed-slide dZ/dknot (H1)** — the feed knot deliberately slid one
   segment off-center. |Z(slide) − Z(base)| sizes what a half-segment
   placement bias could possibly produce; compared per rung against the
   observed walk residual |Z(N) − Z∞|. A walk ≫ the slide term cannot be
   a placement offset.
C. **EX 0 vs EX 4 (H2)** — the same gap driven as a voltage source and
   as NEC-5's native current source. If the two walk differently raw but
   extrapolate together, the walk lives in the gap/readout construction;
   if they walk in lockstep, it is the discretization itself.
D. **AIP readout convention (H2)** — the ANTENNA INPUT PARAMETERS row's
   V, I, Z cross-checked against the Wire Currents table at the feed:
   is the row's I the fed knot's current, one adjacent segment-center
   current, or their mean — and does Z = V/I hold within print precision?
E. **Matched geometry (H3)** — per-wire segment counts actually solved
   on the hentenna ladder (nominal vs NEC-5's even coercion vs bs2's odd
   coercion), plus bs2 re-solved at neighboring counts to bound what a
   ±1-count mismatch can move — geometry endpoints are identical by
   construction (coercion touches only n_seg).
F. **Sample-deck reproduction (H4)** — the LLNL-shipped sample decks run
   through ``NEC5Engine._run`` (our stdin/tempdir protocol) and their
   ANTENNA INPUT PARAMETERS compared row-by-row against the shipped
   reference printouts, both sides read by the engine's own parser.
   Exact reproduction exonerates the runner+parser end-to-end.

Probe decks (the #890 acceptance set): a thin 5 m dipole in free space
(analytic anchor class), the specialty.hentenna phase-2 deck, and the
phase-3a low-height Sommerfeld dipole (0.048 λ over ("finite", 13, .005)).

Requires $NEC5_EXE (or --nec5-exe). NEC-5 printouts ride the capture
cache (End-User Reports, LLNL-CODE-746721).

    python scripts/bench_nec5_walk_why.py --out scratch/nec5-walk-why-890.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_converge as bc  # design loading

FREQ = 28.5  # MHz (dipole probes)
HALF = 2.5  # dipole half-length, m
RADIUS = 0.0005
LAM = 299.792458 / FREQ
GROUND = ("finite", 13.0, 0.005)
H_SOMM = 0.048 * LAM

DIPOLE_LADDER = (20, 40, 80, 160, 320)
HENTENNA_LADDER = (21, 41, 81, 161)

SAMPLE_DIR = Path("~/antennas/NEC5-downloads/NEC-5 2/Sample Data").expanduser()
SAMPLES = (
    ("LP12", "LP12.dat", "LP12.OUT"),
    ("BoxWhip", "BoxWhip.dat", "BoxWhip.OUT"),
    ("HLoopBoxPEC", "HLoopBoxPEC.dat", "HLoopBoxPEC.OUT"),
    ("Outbackf7", "Outback Model/Outbackf7.dat", "Outback Model/Outbackf7.out"),
    ("Outbackf30", "Outback Model/Outbackf30.dat", "Outback Model/Outbackf30.out"),
    ("Outbackf7G", "Outback Model/Outbackf7G.dat", "Outback Model/Outbackf7G.out"),
    ("Outbackf30G", "Outback Model/Outbackf30G.dat", "Outback Model/Outbackf30G.out"),
)

_EX_RE = re.compile(r"(?m)^EX (\d) (\d+) (\d+) 2 (\S+) (\S+)$")


def make_dipole(n: int, ground=None, h: float = 10.0):
    from antennaknobs.builder import AntennaBuilder
    from antennaknobs.network import Wire

    class Dipole(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wires(self):
            return [Wire((0, -HALF, h), (0, HALF, h), n_seg=n, ex=1 + 0j)]

    return Dipole()


def make_hentenna(nseg: int):
    b = bc.load_design("specialty.hentenna")()
    b.nominal_nsegs = nseg
    return b


def zc(z: complex) -> list[float]:
    return [z.real, z.imag]


def fmt(z: complex) -> str:
    return f"{z.real:9.3f}{z.imag:+9.3f}j"


def richardson(series):
    """[(N, Z), ...] ascending, len >= 3 -> observed order + Z∞ from the
    finest three rungs (actual N ratios, as bench_nec5_convergence)."""
    if len(series) < 3:
        return {}
    (n1, z1), (n2, z2), (n3, z3) = series[-3:]
    d1, d2 = z2 - z1, z3 - z2
    if abs(d2) == 0 or abs(d1) == 0:
        return {"order": None, "zinf": z3}
    ratio = abs(d1) / abs(d2)
    if ratio <= 1.0:
        return {"order": None, "zinf": z3, "non_contracting": True}
    p = math.log(ratio) / math.log(n3 / n2)
    return {"order": p, "zinf": z3 + d2 / (ratio - 1)}


class ProbeCase:
    """One probe deck family: engine per rung + EX-line mutations."""

    def __init__(self, name, ladder, make_builder, ground=None):
        self.name = name
        self.ladder = ladder
        self.make_builder = make_builder
        self.ground = ground

    def engine(self, nseg, exe, capture_dir):
        from antennaknobs.engines.nec5 import NEC5Engine

        return NEC5Engine(
            self.make_builder(nseg),
            ground=self.ground,
            nec5_exe=exe,
            capture_dir=capture_dir,
        )


def ex_variants(eng) -> dict[str, str]:
    """The base deck and its EX-line mutations. The engine spells the
    single source as end 2 of segment s = n//2 of the fed wire; every
    variant re-addresses the SAME deck text so geometry, ground and
    frequency stay bit-identical."""
    deck = eng.deck([eng.builder.freq])
    m = _EX_RE.search(deck)
    if m is None:
        raise RuntimeError(f"no engine-spelled EX line in deck:\n{deck}")
    ex_type, tag, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    vre, vim = m.group(4), m.group(5)

    def with_ex(line):
        return _EX_RE.sub(line, deck)

    out = {
        "base": deck,  # end 2 of seg s  = knot s
        "end1": with_ex(f"EX {ex_type} {tag} {s + 1} 1 {vre} {vim}"),  # same knot
        "ex4": with_ex(f"EX 4 {tag} {s} 2 {vre} {vim}"),  # current source, same knot
    }
    if s >= 2:
        out["slide"] = with_ex(f"EX {ex_type} {tag} {s - 1} 2 {vre} {vim}")  # knot s-1
    return out, (tag, s)


def first_z(eng, deck) -> complex:
    return eng.run_deck(deck)[0][0][2]


def parse_aip_full(text):
    """First AIP row as (tag, seg, V, I, Z, P) — the 12-token layout
    tag seg sub Vre Vim Ire Iim Zre Zim Yre Yim P."""
    chunk = text.split("ANTENNA INPUT PARAMETERS")[1]
    for line in chunk.splitlines():
        toks = line.split()
        if len(toks) != 12:
            continue
        try:
            tag, seg = int(toks[0]), int(toks[1])
            v = complex(float(toks[3]), float(toks[4]))
            i = complex(float(toks[5]), float(toks[6]))
            z = complex(float(toks[7]), float(toks[8]))
            p = float(toks[11])
        except ValueError:
            continue
        return tag, seg, v, i, z, p
    raise RuntimeError("no parseable AIP row")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--nec5-exe", default=None)
    ap.add_argument(
        "--nec5-capture-dir",
        type=Path,
        default=Path.home() / ".antennaknobs" / "nec5-captures",
    )
    ap.add_argument("--sample-dir", type=Path, default=SAMPLE_DIR)
    ap.add_argument("--skip-samples", action="store_true")
    args = ap.parse_args(argv)

    from antennaknobs.engines.nec5 import NEC5Engine, find_nec5

    exe = find_nec5(args.nec5_exe)
    if exe is None:
        sys.exit("--nec5-exe / $NEC5_EXE does not resolve to an executable")

    cases = [
        ProbeCase("dipole_free", DIPOLE_LADDER, make_dipole),
        ProbeCase("hentenna", HENTENNA_LADDER, make_hentenna),
        ProbeCase(
            "dipole_somm_0.048",
            DIPOLE_LADDER[:-1],
            lambda n: make_dipole(n, h=H_SOMM),
            ground=GROUND,
        ),
    ]
    results = {"cases": {}, "readout": {}, "geometry": {}, "samples": {}}

    # ---------------- A/B/C: the EX probes ----------------
    for case in cases:
        print("=" * 96)
        print(f"CASE {case.name} — same-knot spelling / feed slide / EX0-vs-EX4")
        print("=" * 96)
        print(
            f"  {'N':>4} {'Z base (end2)':>20} {'|end1-end2|':>12}"
            f" {'|slide-base|':>13} {'Z ex4':>20} {'|ex4-base|':>11}"
        )
        rows = []
        base_series, ex4_series = [], []
        for nseg in case.ladder:
            eng = case.engine(nseg, exe, args.nec5_capture_dir)
            decks, (tag, s) = ex_variants(eng)
            z = {k: first_z(eng, d) for k, d in decks.items()}
            base_series.append((eng._wires[eng._sources[0][0]].n_seg, z["base"]))
            ex4_series.append((base_series[-1][0], z["ex4"]))
            row = {
                "nominal": nseg,
                "fed_wire_nseg": base_series[-1][0],
                "tag": tag,
                "seg": s,
                "z": {k: zc(v) for k, v in z.items()},
                "d_end1": abs(z["end1"] - z["base"]),
                "d_ex4": abs(z["ex4"] - z["base"]),
                "d_slide": abs(z["slide"] - z["base"]) if "slide" in z else None,
            }
            rows.append(row)
            slide_s = (
                f"{row['d_slide']:>12.4f}Ω"
                if row["d_slide"] is not None
                else (f"{'—':>13}")
            )
            print(
                f"  {nseg:>4} {fmt(z['base']):>20} {row['d_end1']:>11.2e}"
                f" {slide_s} {fmt(z['ex4']):>20} {row['d_ex4']:>10.4f}Ω"
            )
        rich = richardson(base_series)
        rich4 = richardson(ex4_series)
        zinf = rich.get("zinf")
        print(
            f"  EX0 Richardson: order {rich.get('order', float('nan')):.2f}"
            f"  Z∞ {fmt(zinf)}"
        )
        if rich4.get("zinf") is not None:
            print(
                f"  EX4 Richardson: order {rich4.get('order') or float('nan'):.2f}"
                f"  Z∞ {fmt(rich4['zinf'])}"
                f"  |Z∞ ex4 - Z∞ ex0| = {abs(rich4['zinf'] - zinf):.4f}Ω"
            )
        # Walk residual vs the slide bound, per rung.
        print(f"  {'N':>4} {'walk |Z(N)-Z∞|':>15} {'slide bound /2':>15}")
        for row, (_, zb) in zip(rows, base_series):
            walk = abs(zb - zinf)
            row["walk_residual"] = walk
            bound = row["d_slide"] / 2 if row["d_slide"] is not None else None
            bs = f"{bound:>14.4f}Ω" if bound is not None else f"{'—':>15}"
            print(f"  {row['nominal']:>4} {walk:>14.4f}Ω {bs}")
        results["cases"][case.name] = {
            "ladder": rows,
            "richardson_ex0": {
                "order": rich.get("order"),
                "zinf": zc(rich["zinf"]),
            },
            "richardson_ex4": {
                "order": rich4.get("order"),
                "zinf": zc(rich4["zinf"]) if rich4.get("zinf") is not None else None,
            },
        }

        # ------------- D: AIP readout convention (finest rung) -------------
        eng = case.engine(case.ladder[-1], exe, args.nec5_capture_dir)
        decks, (tag, s) = ex_variants(eng)
        text = eng._run(decks["base"])
        _tag, _seg, v, i, z, p = parse_aip_full(text)
        per_tag = NEC5Engine._parse_wire_currents(text)[0]
        cur = per_tag[tag]
        lo, hi = cur[s - 1], cur[s]  # segment-center currents flanking the knot
        knot = 0.5 * (lo + hi)
        cand = {"seg_lo_center": lo, "seg_hi_center": hi, "knot_mean": knot}
        print("  READOUT (finest rung): AIP row vs Wire Currents at the fed knot")
        print(f"    AIP: V={fmt(v)}  I={i.real:+.5e}{i.imag:+.5e}j  Z={fmt(z)}")
        print(f"    Z - V/I = {abs(z - v / i):.3e} Ω (row-internal consistency)")
        for k, c in cand.items():
            print(
                f"    AIP I vs {k:<14}: |ΔI|/|I| = {abs(i - c) / abs(i):.4e}"
                f"   V/{k} = {fmt(v / c)}"
            )
        results["readout"][case.name] = {
            "aip": {"v": zc(v), "i": zc(i), "z": zc(z), "p": p},
            "z_minus_v_over_i": abs(z - v / i),
            "candidates": {
                k: {"i": zc(c), "rel_dI": abs(i - c) / abs(i)} for k, c in cand.items()
            },
        }

    # ------- D2: readout discriminators the symmetric feeds can't give -------
    # At a center feed the two flanking segment-center currents are equal by
    # symmetry, so section D cannot tell knot from center from mean. Two
    # sharper probes on the free dipole at N=80: (a) EX 4 genuineness — the
    # AIP row must carry I = 1 A exactly (then V is read against a KNOWN
    # current, no readout convention involved, and its Z still equals EX 0's);
    # (b) an asymmetric feed at knot 0.25L, where the flanking centers differ
    # by O(Δ)·dI/ds and the AIP I's identity is visible.
    print("=" * 96)
    print("D2. READOUT DISCRIMINATORS — EX4 genuineness + asymmetric-feed AIP I")
    print("=" * 96)
    eng = cases[0].engine(80, exe, args.nec5_capture_dir)
    deck = eng.deck([eng.builder.freq])
    t4 = eng._run(deck.replace("EX 0 1 40 2", "EX 4 1 40 2"))
    _t, _s, v4, i4, z4, _p = parse_aip_full(t4)
    z0 = first_z(eng, deck)
    print(
        f"  EX4 @ center knot: I = {i4}  V = {fmt(v4)}  Z = {fmt(z4)}"
        f"  |Z - Z_ex0| = {abs(z4 - z0):.3e} Ω"
    )
    ta = eng._run(deck.replace("EX 0 1 40 2", "EX 0 1 20 2"))
    _t, _s, va, ia, za, _p = parse_aip_full(ta)
    cur = NEC5Engine._parse_wire_currents(ta)[0][1]
    lo, hi = cur[19], cur[20]
    asym = {"seg_lo_center": lo, "seg_hi_center": hi, "knot_mean": 0.5 * (lo + hi)}
    print(
        f"  EX0 @ knot 0.25L (N=80): Z = {fmt(za)}  Z - V/I = {abs(za - va / ia):.3e} Ω"
    )
    for k, c in asym.items():
        print(f"    AIP I vs {k:<14}: |ΔI|/|I| = {abs(ia - c) / abs(ia):.4e}")
    results["readout"]["discriminators"] = {
        "ex4_i": zc(i4),
        "ex4_z_minus_ex0_z": abs(z4 - z0),
        "asym_z_minus_v_over_i": abs(za - va / ia),
        "asym_candidates": {
            k: {"rel_dI": abs(ia - c) / abs(ia)} for k, c in asym.items()
        },
    }

    # ---------------- E: matched geometry (hentenna) ----------------
    print("=" * 96)
    print("E. MATCHED GEOMETRY — hentenna per-wire counts actually solved")
    print("=" * 96)
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.network import as_wire
    from momwire import BSplineSolver

    geo_rows = []
    for nseg in HENTENNA_LADDER:
        b = make_hentenna(nseg)
        nominal = [as_wire(t).n_seg for t in b.build_wires()]
        eng5 = cases[1].engine(nseg, exe, args.nec5_capture_dir)
        nec5_counts = [as_wire(t).n_seg for t in eng5.tups]
        bs2 = MomwireEngine(
            make_hentenna(nseg), solver=BSplineSolver, solver_kwargs={"degree": 2}
        )
        bs2_counts = [
            as_wire(t).n_seg
            for t in bs2._coerce_wire_tuples(make_hentenna(nseg).build_wires())
        ]
        geo_rows.append(
            {
                "nominal_nsegs": nseg,
                "per_wire_nominal": nominal,
                "per_wire_nec5": nec5_counts,
                "per_wire_bs2": bs2_counts,
            }
        )
        d5 = sum(a != b_ for a, b_ in zip(nominal, nec5_counts))
        d2 = sum(a != b_ for a, b_ in zip(nominal, bs2_counts))
        print(
            f"  nominal {nseg:>4}: total {sum(nominal)}"
            f"  nec5 shifts {d5} wire(s) -> {sum(nec5_counts)}"
            f"  bs2 shifts {d2} wire(s) -> {sum(bs2_counts)}"
        )
    # Bound the ±1-count term: bs2 at neighboring nominal meshes around the
    # finest rung — the walk NEC-5 shows per rung dwarfs this or not.
    n_fine = HENTENNA_LADDER[-1]
    z_pairs = {}
    for dn in (0, 2):
        e = MomwireEngine(
            make_hentenna(n_fine + dn),
            solver=BSplineSolver,
            solver_kwargs={"degree": 2},
        )
        z_pairs[n_fine + dn] = e.impedance()[0]
    (na, za), (nb, zb) = sorted(z_pairs.items())
    print(
        f"  bs2 count-sensitivity at census mesh: |Z({nb})-Z({na})|"
        f" = {abs(zb - za):.4f} Ω  ({fmt(za)} vs {fmt(zb)})"
    )
    results["geometry"] = {
        "rows": geo_rows,
        "bs2_count_sensitivity": {
            "n": [na, nb],
            "z": [zc(za), zc(zb)],
            "dz": abs(zb - za),
        },
    }

    # ---------------- F: sample-deck reproduction ----------------
    if not args.skip_samples:
        print("=" * 96)
        print("F. LLNL SAMPLE DECKS through NEC5Engine._run vs shipped reference")
        print("=" * 96)
        eng = ProbeCase("runner", (20,), make_dipole).engine(
            20, exe, args.nec5_capture_dir
        )
        eng._timeout = 600.0
        for name, dat, ref in SAMPLES:
            dat_p, ref_p = args.sample_dir / dat, args.sample_dir / ref
            entry = {"deck": str(dat_p)}
            try:
                deck = dat_p.read_text(errors="replace").replace("\r\n", "\n")
                ours = NEC5Engine._parse_input_parameters(eng._run(deck))
                theirs = NEC5Engine._parse_input_parameters(
                    ref_p.read_text(errors="replace")
                )
                if [len(r) for r in ours] != [len(r) for r in theirs]:
                    raise RuntimeError(
                        f"AIP shape mismatch: ours {[len(r) for r in ours]}"
                        f" vs ref {[len(r) for r in theirs]}"
                    )
                worst = 0.0
                worst_rel = 0.0
                n_rows = 0
                for fo, ft in zip(ours, theirs):
                    for (tg, sg, zo), (tg2, sg2, zt) in zip(fo, ft):
                        if (tg, sg) != (tg2, sg2):
                            raise RuntimeError(
                                f"row addressing mismatch {(tg, sg)} vs {(tg2, sg2)}"
                            )
                        n_rows += 1
                        worst = max(worst, abs(zo - zt))
                        worst_rel = max(worst_rel, abs(zo - zt) / max(abs(zt), 1e-30))
                entry.update({"rows": n_rows, "max_dz": worst, "max_rel": worst_rel})
                print(
                    f"  {name:<12} {n_rows:>3} AIP rows"
                    f"  max|ΔZ| = {worst:.3e} Ω  max rel = {worst_rel:.3e}"
                )
            except Exception as e:  # noqa: BLE001 — record and continue
                entry["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                print(f"  {name:<12} ERROR: {entry['error']}")
            results["samples"][name] = entry

    if args.out:
        args.out.write_text(json.dumps(results, indent=1))
        print(f"\nfull results -> {args.out}")


if __name__ == "__main__":
    main()
