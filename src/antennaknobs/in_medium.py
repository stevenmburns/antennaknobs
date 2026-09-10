"""Currents below the interface in a far-field readout (issue #1341).

Both far-field readouts in this package — `MomwireEngine.far_field` (the
grid behind the compare table and the CLI plots) and the web server's
`_mag2_at_directions` (the polar-chart cuts) — build the pattern from every
solved segment's current moment through the above-ground formula: a PEC
image mirrored in the ground plane, then Fresnel reflection on the image
wave. That formula is the far field of a current ABOVE the interface. The
far field above ground of a current INSIDE the medium is the transmitted
field, refracted at the boundary and attenuated through the soil, and its
stationary-phase form is momwire#570 — not written. Neither readout ever
looked at which side of the plane a segment was on, so the app served for a
wholly buried dipole a −21 dBi pattern that means nothing, and imaged the
buried radials of the ground-mounted vertical as if they stood in air.

This module is the one place the rule lives:

* every current below the plane → the pattern is REFUSED by name (the
  impedance, currents and charges stay served);
* a mixture → the pattern is evaluated twice, with and without the
  in-medium segments, and the largest change over the lit hemisphere is
  the measured sensitivity of this pattern to currents the readout cannot
  place honestly. Under `IN_MEDIUM_PATTERN_BAR_DB` the full readout is
  served (the status quo — excluding the segments is not the transmitted
  answer either, and on the ground-mounted vertical it moves the peak
  0.37 dB AWAY from NEC-5's) with a note carrying both numbers; over the
  bar it is refused, because a pattern that depends materially on
  in-medium currents needs momwire#570.

The measure is deliberately the pattern's own sensitivity and not the
share of current moment below the plane: on the shipped buried-radial
vertical 38 % of Σ|I·dl| is below ground and the pattern moves 0.46 dB,
because a symmetric screen's horizontal currents cancel in the far field.
A moment-fraction bar would refuse a pattern the physics barely notices.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Largest change in dBi, over the lit hemisphere, that imaging the in-medium
# currents as if above ground may make before the pattern is refused. 3 dB
# is half the power: past that the in-medium currents are not a detail of
# the pattern, they are the pattern. Measured on the catalog at 13/0.005
# (2026-09-09): buried_radial_vertical 0.46 dB, elevated_buried_counterpoise
# 0.10 dB, buried_dipole refused (nothing above the plane).
IN_MEDIUM_PATTERN_BAR_DB = 3.0

# Directions more than this far below the pattern's own peak are ignored by
# the sensitivity measure: a null moves by tens of dB when anything moves,
# and a null is not what a pattern is read for.
IN_MEDIUM_LIT_WINDOW_DB = 20.0

TRANSMITTED_FAR_FIELD_ISSUE = "momwire#570"


class InMediumPatternRefusal(ValueError):
    """The far field of this solve cannot be read out honestly (issue #1341).

    Raised by `MomwireEngine.far_field`; the web solve path stores the same
    sentence under ``pattern_refusal`` instead of raising, so impedance and
    currents still ship.
    """


@dataclass(frozen=True)
class InMediumAssessment:
    """What the readout found below the plane. ``fraction`` is the share of
    Σ|I·dl| below the interface; ``delta_db`` the largest change in the lit
    hemisphere between the full readout and the above-ground currents
    alone; exactly one of ``refusal`` / ``note`` is set when ``fraction``
    is non-zero, neither when it is zero."""

    fraction: float
    delta_db: float
    refusal: str | None
    note: str | None

    @property
    def served(self) -> bool:
        return self.refusal is None


def below_surface_mask(
    mid: np.ndarray, ground_z: float | None, *, tol=None
) -> np.ndarray:
    """Segments whose midpoint lies below the ground plane at ``ground_z``.

    ``tol`` defaults to 1e-6 of the structure's largest extent (at least
    1 m): a segment whose midpoint is a float-noise below the plane is ON
    the plane, and a deliberate burial is orders of magnitude deeper.
    """
    mid = np.asarray(mid, dtype=float)
    if ground_z is None or mid.size == 0:
        return np.zeros(mid.shape[0], dtype=bool)
    if tol is None:
        extent = float(np.max(np.ptp(mid, axis=0))) if mid.shape[0] > 1 else 0.0
        tol = 1e-6 * max(extent, 1.0)
    return mid[:, 2] < float(ground_z) - tol


def moment_fraction(dr: np.ndarray, i_mid: np.ndarray, mask: np.ndarray) -> float:
    """Share of Σ|I|·|dl| carried by the masked segments."""
    w = np.abs(np.asarray(i_mid)) * np.linalg.norm(np.asarray(dr, dtype=float), axis=1)
    total = float(np.sum(w))
    return float(np.sum(w[mask]) / total) if total > 0.0 else 0.0


def pattern_delta_db(
    mag2_full: np.ndarray, mag2_above: np.ndarray, *, window_db=IN_MEDIUM_LIT_WINDOW_DB
) -> float:
    """Largest |Δ dBi| between two readouts of one pattern, over the
    directions within ``window_db`` of the full readout's peak."""
    full = 10.0 * np.log10(np.maximum(np.asarray(mag2_full, dtype=float), 1e-30))
    above = 10.0 * np.log10(np.maximum(np.asarray(mag2_above, dtype=float), 1e-30))
    lit = full >= float(np.max(full)) - window_db
    if not np.any(lit):
        return 0.0
    return float(np.max(np.abs(above[lit] - full[lit])))


def wholly_buried_sentence() -> str:
    return (
        "every current in this solve lies below the interface, and the far "
        "field above ground of a source inside the medium is the transmitted "
        "field — refracted at the interface and attenuated through the soil — "
        f"which this readout does not compute ({TRANSMITTED_FAR_FIELD_ISSUE}). "
        "Impedance, currents and charges are served; the pattern is not."
    )


def over_bar_sentence(fraction: float, delta_db: float) -> str:
    return (
        f"{fraction:.0%} of the current moment lies below the interface, and "
        "imaging it as if above ground rather than through the interface "
        f"changes the pattern by up to {delta_db:.1f} dB in the lit hemisphere. "
        "A pattern that depends on in-medium currents needs the transmitted "
        f"far field ({TRANSMITTED_FAR_FIELD_ISSUE}), which this readout does "
        "not compute; the pattern is not served."
    )


def served_note(fraction: float, delta_db: float) -> str:
    return (
        f"{fraction:.0%} of the current moment lies below the interface and is "
        "imaged as if above ground; against the above-ground currents alone "
        f"that moves the pattern by up to {delta_db:.1f} dB in the lit "
        f"hemisphere. The transmitted far field ({TRANSMITTED_FAR_FIELD_ISSUE}) "
        "is not computed."
    )


def assess(mid, dr, i_mid, ground_z, evaluate, *, bar_db=IN_MEDIUM_PATTERN_BAR_DB):
    """Assess one solve's far-field readout against the currents below the
    plane. ``evaluate(mid, dr, i_mid) -> |M_perp|²`` over a fixed direction
    set is the readout under test, called at most twice."""
    mid = np.asarray(mid, dtype=float)
    mask = below_surface_mask(mid, ground_z)
    if not np.any(mask):
        return InMediumAssessment(0.0, 0.0, None, None)
    fraction = moment_fraction(dr, i_mid, mask)
    if not np.any(~mask):
        return InMediumAssessment(
            fraction, float("inf"), wholly_buried_sentence(), None
        )
    above = ~mask
    delta = pattern_delta_db(
        evaluate(mid, dr, i_mid),
        evaluate(mid[above], np.asarray(dr)[above], np.asarray(i_mid)[above]),
    )
    if delta > bar_db:
        return InMediumAssessment(
            fraction, delta, over_bar_sentence(fraction, delta), None
        )
    return InMediumAssessment(fraction, delta, None, served_note(fraction, delta))
