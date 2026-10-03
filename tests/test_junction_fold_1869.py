"""Two objects named through the two wires of one TWO-wire node share one
series port (AK#1869, the AK side of momwire#1300).

NEC-5 puts an object on the wire its card names. Where exactly two wire ends
meet, the two ends carry one through-current, so ``LD 4,1,10`` (end 2 of wire
1) and ``LD 4,2,-1`` (end 1 of wire 2) are one series gap and their loads add.
Measured on the licensed NEC-5 (numbers only, `fixtures/junction_fold_1869/
README.md`): 50 ohms on wire 1 plus j100 on wire 2 answers a single 50+j100
load to the printed digit, 508.53+183.66j. ``momwire.eznec.serve`` agrees:
its ``_assign_columns`` gives the second address the first's column.

The importer used to give each address its own `PortAtVertex` -- its own node
gap -- and momwire refuses a second gap at one junction, so every such deck
errored, K=2 included. Now the addresses fold onto one key and land on one
port, where the `Load`s sum in series and a `Driven` sees the sum.

At a node of THREE or more wire ends NEC-5 puts each object in its own wire's
branch, which is one node gap per wire end. momwire serves one per junction
until momwire#1300's core change ships, so that stays refused, by name.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from antennaknobs.cli import make_engine_factory
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Driven, Load, PortAtVertex

FIXTURES = Path(__file__).parent / "fixtures" / "junction_fold_1869"
TWO_LOADS = FIXTURES / "k2_fs_2ld.nec"  # EX 1,5; LD 50 at 1,10; LD j100 at 2,-1
MIRROR = FIXTURES / "k2_fs_ex2_ld50w1.nec"  # EX at 2,-1; LD 50 at 1,10
BURIED = FIXTURES / "bur_2ld.nec"  # Dan's #182 radials, both loads at z = 0

# The two loads of TWO_LOADS as the one load they are in series.
SERIES = ("LD 4,1,10,0,50.,0.\nLD 4,2,-1,0,0.,100.\n", "LD 4,1,10,0,50.,100.\n")
# The same for BURIED: wire 1 end 1 and wire 6 end 1 are the z = 0 node.
BURIED_SERIES = ("LD 4,1,-1,0,50.,0.\nLD 4,6,-1,0,0.,100.\n", "LD 4,1,-1,0,50.,100.\n")
# A 0.15 m stub from the dipole's centre makes the node K = 3.
STUB = ("GE 0,-1", "GW 3,6,0.,0.,0.0,.15,0.,0.0,.0005\nGE 0,-1")


def _variant(tmp_path, src: Path, swap: tuple[str, str], name: str) -> Path:
    text = src.read_text()
    assert swap[0] in text
    path = tmp_path / name
    path.write_text(text.replace(*swap))
    return path


def _deck(path: Path):
    return parse_nec(path.read_text(), name=path.name, network=True)


def _z(path: Path, basis: str) -> complex:
    """The ``@file.nec`` route: `builder_from_file` plus the CLI's engine
    factory, exactly as ``antennaknobs analyze @deck.nec`` takes it."""
    cls = builder_from_file(str(path))
    factory = make_engine_factory(
        f"momwire:{basis}",
        getattr(cls, "file_ground", None),
        deck_extended_kernel=bool(getattr(cls, "file_extended_kernel", False)),
    )
    return complex(np.atleast_1d(np.asarray(factory(cls()).impedance()))[0])


def test_two_loads_on_the_two_wires_of_a_node_are_one_series_port():
    net = _deck(TWO_LOADS).network()
    assert set(net.ports) == {"feed", "load1"}
    assert net.ports["load1"] == PortAtVertex("load1", end="p1")
    loads = [b for b in net.branches if isinstance(b, Load)]
    assert [ld.port for ld in loads] == ["load1", "load1"]
    assert [(ld.r, ld.z) for ld in loads] == [(50.0, None), (None, 100j)]


@pytest.mark.parametrize("basis", ["razor-nec5", "bspline"])
def test_the_folded_pair_answers_the_single_series_load_bit_for_bit(tmp_path, basis):
    """The same port, the same mesh: the only difference left is that the
    reducer sums 50 and j100 instead of being handed 50+j100, which is exact.
    razor-nec5 also lands on the licensed NEC-5's 508.53+183.66j."""
    series = _variant(tmp_path, TWO_LOADS, SERIES, "series.nec")
    assert _deck(TWO_LOADS).wire_tuples(specs=True) == _deck(series).wire_tuples(
        specs=True
    )
    z = _z(TWO_LOADS, basis)
    assert z == _z(series, basis)
    if basis == "razor-nec5":
        assert abs(z - (508.53 + 183.66j)) < 0.05


def test_a_source_on_the_other_wire_carries_the_load_in_series(tmp_path):
    """The mirror: the source names wire 2's end 1 and the load wire 1's end
    2. One port, keyed on the source so its drive keeps its own direction, and
    the load shifts Z by exactly its own 50 ohms, as NEC-5 prints (130.87 +
    37.992j against 80.865 + 37.992j)."""
    net = _deck(MIRROR).network()
    assert set(net.ports) == {"feed"}
    assert net.ports["feed"] == PortAtVertex("feed", end="p0")
    assert [b.port for b in net.branches if isinstance(b, Load)] == ["feed"]
    assert net.sources == [Driven(port="feed", voltage=1.0)]
    bare = _variant(tmp_path, MIRROR, ("LD 4,1,10,0,50.,0.\n", ""), "bare.nec")
    z, z0 = _z(MIRROR, "razor-nec5"), _z(bare, "razor-nec5")
    assert abs((z - z0) - 50) < 1e-9
    assert abs(z - (130.87 + 37.992j)) < 0.05


def test_the_buried_crossing_node_folds_too(tmp_path):
    """Dan's #182 radial screen with both loads on the z = 0 node (wire 1 end
    1, wire 6 end 1) and the source one segment up wire 1. Besides the second
    gap, the old spelling put the knot-0 load and the knot-1 source on wire
    1's one-segment first piece ("claimed by more than one attachment"); the
    folded, loads-only claim rides wire 6's end instead (AK#1583), exactly as
    the single series load does.

    Structural only: a Sommerfeld solve of this screen costs ~3 s a basis, and
    the bit-for-bit claim for the same port is the dipole test's."""
    series = _variant(tmp_path, BURIED, BURIED_SERIES, "bur_series.nec")
    assert _deck(BURIED).wire_tuples(specs=True) == _deck(series).wire_tuples(
        specs=True
    )
    net, ref = _deck(BURIED).network(), _deck(series).network()
    assert net.ports == ref.ports
    assert net.ports["load1"] == PortAtVertex("load1", end="p0")
    assert net.sources == ref.sources
    assert [b.port for b in net.branches] == ["load1", "load1"]


def test_two_objects_at_a_three_wire_node_are_refused_naming_momwire_1300(
    tmp_path,
):
    deck = _deck(_variant(tmp_path, MIRROR, STUB, "k3.nec"))
    with pytest.raises(ValueError, match="momwire#1300") as e:
        deck.network()
    assert "2,-1 and 1,10" in str(e.value)
    assert "3 wire ends meet" in str(e.value)


def test_two_sources_on_the_two_sides_of_one_node_are_refused(tmp_path):
    text = MIRROR.read_text().replace(
        "EX 0,2,-1,0,1.,0.\n", "EX 0,2,-1,0,1.,0.\nEX 0,1,10,0,1.,0.\n"
    )
    deck = parse_nec(text, name="two_ex.nec", network=True)
    with pytest.raises(ValueError, match="one port carries one drive"):
        deck.network()
