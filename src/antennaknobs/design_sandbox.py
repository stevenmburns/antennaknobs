"""Run a design ``.py`` you did not write, in a disposable child process (AK#2149 unit 2).

`run_design(source, filename, want=...)` starts ``python -I -m
antennaknobs._sandbox_child`` in a fresh scratch folder, hands it the source
on stdin and reads back ONE JSON reply: `design_snapshot` data, which the
caller `decode`s through the allowlist. Nothing the design returns crosses
as an object.

Two layers, and `sandbox_status()` says which is active:

- **Baseline** (any Linux): the child lowers its own rlimits (address space,
  CPU seconds, file size, open files, processes, no core dumps) before the
  design runs; it gets an empty environment (no tokens, no engine paths) and
  a scratch folder of its own; its whole process group is SIGKILLed on a
  wall-clock deadline; and its reply is capped in size. This bounds what a
  design can COST, not what it can SEE: the child runs as the server's user,
  so it can still read the filesystem and open sockets.
- **Jail** (bubblewrap, when it actually starts on this machine): on top of
  the baseline, no network, a read-only root, a private /tmp and private
  process ids. It is used only if a probe run succeeds (`jail_available`),
  so a host whose kernel or AppArmor policy refuses namespaces falls back to
  the baseline instead of failing every design.

The policy that follows (unit 3): the hosted app accepts a visitor's ``.py``
ONLY when the jail is active. A local install runs the user's own file, where
the baseline's resource bounds are the point.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

JAIL_ENV = "ANTENNAKNOBS_DESIGN_JAIL"  # "auto" (default), "bwrap", or "none"


@dataclass(frozen=True)
class Limits:
    memory_mb: int = 1536
    cpu_s: int = 20
    wall_s: float = 30.0
    file_mb: int = 16
    open_files: int = 256
    extra_processes: int = 32
    max_source_bytes: int = 256 * 1024
    max_reply_bytes: int = 16 * 1024 * 1024


class SandboxError(RuntimeError):
    """The design did not produce a reply. ``kind`` is one of: ``source``
    (refused before running), ``timeout``, ``memory``, ``crash`` (the child
    died), ``reply`` (oversized or not JSON), ``design`` (the design raised),
    ``request``."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


# What the jailed child may see, read-only: the system's programs and
# libraries, /etc, and Python with every directory on this process's import
# path (the venv, an editable checkout's src/). NOT the whole root: a server
# keeps readable things a design has no business with (the app folder, /root,
# /home, /var, /run, Fly's /.fly), and a read-only bind still lets them be read.
_SYSTEM_DIRS = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/lib32", "/libx32", "/etc")

# The unprivileged user a child runs as when the server runs as root (as the
# container does): nobody, so even a bind that is too wide reaches no
# root-only file.
NOBODY = 65534


def _jail_binds() -> list[str]:
    seen: list[str] = []
    made: set[str] = set()
    out: list[str] = []
    paths = list(_SYSTEM_DIRS) + [sys.prefix, sys.base_prefix, sys.exec_prefix]
    paths += [p for p in sys.path if p and os.path.isabs(p)]
    for p in paths:
        p = os.path.normpath(p)
        if not os.path.lexists(p) or any(p == q or p.startswith(q + "/") for q in seen):
            continue
        seen.append(p)
        if os.path.islink(p) and os.path.dirname(p) == "/":
            # bookworm's /lib, /bin, ... are symlinks into /usr: recreate them.
            out += ["--symlink", os.readlink(p), p]
        elif os.path.isdir(p):
            # The parents a bind needs (/app for /app/src, /opt/... for a
            # toolcache Python) do not exist in the jail's fresh root, and
            # bubblewrap run as root creates missing ones 0700: nobody could
            # not walk through them. Make each one first, 0755, top-down.
            parts = p.split("/")[1:-1]
            for i in range(1, len(parts) + 1):
                a = "/" + "/".join(parts[:i])
                if a not in made and not any(
                    a == q or a.startswith(q + "/") for q in seen[:-1]
                ):
                    made.add(a)
                    out += ["--perms", "0755", "--dir", a]
            out += ["--ro-bind", p, p]
    return out


def _bwrap_cmd(workdir: str) -> list[str]:
    exe = shutil.which("bwrap")
    if exe is None:
        return []
    # Run as root, bubblewrap drops every capability, and then the child could
    # not drop to nobody (setgid/setuid need CAP_SETGID/CAP_SETUID). It keeps
    # just those two; the child uses them before any design code loads, and
    # leaving uid 0 for nobody clears all capabilities, so the design has none.
    # And as root it makes NO user namespace: one that maps only uid 0 denies
    # setgroups and has no uid 65534, so the drop would fail inside it; with
    # the namespaces listed instead, nobody is the host's real uid 65534. As
    # any other user bubblewrap needs the user namespace, so --unshare-all.
    if os.geteuid() == 0:
        unshare = [
            "--unshare-net", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
            "--unshare-cgroup-try",
            "--cap-add", "CAP_SETUID", "--cap-add", "CAP_SETGID",
        ]  # fmt: skip
    else:
        unshare = ["--unshare-all"]  # net, pid, ipc, uts, cgroup and user
    return [
        exe,
        *unshare,
        "--die-with-parent",
        "--new-session",
        *_jail_binds(),
        "--perms", "1777", "--tmpfs", "/tmp",
        "--bind", workdir, workdir,
        "--proc", "/proc",
        "--dev", "/dev",
        "--chdir", workdir,
    ]  # fmt: skip


@lru_cache(maxsize=1)
def jail_available() -> bool:
    """Whether bubblewrap starts here, with no network inside. Probed once."""
    if os.environ.get(JAIL_ENV, "auto") == "none" or shutil.which("bwrap") is None:
        return False
    with tempfile.TemporaryDirectory(prefix="ak-jail-probe-") as wd:
        cmd = _bwrap_cmd(wd) + [
            sys.executable, "-I", "-c",
            "import socket; s = socket.socket()\n"
            "try:\n s.connect(('1.1.1.1', 53)); print('net')\n"
            "except OSError:\n print('jailed')",
        ]  # fmt: skip
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=20, env=_child_env(wd)
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
    return r.returncode == 0 and r.stdout.strip() == "jailed"


def _use_jail() -> bool:
    mode = os.environ.get(JAIL_ENV, "auto")
    if mode == "none":
        return False
    if mode == "bwrap" and not jail_available():
        raise SandboxError(
            "request", f"{JAIL_ENV}=bwrap but bubblewrap does not start here"
        )
    return jail_available()


def sandbox_status() -> dict:
    """What `run_design` would use on this machine, for logs and /capabilities."""
    return {
        "layer": "jail" if _use_jail() else "baseline",
        "jail": "bwrap" if _use_jail() else None,
    }


def _child_env(workdir: str) -> dict:
    # Nothing of the server's environment: no tokens, no engine paths.
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": workdir,
        "LANG": "C.UTF-8",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "MOMWIRE_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _safe_name(filename: str) -> str:
    name = Path(filename).name
    if not name.endswith(".py") or name.startswith(".") or len(name) > 128:
        raise SandboxError("source", f"{filename!r}: a design file is a .py file")
    return name


def _read_capped(stream, cap: int, sink: list, over: threading.Event) -> None:
    total = 0
    while True:
        # read1: whatever is there now, not a full 64 KB. A grandchild that
        # inherited the pipe can keep it open past the reply, and a blocking
        # read would sit on the bytes already written until it closed.
        chunk = stream.read1(65536)
        if not chunk:
            return
        total += len(chunk)
        if total > cap:
            over.set()
            return
        sink.append(chunk)


def run_design(
    source: str,
    filename: str,
    *,
    want: str = "snapshot",
    params=None,
    limits: Limits | None = None,
) -> dict:
    """The design's `design_snapshot` data: ``static(cls)`` for
    ``want="static"``, or ``snapshot(cls(params))`` for ``want="snapshot"``
    (``params`` already encoded; None for the defaults). Raises
    `SandboxError`."""
    lim = limits or Limits()
    if want not in ("static", "snapshot"):
        raise SandboxError(
            "request", f"want must be 'static' or 'snapshot', not {want!r}"
        )
    name = _check_source(source, filename, lim)
    request = json.dumps(
        {
            "filename": name,
            "source": source,
            "want": want,
            "params": params,
            "limits": asdict(lim),
        }
    ).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="ak-design-") as wd:
        proc = _spawn(wd)
        out, err, over = [], [], threading.Event()
        t_out = threading.Thread(
            target=_read_capped, args=(proc.stdout, lim.max_reply_bytes, out, over)
        )
        t_err = threading.Thread(
            target=_read_capped, args=(proc.stderr, 64 * 1024, err, threading.Event())
        )
        t_out.start()
        t_err.start()
        try:
            proc.stdin.write(request)
            proc.stdin.close()
        except BrokenPipeError:
            pass
        deadline = time.monotonic() + lim.wall_s
        timed_out = False
        while proc.poll() is None:
            if over.is_set() or time.monotonic() > deadline:
                timed_out = not over.is_set()
                break
            time.sleep(0.02)
        _kill_group(proc)
        t_out.join(5)
        t_err.join(5)
    if over.is_set():
        raise SandboxError(
            "reply",
            f"the design's reply passed {lim.max_reply_bytes // (1024 * 1024)} MB",
        )
    if timed_out:
        raise SandboxError("timeout", f"the design ran past {lim.wall_s:g} s")
    raw = b"".join(out)
    if not raw.strip():
        _raise_death(proc.returncode, b"".join(err))
    return _parse_reply(raw)["data"]


def _check_source(source, filename: str, lim: Limits) -> str:
    """The checks made before anything runs; the file's bare name."""
    if (
        not isinstance(source, str)
        or len(source.encode("utf-8")) > lim.max_source_bytes
    ):
        raise SandboxError(
            "source", f"a design file is at most {lim.max_source_bytes // 1024} KB"
        )
    return _safe_name(filename)


def _spawn(wd: str, *args: str) -> subprocess.Popen:
    """The child, started in ``wd`` (jailed when the jail is in use)."""
    if os.geteuid() == 0:
        # The child drops to nobody before the design runs; its folder
        # must be its own. 0755, not tempfile's 0700: bubblewrap run as
        # root drops its capabilities, so it needs the folder's own
        # permissions to enter it.
        os.chown(wd, NOBODY, NOBODY)
        os.chmod(wd, 0o755)
    cmd = [sys.executable, "-I", "-m", "antennaknobs._sandbox_child", *args]
    if _use_jail():
        cmd = _bwrap_cmd(wd) + cmd
    return subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=wd, env=_child_env(wd), start_new_session=True, close_fds=True,
    )  # fmt: skip


def _raise_death(rc, err: bytes):
    """The error for a child that ended without a reply."""
    # A child killed by a signal: -sig from Popen, or 128 + sig when the
    # jail (bubblewrap) reports its child's death as its own exit status.
    if rc is not None and (rc < 0 or 128 < rc < 128 + 65):
        sig = -rc if rc < 0 else rc - 128
        kind = "timeout" if sig in (signal.SIGXCPU, signal.SIGKILL) else "crash"
        what = (
            "used more than its CPU time"
            if kind == "timeout"
            else f"died on signal {sig}"
        )
        raise SandboxError(kind, f"the design {what}")
    tail = err[-500:].decode("utf-8", "replace")
    raise SandboxError(
        "crash", f"the design process gave no reply ({tail.strip() or 'no output'})"
    )


def _parse_reply(raw: bytes) -> dict:
    """One reply, checked; raises the design's own error when it failed."""
    try:
        reply = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise SandboxError("reply", "the design process's reply is not JSON") from None
    if not isinstance(reply, dict) or "ok" not in reply:
        raise SandboxError("reply", "the design process's reply is not a reply")
    if not reply["ok"]:
        raise SandboxError(
            str(reply.get("kind", "design")), str(reply.get("error", ""))
        )
    return reply


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        pass


# --- warm workers (AK#2157) ------------------------------------------------------
#
# A knob turn on an opened design .py used to start a fresh child: about half
# a second, nearly all of it starting Python and importing numpy and
# antennaknobs. A worker is the same child, in the same jail, under the same
# rlimits, kept alive for ONE design and answering snapshot after snapshot.
# Each request has its own wall deadline; a worker that overruns, crashes,
# answers too much, forks, runs out of memory or has used half its CPU
# allowance (RLIMIT_CPU counts the process's whole life) is killed, and the
# next request starts a fresh one. State the design keeps between calls is
# its own: the worker serves nobody else.
#
# Measured on the laptop (AK#2157): a warm turn of a 5-wire design is 12 ms
# against 0.7 s for a one-shot child, and a worker is ~100 MB resident, 60 MB
# of it private. That is the interpreter and its imports; a design's own data
# is the size of its wires and network, never n^2 (the solve stays outside).

WORKERS_ENV = "ANTENNAKNOBS_DESIGN_WORKERS"  # resident cap; 0 = one-shot only
WORKER_IDLE_ENV = "ANTENNAKNOBS_DESIGN_WORKER_IDLE_S"


class _Worker:
    def __init__(self, source: str, name: str, lim: Limits):
        import queue

        self.lim = lim
        self.lock = threading.Lock()
        self.served = 0
        self.last_used = time.monotonic()
        self.wall_timeout = False
        self._dir = tempfile.TemporaryDirectory(prefix="ak-worker-")
        self.proc = _spawn(self._dir.name, "--serve")
        self._lines: queue.Queue = queue.Queue()
        self._over = threading.Event()
        self._err = bytearray()
        threading.Thread(target=self._read_lines, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()
        try:
            self._ask({"filename": name, "source": source, "limits": asdict(lim)})
        except BaseException:
            self.close()
            raise

    @property
    def pid(self) -> int:
        return self.proc.pid

    def alive(self) -> bool:
        return self.proc.poll() is None

    def _read_lines(self) -> None:
        cap, buf = self.lim.max_reply_bytes, bytearray()
        stream = self.proc.stdout
        while True:
            try:
                chunk = stream.read1(65536)
            except (OSError, ValueError):
                chunk = b""
            if not chunk:
                self._lines.put(None)
                return
            buf += chunk
            while (i := buf.find(b"\n")) >= 0:
                self._lines.put(bytes(buf[:i]))
                del buf[: i + 1]
            if len(buf) > cap:
                self._over.set()
                self._lines.put(None)
                return

    def _read_err(self) -> None:
        # What the design printed, a rolling tail: a worker lives long.
        while True:
            try:
                chunk = self.proc.stderr.read1(65536)
            except (OSError, ValueError):
                return
            if not chunk:
                return
            self._err += chunk
            del self._err[:-65536]

    def _ask(self, msg: dict) -> dict:
        import queue

        try:
            self.proc.stdin.write(json.dumps(msg).encode("utf-8") + b"\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass  # it died; the reader reports how
        deadline = time.monotonic() + self.lim.wall_s
        line = None
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                self.wall_timeout = True
                self.close()
                raise SandboxError(
                    "timeout", f"the design ran past {self.lim.wall_s:g} s"
                )
            try:
                line = self._lines.get(timeout=min(left, 0.25))
                break
            except queue.Empty:
                continue
        if line is None:
            self.close()
            if self._over.is_set():
                raise SandboxError(
                    "reply",
                    f"the design's reply passed "
                    f"{self.lim.max_reply_bytes // (1024 * 1024)} MB",
                )
            _raise_death(self.proc.returncode, bytes(self._err))
        if not line.strip():
            self.close()
            _raise_death(self.proc.returncode, bytes(self._err))
        try:
            return _parse_reply(line)
        except SandboxError:
            self.close()
            raise

    def snapshot(self, params) -> tuple[dict, bool]:
        """``(snapshot data, retire)`` at ``params``; raises `SandboxError`."""
        self.last_used = time.monotonic()
        try:
            reply = self._ask({"params": params})
        finally:
            self.served += 1
            self.last_used = time.monotonic()
        return reply["data"], bool(reply.get("retire"))

    def close(self) -> None:
        _kill_group(self.proc)
        for f in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                f.close()
            except OSError:
                pass
        self._dir.cleanup()


class WorkerPool:
    """At most ``max_workers`` warm workers, one per design (its source,
    name and limits), least recently used evicted first, each closed after
    ``idle_s`` without a request."""

    def __init__(self, max_workers: int = 4, idle_s: float = 300.0):
        self.max_workers = max(1, int(max_workers))
        self.idle_s = float(idle_s)
        self.started = 0  # workers started, for tests and logs
        self._workers: dict = {}  # key -> _Worker, oldest use first
        self._lock = threading.Lock()
        self._reaper: threading.Thread | None = None
        self._closed = False

    def __len__(self) -> int:
        with self._lock:
            return len(self._workers)

    def pids(self) -> list[int]:
        with self._lock:
            return [w.pid for w in self._workers.values()]

    def snapshot(self, source: str, filename: str, params=None, limits=None) -> dict:
        """`run_design(want="snapshot")`, answered by this design's warm
        worker. A worker that had already served and then died on its CPU
        allowance or memory is retried once on a fresh one: those limits
        count the worker's whole life, and a request is owed a full one."""
        lim = limits or Limits()
        name = _check_source(source, filename, lim)
        key = self._key(source, name, lim)
        for attempt in (0, 1):
            w = self._worker(key, source, name, lim)
            with w.lock:
                if not w.alive():
                    self._drop(key, w)
                    continue
                try:
                    data, retire = w.snapshot(params)
                except SandboxError as e:
                    self._drop(key, w)
                    used = w.served > 1
                    if (
                        attempt == 0
                        and used
                        and not w.wall_timeout
                        and e.kind in ("timeout", "memory", "crash")
                    ):
                        continue
                    raise
            if retire:
                self._drop(key, w)
            return data
        raise SandboxError("crash", "the design's worker would not stay up")

    @staticmethod
    def _key(source: str, name: str, lim: Limits) -> tuple:
        import hashlib

        return (hashlib.sha256(source.encode("utf-8")).hexdigest(), name, lim)

    def worker_pid(self, source: str, filename: str, limits=None) -> int | None:
        """The host process id of this design's resident worker, if any."""
        lim = limits or Limits()
        key = self._key(source, _safe_name(filename), lim)
        with self._lock:
            w = self._workers.get(key)
            return None if w is None else w.pid

    def _worker(self, key, source, name, lim) -> _Worker:
        with self._lock:
            w = self._workers.pop(key, None)
            if w is not None:
                self._workers[key] = w  # most recently used
                return w
        w = _Worker(source, name, lim)  # outside the lock: it takes a while
        with self._lock:
            self.started += 1
            other = self._workers.get(key)
            if other is not None:  # another request started one meanwhile
                spare, w = w, other
            else:
                spare = None
                self._workers[key] = w
            self._evict_locked(keep=key)
            self._start_reaper_locked()
        if spare is not None:
            spare.close()
        return w

    def _evict_locked(self, keep) -> None:
        over = len(self._workers) - self.max_workers
        for k in list(self._workers):
            if over <= 0:
                break
            if k == keep:
                continue
            w = self._workers[k]
            if w.lock.acquire(blocking=False):  # never kill a busy one
                try:
                    del self._workers[k]
                    w.close()
                finally:
                    w.lock.release()
                over -= 1

    def _drop(self, key, w: _Worker) -> None:
        with self._lock:
            if self._workers.get(key) is w:
                del self._workers[key]
        w.close()

    def reap(self) -> int:
        """Close the workers idle past ``idle_s``; how many were closed."""
        now, n = time.monotonic(), 0
        with self._lock:
            for k, w in list(self._workers.items()):
                if now - w.last_used > self.idle_s and w.lock.acquire(blocking=False):
                    try:
                        del self._workers[k]
                        w.close()
                        n += 1
                    finally:
                        w.lock.release()
        return n

    def _start_reaper_locked(self) -> None:
        if self._reaper is not None and self._reaper.is_alive():
            return

        def loop():
            while not self._closed:
                time.sleep(max(0.05, min(self.idle_s / 4, 30.0)))
                self.reap()
                with self._lock:
                    if not self._workers:
                        self._reaper = None
                        return

        self._reaper = threading.Thread(
            target=loop, daemon=True, name="ak-worker-reaper"
        )
        self._reaper.start()

    def close(self) -> None:
        self._closed = True
        with self._lock:
            ws, self._workers = list(self._workers.values()), {}
        for w in ws:
            w.close()


_POOL: WorkerPool | None = None
_POOL_LOCK = threading.Lock()


def default_pool() -> WorkerPool | None:
    """The process's worker pool, or None when ``ANTENNAKNOBS_DESIGN_WORKERS``
    is 0 (every request is then a one-shot child, as before AK#2157)."""
    global _POOL
    try:
        n = int(os.environ.get(WORKERS_ENV, "8"))
    except ValueError:
        n = 8
    if n <= 0:
        return None
    with _POOL_LOCK:
        if _POOL is None:
            import atexit

            try:
                idle = float(os.environ.get(WORKER_IDLE_ENV, "300"))
            except ValueError:
                idle = 300.0
            _POOL = WorkerPool(max_workers=n, idle_s=idle)
            atexit.register(_POOL.close)
        return _POOL


def warm_snapshot(source: str, filename: str, params=None, limits=None) -> dict:
    """A snapshot from the design's warm worker, or a one-shot child when
    workers are off."""
    pool = default_pool()
    if pool is None:
        return run_design(source, filename, params=params, limits=limits)
    return pool.snapshot(source, filename, params=params, limits=limits)


# --- the server-side builder for a sandboxed design ----------------------------


def sandboxed_builder(
    filename: str, source: str, *, limits: Limits | None = None, check=None
):
    """An `AntennaBuilder` class for a design ``.py`` that runs ONLY in the
    sandbox. Its class-level parts (label, docstring, defaults, variants, c)
    come from one ``static`` run; every hook it answers is a method that asks
    the sandbox for a snapshot at the instance's params (cached per params)
    and decodes that hook's data through the allowlist. ``check(wires)``, if
    given, sees every decoded ``build_wires`` result (the opened-deck limits).
    A hook that raised in the sandbox raises here, named."""
    import collections
    import json as _json
    import threading as _threading
    from pathlib import PurePath

    from . import design_snapshot as ds
    from .builder import AntennaBuilder

    lim = limits or Limits()
    static = run_design(source, filename, want="static", limits=lim)
    hooks = set(warm_snapshot(source, filename, limits=lim))
    stem = PurePath(filename).stem
    cache: collections.OrderedDict = collections.OrderedDict()
    lock = _threading.Lock()

    def snap_for(self) -> dict:
        params = ds.encode(dict(self._params))
        key = _json.dumps(params, sort_keys=True)
        with lock:
            hit = cache.get(key)
            if hit is not None:
                cache.move_to_end(key)
                return hit
        snap = warm_snapshot(source, filename, params=params, limits=lim)
        with lock:
            cache[key] = snap
            while len(cache) > 64:
                cache.popitem(last=False)
        return snap

    def make_hook(name):
        def hook(self):
            data = snap_for(self).get(name)
            if isinstance(data, dict) and set(data) == {"__error__"}:
                raise RuntimeError(f"{filename}: {name}() raised {data['__error__']}")
            value = ds.decode(data)
            if name == "build_wires" and check is not None:
                check(value)
            return value

        hook.__name__ = name
        return hook

    label = ds.decode(static["label"])
    ns = {
        "__doc__": static.get("doc") or None,
        "__module__": "antennaknobs.sandboxed",
        "label": label if isinstance(label, str) and label else stem,
        "default_params": ds.decode(static["default_params"]),
        "c_light_mhz_m": ds.decode(static["c_light_mhz_m"]),
        # Marks the class for the server: its source is a stranger's .py.
        "sandboxed_source_name": filename,
    }
    for v, data in static["variants"].items():
        if v.isidentifier() and not v.startswith("_"):
            ns[f"{v}_params"] = ds.decode(data)
    for h in ds.HOOKS:
        if h in hooks:
            ns[h] = make_hook(h)
    cls = type(
        stem if stem.isidentifier() else "SandboxedDesign", (AntennaBuilder,), ns
    )
    cls.__qualname__ = cls.__name__
    return cls
