"""Which backends serve junction-node ports, MEASURED (#1152).

`_JUNCTION_PORT_BACKENDS` excluded `hmatrix` and `arrayblock` on a docstring
that said they "raise NotImplementedError". momwire declares both as serving
`junction_ports`, and both solve `wire.sterba_bl` (16 `PortAtEnd` ports):

    bspline              672.969912318 + 386.605011472j   (reference)
    sinusoidal-galerkin  672.892988555 + 386.842431879j   rel 3.2e-4
    hmatrix              672.965974382 + 386.610573299j   rel 8.8e-6
    arrayblock           673.035994564 + 386.591938736j   rel 8.7e-5

THE BAR IS THE ONE THE LIST ALREADY APPLIES. `sinusoidal-galerkin` was
admitted long ago and is the LOOSEST member at 3.2e-4 — an order beyond either
accelerator. So the question was never whether the accelerators clear a
standard; it was that refusing them while admitting a looser member was
inconsistent.

The residual is iterative closure, not the port columns, and that was checked
rather than assumed: tightening `aca_tol`/`solve_tol` walks it monotonically to
machine precision (hmatrix 8.8e-6 -> 2.1e-11 -> 2.9e-13, arrayblock 8.7e-5 ->
4.7e-10 -> 1.4e-13). On an easy deck (`dipoles.invvee`, no junction ports) the
same three agree to 3.1e-14 at default tolerance — the deviation here is the
deck's size and conditioning showing through the low-rank approximation, not
the ports being assembled differently.

Marked `antenna_computation_check`: four full solves of a 16-port deck.
"""

from __future__ import annotations

import warnings

import pytest

import antennaknobs.web.examples  # noqa: F401 — adapter is circular; import first
from antennaknobs.designs.wire.sterba_bl import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import PortAtEnd
from antennaknobs.web import adapter

# Comfortably above the loosest member measured (sinusoidal-galerkin, 3.2e-4)
# and far below anything that would hide a structural error in the port
# columns, which showed as 1e-5 and up before the tolerance sweep settled it.
_REL_TOL = 1e-3


def _solve(name: str) -> complex:
    spec = next(s for s in adapter._BACKENDS if s.name == name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return complex(MomwireEngine(Builder(), solver=spec.solver).impedance()[0])


def test_the_deck_really_carries_junction_ports():
    """The precondition. Without `PortAtEnd` ports this file would be four
    solves of an ordinary deck agreeing for reasons that say nothing about
    junction-port support."""
    net = Builder().build_network()
    ends = [k for k, p in net.ports.items() if isinstance(p, PortAtEnd)]
    assert len(ends) >= 2, ends


def test_the_allowlist_is_the_four_measured_backends():
    """Pinned membership, not just iteration. A test that only looped the list
    would pass for a list with an entry REMOVED -- it would simply check one
    fewer backend -- so the set is asserted here and the solves below are what
    justify it."""
    assert adapter._JUNCTION_PORT_BACKENDS == (
        "bspline",
        "sinusoidal-galerkin",
        "hmatrix",
        "arrayblock",
    )
    # `bspline` first: `_required_backends()[0]` becomes the design's default,
    # and the dense mixed-potential solver is the reference for these ports.
    assert adapter._JUNCTION_PORT_BACKENDS[0] == "bspline"


@pytest.mark.antenna_computation_check
def test_every_allowed_backend_solves_the_deck_and_agrees_with_the_parent():
    ref = _solve("bspline")
    assert abs(ref) > 1.0, ref
    for name in adapter._JUNCTION_PORT_BACKENDS[1:]:
        z = _solve(name)
        rel = abs(z - ref) / abs(ref)
        assert rel < _REL_TOL, (name, z, ref, rel)


@pytest.mark.antenna_computation_check
def test_the_accelerators_converge_to_the_parent_as_tolerance_tightens():
    """What separates "iterative closure" from "the port columns are wrong".
    A structural error would not move with `aca_tol`; this does, by orders."""
    ref = _solve("bspline")
    for name in ("hmatrix", "arrayblock"):
        spec = next(s for s in adapter._BACKENDS if s.name == name)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tight = complex(
                MomwireEngine(
                    Builder(),
                    solver=spec.solver,
                    solver_kwargs={"aca_tol": 1e-12, "solve_tol": 1e-14},
                ).impedance()[0]
            )
        loose = _solve(name)
        assert abs(tight - ref) / abs(ref) < 1e-10, (name, tight)
        assert abs(tight - ref) < abs(loose - ref), (name, tight, loose)


def test_the_restriction_reason_no_longer_names_only_two_solvers():
    """The tooltip a user reads on a disabled tab. It said only B-spline and
    sinusoidal-Galerkin implement these ports, which was false for the two
    accelerators before this change and would be false in the other direction
    after it."""
    reason = adapter._RESTRICTION_REASONS["junction_ports"]
    assert "accelerated" in reason
    assert "only the B-spline" not in reason
