"""Staleness guard: prove the interpreter that will solve is the one we think.

    python scratch/catalog-razor-nec5-bs2/verify_env.py [--json]

Run IN THE HARNESS'S OWN INTERPRETER before the first cell, and written into the
records file as its first line so the provenance travels with the data rather
than with a commit message.

Why each check earns its place (all four have failed silently here before):

  * `momwire.__file__` — the venv has both packages editable, so an import can
    resolve into site-packages instead of the submodule working tree and nothing
    in a test run says so.
  * every `*.cpython-*.so` imports, with `__file__` in the source tree — a
    `setup.py` build that fails per-extension WARNS and exits 0, leaving a stale
    `.so`, and `momwire/build/` plus sibling venvs hold copies that are not the
    live one. Importing is the only check that separates an accelerated tree
    from a silently pure-Python one.
  * `importlib.metadata` versions — editable metadata does NOT follow a
    submodule checkout. This is the check that was WRONG for the b9bc3e2f0 run:
    the code and the `.so` were right and the metadata read 0.53.0 against a
    pyproject saying 0.55.0.
  * the accelerator VARIANT — momwire ships `_avx2` and `_sse2` builds behind a
    dispatching module name, and momwire#1064's own gates record last-bit
    differences BETWEEN the variants. A run that does not say which one it used
    cannot be compared bit-for-bit with one that does.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as md
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _git(*args, cwd=ROOT):
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001 -- absence is a recorded value, not a crash
        return None


def collect(nec5_exe: str | None = None, dev_mode: bool = False) -> dict:
    """`dev_mode=True` means the run INTENDS momwire to sit ahead of the pointer.

    The pointer check then still runs and is still recorded -- it just stops
    gating `all_checks_pass`, because in dev mode a mismatch is the configuration
    rather than staleness. Suppressing the whole guard for a dev run would throw
    away the six checks that still mean something (import paths, variant,
    versions, cleanliness); leaving it in place unchanged would make the guard
    cry wolf on every dev run, which is how a guard gets bypassed by hand.
    """
    mw = importlib.import_module("momwire")
    ak = importlib.import_module("antennaknobs")
    sub = ROOT / "momwire" / "src" / "momwire"

    sos = {}
    for path in sorted(sub.glob("*.cpython-*.so")):
        name = path.name.split(".")[0]
        try:
            mod = importlib.import_module(f"momwire.{name}")
            sos[name] = {
                "imported": True,
                "file": mod.__file__,
                "in_source_tree": str(sub) in str(mod.__file__),
            }
        except Exception as e:  # noqa: BLE001 -- a failed import is the finding
            sos[name] = {"imported": False, "error": f"{type(e).__name__}: {e}"}

    variant = {}
    for dispatch in ("_accelerators", "_near_interface_accel"):
        try:
            mod = importlib.import_module(f"momwire.{dispatch}")
            variant[dispatch] = Path(mod.__file__).name
        except Exception as e:  # noqa: BLE001
            variant[dispatch] = f"{type(e).__name__}: {e}"

    out = {
        "record": "provenance",
        "ak_sha": _git("rev-parse", "HEAD"),
        "ak_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "ak_dirty": _git("status", "--porcelain") or "",
        "ak_recorded_momwire_pointer": (
            _git("ls-tree", "HEAD", "momwire") or ""
        ).split()[2]
        if _git("ls-tree", "HEAD", "momwire")
        else None,
        "momwire_sha": _git("rev-parse", "HEAD", cwd=ROOT / "momwire"),
        "momwire_describe": _git(
            "describe", "--tags", "--always", cwd=ROOT / "momwire"
        ),
        "momwire_dirty": _git("status", "--porcelain", cwd=ROOT / "momwire") or "",
        "momwire_file": mw.__file__,
        "momwire_in_source_tree": str(sub) in str(mw.__file__),
        "antennaknobs_file": ak.__file__,
        "version_momwire": md.version("momwire"),
        "version_antennaknobs": md.version("antennaknobs"),
        "extensions": sos,
        "accelerator_variant": variant,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "nec5_exe": nec5_exe,
        "dev_mode": dev_mode,
    }
    out["checks"] = {
        "momwire_in_source_tree": out["momwire_in_source_tree"],
        "all_extensions_import": all(v.get("imported") for v in sos.values()),
        "all_extensions_in_source_tree": all(
            v.get("in_source_tree") for v in sos.values()
        ),
        "momwire_version_0_55_0": out["version_momwire"] == "0.55.0",
        "antennaknobs_version_0_78_0": out["version_antennaknobs"] == "0.78.0",
        "momwire_at_recorded_pointer": out["momwire_sha"]
        == out["ak_recorded_momwire_pointer"],
        "momwire_clean": out["momwire_dirty"] == "",
    }
    gating = dict(out["checks"])
    if dev_mode:
        # Recorded, not gating -- and named so a reader of the JSONL can see the
        # check ran and was deliberately excused.
        out["dev_mode_excused"] = ["momwire_at_recorded_pointer"]
        gating.pop("momwire_at_recorded_pointer", None)
    out["all_checks_pass"] = all(gating.values())
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--nec5-exe", default=None)
    ap.add_argument(
        "--dev-mode",
        action="store_true",
        help="momwire is expected to run ahead of the recorded pointer",
    )
    a = ap.parse_args(argv)
    rec = collect(a.nec5_exe, dev_mode=a.dev_mode)
    if a.json:
        print(json.dumps(rec))
        return 0 if rec["all_checks_pass"] else 1
    print(f"AK       {rec['ak_sha']}  ({rec['ak_branch']})")
    print(f"momwire  {rec['momwire_sha']}  {rec['momwire_describe']}")
    print(f"         recorded pointer {rec['ak_recorded_momwire_pointer']}")
    print(
        f"versions momwire {rec['version_momwire']}  antennaknobs {rec['version_antennaknobs']}"
    )
    print(f"momwire.__file__ {rec['momwire_file']}")
    for k, v in rec["accelerator_variant"].items():
        print(f"variant  {k} -> {v}")
    print("extensions:")
    for k, v in rec["extensions"].items():
        mark = "ok " if v.get("imported") and v.get("in_source_tree") else "BAD"
        print(f"  {mark} {k}  {v.get('file') or v.get('error')}")
    print("checks:")
    excused = set(rec.get("dev_mode_excused") or ())
    for k, v in rec["checks"].items():
        mark = "EXCUSED (dev mode)" if k in excused else ("PASS" if v else "FAIL")
        print(f"  {mark:18s}  {k}")
    print(f"\nALL CHECKS {'PASS' if rec['all_checks_pass'] else 'FAIL'}")
    return 0 if rec["all_checks_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
