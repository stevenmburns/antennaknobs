"""AK#1456 addendum to the #1441 buried census: each committed Population A
row's fed segments, per engine, read from the engines' meshes with no solve.

  PYTHONPATH=<momwire src>:src python scratch/956-census/popa_fed_addendum.py

`popa-rows.csv` predates the `momwire_fed` / `nec5_fed` columns `popa_run.py`
now writes, and re-solving the census to add a mesh fact is not warranted: the
fed segment is a property of the builder and the engine's parity, both of which
this reads directly. Writes `popa-fed-segments.json`, keyed like the CSV rows.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from popa_run import fed_note
from popa_worker import SOIL_A, builder_for

from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine


def main():
    here = Path(__file__).resolve().parent
    with open(here / "popa-rows.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        rec = {k: r[k] for k in ("design", "variant", "rung", "nominal_nsegs")}
        b = builder_for(r["design"], r["variant"], int(r["nominal_nsegs"]))
        ground = ("finite", *SOIL_A)
        for key, make in (
            ("momwire", lambda b=b: MomwireEngine(b, ground=ground, ground_z=0.0)),
            ("nec5", lambda b=b: NEC5Engine(b, ground=ground, require_exe=False)),
        ):
            try:
                cell = {"fed_segments": make().fed_segments()}
                rec[f"{key}_fed"] = fed_note(cell)
                rec[f"{key}_records"] = cell["fed_segments"]
            except Exception as exc:  # noqa: BLE001 - a refusal is a recorded answer here
                rec[f"{key}_fed"] = f"{type(exc).__name__}: {exc}"[:200]
        out.append(rec)
        print(
            f"{rec['design']} {rec['variant']} {rec['rung']}: "
            f"momwire {rec['momwire_fed']} | NEC-5 {rec['nec5_fed']}"
        )
    (here / "popa-fed-segments.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
