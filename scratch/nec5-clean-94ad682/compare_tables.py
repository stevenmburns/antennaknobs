"""Compare two NEC-5 printouts' RP / NE / NH tables under the clean room's rule.

    python scratch/nec5-clean-94ad682/compare_tables.py <dir_a> <dir_b> [--tol 1e-9]

NOT BYTE IDENTITY, and that is the clean room's own correction (REPORT-2026-09-12):
the unit-2 build's printouts are byte-identical between 1 and 4 threads on only 5
of the 10 study decks, and on the other five the ONLY rows that differ are the
analytically-zero ones -- theta = 90 deg over lossy ground, where the program
prints its -999.99 gain floor -- by at most 1.6e-9 of the row's own maximum and
1.5e-15 of the table maximum, deterministically for a given thread count. A byte
gate would report five known floor-row artefacts as regressions.

The rule, per the room:

  * table maximum = the largest field magnitude anywhere in that table; the FLOOR
    is 1e-6 of it.
  * field MAGNITUDES are compared relative to their own ROW's maximum.
  * PHASES only where that component's magnitude is above the floor -- a phase on
    a null is not a number -- scaled by 360 deg so the tolerance means the same
    thing it does for a magnitude.
  * dB GAINS only above -80 dB, which excludes the -999.99 floor rows without
    excusing anything real.
  * pass at 1e-9.

TWO STREAMING PASSES, NOT ONE IN MEMORY. `6mYagi-Onec.out` is **618 MB** --
41 frequencies x 130,321 pattern points -- and a version of this script that
built Python lists of the rows would need many GB and be killed rather than
answer. So pass 1 streams both files to get each table's maximum (the floor
cannot be known before the table is read), and pass 2 streams them again to
compare; memory stays flat in the number of TABLES, not rows.

IMPEDANCE ROWS ARE A SEPARATE, STRICTER GATE and are not touched here: unit 2
leaves the solve alone, so ANTENNA INPUT PARAMETERS must be byte-identical, and
`compare_impedance.py`'s job is to say so.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HEADERS = (
    ("- - - RADIATION PATTERNS - - -", "RP"),
    ("- - - NEAR ELECTRIC FIELDS - - -", "NE"),
    ("- - - NEAR MAGNETIC FIELDS - - -", "NH"),
)
NUMTOK = re.compile(r"^[-+]?(?:\d+\.?\d*|\.\d+)(?:[Ee][-+]?\d+)?$")

# Column indices AFTER dropping non-numeric tokens. An RP row is 12
# whitespace-separated fields of which ONE -- the polarization SENSE word
# (LINEAR / RIGHT / LEFT) -- is not a number, so the numeric width is 11:
#
#   0 THETA  1 PHI | 2 VERT dB  3 HOR dB  4 TOTAL dB | 5 AXIAL  6 TILT
#   7 E(THETA) mag  8 phase | 9 E(PHI) mag  10 phase
#
# The first version of this file said 12 and indexed the magnitudes at 8 and 10,
# which is the PHASE pair, and rejected every row for being one token short. It
# then reported PASS on 40 rows of a 5.3-million-row deck. Hence `WIDTH` below
# and the skipped-line count in the per-deck output: a layout that does not
# match is now a number on the report rather than silence.
COLS = {
    "RP": {"mag": (7, 9), "phase": (8, 10), "db": (2, 3, 4)},
    # X Y Z | EX mag,phase | EY mag,phase | EZ mag,phase
    "NE": {"mag": (3, 5, 7), "phase": (4, 6, 8), "db": ()},
    "NH": {"mag": (3, 5, 7), "phase": (4, 6, 8), "db": ()},
}
WIDTH = {"RP": 11, "NE": 9, "NH": 9}
MINTOK = WIDTH


def _row(line: str, kind: str) -> list[float] | None:
    toks = [t for t in line.split() if NUMTOK.match(t)]
    if len(toks) < MINTOK[kind]:
        return None
    try:
        return [float(t) for t in toks]
    except ValueError:
        return None


def stream(path: Path, skipped: dict | None = None):
    """Yield ('table', kind, index) then ('row', kind, index, values).

    `skipped` counts lines INSIDE a table that carried numbers but not the
    expected width -- the signal that the column layout moved.
    """
    kind = None
    idx = -1
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            hit = None
            for header, k in HEADERS:
                if header in line:
                    hit = k
                    break
            if hit:
                kind = hit
                idx += 1
                yield ("table", kind, idx)
                continue
            if kind is None:
                continue
            r = _row(line, kind)
            if r is not None:
                yield ("row", kind, idx, r)
            elif skipped is not None:
                n = sum(1 for tk in line.split() if NUMTOK.match(tk))
                if n >= 4:  # numbers, but not this table's width
                    skipped[kind] = skipped.get(kind, 0) + 1


def pass1(pa: Path, pb: Path) -> dict[int, float]:
    """Per-table maximum field magnitude, over BOTH sides."""
    tmax: dict[int, float] = {}
    for p in (pa, pb):
        for ev in stream(p):
            if ev[0] != "row":
                continue
            _t, kind, idx, r = ev
            m = max((abs(r[i]) for i in COLS[kind]["mag"] if i < len(r)), default=0.0)
            if m > tmax.get(idx, 0.0):
                tmax[idx] = m
    return tmax


def compare(pa: Path, pb: Path, tol: float) -> dict:
    tmax = pass1(pa, pb)
    skipped: dict[str, int] = {}
    agg = {
        "tables_a": 0,
        "tables_b": 0,
        "rows": 0,
        "worst_mag": 0.0,
        "worst_phase": 0.0,
        "worst_db": 0.0,
        "mag_fail": 0,
        "phase_fail": 0,
        "db_fail": 0,
        "phase_skipped": 0,
        "db_skipped": 0,
        "where": "",
        "misaligned": 0,
        "below_floor": 0,
    }
    ga, gb = stream(pa, skipped), stream(pb)
    for ea, eb in zip(ga, gb, strict=False):
        if ea[0] != eb[0] or ea[1] != eb[1] or ea[2] != eb[2]:
            agg["misaligned"] += 1
            break
        if ea[0] == "table":
            agg["tables_a"] += 1
            agg["tables_b"] += 1
            continue
        _t, kind, idx, ra = ea
        rb = eb[3]
        cols = COLS[kind]
        floor = 1e-6 * tmax.get(idx, 0.0)
        rmax = max(
            max((abs(ra[i]) for i in cols["mag"] if i < len(ra)), default=0.0),
            max((abs(rb[i]) for i in cols["mag"] if i < len(rb)), default=0.0),
        )
        scale = rmax if rmax > 0 else 1.0
        agg["rows"] += 1
        # THE FLOOR GATES THE MAGNITUDES TOO, not only the phases. A row whose
        # own maximum is under 1e-6 of the table maximum carries no field: the
        # theta = 90 rows over lossy ground sit at ~1e-16 V against a table
        # maximum of ~3e-3, i.e. 1.4e-14 of it, and NEC-5 prints its -999.99 dB
        # floor on them. Comparing them relative to their OWN maximum turns
        # 4.7e-17 against 4.74e-17 into "4.9e-04, FAIL" -- which is how this
        # script first reported 215 failures on a deck the clean room measured
        # as clean. Reading the rule as "below the floor, do not compare" is
        # what reproduces the room's own figures.
        if rmax <= floor:
            agg["below_floor"] += 1
            continue
        for i in cols["mag"]:
            if i >= len(ra) or i >= len(rb):
                continue
            d = abs(ra[i] - rb[i]) / scale
            if d > agg["worst_mag"]:
                agg["worst_mag"] = d
                agg["where"] = f"{kind} table {idx} row {agg['rows']} col {i} (mag)"
            if d > tol:
                agg["mag_fail"] += 1
        for mi, pi in zip(cols["mag"], cols["phase"], strict=False):
            if pi >= len(ra) or pi >= len(rb):
                continue
            if max(abs(ra[mi]), abs(rb[mi])) <= floor:
                agg["phase_skipped"] += 1
                continue
            d = abs(ra[pi] - rb[pi]) / 360.0
            agg["worst_phase"] = max(agg["worst_phase"], d)
            if d > tol:
                agg["phase_fail"] += 1
        for i in cols["db"]:
            if i >= len(ra) or i >= len(rb):
                continue
            if max(ra[i], rb[i]) <= -80.0:
                agg["db_skipped"] += 1
                continue
            d = abs(ra[i] - rb[i])
            agg["worst_db"] = max(agg["worst_db"], d)
            if d > tol:
                agg["db_fail"] += 1
    # drain: a length difference is a finding, not a crash
    agg["skipped_lines"] = sum(skipped.values())
    agg["tables_a"] += sum(1 for e in ga if e[0] == "table")
    agg["tables_b"] += sum(1 for e in gb if e[0] == "table")
    return agg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir_a")
    ap.add_argument("dir_b")
    ap.add_argument("--tol", type=float, default=1e-9)
    ap.add_argument("--only", default=None)
    a = ap.parse_args(argv)
    A, B = Path(a.dir_a), Path(a.dir_b)
    decks = sorted(p.stem for p in A.glob("*.out") if (B / p.name).is_file())
    if a.only:
        decks = [d for d in decks if a.only in d]
    print(f"{A.name} vs {B.name}, tol {a.tol:g}\n")
    hdr = (
        f"{'deck':28s} {'rows':>9s} {'worst mag':>11s} {'worst ph':>10s} {'worst dB':>9s} "
        f"{'ph skip':>8s} {'dB skip':>8s}  verdict"
    )
    print(hdr)
    print("-" * len(hdr))
    fails: list[str] = []
    no_tables: list[str] = []
    worst = 0.0
    for d in decks:
        r = compare(A / f"{d}.out", B / f"{d}.out", a.tol)
        bad = r["mag_fail"] + r["phase_fail"] + r["db_fail"] + r["misaligned"]
        worst = max(worst, r["worst_mag"])
        if r["rows"] == 0:
            # A zero-row comparison is NOT a pass: an XQ-only deck has no field
            # tables, and so does a printout this parser failed to read. Saying
            # PASS there is how a broken parser reports a green gate.
            verdict = "n/a — no field tables read"
        elif r["misaligned"]:
            verdict = "FAIL — rows do not align"
        elif r["tables_a"] != r["tables_b"]:
            verdict = f"FAIL — {r['tables_a']} vs {r['tables_b']} tables"
            bad += 1
        elif bad == 0:
            verdict = "PASS"
        else:
            verdict = f"FAIL ({bad} cells; worst at {r['where']})"
        if bad:
            fails.append(d)
        if r["rows"] == 0:
            no_tables.append(d)
        print(
            f"{d:28s} {r['rows']:9d} {r['worst_mag']:11.3e} {r['worst_phase']:10.3e} "
            f"{r['worst_db']:9.2e} {r['phase_skipped']:8d} {r['db_skipped']:8d}  {verdict}"
        )
    compared = [d for d in decks if d not in no_tables]
    print(
        f"\ndecks with field tables compared: {len(compared)} of {len(decks)}"
        + (f"; NO tables in: {', '.join(no_tables)}" if no_tables else "")
    )
    print(f"worst magnitude difference anywhere: {worst:.3e} (tol {a.tol:g})")
    if fails:
        verdict = f"FAIL on {len(fails)} deck(s): {', '.join(fails)}"
    elif not compared:
        # Nothing was compared, so nothing passed. An empty gate is the shape a
        # broken parser takes, and it must not print the word PASS.
        verdict = "NOTHING COMPARED — no deck in this pair carries a field table"
    else:
        verdict = f"PASS — every table within tolerance on {len(compared)} deck(s)"
    print("VERDICT:", verdict)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
