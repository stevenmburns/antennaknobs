"""Which import spelling lands closer to the catalog design itself? (AK#1469 G6 follow-up)

G6 missed: momwire Z on the catalog-nec5 decks moves by up to 11 % between today's
cut spelling and the whole-wire spelling, scaling with the feed impedance. A miss
says nothing about which spelling is RIGHT. The reference is the catalog design
solved directly, built the way `scripts/nec5_corpus/export_catalog_nec5.py`
builds each deck: `cls()`, `nominal_nsegs *= {default: 1, refined: 2}`, ground
free or ("finite", 13, 0.005). Neither import spelling reproduces that mesh
exactly, because the NEC-5 export coerces fed wires to an even count, so the
answer is a distance, not an identity.

    python native_reference.py baseline.json after.json out.jsonl [min_abs_z] [limit]

Rows are appended per deck and a rerun skips decks already written, so a run cut
short by the laptop's memory guard or a timeout loses nothing.
"""

import importlib
import json
import os
import sys

GROUNDS = {"free": None, "somm13": ("finite", 13.0, 0.005)}
RUNGS = {"default": 1, "refined": 2}


def _native(dotted, rung, gname):
    from antennaknobs.engines.momwire import MomwireEngine

    cls = importlib.import_module(f"antennaknobs.designs.{dotted}").Builder
    base_n = cls().nominal_nsegs
    b = cls()
    b.nominal_nsegs = base_n * RUNGS[rung]
    zs = MomwireEngine(b, ground=GROUNDS[gname]).impedance()
    zs = zs if isinstance(zs, (list, tuple)) else [zs]
    return complex(zs[0])


def main(argv):
    import warnings

    warnings.filterwarnings("ignore")
    before = json.load(open(argv[0], encoding="utf-8"))["momwire"]
    after = json.load(open(argv[1], encoding="utf-8"))["momwire"]
    out = argv[2]
    min_abs_z = float(argv[3]) if len(argv) > 3 else 0.0
    limit = int(argv[4]) if len(argv) > 4 else None

    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            done = {json.loads(line)["deck"] for line in fh}
    picks = []
    for name in sorted(set(before) & set(after)):
        parts = name[: -len(".nec")].split(".")
        if len(parts) != 4 or name in done:
            continue  # per-port decks (design.rung.ground.portN) are out of scope
        if before[name]["status"] != "ok" or after[name]["status"] != "ok":
            continue
        zb, za = complex(*before[name]["z"][0]), complex(*after[name]["z"][0])
        if abs(zb) >= min_abs_z:
            picks.append((name, parts, zb, za))
    picks = picks[:limit] if limit else picks
    with open(out, "a", encoding="utf-8") as log:
        for name, (family, design, rung, gname), zb, za in picks:
            row = {"deck": name}
            try:
                zn = _native(f"{family}.{design}", rung, gname)
                row.update(
                    native=[zn.real, zn.imag],
                    before_rel=abs(zb - zn) / abs(zn),
                    after_rel=abs(za - zn) / abs(zn),
                )
            except Exception as e:  # noqa: BLE001 — a design that will not solve is a row
                row.update(error=f"{type(e).__name__}: {str(e)[:160]}")
            log.write(json.dumps(row) + "\n")
            log.flush()
    print(f"{out}: {len(picks)} decks this run, {len(done)} already written")


if __name__ == "__main__":
    main(sys.argv[1:])
