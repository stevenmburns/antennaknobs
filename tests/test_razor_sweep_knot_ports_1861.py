"""A razor-2p frequency sweep of a design with junction-knot ports (momwire#1861).

momwire's `RazorSolver._port_count` left out node gaps, so the swept Y the
frequency-sweep path builds came back empty (one knot port: the network read
a wrong impedance, silently) or raised (two). The app's SWR curves run that
path; its single-point readout never did. Here a sweep must equal the
single-point solves, frequency by frequency. The fixture is synthetic.
"""

from __future__ import annotations

from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import make_engine_factory
from antennaknobs.network import Driven, Load, Network, PortAtVertex, Wire

FREQS = [13.8, 14.0, 14.2]


class _Knotted(AntennaBuilder):
    """A dipole fed at the knot between its arms; with ``load`` a parallel
    RLC at the knot between the right arm and a tail wire, a second port."""

    default_params = MappingProxyType({"freq": 14.0})
    load = False

    def build_wires(self):
        return [
            Wire((0.0, -5.0, 10.0), (0.0, 0.0, 10.0), 11, name="feed"),
            Wire(
                (0.0, 0.0, 10.0),
                (0.0, 5.0, 10.0),
                11,
                name="arm" if self.load else None,
            ),
            Wire((0.0, 5.0, 10.0), (0.0, 6.0, 10.0), 3),
        ]

    def build_network(self):
        ports = {"feed": PortAtVertex("feed", end="p1")}
        branches = []
        if self.load:
            ports["ld"] = PortAtVertex("arm", end="p1")
            branches.append(Load("ld", r=4150.0, l=26.3e-6, c=4.91e-12, parallel=True))
        return Network(ports=ports, branches=branches, sources=[Driven(port="feed")])


class _KnottedLoad(_Knotted):
    load = True


@pytest.mark.parametrize("cls", [_Knotted, _KnottedLoad], ids=["one-port", "two-ports"])
def test_a_razor_sweep_equals_its_single_point_solves(cls):
    eng = make_engine_factory(
        "momwire:razor-2p", None
    )  # free space: the bug is ports, not ground
    swept = np.asarray(eng(cls()).impedance_sweep(FREQS)).reshape(len(FREQS), -1)[:, 0]
    for f, z in zip(FREQS, swept, strict=True):
        one = complex(eng(cls({"freq": f})).impedance()[0])
        assert z == pytest.approx(one, rel=1e-9), f
