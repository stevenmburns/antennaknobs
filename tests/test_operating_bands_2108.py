"""A multiband design declares its bands (AK#2108).

`Builder.operating_bands()` -> [(label, freq_mhz), ...], read at the solve's
knobs and served on the solve response as `operating_bands`: the workbench
fills its band list with them and shows each band's Z on the Smith chart.
Designs without the method serve nothing; a malformed declaration refuses by
name. Mike's (WA7ARK) multiband EFHW is the first to declare.
"""

from __future__ import annotations

import pytest

from antennaknobs.web import server  # noqa: F401  (import order: server first)
from antennaknobs.web import adapter
from antennaknobs.web.examples import REGISTRY


def _solve(geometry: str, **kw) -> dict:
    req = {"geometry": geometry, "momwire_model": "bspline", **kw}
    return REGISTRY[geometry].momwire_solve(req)


def test_the_multiband_efhw_declares_its_four_bands():
    out = _solve("wire.efhw_autotransformer")
    assert out["operating_bands"] == [
        {"label": "40 m", "freq_mhz": 7.15},
        {"label": "20 m", "freq_mhz": 14.175},
        {"label": "15 m", "freq_mhz": 21.225},
        {"label": "10 m", "freq_mhz": 28.3},
    ]


def test_a_single_band_design_serves_none():
    assert "operating_bands" not in _solve("dipoles.invvee")


class _Declares:
    def __init__(self, bands):
        self._bands = bands

    def operating_bands(self):
        return self._bands


def test_duplicates_drop_and_the_list_is_capped():
    bands = [("a", 7.1), ("a again", 7.1)] + [(f"b{i}", 10.0 + i) for i in range(10)]
    got = adapter._operating_bands(_Declares(bands))
    assert got[0] == {"label": "a", "freq_mhz": 7.1}
    assert len(got) == 8


@pytest.mark.parametrize(
    "bad", [[("40 m", 0.0)], [("40 m", float("nan"))], [(40, 7.1)]]
)
def test_a_malformed_declaration_refuses_by_name(bad):
    with pytest.raises(ValueError, match="operating_bands"):
        adapter._operating_bands(_Declares(bad))
