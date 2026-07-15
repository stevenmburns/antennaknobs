import logging
from abc import ABC, abstractmethod
from typing import ClassVar, Literal, NamedTuple

import numpy as np

from .network import Wire, as_wire

_logger = logging.getLogger(__name__)

SegmentParity = Literal["odd", "even", "any"]


class FarField(NamedTuple):
    rings: list
    max_gain: float
    min_gain: float
    thetas: np.ndarray
    phis: np.ndarray


class WireCurrents(NamedTuple):
    """Per-wire knot positions + complex currents at the solve frequency.

    Engines decompose geometry differently — MomwireEngine returns one
    entry per polyline (post-translator), PyNECEngine returns one entry
    per build_wires() tuple. Callers (e.g. the web UI) treat each entry
    as an independent rendering primitive rather than assuming the lists
    are aligned across engines.
    """

    knot_positions: np.ndarray  # (M, 3) float
    knot_currents: np.ndarray  # (M,)   complex


class SimulationEngine(ABC):
    supports_far_field: ClassVar[bool] = False
    # Engines that demand a specific basis parity override this. The
    # geometry loader bumps any incoming n_seg up to the next valid value
    # (we never bump down — n=0 is invalid). "any" disables coercion.
    segment_parity: ClassVar[SegmentParity] = "any"

    def __init__(self, builder):
        self.builder = builder

    @staticmethod
    def coerce_n_seg(n_seg: int, parity: SegmentParity) -> int:
        # Floor below the parity step. n_seg=0 is invalid for every engine
        # (momwire divides edge length by it), and even-parity engines need
        # at least 2 segments to host a feed straddling a midpoint.
        if parity == "even":
            n_seg = max(2, n_seg)
            return n_seg + 1 if n_seg % 2 == 1 else n_seg
        if parity == "odd":
            n_seg = max(1, n_seg)
            return n_seg + 1 if n_seg % 2 == 0 else n_seg
        return max(1, n_seg)

    def _coerce_wire_tuples(self, tups):
        """Returns the input tuples with each n_seg bumped to the engine's
        required parity. Logs once per distinct (n_in, n_out) shift so a
        converge sweep doesn't spam the log per-edge. Reads
        self.segment_parity so subclasses can set it per-instance (e.g.
        MomwireEngine, where the parity depends on the chosen solver)."""
        parity = self.segment_parity
        if parity == "any":
            return tups
        seen = set()
        out = []
        for t in tups:
            w = as_wire(t)
            n_new = self.coerce_n_seg(w.n_seg, parity)
            if n_new != w.n_seg and (w.n_seg, n_new) not in seen:
                seen.add((w.n_seg, n_new))
                _logger.info(
                    "%s bumped n_seg=%d → %d for %s parity",
                    type(self).__name__,
                    w.n_seg,
                    n_new,
                    parity,
                )
            # Preserve the entry's original shape: plain tuples stay plain
            # (so tests and shape-sensitive callers see what they passed),
            # Wire entries keep name and spec.
            if isinstance(t, Wire) or len(t) == 6:
                out.append(w._replace(n_seg=n_new))
            elif len(t) == 5:
                out.append((w.p0, w.p1, n_new, w.ex, w.name))
            else:
                out.append((w.p0, w.p1, n_new, w.ex))
        return out

    @abstractmethod
    def impedance(self): ...

    @abstractmethod
    def impedance_sweep(self, freqs): ...

    def far_field(self, *, n_theta, n_phi, del_theta, del_phi):
        raise NotImplementedError(
            f"{type(self).__name__} does not support far-field computation"
        )

    def current_distribution(self):
        """Return list[WireCurrents] at the builder's frequency."""
        raise NotImplementedError(f"{type(self).__name__} does not expose currents yet")
