"""A sweep that holds resonance draws R alone on its R/X chart.

Its X is the held quantity, zero by construction, so the trace is the root
finder's residual: a few milliohms autoscaled into what looks like structure
(the two-wire doublet's branches, AK#2037). A multi-band hold or a frequency
sweep leaves X free along the curve and keeps both.
"""

from antennaknobs import analyses as an
from antennaknobs.analysis_run import _held_x_only


def _a(hold):
    return an.Analysis(
        "a", an.Sweep("long_ft", 17.0, 32.0, points=3), hold=hold, views=(an.Rx(),)
    )


def test_a_held_resonance_draws_r_alone():
    a = _a(an.Hold("resonance", adjust=("short_ft",)))
    assert _held_x_only(a, frequency=False) == "r"


def test_no_hold_or_another_objective_keeps_both():
    assert _held_x_only(_a(None), frequency=False) is None
    assert (
        _held_x_only(_a(an.Hold("swr", adjust=("short_ft",))), frequency=False) is None
    )


def test_a_frequency_sweep_keeps_both():
    a = _a(an.Hold("resonance", adjust=("short_ft",)))
    assert _held_x_only(a, frequency=True) is None
