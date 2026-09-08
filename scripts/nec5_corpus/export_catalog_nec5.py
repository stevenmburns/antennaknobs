#!/usr/bin/env python3
"""Write antennaknobs' own catalog designs as NEC-5 decks (MIT, ours to share).

    NEC5_EXE=/path/to/nec5cl python scripts/nec5_corpus/export_catalog_nec5.py --out catalog-nec5

Every built-in design is written at its shipped mesh and at double that mesh,
in free space and over the documented Sommerfeld ground (eps_r 13, sigma
0.005 S/m), through `NEC5Engine.deck()` -- the same writer the app's NEC-5
lane uses, so the decks carry the knot-source addressing, even segment
parity, GE/GN spellings and LD forms that lane has been validated with.

Designs whose network needs the shared reducer (transmission lines,
transformers, balanced lines: things NEC-5 has no native card for) are
skipped and listed, because a deck without its network would not be the
design. A manifest.json records what was written and why anything was not.

The NEC-5 executable is only needed for `NEC5Engine`'s constructor check; no
deck is run here.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

GROUNDS = {
    "free": None,
    "somm13": ("finite", 13.0, 0.005),
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default="catalog-nec5")
    ap.add_argument("--only", default=None, help="substring filter on family.design")
    a = ap.parse_args(argv)

    from antennaknobs.cli import list_builtin_designs
    from antennaknobs.engines.nec5 import NEC5Engine, NEC5Error, _network_needs_reducer

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []
    for dotted in list_builtin_designs():
        if a.only and a.only not in dotted:
            continue
        cls = importlib.import_module(f"antennaknobs.designs.{dotted}").Builder
        b = cls()
        net = b.build_network()
        if net is not None and _network_needs_reducer(net):
            skipped.append(
                {
                    "design": dotted,
                    "why": "network needs the reducer (TL / transformer / balanced line)",
                }
            )
            continue
        base_n = b.nominal_nsegs
        for rung, factor in (("default", 1), ("refined", 2)):
            for gname, ground in GROUNDS.items():
                bb = cls()
                bb.nominal_nsegs = base_n * factor
                try:
                    eng = NEC5Engine(bb, ground=ground)
                    deck = eng.deck([float(bb.freq)])
                except NEC5Error as e:
                    skipped.append(
                        {
                            "design": dotted,
                            "rung": rung,
                            "ground": gname,
                            "why": str(e)[:200],
                        }
                    )
                    continue
                except Exception as e:  # noqa: BLE001 — record any builder failure, keep exporting
                    skipped.append(
                        {
                            "design": dotted,
                            "rung": rung,
                            "ground": gname,
                            "why": f"{type(e).__name__}: {e}"[:200],
                        }
                    )
                    continue
                name = re.sub(r"[^\w.]", "_", dotted) + f".{rung}.{gname}.nec"
                header = (
                    f"CM antennaknobs catalog design {dotted} ({rung} mesh, {gname} ground)\n"
                    f"CM {b.freq} MHz; MIT licence, github.com/stevenmburns/antennaknobs\n"
                )
                (out / name).write_text(
                    header + deck.replace("CM antennaknobs NEC5Engine deck\n", "", 1)
                )
                written.append(
                    {"design": dotted, "rung": rung, "ground": gname, "file": name}
                )
    (out / "manifest.json").write_text(
        json.dumps({"written": written, "skipped": skipped}, indent=1)
    )
    print(f"wrote {len(written)} decks, skipped {len(skipped)} -> {out}")
    by = {}
    for s in skipped:
        by[s["why"][:60]] = by.get(s["why"][:60], 0) + 1
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("NEC5_EXE", os.environ.get("NEC5_EXE", ""))
    sys.exit(main())
