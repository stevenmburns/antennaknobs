"""AK#1469 part B baseline/after capture: import structure, NEC-2 export and
NEC-5 deck text for every catalog-nec5 deck and every momwire nec_portal deck.
Parses and writes decks only; nothing is solved.

    PYTHONPATH=<tree>/src python partB_structure_capture.py <catalog-nec5 dir> <nec_portal dir> <out.jsonl>

Rows are appended per deck and a rerun skips decks already written.
"""

import json
import os
import shutil
import sys
import tempfile
import warnings


def _row(path, label):
    from antennaknobs.engines.nec5 import NEC5Engine
    from antennaknobs.file_designs import builder_from_file
    from antennaknobs.nec_export import export_nec
    from antennaknobs.nec_import import parse_nec

    text = open(path, encoding="utf-8", errors="replace").read()
    row = {"set": label, "deck": os.path.basename(path)}
    try:
        deck = parse_nec(text, name=os.path.basename(path), network=True)
        tups = deck.wire_tuples(specs=True)
        row["tuples"] = [[int(w.n_seg), w.name] for w in tups]
        net = deck.network()
        row["ports"] = {
            k: [type(p).__name__, getattr(p, "wire", None), getattr(p, "at", None)]
            for k, p in net.ports.items()
        }
    except Exception as exc:  # a refusal is a recorded outcome
        row["import"] = f"ERR {type(exc).__name__}: {exc}"[:300]
        return row
    tmp = tempfile.mkdtemp()
    try:
        nec = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + ".nec")
        shutil.copyfile(path, nec)
        b = builder_from_file(nec)
        b = b() if isinstance(b, type) else b
        for lane, make in (
            ("nec2", lambda: export_nec(b, ground=getattr(b, "file_ground", None))),
            (
                "nec5",
                lambda: NEC5Engine(
                    b, ground=getattr(b, "file_ground", None), require_exe=False
                ).deck([b.freq]),
            ),
        ):
            try:
                row[lane] = make()
            except Exception as exc:  # the refusal text is the datum
                row[lane] = f"ERR {type(exc).__name__}: {exc}"[:300]
    except Exception as exc:  # a census records what it cannot build
        row["build"] = f"ERR {type(exc).__name__}: {exc}"[:300]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return row


def main(argv):
    warnings.filterwarnings("ignore")
    catalog, portal, out = argv
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            done = {(r["set"], r["deck"]) for r in map(json.loads, fh)}
    jobs = [("catalog-nec5", os.path.join(catalog, n)) for n in sorted(os.listdir(catalog)) if n.endswith(".nec")]
    jobs += [("nec_portal", os.path.join(portal, n)) for n in sorted(os.listdir(portal)) if n.endswith(".deck")]
    with open(out, "a", encoding="utf-8") as fh:
        for label, path in jobs:
            if (label, os.path.basename(path)) in done:
                continue
            fh.write(json.dumps(_row(path, label)) + "\n")
            fh.flush()
    print(f"{len(jobs)} decks in {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
