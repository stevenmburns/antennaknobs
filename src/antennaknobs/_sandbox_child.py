"""The sandboxed side of `design_sandbox` (AK#2149 unit 2). Do not import.

Run as ``python -I -m antennaknobs._sandbox_child`` in a fresh scratch
folder. It reads ONE JSON request on stdin::

    {"filename": "x.py", "source": "...", "want": "static" | "snapshot",
     "params": <design_snapshot data> | null, "limits": {...}}

and writes ONE JSON reply to the stdout it was started with::

    {"ok": true, "data": ...}   or   {"ok": false, "error": "...", "kind": "..."}

Run with ``--serve`` it is a WARM worker for one design (AK#2157): the first
line on stdin is ``{"filename", "source", "limits"}``, answered with one reply
line once the design is loaded; every later line is ``{"params": ...}``,
answered with one snapshot reply line carrying ``"retire": true`` when the
parent should replace it (it forked, ran out of memory, or has used half its
CPU allowance, which an rlimit counts over the process's whole life).

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
    """The tasks RLIMIT_NPROC counts for this user: its THREADS, not just
    its processes (a desktop's browser alone runs hundreds)."""
    uid, n = os.getuid(), 0
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                if os.stat(f"/proc/{d}").st_uid != uid:
                    continue
                with open(f"/proc/{d}/status") as f:
                    for line in f:
                        if line.startswith("Threads:"):
                            n += int(line.split()[1])
                            break
            except (OSError, ValueError):
                pass
    return n


NOBODY = 65534


def _preload() -> None:
    """Import what every design needs while the files are surely readable:
    once the child drops to nobody, a checkout in a private home folder is
    not, and a design should not depend on file permissions to get the
    framework. design_snapshot's allowlist imports every spec module."""
    import antennaknobs  # noqa: F401
    import antennaknobs.builder  # noqa: F401
    import antennaknobs.touchstone  # noqa: F401
    from antennaknobs import design_snapshot

    design_snapshot.allowed_types()


def _drop_root() -> None:
    """A server running as root (the container) runs the design as nobody:
    no supplementary groups, then gid, then uid, irreversibly."""
    if os.getuid() != 0 and os.geteuid() != 0:
        return
    os.setgroups([])
    os.setgid(NOBODY)
    os.setuid(NOBODY)
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("could not drop root")


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


def _kill_my_group(me: int) -> int:
    """SIGKILL every other process in this worker's process group (what the
    design forked during the request) and reap the ones that are ours, so
    they stop counting against RLIMIT_NPROC. Returns how many there were."""
    import signal
    import time

    def stat(pid):
        with open(f"/proc/{pid}/stat") as f:
            # pid (comm) state ppid pgrp ...: comm may hold spaces.
            return f.read().rsplit(")", 1)[1].split()

    # Never this process or what it runs under: in the jail's pid namespace
    # bubblewrap's init (pid 1) can share the group, and killing it ends the
    # namespace, this worker with it.
    spare, pid = {me}, me
    while pid > 1:
        try:
            pid = int(stat(pid)[1])
        except (OSError, ValueError, IndexError):
            break
        spare.add(pid)
    pgrp = os.getpgrp()
    victims = []
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) in spare:
            continue
        try:
            if int(stat(d)[2]) == pgrp:
                victims.append(int(d))
        except (OSError, ValueError, IndexError):
            pass
    for pid in victims:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    end = time.monotonic() + 2.0
    while time.monotonic() < end:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid == 0:
            time.sleep(0.01)
    return len(victims)


def _ran_out_of_memory(data) -> bool:
    return isinstance(data, dict) and any(
        isinstance(v, dict) and str(v.get("__error__", "")).startswith("MemoryError")
        for v in data.values()
    )


def serve() -> int:
    me = os.getpid()
    out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    inp = os.fdopen(os.dup(0), "r", encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    sys.stdin = open(os.devnull)  # noqa: SIM115 — the design's stdin, for its life

    def reply(obj) -> None:
        out.write(json.dumps(obj, allow_nan=False) + "\n")
        out.flush()

    try:
        init = json.loads(inp.readline())
        _preload()
        _drop_root()
        _apply_limits(init["limits"])
        cpu_budget = float(init["limits"]["cpu_s"])
    except Exception as e:  # noqa: BLE001 — a malformed request is reported to the parent
        reply({"ok": False, "kind": "request", "error": f"{type(e).__name__}: {e}"})
        return 2
    from antennaknobs import design_snapshot as ds

    try:
        cls = _load_builder(init["filename"], init["source"])
        ready = {"ok": True, "data": None}
    except MemoryError:
        ready = {"ok": False, "kind": "memory", "error": "the design ran out of memory"}
    except Exception as e:  # noqa: BLE001 — the design's failure is the reply
        ready = {
            "ok": False,
            "kind": "design",
            "error": f"{type(e).__name__}: {e}"[:2000],
        }
    if os.getpid() != me:
        os._exit(0)
    forked = _kill_my_group(me)
    reply(ready)
    if not ready["ok"]:
        return 0
    for line in inp:
        oom = False
        try:
            params = json.loads(line).get("params")
            b = cls(ds.decode(params)) if params is not None else cls()
            data = ds.snapshot(b)
            oom = _ran_out_of_memory(data)
            text = json.dumps({"ok": True, "data": data}, allow_nan=False)
        except MemoryError:
            oom = True
            text = json.dumps(
                {"ok": False, "kind": "memory", "error": "the design ran out of memory"}
            )
        except Exception as e:  # noqa: BLE001 — the design's failure is the reply
            text = json.dumps(
                {
                    "ok": False,
                    "kind": "design",
                    "error": f"{type(e).__name__}: {e}"[:2000],
                }
            )
        if os.getpid() != me:
            os._exit(0)
        forked += _kill_my_group(me)
        ru = resource.getrusage(resource.RUSAGE_SELF)
        retire = bool(forked or oom or ru.ru_utime + ru.ru_stime > cpu_budget / 2)
        out.write(text[:-1] + f', "retire": {"true" if retire else "false"}}}\n')
        out.flush()
        if retire:
            return 0
    return 0


def main() -> int:
    me = os.getpid()
    out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    try:
        req = json.loads(sys.stdin.read())
        _preload()
        _drop_root()
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
    if os.getpid() != me:
        # A forked copy of the design that ran on past its fork: only the
        # child the parent started may answer, or two replies would garble.
        os._exit(0)
    out.write(text)
    out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(serve() if sys.argv[1:] == ["--serve"] else main())
