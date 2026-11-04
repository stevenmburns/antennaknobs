"""A design .py's warm worker (AK#2157).

`test_design_sandbox_2149.py` runs every sandbox promise on both routes; this
file holds what only a worker has: it is reused, it is replaced when it
overruns, eats memory, forks or spends its CPU allowance, one design's
trouble leaves another's worker alone, and the pool is bounded by count and
by idle time.
"""

from __future__ import annotations

import os
import textwrap
import time

import pytest

from antennaknobs import design_sandbox as sb
from antennaknobs import design_snapshot as ds

FAST = sb.Limits(wall_s=20.0, cpu_s=15, memory_mb=1536)


def design(body: str, tag: str = "") -> str:
    """A design whose build_wires runs ``body`` with ``self.mode`` set; it
    reports its process id by raising, so a test can tell workers apart."""
    return textwrap.dedent(f"""
        # {tag}
        from types import MappingProxyType
        from antennaknobs import AntennaBuilder

        class Builder(AntennaBuilder):
            default_params = MappingProxyType(
                {{"freq": 14.2, "design_freq": 14.2, "mode": 0}}
            )

            def build_wires(self):
                import os
                mode = int(self.mode)
        """) + textwrap.indent(textwrap.dedent(body), " " * 8)


PID = "raise ValueError(f'pid={os.getpid()}')\n"


def pid_of(snap: dict) -> int:
    err = snap["build_wires"]["__error__"]
    return int(err.rsplit("pid=", 1)[1])


def ask(pool, src, mode=0, name="d.py", limits=FAST):
    params = ds.encode({"freq": 14.2, "design_freq": 14.2, "mode": mode})
    return pool.snapshot(src, name, params=params, limits=limits)


@pytest.fixture
def pool():
    p = sb.WorkerPool(max_workers=4, idle_s=60)
    yield p
    p.close()


def alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def test_one_worker_answers_every_knob_turn(pool):
    src = design(PID)
    pids = {pid_of(ask(pool, src, mode=m)) for m in range(5)}
    assert len(pids) == 1
    assert pool.started == 1


def test_a_warm_turn_skips_the_start_up():
    """The point of the worker: a turn costs the design's build, not a
    Python start and the imports. Generous bounds, not a benchmark."""
    p = sb.WorkerPool(max_workers=1, idle_s=60)
    try:
        src = design("return []")
        ask(p, src)
        t = time.monotonic()
        for m in range(5):
            ask(p, src, mode=m)
        warm = (time.monotonic() - t) / 5
        t = time.monotonic()
        sb.run_design(
            src, "d.py", params=ds.encode({"freq": 14.2, "mode": 9}), limits=FAST
        )
        cold = time.monotonic() - t
    finally:
        p.close()
    assert warm < cold / 4, (warm, cold)


def test_a_worker_that_overruns_is_killed_and_the_next_turn_gets_a_fresh_one():
    p = sb.WorkerPool(max_workers=2, idle_s=60)
    try:
        src = design("if mode == 1:\n    while True:\n        pass\n" + PID)
        lim = sb.Limits(wall_s=2.0, cpu_s=30)
        first = pid_of(ask(p, src, limits=lim))
        with pytest.raises(sb.SandboxError) as e:
            ask(p, src, mode=1, limits=lim)
        assert e.value.kind == "timeout"
        assert not alive(first)
        second = pid_of(ask(p, src, limits=lim))
        assert second != first
    finally:
        p.close()


def test_one_designs_trouble_leaves_another_designs_worker_alone(pool):
    calm = design(PID, tag="calm")
    wild = design("if mode == 1:\n    os._exit(3)\n" + PID, tag="wild")
    calm_pid = pid_of(ask(pool, calm))
    wild_pid = pid_of(ask(pool, wild))
    with pytest.raises(sb.SandboxError) as e:
        ask(pool, wild, mode=1)
    assert e.value.kind == "crash"
    assert not alive(wild_pid)
    assert alive(calm_pid)
    assert pid_of(ask(pool, calm)) == calm_pid


def test_a_worker_that_ran_out_of_memory_is_replaced(pool):
    src = design("if mode == 1:\n    x = bytearray(4 * 1024 ** 3)\n" + PID)
    lim = sb.Limits(memory_mb=1024, wall_s=20)
    first = pid_of(ask(pool, src, limits=lim))
    snap = ask(pool, src, mode=1, limits=lim)
    assert snap["build_wires"]["__error__"].startswith("MemoryError")
    assert not alive(first)
    assert pid_of(ask(pool, src, limits=lim)) != first


def test_a_worker_whose_design_forked_is_replaced_and_its_children_are_gone(pool):
    marker = f"ak-worker-orphan-{os.getpid()}"
    body = (
        textwrap.dedent(f"""
        import sys
        if mode == 1 and os.fork() == 0:
            os.execv(sys.executable, [sys.executable, "-c", "import time; time.sleep(60)", "{marker}"])
    """)
        + PID
    )
    src = design(body)
    first = pid_of(ask(pool, src))
    assert pid_of(ask(pool, src, mode=1)) == first  # it answers, then goes
    time.sleep(0.5)
    orphans = [
        p
        for p in os.listdir("/proc")
        if p.isdigit()
        and marker in open(f"/proc/{p}/cmdline", "rb").read().decode(errors="replace")
    ]
    assert not orphans
    assert not alive(first)
    assert pid_of(ask(pool, src)) != first


def test_a_worker_is_retired_at_half_its_cpu_allowance_and_the_turn_still_answers(pool):
    """RLIMIT_CPU counts the worker's whole life, so it is replaced before a
    later turn could inherit a spent allowance."""
    burn = "t = __import__('time').process_time()\nwhile __import__('time').process_time() - t < 1.2:\n    pass\n"
    src = design(burn + PID)
    lim = sb.Limits(cpu_s=2, wall_s=20)
    first = pid_of(ask(pool, src, limits=lim))  # 1.2 s of 2: over half
    second = pid_of(ask(pool, src, limits=lim))
    assert second != first


def test_resident_workers_are_bounded_by_count():
    p = sb.WorkerPool(max_workers=2, idle_s=60)
    try:
        pids = [pid_of(ask(p, design(PID, tag=f"d{i}"))) for i in range(3)]
        assert len(p) == 2
        assert not alive(pids[0])  # least recently used goes first
        assert alive(pids[1]) and alive(pids[2])
    finally:
        p.close()


def test_resident_workers_are_bounded_by_idle_time():
    p = sb.WorkerPool(max_workers=4, idle_s=0.4)
    try:
        pid = pid_of(ask(p, design(PID)))
        deadline = time.monotonic() + 5
        while len(p) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert len(p) == 0
        assert not alive(pid)
    finally:
        p.close()


def test_a_sandboxed_builders_knob_turn_is_served_by_one_worker(monkeypatch):
    p = sb.WorkerPool(max_workers=2, idle_s=60)
    monkeypatch.setattr(sb, "default_pool", lambda: p)
    try:
        src = design(
            "return [((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), 11 + 2 * mode, None)]"
        )
        cls = sb.sandboxed_builder("d.py", src, limits=FAST)
        for m in range(4):
            assert (
                cls(dict(cls.default_params, mode=m)).build_wires()[0][2] == 11 + 2 * m
            )
        assert p.started == 1
    finally:
        p.close()


def test_workers_off_means_one_shot(monkeypatch):
    monkeypatch.setenv(sb.WORKERS_ENV, "0")
    assert sb.default_pool() is None
    snap = sb.warm_snapshot(design("return []"), "d.py", limits=FAST)
    assert ds.decode(snap["build_wires"]) == []
