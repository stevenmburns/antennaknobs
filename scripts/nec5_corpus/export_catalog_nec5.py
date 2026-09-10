"""Write antennaknobs' own catalog designs as NEC-5 decks (MIT, ours to share).

    python scripts/nec5_corpus/export_catalog_nec5.py --out catalog-nec5

Every built-in design is written at its shipped mesh and at double that mesh,
in free space and over the documented Sommerfeld ground (eps_r 13, sigma
0.005 S/m), through `NEC5Engine.deck()` -- the same writer the app's NEC-5
lane uses, so the decks carry the knot-source addressing, even segment
parity, GE/GN spellings and LD forms that lane has been validated with.

Designs whose network needs the shared reducer (transmission lines,
transformers, balanced lines: things NEC-5 has no native card for) are
written as the per-port decks the app actually sends NEC-5 -- one deck per
port with that port driven by 1 V -- since the app solves the network
outside NEC-5 from the resulting multiport Y. A manifest.json records what
was written and why anything was not.

No NEC-5 executable is needed: the engine is built with ``require_exe=False``
(a deck writer, never a solver), so the corpus tool's release build can run
this on a box with no engine (#1376). The output is deterministic — the same
commit writes the same bytes — which is what lets the release zip carry it.
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
        # A design whose network NEC-5 has no native card for (transmission
        # lines, transformers, balanced lines) is served by the app through
        # the multiport-Y route: one deck per port, that port driven by 1 V,
        # the network solved outside NEC-5 from the resulting Y matrix. Those
        # per-port decks are exactly what the app sends, so they are written
        # as such (design.rung.ground.portN.nec) rather than skipped.
        per_port = net is not None and _network_needs_reducer(net)
        base_n = b.nominal_nsegs
        for rung, factor in (("default", 1), ("refined", 2)):
            for gname, ground in GROUNDS.items():
                bb = cls()
                bb.nominal_nsegs = base_n * factor
                try:
                    eng = NEC5Engine(bb, ground=ground, require_exe=False)
                    if per_port:
                        decks = [
                            (
                                f"port{k + 1}",
                                eng.deck(
                                    [float(bb.freq)], sources=[(idx, 0, 1 + 0j, knot)]
                                ),
                                f"port {k + 1} of {len(eng._port_attach)} ({name}) driven; "
                                "the network is solved outside NEC-5 from the multiport Y",
                            )
                            for k, (name, (idx, knot)) in enumerate(
                                eng._port_attach.items()
                            )
                        ]
                    else:
                        decks = [("", eng.deck([float(bb.freq)]), "")]
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
                for suffix, deck, note in decks:
                    name = (
                        re.sub(r"[^\w.]", "_", dotted)
                        + f".{rung}.{gname}"
                        + (f".{suffix}" if suffix else "")
                        + ".nec"
                    )
                    header = (
                        f"CM antennaknobs catalog design {dotted} ({rung} mesh, {gname} ground)\n"
                        f"CM {b.freq} MHz; MIT licence, github.com/stevenmburns/antennaknobs\n"
                    )
                    if note:
                        header += f"CM {note}\n"
                    # newline="\n": the same commit writes the same BYTES on
                    # every platform — the release lane is Windows, and its
                    # first publish differed from a Linux export on every
                    # deck by CRLF alone (#1376). NEC-5 reads either.
                    (out / name).write_text(
                        header
                        + deck.replace("CM antennaknobs NEC5Engine deck\n", "", 1),
                        newline="\n",
                    )
                    written.append(
                        {"design": dotted, "rung": rung, "ground": gname, "file": name}
                    )
    (out / "manifest.json").write_text(
        json.dumps({"written": written, "skipped": skipped}, indent=1), newline="\n"
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
