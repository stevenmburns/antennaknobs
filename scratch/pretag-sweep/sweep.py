"""Pre-tag performance sweep: ONE case, solved cold in THIS (fresh) process.

  python sweep.py --expect-tree <momwire tree> --case '<json>'   -> one JSON line
  python sweep.py --expect-tree <momwire tree> --enumerate      -> design census

A case is {"id", "kind", "design", "ground", "engine", ...}:
  kind "catalog" : a REGISTRY design, solved the way the web adapter solves it
                   (`_build_builder` -> `_apply_plane` -> `_make_momwire_engine`),
                   timing only the cold `impedance()` (plus engine construction).
  kind "file"    : a .nec deck through antennaknobs' file-design path
                   (`builder_from_file` -> `_make_example`), then as above.
  kind "raw"     : the momwire#1131 surface screen in plain momwire
                   (`screen_deck_1131.deck`), `compute_impedance()`.
ground: "free" | "fast" (refl-coef) | "sommerfeld" (finite, 13 / 0.005).
engine: "default" (the design's default momwire backend, else bspline)
        | "razor-2p" (RazorSolver, nec5_quadrature=True).

Outcome classification lives here for Python-level failures; a process that
dies (timeout, address-space kill) is classified by the driver.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import resource
import sys
import time
import traceback
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent

_REFUSAL = re.compile(
    r"refus|not supported|unsupported|does not (serve|support)|cannot (be )?solve"
    r"|requires? (a |the )?(sommerfeld|finite)|only (valid|meaningful|defined)",
    re.I,
)


def _vmhwm_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return float("nan")


def _read(p: Path):
    return p.read_text().strip() if p.is_file() else None


def _check_tree(expect: str) -> dict:
    import momwire

    f = str(Path(momwire.__file__).resolve())
    want = str((Path(expect) / "src").resolve())
    if not f.startswith(want + os.sep):
        raise SystemExit(f"momwire imported from {f}, expected under {want}")
    sha_file = Path(expect) / ".sweep_sha"
    sha = sha_file.read_text().split() if sha_file.is_file() else []
    import antennaknobs

    version = getattr(momwire, "__version__", None)
    pyproject = Path(expect) / "pyproject.toml"
    if version is None and pyproject.is_file():
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.M)
        version = m.group(1) if m else None
    return {
        "momwire_file": f,
        "momwire_version": version,
        "momwire_sha": sha[0] if sha else None,
        "momwire_describe": sha[1] if len(sha) > 1 else None,
        "ak_file": str(Path(antennaknobs.__file__).resolve()),
        "ak_sha": _read(Path(antennaknobs.__file__).resolve().parents[1] / ".ak_sha"),
    }


def _ground_req(ground: str) -> dict:
    if ground == "free":
        return {"ground": False}
    if ground == "fast":
        return {"ground": True, "ground_model": "fast"}
    if ground == "sommerfeld":
        return {"ground": True, "ground_model": "sommerfeld"}
    raise ValueError(ground)


def _example_for(case: dict):
    from antennaknobs.web import adapter
    from antennaknobs.web.examples import REGISTRY

    if case["kind"] == "catalog":
        return REGISTRY[case["design"]]
    from antennaknobs.file_designs import builder_from_file

    deck = Path(case["deck"])
    if not deck.is_absolute():
        deck = HERE / deck
    cls = builder_from_file(str(deck))
    name = f"user.{deck.stem}"
    ex = adapter._make_example(name, cls, defer_hints=True)
    REGISTRY[name] = ex
    return ex


def _default_model(ex) -> str:
    from antennaknobs.web import adapter

    db = ex.default_backend
    return db if db in adapter._MOMWIRE_MODELS else "bspline"


def _solve_ak(case: dict) -> dict:
    # examples first: importing adapter first trips the registry's circular
    # import (examples/__init__ calls adapter.register_all()).
    from antennaknobs.web.examples import REGISTRY  # noqa: F401
    from antennaknobs.web import adapter

    ex = _example_for(case)
    cls = ex.builder_cls
    model = _default_model(ex) if case["engine"] == "default" else case["engine"]
    out = {"model": model}
    if case["engine"] != "default":
        cov = adapter.design_backend_coverage(ex.name)
        ref = (cov.get("refusals") or {}).get(case["engine"])
        if ref:
            out.update(outcome="refused", message=f"coverage: {ref}")
            return out
    req = {"momwire_model": model, **_ground_req(case["ground"])}
    req.update(case.get("params") or {})
    vp = adapter._variant_params(cls, req.get("variant"))
    freq = float(vp.get("freq", 14.0))
    builder = adapter._build_builder(cls, req)
    builder.freq = freq
    if "design_freq" in cls.default_params:
        builder.design_freq = freq
    adapter._apply_plane(builder, req)
    out["freq_mhz"] = freq
    try:
        out["n_segs"] = int(sum(int(w[2]) for w in builder.build_wires()))
    except Exception:  # noqa: BLE001 — census field only
        out["n_segs"] = None
    out["vmhwm_before_mb"] = _vmhwm_mb()
    t0 = time.perf_counter()
    eng = adapter._make_momwire_engine(req, builder)
    zs = list(eng.impedance())
    out["wall_s"] = time.perf_counter() - t0
    out["z"] = [[float(complex(z).real), float(complex(z).imag)] for z in zs]
    out["solver_class"] = getattr(getattr(eng, "_solver", None), "__name__", None)
    return out


def _solve_raw(case: dict) -> dict:
    import numpy as np

    sys.path.insert(0, str(HERE))
    from screen_deck_1131 import deck

    p = case.get("params") or {}
    ground = {"free": "free", "fast": "refl-coef", "sommerfeld": "sommerfeld"}[
        case["ground"]
    ]
    out = {"model": "bspline-raw"}
    s = deck(int(p.get("radials", 48)), ground=ground)
    out["vmhwm_before_mb"] = _vmhwm_mb()
    t0 = time.perf_counter()
    z, c = s.compute_impedance()
    out["wall_s"] = time.perf_counter() - t0
    z = np.atleast_1d(z)
    out["z"] = [[float(complex(v).real), float(complex(v).imag)] for v in z]
    out["n_basis"] = int(np.asarray(c).shape[0])
    return out


def run_case(case: dict, expect: str) -> dict:
    rec = {"id": case["id"], "case": case}
    rec.update(_check_tree(expect))
    rec["omp"] = os.environ.get("OMP_NUM_THREADS")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = _solve_raw(case) if case["kind"] == "raw" else _solve_ak(case)
        res.setdefault("outcome", "ok")
        rec.update(res)
    except MemoryError as exc:
        rec.update(outcome="oom", message=repr(exc)[:500])
    except Exception as exc:  # noqa: BLE001 — every failure is a RESULT here
        msg = f"{type(exc).__name__}: {exc}"
        refused = isinstance(exc, NotImplementedError) or bool(_REFUSAL.search(msg))
        if "bad_alloc" in msg or "Unable to allocate" in msg:
            rec["outcome"] = "oom"
        else:
            rec["outcome"] = "refused" if refused else "error"
        rec["message"] = msg[:800]
        rec["traceback_tail"] = traceback.format_exc()[-1200:]
    rec["ru_maxrss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    rec["vmhwm_mb"] = _vmhwm_mb()
    return rec


def enumerate_designs(expect: str) -> dict:
    from antennaknobs.web.examples import REGISTRY

    info = _check_tree(expect)
    designs = []
    for name, ex in REGISTRY.items():
        if name.startswith("user."):
            continue
        d = {
            "design": name,
            "ground_requirement": ex.ground_requirement,
            "default_backend": ex.default_backend,
            "has_buried_wire": bool(ex.has_buried_wire),
        }
        try:
            from antennaknobs.web import adapter

            b = adapter._build_builder(ex.builder_cls, {})
            ws = b.build_wires()
            try:
                d["n_segs"] = int(sum(int(w[2]) for w in ws))
            except (TypeError, ValueError):
                d["n_segs"] = None
            zmin = min(min(float(w[0][2]), float(w[1][2])) for w in ws)
            d["zmin"] = zmin
            d["ground_connected"] = zmin <= 1e-3
        except Exception as exc:  # noqa: BLE001 — census field only
            d["census_error"] = repr(exc)[:200]
            d["ground_connected"] = None
        designs.append(d)
    return {"tree": info, "designs": designs}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-tree", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--case")
    g.add_argument("--enumerate", action="store_true")
    a = ap.parse_args()
    if a.enumerate:
        print(json.dumps(enumerate_designs(a.expect_tree)))
        return
    rec = run_case(json.loads(a.case), a.expect_tree)
    print("SWEEP_RESULT " + json.dumps(rec), flush=True)


if __name__ == "__main__":
    main()
