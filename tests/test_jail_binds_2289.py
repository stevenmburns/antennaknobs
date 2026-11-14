"""What the design jail binds, and that it binds nothing more (AK#2289).

Two defects, each tested at the boundary rather than at the function:

- Under ``python -m uvicorn`` the server's ``sys.path[0]`` is the folder it
  was started in, and the jail used to bind every ``sys.path`` entry, so a
  design could read files next to the server. The jail now binds only the
  child's own import path (`design_sandbox._import_roots`). Each launch shape
  (``-m``, ``-c``, a script / console script) runs a real "server" process in
  a folder holding a secret, and a design in its jail tries to read it. A
  control in the same jail binds that folder on purpose and reads it, so the
  test can tell a refused read from a read it failed to make.
- A uv-managed Python reaches its interpreter through a minor-version
  symlinked folder (``cpython-3.12-…`` -> ``cpython-3.12.12-…``), which the
  jail did not recreate, so bubblewrap could not exec the venv's python and
  `jail_available()` was False. The test builds that exact layout around the
  running interpreter (uv's own shape: an absolute link per hop, and
  ``home`` in pyvenv.cfg naming the link) and checks the jail starts there.

The jail-dependent halves skip where bubblewrap does not start, and fail
instead under ``AK_REQUIRE_JAIL=1`` (the sandbox-jail CI lane).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from antennaknobs import design_sandbox as sb

REQUIRE_JAIL = os.environ.get("AK_REQUIRE_JAIL") == "1"

jail = pytest.mark.skipif(
    not sb.jail_available() and not REQUIRE_JAIL,
    reason="bubblewrap does not start on this machine",
)

# The "server": a process that imports the sandbox the way the web app does,
# launched in each shape, reporting what its jail binds or what a design in
# that jail could read. argv: <server folder> <mode>.
SERVER = textwrap.dedent('''
    import json, os, sys
    from antennaknobs import design_sandbox as sb

    server, mode = sys.argv[1], sys.argv[2]
    secret = os.path.join(server, "secret")
    out = {"path0": sys.path[0]}
    if mode == "binds":
        import sysconfig
        out["binds"] = sb._jail_binds()
        out["stdlib"] = sysconfig.get_paths()["stdlib"]
        out["purelib"] = sysconfig.get_paths()["purelib"]
        print(json.dumps(out))
        sys.exit(0)
    if mode == "baseline":
        os.environ[sb.JAIL_ENV] = "none"
    if mode == "jail+bind":
        # The control: the same folder, bound on purpose.
        roots = sb._import_roots()
        sb._import_roots = lambda: (*roots, server)
    body = """
        import numpy, momwire, antennaknobs
        try:
            got = open(SECRET).read()
        except OSError as e:
            raise RuntimeError(f"not there: {type(e).__name__}")
        raise RuntimeError(f"read it: {got}")
    """.replace("SECRET", repr(secret))
    import textwrap
    src = (
        "from types import MappingProxyType\\n"
        "from antennaknobs import AntennaBuilder\\n"
        "class Builder(AntennaBuilder):\\n"
        "    default_params = MappingProxyType({'freq': 14.2, 'design_freq': 14.2})\\n"
        "    def build_wires(self):\\n"
        + textwrap.indent(textwrap.dedent(body), " " * 8)
    )
    snap = sb.run_design(src, "s.py", limits=sb.Limits(wall_s=25.0, cpu_s=20))
    out["status"] = sb.sandbox_status()
    out["error"] = snap["build_wires"].get("__error__")
    print(json.dumps(out))
''')

SHAPES = ["-m", "-c", "script"]


@pytest.fixture
def server_dir():
    """A folder a server was started in, holding a file no design may read.
    Under the home folder, like a real one (not /tmp, which the jail
    replaces with its own), and world-readable, so the root lane's child
    (nobody) could read it if it were bound."""
    d = Path(tempfile.mkdtemp(prefix=".ak-2289-server-", dir=Path.home()))
    try:
        d.chmod(0o755)
        (d / "secret").write_text("server-only")
        (d / "secret").chmod(0o644)
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def launch(shape: str, server: Path, mode: str) -> dict:
    """Run the SERVER code in ``server`` as its cwd, launched in ``shape``."""
    if shape == "-m":
        (server / "ak_server_probe.py").write_text(SERVER)
        cmd = [sys.executable, "-m", "ak_server_probe"]
    elif shape == "-c":
        cmd = [sys.executable, "-c", SERVER]
    else:  # a script elsewhere, as a console script lives in the venv's bin
        bindir = server.parent / f"{server.name}-bin"
        bindir.mkdir(exist_ok=True)
        (bindir / "ak_server_probe.py").write_text(SERVER)
        cmd = [sys.executable, str(bindir / "ak_server_probe.py")]
    try:
        r = subprocess.run(
            [*cmd, str(server), mode],
            cwd=server, capture_output=True, text=True, timeout=120,
        )  # fmt: skip
    finally:
        shutil.rmtree(server.parent / f"{server.name}-bin", ignore_errors=True)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def ro_binds(args: list[str]) -> list[str]:
    return [args[i + 1] for i, a in enumerate(args) if a == "--ro-bind"]


def covered(path: str, binds: list[str]) -> bool:
    p = os.path.realpath(path)
    return any(p == b or p.startswith(b + "/") for b in binds)


@pytest.mark.parametrize("shape", SHAPES)
def test_the_jail_never_binds_the_folder_the_server_started_in(shape, server_dir):
    out = launch(shape, server_dir, "binds")
    # The launch shape really put what the issue says on sys.path[0].
    expect0 = {
        "-m": str(server_dir),
        "-c": "",
        "script": str(server_dir.parent / f"{server_dir.name}-bin"),
    }[shape]
    assert out["path0"] == expect0
    args = out["binds"]
    real = os.path.realpath(server_dir)
    named = [a for a in args if a == real or a.startswith(real + "/")]
    assert named == [], named
    if shape == "script":
        assert not any(a.startswith(os.path.realpath(expect0)) for a in args), (
            "a script's own folder is not an import root of the child"
        )
    # What a design legitimately imports from is there.
    binds = ro_binds(args)
    assert covered(out["stdlib"], binds), (out["stdlib"], binds)
    assert covered(out["purelib"], binds), (out["purelib"], binds)
    # And so are the packages a design imports, where the CHILD's own
    # interpreter (-I: no PYTHONPATH) finds them; in a dev checkout with
    # PYTHONPATH set, that is the venv's install, not this file's tree.
    r = subprocess.run(
        [sys.executable, "-I", "-c",
         "import json, antennaknobs, momwire, numpy; print(json.dumps("
         "[antennaknobs.__file__, momwire.__file__, numpy.__file__]))"],
        capture_output=True, text=True, timeout=60, cwd="/",
    )  # fmt: skip
    assert r.returncode == 0, r.stderr[-2000:]
    for f in json.loads(r.stdout):
        assert covered(f, binds), (f, binds)


@jail
@pytest.mark.parametrize("shape", SHAPES)
def test_a_design_cannot_read_the_folder_the_server_started_in(shape, server_dir):
    out = launch(shape, server_dir, "jail")
    assert out["status"] == {"layer": "jail", "jail": "bwrap"}
    # Not an ImportError: numpy, momwire and antennaknobs imported first.
    assert out["error"].startswith("RuntimeError: not there:"), out["error"]
    # The control, in the same jail: bound on purpose, the read succeeds, so
    # the refusal above is the jail's and not a read that never happened.
    ctl = launch(shape, server_dir, "jail+bind")
    assert ctl["status"] == {"layer": "jail", "jail": "bwrap"}
    assert ctl["error"] == "RuntimeError: read it: server-only", ctl["error"]


@pytest.mark.skipif(
    os.geteuid() == 0, reason="as root the child is nobody, who cannot walk $HOME"
)
def test_without_the_jail_the_same_design_reads_the_secret(server_dir):
    """The baseline layer's promise is about cost, not sight: the read the
    jail refuses is one a design CAN make outside it."""
    out = launch("-m", server_dir, "baseline")
    assert out["status"]["layer"] == "baseline"
    assert out["error"] == "RuntimeError: read it: server-only", out["error"]


# --- a uv-managed Python: links on the way to the interpreter ------------------


def test_resolve_records_every_link_on_the_way(tmp_path):
    real = tmp_path / "cpython-3.12.12"
    (real / "bin").mkdir(parents=True)
    (real / "bin" / "python3.12").write_text("")
    (tmp_path / "cpython-3.12").symlink_to(real)  # absolute, as uv writes it
    (tmp_path / "venv" / "bin").mkdir(parents=True)
    (tmp_path / "venv" / "bin" / "python").symlink_to(
        tmp_path / "cpython-3.12" / "bin" / "python3.12"
    )
    (tmp_path / "venv" / "bin" / "python3").symlink_to("python")  # relative
    got, links = sb._resolve(str(tmp_path / "venv" / "bin" / "python3"))
    assert got == os.path.realpath(real / "bin" / "python3.12")
    assert [w for w, _ in links] == [
        str(tmp_path / "venv" / "bin" / "python3"),
        str(tmp_path / "venv" / "bin" / "python"),
        str(tmp_path / "cpython-3.12"),
    ]
    assert dict(links)[str(tmp_path / "cpython-3.12")] == str(real)
    got, _ = sb._resolve(str(tmp_path / "cpython-3.12" / "bin" / ".." / "bin"))
    assert got == os.path.realpath(real / "bin")


def uv_shaped_venv(root: Path) -> tuple[Path, Path, str]:
    """A venv laid out as ``uv venv -p 3.12`` lays one out around a uv
    Python, built around the running interpreter so it needs neither uv nor
    a download: ``venv/bin/python`` -> ``<uv>/cpython-X.Y-…/bin/pythonX.Y``
    and ``<uv>/cpython-X.Y-…`` -> the real installation, both absolute, with
    pyvenv.cfg's ``home`` naming the link. The venv's site-packages adds the
    running one's (``site.addsitedir``, so its editable installs come too).
    Returns (the venv's python, the minor-version link, its target)."""
    real_exe = os.path.realpath(sys.executable)
    base = os.path.realpath(sys.base_prefix)
    rel = os.path.relpath(real_exe, base)
    assert not rel.startswith(".."), (real_exe, base)
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    uv = root / "uvpy"
    uv.mkdir()
    link = uv / f"cpython-{ver}-linux-x86_64-gnu"
    link.symlink_to(base)
    venv = root / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").symlink_to(link / rel)
    (venv / "pyvenv.cfg").write_text(
        f"home = {link / os.path.dirname(rel)}\n"
        "include-system-site-packages = false\n"
        f"version_info = {'.'.join(map(str, sys.version_info[:3]))}\n"
    )
    site_dir = venv / "lib" / f"python{ver}" / "site-packages"
    site_dir.mkdir(parents=True)
    import site

    dirs = [d for d in site.getsitepackages() if os.path.isdir(d)]
    (site_dir / "ak_2289_server_site.pth").write_text(
        "import site; " + "; ".join(f"site.addsitedir({d!r})" for d in dirs) + "\n"
    )
    # The root lane's child is nobody: everything it walks must be 0755.
    for d in (root, uv, venv, *venv.rglob("*")):
        if d.is_dir() and not d.is_symlink():
            d.chmod(0o755)
    return venv / "bin" / "python", link, base


UV_CHECK = textwrap.dedent("""
    import json, sys
    from antennaknobs import design_sandbox as sb
    out = {"exe": sys.executable, "binds": sb._jail_binds()}
    if sys.argv[1] == "run":
        out["available"] = sb.jail_available()
        if out["available"]:
            src = (
                "from types import MappingProxyType\\n"
                "from antennaknobs import AntennaBuilder\\n"
                "class Builder(AntennaBuilder):\\n"
                "    default_params = MappingProxyType({'freq': 14.2, 'design_freq': 14.2})\\n"
                "    def build_wires(self):\\n"
                "        import numpy, momwire\\n"
                "        return [((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), 21, None)]\\n"
            )
            out["wires"] = sb.run_design(src, "d.py")["build_wires"]
    print(json.dumps(out))
""")


def run_uv(python: Path, mode: str) -> dict:
    r = subprocess.run(
        [str(python), "-c", UV_CHECK, mode],
        capture_output=True, text=True, timeout=120, cwd="/",
    )  # fmt: skip
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_a_uv_venv_s_interpreter_link_is_recreated_in_the_jail(tmp_path):
    python, link, base = uv_shaped_venv(tmp_path)
    out = run_uv(python, "binds")
    assert out["exe"] == str(python)
    args = out["binds"]
    trip = [args[i : i + 3] for i, a in enumerate(args) if a == "--symlink"]
    assert ["--symlink", base, str(link)] in trip, trip
    # The link itself is never made a directory or bound over (the old bug:
    # a bind under it made it a plain folder, and the exec path led nowhere).
    assert not any(
        a == str(link) or a.startswith(str(link) + "/")
        for i, a in enumerate(args)
        if i and args[i - 1] in ("--dir", "--ro-bind")
    ), args
    assert covered(base, ro_binds(args))
    assert covered(str(tmp_path / "venv"), ro_binds(args))


@jail
def test_the_jail_starts_under_a_uv_venv(tmp_path):
    python, _, _ = uv_shaped_venv(tmp_path)
    out = run_uv(python, "run")
    assert out["available"] is True, "bubblewrap could not exec the uv venv's python"
    assert "__error__" not in out["wires"], out["wires"]
    from antennaknobs import design_snapshot as ds

    assert ds.decode(out["wires"]) == [((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), 21, None)]
