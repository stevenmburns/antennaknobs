"""The workbench's momwire ``/sweep`` is built at the request's measurement
frequency, whichever chunk of the sweep it is solving (review of #1967).

The momwire path solves a sweep in chunks, one build each. Each chunk used to
be built at ITS first frequency (``builder.freq = freqs_mhz[0]``). The
solver overrides k per point, so for most designs that is harmless, but a
design whose BUILD reads ``freq`` — here a self-tuning L tuner that tunes at
``freq`` — was rebuilt per chunk at that chunk's first point: it retuned
there, read SWR 1 at the head of every chunk, and drew a curve that depended
on how the sweep was chunked. Built at the measurement frequency, one chunk
or many give the same curve, tuned once at the session's frequency.

The fixture is a small dipole of its own, so the test does not depend on any
catalog design keeping a tuner that tunes at ``freq``.
"""

from __future__ import annotations

from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    Driven,
    Instance,
    Network,
    PortOnWire,
    PortVirtual,
    Wire,
)
from antennaknobs.station import l_network_tuner


class _TunesAtFreq(AntennaBuilder):
    """A 14 MHz dipole, cut long, behind an L tuner that tunes itself at the
    frequency it is BUILT at: its network genuinely depends on ``freq``."""

    default_params = MappingProxyType(
        {
            "freq": 14.1,
            "design_freq": 14.1,
            "length_m": 11.5,
            "height_m": 10.0,
            "ui_params": MappingProxyType({"target_z0": 50.0}),
        }
    )

    def build_wires(self):
        a = 0.5 * self.length_m
        return self.auto_mesh(
            [Wire((0.0, -a, self.height_m), (0.0, a, self.height_m), name="feed")]
        )

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
            branches=[
                Instance(
                    "tuner",
                    l_network_tuner(
                        tune_to=50.0, tune_at_mhz=float(self.freq), shunt_at="auto"
                    ),
                    rig="rig",
                    out="feed",
                )
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )


def _swr(z, z0=50.0):
    g = abs((z - z0) / (z + z0))
    return (1 + g) / (1 - g)


SESSION = {"geometry": "test.tunes_at_freq", "measurement_freq_mhz": 14.1}
#: 14.1 MHz is index 5: the session's frequency, mid-sweep.
SWEEP = [round(13.85 + 0.05 * i, 4) for i in range(11)]


@pytest.fixture(scope="module")
def example():
    import antennaknobs.web.examples  # noqa: F401 — primes the adapter
    from antennaknobs.web.adapter import _make_example

    return _make_example("test.tunes_at_freq", _TunesAtFreq, defer_hints=True)


def test_the_fixture_build_depends_on_freq():
    """The precondition: without it the chunking test below measures
    nothing. Built at two frequencies, the tuner tunes at each."""
    from antennaknobs.auto_match import find_tuners

    b = _TunesAtFreq()
    for f in (14.1, 14.3):
        b.freq = f
        (t,) = find_tuners(b.build_network())
        assert t.mechanism.f_mhz == f


def test_the_sweep_does_not_depend_on_its_chunking(example):
    re, im = example.momwire_sweep(SESSION, SWEEP)
    whole = np.array(re) + 1j * np.array(im)
    parts = []
    for i in range(0, len(SWEEP), 3):
        r, m = example.momwire_sweep(SESSION, SWEEP[i : i + 3])
        parts += list(np.array(r) + 1j * np.array(m))
    assert np.array(parts) == pytest.approx(whole, rel=1e-9)
    # Tuned once, at the session's frequency: SWR 1 there and only there.
    swr = [_swr(z) for z in whole]
    assert swr[5] == pytest.approx(1.0, abs=1e-6)
    assert all(s > 1.05 for i, s in enumerate(swr) if i != 5), swr
