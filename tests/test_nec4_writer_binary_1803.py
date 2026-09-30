"""AK#1803: the NEC-4 writer's decks against the licensed NEC-4.2 binary.

Skipped unless ``$NEC42_EXE`` names a working NEC-4.2 (`probe_nec42`), so the
default lane passes cleanly without one; the NEC-5 comparison additionally
needs ``$NEC5_EXE`` and nec2c's needs ``nec2c`` on PATH. Every number compared
live is produced by a run in the test itself. The recorded values below are
small numeric expectations from our own runs, not NEC-4.2 printouts.

NEC-4.2: Burke, G. & Poggio, A. (2011). Numerical Electromagnetics Code
version 4.2. LLNL-CODE-491368.
"""

from __future__ import annotations

import shutil
from types import MappingProxyType

import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.engines import nec2 as nec2_mod
from antennaknobs.engines import nec42 as nec42_mod
from antennaknobs.engines.nec2 import NEC2Engine
from antennaknobs.engines.nec42 import NEC42Engine, probe_nec42
from antennaknobs.nec_export import export_nec
from antennaknobs.network import (
    Driven,
    DrivenCurrent,
    GradedSegments,
    Network,
    PortOnWire,
    Wire,
)
from antennaknobs.web.examples import REGISTRY

SOIL = ("finite", 13.0, 0.005)

needs_nec42 = pytest.mark.skipif(
    probe_nec42() is None,
    reason="no licensed NEC-4.2 binary ($NEC42_EXE unset or not a working NEC-4.2)",
)


def _nec2c() -> str:
    exe = shutil.which("nec2c")
    if exe is None:
        pytest.skip("nec2c not on PATH")
    return exe


def _nec5():
    from antennaknobs.engines.nec5 import probe_nec5

    if probe_nec5() is None:
        pytest.skip("no NEC-5 binary ($NEC5_EXE unset or not a working NEC-5)")


def _rel(a: complex, b: complex) -> float:
    return abs(a - b) / abs(b)


# --------------------------------------------------------------------------
# free space: NEC-4.2 against nec2c, within 0.05 %
# --------------------------------------------------------------------------

# Measured 2026-09-29 (release-7768648 nec42cl-omp vs nec2c): 0.0023, 0.0047,
# 0.0008, 0.0017 and 0.0317 %.
FREE = [
    "dipoles.invvee",
    "wire.sterba",
    "arrays.delta_looparray_2x2",
    "wire.rhombic",
    "beams.owa_yagi_6el",
]


@needs_nec42
@pytest.mark.parametrize("name", FREE)
def test_free_space_impedance_agrees_with_nec2c(name):
    cls = REGISTRY[name].builder_cls
    z42 = NEC42Engine(cls(), ground="free").impedance()
    z2 = NEC2Engine(cls(), ground="free", nec2_exe=_nec2c()).impedance()
    assert len(z42) == len(z2)
    for a, b in zip(z42, z2, strict=True):
        assert _rel(a, b) < 5e-4, (name, a, b)


def _graded_dipole():
    """A centre-fed dipole whose arms are graded toward the feed: two graded
    wires either side of a 3-segment feed wire, so the chain and the EX
    renumbering (tag 2 authored, tag 4 written) are both in play."""
    fracs, counts = (0.6, 0.9), (9, 5, 3)

    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": 14.2})

        def build_wires(self):
            return [
                Wire((0, -5, 10), (0, -0.1, 10), GradedSegments(fracs, counts)),
                Wire((0, -0.1, 10), (0, 0.1, 10), 3, ex=1 + 0j, name="feed"),
                Wire(
                    (0, 0.1, 10),
                    (0, 5, 10),
                    GradedSegments(
                        tuple(1 - f for f in reversed(fracs)), tuple(reversed(counts))
                    ),
                ),
            ]

    b = B()
    b.freq = 14.2
    return b


@needs_nec42
def test_a_graded_deck_runs_the_same_on_nec42_and_nec2c():
    """The chained-GW spelling of a graded mesh, in free space (where nec2c
    reads the deck too): one deck, two programs, one impedance. Measured
    0.0010 %.

    Not the catalog's graded buried vertical: its free-space deck (five wires
    at one node, a 5 cm gap segment beside 1.25 cm ones) reads 22.37-96.69j
    on NEC-4.2 and 22.49-99.87j on nec2c, 3.3 % apart, and that is the two
    programs' junction treatment, not the writer's cards."""
    deck = export_nec(
        _graded_dipole(), ground="free", include_rp=False, dialect="nec42"
    )
    assert [ln.split()[2] for ln in deck.splitlines() if ln.startswith("GW ")] == [
        "9",
        "5",
        "3",
        "3",
        "3",
        "5",
        "9",
    ]
    assert "EX 0 4 2 0 1 0" in deck.splitlines()
    parse = NEC2Engine._parse_input_parameters
    ((_t, _s, z42),) = parse(nec42_mod.run_deck(probe_nec42(), deck, timeout=120))[0]
    ((_t, _s, z2),) = parse(nec2_mod.run_deck(_nec2c(), deck, timeout=120))[0]
    assert _rel(z42, z2) < 5e-4, (z42, z2)


# --------------------------------------------------------------------------
# EX 6
# --------------------------------------------------------------------------


def _dipole(source):
    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.47})

        def build_wires(self):
            return [Wire((-2.5, 0, 0), (2.5, 0, 0), 21, name="feed")]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed")}, branches=[], sources=[source]
            )

    b = B()
    b.freq = 28.47
    return b


@needs_nec42
def test_the_ex6_dipole_equals_its_ex0_twin_exactly():
    """The check set's claim, on the writer's own decks: a current source and
    a voltage source on the same segment print the same impedance."""
    e6 = NEC42Engine(_dipole(DrivenCurrent(port="feed", current=1 + 0j)), ground="free")
    e0 = NEC42Engine(_dipole(Driven(port="feed", voltage=1 + 0j)), ground="free")
    assert "EX 6 1 11 0 1 0" in e6.deck(28.47).splitlines()
    zs6, _cur, _b = e6.solve_snapshot()
    zs0, _cur, _b = e0.solve_snapshot()
    assert zs6 == zs0
    # The drive is the forced current, in amps; the twin's is 1 V.
    assert e6._excited_feed_units == ["A"] and e6._excited_feed_values == [1 + 0j]
    assert e0._excited_feed_units == ["V"] and e0._excited_feed_values == [1 + 0j]


# --------------------------------------------------------------------------
# Sommerfeld: NEC-4.2 against NEC-5, recorded
# --------------------------------------------------------------------------

# (design, rung) -> (NEC-4.2 Z, NEC-5 Z), both through this repo's engines at
# the catalog's somm13 ground, measured 2026-09-29 (release-7768648
# nec42cl-omp; nec5cl). Not an agreement bar: NEC-4.2 feeds a segment centre
# and NEC-5 a knot, so the two meshes differ by parity, and the gap is mostly
# reactance that shrinks under refinement (the check set's finding). The
# refined buried vertical sits at 3.8 % where the stopgap deck's 3-segment
# feed wire read 0.74 %: the writer keeps the design's own 1-segment gap wire.
SOMMERFELD = {
    ("dipoles.invvee", "default"): (48.5769 - 8.5359j, 48.4970 - 11.3780j),
    ("wire.sterba", "default"): (617.2470 + 240.9790j, 617.6200 + 201.4100j),
    ("specialty.buried_dipole", "default"): (
        136.4820 + 41.7139j,
        146.3900 + 44.3820j,
    ),
    ("specialty.buried_dipole", "refined"): (
        144.8500 + 44.2364j,
        146.4800 + 44.3820j,
    ),
    ("verticals.buried_radial_vertical", "default"): (
        80.2239 + 48.8619j,
        77.8050 + 44.4680j,
    ),
    ("verticals.buried_radial_vertical", "refined"): (
        79.4136 + 48.3276j,
        77.9370 + 45.2030j,
    ),
}


def _built(name, rung):
    b = REGISTRY[name].builder_cls()
    if rung == "refined":
        b.nominal_nsegs = b.nominal_nsegs * 2
    return b


@needs_nec42
@pytest.mark.parametrize(("name", "rung"), list(SOMMERFELD))
def test_sommerfeld_impedance_against_nec5_is_the_recorded_pair(name, rung):
    z42_rec, z5_rec = SOMMERFELD[(name, rung)]
    z42 = NEC42Engine(_built(name, rung), ground=SOIL).impedance()[0]
    # The printout carries 6 figures; another build may move the last one.
    assert _rel(z42, z42_rec) < 1e-4, (z42, z42_rec)
    _nec5()
    from antennaknobs.engines.nec5 import NEC5Engine

    z5 = NEC5Engine(_built(name, rung), ground=SOIL).impedance()[0]
    assert _rel(z5, z5_rec) < 1e-4, (z5, z5_rec)


@needs_nec42
def test_gn3_runs_and_sits_beside_gn2():
    """NEC-4.2's newer Sommerfeld, from the writer's GN 3 card: the check set
    measured 48.5803-8.5413j beside GN 2's 48.5769-8.5359j."""
    cls = REGISTRY["dipoles.invvee"].builder_cls
    z3 = NEC42Engine(cls(), ground=SOIL, sommerfeld=3).impedance()[0]
    z2 = NEC42Engine(cls(), ground=SOIL).impedance()[0]
    assert z3 != z2
    assert _rel(z3, z2) < 1e-3, (z3, z2)
