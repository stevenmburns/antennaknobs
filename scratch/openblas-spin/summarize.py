"""Summarise bench_thread_policy.py rows into the two tables the issues need.

Reads JSONL (one or more files) and prints, per workload:

  * the #1050 table — spin ON vs OFF at each thread count;
  * the #1051 table — 4 vs 8 threads at each spin state, '+' meaning the
    lower (physical) count won;
  * the thermal columns, because on a mobile part a row with large drift is
    reporting a machine rather than a code path.

Repeats are reduced by MEDIAN, and the spread across repeats is printed next
to it. A margin quoted without its spread is how "+10.0%" got into AK#1051
when the repeats actually ranged +8.5 to +15.7.

    python summarize.py results/xps13.jsonl
    python summarize.py results/*.jsonl        # boxes side by side
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict


def load(paths):
    """Cells carry no host of their own — they inherit the provenance object
    that most recently preceded them, which is what makes several boxes'
    files concatenable on one command line."""
    rows, prov = [], []
    for p in paths:
        host = "?"
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("kind") == "provenance":
                    host = d.get("host", "?")
                    prov.append(d)
                else:
                    d["host"] = host
                    rows.append(d)
    return prov, rows


def reduce_cells(rows):
    """(host, workload, n, threads, spin) -> {ms, spread_pct, drift, clocks}"""
    buckets = defaultdict(list)
    for r in rows:
        if r.get("kind") != "cell":
            continue
        key = (r.get("host", "?"), r["workload"], r["n"], r["threads"], r["spin"])
        buckets[key].append(r)
    out = {}
    for key, rs in buckets.items():
        ms = [r["steady_ms"] for r in rs]
        med = statistics.median(ms)
        out[key] = {
            "ms": med,
            "n_rep": len(ms),
            # Spread as a percentage of the median: the honest width of a cell.
            "spread_pct": (max(ms) - min(ms)) / med * 100 if med else 0.0,
            "drift_pct": statistics.median([r["drift_pct"] for r in rs]),
            "busy_first": statistics.median(
                [r["clock"]["busy_first_fifth"] for r in rs if r.get("clock")]
            )
            if rs[0].get("clock")
            else None,
            "busy_last": statistics.median(
                [r["clock"]["busy_last_fifth"] for r in rs if r.get("clock")]
            )
            if rs[0].get("clock")
            else None,
            "fill_frac": statistics.median(
                [r["fill_frac"] for r in rs if r.get("fill_frac") is not None]
            )
            if any(r.get("fill_frac") is not None for r in rs)
            else None,
        }
    return out


def _gain(before: float, after: float) -> float:
    """Percent improvement of `after` over `before` (positive = after faster)."""
    return (before / after - 1) * 100


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    prov, rows = load(sys.argv[1:])
    for p in prov[:1]:
        print(
            f"# {p.get('host')} — {p.get('cpu')} "
            f"({p.get('cores_physical')}C/{p.get('cores_logical')}T), "
            f"loadavg {p.get('loadavg', ['?'])[0]:.2f}"
        )
    cells = reduce_cells(rows)
    hosts = sorted({k[0] for k in cells})
    for host in hosts:
        keys = [k for k in cells if k[0] == host]
        workloads = sorted({k[1] for k in keys})
        for w in workloads:
            ns = sorted({k[2] for k in keys if k[1] == w})
            thr = sorted({k[3] for k in keys if k[1] == w})
            print(f"\n## {host} / {w}")
            print(
                f"{'N':>6} {'thr':>4} {'spin ON':>10} {'spin OFF':>10} "
                f"{'gain':>8} {'spread':>8} {'drift':>8} {'MHz 1st->last':>16}"
            )
            for n in ns:
                for t in thr:
                    on = cells.get((host, w, n, t, "on"))
                    off = cells.get((host, w, n, t, "off"))
                    if not (on and off):
                        continue
                    sp = max(on["spread_pct"], off["spread_pct"])
                    clk = (
                        f"{off['busy_first']:.0f}->{off['busy_last']:.0f}"
                        if off["busy_first"]
                        else "-"
                    )
                    print(
                        f"{n:>6} {t:>4} {on['ms']:>10.1f} {off['ms']:>10.1f} "
                        f"{_gain(on['ms'], off['ms']):>+7.1f}% {sp:>7.1f}% "
                        f"{off['drift_pct']:>+7.1f}% {clk:>16}"
                    )
            # #1051: physical vs logical, '+' = the lower thread count won.
            if len(thr) >= 2:
                lo, hi = thr[0], thr[-1]
                print(
                    f"\n{'N':>6} {'spin':>5} {'  %d thr' % lo:>10} "
                    f"{'  %d thr' % hi:>10} {'lo vs hi':>10}  winner"
                )
                for n in ns:
                    for spin in ("on", "off"):
                        a = cells.get((host, w, n, lo, spin))
                        b = cells.get((host, w, n, hi, spin))
                        if not (a and b):
                            continue
                        d = _gain(a["ms"], b["ms"])  # + means hi (logical) faster
                        win = f"logical({hi})" if d > 0 else f"physical({lo})"
                        # No verdict from unpaired rows. The tempting test
                        # -- |delta| > spread -- compares a BETWEEN-arm
                        # difference against WITHIN-arm scatter, and is blind
                        # to the between-cell thermal drift that dominates a
                        # mobile part. On this very data it called free N=200
                        # "+10.0% physical, resolved" where the paired rows
                        # say -12.1% logical. Show the spread as context and
                        # let --paired rows carry any verdict.
                        note = "  [unpaired: within-arm spread only]"
                        print(
                            f"{n:>6} {spin:>5} {a['ms']:>10.1f} {b['ms']:>10.1f} "
                            f"{-d:>+9.1f}%  {win}{note}"
                        )


if __name__ == "__main__":
    main()
