"""A multi-source network design's per-feed readout pairs each impedance with
its SOURCE's drive (AK#1636).

AC6LA opened `Cardioidmodnec5.nec` with every built-in solver and got
`ValueError: zip() argument 2 is longer than argument 1`. Library calls were
fine; the crash was the workbench's per-feed readout. It paired the engine's
impedances, one per source, with momwire's `_feeds`, which holds every network
PORT: two sources and two loads, so four entries against two impedances, and
zero-volt placeholders at that, because the network resolves the drive.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import antennaknobs.web.examples  # noqa: F401  registration order
from antennaknobs.file_designs import builder_from_file
from antennaknobs.web.adapter import _make_example, _network_drive_values

CARDIOID = (
    Path(__file__).parent / "fixtures" / "eznec_gyrator_1595" / "Cardioidmodnec5.nec"
)


def test_the_cardioid_solves_in_the_workbench_with_its_own_drives():
    cls = builder_from_file(str(CARDIOID))
    ex = _make_example("Cardioidmodnec5", cls)
    f = cls().freq
    out = ex.momwire_solve(
        {
            "measurement_freq_mhz": f,
            "design_freq_mhz": f,
            "ground": True,
            "ground_model": "pec",
        }
    )
    feeds = out["feeds"]
    assert len(feeds) == 2
    # The deck's two `EX 4` current sources: 1.414 A at 0 deg and at -90 deg.
    drives = [complex(r["v_re"], r["v_im"]) for r in feeds]
    assert drives == [pytest.approx(1.414214), pytest.approx(-1.414214j)]
    # Each paired with its own impedance, in source order.
    assert feeds[0]["z_re"] == pytest.approx(32.88, rel=1e-2)
    assert feeds[1]["z_re"] == pytest.approx(65.49, rel=1e-2)


def test_the_drives_come_from_the_sources_not_the_ports():
    class _Eng:
        pass

    cls = builder_from_file(str(CARDIOID))
    eng = _Eng()
    eng.builder = cls()
    net = eng.builder.build_network()
    assert len(net.ports) == 4 and len(net.sources) == 2
    assert _network_drive_values(eng) == [1.414214 + 0j, -1.414214j]


def test_a_design_without_a_network_has_no_network_drives():
    class _Eng:
        _network = None
        builder = None

    assert _network_drive_values(_Eng()) == []
