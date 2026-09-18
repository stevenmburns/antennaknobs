"""AK#1579 corpus gate: every EZNEC capture with a NEC-5 printout, imported
through antennaknobs and solved, against the printout's own drive rows."""

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path


def drive_rows(out: str):
    """(tag, abs segment, end code, Z) for each ANTENNA INPUT PARAMETERS row."""
    lines = out.splitlines()
    rows = []
    for i, ln in enumerate(lines):
        if "ANTENNA INPUT PARAMETERS" not in ln:
            continue
        for j in range(i + 1, len(lines)):
            t = lines[j].split()
            if len(t) >= 12 and all(re.fullmatch(r"-?\d+", x) for x in t[:3]):
                rows.append(
                    (int(t[0]), int(t[1]), int(t[2]), complex(float(t[7]), float(t[8])))
                )
            elif rows:
                break
        break
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--engines", default="nec5,bspline")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    root = Path(args.root)
    sys.path.insert(0, str(root / "src"))
    from antennaknobs.engines import MomwireEngine, NEC5Engine
    from antennaknobs.file_designs import builder_from_file
    from momwire import BSplineSolver

    corpus = Path(args.corpus)
    manifest = json.loads((corpus / "manifest.json").read_text())
    engines = args.engines.split(",")

    with Path(args.out).open("w") as fh:
        for cap in manifest["captures"]:
            if not cap.get("printout"):
                continue
            if args.only and cap["id"] not in args.only.split(","):
                continue
            deck_path = corpus / cap["deck"]
            rec = {"id": cap["id"], "deck": Path(cap["deck"]).name}
            ref = drive_rows((corpus / cap["printout"]).read_text(errors="replace"))
            rec["ref"] = [[t, s, e, z.real, z.imag] for t, s, e, z in ref]
            t0 = time.time()
            try:
                cls = builder_from_file(str(deck_path))
                rec["import"] = "ok"
            except Exception as e:  # noqa: BLE001 — a census records every refusal
                rec["import"] = "refused"
                rec["reason"] = f"{type(e).__name__}: {e}"[:400]
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                print(rec["id"], "REFUSED", rec["reason"][:110], flush=True)
                continue
            for name in engines:
                try:
                    if name == "nec5":
                        eng = NEC5Engine(cls(), ground=cls.file_ground)
                    else:
                        eng = MomwireEngine(
                            cls(), ground=cls.file_ground, solver=BSplineSolver
                        )
                    zs = [complex(x) for x in eng.impedance()]
                    rec[name] = [[z.real, z.imag] for z in zs]
                    # Not strict: a deck can drive a port the printout does
                    # not list a row for, and the pairing that IS there is
                    # still the measurement.
                    rec[name + "_err"] = [
                        abs(z - r[3]) / abs(r[3]) for z, r in zip(zs, ref, strict=False)
                    ]
                except Exception as e:  # noqa: BLE001 — a census records every failure
                    rec[name] = None
                    rec[name + "_fail"] = f"{type(e).__name__}: {e}"[:300]
                    rec[name + "_tb"] = traceback.format_exc()[-400:]
            rec["secs"] = round(time.time() - t0, 1)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            print(
                rec["id"],
                rec["deck"][:40],
                {
                    k: [round(e, 5) for e in v]
                    for k, v in rec.items()
                    if k.endswith("_err")
                },
                {k: v for k, v in rec.items() if k.endswith("_fail")},
                rec["secs"],
                flush=True,
            )


if __name__ == "__main__":
    main()
