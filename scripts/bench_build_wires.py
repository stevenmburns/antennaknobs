"""Benchmark builder.build_wires() across every design.

We're sizing the headroom we have for an interactive web UI: if pure
geometry construction stays well under a millisecond, the React frontend
can recompute the wire mesh on every slider tick without juddering.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import pathlib
import time
import traceback

DESIGNS_DIR = (
    pathlib.Path(__file__).resolve().parents[1] / "src" / "antennaknobs" / "designs"
)


def list_design_modules() -> list[str]:
    names = []
    for p in sorted(DESIGNS_DIR.glob("*.py")):
        if p.stem.startswith("_"):
            continue
        names.append(p.stem)
    return names


def bench_one(name: str, n_iter: int = 1000) -> dict:
    mod = importlib.import_module(f"antennaknobs.designs.{name}")
    cls = getattr(mod, "Builder", None)
    if cls is None:
        return {"name": name, "status": "no Builder class"}
    try:
        inst = cls()
    except Exception as exc:  # noqa: BLE001 — probe harness — a failing case is recorded and the sweep continues
        return {"name": name, "status": f"ctor: {exc!r}"}

    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        try:
            wires = inst.build_wires()
        except Exception as exc:  # noqa: BLE001 — probe harness — a failing case is recorded and the sweep continues
            return {"name": name, "status": f"build: {exc!r}"}

        n_wires = len(wires)
        n_segs_total = sum(int(t[2]) for t in wires)

        t0 = time.perf_counter()
        for _ in range(n_iter):
            inst.build_wires()
        elapsed = time.perf_counter() - t0
    per_call_us = (elapsed / n_iter) * 1e6

    return {
        "name": name,
        "status": "ok",
        "n_wires": n_wires,
        "n_segs_total": n_segs_total,
        "us_per_call": per_call_us,
    }


def main() -> None:
    names = list_design_modules()
    rows = []
    for n in names:
        try:
            rows.append(bench_one(n))
        except Exception:  # noqa: BLE001 — probe harness — a failing case is recorded and the sweep continues
            rows.append(
                {
                    "name": n,
                    "status": "uncaught: " + traceback.format_exc().splitlines()[-1],
                }
            )

    ok = [r for r in rows if r["status"] == "ok"]
    bad = [r for r in rows if r["status"] != "ok"]

    print(f"{'design':<32} {'n_wires':>8} {'n_segs':>8} {'us/call':>10}")
    print("-" * 62)
    for r in sorted(ok, key=lambda r: r["us_per_call"]):
        print(
            f"{r['name']:<32} {r['n_wires']:>8} {r['n_segs_total']:>8} {r['us_per_call']:>10.2f}"
        )

    if bad:
        print()
        print(f"{'design':<32} status")
        print("-" * 62)
        for r in bad:
            print(f"{r['name']:<32} {r['status']}")

    if ok:
        fastest = min(r["us_per_call"] for r in ok)
        slowest = max(r["us_per_call"] for r in ok)
        median = sorted(r["us_per_call"] for r in ok)[len(ok) // 2]
        print()
        print(f"summary: {len(ok)} ok, {len(bad)} failed")
        print(
            f"fastest: {fastest:.2f} us  median: {median:.2f} us  slowest: {slowest:.2f} us"
        )


if __name__ == "__main__":
    main()
