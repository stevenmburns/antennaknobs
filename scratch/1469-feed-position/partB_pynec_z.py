"""AK#1469 part B: PyNEC Z on every catalog-nec5 and nec_portal deck, from the
tree PYTHONPATH puts first (G2's before/after). Rows are appended per deck, and a
rerun skips decks already written. Each worker caps its address space. A deck
over MAX_SEGS segments is recorded as skipped on every run, so the comparison
stays bounded on a laptop.

    PYTHONPATH=<tree>/src python partB_pynec_z.py <catalog dir> <portal dir> <out.jsonl> [workers]
"""
import json
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

CAP_BYTES = 3_500_000_000
MAX_SEGS = 3000


def _cap():
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (CAP_BYTES, CAP_BYTES))
    os.environ["OMP_NUM_THREADS"] = "1"


def _solve(job):
    import warnings

    warnings.filterwarnings("ignore")
    label, path = job
    import antennaknobs
    from antennaknobs.engines.pynec import PyNECEngine
    from antennaknobs.file_designs import builder_from_file

    row = {"set": label, "deck": os.path.basename(path), "tree": os.path.dirname(os.path.dirname(antennaknobs.__file__))}
    t0 = time.time()
    tmp = tempfile.mkdtemp()
    try:
        nec = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + ".nec")
        shutil.copyfile(path, nec)
        b = builder_from_file(nec)
        b = b() if isinstance(b, type) else b
        eng = PyNECEngine(b, ground=getattr(b, "file_ground", None))
        nseg = sum(int(t[2]) for t in eng.tups)
        row["segs"] = nseg
        if nseg > MAX_SEGS:
            row["status"] = "skipped-large"
        else:
            zs = eng.impedance()
            zs = zs if isinstance(zs, (list, tuple)) else [zs]
            row.update(status="ok", z=[[complex(z).real, complex(z).imag] for z in zs])
    except Exception as exc:  # a refusal is a recorded outcome
        row.update(status="error", type=type(exc).__name__, msg=str(exc)[:300])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    row["s"] = round(time.time() - t0, 2)
    return row


def main(argv):
    catalog, portal, out = argv[:3]
    workers = int(argv[3]) if len(argv) > 3 else 3
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            done = {(r["set"], r["deck"]) for r in map(json.loads, fh)}
    jobs = [("catalog-nec5", os.path.join(catalog, n)) for n in sorted(os.listdir(catalog)) if n.endswith(".nec")]
    jobs += [("nec_portal", os.path.join(portal, n)) for n in sorted(os.listdir(portal)) if n.endswith(".deck")]
    jobs = [j for j in jobs if (j[0], os.path.basename(j[1])) not in done]
    with open(out, "a", encoding="utf-8") as fh, ProcessPoolExecutor(workers, initializer=_cap) as ex:
        for row in ex.map(_solve, jobs):
            fh.write(json.dumps(row) + "\n")
            fh.flush()
    print(f"wrote {len(jobs)} rows to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
