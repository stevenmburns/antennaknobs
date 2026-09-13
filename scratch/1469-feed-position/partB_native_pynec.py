"""AK#1469 amendment 1, G8's reference: PyNEC Z of each catalog design itself,
for every catalog-nec5 deck that carries a discrete LD card (AK#1483).

The design is built the way `scripts/nec5_corpus/export_catalog_nec5.py` builds
each deck, as `native_reference.py` does for momwire: `cls()`, `nominal_nsegs`
times {default: 1, refined: 2}, ground free or ("finite", 13, 0.005). The
importer is not involved, so any tree with the engines gives the same answer.

    PYTHONPATH=<tree>/src python partB_native_pynec.py <catalog dir> <out.jsonl> [workers]

Rows are appended per deck and a rerun skips decks already written.
"""

import importlib
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor

CAP_BYTES = 3_500_000_000
GROUNDS = {"free": None, "somm13": ("finite", 13.0, 0.005)}
RUNGS = {"default": 1, "refined": 2}


def _cap():
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (CAP_BYTES, CAP_BYTES))
    os.environ["OMP_NUM_THREADS"] = "1"


def _solve(name):
    import warnings

    warnings.filterwarnings("ignore")
    from antennaknobs.engines.pynec import PyNECEngine

    family, design, rung, gname = name[: -len(".nec")].split(".")
    row = {"deck": name}
    t0 = time.time()
    try:
        cls = importlib.import_module(f"antennaknobs.designs.{family}.{design}").Builder
        b = cls()
        b.nominal_nsegs = cls().nominal_nsegs * RUNGS[rung]
        zs = PyNECEngine(b, ground=GROUNDS[gname]).impedance()
        zs = zs if isinstance(zs, (list, tuple)) else [zs]
        row.update(status="ok", z=[[complex(z).real, complex(z).imag] for z in zs])
    except Exception as exc:  # noqa: BLE001 — a refusal is a recorded outcome
        row.update(status="error", type=type(exc).__name__, msg=str(exc)[:300])
    row["s"] = round(time.time() - t0, 2)
    return row


def main(argv):
    catalog, out = argv[:2]
    workers = int(argv[2]) if len(argv) > 2 else 2
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            done = {json.loads(line)["deck"] for line in fh}
    names = []
    for n in sorted(os.listdir(catalog)):
        if (
            not n.endswith(".nec")
            or n in done
            or len(n[: -len(".nec")].split(".")) != 4
        ):
            continue
        with open(os.path.join(catalog, n), encoding="utf-8", errors="replace") as fh:
            if re.search(r"^LD [0146] ", fh.read(), re.M):
                names.append(n)
    with (
        open(out, "a", encoding="utf-8") as fh,
        ProcessPoolExecutor(workers, initializer=_cap) as ex,
    ):
        for row in ex.map(_solve, names):
            fh.write(json.dumps(row) + "\n")
            fh.flush()
    print(f"wrote {len(names)} rows to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
