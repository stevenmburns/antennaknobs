"""SimNEC ``.ssn`` forms a user's files carry that the import refused.

- A Generator ``MHz`` holding several frequencies (``3.55 14.05 21.1 28.3``):
  SimNEC solves at the last and marks every one; the design opens at the last
  and offers each as a band.

Every fixture is synthetic.
"""

from __future__ import annotations

import pytest
from test_simnec_import import _SCRIPT_M, _ssn

from antennaknobs.file_designs import builder_from_text
from antennaknobs.simnec_import import parse_ssn, parse_ssn_station


def _with_mhz(text: str, mhz: str) -> str:
    """``text`` (an `_ssn` circuit) with its Generator's MHz written ``mhz``."""
    old = "<p><n>MHz</n><v>7.1</v></p>"
    assert text.count(old) == 1
    return text.replace(old, f"<p><n>MHz</n><v>{mhz}</v></p>")


# --- a Generator MHz list ---------------------------------------------------


def test_a_generator_mhz_list_solves_at_its_last_frequency_and_keeps_them_all():
    text = _with_mhz(_ssn(_SCRIPT_M), "3.55 14.05 21.1 28.3")
    c = parse_ssn(text)
    assert c.freq_mhz == 28.3
    assert c.freqs == (3.55, 14.05, 21.1, 28.3)
    assert parse_ssn_station(text).freqs == c.freqs
    assert parse_ssn_station(text).freq_mhz == 28.3


def test_a_listed_design_opens_at_the_last_and_offers_each_as_a_band():
    B = builder_from_text(
        "multi.ssn", _with_mhz(_ssn(_SCRIPT_M), "3.55 14.05 21.1 28.3")
    )
    assert B.default_params["freq"] == 28.3 == B.default_params["design_freq"]
    assert B().operating_bands() == [
        ("3.55 MHz", 3.55),
        ("14.05 MHz", 14.05),
        ("21.1 MHz", 21.1),
        ("28.3 MHz", 28.3),
    ]
    assert "lists 4 frequencies" in B.default_params["ui_params"]["notes"]


def test_one_generator_frequency_is_read_as_before_with_no_bands():
    text = _ssn(_SCRIPT_M)
    c = parse_ssn(text)
    assert (c.freq_mhz, c.freqs) == (7.1, (7.1,))
    B = builder_from_text("one.ssn", text)
    assert B.default_params["freq"] == 7.1
    assert not hasattr(B, "operating_bands")


def test_a_list_with_a_word_in_it_is_refused_by_name():
    with pytest.raises(ValueError, match=r"bad GENERATOR MHz '3\.55 abc'"):
        parse_ssn(_with_mhz(_ssn(_SCRIPT_M), "3.55 abc"))
