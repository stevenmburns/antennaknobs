"""AK#2342: a PyNECEngine solved twice answers the second solve, not the first.

PyNEC numbers its results per context across every run made on it, so a
reader that indexed from 0 read the first run's rows: a second sweep on the
same engine returned the first sweep's impedances. Every comparison here is
against a FRESH engine at the second frequency, which has only the one run, so
it cannot share the bug it is checking for.
"""

import numpy as np
import pytest

pytest.importorskip("PyNEC")

from antennaknobs.cli import get_builder  # noqa: E402
from antennaknobs.engines import PyNECEngine  # noqa: E402

DESIGN = "dipoles.folded_invvee"  # the deck the corpus study caught it on


def engine(freq=None):
    b = get_builder(DESIGN)()
    if freq is not None:
        b.freq = freq
    return PyNECEngine(b, ground="free")


def test_a_second_sweep_answers_its_own_frequencies():
    first, second = [28.0, 28.1], [29.6, 29.7]
    e = engine()
    z1 = e.impedance_sweep(first)
    z2 = e.impedance_sweep(second)
    np.testing.assert_allclose(z2, engine().impedance_sweep(second), rtol=1e-12)
    # and the first sweep read the first frequencies, so the two really differ
    assert not np.allclose(z1, z2)


def test_impedance_after_a_frequency_change():
    e = engine(28.0)
    e.impedance()
    e.builder.freq = 29.7
    np.testing.assert_allclose(e.impedance(), engine(29.7).impedance(), rtol=1e-12)


def test_currents_after_an_impedance_at_another_frequency():
    e = engine(28.0)
    e.impedance()
    e.builder.freq = 29.7
    got = e.current_distribution()
    want = engine(29.7).current_distribution()
    for g, w in zip(got, want, strict=True):
        np.testing.assert_allclose(
            g.knot_currents, w.knot_currents, rtol=1e-12, atol=1e-15
        )


def test_a_second_pattern_is_its_own():
    grid = {"n_theta": 9, "n_phi": 36, "del_theta": 10, "del_phi": 10}
    e = engine(28.0)
    e.far_field(**grid)
    e.builder.freq = 29.7
    got = e.far_field(**grid)
    want = engine(29.7).far_field(**grid)
    np.testing.assert_allclose(got.rings, want.rings, rtol=1e-12)
    assert got.max_gain == pytest.approx(want.max_gain, rel=1e-12)
