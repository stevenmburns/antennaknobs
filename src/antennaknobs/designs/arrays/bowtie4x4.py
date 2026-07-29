"""4x4 broadside bowtie panel — sixteen identical bowtie elements on a regular
y-z grid, each fed in phase.

The catalog's showcase for the paired geometry+network hierarchy (`Module` /
`lattice`). One bowtie element is described once as a `Module` — its geometry
`Cell` plus a single `PortOnWire` feed — and `lattice()` stamps it on a
centroid-centered 4x4 grid with pure-translation poses. `expand_modules()`
namespaces each element's feed to ``"e{i}_{j}.feed"`` on BOTH faces at once, so
the wire the geometry emits and the port `build_network()` drives are the same
name by construction (no hand-typed per-element strings, the failure mode the
older array designs court).

Sixteen identical, uniformly-spaced elements is exactly the structure momwire's
lattice-FFT coupling operator recognizes (P >= 16, one shape class): solve it
through `ArrayBlockSolver` and the block-Toeplitz/FFT path engages
automatically. The default engine still uses the dense B-spline solver; the FFT
path is opt-in via ``solver_kwargs``.

All sixteen feeds are driven at unit amplitude and zero relative phase
(broadside); `impedance()` returns the sixteen per-element driving-point values.
"""

from types import MappingProxyType

from antennaknobs import (
    AntennaBuilder,
    Cell,
    Module,
    expand_modules,
    lattice,
)
from antennaknobs.designs.specialty import bowtie
from antennaknobs.network import Driven, Network, PortOnWire

#: Fixed grid — the name says 4x4, and 16 elements is the lattice-FFT floor.
_NX, _NZ = 4, 4

#: The namespaced feed-port names lattice() produces (instance "e{i}_{j}" +
#: formal feed "feed"). Declared to the web UI as ``ui_params["feed_ports"]``
#: so all sixteen feed markers render — build_network() designs don't infer
#: feed topology, they trust this list (adapter._declared_feed_ports).
_FEED_PORTS = tuple(f"e{i}_{j}.feed" for i in range(_NX) for j in range(_NZ))


class Builder(AntennaBuilder):
    NX = _NX
    NZ = _NZ

    default_params = MappingProxyType(
        {
            "freq": 28.47,
            # Geometry is hand-tuned in absolute metres (inherited from the
            # bowtie element); design_freq only anchors auto_mesh's density.
            "design_freq": 28.47,
            "angle_deg": 28.2625,  # bowtie arm droop
            "length": 5.4213,  # bowtie half-span
            "base": 9.0,  # element height (z of the fan centre)
            "del_y": 4.0,  # column spacing along y
            "del_z": 4.0,  # row spacing along z
            "ui_params": MappingProxyType(
                {"design_freq": {"hidden": True}, "feed_ports": _FEED_PORTS}
            ),
        }
    )

    def _element_module(self):
        # One bowtie element, meshed at this array's density, with its feed
        # edge named and its inline excitation dropped (the port drives it).
        elem_params = dict(bowtie.Builder.default_params)
        elem_params.update(
            freq=self.freq,
            design_freq=self.design_freq,
            angle_deg=self.angle_deg,
            length=self.length,
            base=self.base,
        )
        for k in self.FRAMEWORK_PARAMS:
            if k in self._params:
                elem_params[k] = self._params[k]

        wires = [
            w._replace(name="feed", ex=None) if w.ex is not None else w
            for w in bowtie.Builder(elem_params).build_wires()
        ]
        return Module(
            cell=Cell(feeds=("feed",), wires=wires),
            ports={"feed": PortOnWire("feed")},
        )

    def _elements(self):
        return lattice(
            self._element_module(),
            nx=self.NX,
            nz=self.NZ,
            dy=self.del_y,
            dz=self.del_z,
        )

    def build_wires(self):
        return expand_modules(self._elements()).wires

    def build_network(self):
        a = expand_modules(self._elements())
        return Network(
            ports=a.ports,
            branches=a.branches,
            sources=[Driven(port=f, voltage=1 + 0j) for f in a.feeds],
        )
