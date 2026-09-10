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
  in-medium segments, and the share of the radiated power (over the lit
  hemisphere, sin θ weighted) that the imaged in-medium currents account
  for is the measured dependence of this pattern on currents the readout
  cannot place honestly. Under `IN_MEDIUM_POWER_SHARE_BAR` the full
  readout is served (the status quo — excluding the segments is not the
  transmitted answer either, and on the ground-mounted vertical it moves
  the peak 0.37 dB AWAY from NEC-5's) with a note carrying the share and
  the change at the peak direction; over the bar it is refused, because a
  pattern that depends materially on in-medium currents needs momwire#570.

The measure is a POWER SHARE and not a worst-direction dB change, and
not the share of current moment below the plane, for two reasons found
by fire. A dB change over the lit hemisphere compares against nulls: a
monopole over one buried radial has an exact zenith null on its
above-ground currents alone and a filled one with the radial imaged, and
that read as "254 dB" and refused a pattern the physics barely notices
(the main-only power-balance suite, 2026-09-10). A moment fraction sees
38 % of Σ|I·dl| below ground on the shipped buried-radial vertical, whose
symmetric screen cancels in the far field and accounts for 8 % of the
radiated power as imaged. The power share is bounded, integrates over
the whole lit hemisphere, and is 100 % exactly when nothing is above
the plane.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# The share of the lit hemisphere's radiated power that the imaged in-medium
# currents account for, past which the pattern is refused. Half: past that
# the in-medium currents are not a detail of the pattern, they are the
# pattern. Measured on the catalog at 13/0.005 (2026-09-10):
# buried_radial_vertical 8.3 % (4 radials; 8.8 % at one, 8.1 % at two),
# elevated_buried_counterpoise 1.6 %, buried_dipole 100 % (refused: nothing
# above the plane).
IN_MEDIUM_POWER_SHARE_BAR = 0.5

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
    Σ|I·dl| below the interface; ``power_share`` the share of the lit
    hemisphere's radiated power the imaged in-medium currents account for;
    ``delta_db`` the change at the full pattern's peak direction between
    the full readout and the above-ground currents alone (negative when
    the imaged currents add there); exactly one of ``refusal`` / ``note``
    is set when ``fraction`` is non-zero, neither when it is zero."""

    fraction: float
    power_share: float
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


def power_share(
    mag2_full, mag2_above, weights=None, *, window_db=IN_MEDIUM_LIT_WINDOW_DB
):
    """The share of the full readout's radiated power, over the directions
    within ``window_db`` of its peak, that the imaged in-medium currents
    account for: Σ w·|full − above| / Σ w·full. ``weights`` is the solid-
    angle weight per direction (sin θ per row on a θ×φ grid), broadcast
    against the arrays; None means a uniform direction set."""
    full = np.asarray(mag2_full, dtype=float)
    above = np.asarray(mag2_above, dtype=float)
    if weights is None:
        w = np.ones_like(full)
    else:
        w = np.broadcast_to(np.asarray(weights, dtype=float), full.shape)
    peak = float(np.max(full))
    if peak <= 0.0:
        return 0.0
    lit = full >= peak * 10.0 ** (-window_db / 10.0)
    denominator = float(np.sum(w[lit] * full[lit]))
    if denominator <= 0.0:
        return 0.0
    return float(np.sum(w[lit] * np.abs(full[lit] - above[lit])) / denominator)


def peak_delta_db(mag2_full, mag2_above) -> float:
    """The change, in dB, at the full readout's peak direction when the
    in-medium currents are dropped: 10·log10(above/full) there. Bounded
    below at −99 for an exact null."""
    full = np.asarray(mag2_full, dtype=float)
    above = np.asarray(mag2_above, dtype=float)
    idx = np.unravel_index(int(np.argmax(full)), full.shape)
    if full[idx] <= 0.0:
        return 0.0
    if above[idx] <= 0.0:
        return -99.0
    return float(10.0 * np.log10(above[idx] / full[idx]))


def wholly_buried_sentence() -> str:
    return (
        "every current in this solve lies below the interface, and the far "
        "field above ground of a source inside the medium is the transmitted "
        "field — refracted at the interface and attenuated through the soil — "
        f"which this readout does not compute ({TRANSMITTED_FAR_FIELD_ISSUE}). "
        "Impedance, currents and charges are served; the pattern is not."
    )


def over_bar_sentence(fraction: float, share: float, delta_db: float) -> str:
    return (
        f"{fraction:.0%} of the current moment lies below the interface, and "
        "imaged as if above ground rather than through the interface it "
        f"accounts for {share:.0%} of the radiated power ({delta_db:+.1f} dB at "
        "the peak). A pattern that depends on in-medium currents needs the "
        f"transmitted far field ({TRANSMITTED_FAR_FIELD_ISSUE}), which this "
        "readout does not compute; the pattern is not served."
    )


def served_note(fraction: float, share: float, delta_db: float) -> str:
    return (
        f"{fraction:.0%} of the current moment lies below the interface and is "
        f"imaged as if above ground; that accounts for {share:.0%} of the "
        f"radiated power ({delta_db:+.1f} dB at the peak). The transmitted far "
        f"field ({TRANSMITTED_FAR_FIELD_ISSUE}) is not computed."
    )


def assess(
    mid, dr, i_mid, ground_z, evaluate, *, weights=None, bar=IN_MEDIUM_POWER_SHARE_BAR
):
    """Assess one solve's far-field readout against the currents below the
    plane. ``evaluate(mid, dr, i_mid) -> |M_perp|²`` over a fixed direction
    set is the readout under test, called at most twice; ``weights`` is that
    direction set's solid-angle weight (sin θ per row on a θ×φ grid)."""
    mid = np.asarray(mid, dtype=float)
    mask = below_surface_mask(mid, ground_z)
    if not np.any(mask):
        return InMediumAssessment(0.0, 0.0, 0.0, None, None)
    fraction = moment_fraction(dr, i_mid, mask)
    if not np.any(~mask):
        return InMediumAssessment(fraction, 1.0, -99.0, wholly_buried_sentence(), None)
    above = ~mask
    full = evaluate(mid, dr, i_mid)
    part = evaluate(mid[above], np.asarray(dr)[above], np.asarray(i_mid)[above])
    share = power_share(full, part, weights)
    delta = peak_delta_db(full, part)
    if share > bar:
        return InMediumAssessment(
            fraction, share, delta, over_bar_sentence(fraction, share, delta), None
        )
    return InMediumAssessment(
        fraction, share, delta, None, served_note(fraction, share, delta)
    )
