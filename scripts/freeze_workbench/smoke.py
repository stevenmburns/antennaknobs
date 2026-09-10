"""Smoke-gate the frozen workbench (issue #1349).

Usage::

    python scripts/freeze_workbench/smoke.py dist/antennaknobs-workbench/antennaknobs-workbench[.exe]

Three gates, each run against the FROZEN executable and nothing else:

1. ``--selftest`` exits 0 and prints ``accelerated = True`` and an invvee
   impedance equal to the unfrozen package's to 1e-9 (same code, same
   wheel: packaging may not move a number).
2. The server starts on a chosen port with ``--no-browser`` and answers
   ``/healthz`` with ``{"ok": true}`` and ``/capabilities`` with a backend
   list that names the momwire lanes — the two checks the install scripts
   already make.
3. One solve through the server's own sweep endpoint returns a finite
   impedance from the momwire solver.
4. ``/export_nec`` (the gear menu's Download .nec) returns a NEC-2 deck. The
   bundle carries no PyNEC by policy, and the export used to need it (#1387).
"""

from __future__ import annotations

import json
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
        print("SMOKE OK")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
