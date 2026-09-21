"""NEC5Engine feeds a port at a wire END at that end, and reads every port's
current from NEC-5's own source rows (AK#1629).

Two defects, found triaging AC6LA's Cardioid (QRZ 1003328 #115), both in the
engine that had no gate against an external reference.

THE ADDRESS. `gap_knot` clamped every position into the interior knots, so a
port at arclength 0.0 took knot 1 and a base-fed vertical was driven a whole
segment up its wire (and 1.0 took knot n - 1). Dan's two-element Cardioid read
35.908 - 26.657j / 67.379 + 13.518j against EZNEC's 32.09 - 25.43j /
63.35 + 10.31j. An endpoint is a knot, `on_site`'s rule since AK#1605: knot 0
is segment 1 end 1, the address `p0` already took.

THE READOUT. The multiport-Y route read each undriven port's current by
interpolating the `Wire Currents` table, which carries segment CENTRES only.
NEC-5's basis is a tent on the knots, so a centre is the mean of two knot
values and no interpolation between centres recovers one: 2.4 % out at the
centre knot of a ten-segment dipole, and at a wire's p0 it took the first
segment's centre outright. The four-squares, whose ports all sit at p0, came
out 5-10 % wrong, and passed the reciprocity gate at a residual of exactly
0.0 because the error was as symmetric as the array. Every entry of Y now
comes from an ANTENNA INPUT PARAMETERS row: the undriven ports carry a
`_PROBE_VOLTS` source, whose row is the knot's own current.

Over the 80-deck EZNEC corpus plus the Cardioid, against the licensed engine
run on EZNEC's own deck text: before, 9 refused and 35 were out by more than
1e-2; after, all 81 solve and the worst is 2.6e-4. The licensed-box tests at
the bottom keep five of those decks as a standing gate.
"""

from __future__ import annotations

import pathlib
from types import MappingProxyType, SimpleNamespace

import momwire
import numpy as np
import pytest
from conftest import needs_nec5, nec5_fake_y_runs

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import nec5
from antennaknobs.engines.nec5 import NEC5Engine, NEC5Error
from antennaknobs.file_designs import builder_from_file
from antennaknobs.network import (
    TL,
    Driven,
    Load,
    Network,
    PortOnWire,
    PortVirtual,
    Wire,
)
from antennaknobs.wire_catalog import gap_knot

HERE = pathlib.Path(__file__).parent
CORPUS = (
    pathlib.Path(momwire.__file__).resolve().parents[2] / "tests/fixtures/eznec/decks"
)
CARDIOID = HERE / "fixtures" / "eznec_gyrator_1595" / "Cardioidmodnec5.nec"


# ---------------------------------------------------------------------------
# the address
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("at", "knot"),
    [(0.0, 0), (1.0, 6), (0, 0), (1, 6), (1e-9, 1), (1 - 1e-9, 5), (0.5, 3)],
)
def test_an_end_is_a_knot(at, knot):
    """The ends are knots 0 and n; anything short of an end still takes the
    nearest INTERIOR knot, exactly as before."""
    assert gap_knot(6, at) == knot


class _BaseFedVertical(AntennaBuilder):
    """A ground-mounted vertical fed AT the contact, with a load partway up
    that is off every site, so the knot engine cuts the wire there. The load
    port then shares the first piece with the feed and takes the positioned
    spelling at that piece's far end, 1.0 (AK#1619) — so this one design holds
    BOTH ends of the defect."""

    default_params = MappingProxyType({"freq": 7.1, "design_freq": 7.1})

    def build_wires(self):
        return [Wire((0.0, 0.0, 0.0), (0.0, 0.0, 10.0), n_seg=6, name="w")]

    def build_wire_material(self):
        return WireSpec(radius=1e-3)

    def build_network(self):
        return Network(
            ports={
                "feed": PortOnWire("feed", wire="w", at=0.0),
                "load": PortOnWire("load", wire="w", at=0.31),
            },
            branches=[Load(port="load", r=50.0)],
            sources=[Driven(port="feed")],
        )


def test_a_base_feed_and_a_cut_load_sit_where_the_design_puts_them():
    """Before AK#1629 both landed on the MIDDLE knot of the first piece — the
    feed clamped up from 0.0 and the load clamped down from 1.0 — one knot
    for two ports, neither of them where the design put it."""
    eng = NEC5Engine(_BaseFedVertical(), ground="pec", require_exe=False)
    assert [(i, knot) for i, _t, _v, knot in eng._sources] == [(0, 0.0)]
    ((idx, load_knot, _br),) = eng._loads
    assert (idx, load_knot) == (0, 1.0)
    n0 = eng._wires[0].n_seg
    deck = eng.deck([7.1])
    assert "EX 0 1 1 1 " in deck  # segment 1 end 1: the contact
    assert f"LD 0 1 {n0} 2 " in deck  # the last knot of the piece: the cut
    top = np.asarray(eng._wires[0].p1)
    assert np.linalg.norm(top - (0.0, 0.0, 3.1)) < 1e-9


# ---------------------------------------------------------------------------
# the readout, through a fake binary
# ---------------------------------------------------------------------------


class _ThreePorts(AntennaBuilder):
    """Three real ports on three wires, one at each kind of site: a centre
    knot, a wire's p0 standing on the ground, and an interior knot off the
    middle. A line from a virtual source sends it down the multiport-Y route."""

    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})

    def build_wires(self):
        return [
            Wire((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), n_seg=10, name="a"),
            Wire((3.0, 0.0, 0.0), (3.0, 0.0, 5.0), n_seg=10, name="b"),
            Wire((6.0, -5.0, 10.0), (6.0, 5.0, 10.0), n_seg=10, name="c"),
        ]

    def build_wire_material(self):
        return WireSpec(radius=1e-3)

    def build_network(self):
        return Network(
            ports={
                "src": PortVirtual("src"),
                "a": PortOnWire("a"),
                "b": PortOnWire("b", wire="b", at=0.0),
                "c": PortOnWire("c", wire="c", at=0.3),
            },
            branches=[
                TL(a="src", b="a", z0=50.0, length=3.0),
                TL(a="a", b="b", z0=50.0, length=2.0),
                TL(a="a", b="c", z0=75.0, length=4.0),
            ],
            sources=[Driven(port="src")],
        )


# A symmetric Y whose entries are all distinct, so a row read into the wrong
# port cannot land on a value it happens to share.
_Y = np.array(
    [
        [2.1e-3 - 8.1e-3j, 3.3e-4 + 1.7e-4j, -1.9e-4 + 2.9e-4j],
        [3.3e-4 + 1.7e-4j, 8.7e-3 - 9.5e-3j, 4.4e-5 - 6.1e-5j],
        [-1.9e-4 + 2.9e-4j, 4.4e-5 - 6.1e-5j, 5.2e-3 + 1.3e-3j],
    ]
)
# Where each port's EX lands: tag, segment, end.
_ADDRESS = {"a": "1 5 2", "b": "2 1 1", "c": "3 3 2"}


def _ex_cards(deck):
    return [ln.split() for ln in deck.splitlines() if ln.startswith("EX ")]


def test_every_y_run_drives_one_port_and_probes_the_others():
    eng = NEC5Engine(_ThreePorts(), ground="pec", require_exe=False)
    assert eng._use_reducer and eng._real_port_names == ["a", "b", "c"]
    decks = nec5_fake_y_runs(eng, _Y)
    Y = eng._compute_y_matrix(nec5.C_LIGHT / 14e6)
    assert len(decks) == 3
    for j, deck in enumerate(decks):
        cards = _ex_cards(deck)
        # One card per real port, in port order, at the port's own site —
        # the same address whether the port is driven or probed.
        assert [" ".join(f[2:5]) for f in cards] == list(_ADDRESS.values())
        volts = [float(f[5]) for f in cards]
        assert volts[j] == 1.0
        assert [v for k, v in enumerate(volts) if k != j] == [nec5._PROBE_VOLTS] * 2
    # Every entry is a printed current: five figures, nothing interpolated.
    assert Y == pytest.approx(_Y, rel=1e-4)
    assert eng._y_reciprocity_rel < 1e-4


def test_rows_that_do_not_match_the_cards_refuse():
    """The rows are matched to the ports by position, so the tag/segment check
    is what stands between a reordered printout and a transposed Y."""
    eng = NEC5Engine(_ThreePorts(), ground="pec", require_exe=False)
    nec5_fake_y_runs(eng, _Y, reverse=True)
    with pytest.raises(NEC5Error, match="source rows"):
        eng._compute_y_matrix(nec5.C_LIGHT / 14e6)


def test_the_probe_cannot_be_zero():
    """NEC-5 reads a zero-amplitude EX as 1 V (measured on the licensed
    binary), which would drive the port it was meant to short."""
    assert 0.0 < nec5._PROBE_VOLTS <= 1e-15


# ---------------------------------------------------------------------------
# the reciprocity gate
# ---------------------------------------------------------------------------


def _gate(Y):
    probe = SimpleNamespace()
    NEC5Engine._check_reciprocity(probe, np.asarray(Y), ["p", "q"])
    return probe._y_reciprocity_rel


def test_the_gate_measures_against_the_ports_own_scale():
    """0028's shape: a port coupled at roundoff. Against the coupling itself
    its two entries disagree by 67 %; against the ports they are 3e-11."""
    assert _gate([[1e-3, 1e-14], [3e-14, 4e-4]]) < 1e-10


def test_the_gate_still_refuses_a_row_read_into_the_wrong_port():
    """One port's reading scaled by 10 % on a coupled pair (|Y01| /
    sqrt(|Y00 Y11|) = 0.51 here; hb9cv's is 0.72) is 4.9e-2 of the ports'
    scale, five times the tolerance."""
    Y = np.array(
        [[2.2e-3 - 8.2e-3j, 5.0e-3 - 2.0e-3j], [5.0e-3 - 2.0e-3j, 8.7e-3 - 9.5e-3j]]
    )
    Y[0, :] *= 1.1
    with pytest.raises(NEC5Error, match="not reciprocal"):
        _gate(Y)


# ---------------------------------------------------------------------------
# the licensed engine, on EZNEC's own deck
# ---------------------------------------------------------------------------

# The external reference NEC5Engine never had: the licensed binary run on
# EZNEC's OWN deck text. It is the same binary, so a difference is antennaknobs'
# translation. A deck with no network prints the same impedance both ways. A
# networked one goes through the reducer, whose five-figure Y and speed of light
# put it 1e-5 to 2.6e-4 from NEC-5's own TL/NT solution: re-reducing 0001's Y
# with c = 299.8e6 m/s instead of 299792458 takes it from 2.5e-4 to 7.8e-5.
#
#   deck       EZNEC's deck                    NEC5Engine before AK#1629
#   0001       13.949 + 5.6027j                14.362 + 4.1699j
#   0011       24.442 - 11.533j                refused (reciprocity)
#   0028       129.50 - 73.453j                refused (reciprocity)
#   0019       35.571 - 1.4223j                36.430 - 0.7748j
#   Cardioid   32.092 - 25.434j / 63.354 + 10.308j
#                                  35.908 - 26.657j / 67.379 + 13.518j
#
# Live, not replayed: the repo keeps as few NEC-5 printouts as it can. The CI
# half of this module is the fake binary above.
_NETWORKED = 5e-4
LICENSED = [
    pytest.param(
        CORPUS / "0001_4-square-array-w-feed-system.nec",
        [13.949 + 5.6027j],
        _NETWORKED,
        id="0001-four-ports-at-p0",
    ),
    pytest.param(
        CORPUS / "0011_dipole-with-coax-feedline.nec",
        [24.442 - 11.533j],
        _NETWORKED,
        id="0011-junction-ports",
    ),
    pytest.param(
        CORPUS / "0028_17-10m-log-per-arrl-ant-book.nec",
        [129.5 - 73.453j],
        _NETWORKED,
        id="0028-roundoff-coupling",
    ),
    pytest.param(
        CORPUS / "0019_vertical-over-real-ground.nec",
        [35.571 - 1.4223j],
        0.0,
        id="0019-base-feed",
    ),
    pytest.param(
        CARDIOID, [32.092 - 25.434j, 63.354 + 10.308j], 0.0, id="dan-cardioid"
    ),
]


def _eznecs_own_deck(path):
    """The licensed engine's driving-point impedances on the deck as EZNEC
    wrote it. NEC-5 reads the cards and stops with no results unless the deck
    asks for execution, so an `XQ` goes in ahead of `EN` when it has none."""
    lines = [ln for ln in path.read_text(errors="replace").splitlines() if ln.strip()]
    if not any(ln[:2] == "XQ" for ln in lines):
        end = next(k for k, ln in enumerate(lines) if ln[:2] == "EN")
        lines.insert(end, "XQ")
    text = nec5.run_deck(nec5.find_nec5(), "\n".join(lines) + "\n", timeout=120)
    return np.asarray([z for _t, _s, z in NEC5Engine._parse_input_parameters(text)[0]])


@needs_nec5
@pytest.mark.parametrize(("path", "want", "bar"), LICENSED)
def test_nec5_engine_reproduces_the_licensed_engine_on_eznecs_own_deck(path, want, bar):
    ref = _eznecs_own_deck(path)
    # The control: if the reference moved, the binary did, and every bar
    # below is measured against something else.
    assert ref == pytest.approx(want, rel=1e-4)
    cls = builder_from_file(str(path))
    z = np.asarray(NEC5Engine(cls(), ground=cls.file_ground).impedance())
    assert z.shape == ref.shape
    assert np.max(np.abs(z - ref) / np.abs(ref)) <= bar, z


@needs_nec5
def test_a_real_printout_is_not_symmetric_to_the_bit(monkeypatch):
    """The gate's other arm, on a real printout: 0011's junction ports carry
    NEC-5's own asymmetry at 1.2e-3 of the ports' scale. So the comparison
    runs on real data, and a zero tolerance fires on it."""
    cls = builder_from_file(str(CORPUS / "0011_dipole-with-coax-feedline.nec"))
    eng = NEC5Engine(cls(), ground=cls.file_ground)
    eng.impedance()
    assert 1e-4 < eng._y_reciprocity_rel < nec5._Y_RECIPROCITY_RTOL
    monkeypatch.setattr(nec5, "_Y_RECIPROCITY_RTOL", 0.0)
    with pytest.raises(NEC5Error, match="not reciprocal"):
        eng.impedance()
