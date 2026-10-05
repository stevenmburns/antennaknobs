"""EZNEC's "parallel connected loads" import and solve (AK#1880).

Dan AC6LA, QRZ 1003328 #190: EZNEC's sample "Network connection test.EZ",
saved in NEC-5 format, failed in the workbench with ``SingularNetworkError``
on every engine. EZNEC writes each of its "parallel connected loads" as a
ONE-port ``NT``: Y11 only, port 2 on its far-away virtual wire 4 with
Y12 = Y22 = 0. Here the two cards address the two sides of one two-wire node
(``2,3`` and ``3,-1``).

The cause was not the junction. The two ends at the node already take AK#1617's
spelling, two ports at one junction, which is the series circuit NEC-5 solves.
What failed was port 2: the card's all-zero half emits no branch, so each
virtual node had an identically zero KCL row. momwire's corpus deck 0017 is
the same antenna with the two loads on swapped sides, and it always solved,
because EZNEC also wrote ``LD 4 ... 1.E+10`` pins there, each a 1e-10 S branch
holding its node. Dan's saved file carries no pins.

momwire 0.70.0's ``eznec.serve`` raises the same ``SingularNetworkError`` on
the unpinned file, so the seam's reference numbers here are for the PINNED
variant, which is the same circuit (the pin holds a node that Y12 = 0 keeps
the antenna from reading; the AK route gives the two decks the same Z).

Licensed NEC-5 (black box, ``nec5cl``, numbers only), 2026-10-03:

=====================  =====================
deck                   NEC-5 Z (printed)
=====================  =====================
Dan's, as saved        195.34 - 57.458j
loads swapped (mirror) 195.34 - 57.458j
both on ``3,-1``       114.47 + 21.096j
the TL variant below   62.826 - 75.677j
a stub at the joint    187.13 + 23.127j
=====================  =====================
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from antennaknobs.cli import deck_extended_kernel_flag, make_engine_factory
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Shunt

FIXTURES = Path(__file__).parent / "fixtures" / "eznec_parallel_loads_1880"
DECK = FIXTURES / "ezLoadPositionsB.nec"

# EZNEC's open-circuit pins on the two virtual segments the NT cards use.
PINNED = (
    "GE 0\r\n",
    "GE 0\r\nLD 4,4,1,0,1.E+10,0.\r\nLD 4,4,2,0,1.E+10,0.\r\n",
)
# The two loads on swapped sides of the node (0017's placement, unpinned).
MIRROR = (
    ("NT 2,3,4,1,.01", "NT 3,-1,4,1,.01"),
    ("NT 3,-1,4,2,.005", "NT 2,3,4,2,.005"),
)
# Open stubs from the two sides of the node to the virtual wire.
LINES = (
    ("NT 2,3,4,1,.01,0.,0.,0.,0.,0.", "TL 2,3,4,1,50.,.1,0.,0.,0.,0."),
    ("NT 3,-1,4,2,.005,0.,0.,0.,0.,0.", "TL 3,-1,4,2,75.,.05,0.,0.,0.,0."),
)
# A third wire's end at the joint: the node becomes K = 3.
STUB = (("GW 4,3,", "GW 5,3,0.,.125,0.,.1,.125,0.,.0005\r\nGW 4,3,"),)

NEC5 = 195.34 - 57.458j
NEC5_LINES = 62.826 - 75.677j

# razor-2p is one computation on both routes: float noise (2.7e-15 measured).
# bspline is AK's default `BSplineSolver` against serve's `basis="bspline"`,
# two differently configured lanes; 0017's row in
# `test_two_routes_agree_corpus_1584.py` carries the same 2.2e-04 at 5e-4.
BAR = {"razor-2p": 1e-12, "bspline": 5e-4}


def _variant(tmp_path, swaps, name) -> Path:
    text = DECK.read_bytes().decode()
    for a, b in swaps:
        assert a in text, a
        text = text.replace(a, b)
    path = tmp_path / name
    path.write_bytes(text.encode())
    return path


def _deck(path: Path):
    return parse_nec(path.read_bytes().decode(), name=path.name, network=True)


def _z(path: Path, basis: str) -> complex:
    """The ``@file.nec`` route: `builder_from_file` plus the CLI's engine
    factory, exactly as ``antennaknobs analyze @deck.nec`` takes it."""
    cls = builder_from_file(str(path))
    factory = make_engine_factory(
        f"momwire:{basis}",
        getattr(cls, "file_ground", None),
        deck_extended_kernel=deck_extended_kernel_flag(cls),
    )
    return complex(np.atleast_1d(np.asarray(factory(cls()).impedance()))[0])


def _seam(path: Path, basis: str) -> complex:
    from momwire.deck._nec5 import parse_nec5
    from momwire.eznec import serve

    run = serve(parse_nec5(path.read_text(errors="replace")), basis=basis)
    return complex(run.sources[0].impedance)


def test_the_unconnected_halves_leave_no_node_behind():
    deck = _deck(DECK)
    net = deck.network()
    # Two loads on two ports at the one junction (AK#1617, not folded: one
    # port would put the shunts in parallel, 114.47 + 21.096j), and no node
    # for the all-zero halves on the virtual wire.
    assert set(net.ports) == {"feed", "nt1a", "nt2a"}
    shunts = {b.port: b.r for b in net.branches if isinstance(b, Shunt)}
    assert shunts == {"nt1a": 100.0, "nt2a": 200.0}
    assert "2 unconnected NT ends" in deck.skipped_note()


def test_a_pinned_node_is_still_kept(tmp_path):
    """The pin is a branch on its node, so the 0017 shape is untouched."""
    net = _deck(_variant(tmp_path, [PINNED], "pinned.nec")).network()
    assert {"nt1b", "nt2b"} <= set(net.ports)


@pytest.mark.parametrize("basis", ["razor-2p", "bspline"])
def test_leaving_the_node_out_is_the_pinned_circuit(tmp_path, basis):
    """Exact up to round-off: Y12 = 0, so nothing reads the node a pin holds."""
    pinned = _variant(tmp_path, [PINNED], "pinned.nec")
    assert _z(DECK, basis) == pytest.approx(_z(pinned, basis), rel=1e-12)


@pytest.mark.parametrize("basis", ["razor-2p", "bspline"])
@pytest.mark.parametrize("variant", ["dan", "mirror"])
def test_the_ak_route_answers_the_seam(tmp_path, basis, variant):
    swaps = [] if variant == "dan" else list(MIRROR)
    path = _variant(tmp_path, swaps, f"{variant}.nec")
    pinned = _variant(tmp_path, [*swaps, PINNED], f"{variant}_pinned.nec")
    z, ref = _z(path, basis), _seam(pinned, basis)
    assert abs(z - ref) / abs(ref) < BAR[basis], (z, ref)
    if basis == "razor-2p":
        # NEC-5's own basis: the licensed engine's printed digits, both
        # orders (two loads in series either way round).
        assert abs(z - NEC5) < 5e-3, z


def test_open_stubs_on_the_two_sides_answer_nec5(tmp_path):
    """The TL variant. It never failed (a line holds its far node), so this
    is a guard on AK#1617's two-port spelling for lines, not a regression
    test: razor-2p lands 5.5e-05 from NEC-5's printout."""
    z = _z(_variant(tmp_path, LINES, "lines.nec"), "razor-2p")
    assert abs(z - NEC5_LINES) / abs(NEC5_LINES) < 1e-4, z


def test_loads_on_two_wires_at_a_three_wire_node_are_refused(tmp_path):
    """NEC-5 puts each end in its own wire's branch there, which needs one
    series gap per wire end. razor-2p refused the positioned gap on its own;
    bspline answered 191.53 + 28.54j where NEC-5 prints 187.13 + 23.127j."""
    deck = _deck(_variant(tmp_path, STUB, "k3.nec"))
    with pytest.raises(ValueError, match="momwire#1300") as e:
        deck.network()
    assert "2,3 and 3,-1" in str(e.value)
    assert "3 wire ends meet" in str(e.value)
    assert "AK#1886" in str(e.value)
