"""SimNEC import defects on AC6LA's files (AK#1679, QRZ 1003328 #140-#144).

The fixtures are Dan's own circuits (see ``fixtures/simnec_ac6la_1679``):
``snBydipole1-LC1.ssn``, the back-yard dipole behind a self-tuning XMATCH, and
``Bydipole-TL-Xfmr-CLC.ssn``, the same dipole fed through 100 ft of lossy line,
a compensating series Z, an ideal 1:4 transformer and a CLC high-pass T.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest
from momwire.networks._reduce import C_LIGHT, tl_abcd

from antennaknobs.file_designs import builder_from_file
from antennaknobs.network import TL
from antennaknobs.simnec_import import parse_ssn

FIX = Path(__file__).parent / "fixtures" / "simnec_ac6la_1679"
LC1 = FIX / "snBydipole1-LC1.ssn"
CLC = FIX / "Bydipole-TL-Xfmr-CLC.ssn"


def _parse(path: Path, text: str | None = None):
    return parse_ssn(text or path.read_text(), name=path.name, network=True)


# --- the Generator's sweep expression ----------------------------------------


def test_the_generator_sweep_expression_sets_the_measurement_range():
    """Dan's Generator sweeps ``log = expr`` with ``14 : 14.35 : 0.025``; the
    stale 1-30 MHz ``from``/``to`` next to it are not what SimNEC sweeps, and
    reading them spread the measurement dial over 1-30 MHz."""
    c = _parse(LC1)
    assert c.sweep == pytest.approx((14.0, 14.35))
    assert len(c.sweep_points) == 15
    assert c.sweep_points[1] - c.sweep_points[0] == pytest.approx(0.025)
    assert c.sweep_note is None

    ui = builder_from_file(str(LC1)).default_params["ui_params"]
    assert ui["meas_freq_range"] == pytest.approx((14.0, 14.35))


@pytest.mark.parametrize(
    ("expr", "points"),
    [
        ("14 : 14.35 : 0.025", 15),
        ("1:30:1", 30),
        # the manual's logStep example: the ends, plus every value whose
        # log10 is a multiple of 0.1 in between
        ("1.1:2.2:logStep .1", 5),
        # several ranges, a {}-plotted one, and a single point
        ("7:7.3:.05 {14:14.35:.1} 21.2", 12),
    ],
)
def test_sweep_expressions_follow_the_manual_grammar(expr, points):
    text = LC1.read_text().replace("14 : 14.35 : 0.025", expr)
    assert len(_parse(LC1, text).sweep_points) == points


def test_log_and_lin_spacing_are_honoured():
    base = LC1.read_text().replace(
        "<p><n>log</n><v>expr</v></p>\n"
        "                           <p><n>doSweep</n><v>y</v></p>",
        "<p><n>log</n><v>SPACING</v></p>\n"
        "                           <p><n>doSweep</n><v>y</v></p>",
    )
    assert "SPACING" in base
    lin = _parse(LC1, base.replace("SPACING", "lin"))
    log = _parse(LC1, base.replace("SPACING", "log"))
    for c in (lin, log):
        assert c.sweep == pytest.approx((1.0, 30.0))
        assert len(c.sweep_points) == 100
    assert lin.sweep_points[1] - lin.sweep_points[0] == pytest.approx(29 / 99)
    assert log.sweep_points[1] / log.sweep_points[0] == pytest.approx(30 ** (1 / 99))


def test_an_unreadable_sweep_expression_is_said_not_guessed():
    """``Vary`` spans a SimNEC preference the file does not carry."""
    c = _parse(LC1, LC1.read_text().replace("14 : 14.35 : 0.025", "Vary"))
    assert c.sweep is None and c.sweep_points is None
    assert "'Vary' was not read" in c.skipped_note()


# --- the 'simplified' line model's loss --------------------------------------


def _without_r1(text: str) -> str:
    """Dan's CLC circuit with its SERIES_Z R1 deleted: the variant he could
    import before AK#1679, and the reference the R1 import is checked
    against."""
    out, n = re.subn(
        r"<element>\s*<type>SERIES_Z</type>.*?</element>\s*", "", text, flags=re.S
    )
    assert n == 1
    return out


def _matched_loss_db(tl, f_mhz: float) -> float:
    a, b, _c, _d = tl_abcd(
        tl.z0, tl.length, C_LIGHT / (f_mhz * 1e6), tl.vf, tl.k1, tl.k2
    )
    return 20.0 * math.log10(abs(a + b / tl.z0))


def _line(text: str):
    net = _parse(CLC, _without_r1(text)).network()
    (tl,) = [b for b in net.branches if isinstance(b, TL)]
    return tl


def test_the_simplified_line_loss_is_exact_at_its_quoted_frequency():
    """T1 is 100 ft of 50 ohm line in SimNEC's default 'simplified' model,
    0.5 dB/100 ft at 14.175 MHz, with k0 = k1 = k2 = 0 stored beside it. It
    imported LOSSLESS, with no warning. The model scales its one loss point
    with sqrt(f) (SimNEC's k1), so the line's matched loss is 0.5 dB at
    14.175 MHz and 0.5*sqrt(2) dB at twice that."""
    tl = _line(CLC.read_text())
    assert tl.k2 == 0.0
    assert tl.k1 == pytest.approx(0.5 / math.sqrt(14.175))
    assert _matched_loss_db(tl, 14.175) == pytest.approx(0.5, rel=1e-12)
    assert _matched_loss_db(tl, 28.35) == pytest.approx(0.5 * math.sqrt(2), rel=1e-12)


def test_a_simplified_loss_per_100_metres_is_converted():
    text = CLC.read_text().replace("<n>/100f</n>", "<n>/100m</n>")
    tl = _line(text)
    assert _matched_loss_db(tl, 14.175) == pytest.approx(0.5 * 0.3048, rel=1e-12)


def test_an_untranslated_line_model_is_refused_by_name():
    text = CLC.read_text().replace(
        "<p><n>Mdl</n><v>simplified</v></p>", "<p><n>Mdl</n><v>RG-213</v></p>"
    )
    assert "RG-213" in text
    with pytest.raises(ValueError, match="line model 'RG-213' is not translated"):
        _line(text)
