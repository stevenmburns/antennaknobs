"""The external engines read a knot current where the current really is
(issue #1638).

Two defects, found on AC6LA's `Cardioidmodnec5.nec` (two lambda/4 verticals
over PEC, `EX 4` forcing 1.414 A at each base), whose NEC-5 trace peaked at
5.41 dBi against EZNEC's 6.78 and razor-2p's 6.782:

* a wire end on the ground plane was read as a FREE end, so the base knot
  carrying the forced current rendered and radiated as 0 A, on NEC-5, NEC-2
  and PyNEC alike, although each engine bonds that end to the ground;
* NEC-5 prints tent-basis currents at segment centres, each the MEAN of its
  two knots, and the knots were rebuilt by averaging adjacent centres,
  smoothing the current twice. `_tent_knot_currents` inverts it exactly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from conftest import needs_nec5, needs_pynec

from antennaknobs.engines.nec5 import NEC5Engine, _tent_knot_currents
from antennaknobs.file_designs import builder_from_file

CARDIOID = (
    Path(__file__).parent / "fixtures" / "eznec_gyrator_1595" / "Cardioidmodnec5.nec"
)
I_BASE = 1.414214


def _mid(k):
    return 0.5 * (k[:-1] + k[1:])


def _s(n):
    return np.linspace(0.0, 1.0, n + 1)


# ---------------------------------------------------------------------------
# the inversion, topology by topology
# ---------------------------------------------------------------------------


def test_a_grounded_vertical_is_exact_and_carries_its_base_current():
    truth = I_BASE * np.cos(0.5 * np.pi * _s(6)) * np.exp(-0.05j * _s(6))
    (k,) = _tent_knot_currents(
        [_mid(truth)], [("g", "top")], {"g": "contact", "top": "free"}
    )
    np.testing.assert_allclose(k, truth, atol=1e-12)
    assert abs(k[0]) == pytest.approx(I_BASE)


def test_a_dipole_in_two_wires_is_exact():
    """Overdetermined (two free ends and a junction for two unknowns), and
    consistent."""
    a = np.sin(0.5 * np.pi * _s(5))
    b = np.cos(0.5 * np.pi * _s(7))
    kinds = {"l": "free", "c": "junction", "r": "free"}
    ka, kb = _tent_knot_currents([_mid(a), _mid(b)], [("l", "c"), ("c", "r")], kinds)
    np.testing.assert_allclose(ka, a, atol=1e-12)
    np.testing.assert_allclose(kb, b, atol=1e-12)


def test_a_three_wire_junction_obeys_kcl():
    x, y = 1.0 - 0.3j, 0.4 + 0.2j
    a = x * np.sin(0.5 * np.pi * _s(4))  # free -> J, arriving with x
    b = y * np.cos(0.5 * np.pi * _s(5))  # J -> free, leaving with y
    c = (x - y) * np.cos(0.5 * np.pi * _s(3))  # J -> free, the rest
    kinds = {"f1": "free", "j": "junction", "f2": "free", "f3": "free"}
    got = _tent_knot_currents(
        [_mid(a), _mid(b), _mid(c)], [("f1", "j"), ("j", "f2"), ("j", "f3")], kinds
    )
    for k, want in zip(got, (a, b, c), strict=True):
        np.testing.assert_allclose(k, want, atol=1e-12)


def _path_case(ends, kinds, lengths, shape):
    """Wires laid end to end along one path, the truth one smooth `shape` of
    the path's arclength; returns (truth per wire, recovered per wire)."""
    t = np.linspace(0.0, 1.0, sum(lengths) + 1)
    truth, at = [], 0
    for n in lengths:
        truth.append(shape(t[at : at + n + 1]))
        at += n
    return truth, _tent_knot_currents([_mid(k) for k in truth], ends, kinds)


@pytest.mark.parametrize(
    ("ends", "kinds", "lengths", "shape", "atol"),
    [
        # An inverted U grounded at both feet: no free end anywhere. The
        # smoothest choice is not the truth here, only near it; 1.5e-3
        # measured on this shape and mesh, shrinking as the mesh refines.
        (
            [("g1", "j1"), ("j1", "j2"), ("j2", "g2")],
            {"g1": "contact", "j1": "junction", "j2": "junction", "g2": "contact"},
            [8, 12, 8],
            lambda t: np.exp(t) + t**3 - 0.2j * t,
            5e-3,
        ),
        # A closed loop with an even number of segments: around a loop the
        # alternating mode's pull telescopes away, so it comes back exactly.
        (
            [("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")],
            {"a": "junction", "b": "junction", "c": "junction", "d": "junction"},
            [6, 6, 6, 6],
            lambda t: (
                np.cos(2.0 * np.pi * t)
                + 0.3 * np.sin(4.0 * np.pi * t)
                + 0.2j * np.cos(6.0 * np.pi * t)
                + 0.1j * np.sin(2.0 * np.pi * t)
            ),
            1e-12,
        ),
    ],
)
def test_what_the_nodes_leave_open_goes_to_the_smoothest_solution(
    ends, kinds, lengths, shape, atol
):
    """No free end pins the alternating mode, and it moves no midpoint: the
    printed centres come back exactly (the far field reads only those), and
    the knots land on or near the smooth truth rather than anywhere along
    the mode."""
    truth, got = _path_case(ends, kinds, lengths, shape)
    for k, want in zip(got, truth, strict=True):
        np.testing.assert_allclose(_mid(k), _mid(want), atol=1e-12)
        np.testing.assert_allclose(k, want, atol=atol)


def test_the_printouts_rounding_does_not_accumulate():
    """NEC-5 prints six significant figures; 120 segments of back-substitution
    stay at the printout's precision, not a random walk away from it."""
    truth = np.cos(0.5 * np.pi * _s(120)) * (1.2 - 0.4j)
    c = _mid(truth)
    rounded = np.array(
        [complex(float(f"{z.real:.5e}"), float(f"{z.imag:.5e}")) for z in c]
    )
    (k,) = _tent_knot_currents(
        [rounded], [("g", "top")], {"g": "contact", "top": "free"}
    )
    np.testing.assert_allclose(k, truth, atol=1e-4)


# ---------------------------------------------------------------------------
# NEC-5: which node is which (no binary)
# ---------------------------------------------------------------------------


def _cardioid_nec5(ground):
    cls = builder_from_file(str(CARDIOID))
    return NEC5Engine(cls(), ground=ground, require_exe=False)


def _vertical_truth(n):
    return I_BASE * np.cos(0.5 * np.pi * _s(n))


def test_nec5_bonds_a_base_on_the_ground_plane():
    eng = _cardioid_nec5("pec")
    truth = [_vertical_truth(card[3]) for card in eng._cards]
    per_tag = {t + 1: _mid(k) for t, k in enumerate(truth)}
    for wc, want in zip(eng._currents_from(per_tag), truth, strict=True):
        np.testing.assert_allclose(wc.knot_currents, want, atol=1e-12)
        assert abs(wc.knot_currents[0]) == pytest.approx(I_BASE)


def test_nec5_in_free_space_leaves_a_z0_end_free():
    """No ground card, no bond: the same end is an open wire end."""
    eng = _cardioid_nec5(None)
    n = eng._cards[0][3]
    truth = np.sin(np.pi * _s(n))  # zero at both ends
    per_tag = {t + 1: _mid(truth) for t in range(len(eng._cards))}
    for wc in eng._currents_from(per_tag):
        np.testing.assert_allclose(wc.knot_currents, truth, atol=1e-12)


# ---------------------------------------------------------------------------
# NEC-2 and PyNEC: the ground-contact rule
# ---------------------------------------------------------------------------


def _cardioid_nec2(ground):
    from antennaknobs.engines.nec2 import NEC2Engine

    cls = builder_from_file(str(CARDIOID))
    # Construction never runs the binary; any executable stands in for it.
    return NEC2Engine(cls(), ground=ground, nec2_exe=sys.executable)


def test_nec2_carries_a_bonded_base_and_zeroes_a_free_end():
    for ground, base in (("pec", 1.4), (None, 0.0)):
        eng = _cardioid_nec2(ground)
        per_tag = {
            i + 1: [1.4, 1.2, 0.9, 0.6, 0.3][: t[2]] for i, t in enumerate(eng.tups)
        }
        for wc in eng._currents_from(per_tag):
            assert wc.knot_currents[0] == base, ground
            assert wc.knot_currents[-1] == 0.0  # the top is free either way


@needs_pynec
def test_pynec_carries_a_bonded_base():
    from antennaknobs.engines.pynec import PyNECEngine

    cls = builder_from_file(str(CARDIOID))
    for wc in PyNECEngine(cls(), ground="pec").current_distribution():
        # NEC-2's source sits at the base segment's centre, so its centre
        # current IS the forced one.
        assert abs(wc.knot_currents[0]) == pytest.approx(I_BASE, rel=1e-4)
        assert wc.knot_currents[-1] == 0.0


# ---------------------------------------------------------------------------
# the licensed binary: the Cardioid itself
# ---------------------------------------------------------------------------


@needs_nec5
def test_the_cardioids_nec5_trace_is_razor_2ps():
    """The same basis on the same mesh: the knots agree to the printout's
    precision, and so does the pattern the app draws from them."""
    import copy

    import antennaknobs.web.examples  # noqa: F401  (before the adapter)
    from antennaknobs.web import server
    from antennaknobs.web.adapter import _make_example

    cls = builder_from_file(str(CARDIOID))
    f = cls().freq
    ex = _make_example("Cardioidmodnec5", cls)
    req = {
        "measurement_freq_mhz": f,
        "design_freq_mhz": f,
        "ground": True,
        "ground_model": "pec",
    }
    outs = [
        ex.nec5_solve(dict(req)),
        ex.momwire_solve(dict(req, momwire_model="razor-2p")),
    ]
    peaks = []
    for out in outs:
        o = copy.deepcopy(out)
        server._attach_derived_em_fields(o)
        server._attach_gain_norm(o)
        peaks.append(float(np.max(server._pattern_cuts(o, 0.5, 0.0)["azimuth"])))
    assert peaks[0] == pytest.approx(peaks[1], abs=0.005)
    assert peaks[0] == pytest.approx(6.78, abs=0.01)  # EZNEC's 6.78; it read 5.41
    for w5, wr in zip(outs[0]["wires"], outs[1]["wires"], strict=True):
        k5 = np.asarray(w5["knot_currents_re"]) + 1j * np.asarray(
            w5["knot_currents_im"]
        )
        kr = np.asarray(wr["knot_currents_re"]) + 1j * np.asarray(
            wr["knot_currents_im"]
        )
        np.testing.assert_allclose(k5, kr, atol=5e-4)
        assert abs(k5[0]) == pytest.approx(I_BASE, rel=1e-4)
