"""AK#1708: an LD range wider than 8 segments, and two loads on one segment.

Both used to be dropped with a note, which imported a different antenna:
`36ccd` (a capacitor in each of 24 segments) came in as a bare full-wave
dipole, and `UA3SFH`'s trap lost the series capacitor on its fed segment.

NEC's rule for two loads on one segment is that their impedances ADD. The
fixtures pin it with nec2c 1.3.1's own printouts (``*.out`` beside each deck,
generated with ``nec2c -i deck.nec -o deck.out``): two cards answer exactly
what one card with the summed impedance answers, in series order or not, with
a parallel trap beside a series C, on a fed segment or not, and nec2c prints
"LOADED TWICE - IMPEDANCES ADDED" where it applies the rule. The licensed
NEC-5 prints the same note and answers the summed load to the digit (checked
2026-10-04, black box; not a fixture).

``ccd36_*.nec`` are `36ccd` (nec-wild ``community/icecube-dbesson``) with its
SY symbols evaluated, since nec2c reads no SY, and in free space.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pytest

from antennaknobs.cli import _GROUND_UNSET, make_engine_factory, resolve_ground
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Load

FIXTURES = Path(__file__).parent / "fixtures" / "ld_ranges_stacked_1708"
_E = r"(-?\d\.\d+E[+-]\d+)"
_INPUT = re.compile(r"^\s+\d+\s+\d+" + r"\s+" + r"\s+".join([_E] * 6), re.M)


def _printed_z(stem: str) -> complex:
    """The first source's impedance from nec2c's ANTENNA INPUT PARAMETERS."""
    text = (FIXTURES / f"{stem}.out").read_text()
    m = _INPUT.search(text.split("ANTENNA INPUT PARAMETERS")[1])
    return complex(float(m.group(5)), float(m.group(6)))


def _added(stem: str) -> bool:
    return "IMPEDANCES ADDED" in (FIXTURES / f"{stem}.out").read_text()


def _deck(stem: str):
    path = FIXTURES / f"{stem}.nec"
    return parse_nec(path.read_text(), name=path.name, network=True)


def _z(stem: str, engine: str) -> complex:
    """The ``@deck.nec`` route, as ``antennaknobs analyze`` takes it."""
    cls = builder_from_file(str(FIXTURES / f"{stem}.nec"))
    factory = make_engine_factory(engine, resolve_ground(_GROUND_UNSET, cls))
    return complex(np.atleast_1d(np.asarray(factory(cls()).impedance()))[0])


# --- the oracle's rule, as printed -----------------------------------------


@pytest.mark.parametrize(
    ("two", "one"),
    [
        ("stacked_two", "stacked_one"),
        ("stacked_par_ser", "stacked_fixed"),
        ("stacked_fed_par_ser", "stacked_fed_fixed"),
    ],
)
def test_nec2c_adds_two_loads_on_one_segment(two, one):
    assert _added(two) and not _added(one)
    assert _printed_z(two) == _printed_z(one)


# --- the import -------------------------------------------------------------


def test_every_capacitor_of_36ccd_is_a_load():
    deck = _deck("ccd36_loaded")
    assert "LD" not in deck.ignored
    by_tag = {}
    for ld in deck.loads:
        assert ld.c == pytest.approx(377.82e-12) and ld.r is None and ld.l is None
        by_tag.setdefault(deck.wires[ld.wire].tag, []).append(ld.seg)
    assert by_tag == {2: list(range(1, 13)), 4: list(range(1, 13))}
    # One port per loaded segment, on the uncut wires.
    net = deck.network()
    assert sum(isinstance(b, Load) for b in net.branches) == 24
    assert len(deck.wire_tuples()) == 5


@pytest.mark.parametrize("stem", ["stacked_two", "stacked_fed_par_ser"])
def test_both_loads_land_on_one_port(stem):
    deck = _deck(stem)
    assert "LD" not in deck.ignored
    assert len(deck.loads) == 2
    assert len({(ld.wire, ld.seg) for ld in deck.loads}) == 1
    ports = [b.port for b in deck.network().branches if isinstance(b, Load)]
    assert len(ports) == 2 and len(set(ports)) == 1


def test_a_second_load_at_a_line_connection_is_still_refused():
    """There each load is a series branch to the node the line moved to, so a
    second one would sit in parallel with the first."""
    text = (
        "GW 1 7 0 -3.5 10 0 3.5 10 0.001\nGW 2 7 1 -3.5 10 1 3.5 10 0.001\nGE\n"
        "EX 0 1 4 0 1 0\nTL 1 2 2 2 300 1.5 0 0 0 0\n"
        "LD 4 1 2 2 5 0\nLD 4 1 2 2 7 0\nEN\n"
    )
    deck = parse_nec(text, network=True)
    assert len(deck.loads) == 1
    assert any("second load at a TL/NT" in why for _m, why in deck.ignored_detail)


# --- the solve ----------------------------------------------------------------


@pytest.mark.parametrize("engine", ["momwire:bspline", "pynec"])
def test_two_series_cards_solve_as_their_sum(engine):
    """On our side of the seam the rule is exact: the two-card deck and the
    one-card deck are one circuit, to round-off."""
    if engine == "pynec":
        pytest.importorskip("PyNEC")
    z_two, z_one = _z("stacked_two", engine), _z("stacked_one", engine)
    assert z_two == pytest.approx(z_one, rel=1e-9)


def _trap_plus_c(f_mhz: float) -> complex:
    """The two stacked cards' summed impedance: a parallel RLC (1 kohm, 2 uH,
    50 pF) in series with 100 pF."""
    w = 2.0 * math.pi * f_mhz * 1e6
    tank = 1.0 / (1.0 / 1000.0 + 1.0 / (1j * w * 2e-6) + 1j * w * 50e-12)
    return tank + 1.0 / (1j * w * 100e-12)


@pytest.mark.parametrize("stem", ["stacked_par_ser", "stacked_fed_par_ser"])
def test_a_trap_and_a_series_c_solve_as_their_sum(tmp_path, stem):
    """The trap beside a series C, on and off the fed segment, against ONE
    fixed load of their summed impedance (momwire bspline, exact).

    The fixed load is evaluated at 14 MHz x 299.792458/299.8, not at the deck's
    14 MHz: a file design's network is stamped 25 ppm below its frequency
    (AK#1685, NEC's c against SI c), and a fixed impedance cannot follow it.
    When AK#1685 is fixed this factor goes."""
    fixed = (FIXTURES / stem.replace("par_ser", "fixed")).with_suffix(".nec")
    z = _trap_plus_c(14.0 * 299.792458 / 299.8)
    text = re.sub(
        r"^LD 4 (\d+ \d+ \d+) .*$",
        lambda m: f"LD 4 {m.group(1)} {z.real!r} {z.imag!r}",
        fixed.read_text(),
        flags=re.M,
    )
    one = tmp_path / fixed.name
    one.write_text(text)
    cls = builder_from_file(str(one))
    factory = make_engine_factory("momwire:bspline", resolve_ground(_GROUND_UNSET, cls))
    z_one = complex(np.atleast_1d(np.asarray(factory(cls()).impedance()))[0])
    assert _z(stem, "momwire:bspline") == pytest.approx(z_one, rel=1e-9)


@pytest.mark.parametrize(
    "stem", ["stacked_two", "stacked_par_ser", "stacked_fed_par_ser", "ccd36_loaded"]
)
def test_pynec_answers_nec2cs_printout(stem):
    """Through the import PyNEC answers nec2c's printed impedance with the
    loads applied as NEC applies them. PyNEC is nec2++, not nec2c: on these
    decks the two differ by up to 3.4e-4 (measured), so the bar is 1e-3, far
    below what dropping or paralleling a load moves (36ccd bare: 6357 ohm)."""
    pytest.importorskip("PyNEC")
    z, ref = _z(stem, "pynec"), _printed_z(stem)
    assert abs(z - ref) / abs(ref) < 1e-3, (z, ref)


def test_the_capacitors_move_36ccd_to_resonance():
    """The acceptance's "visibly": the loaded wire is near series resonance at
    3.5 MHz, the bare one is a full-wave dipole far from it."""
    loaded, bare = _printed_z("ccd36_loaded"), _printed_z("ccd36_bare")
    assert abs(loaded.imag) < 0.3 * loaded.real
    assert bare.real > 20 * loaded.real
    z = _z("ccd36_loaded", "momwire:bspline")
    assert abs(z - loaded) / abs(loaded) < 0.05, (z, loaded)
