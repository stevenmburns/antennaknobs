"""AntennaBuilder.design_wavelength — the wavelength-fraction scaling helper.

The single named quantity for the ``299.792458 / self.design_freq`` idiom that
wavelength-scaled builders repeat: a free-space wavelength in metres at the
design frequency, sourced from the one exported ``C_LIGHT_MHZ_M`` constant.
Anchored on ``design_freq`` (the frequency the geometry is dimensioned for),
never the measurement ``freq``, so a frequency sweep can never resize the
antenna — the same contract ``auto_mesh`` enforces.
"""

from types import MappingProxyType

import pytest

import antennaknobs
from antennaknobs import AntennaBuilder, C_LIGHT_MHZ_M


class _Design(AntennaBuilder):
    default_params = MappingProxyType({"freq": 21.0, "design_freq": 28.4})


class _NoDesignFreq(AntennaBuilder):
    default_params = MappingProxyType({"freq": 21.0})


def test_constant_is_exported_and_is_c_in_mhz_metres():
    assert antennaknobs.C_LIGHT_MHZ_M == C_LIGHT_MHZ_M
    assert C_LIGHT_MHZ_M == pytest.approx(299.792458)
    # it is the SI speed of light scaled for MHz·metres work
    assert C_LIGHT_MHZ_M * 1e6 == pytest.approx(299_792_458.0)


def test_design_wavelength_is_c_over_design_freq():
    b = _Design()
    assert b.design_wavelength == pytest.approx(C_LIGHT_MHZ_M / 28.4)


def test_scales_on_design_freq_not_measurement_freq():
    """Sweeping the measurement ``freq`` must not move the wavelength the
    geometry scales against — only ``design_freq`` does."""
    b = _Design()
    wl = b.design_wavelength
    b.freq = 7.15  # retune the measurement point
    assert b.design_wavelength == wl
    b.design_freq = 14.2  # halve the design frequency -> double the wavelength
    assert b.design_wavelength == pytest.approx(2.0 * wl)


def test_missing_design_freq_raises():
    b = _NoDesignFreq()
    with pytest.raises(ValueError, match="design_freq"):
        _ = b.design_wavelength
