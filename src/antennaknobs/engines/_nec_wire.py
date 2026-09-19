"""A wire's material as NEC cards: the GW radius, LD 5 and LD 2 (issue #1523).

NEC has no insulated-wire card (NEC-2 never had one, and NEC-5 dropped NEC-4's
IS), so every deck writer here spells a dielectric jacket with the cards it does
have. momwire models the jacket as the Popović–Nešić PAIR (momwire#865):

  * the kernel sees the equivalent radius a′ = a·(b/a)^((εr−1)/εr), which is
    the jacket's effect on the charge;
  * a distributed series inductance L′ = (μ0/2π)·(1 − 1/εr)·ln(b/a) puts back
    the inductance that enlarging the radius removed.

The NEC writers used to write L′ alone, on the bare radius. That gets the
phase velocity right only to first order and overstates the V/I line impedance
by 2–9 %. On a jacketed dipole the two spellings differ by 1.6–5 % of |Z|, by
the same amount on bs2, razor-2p and NEC-5 (#1523's verdict). This module is
the one place the pair is spelled, so the NEC-5 deck, PyNEC's card calls and the
exported NEC-2 deck cannot disagree about what a jacket is.

WRITING a′ ON THE GW CARD MOVES LD 5 TOO. NEC evaluates a conductor's internal
impedance at the GW radius, and at a′ that is a thicker wire: the copper's
resistance would fall by 41–80 % on the catalog's PVC wires. Scaling the
conductivity by (a/a′)² puts it back exactly. A round conductor's internal
impedance is Z = k·I0(ka) / (2πaσ·I1(ka)) with k = √(jωμ0σ), and σ′ = σ·(a/a′)²
leaves both k·a and k/(aσ) unchanged at a′. That holds at every frequency, so
one card still serves a sweep.

READING THE PAIR BACK (issue #1591): ``jacket_from_equivalent_radius`` inverts
``equivalent_radius``/``insulation_inductance`` — from a GW radius a′ and an
LD 2 inductance L′ alone, ``ln(a'/a) = L' / (mu0/2pi)`` gives back the exact
conductor radius a, no root-finding needed. (b, εr) is NOT recoverable the
same way: only the product k·ln(b/a) (k = 1 − 1/εr) is pinned by a′ and L′, so
every (b, εr) on that curve is electrically identical (same a′, same L′). The
inverse reports one canonical member of that family, not a measurement of the
physical jacket.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from momwire import equivalent_radius, insulation_inductance

if TYPE_CHECKING:
    from ..wire_catalog import WireSpec

# mu0/2pi, DERIVED from momwire's own constant rather than copied, so this
# can never drift from the value `equivalent_radius`/`insulation_inductance`
# actually used: probe radii chosen so ln(b/a) = 1 and (1 - 1/eps_r) = 0.5
# make `insulation_inductance` return exactly (mu0/2pi)/2.
_MU0_2PI = 2.0 * float(insulation_inductance(1.0, math.e, 2.0))

# The one-parameter family of (insulation_radius, eps_r) pairs that share a
# given a'/L' is reported through this eps_r — an arbitrary but fixed choice
# (>1, so `insulation_inductance`'s own validation accepts it) with no
# physical significance; see the module docstring.
CANONICAL_INSULATION_EPS_R = 2.0

# A deck that carries a jacket says so, because its GW radius is larger than the
# wire gauge's and a reader comparing the two would otherwise suspect a bug.
JACKET_COMMENT_CARDS = (
    "CM jacketed wire: GW radius = equivalent radius a' = a*(b/a)^((er-1)/er)",
    "CM its LD 5 conductivity is scaled by (a/a')^2; LD 2 = jacket inductance",
)


@dataclass(frozen=True)
class NecWireMaterial:
    """One wire's material cards."""

    radius: float  # GW card radius, m
    conductivity: float | None  # LD 5, S/m; None = no card (PEC)
    inductance: float | None  # LD 2, H/m; None = no card (bare wire)


def nec_wire_material(
    radius: float,
    conductivity: float | None,
    spec: WireSpec | None,
    *,
    pair: bool = True,
) -> NecWireMaterial:
    """The NEC cards for a wire of conductor radius ``radius`` [m] and
    ``conductivity`` [S/m, None = PEC], jacketed as ``spec`` says.

    A bare wire (``spec`` None, or no ``insulation_radius``) passes through
    unchanged. ``pair=False`` is the inductance-only spelling: the bare radius,
    the unscaled conductivity and L′. It is for a consumer that drops the LD
    cards (SimNEC's portal), where a′ without its L′ would be half of a model.
    """
    if spec is None or not spec.insulation_radius:
        return NecWireMaterial(radius, conductivity, None)
    b, eps_r = spec.insulation_radius, spec.insulation_eps_r
    inductance = float(insulation_inductance(radius, b, eps_r))
    if not pair:
        return NecWireMaterial(radius, conductivity, inductance)
    a_eq = float(equivalent_radius(radius, b, eps_r))
    if conductivity is not None:
        conductivity = conductivity * (radius / a_eq) ** 2
    return NecWireMaterial(a_eq, conductivity, inductance)


def jacket_from_equivalent_radius(
    a_eq: float, inductance: float
) -> tuple[float, float, float] | None:
    """Invert the a′+L′ pair (issue #1591): given a GW card's radius ``a_eq``
    and an LD 2 card's inductance ``inductance`` [H/m], recover a (conductor
    radius, insulation_radius, insulation_eps_r) triple that reproduces both
    exactly through ``nec_wire_material`` — see the module docstring for why
    the radius is exact and (b, εr) is one member of a family rather than a
    measurement.

    Returns ``None`` when ``inductance`` does not correspond to a physical
    jacket on ``a_eq``: a jacket only ever inflates the equivalent radius
    (a < a′), so ``inductance`` must be positive and imply a radius strictly
    less than ``a_eq``. A non-jacket LD 2 card (no inductance to invert, or
    one that fails this check) is the caller's cue to report the card as
    untranslated rather than call this function at all.
    """
    if inductance <= 0.0:
        return None
    ln_ratio = inductance / _MU0_2PI  # ln(a_eq / a), from the identity above
    radius = a_eq * math.exp(-ln_ratio)
    if not (0.0 < radius < a_eq):
        return None
    k = 1.0 - 1.0 / CANONICAL_INSULATION_EPS_R
    insulation_radius = radius * math.exp(ln_ratio / k)
    return radius, insulation_radius, CANONICAL_INSULATION_EPS_R
