"""AK#1469 amendment 2, G9: momwire Z at refinement r = 1, 3, 9 on the nec_portal
geometries with off-centre attachments, from the tree PYTHONPATH puts first.

Run once on main (the cut spelling) and once on the part-B branch (the
positioned spelling), then score with `partB_gates_g9.py`:

    PYTHONPATH=<tree>/src python partB_portal_ladder.py <portal dir> <out.jsonl> [workers]

Rows are appended per (deck, r) and a rerun skips rows already written.
"""

import json
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

CAP_BYTES = 3_500_000_000
# One deck per distinct geometry: the six MININEC verticals share one.
DECKS = (
    "mininec_vertical_rp0.deck",
    "apex_pq_reversed_walk.deck",
    "mininec_gp80_seam.deck",
    "dipole_load_ld0.deck",
    "dipole_load_ld4.deck",
)
RUNGS = (1, 3, 9)


def _cap():
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (CAP_BYTES, CAP_BYTES))
    os.environ["OMP_NUM_THREADS"] = "1"


def _solve(job):
    import warnings

    warnings.filterwarnings("ignore")
    import antennaknobs
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.file_designs import builder_from_file

    portal, deck, r = job
    row = {
        "deck": deck,
        "r": r,
        "tree": os.path.dirname(os.path.dirname(antennaknobs.__file__)),
    }
    t0 = time.time()
    tmp = tempfile.mkdtemp()
    try:
        nec = os.path.join(tmp, deck.replace(".deck", ".nec"))
        shutil.copyfile(os.path.join(portal, deck), nec)
        b = builder_from_file(nec, refine=r)
        b = b() if isinstance(b, type) else b
        zs = MomwireEngine(b, ground=getattr(b, "file_ground", None)).impedance()
        zs = zs if isinstance(zs, (list, tuple)) else [zs]
        row.update(status="ok", z=[[complex(z).real, complex(z).imag] for z in zs])
    except Exception as exc:  # noqa: BLE001 — a refusal is a recorded outcome
        row.update(status="error", type=type(exc).__name__, msg=str(exc)[:300])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    row["s"] = round(time.time() - t0, 2)
    return row


def main(argv):
    portal, out = argv[:2]
    workers = int(argv[2]) if len(argv) > 2 else 2
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            done = {(row["deck"], row["r"]) for row in map(json.loads, fh)}
    jobs = [(portal, d, r) for d in DECKS for r in RUNGS if (d, r) not in done]
    with (
        open(out, "a", encoding="utf-8") as fh,
        ProcessPoolExecutor(workers, initializer=_cap) as ex,
    ):
        for row in ex.map(_solve, jobs):
            fh.write(json.dumps(row) + "\n")
            fh.flush()
    print(f"wrote {len(jobs)} rows to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
