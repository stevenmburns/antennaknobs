"""Measured-data overlay: the VNA `.s1p` as a reference trace (issue #595).

Three layers: the trace itself (parsing, reference renormalization, derived
R/X/SWR), grid alignment against a sweep band (interpolation, partial overlap,
disjoint bands), and the CLI wiring that draws it on each chart form.
"""

import numpy as np
import pytest

import antennaknobs as ant
from antennaknobs.measured import BandOverlapError, MeasuredTrace, read_measured
from antennaknobs.sweep import _align_measured
from antennaknobs.touchstone import parse_touchstone


def gamma_of(z, z0=50.0):
    return (z - z0) / (z + z0)


def write_s1p(tmp_path, freqs_mhz, zs, *, z0=50.0, name="meas.s1p"):
    """A synthetic RI-format .s1p for impedances ``zs`` at ``freqs_mhz``."""
    g = gamma_of(np.asarray(zs, dtype=complex), z0)
    lines = [f"# MHZ S RI R {z0:g}"]
    lines += [
        f"{f:.6f} {v.real:.9f} {v.imag:.9f}" for f, v in zip(freqs_mhz, g, strict=True)
    ]
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n")
    return p


# ---------------------------------------------------------------------------
# the trace
# ---------------------------------------------------------------------------
def test_reads_s1p_into_mhz_grid_and_impedance(tmp_path):
    freqs = [14.0, 14.1, 14.2]
    zs = [40 - 30j, 50 + 0j, 60 + 25j]
    trace = read_measured(write_s1p(tmp_path, freqs, zs))

    assert trace.label == "meas"  # file stem
    assert trace.z0 == 50.0
    np.testing.assert_allclose(trace.freqs, freqs)  # Hz in the file → MHz here
    np.testing.assert_allclose(trace.impedance, zs, atol=1e-7)


def test_z_parameter_file_converts_to_reflection(tmp_path):
    """An .s1p written as R+jX overlays exactly like one written as S11."""
    freqs, zs = [14.0, 14.2], [40 - 30j, 60 + 25j]
    text = "# MHZ Z RI R 50\n" + "\n".join(
        f"{f} {z.real} {z.imag}" for f, z in zip(freqs, zs, strict=True)
    )
    trace = MeasuredTrace.from_touchstone(parse_touchstone(text, nports=1))
    np.testing.assert_allclose(trace.gamma, gamma_of(np.array(zs)), atol=1e-12)


def test_renormalizing_preserves_impedance(tmp_path):
    """Γ is reference-dependent; the impedance it stands for is not."""
    zs = [40 - 30j, 60 + 25j]
    trace = read_measured(write_s1p(tmp_path, [14.0, 14.2], zs, z0=75.0), z0=50.0)

    assert trace.z0 == 50.0
    np.testing.assert_allclose(trace.gamma, gamma_of(np.array(zs), 50.0), atol=1e-7)
    np.testing.assert_allclose(trace.impedance, zs, atol=1e-6)
    # A 75 Ω file drawn against a 50 Ω chart is a different curve — the
    # renormalization is not cosmetic.
    raw = read_measured(write_s1p(tmp_path, [14.0, 14.2], zs, z0=75.0))
    assert not np.allclose(raw.gamma, trace.gamma)


def test_renormalizing_to_the_same_reference_is_identity(tmp_path):
    trace = read_measured(write_s1p(tmp_path, [14.0, 14.2], [40 - 30j, 60 + 25j]))
    assert trace.renormalized(50.0) is trace


def test_swr_clamps_a_unit_magnitude_measurement():
    """|Γ| ≥ 1 happens on noisy near-open measurements; it must not divide by 0."""
    trace = MeasuredTrace(
        freqs=np.array([14.0, 14.1]), gamma=np.array([1.0 + 0j, 1.02 + 0j]), z0=50.0
    )
    swr = trace.swr
    assert np.all(np.isfinite(swr)) and np.all(swr > 1e6)


def test_s2p_is_rejected_as_an_overlay(tmp_path):
    p = tmp_path / "balun.s2p"
    p.write_text("# MHZ S RI R 50\n14.0 0 0 1 0 1 0 0 0\n")
    with pytest.raises(ValueError, match="1-port"):
        read_measured(p)


def test_unknown_extension_is_rejected(tmp_path):
    p = tmp_path / "sweep.csv"
    p.write_text("14.0 0 0\n")
    with pytest.raises(ValueError, match="s1p"):
        read_measured(p)


# ---------------------------------------------------------------------------
# alignment onto the sweep grid
# ---------------------------------------------------------------------------
def test_align_interpolates_onto_the_sweep_grid(tmp_path):
    trace = read_measured(write_s1p(tmp_path, [14.0, 14.2], [50 + 0j, 50 + 20j]))
    xs, gamma = trace.align(np.array([14.0, 14.1, 14.2]))

    np.testing.assert_allclose(xs, [14.0, 14.1, 14.2])
    # Linear in the complex plane between the two measured points.
    np.testing.assert_allclose(gamma[1], 0.5 * (trace.gamma[0] + trace.gamma[1]))


def test_align_clips_to_the_overlap(tmp_path):
    """A single-band measurement against a wide sweep draws over its own band."""
    trace = read_measured(write_s1p(tmp_path, [14.0, 14.35], [50 + 0j, 50 + 20j]))
    xs, gamma = trace.align(np.linspace(10.0, 30.0, 21))  # 1 MHz steps

    np.testing.assert_allclose(xs, [14.0])
    assert gamma.shape == (1,)


def test_align_errors_on_disjoint_bands(tmp_path):
    trace = read_measured(write_s1p(tmp_path, [14.0, 14.35], [50 + 0j, 50 + 20j]))
    with pytest.raises(BandOverlapError, match="does not overlap"):
        trace.align(np.linspace(28.0, 29.0, 11))


def test_measured_needs_a_frequency_sweep(tmp_path):
    trace = read_measured(write_s1p(tmp_path, [14.0, 14.2], [50 + 0j, 50 + 20j]))
    with pytest.raises(ValueError, match="frequency data"):
        _align_measured(trace, "length_top", np.linspace(1.0, 2.0, 5), 50.0)
    # ...and is a no-op when absent, whatever the swept knob.
    assert _align_measured(None, "length_top", np.linspace(1.0, 2.0, 5), 50.0) is None


def test_align_renormalizes_through_the_chart_reference(tmp_path):
    """The chart's z0, not the file's, decides the Γ that gets drawn."""
    zs = [40 - 30j, 60 + 25j]
    trace = read_measured(write_s1p(tmp_path, [14.0, 14.2], zs, z0=75.0))
    _, gamma = _align_measured(trace, "freq", np.array([14.0, 14.2]), 50.0)
    np.testing.assert_allclose(gamma, gamma_of(np.array(zs), 50.0), atol=1e-7)


# ---------------------------------------------------------------------------
# CLI wiring — one smoke run per chart form
# ---------------------------------------------------------------------------
@pytest.fixture
def measured_10m(tmp_path):
    """A plausible 10 m measured sweep spanning part of the default band."""
    freqs = np.linspace(28.0, 29.0, 11)
    zs = 45.0 + 1j * np.linspace(-40.0, 40.0, 11)
    return str(write_s1p(tmp_path, freqs, zs, name="bench_10m.s1p"))


@pytest.mark.parametrize("chart", ["--swr", "--use_smithchart", ""])
def test_cli_sweep_draws_the_overlay(measured_10m, chart):
    args = f"sweep --param freq --range 28.2 28.8 --npoints 3 --z0 50 {chart}"
    ant.cli(f"{args} --measured {measured_10m} --fn /dev/null".split())


def test_cli_sweep_measured_rejects_gain_and_patterns(measured_10m):
    for flag in ("--gain", "--patterns"):
        with pytest.raises(SystemExit, match="impedance/SWR"):
            ant.cli(
                f"sweep {flag} --npoints 2 --measured {measured_10m} "
                "--fn /dev/null".split()
            )


def test_cli_sweep_measured_disjoint_band_is_a_clear_error(measured_10m):
    with pytest.raises(BandOverlapError, match="does not overlap"):
        ant.cli(
            f"sweep --swr --param freq --range 14.0 14.3 --npoints 3 "
            f"--measured {measured_10m} --fn /dev/null".split()
        )
