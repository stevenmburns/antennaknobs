"""Loads at a TL/NT connection point: a parallel RLC, and several loads on
one site, solve as the impedance NEC would sum there.

Reported by AC6LA's decks: EZNEC writes a parallel trap (LD 1) on a segment
a transmission line attaches to, and the importer used to refuse it (the
.nec) or fail its own read-back check (the .ez). The decks here are
synthetic; the reports' model files are private.

Each case is checked against ONE fixed-impedance LD 4 at the same site whose
R + jX is the expected impedance at the deck's frequency (momwire bspline,
exact to round-off).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from antennaknobs.cli import _GROUND_UNSET, make_engine_factory, resolve_ground
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec

F_MHZ = 14.0
_HEAD = (
    "CM connection-point loads\nCE\n"
    "GW 1 7 0 -3.5 10 0 3.5 10 0.001\nGW 2 7 1 -3.5 10 1 3.5 10 0.001\nGE\n"
    "EX 0 1 4 0 1 0\nTL 1 2 2 4 300 1.5 0 0 0 0\n"
)
_TAIL = f"FR 0 1 0 0 {F_MHZ} 0\nXQ\nEN\n"


def _z(tmp_path, name: str, loads: str) -> complex:
    path = tmp_path / f"{name}.nec"
    path.write_text(_HEAD + loads + _TAIL)
    cls = builder_from_file(str(path))
    factory = make_engine_factory("momwire:bspline", resolve_ground(_GROUND_UNSET, cls))
    return complex(np.atleast_1d(np.asarray(factory(cls()).impedance()))[0])


def _fixed(z: complex) -> str:
    return f"LD 4 1 2 2 {z.real!r} {z.imag!r}\n"


def _tank(r: float, l_h: float, c_f: float) -> complex:
    w = 2.0 * math.pi * F_MHZ * 1e6
    return 1.0 / (1.0 / r + 1.0 / (1j * w * l_h) + 1j * w * c_f)


def test_a_parallel_rlc_is_imported_not_refused():
    deck = parse_nec(_HEAD + "LD 1 1 2 2 1000 2e-6 50e-12\n" + _TAIL, network=True)
    assert len(deck.loads) == 1
    assert not any("TL/NT" in why for _m, why in deck.ignored_detail)


def test_a_parallel_rlc_solves_as_its_impedance(tmp_path):
    z = _z(tmp_path, "trap", "LD 1 1 2 2 1000 2e-6 50e-12\n")
    ref = _z(tmp_path, "fixed", _fixed(_tank(1000.0, 2e-6, 50e-12)))
    assert z == pytest.approx(ref, rel=1e-9)


def test_a_parallel_lc_with_no_r_solves_as_its_impedance(tmp_path):
    """A zero R in a parallel card means no resistor, not a short."""
    z = _z(tmp_path, "lc", "LD 1 1 2 2 0 2e-6 50e-12\n")
    ref = _z(tmp_path, "fixed", _fixed(_tank(math.inf, 2e-6, 50e-12)))
    assert z == pytest.approx(ref, rel=1e-9)


def test_two_loads_on_one_connection_solve_as_their_sum(tmp_path):
    w = 2.0 * math.pi * F_MHZ * 1e6
    z = _z(tmp_path, "two", "LD 1 1 2 2 1000 2e-6 50e-12\nLD 0 1 2 2 5 0 100e-12\n")
    ref = _z(
        tmp_path,
        "fixed",
        _fixed(_tank(1000.0, 2e-6, 50e-12) + 5 + 1 / (1j * w * 100e-12)),
    )
    assert z == pytest.approx(ref, rel=1e-9)


def test_three_fixed_loads_on_one_connection_solve_as_their_sum(tmp_path):
    z = _z(tmp_path, "three", "LD 4 1 2 2 5 7\nLD 4 1 2 2 11 -3\nLD 4 1 2 2 2 20\n")
    ref = _z(tmp_path, "fixed", _fixed(complex(18, 24)))
    assert z == pytest.approx(ref, rel=1e-9)
