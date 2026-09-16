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
  larger mesh to reach the same answer. d=3 at 16 (Steve, 2026-09-16, on
  the ΔΓ re-cut of the served-rung census, AK#1552 / #1553): at 12 its
  MEDIAN matched the others (ΔΓ 0.0040 against bs2@160, beside d=2's
  0.0037 and d=1's 0.0076) but its TAIL did not — worst 0.90 on
  ``short_dipole_loaded`` with the reactance's sign wrong, nine times d=1's
  worst — and a served density is judged on what a user can hit, not on the
  median. Measured at 16 the same day (Skylake, 206 cells, record branch
  ``scratch/1553-d3-at-16``): median ΔΓ 0.0035, p90 0.074, worst 0.74; the
  one genuine density row (``continuous_helix``) improves by a third, the
  loaded dipole by 17 % (a conditioning case no served density rescues —
  judge it at the antenna port), the zepp not at all (its fed wire is one
  fixed segment); catalog cold total 1.41x that of 12. bs2@160 is near the
  floor of what it can adjudicate at this density (admissible rows fell
  158 to 140 as the errors shrank), so saying more needs a deeper
  reference. Even, so a centre-fed wire keeps a knot at its middle.
- ``razor-2p`` and ``nec5`` at 40: one number for the two first-order
  engines, so an A/B between momwire's formulation twin and the licensed
  binary is not also an A/B on the mesh. It is higher than bspline's because
  both engines converge at FIRST order in the segment count (the #1525
  density ladder: razor-2p's fitted order is ~0.9 against bs2 refined to 160
  per wire; on ΔΓ, the metric the July corpus benchmark scores on, its
  median at 40 is 0.0129 against bs2@160 where d=2 at 15 reads 0.0037 —
  AK#1553's re-cut), where bs2 is within a few percent of its limit at 15. EVEN because both want a source at a segment
  end / a knot at the wire's exact middle. The number itself is the #1525
  decision (2026-09-16).
- ``arrayblock``, ``pynec``, ``nec2`` at 21 — the Builder framework default
  (``AntennaBuilder.FRAMEWORK_PARAMS``), odd for the same feed-knot reason.
- ``sinusoidal`` at 21: it is NEC-2's own basis, so it meshes as ``nec2`` and
  ``pynec`` do and an A/B across the three is not an A/B on the mesh.
  ``sinusoidal-galerkin`` at 20 (both decided 2026-09-16 on #1543).
- ``pulse`` at 41: a pulse row IS a segment, so the basis is odd-parity like
  ``nec2``'s, and it wants the denser mesh of a first-order basis (decided
  2026-09-16 on #1543).
- ``hmatrix`` at 30, unchanged and unmeasured: no census has said otherwise.

An engine ABSENT from this table has no antennaknobs opinion, and its caller
falls back to the Builder framework default. That is what ``--engine
momwire`` with no basis does, which is why a command line that names no basis
meshes exactly as it did before #1543.
"""

from collections.abc import Mapping

# Engine/roster name -> segments per quarter-wave at design_freq.
DEFAULT_NSEGS: Mapping[str, int] = {
    "sinusoidal": 21,
    "sinusoidal-galerkin": 20,
    "bspline": 15,
    "pulse": 41,
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
    "bspline": {1: 20, 2: 15, 3: 16},
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
