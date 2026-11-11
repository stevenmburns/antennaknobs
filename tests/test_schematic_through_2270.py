"""The SimNEC importer joins a .ssn's blocks with `Through` links (AK#2270):
an ideal zero-impedance branch, so each block keeps a node of its own and a
measurement plane can stand on either side (AK#1679). It replaced an ideal
1:1 `Transformer` inside a `Composite` named "through<k>", which drew as a
captioned dashed box a user asked about, and whose meaning rode on the
balun element's defaults.

The schematic draws a `Through` as bare wire, with no caption; the network
holds `Through` branches and no 1:1 Transformer; and every plane reads what
the Transformer version read, to the bit."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import numpy as np
import pytest

from antennaknobs.file_designs import builder_from_file
from antennaknobs.mw.networks import NetworkReducer
from antennaknobs.mw.networks._reduce import C_LIGHT
from antennaknobs.network import PortVirtual, Through, Transformer
from antennaknobs.plane import driven_at, planes_of
from antennaknobs.schematic import lower, render_svg
from antennaknobs.simnec_import import parse_ssn

C1L1 = Path(__file__).parent / "fixtures" / "ac6la_1678" / "snBydipole1-C1-L1.ssn"

# The antenna one-port the circuit gates drive the network with: NEC-5's
# reading of Dan's antenna alone at 14.175 MHz (test_simnec_planes_1679).
Z_ANTENNA = complex(73.23, -38.61)

# Each plane's impedance as recorded on the branch head BEFORE AK#2270, when
# the pass-throughs were 1:1 Transformers (d792f8dc), as exact float.hex.
RECORDED = {
    (14.0, "rig"): ("0x1.bb34c3de4af3cp+5", "0x1.255fbabe14916p+4"),
    (14.0, "L1"): ("0x1.bb34c3de4af3cp+5", "0x1.255fbabe14916p+4"),
    (14.0, "C1"): ("0x1.b8a180303f7fap+5", "-0x1.705d0299e8338p+5"),
    (14.0, "feed"): ("0x1.24eb851eb8520p+6", "-0x1.34e147ae147aep+5"),
    (14.175, "rig"): ("0x1.b9910c57c18a4p+5", "0x1.31a858e027a55p+4"),
    (14.175, "L1"): ("0x1.b9910c57c18a4p+5", "0x1.31a858e027a54p+4"),
    (14.175, "C1"): ("0x1.b6f58b0455f1ap+5", "-0x1.70a8dcbbfb4b0p+5"),
    (14.175, "feed"): ("0x1.24eb851eb8520p+6", "-0x1.34e147ae147aep+5"),
}


def _net():
    return parse_ssn(C1L1.read_text(), name=C1L1.name, network=True).network()


def _svg_text():
    b = builder_from_file(C1L1)()
    net = b.build_network()
    svg = render_svg(lower(net, freq_mhz=float(b.freq)))
    return net, [
        re.sub(r"<[^>]+>", "", t).strip()
        for t in re.findall(r"<text[^>]*>(.*?)</text>", svg, re.S)
    ]


def _as_transformers(net):
    """``net`` with each Through swapped for the ideal 1:1 Transformer the
    importer used before AK#2270, position for position."""
    out = copy.copy(net)
    out.branches = [
        Transformer(a=br.a, b=br.b, n=1.0) if isinstance(br, Through) else br
        for br in net.branches
    ]
    return out


def _plane_z(net, plane, f_mhz):
    pn = driven_at(net, plane)
    real = [n for n, p in pn.ports.items() if not isinstance(p, PortVirtual)]
    idx = {n: i for i, n in enumerate(real)}
    for n in pn.ports:
        idx.setdefault(n, len(idx))
    z = NetworkReducer(pn, idx, len(idx)).driven_impedance(
        np.array([[1.0 / Z_ANTENNA]], dtype=complex), C_LIGHT / (f_mhz * 1e6)
    )
    return np.atleast_1d(np.asarray(z, dtype=complex))


# --- the drawing -----------------------------------------------------------------


def test_the_pass_throughs_carry_no_caption():
    _net_, texts = _svg_text()
    assert not [t for t in texts if t.lower().startswith("through")], texts


def test_the_real_components_keep_their_labels():
    """L1 and C1 still draw with their values, and the chain's ends with
    theirs: only the pass-throughs have no caption."""
    _net_, texts = _svg_text()
    assert "rig" in texts and "antenna" in texts, texts
    assert any(t.endswith("µH") for t in texts), texts
    assert any(t.endswith("pF") for t in texts), texts


def test_every_plane_still_marks_on_the_drawing():
    """The planes were never keyed on the old "through<k>." composite path:
    each one the picker lists still lands on the drawing."""
    net = _net()
    assert planes_of(net) == ["rig", "L1", "C1", "feed"]
    for plane in planes_of(net):
        assert lower(net, freq_mhz=14.0, plane=plane).plane == plane


# --- the network -----------------------------------------------------------------


def test_the_network_holds_throughs_and_no_1to1_transformer():
    net, _texts = _svg_text()
    links = [(br.a, br.b) for br in net.branches if isinstance(br, Through)]
    assert links == [("rig", "L1"), ("C1", "feed")]
    assert not [br for br in net.branches if isinstance(br, Transformer)]
    assert not net.composites, net.composites
    assert set(net.branch_paths) == {""}


@pytest.mark.parametrize("f_mhz", (14.0, 14.175))
@pytest.mark.parametrize("plane", ("rig", "L1", "C1", "feed"))
def test_every_plane_reads_what_the_transformer_version_read(plane, f_mhz):
    """Bit identity, two ways. Live: the same network with each Through
    swapped back to the 1:1 Transformer gives the same bytes. Recorded: the
    value the branch head gave before the change, exactly."""
    net = _net()
    z = _plane_z(net, plane, f_mhz)
    z_old = _plane_z(_as_transformers(net), plane, f_mhz)
    assert np.array_equal(z, z_old) and z.tobytes() == z_old.tobytes()
    re_hex, im_hex = RECORDED[(f_mhz, plane)]
    assert z[0] == complex(float.fromhex(re_hex), float.fromhex(im_hex)), z
