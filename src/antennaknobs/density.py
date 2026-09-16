"""The per-engine default mesh density, as one table (antennaknobs#1543).

``nominal_nsegs`` is a DENSITY, not a count: ``AntennaBuilder.auto_mesh``
reads it as segments per quarter-wave at ``design_freq``, so one number is
comparable across designs. What N a solver needs to be converged is a
property of its BASIS, which is why the number belongs to the engine and not
to the design.

This table is the only place those numbers are written down. The web roster
(``web/adapter.py``'s ``default_n_per_wire``) and the CLI both read it, so a
density quoted from the app and the same density quoted from a command line
cannot drift apart — before #1543 they were two tables and the CLI's was
empty, which is how the app's razor-2p tab came to run at 15.

Keys are the ROSTER names. The CLI's extra spellings (``bspline-d1``,
``razor-nec5``) resolve to a key here rather than growing a row, because they
are spellings of the same engine and a second row would be a second number to
move.

WHERE EACH NUMBER COMES FROM

- ``bspline`` is per DEGREE, and only bspline is: the degree IS the basis, and
  the basis is what sets the density. d=2 at 15 and d=1 at 20 are the
  basis-convergence census (docs/status/2026-07-20) — within 2% of the
  basis-agreed limit on 50/66 scorable designs at d=2, with d=1 needing the
  larger mesh to reach the same answer. d=3 at 12 continues the sequence
  (#1543, 2026-09-16). Odd, so a centre-fed deck gets an interior knot at the
  feed.
- ``razor-2p`` and ``nec5`` at 40: one number for the two first-order
  engines, so an A/B between momwire's formulation twin and the licensed
  binary is not also an A/B on the mesh. ~16x the mesh of bspline for the same
  self-convergence on the ByDipole1 ladder (momwire#780) is why it is higher,
  and EVEN because both want a source at a segment end / a knot at the wire's
  exact middle.
- ``arrayblock``, ``pynec``, ``nec2`` at 21 — the Builder framework default
  (``AntennaBuilder.FRAMEWORK_PARAMS``), odd for the same feed-knot reason.
- The rest at 30, unchanged and unmeasured: no census has said otherwise.

An engine ABSENT from this table has no antennaknobs opinion, and its caller
falls back to the Builder framework default. That is what ``--engine
momwire`` with no basis does, which is why a command line that names no basis
meshes exactly as it did before #1543.
"""

from collections.abc import Mapping

# Engine/roster name -> segments per quarter-wave at design_freq.
DEFAULT_NSEGS: Mapping[str, int] = {
    "sinusoidal": 30,
    "sinusoidal-galerkin": 30,
    "bspline": 15,
    "pulse": 30,
    "hmatrix": 30,
    "arrayblock": 21,
    "razor-2p": 40,
    "pynec": 21,
    "nec5": 40,
    "nec2": 21,
}

# Engine name -> degree -> density, for the engines whose degree is their
# basis. The degree the solver itself defaults to (``_OPTION_SPECS["degree"]``,
# 2) must map to the same number as the flat entry above, or a swap and a
# degree change would disagree about the stock mesh; gated in
# tests/test_density_1543.py.
#
# hmatrix and arrayblock expose `degree` too and are deliberately NOT here:
# they are accelerators chosen for SIZE, and no census has measured a
# per-degree density for them, so they keep one number across the tab.
NSEGS_BY_DEGREE: Mapping[str, Mapping[int, int]] = {
    "bspline": {1: 20, 2: 15, 3: 12},
}


def default_nsegs(name: str, *, degree: int | None = None) -> int | None:
    """This engine's default density, or None when it has no entry.

    None means "no antennaknobs opinion" and never 0 — the caller keeps the
    Builder framework default. A `degree` this engine has no per-degree row
    for falls back to its flat entry rather than to None, so an engine that
    merely ACCEPTS a degree keeps one density across it.
    """
    by_degree = NSEGS_BY_DEGREE.get(name)
    if by_degree is not None and degree is not None and degree in by_degree:
        return by_degree[degree]
    return DEFAULT_NSEGS.get(name)


def nsegs_by_degree(name: str) -> dict[int, int] | None:
    """This engine's per-degree densities as a fresh dict, or None.

    A fresh dict because this crosses the wire (the roster payload) and into
    a CLI resolver; a shared mapping handed out here would let one caller
    edit the table for every other.
    """
    by_degree = NSEGS_BY_DEGREE.get(name)
    return None if by_degree is None else dict(by_degree)
