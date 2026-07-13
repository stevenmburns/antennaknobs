"""Shared pytest setup.

- Force a headless matplotlib backend so plot tests run without a display.
- Expose `needs_pynec`, a skip marker for tests that require the optional
  PyNEC engine (unavailable e.g. on Windows).
- Point the user-design folder at a throwaway temp dir for the whole test
  session, set *before* any `import antennaknobs.web.server` (which scaffolds the folder
  at import time). Keeps the suite from writing TEMPLATE.py / CLAUDE.md into
  the developer's real ~/.antennaknobs. Individual tests can still
  override ANTENNAKNOBS_USER_DIR via monkeypatch — user_designs reads it
  fresh on every refresh().
"""

import importlib.util
import os
import tempfile

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib  # noqa: E402

matplotlib.use("Agg", force=True)

import pytest  # noqa: E402

os.environ.setdefault(
    "ANTENNAKNOBS_USER_DIR",
    tempfile.mkdtemp(prefix="antennaknobs_userdesigns_test_"),
)

# Blanket-trust user designs for the suite so tests that load them don't each
# have to grant trust (the trust gate is exercised specifically in
# test_design_trust.py, which turns this flag off per-test).
os.environ.setdefault("ANTENNAKNOBS_TRUST_USER_DESIGNS", "1")

HAS_PYNEC = importlib.util.find_spec("PyNEC") is not None

needs_pynec = pytest.mark.skipif(
    not HAS_PYNEC, reason="PyNEC not installed (engine unavailable on this platform)"
)
