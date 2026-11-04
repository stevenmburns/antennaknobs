"""The sandboxed side of `design_sandbox` (AK#2149 unit 2). Do not import.

Run as ``python -I -m antennaknobs._sandbox_child`` in a fresh scratch
folder. It reads ONE JSON request on stdin::

    {"filename": "x.py", "source": "...", "want": "static" | "snapshot",
     "params": <design_snapshot data> | null, "limits": {...}}

and writes ONE JSON reply to the stdout it was started with::

    {"ok": true, "data": ...}   or   {"ok": false, "error": "...", "kind": "..."}

Before any design code runs it lowers its own resource limits (soft and hard,
so the design cannot raise them back) and points ``sys.stdout`` at stderr, so
a design that prints cannot corrupt the reply. Everything after that is the
design's: this process is disposable and the parent kills its whole process
group when it is done or out of time.
"""

from __future__ import annotations

import json
import os
import resource
import sys


def _nprocs_of_this_user() -> int:
    uid, n = os.getuid(), 0
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                if os.stat(f"/proc/{d}").st_uid == uid:
                    n += 1
            except OSError:
                pass
    return n


def _limit(which, soft, hard=None):
    hard = soft if hard is None else hard
    _, cur_hard = resource.getrlimit(which)
    if cur_hard != resource.RLIM_INFINITY:
        soft, hard = min(soft, cur_hard), min(hard, cur_hard)
    resource.setrlimit(which, (soft, hard))


def _apply_limits(lim: dict) -> None:
    mb = 1024 * 1024
    _limit(resource.RLIMIT_AS, int(lim["memory_mb"]) * mb)
    # Soft CPU limit raises SIGXCPU, the hard one a second later SIGKILL.
    cpu = int(lim["cpu_s"])
    _limit(resource.RLIMIT_CPU, cpu, cpu + 1)
    _limit(resource.RLIMIT_FSIZE, int(lim["file_mb"]) * mb)
    _limit(resource.RLIMIT_NOFILE, int(lim["open_files"]))
    _limit(resource.RLIMIT_CORE, 0)
    # RLIMIT_NPROC counts every process of this user, not just ours, so the
    # cap is what already runs plus a small allowance.
    _limit(resource.RLIMIT_NPROC, _nprocs_of_this_user() + int(lim["extra_processes"]))


def _load_builder(filename: str, source: str):
    import importlib.util

    from antennaknobs.builder import AntennaBuilder

    path = os.path.join(os.getcwd(), filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(source)
    spec = importlib.util.spec_from_file_location("visitor_design", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["visitor_design"] = mod
    spec.loader.exec_module(mod)
    cls = getattr(mod, "Builder", None)
    if not (isinstance(cls, type) and issubclass(cls, AntennaBuilder)):
        raise TypeError(f"{filename} defines no Builder (an AntennaBuilder subclass)")
    return cls


def main() -> int:
    out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    try:
        req = json.loads(sys.stdin.read())
        _apply_limits(req["limits"])
    except Exception as e:  # noqa: BLE001 — a malformed request is reported to the parent
        out.write(
            json.dumps(
                {"ok": False, "kind": "request", "error": f"{type(e).__name__}: {e}"}
            )
        )
        return 2
    try:
        from antennaknobs import design_snapshot as ds

        cls = _load_builder(req["filename"], req["source"])
        if req["want"] == "static":
            data = ds.static(cls)
        else:
            params = req.get("params")
            b = cls(ds.decode(params)) if params is not None else cls()
            data = ds.snapshot(b)
        text = json.dumps({"ok": True, "data": data}, allow_nan=False)
    except MemoryError:
        text = json.dumps(
            {"ok": False, "kind": "memory", "error": "the design ran out of memory"}
        )
    except Exception as e:  # noqa: BLE001 — the design's failure is the reply
        text = json.dumps(
            {"ok": False, "kind": "design", "error": f"{type(e).__name__}: {e}"[:2000]}
        )
    out.write(text)
    out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
