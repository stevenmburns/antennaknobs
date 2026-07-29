"""16-element linear bowtie array — sixteen identical bowtie elements on a
single row (constant height), each fed in phase.

Same Module/lattice construction as `arrays.bowtie4x4`, but where that panel
stacks elements across 4 heights (nz=4) — which splits momwire's block-shape
classes by height under ANY ground model and drops the lattice-FFT coupling
path (array_block.py's height-refined shape classes; see issue #613) — this
array keeps every element at the SAME height (nz=1): one geometric shape, one
height, one block-shape class, always. The FFT lattice path engages in free
space AND stays engaged over ground (issue #613's other worked case: a
same-height array keeps the fast path even over Sommerfeld ground).

Sixteen identical, uniformly-spaced elements on a regular row is exactly the
structure momwire's lattice-FFT coupling operator recognizes (P >= 16, one
shape class): solve it through `ArrayBlockSolver` and the block-Toeplitz/FFT
path engages automatically, ground or no ground. The default engine still
uses the dense B-spline solver; the FFT path is opt-in via `solver_kwargs`.

All sixteen feeds are driven at unit amplitude and zero relative phase
(broadside); `impedance()` returns the sixteen per-element driving-point
values.
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

#: Fixed row — the name says 16x1, and 16 elements is the lattice-FFT floor.
_NX, _NZ = 16, 1

#: The namespaced feed-port names lattice() produces (instance "e{i}_0" +
#: formal feed "feed"). Declared to the web UI as ``ui_params["feed_ports"]``
#: so all sixteen feed markers render — build_network() designs don't infer
#: feed topology, they trust this list (adapter._declared_feed_ports).
_FEED_PORTS = tuple(f"e{i}_0.feed" for i in range(_NX))


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
            "base": 9.0,  # element height (z of the fan centre) — same for every element
            "del_y": 4.0,  # element spacing along the row
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
        # Single row (nz=1): every element lands at the same z regardless of
        # dz, so it's passed as 0.0 rather than exposed as a knob.
        return lattice(
            self._element_module(),
            nx=self.NX,
            nz=self.NZ,
            dy=self.del_y,
            dz=0.0,
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
