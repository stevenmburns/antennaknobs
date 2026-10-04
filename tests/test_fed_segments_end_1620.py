"""AK#1620: a gap port AT its wire's end is an ``"end"`` site.

`fed_segments()` used to hard-code the family's site, ``"centre"`` or
``"knot"``, for every `PortOnWire`, so a port at 0.0 or 1.0 (a base feed at a
ground contact, AK#1598/#1605) read as the middle of a segment it is at the
edge of. The site vocabulary already had the word: ``"end"``, a port at the
wire's end. Nothing here solves.

The deck is momwire's corpus 0019 in shape: one wire of ten segments standing
on a perfect ground, fed at the contact (``EX 4,1,-1``, NEC-5's end 1 of
segment 1). Nothing splits, so this is the plain path the issue measured.
"""

import pytest

from antennaknobs.engine import fed_records, gap_site
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.file_designs import builder_from_text
from antennaknobs.network import Driven, Network, PortOnWire

DECK = """\
CM NEC-5
CE
GW 1 10 0 0 0 0 0 10.7 0.01
GE 1
GN 1
EX 4 1 -1 0 1 0
FR 0 1 0 0 7 0
EN
"""
HEIGHT = 10.7


def _builder():
    return builder_from_text("vertical.nec", DECK)()


def _check(records):
    (rec,) = records
    assert rec["port"] == "feed"
    assert rec["site"] == "end"
    assert "length_after_m" not in rec
    # The segment the port stands at the edge of, at this engine's count.
    assert rec["length_m"] * rec["segments"] == pytest.approx(HEIGHT)
    return rec


def test_the_deck_feeds_at_the_contact():
    port = _builder().build_network().ports["feed"]
    assert isinstance(port, PortOnWire) and port.at == 0.0


def test_momwire_reports_the_contact_as_an_end():
    _check(MomwireEngine(_builder(), ground="pec").fed_segments())


def test_nec5_reports_the_contact_as_an_end():
    _check(NEC5Engine(_builder(), ground="pec", require_exe=False).fed_segments())


def test_pynec_reports_the_contact_as_an_end():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    _check(PyNECEngine(_builder(), ground="pec").fed_segments())


@pytest.mark.parametrize(
    ("at", "site"),
    [(0.0, "end"), (1.0, "end"), (None, "centre"), (0.31, "centre")],
)
def test_only_the_two_ends_change_the_site(at, site):
    port = PortOnWire("p", wire="w", at=at) if at is not None else PortOnWire("p")
    assert gap_site(port, "centre") == site
    assert gap_site(port, "knot") == ("end" if site == "end" else "knot")


def test_fed_records_reads_the_position():
    wires = [((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 5, None, "w")]
    for at, site in ((1.0, "end"), (0.5, "centre")):
        net = Network(
            ports={"p": PortOnWire("p", wire="w", at=at)},
            branches=[],
            sources=[Driven(port="p")],
        )
        (rec,) = fed_records(wires, net, "odd")
        assert rec["site"] == site and rec["length_m"] == pytest.approx(0.2)
