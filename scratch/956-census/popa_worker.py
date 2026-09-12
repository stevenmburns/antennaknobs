"""One cell of the Population A census: one (design, variant, mesh, engine) -> JSON.

CHILD PROCESS ON PURPOSE. The two momwire commits are two checkouts, selected by
PYTHONPATH, so "which momwire answered" is a property of the process rather than
of an import-time switch inside one. It also means a refusal or a crash on one
cell cannot take the census with it, and the thread pinning is per process.

    PYTHONPATH=<checkout>/src python popa_worker.py --design ... --variant ... \
        --nn 21 --engine momwire

Prints one JSON object. `momwire_provenance` carries the import path, the
checkout's commit, and a content hash of `_crossing_fill.py` plus the token
counts that tell the two spellings apart (`dzpW`, `TW`) -- three independent
ways, because both checkouts report version 0.53.0 and a version string cannot
distinguish them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "nec5_corpus"))

SOIL_A = (13.0, 0.005)  # the app's DEFAULT_GROUND, and #956's soil A


def builder_for(design: str, variant: str, nn: int):
    import importlib

    # `antennaknobs.web.examples` first: importing `web.adapter` directly trips
    # a circular import (examples/__init__ calls back into adapter.register_all
    # while adapter is still executing). The package import binds it.
    import antennaknobs.web.examples  # noqa: F401
    from antennaknobs.web.adapter import resolve_variant_params

    cls = importlib.import_module(f"antennaknobs.designs.{design}").Builder
    params = dict(resolve_variant_params(cls, variant))
    b = cls(params=params) if variant != "default" else cls()
    # The refinement rung is the design's own knob, set after construction --
    # the same way `export_catalog_nec5.py` writes its refined rung, so the
    # ladder is the catalog's mesh doubled and not a different geometry.
    b.nominal_nsegs = nn
    return b


def momwire_provenance() -> dict:
    import momwire

    src = Path(momwire.__file__).resolve().parent
    cf = src / "_crossing_fill.py"
    bi = src / "_below_interface.py"
    text = cf.read_text(encoding="utf-8")
    below = bi.read_text(encoding="utf-8")
    commit = "?"
    try:
        commit = (
            subprocess.run(
                ["git", "-C", str(src), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
            or "?"
        )
    except OSError:
        pass
    return {
        "import_path": str(src),
        "commit": commit,
        "crossing_fill_sha256": hashlib.sha256(text.encode()).hexdigest()[:16],
        # `_below_interface.py` separates the middle commit from the pointer the
        # way `_crossing_fill.py` separates main from the middle: one file's hash
        # moves per leg, so a row can say which of the two changes it saw.
        "below_interface_sha256": hashlib.sha256(below.encode()).hexdigest()[:16],
        "near_q_factor": len(re.findall(r"near_q_factor", below)),
        "dzpW": len(re.findall(r"dzpW", text)),
        "dzW": len(re.findall(r"(?<!dzp)dzW", text)),
        "TW": len(re.findall(r"\bTW\b", text)),
        "version": getattr(momwire, "__version__", "?"),
    }


def run_momwire(b) -> dict:
    from antennaknobs.engines.momwire import MomwireEngine

    eng = MomwireEngine(b, ground=("finite",) + SOIL_A, ground_z=0.0)
    out = {"engine": "momwire", "momwire_provenance": momwire_provenance()}
    try:
        z = complex(eng.impedance()[0])
        out.update(status="ok", z_re=z.real, z_im=z.imag)
    except Exception as e:  # noqa: BLE001 -- a refusal is a result here, recorded by name
        out.update(status="refused", error=f"{type(e).__name__}: {e}"[:300])
    try:
        out["nsegs"] = int(sum(w.n_seg for w in eng._wires()))
    except Exception:  # noqa: BLE001 -- segment bookkeeping must never decide the row
        pass
    return out


def run_nec5(b, exe: str) -> dict:
    from nec5_corpus import _aip

    from antennaknobs.engines.nec5 import NEC5Engine

    eng = NEC5Engine(b, ground=("finite",) + SOIL_A)
    deck = eng.deck([b.freq])
    out = {
        "engine": "nec5",
        "exe": exe,
        "exe_sha256": hashlib.sha256(Path(exe).read_bytes()).hexdigest()[:16],
        "deck_sha256": hashlib.sha256(deck.encode()).hexdigest()[:16],
        "ge_card": next((ln for ln in deck.splitlines() if ln.startswith("GE")), "?"),
        "gw_cards": sum(1 for ln in deck.splitlines() if ln.startswith("GW")),
        "nsegs": sum(
            int(ln.split()[2]) for ln in deck.splitlines() if ln.startswith("GW")
        ),
    }
    with tempfile.TemporaryDirectory(prefix="nec5_956_") as td:
        (Path(td) / "m.nec").write_text(deck)
        proc = subprocess.run(
            [exe],
            input="m.nec\nm.out\n\n",
            text=True,
            capture_output=True,
            cwd=td,
            timeout=1800,
        )
        op = Path(td) / "m.out"
        text = op.read_text(errors="replace") if op.is_file() else ""
        out["exit_code"] = proc.returncode
    rows = _aip(text)
    if rows:
        out.update(
            status="ok",
            z_re=rows[0][2],
            z_im=rows[0][3],
            tag=rows[0][0],
            seg=rows[0][1],
            aip_rows=len(rows),
        )
    else:
        out.update(status="no-impedance", error="no ANTENNA INPUT PARAMETERS row")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--variant", default="default")
    ap.add_argument("--nn", type=int, required=True)
    ap.add_argument("--engine", choices=("momwire", "nec5"), required=True)
    ap.add_argument("--exe", default=os.environ.get("NEC5_EXE", ""))
    a = ap.parse_args(argv)

    rec = {"design": a.design, "variant": a.variant, "nn": a.nn}
    try:
        b = builder_for(a.design, a.variant, a.nn)
        rec["freq_mhz"] = float(b.freq)
        rec.update(run_momwire(b) if a.engine == "momwire" else run_nec5(b, a.exe))
    except Exception as e:  # noqa: BLE001 -- the cell reports its own failure
        rec.update(
            engine=a.engine,
            status="cell-failed",
            error=f"{type(e).__name__}: {e}"[:300],
        )
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
