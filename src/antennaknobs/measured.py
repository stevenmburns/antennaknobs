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

__all__ = [
    "MeasuredTrace",
    "parse_measured",
    "read_measured",
    "BandOverlapError",
    "RHO_MAX",
]

logger = logging.getLogger(__name__)

# Largest |Γ| the derived impedance/SWR views will evaluate at — see
# MeasuredTrace.impedance. 1 − 1e-9 puts a measured open at ~1e11 Ω: off the
# top of any chart, but finite.
RHO_MAX = 1.0 - 1e-9


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
        """Measured impedance (Ω) — ``z0·(1+Γ)/(1−Γ)``.

        A real measurement can land at or just outside |Γ| = 1 (noise on a
        near-open, an imperfect calibration), where that expression divides by
        zero. The magnitude is clamped a hair inside the unit circle so the
        result stays finite — huge, which is the honest reading of a measured
        open, and JSON-safe for the web overlay, where a bare ``inf`` would
        produce a body the browser refuses to parse.
        """
        g = self.gamma
        rho = np.abs(g)
        over = rho > RHO_MAX
        if over.any():
            g = np.where(over, g * (RHO_MAX / np.maximum(rho, 1e-300)), g)
        return self.z0 * (1.0 + g) / (1.0 - g)

    @property
    def swr(self) -> np.ndarray:
        # Same clamp as `impedance`, for the same reason: |Γ| ≥ 1 would divide
        # by zero or go negative. The trace pins at a large SWR instead.
        rho = np.minimum(np.abs(self.gamma), RHO_MAX)
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


def parse_measured(
    text: str, *, z0: float | None = None, label: str = "measured"
) -> MeasuredTrace:
    """Parse Touchstone ``text`` into a measured overlay trace.

    The port count is *inferred from the data* rather than taken on trust, so a
    two-port file that reached here under a one-port name gets the "needs a
    1-port" error instead of being silently read as three times as many
    frequency points. This is the shared entry point for the web upload
    (``/measured``) and :func:`read_measured`.
    """
    trace = MeasuredTrace.from_touchstone(parse_touchstone(text), label=label)
    return trace if z0 is None else trace.renormalized(z0)


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
    if _nports_from_name(p.name) != 1:  # validate the extension before reading
        raise ValueError(
            f"{p.name}: a measured overlay needs a 1-port .s1p file "
            "(a .s2p is a two-port block — see TouchstoneTwoPort)"
        )
    return parse_measured(p.read_text(), z0=z0, label=label or p.stem)
