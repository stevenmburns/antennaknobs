"""The momwire bases antennaknobs offers: one table, read by the app and the
CLI alike (antennaknobs#1560).

Three places used to name the same bases: the CLI's hand-kept
``MOMWIRE_BASES`` / ``MOMWIRE_BASIS_VARIANTS`` (plus two ``--engine`` help
strings), the web roster's ``_BACKENDS``, and ``density.py``. The app served a
Pulse tab and ``density.py`` gave ``pulse`` a row while the CLI refused the
name (#1559). Now:

- ``BASES`` is the roster: name -> solver class + the constructor kwargs the
  name BINDS. ``web/adapter.py``'s ``_BACKENDS`` takes each momwire tab's
  class and binding from here (it adds only what the app renders: labels,
  options, panels), and the CLI accepts ``momwire:<name>`` for exactly these.
- ``ALIASES`` are the CLI's extra spellings. Each is a roster name plus
  kwargs, so it is the same ENGINE and reads its roster name's density row
  rather than growing one (#1543).
- ``density.py`` keeps the numbers; ``tests/test_momwire_bases_1560.py`` gates
  that every roster name has a row, that the app serves exactly ``BASES``, and
  that the CLI accepts exactly ``BASES`` plus ``ALIASES``.

WHAT THE NAMES BIND

The names are momwire's (momwire#2091): no dash, the basis alone. The
spellings that shipped before the rename are read through
`antennaknobs.engine_names` at every entry and never printed.

- ``sinusoidal`` is NEC-2's formulation: the three-term basis, point matching
  and the segment gap. ``sg`` is the same basis tested variationally
  (momwire#182), with the point gap as its default; its feed model is a
  web-panel choice (#640), not a second CLI name (momwire#654 retired the
  ``-converged`` suffix).
- ``razor2p`` binds ``RazorSolver``'s identified two-point quadrature
  (``nec5_quadrature=True``, momwire#316), the name momwire's own deck front
  end (``momwire.deck.BASES``) uses. Plain ``razor`` — the converged
  Gauss-Legendre lane, 12-80x slower than ``bs2`` for ~0.001 Ω — left the
  roster in momwire#753; construct ``RazorSolver(...)`` directly for
  convergence work.
- ``pulse`` is ``HarringtonSolver``, point-matched pulse expansion (the app's
  Pulse tab, AK#1148). The bare ``PulseSolver`` stays library-only.
- ``bs1`` (alias) is the degree axis: ``bs2`` with ``degree=1`` (#821).
  ``razor-nec5``, the old spelling of ``razor2p``, is refused by name, as
  momwire refuses it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from momwire import (
    ArrayBlockSolver,
    BSplineSolver,
    HarringtonSolver,
    HMatrixSolver,
    RazorSolver,
    SinusoidalGalerkinSolver,
    SinusoidalSolver,
)

from .engine_names import canonical_basis


@dataclass(frozen=True)
class Basis:
    solver: type
    # Constructor kwargs the NAME binds. The app applies them after a
    # request's model options, so a bound lane cannot be flipped from the
    # wire; the CLI passes them as `solver_kwargs`.
    bound: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))


# Roster name -> basis, in the app's tab order.
BASES: Mapping[str, Basis] = MappingProxyType(
    {
        "sinusoidal": Basis(SinusoidalSolver),
        "sg": Basis(SinusoidalGalerkinSolver),
        "bs2": Basis(BSplineSolver),
        "pulse": Basis(HarringtonSolver),
        "hmatrix": Basis(HMatrixSolver),
        "arrayblock": Basis(ArrayBlockSolver),
        "razor2p": Basis(RazorSolver, MappingProxyType({"nec5_quadrature": True})),
    }
)

# CLI spelling -> (roster name, kwargs it adds to that name's binding).
ALIASES: Mapping[str, tuple[str, Mapping[str, object]]] = MappingProxyType(
    {
        "bs1": ("bs2", MappingProxyType({"degree": 1})),
    }
)


def cli_names() -> list[str]:
    """Every ``momwire:<name>`` the CLI accepts: the roster, then the aliases."""
    return [*BASES, *ALIASES]


def resolve(name: str) -> tuple[str, type, dict[str, object]] | None:
    """``(roster name, solver class, bound kwargs)`` for a CLI basis name, or
    None when it names no basis. A deprecated spelling (``bspline``) resolves
    as its canonical name; a retired one raises `RetiredEngineName`."""
    name = canonical_basis(name)
    roster, extra = ALIASES.get(name, (name, {}))
    basis = BASES.get(roster)
    if basis is None:
        return None
    return roster, basis.solver, {**basis.bound, **extra}
