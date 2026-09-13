"""G7/G3 capture for AK#1469 slice 1: every catalog-nec5 deck's momwire Z, and
AC6LA's deck on NEC-5, from whichever antennaknobs tree PYTHONPATH puts first.

Run once on the baseline worktree (main f77b4fd, today's wire cut) and once on
the slice-1 branch, then compare:

    PYTHONPATH=<tree>/src python catalog_nec5_z.py <decks dir> <out.json> [workers]

Each worker caps its address space (the laptop's 8 GB rule), so a deck too big
for the cap records a MemoryError on both runs and drops out of the comparison.

Rows are appended to ``<out.json>.partial`` as they finish, and a rerun skips
decks already there. So an out-of-memory kill of the whole run loses nothing
already solved, which matters on a 16 GB laptop that shares memory with a
desktop.
"""

import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

CAP_BYTES = 3_500_000_000
NEC5_DECK = "dipoles.invvee.default.somm13.nec"


def _cap():
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (CAP_BYTES, CAP_BYTES))
    os.environ.setdefault("OMP_NUM_THREADS", "2")


def _solve(path):
    import warnings

    warnings.filterwarnings("ignore")
    import antennaknobs
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.file_designs import builder_from_file

    t0 = time.time()
    row = {"tree": os.path.dirname(os.path.dirname(antennaknobs.__file__))}
    try:
        b = builder_from_file(path)
        b = b() if isinstance(b, type) else b
        eng = MomwireEngine(b, ground=getattr(b, "file_ground", None))
        zs = eng.impedance()
        zs = zs if isinstance(zs, (list, tuple)) else [zs]
        row.update(status="ok", z=[[complex(z).real, complex(z).imag] for z in zs])
    except Exception as e:  # noqa: BLE001 — a refusal is a recorded outcome
        row.update(status="error", type=type(e).__name__, msg=str(e)[:300])
    row["s"] = round(time.time() - t0, 2)
    return os.path.basename(path), row


def _nec5(path):
    from antennaknobs.engines.nec5 import NEC5Engine
    from antennaknobs.file_designs import builder_from_file

    b = builder_from_file(path)
    b = b() if isinstance(b, type) else b
    eng = NEC5Engine(b, ground=getattr(b, "file_ground", None))
    zs = eng.impedance()
    zs = zs if isinstance(zs, (list, tuple)) else [zs]
    return {
        "z": [[complex(z).real, complex(z).imag] for z in zs],
        "deck": eng.deck([b.freq]),
    }


def main(argv):
    decks_dir, out = argv[0], argv[1]
    workers = int(argv[2]) if len(argv) > 2 else 2
    paths = sorted(
        os.path.join(decks_dir, f) for f in os.listdir(decks_dir) if f.endswith(".nec")
    )
    partial = out + ".partial"
    rows = {}
    if os.path.exists(partial):
        with open(partial, encoding="utf-8") as fh:
            for line in fh:
                name, row = json.loads(line)
                rows[name] = row
    todo = [p for p in paths if os.path.basename(p) not in rows]
    with (
        ProcessPoolExecutor(max_workers=workers, initializer=_cap) as pool,
        open(partial, "a", encoding="utf-8") as log,
    ):
        for name, row in pool.map(_solve, todo):
            rows[name] = row
            log.write(json.dumps([name, row]) + "\n")
            log.flush()
    result = {"momwire": rows}
    if os.environ.get("NEC5_EXE"):
        result["nec5_ac6la"] = _nec5(os.path.join(decks_dir, NEC5_DECK))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, sort_keys=True)
    ok = sum(r["status"] == "ok" for r in rows.values())
    print(f"{out}: {len(rows)} decks, {ok} ok, {len(rows) - ok} refused or failed")


if __name__ == "__main__":
    main(sys.argv[1:])
