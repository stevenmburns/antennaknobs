"""The package sets the thread-pool wait variables before NumPy loads.

`antennaknobs/__init__.py` opens with a block that `setdefault`s
OMP_WAIT_POLICY / GOMP_SPINCOUNT / OPENBLAS_THREAD_TIMEOUT. The native pools
read them once, at library load, so the block only works while it runs
before the package's first import of NumPy: these tests run a fresh
interpreter (a subprocess, since this one loaded NumPy long ago).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

_KEYS = ("OMP_WAIT_POLICY", "GOMP_SPINCOUNT", "OPENBLAS_THREAD_TIMEOUT")

# Read the variables at the moment NumPy is first imported, by hooking the
# import itself: that is when OpenBLAS reads its environment.
_PROBE = """
import builtins, json, os, sys
seen = {}
_real = builtins.__import__
def _hook(name, *a, **k):
    if name.split(".")[0] == "numpy" and "numpy" not in seen:
        seen["numpy"] = {k: os.environ.get(k) for k in %r}
    return _real(name, *a, **k)
builtins.__import__ = _hook
import antennaknobs.web.server  # the uvicorn import path
print(json.dumps(seen.get("numpy")))
""" % (_KEYS,)


def _env_at_numpy_import(**set_vars) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _KEYS}
    env.update(set_vars)
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_wait_variables_are_set_before_numpy_loads():
    seen = _env_at_numpy_import()
    assert seen == {
        "OMP_WAIT_POLICY": "PASSIVE",
        "GOMP_SPINCOUNT": "0",
        "OPENBLAS_THREAD_TIMEOUT": "1",
    }


def test_a_callers_own_value_is_kept():
    seen = _env_at_numpy_import(OPENBLAS_THREAD_TIMEOUT="7", OMP_WAIT_POLICY="ACTIVE")
    assert seen["OPENBLAS_THREAD_TIMEOUT"] == "7"
    assert seen["OMP_WAIT_POLICY"] == "ACTIVE"
    assert seen["GOMP_SPINCOUNT"] == "0"
