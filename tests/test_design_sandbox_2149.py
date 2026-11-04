"""A design .py you did not write, run in a disposable child (AK#2149 unit 2).

The baseline layer's promises are tested everywhere: the right data comes
back, and a design that loops, eats memory, forks, prints, reads the
environment or answers too much is stopped and reported. The jail's extra
promises (no network, read-only root) are tested only where bubblewrap
starts; elsewhere they skip, which is the point of `sandbox_status()`.
"""

from __future__ import annotations

import importlib
import json
import os
import textwrap
import time
import warnings
from pathlib import Path

import pytest

from antennaknobs import design_sandbox as sb
from antennaknobs import design_snapshot as ds

cli = importlib.import_module("antennaknobs.cli")

DIPOLE = textwrap.dedent('''
    """A test dipole."""
    from types import MappingProxyType
    from antennaknobs import AntennaBuilder

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 14.2, "design_freq": 14.2, "half": 5.0})
        tall_params = MappingProxyType({"half": 5.5})

        def build_wires(self):
            return [((0.0, -self.half, 10.0), (0.0, self.half, 10.0), 21, None)]
''')

FAST = sb.Limits(wall_s=20.0, cpu_s=15, memory_mb=1536)


def design(body: str, header: str = "") -> str:
    """A minimal design whose build_wires runs ``body``."""
    return textwrap.dedent(f"""
        from types import MappingProxyType
        from antennaknobs import AntennaBuilder
        {header}
        class Builder(AntennaBuilder):
            default_params = MappingProxyType({{"freq": 14.2, "design_freq": 14.2}})

            def build_wires(self):
        """) + textwrap.indent(textwrap.dedent(body), " " * 8)


def hook_error(snap: dict, hook: str = "build_wires") -> str:
    """A design that raises inside a hook comes back as that hook's
    ``__error__`` (`design_snapshot.snapshot`), so the server can show it."""
    data = snap[hook]
    assert isinstance(data, dict) and "__error__" in data, data
    return data["__error__"]


def test_a_design_comes_back_as_the_same_data_it_gives_in_process():
    snap = sb.run_design(DIPOLE, "dipole.py", limits=FAST)
    static = sb.run_design(DIPOLE, "dipole.py", want="static", limits=FAST)
    wires = ds.decode(snap["build_wires"])
    assert wires == [((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), 21, None)]
    assert ds.decode(static["default_params"])["half"] == 5.0
    assert set(static["variants"]) == {"tall"}
    # and at other params
    p = ds.encode({"freq": 14.2, "design_freq": 14.2, "half": 6.0})
    wires = ds.decode(
        sb.run_design(DIPOLE, "dipole.py", params=p, limits=FAST)["build_wires"]
    )
    assert wires[0][1] == (0.0, 6.0, 10.0)


@pytest.mark.parametrize(
    "name", ["dipoles.folded_invvee_balun", "loops.skyloop_lmatch"]
)
def test_a_catalog_designs_source_gives_the_same_snapshot_in_the_sandbox(name):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cls = type(cli.get_builder(name)())
        mod = importlib.import_module(cls.__module__)
        here = ds.snapshot(cls())
    src = Path(mod.__file__).read_text()
    there = sb.run_design(src, Path(mod.__file__).name, limits=FAST)
    assert json.loads(json.dumps(here)) == there


def test_a_design_that_prints_cannot_corrupt_the_reply():
    snap = sb.run_design(
        design('print("{\\"ok\\": false}"); return []'), "p.py", limits=FAST
    )
    assert ds.decode(snap["build_wires"]) == []


def test_a_design_that_never_returns_is_killed_at_the_deadline():
    t = time.monotonic()
    with pytest.raises(sb.SandboxError) as e:
        sb.run_design(
            "while True:\n    pass\n", "loop.py", limits=sb.Limits(wall_s=3.0, cpu_s=30)
        )
    assert e.value.kind == "timeout"
    assert time.monotonic() - t < 10


def test_a_design_that_burns_cpu_meets_the_cpu_limit():
    with pytest.raises(sb.SandboxError) as e:
        sb.run_design(
            "while True:\n    pass\n", "burn.py", limits=sb.Limits(wall_s=30.0, cpu_s=2)
        )
    assert e.value.kind == "timeout"


def test_a_design_that_eats_memory_is_stopped():
    snap = sb.run_design(
        design("x = bytearray(4 * 1024 ** 3)\nreturn []"),
        "m.py",
        limits=sb.Limits(memory_mb=1024, wall_s=20),
    )
    assert hook_error(snap).startswith("MemoryError")


def test_a_design_that_eats_memory_at_import_is_stopped():
    with pytest.raises(sb.SandboxError) as e:
        sb.run_design(
            "x = bytearray(4 * 1024 ** 3)\n",
            "m.py",
            limits=sb.Limits(memory_mb=1024, wall_s=20),
        )
    assert e.value.kind == "memory"


def test_a_design_cannot_fork_without_limit():
    body = """
        import os
        n = 0
        try:
            for _ in range(500):
                if os.fork() == 0:
                    import time; time.sleep(30); os._exit(0)
                n += 1
        except OSError:
            raise RuntimeError(f"fork refused after {n}")
        raise RuntimeError(f"forked {n}")
    """
    snap = sb.run_design(
        design(body), "f.py", limits=sb.Limits(extra_processes=8, wall_s=20)
    )
    err = hook_error(snap)
    assert "fork refused after" in err, err
    # At least one fork went through (the cap is headroom, not zero), and no
    # more than the allowance did.
    assert 1 <= int(err.rsplit(" ", 1)[1]) <= 8, err


def test_the_forked_children_do_not_outlive_the_run():
    marker = f"ak-sandbox-orphan-{os.getpid()}"
    body = f"""
        import os, sys
        if os.fork() == 0:
            os.execv(sys.executable, [sys.executable, "-c", "import time; time.sleep(60)", "{marker}"])
        return []
    """
    sb.run_design(design(body), "o.py", limits=FAST)
    time.sleep(0.5)
    alive = [
        p
        for p in os.listdir("/proc")
        if p.isdigit()
        and marker in Path(f"/proc/{p}/cmdline").read_bytes().decode(errors="replace")
    ]
    assert not alive


def test_a_forked_copy_of_the_design_cannot_add_a_second_reply():
    """A fork whose child does not exec runs on as a second copy of the
    design; only the process the parent started may answer."""
    body = """
        import os
        os.fork()
        return []
    """
    snap = sb.run_design(design(body), "twin.py", limits=FAST)
    assert ds.decode(snap["build_wires"]) == []


def test_the_design_sees_none_of_the_servers_environment(monkeypatch):
    monkeypatch.setenv("AK_TEST_SECRET_2149", "s3cret")
    snap = sb.run_design(
        design("import os\nraise ValueError(repr(sorted(os.environ)))"),
        "e.py",
        limits=FAST,
    )
    err = hook_error(snap)
    assert "AK_TEST_SECRET_2149" not in err
    assert "'PATH'" in err and "'HOME'" in err


def test_an_oversized_reply_is_refused():
    with pytest.raises(sb.SandboxError) as e:
        sb.run_design(
            design(
                "return [((0.0, 0.0, float(i)), (0.0, 1.0, float(i)), 5, None) for i in range(400000)]"
            ),
            "big.py",
            limits=sb.Limits(max_reply_bytes=1024 * 1024, wall_s=30),
        )
    assert e.value.kind == "reply"


def test_a_design_that_returns_an_object_is_refused_by_name():
    src = (
        design("return []")
        + "\n    def plane_labels(self):\n        return {'rig': object()}\n"
    )
    with pytest.raises(sb.SandboxError) as e:
        sb.run_design(src, "obj.py", limits=FAST)
    assert e.value.kind == "design" and "is not design data" in str(e.value)


def test_a_file_without_a_builder_is_reported():
    with pytest.raises(sb.SandboxError) as e:
        sb.run_design("x = 1\n", "nothing.py", limits=FAST)
    assert e.value.kind == "design" and "defines no Builder" in str(e.value)


def test_the_source_and_its_name_are_checked_before_anything_runs():
    with pytest.raises(sb.SandboxError) as e:
        sb.run_design("x" * (300 * 1024), "big.py")
    assert e.value.kind == "source"
    for bad in ("design.txt", ".hidden.py", "a" * 200 + ".py"):
        with pytest.raises(sb.SandboxError):
            sb.run_design(DIPOLE, bad)
    # A path is reduced to its name: the file lands in the scratch folder.
    snap = sb.run_design(DIPOLE, "../../etc/dipole.py", limits=FAST)
    assert "build_wires" in snap


def test_the_status_names_the_layer_in_use():
    s = sb.sandbox_status()
    assert s["layer"] in ("jail", "baseline")
    assert (s["jail"] is not None) == (s["layer"] == "jail")


# AK_REQUIRE_JAIL=1 (the sandbox-jail CI lane): a jail that does not start is
# a failure there, never a skip, so the lane cannot pass without running them.
REQUIRE_JAIL = os.environ.get("AK_REQUIRE_JAIL") == "1"


def test_the_jail_starts_where_it_is_required():
    if not REQUIRE_JAIL:
        pytest.skip("AK_REQUIRE_JAIL is not set")
    assert sb.jail_available(), "AK_REQUIRE_JAIL=1 but bubblewrap does not start"
    assert sb.sandbox_status() == {"layer": "jail", "jail": "bwrap"}


jail = pytest.mark.skipif(
    not sb.jail_available() and not REQUIRE_JAIL,
    reason="bubblewrap does not start on this machine",
)


@jail
def test_in_the_jail_the_design_has_no_network():
    body = """
        import socket
        s = socket.socket()
        try:
            s.connect(("1.1.1.1", 53))
        except OSError as e:
            raise RuntimeError(f"no network: {e}")
        raise RuntimeError("connected")
    """
    snap = sb.run_design(design(body), "net.py", limits=FAST)
    assert "no network" in hook_error(snap)


@jail
def test_in_the_jail_the_root_is_read_only(tmp_path):
    target = tmp_path / "should-not-exist"
    body = f"""
        try:
            open({str(target)!r}, "w").write("x")
        except OSError as e:
            raise RuntimeError(f"refused: {{e}}")
        raise RuntimeError("wrote")
    """
    snap = sb.run_design(design(body), "w.py", limits=FAST)
    assert "refused" in hook_error(snap)
    assert not target.exists()


@jail
def test_in_the_jail_what_is_not_bound_is_not_there():
    """The jail binds the system, /etc and Python's import path, read-only,
    and nothing else: a file in the home folder (outside them) is absent."""
    secret = Path.home() / f".ak-jail-test-{os.getpid()}"
    secret.write_text("server-only")
    try:
        body = f"""
            try:
                open({str(secret)!r}).read()
            except OSError as e:
                raise RuntimeError(f"not there: {{type(e).__name__}}")
            raise RuntimeError("read it")
        """
        snap = sb.run_design(design(body), "s.py", limits=FAST)
        assert "not there" in hook_error(snap)
    finally:
        secret.unlink()


@pytest.mark.skipif(
    os.geteuid() != 0, reason="only a server running as root drops to nobody"
)
def test_a_server_running_as_root_runs_the_design_as_nobody():
    body = """
        import os
        caps = {k: v.strip() for k, v in (line.split(":", 1) for line in open("/proc/self/status"))
                if k in ("CapEff", "CapPrm")}
        raise RuntimeError(f"uid {os.getuid()} gid {os.getgid()} groups {os.getgroups()} "
                           f"eff {caps['CapEff']} prm {caps['CapPrm']}")
    """
    snap = sb.run_design(design(body), "u.py", limits=FAST)
    err = hook_error(snap)
    assert "uid 65534 gid 65534 groups []" in err, err
    # Leaving uid 0 cleared every capability, including the two kept for the drop.
    assert err.endswith("eff 0000000000000000 prm 0000000000000000"), err
