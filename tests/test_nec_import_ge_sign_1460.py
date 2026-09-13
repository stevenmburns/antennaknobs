"""antennaknobs#1460 — the importer carries GE's sign.

`GE -1` declares the ground plane WITHOUT the ground-contact current expansion
(momwire#489). Every engine here serves the interpolated (`GE 1`) contact, so a
FREE wire end standing in the plane under an applied ground is refused at
engine construction, in #489's wording. A crossing junction (a wire continuing
above the plane and one continuing below, momwire#1052) is served, identically
under either sign.

The refusal lives at engine construction rather than at parse time because the
CLI's `--ground` and the app's ground switch can apply a ground after the deck
is parsed: the same `GE -1` deck refuses under a ground and serves in free
space. Design: scratch/1460-ge-sign/DESIGN.md.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec2 import NEC2Engine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import ge_minus_one_contact_refusal, parse_nec

TAIL = "FR 0 1 0 0 30 0\nXQ 0\nEN\n"
# A 30 MHz quarter-wave standing on the plane, base-fed.
VERTICAL = (
    "CM vertical\nCE\nGW 1 11 0 0 0 0 0 2.5 0.001\n{ge}\n{gn}EX 0 1 1 0 1 0\n" + TAIL
)
# The same wire lifted clear of the plane, centre-fed.
LIFTED = (
    "CM lifted\nCE\nGW 1 11 0 0 0.5 0 0 3.0 0.001\n{ge}\nGN 1\nEX 0 1 6 0 1 0\n" + TAIL
)
# A crossing rod: 2.5 m above and 0.5 m below, joined at z = 0, over soil A.
CROSSING = (
    "CM crossing\nCE\nGW 1 11 0 0 0 0 0 2.5 0.001\nGW 2 4 0 0 0 0 0 -0.5 0.001\n"
    "{ge}\nGN 2 0 0 0 13 0.005\nEX 0 1 6 0 1 0\n" + TAIL
)
SOIL_A = ("finite", 13.0, 0.005)
REFUSAL = (
    r"GE -1 declares the ground plane without the ground-contact current "
    r"expansion, and wire 1's end stands in the plane"
)


def _builder(tmp_path, text, name="deck.nec"):
    p = tmp_path / name
    p.write_text(text)
    return builder_from_file(str(p))


def _z(builder, ground):
    return complex(MomwireEngine(builder(), ground=ground).impedance()[0])


def test_g1460_1_a_grounded_quarter_wave_refuses_under_ge_minus_one(tmp_path):
    b = _builder(tmp_path, VERTICAL.format(ge="GE -1", gn="GN 1\n"))
    with pytest.raises(ValueError, match=REFUSAL):
        MomwireEngine(b(), ground="pec")


@pytest.mark.parametrize("engine", ["nec2", "nec5", "pynec"])
def test_g1460_1b_every_engine_refuses_before_looking_for_its_binary(tmp_path, engine):
    """The refusal is about the deck's geometry against the applied ground,
    so it comes before any binary probe: a missing binary cannot mask it."""
    b = _builder(tmp_path, VERTICAL.format(ge="GE -1", gn="GN 1\n"))
    if engine == "pynec":
        cls = pytest.importorskip("antennaknobs.engines.pynec").PyNECEngine
        kwargs = {}
    elif engine == "nec2":
        cls, kwargs = NEC2Engine, {"nec2_exe": "/nonexistent/nec2c"}
    else:
        cls, kwargs = NEC5Engine, {"nec5_exe": "/nonexistent/nec5"}
    with pytest.raises(ValueError, match=REFUSAL):
        cls(b(), ground="pec", **kwargs)


def test_g1460_2_the_same_vertical_serves_under_ge_one(tmp_path):
    b = _builder(tmp_path, VERTICAL.format(ge="GE 1", gn="GN 1\n"))
    assert np.isfinite(_z(b, "pec"))


def test_g1460_3_ge_minus_one_clear_of_the_plane_serves(tmp_path):
    b = _builder(tmp_path, LIFTED.format(ge="GE -1"))
    assert np.isfinite(_z(b, "pec"))


def test_g1460_4_ge_minus_one_in_free_space_serves(tmp_path):
    """The deck models a ground, but the run applies none (`--ground free`):
    there is no image to disagree about."""
    b = _builder(tmp_path, VERTICAL.format(ge="GE -1", gn="GN 1\n"))
    assert np.isfinite(_z(b, "free"))
    assert np.isfinite(_z(b, None))


def test_g1460_5_a_crossing_junction_serves_identically_under_either_sign(tmp_path):
    """The sign never reaches the solver, so the two answers are one number."""
    minus = _builder(tmp_path, CROSSING.format(ge="GE -1"), name="minus.nec")
    plus = _builder(tmp_path, CROSSING.format(ge="GE 1"), name="plus.nec")
    z_minus, z_plus = _z(minus, SOIL_A), _z(plus, SOIL_A)
    assert np.isfinite(z_minus)
    assert z_minus == z_plus


def test_g1460_6_the_sign_and_the_free_plane_ends():
    vertical = parse_nec(VERTICAL.format(ge="GE -1", gn="GN 1\n"))
    assert vertical.ground_contact_interpolates is False
    for ge in ("GE 1", "GE 0"):
        deck = parse_nec(VERTICAL.format(ge=ge, gn=""))
        assert deck.ground_contact_interpolates is True
    assert vertical.free_plane_ends() == ((0, "p1"),)
    assert parse_nec(CROSSING.format(ge="GE -1")).free_plane_ends() == ()
    # a buried wire that only reaches UP to the plane is a free end too
    below_only = parse_nec(
        "CM below\nCE\nGW 1 4 0 0 0 0 0 -0.5 0.001\nGE -1\nGN 2 0 0 0 13 0.005\n"
        "EX 0 1 2 0 1 0\n" + TAIL
    )
    assert below_only.free_plane_ends() == ((0, "p1"),)
    # the pure refusal: only GE -1, only under an applied ground, only a free end
    assert "wire 1's end stands in the plane" in ge_minus_one_contact_refusal(
        vertical, "pec"
    )
    assert ge_minus_one_contact_refusal(vertical, SOIL_A) is not None
    assert ge_minus_one_contact_refusal(vertical, "free") is None
    assert ge_minus_one_contact_refusal(vertical, None) is None
    assert ge_minus_one_contact_refusal(None, "pec") is None
    ge1 = parse_nec(VERTICAL.format(ge="GE 1", gn="GN 1\n"))
    assert ge_minus_one_contact_refusal(ge1, "pec") is None
    lifted = parse_nec(LIFTED.format(ge="GE -1"))
    assert ge_minus_one_contact_refusal(lifted, "pec") is None


def test_g1460_7_refinement_keeps_the_sign():
    deck = parse_nec(VERTICAL.format(ge="GE -1", gn="GN 1\n"))
    assert deck.refined(3).ground_contact_interpolates is False
    assert deck.refined(3).free_plane_ends() == ((0, "p1"),)
