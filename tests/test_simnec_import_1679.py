"""SimNEC import defects on AC6LA's files (AK#1679, QRZ 1003328 #140-#144).

The fixtures are Dan's own circuits (see ``fixtures/simnec_ac6la_1679``):
``snBydipole1-LC1.ssn``, the back-yard dipole behind a self-tuning XMATCH, and
``Bydipole-TL-Xfmr-CLC.ssn``, the same dipole fed through 100 ft of lossy line,
a compensating series Z, an ideal 1:4 transformer and a CLC high-pass T.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from antennaknobs.file_designs import builder_from_file
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
