"""Smoke-gate the frozen workbench (issue #1349).

Usage::

    python scripts/freeze_workbench/smoke.py dist/antennaknobs-workbench/antennaknobs-workbench[.exe]

The numbered gates below, each run against the FROZEN executable and
nothing else:

1. ``--selftest`` exits 0 and prints ``accelerated = True`` and an invvee
   impedance equal to the unfrozen package's to 1e-9 (same code, same
   wheel: packaging may not move a number).
   1b. The same selftest with ``MOMWIRE_FORCE_VARIANT=sse2``, when the bundle
   carries momwire's baseline build: it must load (``variant = sse2``) and
   reproduce the invvee to 1e-9 (issue #1405). Every box on the fleet has
   AVX2, so a plain selftest alone would leave the sse2 build unproven in
   every bundle.
2. The server starts on a chosen port with ``--no-browser`` and answers
   ``/healthz`` with ``{"ok": true}`` and ``/capabilities`` with a backend
   list that names the momwire lanes — the two checks the install scripts
   already make. Also (issue #1507): ``/capabilities``' ``version_label``
   names both the antennaknobs and momwire versions this SAME environment's
   installed metadata reports — the fix for a user who ran a stale bundle
   because copying only the .exe over an old folder silently keeps the old
   ``_internal`` beside it.
3. One solve through the server's own sweep endpoint returns a finite
   impedance from the momwire solver.
4. ``/export_nec`` (the gear menu's Download .nec) returns a NEC-2 deck. The
   bundle carries no PyNEC by policy, and the export used to need it (#1387).
5. ``/design_source`` (the Files view's Source tab, #1428) serves a catalog
   design's own ``.py``. The modules import from the bundle's archive; the
   source exists only because build.py ships ``designs/`` as files too.
6. (Windows only) the exe's own Windows version resource — Explorer's
   Properties -> Details — reports ProductVersion equal to the antennaknobs
   version. Skipped with a printed note on any other platform: a version
   resource is a PE concept, and there is nothing to read.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _get(url: str, timeout: float = 30.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 — loopback http only
        return r.status, json.loads(r.read().decode("utf-8"))


def _exe_product_version(exe: Path) -> str | None:
    """The exe's own Windows version resource ProductVersion string — what
    Explorer's Properties -> Details actually shows (issue #1507). Reads it
    through PowerShell's .NET FileVersionInfo reflection (`Get-Item
    ... .VersionInfo.ProductVersion`) rather than hand-rolled ctypes bindings
    to version.dll: every windows-latest GitHub runner has powershell.exe by
    definition, and .NET's ProductVersion reads the StringFileInfo
    'ProductVersion' entry verbatim when the resource sets one — which is
    what `version_file.build_version_info` does — rather than reformatting
    FixedFileInfo's packed DWORDs, so it returns the full antennaknobs string
    (dev/local suffix included) exactly as written."""
    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Item -LiteralPath '{exe}').VersionInfo.ProductVersion",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except Exception as e:  # noqa: BLE001 — reported to the caller as a gate failure, not raised
        print(f"WARNING: could not read the exe's version resource: {e}")
        return None
    value = out.stdout.strip()
    return value or None


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    exe = Path(argv[0]).resolve()
    assert exe.is_file(), exe

    # 0. NO GPL CODE IN THE BUNDLE. This is a licence gate, not a size one, and
    # it runs before anything else because a bundle that fails it must not be
    # signed, zipped or launched.
    #
    # PyNEC is GPL and the workbench is not: `pyproject.toml` leaves it out of
    # every extra deliberately ("installed separately per README"), and
    # antennaknobs#1354's text coupling exists so the app never needs to import
    # it. But `--collect-submodules antennaknobs` follows what the BUILD VENV
    # can see, so a developer whose venv has `pynec-accel` gets `PyNEC.py`,
    # `_PyNEC*.so` and a 27 MB `pynec_accel.libs/` in the bundle without being
    # told. Measured on a dev box 2026-09-10: 36 MB of GPL code, silently.
    #
    # `build.py` excludes the modules by name; this asserts the outcome, so the
    # gate does not depend on the exclusion list keeping up with the wheel's
    # module names.
    bad = sorted(
        p.relative_to(exe.parent).as_posix()
        for p in exe.parent.rglob("*")
        if p.is_file() and "pynec" in p.name.lower()
    )
    if bad:
        print(
            "FAIL: GPL code in the bundle — PyNEC must never ship in the "
            "frozen workbench (antennaknobs#1359). Found:\n  "
            + "\n  ".join(bad[:20])
            + (f"\n  ... and {len(bad) - 20} more" if len(bad) > 20 else ""),
            file=sys.stderr,
        )
        return 1
    print(f"no GPL (pynec) files in {exe.parent.name}: OK")

    # 1. selftest against the unfrozen package.
    #
    # A build that prints the openmp line and then fails accelerated=True is
    # momwire#737; gate 1 is the check. build.py finding *an* OpenMP runtime
    # says nothing about whether the extension can load: the published wheel
    # is delvewheel-repaired and vendors several hash-renamed DLLs, so a
    # bundle can ship libomp, report it happily, and still have a dead
    # accelerator because a sibling (msvcp140-<hash>.dll) was left behind.
    # Only running the thing catches that.
    t0 = time.perf_counter()
    out = subprocess.run(
        [str(exe), "--selftest"], capture_output=True, text=True, timeout=600
    )
    dt = time.perf_counter() - t0
    print(out.stdout)
    if out.returncode != 0 or "SELFTEST OK" not in out.stdout:
        print(out.stderr[-2000:], file=sys.stderr)
        print(f"FAIL: selftest exit {out.returncode}")
        return 1
    m = re.search(r"invvee free space: \[\(([-+0-9.e]+)([-+][0-9.e]+)j\)\]", out.stdout)
    assert m, out.stdout
    frozen_z = complex(float(m.group(1)), float(m.group(2)))
    from antennaknobs import Antenna
    from antennaknobs.designs.dipoles.invvee import Builder

    ref_z = Antenna(Builder()).impedance()[0]
    if abs(frozen_z - ref_z) > 1e-9 * abs(ref_z):
        print(f"FAIL: frozen invvee {frozen_z} != unfrozen {ref_z}")
        return 1
    print(f"gate 1 OK: selftest in {dt:.1f} s, invvee {frozen_z} == unfrozen")

    # 1b. the BASELINE build, forced (issue #1405). Every box on the fleet has
    # AVX2, so a plain selftest only ever loads the avx2 half of momwire's
    # double build (momwire#1032), and the sse2 half would ship unproven.
    if any(exe.parent.rglob("_accelerators_sse2*")):
        out = subprocess.run(
            [str(exe), "--selftest"],
            capture_output=True,
            text=True,
            timeout=600,
            env=dict(os.environ, MOMWIRE_FORCE_VARIANT="sse2"),
        )
        print(out.stdout)
        if (
            out.returncode != 0
            or "variant = sse2" not in out.stdout
            or "SELFTEST OK" not in out.stdout
        ):
            print(out.stderr[-2000:], file=sys.stderr)
            print(f"FAIL: the forced sse2 selftest (exit {out.returncode})")
            return 1
        m = re.search(
            r"invvee free space: \[\(([-+0-9.e]+)([-+][0-9.e]+)j\)\]", out.stdout
        )
        assert m, out.stdout
        sse2_z = complex(float(m.group(1)), float(m.group(2)))
        if abs(sse2_z - ref_z) > 1e-9 * abs(ref_z):
            print(f"FAIL: sse2 invvee {sse2_z} != unfrozen {ref_z}")
            return 1
        print(f"gate 1b OK: the sse2 build loads, invvee {sse2_z} == unfrozen")
    else:
        print("gate 1b skipped: no sse2 build in this bundle (not an x86 double build)")

    # 2 + 3. the server
    port = _free_port()
    proc = subprocess.Popen(
        [str(exe), "--no-browser", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 180
        while True:
            try:
                status, body = _get(base + "/healthz", timeout=3)
                if status == 200 and body.get("ok") is True:
                    break
            except Exception:  # noqa: BLE001 — polling until the server binds
                if proc.poll() is not None:
                    print(proc.stdout.read()[-3000:])
                    print("FAIL: server exited before answering")
                    return 1
                if time.time() > deadline:
                    print("FAIL: server did not answer within 180 s")
                    return 1
                time.sleep(0.5)
        status, caps = _get(base + "/capabilities", timeout=60)
        names = [b.get("name") for b in caps.get("backends", [])]
        print("gate 2 OK: /healthz ok, backends =", names)
        if "momwire" not in " ".join(str(n) for n in names) and not any(
            "bspline" in str(n) or "momwire" in str(n) for n in names
        ):
            print("FAIL: no momwire backend in /capabilities")
            return 1

        # #1507: the served label names the SAME versions this environment's
        # own installed metadata reports — the bundle is built from this
        # environment's wheels, so the two must agree.
        from importlib.metadata import version as pkg_version

        ak_version = pkg_version("antennaknobs")
        mw_version = pkg_version("momwire")
        label = caps.get("version_label", "")
        if ak_version not in label or mw_version not in label:
            print(
                f"FAIL: /capabilities version_label {label!r} does not name "
                f"antennaknobs {ak_version} and momwire {mw_version}"
            )
            return 1
        print(f"gate 2b OK: version_label = {label!r}")
        req = json.dumps(
            {"geometry": "dipoles.invvee", "freqs_mhz": [14.1], "solver": "momwire"}
        ).encode()
        r = urllib.request.Request(  # noqa: S310 — loopback http only
            base + "/sweep", data=req, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(r, timeout=600) as resp:  # noqa: S310 — loopback http only
            text = resp.read().decode("utf-8")
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        zs = [
            (row.get("z_re"), row.get("z_im"))
            for row in rows
            if row.get("z_re") is not None
        ]
        print(f"gate 3: sweep rows {len(rows)}, impedances {zs[:2]}")
        if not zs:
            print("FAIL: the sweep returned no impedance")
            return 1

        # 4. Download .nec through the bundle, which has NO PyNEC by policy
        # (gate 0). The export used to construct the PyNEC engine, whose
        # module imported PyNEC at the top, so this button was a 500 in
        # every bundle before #1387 — and nothing here pressed it.
        req = json.dumps({"geometry": "dipoles.invvee", "freqs_mhz": [14.1]}).encode()
        r = urllib.request.Request(  # noqa: S310 — loopback http only
            base + "/export_nec", data=req, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(r, timeout=120) as resp:  # noqa: S310 — loopback http only
            deck = resp.read().decode("utf-8")
        cards = [ln.split()[0] for ln in deck.splitlines() if ln.strip()]
        if "GW" not in cards or "EX" not in cards or cards[-1] != "EN":
            print(f"FAIL: /export_nec returned no NEC deck:\n{deck[:400]}")
            return 1
        print(f"gate 4: /export_nec wrote {len(cards)} cards without PyNEC")

        # 5. The Files view's Source tab (AK#1428) reads a catalog design's own
        # .py. The bundle imports the modules from its archive, so the source is
        # there only because build.py also ships designs/ as files.
        req = json.dumps({"geometry": "dipoles.invvee"}).encode()
        r = urllib.request.Request(  # noqa: S310 — loopback http only
            base + "/design_source",
            data=req,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(r, timeout=60) as resp:  # noqa: S310 — loopback http only
            src = json.loads(resp.read().decode("utf-8"))
        if not src.get("available") or "class Builder" not in src.get("text", ""):
            print(
                f"FAIL: /design_source found no source in the bundle: {str(src)[:300]}"
            )
            return 1
        print(f"gate 5: /design_source served {src['filename']} from the bundle")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()

    # 6. (Windows only) the exe's own version resource, which is what a user
    # actually sees in Explorer's Properties -> Details — the second half of
    # #1507, checked after the server is stopped since it needs nothing from
    # it. `_exe_product_version` returns None (with its own printed reason)
    # off Windows or if the resource cannot be read, and this gate is the
    # ONE place that is allowed to be a no-op rather than a failure: a
    # version resource is a PE concept, so there is nothing to check
    # elsewhere.
    if sys.platform == "win32":
        from importlib.metadata import version as pkg_version

        ak_version = pkg_version("antennaknobs")
        resource_version = _exe_product_version(exe)
        if resource_version is None:
            print("FAIL: could not read the exe's version resource on Windows")
            return 1
        if resource_version != ak_version:
            print(
                f"FAIL: exe version resource ProductVersion {resource_version!r} "
                f"!= antennaknobs {ak_version!r}"
            )
            return 1
        print(f"gate 6 OK: exe version resource ProductVersion = {resource_version!r}")
    else:
        print(
            f"gate 6 skipped: not Windows ({sys.platform}); no version resource to read"
        )

    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
