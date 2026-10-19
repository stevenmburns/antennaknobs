"""AK#2020: AVX-512 off before numpy loads, at every antennaknobs entry point.

momwire#1533's `momwire_serve_client.pin_cpu_env` names numpy's AVX-512
dispatch targets in NPY_DISABLE_CPU_FEATURES and sets OPENBLAS_CORETYPE=Haswell
on an AVX-512 CPU, so a result's last bits do not depend on whether the box
has AVX-512. antennaknobs imports numpy itself, so it pins in its own package
``__init__`` (which every entry point imports first: the CLI, ``python -m``,
uvicorn and the Docker image), in the frozen app's ``entry.py``, and in
tests/conftest.py for this session.

Every check here holds on every box: on a CPU without AVX-512 the pin sets
nothing and numpy has no AVX-512 target to run.
"""

from __future__ import annotations

import os
import subprocess
import sys

import momwire_serve_client as mech
import pytest

_PIN_VARS = (mech.NPY_DISABLE_ENV, mech.NPY_ENABLE_ENV, mech.OPENBLAS_CORETYPE_ENV)

# A fresh interpreter: import antennaknobs (or numpy first), then report the
# two variables and whether numpy dispatches any AVX-512 target.
_PROBE = """
import os, sys
if sys.argv[1] == "numpy-first":
    import numpy
import antennaknobs
import numpy
from numpy._core import _multiarray_umath as u
on = [n for n in u.__cpu_dispatch__
      if ("AVX512" in n or n == "X86_V4") and u.__cpu_features__.get(n)]
print(repr((os.environ.get("NPY_DISABLE_CPU_FEATURES"),
            os.environ.get("OPENBLAS_CORETYPE"), on)))
"""


def _clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _PIN_VARS}
    env.update(extra)
    return env


def _probe(mode: str, env: dict[str, str]):
    out = subprocess.run(
        [sys.executable, "-c", _PROBE, mode],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return eval(out.stdout.strip().splitlines()[-1])  # noqa: S307 - our own repr


def test_this_session_runs_no_avx512_numpy_target():
    want = mech.cpu_env({}).get(mech.NPY_DISABLE_ENV)
    if os.environ.get(mech.NPY_DISABLE_ENV, want) != want:
        pytest.skip("NPY_DISABLE_CPU_FEATURES exported by the user")
    from numpy._core import _multiarray_umath as u

    on = [
        n
        for n in u.__cpu_dispatch__
        if ("AVX512" in n or n == "X86_V4") and u.__cpu_features__.get(n)
    ]
    assert on == []


def test_importing_antennaknobs_pins_before_numpy():
    expected = mech.cpu_env({})
    npy, coretype, on = _probe("antennaknobs-first", _clean_env())
    assert npy == expected.get(mech.NPY_DISABLE_ENV)
    assert coretype == expected.get(mech.OPENBLAS_CORETYPE_ENV)
    assert on == []


def test_a_users_own_values_are_kept():
    env = _clean_env(NPY_DISABLE_CPU_FEATURES="", OPENBLAS_CORETYPE="Prescott")
    npy, coretype, _ = _probe("antennaknobs-first", env)
    assert (npy, coretype) == ("", "Prescott")


def test_numpy_loaded_first_is_left_alone():
    # The caller chose by importing numpy first; pinning now would reach only
    # its subprocesses and split them from the parent.
    npy, coretype, _ = _probe("numpy-first", _clean_env())
    assert (npy, coretype) == (None, None)
