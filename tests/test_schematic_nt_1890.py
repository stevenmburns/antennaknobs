"""AK#1890: an EZNEC ``NT`` card draws as what it is, not as an opaque box.

Dan AC6LA's feed-system deck (`tests/fixtures/eznec_ac6la_1681/`, README there)
writes a high-pass T as two L-network ``NT`` cards and 100 ft of lossy line as
a third. All three drew as a box labelled "admittance". From the Y alone:

- an L network is a series element and one shunt, exact at the deck's ``FR``
  frequency (14.175 MHz here), labelled in pF and µH as EZNEC shows them;
- the second card is wired the other way round, so the chain walks it from
  its shunt side, and the symbols must follow the walk, not the card;
- the symmetric card is a 50.0 Ω line with 0.50 dB of matched loss.

Drawing only: the network the solver stamps is the same object, untouched.
"""

from __future__ import annotations

import base64
import cmath
import math
import zlib
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.examples  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.network import Admittance, PortVirtual
from antennaknobs.nec_import import parse_nec
from antennaknobs.schematic import default_elements, lower
from antennaknobs.web import decks, server
from momwire.networks import NetworkReducer

DECK = (
    Path(__file__).parent / "fixtures" / "eznec_ac6la_1681" / "Bydpole-TL-Xfmr-CLC.nec"
)
FREQ = 14.175
W = 2 * math.pi * FREQ * 1e6


def _deck():
    return parse_nec(
        DECK.read_text(encoding="utf-8", errors="replace"),
        name=DECK.name,
        network=True,
    )


def _chain(sch):
    return [[(e.kind, e.orient) for e in b.elements] for b in sch.blocks]


def test_the_deck_holds_its_nts_at_its_fr_frequency():
    assert _deck().nt_frequency_mhz() == FREQ


def test_two_l_networks_and_a_line_draw_as_themselves():
    net = _deck().network()
    sch = lower(net, nt_freq_mhz=FREQ)
    assert _chain(sch) == [
        [("capacitor", "series"), ("inductor", "shunt")],
        # The second card's shunt is on the side the walk ENTERS.
        [("inductor", "shunt"), ("capacitor", "series")],
        [("transformer", "series")],
        [("coax", "series")],
    ]
    labels = [[(e.label, e.sublabel) for e in b.elements] for b in sch.blocks]
    assert labels[0] == [("157 pF", "Q 1991"), ("0.586 µH", "Q 200")]
    assert labels[1] == [("0.586 µH", "Q 200"), ("350 pF", "Q 2005")]
    assert labels[3] == [("50 Ω line", "0.5 dB")]


def test_the_labels_are_the_cards_own_values():
    """Independent of the drawing code: the series C is -1/(ω·X) of
    Z = -1/Y12, and the shunt L is -1/(ω·B) of Y22 + Y12, straight off the
    card ``NT 2,1,2,4,7.0066E-6,1.3951E-2,-7.007E-6,-1.395E-2,1.0299E-4,-5.226E-3``."""
    y12 = complex(-7.007e-6, -1.395e-2)
    y22 = complex(1.0299e-4, -5.226e-3)
    c = -1.0 / (W * (-1.0 / y12).imag)
    lsh = -1.0 / (W * (y22 + y12).imag)
    assert f"{c * 1e12:.0f} pF" == "157 pF"
    assert f"{lsh * 1e6:.3f} µH" == "0.586 µH"


def test_the_line_reads_back_its_z0_and_loss():
    """``NT 2,3,1,10``: Z0 = 1/sqrt(Y11² − Y12²) = 50.000 − j0.21 Ω, and the
    matched loss Re(acosh(−Y11/Y12)) is 0.500 dB."""
    y11 = complex(1.4119e-3, -8.8203e-3)
    y12 = complex(-6.476e-4, 2.18219e-2)
    z0 = 1.0 / cmath.sqrt(y11 * y11 - y12 * y12)
    assert z0 == pytest.approx(50.0, abs=0.25)
    assert 8.6859 * cmath.acosh(-y11 / y12).real == pytest.approx(0.5, abs=1e-3)


def test_drawing_does_not_touch_the_network():
    """The solved Z is unchanged: `lower` reads the network and the reducer
    stamps the same branches, so the driven impedance is identical."""
    net = _deck().network()
    before = list(net.branches)

    def driven(n):
        real = [k for k, p in n.ports.items() if not isinstance(p, PortVirtual)]
        idx = {k: i for i, k in enumerate(real)}
        for k in n.ports:
            idx.setdefault(k, len(idx))
        z = NetworkReducer(n, idx, len(idx)).driven_impedance(
            np.array([[1.0 / complex(75.3, -30.9)]]), 299792458.0 / (FREQ * 1e6)
        )
        return complex(np.atleast_1d(z)[0])

    z0 = driven(net)
    lower(net, nt_freq_mhz=FREQ)
    assert list(net.branches) == before
    assert driven(net) == z0


def test_without_a_frequency_the_values_are_labelled_as_admittances():
    """A network built in code has no FR card: same symbols, labelled with
    the reactance and susceptance the card holds."""
    br = Admittance(
        ports=("a", "b"),
        y=((7.0066e-6 + 1.3951e-2j, -7.007e-6 - 1.395e-2j),
           (-7.007e-6 - 1.395e-2j, 1.0299e-4 - 5.226e-3j)),
    )  # fmt: skip
    els = default_elements(br)
    assert [(e.kind, e.orient) for e in els] == [
        ("capacitor", "series"),
        ("inductor", "shunt"),
    ]
    assert els[0].label == "X -71.7 Ω"
    assert els[1].label == "B -19.2 mS"


@pytest.mark.parametrize(
    "y",
    [
        # A pi with a shunt at both ports is not an L network...
        ((0.01 + 0.02j, -0.02j), (-0.02j, 0.01 + 0.03j)),
        # ...nor is a non-reciprocal 2-port...
        ((0.02j, -0.02j), (-0.03j, 0.01 + 0.03j)),
        # ...nor a symmetric one whose Z0 is far from real.
        ((0.01 + 0.0j, 0.002 + 0.02j), (0.002 + 0.02j, 0.01 + 0.0j)),
    ],
)
def test_other_shapes_keep_the_box(y):
    els = default_elements(Admittance(ports=("a", "b"), y=y), FREQ)
    assert [(e.kind, e.label) for e in els] == [("box", "admittance")]


def test_a_one_port_admittance_keeps_the_box():
    els = default_elements(Admittance(ports=("a",), y=((0.01j,),)), FREQ)
    assert [e.kind for e in els] == ["box"]


# ---------------------------------------------------------------------------
# the server: an opened deck's schematic carries the values
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh_decks(monkeypatch):
    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


def test_an_opened_deck_draws_its_l_networks_with_values(fresh_decks):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = c.compress(DECK.read_bytes()) + c.flush()
    client = TestClient(server.app)
    r = client.post(
        "/deck",
        json={
            "name": DECK.name,
            "z": base64.urlsafe_b64encode(packed).decode().rstrip("="),
        },
    )
    assert r.status_code == 200, r.text
    svg = client.post("/schematic", json={"geometry": r.json()["key"]}).json()["svg"]
    for text in ("157 pF", "0.586 µH", "350 pF", "50 Ω line"):
        assert text in svg, text
    assert "admittance" not in svg
