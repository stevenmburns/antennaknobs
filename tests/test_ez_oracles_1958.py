"""EZNEC ``.ez`` models against EZNEC's own ``.nec`` of the same model (AK#1958).

The strongest check of the ``.ez`` reader is EZNEC itself: for each model
here EZNEC wrote a ``.nec`` (a Save As export, or for efhw2 the deck it
handed its NEC-5 engine), and AK already reads those. An ``.ez`` must open as
the design its export opens as -- the same wires, and the same driving-point
impedance once both are solved.

Most of these ``.ez`` files (and some exports) are other people's models,
shared with this project privately, so they are not in the repo: this module
reads them from a local tree and skips a pairing whose files are not there.
``ANTENNAKNOBS_EZ_ORACLES`` names the tree (default: this checkout's
``scratch/``); a path starting with ``~`` is the user's home. The coupled
loop's ``.ez`` and both its exports are already banked under ``scratch/``, so
those pairings run in every checkout and the module as a whole skips only
when even they are missing -- the one reason `test_ez_oracles_skip_1958.py`
allows.

Tolerances are each pairing's measured gap, with headroom, and why:

* SI c here against NEC's 299.8 in the export's reading: 2.5e-5 (coupled loop).
* EZNEC's export rounds every number to 7 digits; the ``.ez`` keeps the
  singles: a few 1e-5 to 1e-4.
* A lossy line: EZNEC's export writes its two-port with a constant that
  closes all but the last digit of the Y parameters: 3.4e-4 (Bydpole).
* The NEC-2 export of a current source is NEC-2's gyrator idiom, and its
  virtual wire stays real wire (a phantom wire parks beside it), so that
  reading drives 1/Z through a slightly leaky node: 2.8e-3 (cardL, NEC-2).
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

from antennaknobs.engines import MomwireEngine
from antennaknobs.ez_import import read_ez
from antennaknobs.file_designs import builder_from_file, builder_from_text

ORACLES_ENV = "ANTENNAKNOBS_EZ_ORACLES"
ROOT = Path(
    os.environ.get(ORACLES_ENV) or Path(__file__).resolve().parent.parent / "scratch"
).expanduser()
_CARDL = "ez-census/fetched/github__n8mus__Wiresmith/reference/examples/Cardioid L Network Feed ARRL Example.ez"
# The file whose presence says the tree is here.
SENTINEL = "qrz-lfa-thread/NEC-4 coupled loop.ez"

# name: (.ez, EZNEC's .nec, reading, the reference drives 1/Z, rel tolerance)
PAIRS = {
    "coupled loop, NEC-2 export": (
        SENTINEL,
        "qrz-lfa-thread/coupled-loop-nec2.nec",
        None,
        False,
        1e-4,
    ),
    "coupled loop, NEC-5 export": (
        SENTINEL,
        "qrz-lfa-thread/coupled-loop-nec5.nec",
        "nec5",
        False,
        1e-4,
    ),
    "cardioid L network, NEC-5 export": (
        _CARDL,
        "qrz-lfa-thread/cardL-nec5.nec",
        "nec5",
        False,
        5e-4,
    ),
    "cardioid L network, NEC-2 export": (
        _CARDL,
        "qrz-lfa-thread/cardL-nec2.nec",
        None,
        True,
        5e-3,
    ),
    "Bydpole TL + transformer + L networks, NEC-5 export": (
        "dan-140-144/tl-xfmr-clc/Bydpole-TL-Xfmr-CLC.ez",
        "dan-140-144/tl-xfmr-clc/Bydpole-TL-Xfmr-CLC.nec",
        "nec5",
        False,
        1e-3,
    ),
    "efhw2, EZNEC's NEC-5 engine deck": (
        "~/Downloads/GroundRod/efhw2.ez",
        "~/Downloads/GroundRod/EZN5.NEC",
        None,
        False,
        1e-3,
    ),
}


def _path(rel: str) -> Path:
    return Path(rel).expanduser() if rel.startswith("~") else ROOT / rel


pytestmark = pytest.mark.skipif(
    not _path(SENTINEL).is_file(),
    reason=(
        f"the private oracle tree is not at {ROOT} (set {ORACLES_ENV} to it); "
        "the .ez files are not ours to publish"
    ),
)


def _z(cls) -> complex:
    return complex(MomwireEngine(cls(), ground=cls.file_ground).impedance()[0])


def _pair(name):
    ez, ref, reading, invert, tol = PAIRS[name]
    ez, ref = _path(ez), _path(ref)
    if not (ez.is_file() and ref.is_file()):
        pytest.skip(f"{name}: {ez if not ez.is_file() else ref} is not here")
    return ez, ref, reading, invert, tol


def _reference(ref: Path):
    return builder_from_text(ref.name, ref.read_text(encoding="latin-1"))


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_an_ez_solves_as_its_eznec_nec_does(name):
    ez, ref, reading, invert, tol = _pair(name)
    ours = builder_from_file(str(ez), dialect=reading)
    theirs = _reference(ref)
    assert ours.file_ground == theirs.file_ground
    z_ours, z_ref = _z(ours), _z(theirs)
    if invert:
        z_ref = 1.0 / z_ref
    assert abs(z_ours - z_ref) <= tol * abs(z_ref), (z_ours, z_ref)


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_an_ez_has_the_wires_of_its_eznec_nec(name):
    ez, ref, reading, _invert, _tol = _pair(name)
    imp = read_ez(ez.read_bytes(), name=ez.name, reading=reading)
    theirs = _reference(ref).file_deck_parsed
    n = len(imp.model.wires)
    for a, b in zip(imp.deck.wires[:n], theirs.wires[:n], strict=True):
        assert a.n_seg == b.n_seg
        for u, v in zip(
            (*a.p1, *a.p2, a.radius), (*b.p1, *b.p2, b.radius), strict=True
        ):
            assert math.isclose(u, v, rel_tol=2e-6, abs_tol=1e-6), (a, b)


def test_the_lossy_line_is_the_two_port_eznec_writes():
    """Bydpole's lossy line, held at the model frequency as EZNEC's export
    writes it: the same Y parameters to its 3.4e-4 constant gap."""
    ez, ref, reading, _invert, _tol = _pair(
        "Bydpole TL + transformer + L networks, NEC-5 export"
    )
    ours = read_ez(ez.read_bytes(), name=ez.name, reading=reading).deck
    theirs = _reference(ref).file_deck_parsed
    (a,) = [nt for nt in ours.nts if nt.custom is None]
    b = theirs.nts[0]
    for ra, rb in zip(a.y, b.y, strict=True):
        for u, v in zip(ra, rb, strict=True):
            assert abs(u - v) <= 4e-4 * abs(v), (u, v)
