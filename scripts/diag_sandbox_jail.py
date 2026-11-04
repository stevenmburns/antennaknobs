"""TEMPORARY diagnostic for the sandbox-jail CI lane (AK#2149 unit 4).

Run as root on the lane; prints, from inside the jailed child, what the
design can see of the antennaknobs checkout, and what a fork does. Remove
with the step that runs it once the root-case failures are understood.
"""

import os
import sys
import textwrap

from antennaknobs import design_sandbox as sb

PKG = os.path.dirname(os.path.abspath(sb.__file__))

PROBE = textwrap.dedent(f"""
    import os, stat, sys
    from types import MappingProxyType
    from antennaknobs import AntennaBuilder

    def walk(path):
        out = []
        parts = path.split("/")
        for i in range(2, len(parts) + 1):
            p = "/".join(parts[:i])
            try:
                st = os.stat(p)
                out.append(f"{{p}} uid={{st.st_uid}} mode={{stat.filemode(st.st_mode)}}")
            except OSError as e:
                out.append(f"{{p}} ERR {{e}}")
        return out

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({{"freq": 14.2, "design_freq": 14.2}})

        def build_wires(self):
            lines = [f"uid={{os.getuid()}} euid={{os.geteuid()}} groups={{os.getgroups()}}"]
            lines += walk({PKG!r} + "/station")
            try:
                lines.append("listdir pkg: " + ",".join(sorted(os.listdir({PKG!r}))[:8]))
            except OSError as e:
                lines.append(f"listdir pkg ERR {{e}}")
            import antennaknobs
            lines.append(f"antennaknobs.__path__={{list(antennaknobs.__path__)}}")
            lines.append(f"sys.path={{sys.path}}")
            try:
                import antennaknobs.station  # noqa: F401
                lines.append("import antennaknobs.station: ok")
            except Exception as e:  # noqa: BLE001
                lines.append(f"import antennaknobs.station: {{type(e).__name__}}: {{e}}")
            pid = os.fork()
            if pid == 0:
                os._exit(0)
            lines.append(f"fork ok, waited {{os.waitpid(pid, 0)}}")
            raise RuntimeError(" || ".join(lines))
""")

print(
    "server uid",
    os.getuid(),
    "jail",
    sb.jail_available(),
    "status",
    sb.sandbox_status(),
)
print("bwrap cmd:", " ".join(sb._bwrap_cmd("/tmp/WORKDIR")))
try:
    snap = sb.run_design(PROBE, "probe.py", limits=sb.Limits(wall_s=30))
    print("\n".join(snap["build_wires"]["__error__"].split(" || ")))
except sb.SandboxError as e:
    print("SandboxError", e.kind, e)

FORKER = textwrap.dedent("""
    import os, sys
    from types import MappingProxyType
    from antennaknobs import AntennaBuilder

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 14.2, "design_freq": 14.2})

        def build_wires(self):
            if os.fork() == 0:
                os.execv(sys.executable, [sys.executable, "-c", "import time; time.sleep(60)", "ak-diag-orphan"])
            return []
""")
try:
    snap = sb.run_design(FORKER, "forker.py", limits=sb.Limits(wall_s=30))
    print("forker reply hooks:", sorted(snap))
except sb.SandboxError as e:
    print("forker SandboxError", e.kind, e)
os.system(
    "ps -eo pid,user,args | grep ak-diag-orphan | grep -v grep || echo 'no orphan left'"
)
sys.exit(0)
