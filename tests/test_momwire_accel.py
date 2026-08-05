"""Consumer-side guard for the pynec-accel/libgomp trap (issue #737).

momwire's own `test_accel_fallback.py` (momwire/tests/test_accel_fallback.py)
pins the LOADER's behavior — that a *built* accelerator which fails to import
warns loudly, on the fallback path deliberately triggered with monkeypatch.
That test never actually asserts the accelerator is loaded in THIS install;
it only tests the warn-vs-quiet branch decision in isolation.

This is the complement: the antennaknobs environment's momwire must actually
have the C++ accelerator loaded, not silently running the slow pure-Python
path (the historical failure here was a static-TLS clash from an old
pynec-accel vendoring its own libgomp — momwire < 0.2.2 or
pynec-accel < 1.7.4.post1 — see momwire/src/momwire/_accel.py's docstring).
Skipped, rather than failed, when the extension was never built for this
platform at all (mirrors momwire's own `_extension_built()` detector) — that
is a legitimate pure-Python install, not the trap this guards against.
"""

import momwire
import pytest
from momwire import _accel


def test_accelerator_is_loaded():
    if not _accel._extension_built():
        pytest.skip(
            "momwire's _accelerators extension was never built for this "
            "platform/install — pure-Python is the expected (not the "
            "trapped) outcome here; see issue #737 and "
            "momwire/src/momwire/_accel.py"
        )
    assert _accel.LOADED is True, (
        "momwire's compiled accelerator is built but did not load — the "
        "pynec-accel/libgomp static-TLS trap (issue #737): check "
        "`apt install libgomp1` / pynec-accel >= 1.7.4.post2, or see the "
        "RuntimeWarning momwire._accel emits on import"
    )
    # Public flag (momwire/__init__.py: `from ._accel import LOADED as
    # accelerated`) must agree with the internal one.
    assert momwire.accelerated is True
    assert momwire.accelerated is _accel.LOADED
