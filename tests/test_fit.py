"""Fitting model parameters to a measured sweep (issue #639).

Most of these run against an *analytic* stand-in engine — a series-RLC
feedpoint whose resonance and loss follow the builder's knobs. That is on
purpose: the machinery under test is the objective, the bounds, the
identifiability diagnostics and the plane handling, and an engine with a closed
form makes "did the fit recover the truth?" an exact question with no meshing
noise and no seconds-long solves. One test at the bottom does the same round
trip through the real momwire engine, so the wiring is covered too.
"""

from types import MappingProxyType

import numpy as np
import pytest

import antennaknobs as ant
from antennaknobs import AntennaBuilder
from antennaknobs.fit import (
    MAX_FREE_PARAMS,
    FitResult,
    LineEmbedding,
    fit,
    plot_fit,
)
from antennaknobs.measured import BandOverlapError, MeasuredTrace


class Builder(AntennaBuilder):
    """Knobs for the analytic engine below; never actually meshed."""

    default_params = MappingProxyType(
        {"freq": 14.1, "design_freq": 14.1, "length_factor": 1.0, "rs": 60.0}
    )

    def build_wires(self):  # pragma: no cover — the fake engine never calls it
        raise NotImplementedError


class RLCEngine:
    """A series-RLC feedpoint: R = ``rs``, resonant where the element is 1/2 λ.

    ``length_factor`` slides the resonance and ``rs`` sets the depth of the
    match — two knobs that bend Γ in genuinely different ways, which is what
    makes them jointly identifiable (unlike ``length_factor`` and
    ``design_freq``, which do not, and which one test below relies on).
    """

    Q = 12.0

    def __init__(self, builder):
        self.b = builder

    def impedance_sweep(self, freqs):
        f = np.asarray(freqs, dtype=float)
        f0 = self.b.design_freq / self.b.length_factor
        x = self.b.rs * self.Q * (f / f0 - f0 / f)
        return (self.b.rs + 1j * x)[:, None]


def synth_measurement(
    z0=50.0, label="synthetic", npoints=41, band=(13.6, 14.6), **knobs
):
    """A 'measurement' generated from the model itself at known knob values."""
    b = Builder()
    for k, v in knobs.items():
        setattr(b, k, v)
    freqs = np.linspace(band[0], band[1], npoints)
    z = RLCEngine(b).impedance_sweep(freqs)[:, 0]
    return MeasuredTrace(freqs=freqs, gamma=(z - z0) / (z + z0), z0=z0, label=label)


# ---------------------------------------------------------------------------
# the fit itself
# ---------------------------------------------------------------------------
def test_recovers_known_parameters():
    """The headline claim: perturb the model, and the fit finds the perturbation."""
    meas = synth_measurement(length_factor=1.035, rs=72.0)
    res = fit(
        Builder(), meas, ["length_factor", "rs"], engine=RLCEngine, npoints=15,
        fractions=0.3,
    )  # fmt: skip

    assert res.fitted[0] == pytest.approx(1.035, rel=1e-3)
    assert res.fitted[1] == pytest.approx(72.0, rel=1e-3)
    assert res.rms_fitted < 1e-4 < res.rms_nominal
    assert res.at_bound == ()
    assert res.condition < 100  # these two knobs really are distinguishable


def test_fitted_builder_carries_the_answer():
    """The builder comes back *at* the fit, ready to serialise as a variant."""
    meas = synth_measurement(length_factor=1.02)
    b = Builder()
    res = fit(b, meas, ["length_factor"], engine=RLCEngine, npoints=9)
    assert res.builder is b
    assert b.length_factor == pytest.approx(res.fitted[0])
    assert "length_factor" in ant.builder_params_source(b, include_ui=False)


def test_reports_a_degenerate_pair_by_name():
    """length_factor and design_freq are the same knob wearing two hats.

    The fit still converges — the *identified* direction is well determined —
    so the only thing standing between the user and a confident nonsense value
    is this diagnostic.
    """
    meas = synth_measurement(length_factor=1.03)
    res = fit(
        Builder(), meas, ["length_factor", "design_freq"], engine=RLCEngine,
        npoints=11, fractions=0.15,
    )  # fmt: skip

    assert res.condition > 100
    # Both knobs scale the element the same way, so the blind direction moves
    # them together with equal weight.
    w = np.abs(np.array(res.weakest))
    assert w[0] == pytest.approx(w[1], rel=0.05)
    assert "under-determined" in res.report()


def test_bounds_are_respected_and_pinning_is_reported():
    meas = synth_measurement(length_factor=1.20)  # far outside the bounds below
    res = fit(
        Builder(), meas, ["length_factor"], engine=RLCEngine, npoints=9,
        bounds=[(0.98, 1.02)],
    )  # fmt: skip

    assert res.fitted[0] == pytest.approx(1.02, abs=1e-9)
    assert res.at_bound == ("length_factor",)
    assert "ended at a bound" in res.report()


def test_a_scalar_fraction_covers_every_parameter():
    meas = synth_measurement(length_factor=1.01, rs=63.0)
    res = fit(
        Builder(), meas, ["length_factor", "rs"], engine=RLCEngine, npoints=9,
        fractions=[0.2],
    )  # fmt: skip
    assert res.bounds == ((0.8, 1.2), (48.0, 72.0))


def test_too_many_free_parameters_is_refused():
    meas = synth_measurement()
    names = ["length_factor", "rs", "design_freq", "freq", "base"]
    assert len(names) > MAX_FREE_PARAMS
    with pytest.raises(ValueError, match="identify"):
        fit(Builder(), meas, names, engine=RLCEngine)


def test_disjoint_fit_range_is_a_clear_error():
    meas = synth_measurement()
    with pytest.raises(BandOverlapError, match="does not overlap"):
        fit(Builder(), meas, ["length_factor"], engine=RLCEngine, band=(21.0, 21.5))


def test_fit_range_restricts_the_comparison_band():
    meas = synth_measurement(length_factor=1.02, npoints=101)
    res = fit(
        Builder(), meas, ["length_factor"], engine=RLCEngine, npoints=9,
        band=(14.0, 14.3),
    )  # fmt: skip
    assert res.freqs.min() >= 14.0 and res.freqs.max() <= 14.3
    assert 2 <= res.freqs.size <= 9
    # Evenly spaced, which PyNECEngine.impedance_sweep requires.
    assert np.allclose(np.diff(res.freqs), np.diff(res.freqs)[0])
    assert res.fitted[0] == pytest.approx(1.02, rel=1e-3)


def test_comparison_points_are_measured_frequencies():
    """The grid is a subsample of the measurement — nothing is interpolated."""
    meas = synth_measurement(npoints=41)
    res = fit(Builder(), meas, ["length_factor"], engine=RLCEngine, npoints=11)
    assert res.freqs.size == 11
    assert np.all(np.isin(res.freqs, meas.freqs))


def test_a_coarse_measurement_is_used_whole():
    meas = synth_measurement(npoints=5)
    res = fit(Builder(), meas, ["length_factor"], engine=RLCEngine, npoints=21)
    np.testing.assert_allclose(res.freqs, meas.freqs)


def test_off_band_measurement_is_flagged_not_refused():
    """Fitting off-band is legitimate; picking the wrong file is not. Say so."""
    meas = synth_measurement(band=(21.0, 21.5))  # 20 m design, a 15 m measurement
    res = fit(Builder(), meas, ["length_factor"], engine=RLCEngine, npoints=7)
    assert "long way off-band" in res.report()


def test_harmonic_band_reads_as_harmonic_operation():
    meas = synth_measurement(band=(42.0, 42.6))  # 3rd harmonic of 14.1
    res = fit(Builder(), meas, ["length_factor"], engine=RLCEngine, npoints=7)
    assert "3rd harmonic" in res.report() or "3th harmonic" in res.report()


# ---------------------------------------------------------------------------
# measurement plane
# ---------------------------------------------------------------------------
def test_line_embedding_matches_the_classic_transforms():
    lam_vf = 299792458.0 / 14e6 * 0.66
    quarter = LineEmbedding(z0=50.0, length_m=lam_vf / 4, vf=0.66)
    half = LineEmbedding(z0=50.0, length_m=lam_vf / 2, vf=0.66)
    f = np.array([14.0])
    # Quarter-wave inverts about z0²; half-wave is the identity.
    assert quarter.embed(np.array([100 + 0j]), f)[0] == pytest.approx(25.0, abs=1e-9)
    assert half.embed(np.array([100 + 0j]), f)[0] == pytest.approx(100.0, abs=1e-9)


def test_lossy_line_pulls_a_mismatch_toward_z0():
    """Loss is why a long coax makes a bad antenna look good from the shack."""
    line = LineEmbedding.from_cable("RG-58", 60.0)
    f = np.array([28.0])
    z = line.embed(np.array([500 + 0j]), f)[0]
    g_in = abs((z - 50.0) / (z + 50.0))
    g_load = abs((500 - 50.0) / (500 + 50.0))
    assert g_in < g_load


def test_station_plane_measurement_recovers_the_antenna():
    """A sweep taken through 20 m of coax fits the same antenna it came from.

    This is the whole point of --plane station: the parameters are properties
    of the antenna, so moving the measurement plane must not move them.
    """
    line = LineEmbedding.from_cable("RG-213", 20.0)
    truth = synth_measurement(length_factor=1.04, rs=70.0)
    at_shack = MeasuredTrace(
        freqs=truth.freqs,
        gamma=(lambda z: (z - 50.0) / (z + 50.0))(
            line.embed(truth.impedance, truth.freqs)
        ),
        z0=50.0,
        label="shack",
    )
    res = fit(
        Builder(), at_shack, ["length_factor", "rs"], engine=RLCEngine,
        npoints=15, fractions=0.3, line=line,
    )  # fmt: skip
    assert res.fitted[0] == pytest.approx(1.04, rel=1e-3)
    assert res.fitted[1] == pytest.approx(70.0, rel=1e-3)
    assert res.rms_fitted < 1e-4


def test_ignoring_the_line_gets_the_antenna_wrong():
    """The counterexample that makes the previous test mean something.

    Note *how* it goes wrong: the line rotates Γ, so the fit can still land the
    resonance roughly right while the feedpoint resistance it infers is badly
    off (here it runs into its bound). That is the shape of the mistake a
    shack-end measurement fitted at the feedpoint plane actually makes.
    """
    line = LineEmbedding.from_cable("RG-213", 20.0)
    truth = synth_measurement(length_factor=1.04, rs=70.0)
    at_shack = MeasuredTrace(
        freqs=truth.freqs,
        gamma=(lambda z: (z - 50.0) / (z + 50.0))(
            line.embed(truth.impedance, truth.freqs)
        ),
        z0=50.0,
        label="shack",
    )
    res = fit(
        Builder(), at_shack, ["length_factor", "rs"], engine=RLCEngine,
        npoints=15, fractions=0.3,
    )  # fmt: skip
    assert res.fitted[1] != pytest.approx(70.0, rel=1e-2)
    assert res.at_bound  # it hits a bound reaching for an explanation
    assert res.rms_fitted > 0.05


def test_line_spec_parsing():
    assert LineEmbedding.parse("RG-8X:12.5").length_m == 12.5
    assert LineEmbedding.parse("RG-8X:12.5").vf == 0.80
    with pytest.raises(ValueError, match="cable"):
        LineEmbedding.parse("RG-8X")
    with pytest.raises(KeyError, match="unknown cable"):
        LineEmbedding.parse("RG-999:10")


# ---------------------------------------------------------------------------
# reporting & plotting
# ---------------------------------------------------------------------------
def test_report_names_the_shift_and_the_residual():
    meas = synth_measurement(length_factor=1.05)
    res = fit(Builder(), meas, ["length_factor"], engine=RLCEngine, npoints=9,
              fractions=0.2)  # fmt: skip
    text = res.report()
    assert "length_factor" in text
    assert "RMS |ΔΓ|" in text
    assert f"{res.rms_fitted:.4f}" in text


def test_large_residual_is_called_out():
    """A measurement the model can't reproduce must not read as a good fit."""
    meas = synth_measurement()
    # Nothing like the model: a flat 200 Ω load across the band.
    meas = MeasuredTrace(
        freqs=meas.freqs,
        gamma=np.full(meas.freqs.shape, (200 - 50) / (200 + 50) + 0j),
        z0=50.0,
    )
    res = fit(Builder(), meas, ["length_factor"], engine=RLCEngine, npoints=9)
    assert res.rms_fitted > 0.05
    assert "large residual" in res.report()


def test_plot_fit_draws(tmp_path):
    meas = synth_measurement(length_factor=1.02)
    res = fit(Builder(), meas, ["length_factor"], engine=RLCEngine, npoints=9)
    out = tmp_path / "fit.png"
    plot_fit(res, fn=str(out))
    assert out.stat().st_size > 0


def test_fit_result_is_reusable_without_an_optimizer_run():
    """FitResult's numbers are derived, so a hand-built one still reports."""
    f = np.array([14.0, 14.1])
    g = np.array([0.1 + 0j, 0.1 + 0j])
    res = FitResult(
        names=("x",), nominal=(1.0,), fitted=(1.1,), bounds=((0.9, 1.2),),
        freqs=f, gamma_measured=g, gamma_nominal=g + 0.2, gamma_fitted=g + 0.01,
        z0=50.0, builder=None,
    )  # fmt: skip
    assert res.rms_nominal == pytest.approx(0.2)
    assert res.rms_fitted == pytest.approx(0.01)
    assert res.at_bound == ()


# ---------------------------------------------------------------------------
# the real engine, end to end
# ---------------------------------------------------------------------------
@pytest.fixture
def invvee_s1p(tmp_path):
    """A 'measurement' of an inverted-V built 2.5% longer than the design."""
    from antennaknobs.designs.dipoles.invvee import Builder as InvVee
    from antennaknobs.engines import MomwireEngine

    b = InvVee()
    b.length_factor = b.length_factor * 1.025
    freqs = np.linspace(27.5, 29.5, 9)
    z = MomwireEngine(b).impedance_sweep(freqs)[:, 0]
    g = (z - 50.0) / (z + 50.0)
    p = tmp_path / "asbuilt.s1p"
    p.write_text(
        "# MHZ S RI R 50\n"
        + "\n".join(f"{f:.6f} {v.real:.9f} {v.imag:.9f}" for f, v in zip(freqs, g))
        + "\n"
    )
    return p


def test_momwire_fit_recovers_an_as_built_length(invvee_s1p):
    from antennaknobs.designs.dipoles.invvee import Builder as InvVee
    from antennaknobs.engines import MomwireEngine
    from antennaknobs.measured import read_measured

    nominal = InvVee().length_factor
    res = fit(
        InvVee(), read_measured(invvee_s1p), ["length_factor"], npoints=7,
        fractions=0.1, engine=MomwireEngine,
    )  # fmt: skip
    assert res.fitted[0] == pytest.approx(nominal * 1.025, rel=2e-3)
    assert res.rms_fitted < 1e-3


def test_cli_fit(invvee_s1p, tmp_path):
    out = tmp_path / "fit.png"
    ant.cli(
        f"fit --builder dipoles.invvee --measured {invvee_s1p} "
        f"--params length_factor --npoints 5 --fn {out}".split()
    )
    assert out.stat().st_size > 0


def test_cli_fit_rejects_a_bad_invocation(invvee_s1p):
    with pytest.raises(SystemExit, match="--plane station needs --line"):
        ant.cli(
            f"fit --builder dipoles.invvee --measured {invvee_s1p} "
            "--params length_factor --plane station --no_plot".split()
        )
    with pytest.raises(SystemExit, match="lo hi"):
        ant.cli(
            f"fit --builder dipoles.invvee --measured {invvee_s1p} "
            "--params length_factor --bounds 0.9 --no_plot".split()
        )
    with pytest.raises(SystemExit, match="identify"):
        ant.cli(
            f"fit --builder dipoles.invvee --measured {invvee_s1p} "
            "--params a b c d e --no_plot".split()
        )
