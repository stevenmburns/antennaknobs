"""OpenNEC through pyopennec: the PyNEC engine on another NEC-2 binding.

pyopennec (https://github.com/stevenmburns/pyopennec) wraps OpenNEC, a C
rewrite of NEC-2 / nec2c, behind PyNEC's own API — ``nec_context``,
``get_geometry().wire``, the ``*_card`` methods and the result getters, with
PyNEC's names and argument order. So this engine is `PyNECEngine` with one
thing changed: where its contexts come from (`nec_module` / `_make_context`).
Every card it emits, every readout and every refusal is PyNEC's.

What follows from the binding being different, not from the engine:

* ``fill_reuse`` is pynec-accel's ``set_fill_reuse``. It is gated on the live
  probe `takes_fill_reuse`, and pyopennec has no such method today, so the
  engine neither offers it nor sends it (`PyNECEngine._apply_fill_reuse` only
  calls a setter the context has).
* ``check_intersections``: OpenNEC makes no nec2++-style intersection check at
  all, so the default and ``False`` behave alike.
* nec2++'s pre-1.7.6 Sommerfeld defect (#448) is nec2++'s: the warning for
  it is off here.

What OpenNEC itself refuses (pyopennec README, "Known limitations"): EX 1-4
(plane wave, elementary current source), CP, GN 3; the engine emits none of
them. Buried wires are NEC-2's limitation, the same as PyNEC's.

pyopennec is MIT, like antennaknobs, but it is not on PyPI yet, so it stays
an OPTIONAL import exactly as PyNEC is: absent, the engine builds against the
deck-only stand-in and a solve raises an ImportError naming the package.
"""

from __future__ import annotations

try:
    import pyopennec
except ImportError:  # optional; built from source (see OPENNEC_MISSING)
    pyopennec = None

from .pynec import PyNECEngine, _DeckOnlyContext, module_takes_fill_reuse

OPENNEC_MISSING = (
    "pyopennec is not installed: the opennec engine cannot solve without it. "
    "It is not on PyPI yet; build it from source with `pip install "
    "git+https://github.com/stevenmburns/pyopennec` (MIT; needs a C compiler, "
    "CMake and, optionally, OpenBLAS), or solve with momwire."
)


def _new_context():
    return (
        pyopennec.nec_context()
        if pyopennec is not None
        else _DeckOnlyContext(OPENNEC_MISSING)
    )


def takes_fill_reuse() -> bool:
    """Whether the installed pyopennec's ``nec_context`` has
    ``set_fill_reuse``. A live probe, as `pynec.takes_fill_reuse` is: False
    today, and True the day the binding grows the method."""
    return module_takes_fill_reuse(pyopennec)


class OpenNECEngine(PyNECEngine):
    """OpenNEC (NEC-2) through pyopennec, with PyNECEngine's whole model.

    On the same deck it agrees with PyNEC to ~1e-3 on Z: both are NEC-2's
    formulation, and nec2++ itself differs from nec2c by ~2e-4.
    tests/test_opennec_parity.py holds the two engines together over the
    catalog.
    """

    engine_label = "OpenNEC"
    warns_somm_low_wires = False

    @staticmethod
    def nec_module():
        return pyopennec

    def _make_context(self):
        return _new_context()
