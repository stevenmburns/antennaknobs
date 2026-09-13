"""antennaknobs#1485 export census (PLAN.md, gates PC1 and PC2).

Records every catalog design's and every nec_portal deck's NEC-2 export text,
or its refusal, plus an AST scan of designs/ for `Load(..., z=...)` calls. Run
it once before the fix and once after, then diff the two records:

  PYTHONPATH=<worktree>/src python scratch/1485-export-ld4/census_export.py \\
      --out scratch/1485-export-ld4/census_before.json
  python scratch/1485-export-ld4/census_export.py --diff before.json after.json

A portal deck is read the way the app reads a design file: copied to a `.nec`
path and loaded with `builder_from_file`, with its own ground as the default.
The CM title is pinned, because the default title would carry the temp path.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import importlib
import json
import pkgutil
import shutil
import tempfile
import warnings
from pathlib import Path

TITLE = "antennaknobs#1485 census"


def _z_load_calls(designs_dir):
    hits = []
    for path in sorted(designs_dir.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "Load" and any(k.arg == "z" for k in node.keywords):
                hits.append(f"{path.relative_to(designs_dir)}:{node.lineno}")
    return hits


def _export(builder, **kw):
    from antennaknobs.nec_export import export_nec

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return "ok", export_nec(builder, include_rp=False, **kw)
    except Exception as exc:  # noqa: BLE001 - a refusal is a recorded outcome
        return "refused", f"{type(exc).__name__}: {exc}"


def _z_loads(builder):
    from antennaknobs.network import Load

    try:
        net = builder.build_network()
    except Exception:  # noqa: BLE001 - no buildable network means no loads
        return 0
    branches = getattr(net, "branches", None) or ()
    return sum(1 for br in branches if isinstance(br, Load) and br.z is not None)


def census():
    import antennaknobs
    import antennaknobs.designs as designs_pkg
    import momwire
    from antennaknobs.cli import _GROUND_UNSET, file_ground_default
    from antennaknobs.file_designs import builder_from_file

    rec = {
        "antennaknobs": antennaknobs.__file__,
        "z_load_calls": _z_load_calls(Path(designs_pkg.__file__).parent),
        "catalog": {},
        "portal": {},
    }
    for m in pkgutil.walk_packages(designs_pkg.__path__, designs_pkg.__name__ + "."):
        name = m.name.removeprefix("antennaknobs.designs.")
        try:
            builder = importlib.import_module(m.name).Builder()
        except Exception as exc:  # noqa: BLE001 - unimportable designs are gated elsewhere
            rec["catalog"][name] = {"status": "no-builder", "text": type(exc).__name__}
            continue
        status, text = _export(builder)
        rec["catalog"][name] = {
            "z_loads": _z_loads(builder),
            "status": status,
            "text": text,
        }

    portal = Path(momwire.__file__).resolve().parents[2] / "tests/fixtures/nec_portal"
    with tempfile.TemporaryDirectory() as tmp:
        for deck in sorted(portal.glob("*.deck")):
            lines = deck.read_text(errors="replace").splitlines()
            ld4 = [ln for ln in lines if ln.split()[:2] == ["LD", "4"]]
            nec = Path(tmp) / (deck.stem + ".nec")
            shutil.copyfile(deck, nec)
            try:
                cls = builder_from_file(str(nec))
            except (Exception, SystemExit) as exc:  # noqa: BLE001 - recorded, not raised
                rec["portal"][deck.name] = {
                    "ld4": ld4,
                    "status": "no-builder",
                    "text": f"{type(exc).__name__}: {exc}",
                }
                continue
            ground = file_ground_default(_GROUND_UNSET, cls)
            kw = {"title": TITLE}
            if ground is not _GROUND_UNSET:
                kw["ground"] = ground
            status, text = _export(cls(), **kw)
            rec["portal"][deck.name] = {"ld4": ld4, "status": status, "text": text}
    return rec


def diff(before_path, after_path):
    a = json.loads(Path(before_path).read_text())
    b = json.loads(Path(after_path).read_text())
    print("z_load_calls before", a["z_load_calls"], "after", b["z_load_calls"])
    print(
        "catalog designs carrying a z-load: before",
        sum(v.get("z_loads", 0) > 0 for v in a["catalog"].values()),
        "after",
        sum(v.get("z_loads", 0) > 0 for v in b["catalog"].values()),
    )
    for section in ("catalog", "portal"):
        names = sorted(set(a[section]) | set(b[section]))
        statuses = {}
        for n in names:
            s = a[section].get(n, {}).get("status")
            statuses[s] = statuses.get(s, 0) + 1
        changed = [n for n in names if a[section].get(n) != b[section].get(n)]
        print(f"{section}: {len(names)} entries {statuses}; {len(changed)} changed")
        for n in changed:
            print(f"  == {n}")
            ta = (a[section].get(n) or {}).get("text", "").splitlines()
            tb = (b[section].get(n) or {}).get("text", "").splitlines()
            for line in difflib.unified_diff(ta, tb, lineterm="", n=0):
                print("    " + line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"))
    args = ap.parse_args()
    if args.diff:
        diff(*args.diff)
        return
    rec = census()
    args.out.write_text(json.dumps(rec, indent=1))
    print(
        "catalog",
        len(rec["catalog"]),
        "portal",
        len(rec["portal"]),
        "z_load_calls",
        rec["z_load_calls"],
    )


if __name__ == "__main__":
    main()
