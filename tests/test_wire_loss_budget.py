"""Wire-loss power accounting (issue #317): the "wire loss (I²R)" budget
row and the efficiency fold-in, on both engines and all excitation paths.

Ohmic wire loss happens *inside* the MoM solve (momwire#131 loading /
NEC's LD 5), so it already lives in P_in and the gain normalisation —
these tests pin the *bookkeeping*: budget rows and reported efficiency.
"""

import numpy as np
import pytest

from antennaknobs import resolve_variant_params
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines import MomwireEngine, PyNECEngine

from conftest import needs_pynec

WIRE_ROW = "wire loss (I²R)"


def _builder(wire_type=None, variant=None):
    params = resolve_variant_params(Builder, variant) if variant else None
    b = Builder(params)
    if wire_type is not None:
        b.wire_type = wire_type
    return b


def _excited(eng):
    eng.current_distribution()
    p_in = eng._excited_p_in
    if p_in is None:  # momwire plain path derives it on demand
        p_in = eng.input_power()
    return eng._excited_efficiency, float(p_in), list(eng._excited_power_budget)


def test_ideal_design_bookkeeping_unchanged():
    eff, p_in, budget = _excited(MomwireEngine(_builder(), ground=None))
    assert eff == 1.0
    assert budget == []
    assert p_in > 0.0


def test_momwire_plain_path_row_and_efficiency():
    eff, p_in, budget = _excited(MomwireEngine(_builder("28-awg"), ground=None))
    rows = [w for label, w in budget if label == WIRE_ROW]
    assert len(rows) == 1
    p_wire = rows[0]
    assert 0.0 < p_wire < p_in
    assert eff == pytest.approx(1.0 - p_wire / p_in, abs=1e-12)
    # 28 AWG on a 10 m-band invvee: mid-90s% efficiency window
    assert 0.90 < eff < 0.97


def test_momwire_repeated_excite_single_row():
    eng = MomwireEngine(_builder("28-awg"), ground=None)
    eng.current_distribution()
    eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    eng.current_distribution()
    labels = [label for label, _w in eng._excited_power_budget]
    assert labels.count(WIRE_ROW) == 1


def test_momwire_radiated_power_matches_far_field_integral():
    """Free-space straight dipole (up/down symmetric): integrating the
    gain pattern over the sphere must return 4π·efficiency — the wire
    loss the budget claims is exactly the power missing from the sky."""
    eng = MomwireEngine(_builder("28-awg", variant="dipole"), ground=None)
    eff, _p_in, _budget = _excited(eng)
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    D = 10.0 ** (np.asarray(ff.rings) / 10.0)  # (n_theta, n_phi+1)
    theta = np.deg2rad(np.linspace(0, 89, 90))
    dth, dph = np.deg2rad(1.0), np.deg2rad(1.0)
    hemi = float(np.sum(D[:, :-1] * np.sin(theta)[:, None]) * dth * dph)
    eff_from_sky = 2.0 * hemi / (4.0 * np.pi)  # symmetric: sphere = 2×hemi
    assert eff_from_sky == pytest.approx(eff, rel=0.05)


@needs_pynec
def test_cross_engine_efficiency_oracle():
    """momwire's c†·Re(L)·c readout vs PyNEC's LD 5 + segment-current
    integration: two independent implementations of the same physics."""
    eff_m, _pm, bud_m = _excited(MomwireEngine(_builder("28-awg"), ground=None))
    eff_p, _pp, bud_p = _excited(PyNECEngine(_builder("28-awg"), ground=None))
    assert abs(eff_m - eff_p) < 0.01
    assert [label for label, _ in bud_m] == [WIRE_ROW]
    assert [label for label, _ in bud_p] == [WIRE_ROW]


@needs_pynec
def test_pynec_ideal_unchanged():
    eff, _p_in, budget = _excited(PyNECEngine(_builder(), ground=None))
    assert eff == 1.0
    assert budget == []


def test_momwire_network_path_appends_to_branch_rows():
    """A lossy-wire station design (TL network): the wire row joins the
    existing branch budget instead of replacing it, and efficiency drops
    below the network-only value."""
    from antennaknobs.designs.dipoles.invvee_coax_station import (
        Builder as Station,
    )

    b_ideal = Station()
    b_lossy = Station()
    b_lossy.wire_type = "28-awg"
    eng_i = MomwireEngine(b_ideal, ground=None)
    eng_l = MomwireEngine(b_lossy, ground=None)
    eff_i, _pi, bud_i = _excited(eng_i)
    eff_l, _pl, bud_l = _excited(eng_l)
    labels_i = [label for label, _ in bud_i]
    labels_l = [label for label, _ in bud_l]
    assert WIRE_ROW not in labels_i
    assert labels_l == labels_i + [WIRE_ROW]
    assert eff_l < eff_i
