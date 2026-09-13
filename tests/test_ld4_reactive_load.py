"""Issue #422: a fixed-complex-Z (frequency-independent) series Load.

A NEC ``LD`` card type 4 is a fixed ``R + jX`` impedance in SERIES with a
segment's current path. Unlike the shunt-to-common ``Admittance`` (issue #416,
which handles the reactive NT / TL-end-shunt cases), this is the series sibling:
it becomes the reducer's group-2 termination, composed with any feed EMF, so on
a *driven+loaded* segment it correctly adds to the driving-point Z where a shunt
would be silently wrong.

Two layers, mirroring test_admittance_branch.py: circuit-theory oracles on a
synthetic antenna Y (fast, no MoM), then a cross-engine MoM check that PyNEC
(native ld_card type 4) and momwire (reducer stamp) agree once the load is in
the solve — including the load-on-the-fed-segment case.
"""

import shutil

import numpy as np
import pytest

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import MomwireEngine, PyNECEngine
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import (
    Driven,
    Load,
    Network,
    PortOnWire,
    PortVirtual,
    load_impedance,
)
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer
from momwire import SinusoidalSolver

FREQ_MHZ = 28.0
WL = C_LIGHT / (FREQ_MHZ * 1e6)


def synth_y(n, seed):
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))
    y = 0.004 * (a + a.T) / 2.0
    return y + np.eye(n) * (0.02 + 0.008j)


def reducer(net, n_real):
    real = [n for n, p in net.ports.items() if isinstance(p, PortOnWire)]
    virt = [n for n, p in net.ports.items() if isinstance(p, PortVirtual)]
    port_to_idx = {n: i for i, n in enumerate(real + virt)}
    return NetworkReducer(net, port_to_idx, len(real) + len(virt))


# ---------------------------------------------------------------------------
# 1. Primitive: Load.z is a fixed series impedance
# ---------------------------------------------------------------------------
def test_fixed_z_load_impedance_is_z_at_every_frequency():
    br = Load(port="p", z=30.0 - 40.0j)
    assert load_impedance(br, 2 * np.pi * 10e6) == 30.0 - 40.0j
    assert load_impedance(br, 2 * np.pi * 30e6) == 30.0 - 40.0j


def test_fixed_z_series_load_on_driven_port_adds_to_z():
    """Z_seen = Z_L + 1/Y00 — the load is in series with the feed (a shunt
    would instead give 1/(Y00 + 1/Z_L)). Frequency-independent, so identical
    at two wavelengths despite a reactive Z_L."""
    y = synth_y(1, 5)
    z_l = 60.0 + 25.0j
    net = Network(
        ports={"f": PortOnWire("f")},
        branches=[Load(port="f", z=z_l)],
        sources=[Driven(port="f")],
    )
    red = reducer(net, 1)
    z1 = red.driven_impedance(y, C_LIGHT / 10e6)[0]
    z2 = red.driven_impedance(y, C_LIGHT / 30e6)[0]
    assert z1 == pytest.approx(z_l + 1.0 / y[0, 0], rel=1e-12)
    assert z1 == pytest.approx(z2, rel=1e-12)  # fixed, not jωL-scaled


def test_fixed_z_load_rejects_rlc_legs():
    # z is mutually exclusive with the frequency-dependent R/L/C legs.
    with pytest.raises(ValueError):
        Load(port="p", z=10 + 5j, r=3.0)
    with pytest.raises(ValueError):
        Load(port="p", z=10 + 5j, l=1e-6)
    with pytest.raises(ValueError):
        Load(port="p", z=10 + 5j, parallel=True)


# ---------------------------------------------------------------------------
# 2. nec_import translation of an LD 4 reactive load (issue #422)
# ---------------------------------------------------------------------------
def _dipole7(*cards):
    return (
        "GW 1 7 0 -3.5 10 0 3.5 10 0.001\nGE 0\nEX 0 1 4 0 1 0\n"
        + "".join(c + "\n" for c in cards)
        + "EN\n"
    )


def test_ld4_reactive_translates_to_fixed_z_load():
    """LD 4 tag s0 s1 R X (X != 0) is no longer dropped — it becomes a fixed
    complex-Z series Load, exact at every frequency."""
    deck = parse_nec(_dipole7("LD 4 1 2 2 100 -50"), network=True)
    assert "LD" not in deck.ignored
    assert not any(m == "LD" for m, _ in deck.ignored_detail)
    (ld,) = deck.loads
    assert ld.z == complex(100.0, -50.0)
    assert ld.r is None and ld.l is None and ld.c is None
    (br,) = deck.network().branches
    assert isinstance(br, Load) and br.z == complex(100.0, -50.0)


# ---------------------------------------------------------------------------
# 3. Cross-engine MoM oracle: PyNEC (native ld_card 4) and momwire (reducer)
# ---------------------------------------------------------------------------
def _deck_builder(deck, freq=FREQ_MHZ):
    class B(AntennaBuilder):
        default_params = {"freq": freq}

        def build_wires(self):
            return deck.wire_tuples()

        def build_network(self):
            return deck.network()

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    return B()


def _mw_z(deck):
    return MomwireEngine(
        _deck_builder(deck), solver=SinusoidalSolver, ground="free"
    ).impedance()[0]


def _cross_engine(deck):
    b = _deck_builder(deck)
    z_pynec = PyNECEngine(b, ground="free").impedance()[0]
    z_mw = MomwireEngine(b, solver=SinusoidalSolver, ground="free").impedance()[0]
    return z_pynec, z_mw


def test_ld4_reactive_on_fed_segment_cross_engine_agrees():
    """The load sits on the FED segment — the case a shunt gets wrong (the
    ideal source pins the node, so a shunt never reaches the driving-point Z).
    As a series Load it adds to Z: Z = Z_bare + (120 − 60j), exactly the
    independent circuit calc, and PyNEC's native ld_card type 4 agrees with
    momwire's reducer stamp. (Both assertions fail if the load is dropped.)"""
    deck = parse_nec(_dipole7("LD 4 1 4 4 120 -60"), network=True)
    z_pynec, z_mw = _cross_engine(deck)
    assert abs(z_pynec - z_mw) / abs(z_mw) < 0.02
    z_bare = _mw_z(parse_nec(_dipole7(), network=True))
    assert z_mw == pytest.approx(z_bare + (120.0 - 60.0j), rel=0.02)


def test_ld4_reactive_on_parasitic_segment_cross_engine_agrees():
    """A reactively-loaded parasite (two-element deck): the load is on an
    undriven segment; both engines agree, and the reactive load measurably
    shifts the driven Z (so the test fails if the load is dropped)."""
    loaded = (
        "GW 1 7 0 -3.5 10 0 3.5 10 0.001\n"
        "GW 2 7 1.5 -3.5 10 1.5 3.5 10 0.001\n"
        "GE 0\n"
        "EX 0 1 4 0 1 0\n"
        "{ld}"
        "EN\n"
    )
    deck = parse_nec(loaded.format(ld="LD 4 2 4 4 80 40\n"), network=True)
    z_pynec, z_mw = _cross_engine(deck)
    assert abs(z_pynec - z_mw) / abs(z_mw) < 0.02
    z_bare = _mw_z(parse_nec(loaded.format(ld=""), network=True))
    assert abs(z_mw - z_bare) > 1.0


# ---------------------------------------------------------------------------
# 4. export_nec writes the fixed-z load as LD 4 (antennaknobs#1485)
# ---------------------------------------------------------------------------
def _ld_rows(text, ldtyp):
    return [ln.split() for ln in text.splitlines() if ln.split()[:2] == ["LD", ldtyp]]


def _export(builder):
    pytest.importorskip("PyNEC")
    from antennaknobs.nec_export import export_nec

    return export_nec(builder, ground="free", include_rp=False)


def test_export_writes_a_fixed_z_load_as_ld4_at_its_segment():
    """The hole in #1485: `export_nec` read only a Load's R/L/C legs, so a
    `Load(z=...)` fell through to the all-zero `continue`, no card was written,
    and the NEC-2 tab, which runs this export, solved the design without its
    load. It is now PyNECEngine's `ld_card(4, tag, seg, seg, R, X, 0)` as text,
    on the segment PyNECEngine puts that card on.

    That location is in the export's own numbering, not the imported deck's:
    the importer gives a loaded segment a one-segment wire of its own, and the
    export numbers wires by the GW cards it writes. So the row does not read
    "tag 1 seg 2" the way the source deck did, and asserting that would test
    the importer, not this card."""
    deck = parse_nec(_dipole7("LD 4 1 2 2 100 -50"), network=True)
    (row,) = _ld_rows(_export(_deck_builder(deck)), "4")
    eng = PyNECEngine(_deck_builder(deck), ground="free")
    (load,) = [br for br in eng._network.branches if isinstance(br, Load)]
    tag, seg = eng._network_port_loc[load.port]
    assert row[2:5] == [str(tag), str(seg), str(seg)], (row, tag, seg)
    assert [float(v) for v in row[5:8]] == [100.0, -50.0, 0.0], row


def test_the_exported_ld4_reads_back_as_the_same_load():
    """Import the export and export it again: the same fixed-z load comes back,
    and the second export repeats the first, card for card, so the LD 4 names
    the same segment of the same geometry both times."""
    deck = parse_nec(_dipole7("LD 4 1 2 2 100 -50"), network=True)
    first = _export(_deck_builder(deck))
    back = parse_nec(first, network=True)
    assert [ld.z for ld in back.loads] == [complex(100.0, -50.0)]
    second = _export(_deck_builder(back))
    cards = ("GW", "GE", "LD", "EX", "FR")
    assert [ln for ln in second.splitlines() if ln[:2] in cards] == [
        ln for ln in first.splitlines() if ln[:2] in cards
    ]


def test_a_zero_fixed_z_load_writes_no_card():
    """z == 0 is no load at all: PyNECEngine skips its ld_card, and the export
    writes nothing for it either."""
    deck = parse_nec(_dipole7("LD 4 1 2 2 100 -50"), network=True)
    net = deck.network()
    zeroed = Network(
        ports=net.ports,
        branches=[
            Load(port=br.port, z=0j) if isinstance(br, Load) else br
            for br in net.branches
        ],
        sources=net.sources,
    )

    class ZeroLoad(type(_deck_builder(deck))):
        def build_network(self):
            return zeroed

    assert _ld_rows(_export(ZeroLoad()), "4") == []


@pytest.mark.skipif(shutil.which("nec2c") is None, reason="nec2c CLI not installed")
def test_the_nec2_tab_solves_the_fixed_z_load_it_used_to_drop(monkeypatch):
    """The NEC-2 tab (`NEC2Engine`) runs `export_nec`'s deck through the user's
    own binary, so until the hole in #1485 was filled it disagreed with PyNEC on
    a z-load design by exactly the missing load. Against a real nec2c it now
    agrees with PyNEC to the repo's nec2c bar (0.1 ohm, `test_nec_export.py`),
    and it is nowhere near the load-free impedance."""
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.nec2 import NEC2Engine

    monkeypatch.setenv("NEC2_EXE", shutil.which("nec2c"))
    loaded = _dipole7("LD 4 1 2 2 100 -50")

    def z_of(engine_cls, text):
        builder = _deck_builder(parse_nec(text, network=True))
        return complex(np.atleast_1d(engine_cls(builder, ground="free").impedance())[0])

    z_nec2 = z_of(NEC2Engine, loaded)
    z_pynec = z_of(PyNECEngine, loaded)
    z_bare = z_of(PyNECEngine, _dipole7())
    assert abs(z_nec2 - z_pynec) < 0.1, (z_nec2, z_pynec)
    assert abs(z_nec2 - z_bare) > 1.0, (z_nec2, z_bare)
