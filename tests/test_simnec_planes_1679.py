"""SimNEC's blocks as measurement planes (AK#1679 item 5, AK#1681 item 4).

Decided 2026-09-23: ``rig`` is the generator side (SimNEC's GENERATOR),
``feed`` is the antenna's own terminals, and every chain block gets a node of
its own named after its label, joined to its neighbours by ideal
pass-throughs. AC6LA's ``snBydipole1-C1-L1.ssn`` (post #140, in
``fixtures/ac6la_1678``) is the case that showed the defect: generator → L1 (series) → C1 (shunt) →
antenna. Before, L1 landed on the feed port and C1 hung on it, so ``feed``
read the antenna in parallel with C1 — the value SimNEC shows under block C1,
not under the antenna.

A block's node is its GENERATOR side, the point SimNEC reports under that
block: the impedance looking into the block and everything antenna-ward
(Dan's screenshot of post #140: under A the antenna, under C1 the antenna
across C1, under L1 the generator's reading).

The circuit gates drive the imported network with a fixed antenna one-port,
so they pin the topology with no solver; the end-to-end gates run the
licensed NEC-5 binary.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from momwire.networks import NetworkReducer
from momwire.networks._reduce import C_LIGHT

from antennaknobs.engines import NEC5Engine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.network import PortVirtual, Shunt, Transformer, TwoPort
from antennaknobs.plane import driven_at, planes_of
from antennaknobs.simnec_import import parse_ssn

from conftest import needs_nec5

C1L1 = Path(__file__).parent / "fixtures" / "ac6la_1678" / "snBydipole1-C1-L1.ssn"

# The issue's oracle: NEC-5's reading of Dan's antenna alone at 14.175 MHz
# (the app's multiport-Y route, the file's own ground and JamSegments(12)
# mesh), and the same antenna across C1, which is what `feed` read before.
F_ISSUE = 14.175
Z_ANTENNA = complex(73.23, -38.61)
Z_ANTENNA_PARALLEL_C1 = complex(54.87, -46.08)

# SimNEC's own readings at the file's Generator frequency, 14 MHz, as Dan's
# post #140 screenshot prints them under each block (5.1a1, NEC-5, the same
# 12-segment mesh).
F_FILE = 14.0
SIMNEC = {
    "feed": complex(71.49, -55.57),  # block A, the antenna
    "C1": complex(49.1, -56.74),
    "L1": complex(49.42, 7.645),
}

# The issue and SimNEC print two decimals, so a reading agrees when it is
# within half a unit in that last place: 0.005 ohm (0.05 for SimNEC's
# one-decimal R under C1). The 25 ppm between the deck's c and the reducer's
# SI c (AK#1685) moves these readings by well under that.
TOL = 5e-3


def _net():
    c = parse_ssn(C1L1.read_text(), name=C1L1.name, network=True)
    return c.network()


def _driven_z(net, z_antenna, f_mhz):
    """The driven-port impedance of `net`, its one real port carrying
    `z_antenna` in place of the MoM."""
    real = [n for n, p in net.ports.items() if not isinstance(p, PortVirtual)]
    assert real == ["feed"], real
    idx = {n: i for i, n in enumerate(real)}
    for n in net.ports:
        idx.setdefault(n, len(idx))
    z = NetworkReducer(net, idx, len(idx)).driven_impedance(
        np.array([[1.0 / z_antenna]], dtype=complex), C_LIGHT / (f_mhz * 1e6)
    )
    return complex(np.atleast_1d(z)[0])


# --- the topology --------------------------------------------------------------


def test_every_block_is_a_plane_named_after_its_label():
    """rig (the generator), then each block in generator→antenna order, then
    feed (the antenna). The source is at the rig."""
    net = _net()
    assert planes_of(net) == ["rig", "L1", "C1", "feed"]
    assert [s.port for s in net.sources] == ["rig"]
    for name in ("rig", "L1", "C1"):
        assert isinstance(net.ports[name], PortVirtual)


def test_the_blocks_are_wired_generator_to_antenna():
    """L1 runs from its node to C1's; C1 hangs on its own node; ideal 1:1
    pass-throughs join rig to L1 and C1 to feed, so C1 is NOT across the
    antenna terminals."""
    net = _net()
    (coil,) = [b for b in net.branches if isinstance(b, TwoPort)]
    assert (coil.a, coil.b) == ("L1", "C1")
    assert coil.l == pytest.approx(731.9e-9)
    (cap,) = [b for b in net.branches if isinstance(b, Shunt)]
    assert cap.port == "C1" and cap.c == pytest.approx(37.52e-12)
    thru = [(b.a, b.b, b.n, b.r) for b in net.branches if isinstance(b, Transformer)]
    assert thru == [("rig", "L1", 1.0, None), ("C1", "feed", 1.0, None)]


# --- the planes' readings, circuit only -----------------------------------------


def test_feed_reads_the_antenna_alone():
    """The issue's oracle: `feed` reads the antenna's own 73.23 - j38.61, not
    the antenna across C1 (54.87 - j46.08, what it read before). Exact here:
    nothing but an ideal pass-through is left between the plane and the
    antenna."""
    net = _net()
    z_feed = _driven_z(driven_at(net, "feed"), Z_ANTENNA, F_ISSUE)
    assert abs(z_feed - Z_ANTENNA) < 1e-9
    z_c1 = _driven_z(driven_at(net, "C1"), Z_ANTENNA, F_ISSUE)
    assert abs(z_c1 - Z_ANTENNA_PARALLEL_C1) < TOL


def test_each_plane_reads_its_block_and_everything_antenna_ward():
    """C1's plane is the antenna across C1 (Q 2000 at 14.175 MHz); L1's adds
    L1 in series (Q 200), and the rig reads what L1's plane reads, through
    the ideal pass-through."""
    w = 2 * math.pi * F_ISSUE * 1e6
    z_cap = 1 / (w * 37.52e-12 * 2000) - 1j / (w * 37.52e-12)
    z_c1 = Z_ANTENNA * z_cap / (Z_ANTENNA + z_cap)
    z_l1 = z_c1 + w * 731.9e-9 / 200 + 1j * w * 731.9e-9
    net = _net()
    for plane, want in (("C1", z_c1), ("L1", z_l1), ("rig", z_l1)):
        z = _driven_z(driven_at(net, plane), Z_ANTENNA, F_ISSUE)
        assert z == pytest.approx(want, rel=1e-9), plane


# --- end to end on the licensed binary ----------------------------------------


def _nec5_at(plane: str, f_mhz: float) -> complex:
    cls = builder_from_file(str(C1L1))
    pruned = driven_at(cls().build_network(), plane)
    b = cls({"freq": f_mhz, "design_freq": f_mhz})
    object.__setattr__(b, "build_network", lambda: pruned)
    (z,) = NEC5Engine(b, ground=cls.file_ground).impedance()
    return complex(z)


@needs_nec5
def test_nec5_feed_is_the_antenna_the_issue_quotes():
    """NEC-5 at 14.175 MHz: feed is the antenna's own 73.23 - j38.61, and
    C1's plane is the reading feed used to give."""
    assert abs(_nec5_at("feed", F_ISSUE) - Z_ANTENNA) < TOL
    assert abs(_nec5_at("C1", F_ISSUE) - Z_ANTENNA_PARALLEL_C1) < TOL


@needs_nec5
@pytest.mark.parametrize("plane", ["feed", "C1", "L1", "rig"])
def test_nec5_reads_what_simnec_shows_under_each_block(plane):
    """At the file's own 14 MHz, each plane agrees with the value SimNEC 5.1a1
    prints under that block (Dan's post #140 screenshot), to its printed
    digits; the rig is the generator, which SimNEC shows under L1."""
    want = SIMNEC["L1" if plane == "rig" else plane]
    z = _nec5_at(plane, F_FILE)
    assert abs(z.real - want.real) < (0.05 if plane == "C1" else TOL), z
    assert abs(z.imag - want.imag) < TOL, z
