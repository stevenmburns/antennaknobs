"""Measured antenna data as a *reference trace* for the sweep plots (issue #595).

A NanoVNA (or any VNA) exports a one-port Touchstone ``.s1p``: S11 versus
frequency for the antenna as it actually stands in the yard. This module turns
such a file into a :class:`MeasuredTrace` — a frequency-indexed complex
reflection coefficient that the CLI sweeps draw *alongside* the simulated
curve, closing the loop between a design and the bench.

The distinction from ``touchstone.py``'s consumers is one of *use*, not format:
``network.TouchstoneLoad`` makes an ``.s1p`` a **circuit element** inside
``build_network()``; here the same parsed file is **reference data** on the
chart. One parser, two subsystems.

Two pieces of arithmetic carry the feature:

- **Reference renormalization.** The file declares its own ``R <z0>`` (a
  NanoVNA writes 50 Ω, but a 75 Ω or 200 Ω calibration is legal). The plot has
  its own ``--z0``. Comparing raw Γ across differing references is a silent
  error, so a trace is always renormalized through the impedance it represents:
  ``Z = z0_file·(1+Γ)/(1−Γ)`` then ``Γ' = (Z−z0)/(Z+z0)``.
- **Grid alignment.** The measured grid is the VNA's (often hundreds of
  points); the model grid is the sweep's (often ~21). :meth:`MeasuredTrace.align`
  interpolates the measurement onto the sweep grid *restricted to the overlap*,
  so a measurement covering only part of the swept span renders over its own
  band and nothing is extrapolated. No overlap at all is an error, not an empty
  chart.

Comparison happens at whatever plane the chart already plots — normally the
antenna feedpoint, so the VNA should be calibrated at the feedpoint too (a
design whose ``build_network()`` includes a station chain plots the station
plane instead, and a shack-end measurement matches that). Issue #639 makes the
plane an explicit choice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .touchstone import Touchstone, _nports_from_name, parse_touchstone

__all__ = ["MeasuredTrace", "read_measured", "BandOverlapError"]

logger = logging.getLogger(__name__)


class BandOverlapError(ValueError):
    """The measured band and the swept band do not overlap at all."""


@dataclass(frozen=True, eq=False)
class MeasuredTrace:
    """A measured one-port response on its own frequency grid.

    ``freqs`` is MHz ascending (the unit the builders and sweep charts use, not
    the Hz of the Touchstone file); ``gamma`` is the complex reflection
    coefficient referenced to ``z0``; ``label`` names the trace in legends.
    ``eq=False`` for the same reason as :class:`~antennaknobs.touchstone.Touchstone`
    — array fields make value-equality meaningless.
    """

    freqs: np.ndarray
    gamma: np.ndarray
    z0: float
    label: str = "measured"

    @classmethod
    def from_touchstone(
        cls, ts: Touchstone, *, label: str = "measured"
    ) -> "MeasuredTrace":
        """Build from a parsed 1-port :class:`Touchstone`.

        Y- and Z-parameter files convert through ``s_at`` (evaluated at the
        file's own grid points, where the interpolation is exact), so an
        ``.s1p`` written as R+jX overlays just like one written as S11.
        """
        if ts.nports != 1:
            raise ValueError(
                f"a measured overlay needs a 1-port (.s1p) file; got {ts.nports} ports"
            )
        if ts.ptype == "S":
            gamma = ts.params[:, 0, 0].copy()
        else:
            gamma = np.array([ts.s_at(float(f))[0, 0] for f in ts.freqs])
        return cls(freqs=ts.freqs / 1e6, gamma=gamma, z0=float(ts.z0), label=label)

    # -- derived views ------------------------------------------------------
    @property
    def impedance(self) -> np.ndarray:
        """Measured impedance (Ω) — ``z0·(1+Γ)/(1−Γ)``."""
        return self.z0 * (1.0 + self.gamma) / (1.0 - self.gamma)

    @property
    def swr(self) -> np.ndarray:
        rho = np.abs(self.gamma)
        # A measurement with |Γ| ≥ 1 (noise, or a bad calibration on a
        # near-open) would divide by zero or go negative; clamp just below 1 so
        # the trace pins at a large SWR instead of exploding the axis.
        rho = np.minimum(rho, 1.0 - 1e-9)
        return (1.0 + rho) / (1.0 - rho)

    def renormalized(self, z0: float) -> "MeasuredTrace":
        """This trace re-referenced to ``z0`` (identity when already there)."""
        if abs(z0 - self.z0) < 1e-12:
            return self
        z = self.impedance
        return MeasuredTrace(
            freqs=self.freqs,
            gamma=(z - z0) / (z + z0),
            z0=float(z0),
            label=self.label,
        )

    # -- alignment onto a sweep grid ---------------------------------------
    def align(self, freqs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Interpolate onto sweep grid ``freqs`` (MHz), clipped to the overlap.

        Returns ``(xs, gamma)`` over the sweep points that fall inside the
        measured span. Raises :class:`BandOverlapError` when the bands are
        disjoint; logs an informational message when the measurement covers the
        swept band only partly (a legitimate and common case — a single-band
        measurement against a multi-band sweep).
        """
        freqs = np.asarray(freqs, dtype=float)
        f0, f1 = float(self.freqs[0]), float(self.freqs[-1])
        tol = 1e-9 * max(abs(f1), 1.0)
        inside = (freqs >= f0 - tol) & (freqs <= f1 + tol)
        if not inside.any():
            raise BandOverlapError(
                f"measured band [{f0:.6g}, {f1:.6g}] MHz does not overlap the "
                f"swept band [{freqs.min():.6g}, {freqs.max():.6g}] MHz — "
                "sweep the measured band, or measure the swept one"
            )
        if not inside.all():
            logger.info(
                "measured trace %r covers %d of %d sweep points "
                "([%.6g, %.6g] MHz of [%.6g, %.6g] MHz); drawing the overlap",
                self.label,
                int(inside.sum()),
                freqs.size,
                f0,
                f1,
                freqs.min(),
                freqs.max(),
            )
        xs = freqs[inside]
        gamma = np.interp(xs, self.freqs, self.gamma.real) + 1j * np.interp(
            xs, self.freqs, self.gamma.imag
        )
        return xs, gamma


def read_measured(
    path, *, z0: float | None = None, label: str | None = None
) -> MeasuredTrace:
    """Read a measured ``.s1p`` from an arbitrary filesystem path.

    This is the CLI/operator entry point: unlike
    :func:`~antennaknobs.touchstone.read_touchstone` — which is confined to a
    *design's* own folder because designs are untrusted code — a measured
    overlay is a file the person at the keyboard names on the command line, so
    an ordinary path is right. ``z0`` renormalizes the trace to the chart's
    reference; ``label`` defaults to the file's stem.
    """
    p = Path(path)
    nports = _nports_from_name(p.name)  # validate the extension before reading
    if nports != 1:
        raise ValueError(
            f"{p.name}: a measured overlay needs a 1-port .s1p file "
            "(a .s2p is a two-port block — see TouchstoneTwoPort)"
        )
    trace = MeasuredTrace.from_touchstone(
        parse_touchstone(p.read_text(), nports=1), label=label or p.stem
    )
    return trace if z0 is None else trace.renormalized(z0)
