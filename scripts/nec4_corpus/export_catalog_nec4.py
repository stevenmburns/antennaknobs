"""Write antennaknobs' own catalog designs as NEC-4 decks (MIT, ours to share).

    python scripts/nec4_corpus/export_catalog_nec4.py --out catalog-nec4

The NEC-4 twin of `scripts/nec5_corpus/export_catalog_nec5.py` (AK#1803), with
the same CLI and the same grid: every built-in design at its shipped mesh and
at double that mesh, in free space and over the documented Sommerfeld ground
(eps_r 13, sigma 0.005 S/m), through `nec_export.export_nec(dialect="nec42")`
-- the writer the app's Download NEC-4 item and the NEC-4.2 engine slot use.
So the decks carry that dialect's spellings: feeds on segment centres (odd
parity), ``GN 2 ... NOFILE``, buried wires under ``GE -1``, graded meshes as
chained GW cards, ``EX 6`` current sources.

Designs whose network needs the shared reducer (transmission lines,
transformers, virtual drivers: nothing NEC-4 has a faithful card for) are
written as the per-port structure decks the NEC-4.2 slot actually runs -- one
deck per real port, that port driven by 1 V across its segments -- since the
app solves the network outside NEC-4.2 from the resulting multiport Y. A
manifest.json records what was written and why anything was not.

``--gn3-twins`` also writes every Sommerfeld deck a second time with NEC-4.2's
newer ``GN 3`` in place of ``GN 2`` (the writer's ``sommerfeld=3``, nothing
else changed), and names the pair ``<name>.gn2.nec`` / ``<name>.gn3.nec``: the
input a GN 2 / GN 3 fix is judged on, and the catalog half of
``nec4_corpus.py``'s regression corpus. It is a flag rather than the default
because the default output is the published catalog, whose file names and
grid match the NEC-5 catalog deck for deck (AK#1803); the corpus asks for the
twins explicitly. The manifest records each deck's card-level ground ("free",
"gn2", "gn3") as ``gn`` and its partner as ``twin``.

No NEC-4.2 executable is needed or looked for: writing a deck is not running
the licensed program. The output is deterministic -- the same commit writes
the same bytes (LF line ends on every platform).
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

GROUNDS = {
    "free": "free",
    "somm13": ("finite", 13.0, 0.005),
}

NEC4_NOTE = "NEC-4 (NEC-4.2) syntax"


def _decks(cls, factor: int, ground, sommerfeld: int = 2):
    """``[(suffix, deck text, note)]`` for one design, rung and ground."""
    from antennaknobs.nec_export import (
        deck_engine_cls,
        export_nec,
        export_nec_structure,
    )
    from antennaknobs.network import as_wire

    b = cls()
    b.nominal_nsegs = b.nominal_nsegs * factor
    freq = float(b.freq)
    try:
        return [
            (
                "",
                export_nec(
                    b,
                    ground=ground,
                    include_rp=False,
                    dialect="nec42",
                    sommerfeld=sommerfeld,
                ),
                "",
            )
        ]
    except NotImplementedError as e:
        if "single NEC-4 deck" not in str(e):
            raise
    # The multiport-Y route: the NEC-4.2 slot's own per-port decks
    # (`NEC2Engine._init_route`, which NEC42Engine inherits).
    eng = deck_engine_cls("nec42")(b, ground=ground)
    tag_of = {
        as_wire(t).name: tag
        for tag, t in enumerate(eng.tups, start=1)
        if as_wire(t).name is not None
    }
    names = list(eng._real_port_names)
    out = []
    for k, name in enumerate(names):
        tag = tag_of[eng._port_wire_of[name]]
        sources = [(tag, int(seg), float(w)) for seg, w in eng._port_drive_points[name]]
        out.append(
            (
                f"port{k + 1}",
                export_nec_structure(
                    eng,
                    freq=freq,
                    sources=sources,
                    dialect="nec42",
                    sommerfeld=sommerfeld,
                ),
                f"port {k + 1} of {len(names)} ({name}) driven; the network is "
                "solved outside NEC-4.2 from the multiport Y",
            )
        )
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default="catalog-nec4")
    ap.add_argument("--only", default=None, help="substring filter on family.design")
    ap.add_argument(
        "--gn3-twins",
        action="store_true",
        help="write each Sommerfeld deck as a .gn2.nec / .gn3.nec pair",
    )
    a = ap.parse_args(argv)

    from antennaknobs.cli import list_builtin_designs
    from antennaknobs.nec5_export import catalog_header

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []
    for dotted in list_builtin_designs():
        if a.only and a.only not in dotted:
            continue
        cls = importlib.import_module(f"antennaknobs.designs.{dotted}").Builder
        design_freq = cls().freq
        for rung, factor in (("default", 1), ("refined", 2)):
            for gname, ground in GROUNDS.items():
                somm = gname != "free"
                variants = (2, 3) if (somm and a.gn3_twins) else (2,)
                try:
                    decks = {v: _decks(cls, factor, ground, v) for v in variants}
                except Exception as e:  # noqa: BLE001 — record any refusal or builder failure, keep exporting
                    skipped.append(
                        {
                            "design": dotted,
                            "rung": rung,
                            "ground": gname,
                            "why": f"{type(e).__name__}: {e}"[:200],
                        }
                    )
                    continue
                for v, vdecks in decks.items():
                    gn = f"gn{v}" if somm else "free"
                    for suffix, deck, note in vdecks:
                        stem = (
                            re.sub(r"[^\w.]", "_", dotted)
                            + f".{rung}.{gname}"
                            + (f".{suffix}" if suffix else "")
                        )
                        twin = len(variants) > 1
                        name = stem + (f".{gn}" if twin else "") + ".nec"
                        # The writer's own two CM lines (its class path, and
                        # "exported by") give way to the catalog header the
                        # NEC-5 corpus uses, so the two zips name a design alike.
                        body = deck.split("\n", 2)[2]
                        note_text = f"{NEC4_NOTE}; {note}" if note else NEC4_NOTE
                        if twin:
                            note_text += f"; GN {v} of a GN 2 / GN 3 pair"
                        header = catalog_header(
                            dotted, rung, gname, design_freq, note=note_text
                        )
                        (out / name).write_text(header + body, newline="\n")
                        row = {
                            "design": dotted,
                            "rung": rung,
                            "ground": gname,
                            "file": name,
                            "gn": gn,
                        }
                        if twin:
                            other = 5 - v
                            row["twin"] = f"{stem}.gn{other}.nec"
                        written.append(row)
    (out / "manifest.json").write_text(
        json.dumps({"written": written, "skipped": skipped}, indent=1), newline="\n"
    )
    print(f"wrote {len(written)} decks, skipped {len(skipped)} -> {out}")
    by: dict[str, int] = {}
    for s in skipped:
        by[s["why"][:90]] = by.get(s["why"][:90], 0) + 1
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
