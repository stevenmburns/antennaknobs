"""The SimNEC importer's ideal pass-throughs (AK#1679) draw as bare wire on
the schematic, with no "through<k>" caption or enclosure (AK#2270). They are
plumbing the importer adds so each block keeps a node of its own, not
components the .ssn names; the network still carries them."""

from __future__ import annotations

import re
from pathlib import Path

from antennaknobs.file_designs import builder_from_file
from antennaknobs.network import Transformer
from antennaknobs.schematic import lower, render_svg

C1L1 = Path(__file__).parent / "fixtures" / "ac6la_1678" / "snBydipole1-C1-L1.ssn"


def _svg_text():
    b = builder_from_file(C1L1)()
    net = b.build_network()
    svg = render_svg(lower(net, freq_mhz=float(b.freq)))
    return net, [
        re.sub(r"<[^>]+>", "", t).strip()
        for t in re.findall(r"<text[^>]*>(.*?)</text>", svg, re.S)
    ]


def test_the_pass_throughs_carry_no_caption():
    _net, texts = _svg_text()
    assert not [t for t in texts if t.startswith("through")], texts


def test_the_real_components_keep_their_labels():
    """L1 and C1 still draw with their values, and the chain's ends with
    theirs: only the pass-throughs lose a caption."""
    _net, texts = _svg_text()
    assert "rig" in texts and "antenna" in texts, texts
    assert any(t.endswith("µH") for t in texts), texts
    assert any(t.endswith("pF") for t in texts), texts


def test_the_network_still_holds_them():
    """Only the drawing changes: the ideal 1:1 links are still branches."""
    net, _texts = _svg_text()
    links = [br for br in net.branches if isinstance(br, Transformer) and br.n == 1.0]
    assert links, "the pass-throughs left the network"
