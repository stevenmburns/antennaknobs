"""EZNEC's NT cards, read for what they are (AK#1681).

Dan AC6LA's feed-system deck (`tests/fixtures/eznec_ac6la_1681/`, README there)
drives a dipole through two L networks, an EZNEC transformer and 100 ft of lossy
line, every one of them an ``NT`` card on EZNEC's virtual wire. The
transformer card ``NT 2,2,2,3,20.,0.,-10.,0.,5.,0.`` is rank 1 — an ideal
1:2 with 0.2 Ω — but imported as its resistive pi, whose −0.2 Ω shunt leg
made the plane at the line's input read −0.201 Ω.

The circuit gates drive the imported network with NEC-5's own reading of the
antenna one-port (plane ``nt1b``), so they pin the translation with no solver
involved; the end-to-end gate runs the licensed binary.
"""

from pathlib import Path

import numpy as np
import pytest

from antennaknobs.engines import NEC5Engine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import (
    _rank_one_transformer,
    parse_nec,
)
from antennaknobs.network import PortVirtual, Shunt, Transformer, TwoPort
from antennaknobs.plane import driven_at, planes_of
from momwire.networks import NetworkReducer

from conftest import needs_nec5

FIXTURES = Path(__file__).parent / "fixtures"
DECK = FIXTURES / "eznec_ac6la_1681" / "Bydpole-TL-Xfmr-CLC.nec"
WA7ARK = FIXTURES / "eznec_virtual_wire_1577" / "WA7ARK-OCF-Load-Xfmr-TL.nec"

FREQ = 14.175
LAMBDA = 299792458.0 / (FREQ * 1e6)

# NEC-5 through the app's multiport-Y route at 14.175 MHz, the deck's own mesh
# and ground (README.md). `nt1b` is the dipole's feedpoint; the others are the
# nodes of the feed system, source first.
NEC5 = {
    "feed": complex(50.010, 0.003),
    "nt3b": complex(46.930, -71.246),
    "nt2a": complex(7.209, -0.861),
    "nt1a": complex(28.635, -3.442),
    "nt1b": complex(75.315, -30.879),
}


def _deck(path=DECK):
    return parse_nec(
        path.read_text(encoding="utf-8", errors="replace"),
        name=path.name,
        network=True,
    )


def _driven_z(net, z_antenna):
    """The driven-port impedance of `net`, its one real port carrying
    `z_antenna` in place of the MoM."""
    real = [n for n, p in net.ports.items() if not isinstance(p, PortVirtual)]
    assert len(real) == 1, real
    idx = {n: i for i, n in enumerate(real)}
    for n in net.ports:
        idx.setdefault(n, len(idx))
    z = NetworkReducer(net, idx, len(idx)).driven_impedance(
        np.array([[1.0 / z_antenna]], dtype=complex), LAMBDA
    )
    return complex(np.atleast_1d(z)[0])


def _y_of(n, r, g_b):
    """The 2×2 short-circuit Y of `Transformer(n, r)` plus a shunt g_b at b."""
    return np.array([[1.0, -n], [-n, n * n]]) / r + np.diag([0.0, g_b])


# --------------------------------------------------------------------------
# the transformer
# --------------------------------------------------------------------------
def test_the_transformer_card_imports_as_a_transformer():
    net = _deck().network()
    xfmrs = [b for b in net.branches if isinstance(b, Transformer)]
    assert xfmrs == [Transformer(a="nt2a", b="nt1a", n=0.5, r=0.05)]
    # Printed exactly, so nothing is left over: no shunt, and no pi.
    assert not [b for b in net.branches if isinstance(b, (Shunt, TwoPort))]


@pytest.mark.parametrize(
    ("y", "expect"),
    [
        # Dan's: 1:2 turns with 0.05 Ω on side a, printed exactly.
        ((20.0, -10.0, 5.0), (0.5, 0.05, 0.0)),
        # The phase-inverting winding.
        ((20.0, 10.0, 5.0), (-0.5, 0.05, 0.0)),
        # Mike WA7ARK's 7:1, printed to seven figures: the digits leave
        # 4.4e-6 S over, which is kept (see the exactness test).
        ((0.2040816, -1.428571, 10.0), (6.99999902, 4.90000078, 4.4e-6)),
    ],
)
def test_a_rank_one_y_is_a_transformer(y, expect):
    n, r, g_b = _rank_one_transformer(*y)
    assert (n, r) == pytest.approx(expect[:2], rel=1e-8)
    assert g_b == pytest.approx(expect[2], rel=1e-6, abs=1e-15)


@pytest.mark.parametrize(
    "y",
    [
        (1.0, -0.5, 1.0),  # a real pi with two positive shunt legs
        (20.0, -10.0, 5.1),  # 2 % off rank 1: a transformer AND a shunt
        (20.0, 0.0, 5.0),  # two unconnected shunts
        (-20.0, -10.0, -5.0),  # negative diagonal: no winding resistance
        (0.0, 0.0, 0.0),  # the all-zero card, which is an open (issue #961)
    ],
)
def test_anything_else_keeps_the_resistive_pi(y):
    assert _rank_one_transformer(*y) is None


@pytest.mark.parametrize("path", [DECK, WA7ARK])
def test_the_branches_are_the_card_exactly(path):
    """The pair reproduces the card's Y to rounding: the transformer is not an
    approximation of the card, and neither is the shunt that carries what its
    digits leave over."""
    deck = _deck(path)
    raw = [
        line.replace(",", " ").split()
        for line in path.read_text(errors="replace").splitlines()
        if line.startswith("NT")
    ]
    checked = 0
    for card, nt in zip(raw, deck.nts, strict=True):
        if nt.xfmr_n is None:
            continue
        y11, y12, y22 = (float(card[k]) for k in (5, 7, 9))
        g_b = 0.0 if nt.shunt_r_b is None else 1.0 / nt.shunt_r_b
        np.testing.assert_allclose(
            _y_of(nt.xfmr_n, nt.xfmr_r, g_b),
            [[y11, y12], [y12, y22]],
            rtol=1e-12,
        )
        checked += 1
    assert checked == 1


# --------------------------------------------------------------------------
# the planes, as a circuit
# --------------------------------------------------------------------------
def test_the_line_input_plane_reads_the_line():
    """Drive the imported network at each plane with NEC-5's antenna one-port:
    every plane lands on NEC-5's own reading there. The line's input was
    −0.201 Ω while the pi's −0.2 Ω leg hung on it."""
    net = _deck().network()
    assert planes_of(net) == ["feed", "nt3b", "nt2a", "nt1a", "nt1b"]
    z_ant = NEC5["nt1b"]
    for plane in ("nt1a", "nt2a", "nt3b", "feed"):
        z = _driven_z(driven_at(net, plane), z_ant)
        # NEC-5's readings carry three decimals; so does its antenna.
        assert abs(z - NEC5[plane]) < 2e-3, (plane, z)
    # The transformer, read off two planes: a quarter of the line, plus r.
    z1 = _driven_z(driven_at(net, "nt1a"), z_ant)
    z2 = _driven_z(driven_at(net, "nt2a"), z_ant)
    assert z2 == pytest.approx(z1 / 4 + 0.05, rel=1e-12)


@needs_nec5
def test_nec5_reads_the_line_input_and_the_rig_unchanged():
    """End to end on the licensed binary: the line's input where it read
    −0.201 Ω, and the source's impedance, which the pi had right all along."""
    cls = builder_from_file(str(DECK))
    b = cls()
    (z_rig,) = (complex(x) for x in NEC5Engine(b, ground=cls.file_ground).impedance())
    assert abs(z_rig - NEC5["feed"]) < 1e-3
    pruned = driven_at(b.build_network(), "nt1a")
    b = cls()
    object.__setattr__(b, "build_network", lambda: pruned)
    (z_line,) = (complex(x) for x in NEC5Engine(b, ground=cls.file_ground).impedance())
    assert abs(z_line - NEC5["nt1a"]) < 1e-3
