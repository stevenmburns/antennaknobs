"""Ferrite cores from complex permeability (issue #599).

`qlmag` is one number for a quantity that is emphatically not one number: a
43-mix balun burns its watts in one part of the spectrum and is nearly
lossless elsewhere. These tests cover the material model (μ′ sets the
inductance, μ″ the loss), the bridge back to the scalar model, and the choke
behaviour the frequency dependence exists to reproduce.
"""

import math

import numpy as np
import pytest

from antennaknobs.ferrite import (
    CORES,
    MATERIALS,
    FerriteCore,
    FerriteMaterial,
    core_from_catalog,
    material_from_catalog,
)
from antennaknobs.network import Driven, Instance, Network, PortVirtual, Shunt
from antennaknobs.network_reduce import NetworkReducer, magnetizing_impedance
from antennaknobs.station import unun

NO_ANTENNA = np.zeros((0, 0), dtype=complex)


def flat_material(mu=100.0, q=20.0, name="flat"):
    """A material with constant μ′ and μ″ = μ′/Q — i.e. a scalar Q, dressed up
    as a table. The bridge between the two models."""
    f = np.array([0.01, 1.0, 100.0, 1000.0])
    return FerriteMaterial.from_table(
        name, f, np.full(4, mu), np.full(4, mu / q), source="test"
    )


# ---------------------------------------------------------------------------
# the material
# ---------------------------------------------------------------------------
def test_debye_has_the_shape_every_datasheet_shows():
    m = FerriteMaterial.debye("t", 800.0, 10.0)
    lo, at, hi = m.at(0.1), m.at(10.0), m.at(1000.0)

    assert lo.real == pytest.approx(800.0, rel=1e-3)  # μ′ → μi well below f_r
    assert at.real == pytest.approx(400.0, rel=1e-3)  # ...half of it at f_r
    assert hi.real < 1.0  # ...and gone above
    # μ″ peaks at f_r, at μi/2.
    assert -at.imag == pytest.approx(400.0, rel=1e-3)
    assert -lo.imag < -at.imag and -hi.imag < -at.imag


def test_q_is_mu_prime_over_mu_double():
    """The identity that makes this a generalisation of `qlmag` rather than a
    replacement for it."""
    m = FerriteMaterial.debye("t", 800.0, 10.0)
    for f in (1.0, 5.0, 10.0, 50.0):
        mu = m.at(f)
        assert m.q_at(f) == pytest.approx(mu.real / -mu.imag, rel=1e-12)
    # Q falls through 1 exactly at the relaxation frequency.
    assert m.q_at(10.0) == pytest.approx(1.0, rel=1e-3)
    assert m.q_at(1.0) > 5.0


def test_permeability_is_not_extrapolated():
    m = FerriteMaterial.debye("t", 800.0, 10.0)
    lo, hi = m.freqs[0], m.freqs[-1]
    with pytest.raises(ValueError, match="not extrapolated"):
        m.at(lo * 0.5)
    with pytest.raises(ValueError, match="outside the material data"):
        m.at(hi * 2.0)
    assert m.at(lo) and m.at(hi)  # the endpoints themselves are fine


def test_interpolation_is_done_in_log_frequency():
    """Permeability curves live on log axes; linear-in-f interpolation across a
    decade would badly undercut μ″."""
    m = FerriteMaterial.from_table("t", [1.0, 100.0], [100.0, 200.0], [10.0, 20.0])
    mid = m.at(10.0)  # the geometric centre, not the arithmetic one
    assert mid.real == pytest.approx(150.0, rel=1e-9)
    assert -mid.imag == pytest.approx(15.0, rel=1e-9)


def test_from_table_validates_and_sorts():
    m = FerriteMaterial.from_table("t", [10.0, 1.0], [50.0, 100.0], [5.0, 10.0])
    assert list(m.freqs) == [1.0, 10.0]
    assert list(m.mu_prime) == [100.0, 50.0]
    with pytest.raises(ValueError, match="equal length"):
        FerriteMaterial.from_table("t", [1.0, 2.0], [1.0], [1.0, 2.0])
    with pytest.raises(ValueError, match="μ′ must be positive"):
        FerriteMaterial.from_table("t", [1.0, 2.0], [0.0, 1.0], [1.0, 2.0])


# ---------------------------------------------------------------------------
# the wound core
# ---------------------------------------------------------------------------
def test_inductance_comes_from_mu_prime_and_turns_squared():
    a = core_from_catalog("FT-240", "43", 10)
    b = core_from_catalog("FT-240", "43", 20)
    assert b.inductance(1.0) == pytest.approx(4.0 * a.inductance(1.0), rel=1e-12)
    # L = k·μ′ exactly, with k the geometry constant.
    assert a.inductance(1.0) == pytest.approx(
        a.al_factor * a.material.at(1.0).real, rel=1e-12
    )


def test_impedance_splits_into_mu_double_loss_and_mu_prime_reactance():
    c = core_from_catalog("FT-240", "43", 11)
    f = 7.0
    z = c.impedance(f)
    omega = 2 * math.pi * f * 1e6
    mu = c.material.at(f)
    assert z.real == pytest.approx(omega * c.al_factor * -mu.imag, rel=1e-12)
    assert z.imag == pytest.approx(omega * c.al_factor * mu.real, rel=1e-12)
    assert z.real > 0  # loss is dissipative, whatever the material


def test_a_flat_material_reproduces_scalar_qlmag_exactly():
    """The acceptance criterion, and the reason this is a generalisation: a
    material with constant μ′ and μ″ = μ′/Q must give the same magnetizing
    branch as the old two-scalar model."""
    from antennaknobs.network import Transformer

    core = FerriteCore(
        material=flat_material(mu=100.0, q=20.0), turns=10, ae=1e-4, le=0.1
    )
    f = 14.0
    omega = 2 * math.pi * f * 1e6
    lmag = core.inductance(f)

    scalar = Transformer(a="x", b="y", n=1.0, lmag=lmag, qlmag=20.0)
    material = Transformer(a="x", b="y", n=1.0, core=core)
    assert magnetizing_impedance(material, omega) == pytest.approx(
        magnetizing_impedance(scalar, omega), rel=1e-12
    )


def test_a_real_choke_impedance_peaks_and_falls():
    """The characteristic curve. A single relaxation alone climbs and
    saturates; the winding's few pF resonate with it, which is what puts the
    peak in every published choke plot — and why `c_stray` exists.
    """
    c = core_from_catalog("FT-240", "43", 11, c_stray_pF=3.0)
    freqs = np.array([1.0, 2.0, 3.5, 7.0, 14.0, 28.0, 50.0])
    mags = np.array([abs(c.impedance(f)) for f in freqs])
    peak = int(np.argmax(mags))

    assert 0 < peak < len(freqs) - 1, "the peak must be interior, not an endpoint"
    assert mags[0] < mags[peak] > mags[-1]
    # Above resonance the winding looks capacitive — the other half of the
    # signature, and the reason a choke stops choking at VHF.
    assert c.impedance(freqs[peak + 1]).imag < 0
    assert c.impedance(1.0).imag > 0


def test_without_stray_capacitance_the_one_pole_model_saturates():
    """Stated as a limitation rather than hidden: this is why `c_stray` is part
    of modelling a real choke and not an optional refinement."""
    c = core_from_catalog("FT-240", "43", 11)
    mags = [abs(c.impedance(f)) for f in (1.0, 3.5, 14.0, 50.0, 200.0)]
    assert all(b >= a * 0.999 for a, b in zip(mags, mags[1:]))  # monotone


def test_more_turns_is_more_impedance():
    z10 = abs(core_from_catalog("FT-240", "43", 10).impedance(7.0))
    z20 = abs(core_from_catalog("FT-240", "43", 20).impedance(7.0))
    assert z20 == pytest.approx(4.0 * z10, rel=1e-12)


# ---------------------------------------------------------------------------
# catalogs
# ---------------------------------------------------------------------------
def test_the_catalog_covers_the_common_mixes_and_sizes():
    assert {"31", "43", "52", "61"} <= set(MATERIALS)
    assert {"FT-240", "FT-140", "FT-82"} <= set(CORES)


def test_every_catalog_material_says_where_it_came_from():
    """These are one-pole fits, not vendor curves, and each entry has to say
    so — it is the first question anyone comparing to a measurement asks."""
    for name, m in MATERIALS.items():
        assert m.source, name
        assert "fit" in m.source


def test_higher_permeability_mixes_relax_lower():
    """The physical ordering (Snoek's limit): more μ, lower usable frequency."""
    mu_i = {k: m.mu_prime[0] for k, m in MATERIALS.items()}
    assert mu_i["31"] > mu_i["43"] > mu_i["61"]
    # ...and their loss peaks run the other way.
    peak = {k: m.freqs[int(np.argmax(m.mu_double))] for k, m in MATERIALS.items()}
    assert peak["31"] < peak["43"] < peak["61"]


def test_unknown_catalog_keys_name_the_alternatives():
    with pytest.raises(KeyError, match="unknown ferrite mix"):
        material_from_catalog("99")
    with pytest.raises(KeyError, match="unknown core size"):
        core_from_catalog("FT-999", "43", 10)
    with pytest.raises(ValueError, match="turns must be positive"):
        core_from_catalog("FT-240", "43", 0)


# ---------------------------------------------------------------------------
# in a circuit
# ---------------------------------------------------------------------------
def loss_fraction(f_mhz, **unun_kw):
    """Core loss as a fraction of input power, for a 49:1 unun into 2450 Ω."""
    net = Network(
        ports={"line": PortVirtual("line"), "ant": PortVirtual("ant")},
        branches=[
            Instance("x", unun(7.0, **unun_kw), line="line", ant="ant"),
            Shunt(port="ant", r=2450.0, parallel=True),
        ],
        sources=[Driven(port="line")],
    )
    red = NetworkReducer(net, {"line": 0, "ant": 1}, 2)
    _v, _eff, p_in, rows = red.excited_state(NO_ANTENNA, 299_792_458.0 / (f_mhz * 1e6))
    return sum(w for label, w in rows if "Transformer" in label) / p_in


def test_a_core_dissipates_and_itemises_in_the_budget():
    core = core_from_catalog("FT-240", "43", 11, c_stray_pF=3.0)
    assert loss_fraction(7.0, core=core) > 0.0


def test_the_core_supersedes_the_scalar_pair():
    """`core` is the core, not a default — the same posture as
    `TL.from_cable`'s cable."""
    core = core_from_catalog("FT-240", "43", 11)
    with_core = loss_fraction(7.0, core=core, lmag_uH=1.0, qlmag=1.0)
    core_only = loss_fraction(7.0, core=core)
    assert with_core == pytest.approx(core_only, rel=1e-12)


def test_material_loss_has_a_frequency_shape_a_flat_q_cannot():
    """The whole point of the issue. Across a decade the two models disagree
    about the *shape* of the loss, not merely its size."""
    core = core_from_catalog("FT-240", "43", 11, c_stray_pF=3.0)
    freqs = [1.8, 3.5, 7.0, 14.0, 28.0]
    material = np.array([loss_fraction(f, core=core) for f in freqs])
    scalar = np.array([loss_fraction(f, lmag_uH=320.0, qlmag=20.0) for f in freqs])

    # Normalise out the overall level: the claim is about shape.
    material /= material.max()
    scalar /= scalar.max()
    assert np.max(np.abs(material - scalar)) > 0.25
    # The scalar model can only ever fall monotonically here.
    assert all(b <= a for a, b in zip(scalar, scalar[1:]))


def test_a_lossless_material_burns_nothing():
    core = FerriteCore(
        material=FerriteMaterial.from_table(
            "ideal", [0.1, 1000.0], [100.0, 100.0], [0.0, 0.0]
        ),
        turns=10,
        ae=1e-4,
        le=0.1,
    )
    assert loss_fraction(7.0, core=core) == pytest.approx(0.0, abs=1e-12)
