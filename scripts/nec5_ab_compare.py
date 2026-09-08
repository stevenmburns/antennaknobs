"""Black-box A/B of two NEC-5 executables on the same decks.

Written for the beta of an "accelerated" NEC-5 Windows build: we may never
see its source, so the comparison is printout-to-printout against the stock
binary, deck by deck, plus a determinism check on the new binary alone (the
report that motivated this was multithreading changing answers).

For every deck:

  * REF: the stock binary once (or its captured ``<deck>.out`` sibling when
    ``--use-captured`` is set and the sibling exists);
  * NEW: the candidate binary ``--repeats`` times under each ``--threads``
    setting (exported through every env var in ``--thread-env``, e.g.
    OMP_NUM_THREADS; a binary that ignores them simply repeats);

and reads from each printout, with ``NEC5Engine``'s own parsers: the driving-
point Z per feed and frequency, the power budget, the peak of the radiation
pattern, and the wire currents. Reported per deck:

  * new-vs-ref: max relative |dZ| over feeds/frequencies, the dZ itself, the
    peak-gain difference in dB, the max relative current difference;
  * new-vs-new: the same quantities across repeats/threads (0 = deterministic);
  * whether the printouts are byte-identical once timing lines are dropped;
  * wall time per run and the speedup (ref wall / new median wall).

Output: one JSON line per (deck, exe, threads, repeat) plus a summary table.
Exit codes are not trusted on NEC-5 (Fortran STOP); a missing or unparseable
printout is a FAIL row, never a crash of the sweep.

Usage (Linux self-check: same binary twice, expects zeros everywhere):

    NEC5_EXE=~/antennas/NEC5-downloads/nec5-linux/nec5cl \
    python scripts/nec5_ab_compare.py --ref-exe $NEC5_EXE --new-exe $NEC5_EXE \
        --decks tests/fixtures/nec5 tests/fixtures/eznec_nec5 --out ab.jsonl

    python scripts/nec5_ab_compare.py --ref-exe NEC5CL_x13.exe --new-exe accel\\nec5.exe \
        --decks decks --threads 1,2,4,8 --repeats 3 --out ab.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antennaknobs.engines.nec5 import NEC5Engine, NEC5Error  # noqa: E402

_TIMING_LINE = re.compile(r"FILL=|FACTOR=|RUN\s+TIME|\bSEC\.", re.IGNORECASE)


def _run_exe(
    exe: str, deck_text: str, env: dict, timeout: float
) -> tuple[str | None, float, str]:
    """Run one deck the way NEC5Engine does: file names on stdin, printout in
    the working directory. Returns (printout or None, wall seconds, note)."""
    with tempfile.TemporaryDirectory(prefix="nec5ab_") as td:
        tdp = Path(td)
        (tdp / "model.nec").write_text(deck_text)
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [exe],
                input="model.nec\nmodel.out\n\n",
                text=True,
                capture_output=True,
                cwd=td,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return None, time.perf_counter() - t0, f"timeout after {timeout:.0f}s"
        wall = time.perf_counter() - t0
        out = tdp / "model.out"
        if not out.is_file():
            tail = (proc.stdout or "")[-300:] + (proc.stderr or "")[-300:]
            return None, wall, "no printout: " + tail.replace("\n", " | ")
        return out.read_text(errors="replace"), wall, ""


def _keep(
    keep_dir: str, deck: Path, exe: str, th: str, rep: int, printout: str | None
) -> None:
    if not keep_dir or printout is None:
        return
    d = Path(keep_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{deck.stem}.{exe}.t{th or 'x'}.r{rep}.out").write_text(printout)


def _strip_timing(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not _TIMING_LINE.search(ln))


def _extract(text: str) -> dict:
    """What we compare, from one printout. Missing sections are None, not
    errors — a deck with no RP card has no pattern."""
    d: dict = {"z": None, "peak_gain_db": None, "budget": None, "currents": None}
    try:
        aip = NEC5Engine._parse_input_parameters(text)
        d["z"] = [[[tag, seg, z.real, z.imag] for tag, seg, z in rows] for rows in aip]
    except NEC5Error as e:
        d["z_error"] = str(e)[:200]
    try:
        pat = NEC5Engine._parse_radiation_patterns(text)
        finite = [g for g in pat.values() if g > -900]
        d["peak_gain_db"] = max(finite) if finite else None
        d["pattern_n"] = len(pat)
    except (NEC5Error, IndexError, ValueError):
        pass
    try:
        d["budget"] = NEC5Engine._parse_power_budget(text)
    except (NEC5Error, IndexError, ValueError):
        pass
    try:
        cur = NEC5Engine._parse_wire_currents(text)
        d["currents"] = [
            {str(k): [[c.real, c.imag] for c in v] for k, v in per_freq.items()}
            for per_freq in cur
        ]
    except (NEC5Error, IndexError, ValueError):
        pass
    return d


def _z_list(d: dict) -> list[complex]:
    return [complex(r[2], r[3]) for rows in (d.get("z") or []) for r in rows]


def _rel_dz(a: dict, b: dict) -> tuple[float | None, float | None]:
    """(max relative |dZ|, max |dZ| in ohms) between two extracts, None when
    either has no Z or the feed lists differ in length."""
    za, zb = _z_list(a), _z_list(b)
    if not za or len(za) != len(zb):
        return None, None
    rel, absd = 0.0, 0.0
    for x, y in zip(za, zb, strict=True):
        dz = abs(x - y)
        absd = max(absd, dz)
        rel = max(rel, dz / max(abs(x), 1e-12))
    return rel, absd


def _rel_di(a: dict, b: dict) -> float | None:
    ca, cb = a.get("currents"), b.get("currents")
    if not ca or not cb or len(ca) != len(cb):
        return None
    worst = 0.0
    for fa, fb in zip(ca, cb, strict=True):
        if fa.keys() != fb.keys():
            return None
        for k in fa:
            va = [complex(*p) for p in fa[k]]
            vb = [complex(*p) for p in fb[k]]
            if len(va) != len(vb):
                return None
            scale = max((abs(v) for v in va), default=1e-12) or 1e-12
            worst = max(
                worst, max(abs(x - y) for x, y in zip(va, vb, strict=True)) / scale
            )
    return worst


def _collect_decks(specs: list[str]) -> list[Path]:
    out: list[Path] = []
    for s in specs:
        p = Path(s)
        if p.is_dir():
            out.extend(sorted(q for q in p.rglob("*.nec") if q.is_file()))
        elif p.is_file():
            out.append(p)
        else:
            out.extend(sorted(Path().glob(s)))
    seen, uniq = set(), []
    for p in out:
        r = p.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(p)
    return uniq


def main(argv=None) -> int:
    # Windows consoles default to cp1252; keep every print ASCII-safe anyway.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ref-exe", required=True, help="the stock NEC-5 binary")
    ap.add_argument("--new-exe", required=True, help="the candidate binary")
    ap.add_argument(
        "--decks",
        nargs="+",
        required=True,
        help="deck files, dirs (recursive *.nec) or globs",
    )
    ap.add_argument(
        "--out",
        required=True,
        help="jsonl of every run (resume point: done (deck, exe, threads, repeat) rows are skipped)",
    )
    ap.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="runs of the NEW binary per thread setting",
    )
    ap.add_argument(
        "--threads",
        default="",
        help="comma list, e.g. 1,2,4,8; empty = one run with the env as is",
    )
    ap.add_argument(
        "--thread-env",
        default="OMP_NUM_THREADS,MKL_NUM_THREADS,OPENBLAS_NUM_THREADS",
        help="env vars that carry --threads",
    )
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument(
        "--use-captured",
        action="store_true",
        help="take <deck>.out beside a deck as the REF printout when present",
    )
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--keep-dir",
        default="",
        help="save every printout here as <deck>.<exe>.t<threads>.r<repeat>.out for post-hoc diffs",
    )
    ap.add_argument(
        "--z-tol",
        type=float,
        default=1e-4,
        help="relative |dZ| above which a deck is flagged",
    )
    args = ap.parse_args(argv)

    decks = _collect_decks(args.decks)
    if args.limit:
        decks = decks[: args.limit]
    if not decks:
        print("no decks", file=sys.stderr)
        return 2
    threads = [t.strip() for t in args.threads.split(",") if t.strip()] or [""]
    env_names = [e.strip() for e in args.thread_env.split(",") if e.strip()]

    out_path = Path(args.out)
    done = set()
    if out_path.exists():
        for ln in out_path.read_text().splitlines():
            try:
                r = json.loads(ln)
                done.add(
                    (r["deck"], r["exe"], r.get("threads", ""), r.get("repeat", 0))
                )
            except (ValueError, KeyError):
                continue
    fh = out_path.open("a")
    meta = {
        "_meta": True,
        "ref_exe": args.ref_exe,
        "new_exe": args.new_exe,
        "threads": threads,
        "repeats": args.repeats,
        "thread_env": env_names,
        "platform": sys.platform,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    fh.write(json.dumps(meta) + "\n")

    summary = []
    for i, deck in enumerate(decks, 1):
        text = deck.read_text(errors="replace")
        name = str(deck)
        runs: dict[str, list[dict]] = {"ref": [], "new": []}

        # --- REF
        key = (name, "ref", "", 0)
        cap = deck.with_suffix(".out")
        if key not in done:
            if args.use_captured and cap.is_file():
                printout, wall, note = (
                    cap.read_text(errors="replace"),
                    float("nan"),
                    "captured",
                )
            else:
                printout, wall, note = _run_exe(
                    args.ref_exe, text, dict(os.environ), args.timeout
                )
            row = {
                "deck": name,
                "exe": "ref",
                "threads": "",
                "repeat": 0,
                "wall_s": wall,
                "note": note,
            }
            _keep(args.keep_dir, deck, "ref", "", 0, printout)
            row.update(_extract(printout) if printout else {"z": None})
            row["printout_sha"] = hashlib.sha256(
                _strip_timing(printout or "").encode()
            ).hexdigest()[:16]
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            runs["ref"].append(row)

        # --- NEW
        for th in threads:
            env = dict(os.environ)
            for e in env_names:
                if th:
                    env[e] = th
            for rep in range(args.repeats):
                key = (name, "new", th, rep)
                if key in done:
                    continue
                printout, wall, note = _run_exe(args.new_exe, text, env, args.timeout)
                row = {
                    "deck": name,
                    "exe": "new",
                    "threads": th,
                    "repeat": rep,
                    "wall_s": wall,
                    "note": note,
                }
                _keep(args.keep_dir, deck, "new", th, rep, printout)
                row.update(_extract(printout) if printout else {"z": None})
                row["printout_sha"] = hashlib.sha256(
                    _strip_timing(printout or "").encode()
                ).hexdigest()[:16]
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                runs["new"].append(row)

        # --- compare (from what this invocation ran; a resumed run re-reads the jsonl below)
        summary.append((name, runs))
        print(f"[{i}/{len(decks)}] {deck.name}", file=sys.stderr)
    fh.close()

    # Rebuild from the jsonl so resumed runs report everything.
    rows = [json.loads(ln) for ln in out_path.read_text().splitlines() if ln.strip()]
    rows = [r for r in rows if not r.get("_meta")]
    by_deck: dict[str, dict[str, list[dict]]] = {}
    for r in rows:
        by_deck.setdefault(r["deck"], {"ref": [], "new": []})[r["exe"]].append(r)

    table = []
    for name, rr in by_deck.items():
        ref = rr["ref"][0] if rr["ref"] else None
        new = rr["new"]
        rec = {
            "deck": Path(name).name,
            "n_new": len(new),
            "fail_new": sum(1 for r in new if r.get("z") is None),
            "ref_ok": bool(ref and ref.get("z")),
        }
        good = [r for r in new if r.get("z")]
        if ref and ref.get("z") and good:
            rels = [_rel_dz(ref, r) for r in good]
            rec["rel_dz_max"] = (
                max(x[0] for x in rels if x[0] is not None)
                if any(x[0] is not None for x in rels)
                else None
            )
            rec["abs_dz_max"] = (
                max(x[1] for x in rels if x[1] is not None)
                if any(x[1] is not None for x in rels)
                else None
            )
            dis = [_rel_di(ref, r) for r in good]
            rec["rel_di_max"] = max((x for x in dis if x is not None), default=None)
            if ref.get("peak_gain_db") is not None and all(
                r.get("peak_gain_db") is not None for r in good
            ):
                rec["dgain_db_max"] = max(
                    abs(r["peak_gain_db"] - ref["peak_gain_db"]) for r in good
                )
            # new-vs-new
            if len(good) > 1:
                base = good[0]
                rec["nn_rel_dz_max"] = max(
                    (_rel_dz(base, r)[0] or 0.0) for r in good[1:]
                )
                rec["nn_identical_printouts"] = (
                    len({r["printout_sha"] for r in good}) == 1
                )
            walls = [r["wall_s"] for r in good if r["wall_s"] == r["wall_s"]]
            if walls and ref["wall_s"] == ref["wall_s"]:
                rec["speedup"] = (
                    ref["wall_s"] / statistics.median(walls)
                    if statistics.median(walls) > 0
                    else None
                )
            rec["flag"] = (rec.get("rel_dz_max") or 0) > args.z_tol or (
                rec.get("nn_rel_dz_max") or 0
            ) > 0
        table.append(rec)

    print("\n=== NEC-5 A/B summary ===")
    print(
        f"decks {len(table)}; ref failed {sum(1 for t in table if not t['ref_ok'])}; new runs failed {sum(t['fail_new'] for t in table)}"
    )
    rel = [t["rel_dz_max"] for t in table if t.get("rel_dz_max") is not None]
    if rel:
        rel_sorted = sorted(rel)
        p90 = rel_sorted[min(len(rel_sorted) - 1, int(0.9 * len(rel_sorted)))]
        print(
            f"new-vs-ref rel |dZ|: median {statistics.median(rel):.2e}  p90 {p90:.2e}  max {max(rel):.2e}  (> {args.z_tol:g} on {sum(1 for x in rel if x > args.z_tol)} decks)"
        )
    nn = [t["nn_rel_dz_max"] for t in table if t.get("nn_rel_dz_max") is not None]
    if nn:
        print(
            f"new-vs-new (repeats/threads) rel |dZ|: max {max(nn):.2e}; non-identical printouts on {sum(1 for t in table if t.get('nn_identical_printouts') is False)} decks"
        )
    sp = [t["speedup"] for t in table if t.get("speedup")]
    if sp:
        print(
            f"speedup ref/new wall: median {statistics.median(sp):.2f}x  min {min(sp):.2f}x  max {max(sp):.2f}x"
        )
    flagged = [t for t in table if t.get("flag")]
    if flagged:
        print("\nflagged decks:")
        for t in sorted(flagged, key=lambda t: -(t.get("rel_dz_max") or 0))[:40]:
            print(
                f"  {t['deck']:48s} rel dZ {t.get('rel_dz_max')!s:>10} abs {t.get('abs_dz_max')!s:>10} nn {t.get('nn_rel_dz_max')!s:>10} dG {t.get('dgain_db_max')!s:>8}"
            )
    summ_path = out_path.with_suffix(".summary.json")
    summ_path.write_text(json.dumps(table, indent=1))
    print(f"\nper-deck table: {summ_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
