"""A named build_wires() wire that no PortOnWire references is rejected at
engine init (issue #578).

The geometry layer registers every named wire as a port edge; on the
reducer path an unreferenced port row is left electrically open, and an
open series gap CUTS the current path at that wire. The failure was silent
and looked like plausible physics (found during #576's validation: a
dipole fed through a physical line read −j46 kΩ — the isolated feed
bridge — because the line's attachment stubs carried names the reference
variant's network didn't use). It is now an init-time ValueError on the
paths where the cut would happen: momwire always (networks always reduce
there), PyNEC on its reducer path (the native-card path places no ex card
for an unreferenced name, so the segment stays plain wire — harmless, and
deliberately not validated).
"""

from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL, Wire

FREQ = 28.47
ARM = 0.24 * 299.792458 / FREQ


class _Dipole(AntennaBuilder):
    """Center-fed dipole; `stray_name` adds a named-but-unreferenced stub."""

    default_params = MappingProxyType(
        {"design_freq": FREQ, "freq": FREQ, "stray_name": None}
    )

    def build_wires(self):
        g = 0.2
        return [
            Wire((0, -ARM, 10.0), (0, -g, 10.0), name=self.stray_name),
            Wire((0, -g, 10.0), (0, g, 10.0), name="feed"),
            Wire((0, g, 10.0), (0, ARM, 10.0)),
        ]

    def build_network(self):
        # A TL stub keeps the network on the reducer path for BOTH engines
        # (PyNEC's native path would not call the reducer, and there an
        # unreferenced name is genuinely harmless).
        return Network(
            ports={
                "feed": PortOnWire("feed", distributed=True),
                "stub": PortVirtual("stub"),
            },
            branches=[TL(a="feed", b="stub", z0=300.0, length=0.01)],
            sources=[Driven(port="stub", voltage=1 + 0j)],
        )


def test_momwire_rejects_orphaned_named_wire():
    from antennaknobs.engines.momwire import MomwireEngine

    with pytest.raises(ValueError, match="issue #578"):
        MomwireEngine(_Dipole(dict(_Dipole.default_params, stray_name="oops")))


def test_pynec_reducer_path_rejects_orphaned_named_wire():
    from antennaknobs.engines.pynec import PyNECEngine

    with pytest.raises(ValueError, match="issue #578"):
        PyNECEngine(_Dipole(dict(_Dipole.default_params, stray_name="oops")))


def test_fully_referenced_names_pass():
    from antennaknobs.engines.momwire import MomwireEngine

    eng = MomwireEngine(_Dipole())
    z = complex(eng.impedance()[0])
    assert z.real > 1.0  # solves; a cut dipole would read as a tiny capacitor
