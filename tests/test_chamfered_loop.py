"""A chamfered n-gon skyloop as ``n`` passes of a two-wire unit (a short
chamfer across a vertex, then a long leg), under one transform stack, each pass its own
``with`` block.

For n = 3 it is the catalog's ``triangular_skyloop``, which is flown with the
turtle; the two must be the same wires."""

import math

import numpy as np
import pytest

from antennaknobs import Transform, TransformStack, as_wire
from antennaknobs.designs.loops.triangular_skyloop import Builder as TriangularSkyloop


def chamfered_loop(n, side, base, eps=0.05):
    """Equiangular 2n-gon: n long legs alternating with n short chamfers of
    length 2*eps; one pass of the unit is a chamfer and a leg. Every
    corner turns 180/n degrees, so the chamfer sits across what would be the
    n-gon's vertex, perpendicular to its bisector. The perimeter is n * side.
    The loop hangs toward -y from an apex chamfer centred on the origin, and
    is fed across that chamfer."""
    gap = 2 * eps
    run = side - gap
    half = math.pi / n  # each corner's turn
    # The vertex distance from the centre that closes the loop: the leg that
    # leaves one chamfer must land on the next pass's chamfer.
    rho = (run + gap * math.cos(half)) / (2 * math.sin(half))
    st = TransformStack()
    st.push(Transform.translate(0, -rho, base))
    for i in range(n):
        with st.push_pop_tr(Transform.rotZ(-360.0 * i / n)):
            # One pass, in the apex's frame about the centre: the chamfer
            # across the vertex, then the leg that carries on to the next one.
            st.wire_x(-gap / 2, gap / 2, y=rho, ex=(1 + 0j) if i == 0 else None)
            leg = (gap / 2 + run * math.cos(half), rho - run * math.sin(half), 0)
            st.path([(gap / 2, rho, 0), leg])
    return st.wires


def test_three_passes_are_the_catalog_triangle():
    b = TriangularSkyloop(TriangularSkyloop.default_params)
    side = (b.design_wavelength / 3.0) * b.length_factor
    got = chamfered_loop(3, side, b.base)
    want = [as_wire(w) for w in b.build_wires()]
    assert len(got) == len(want) == 6
    for g, w in zip(got, want, strict=True):
        assert np.allclose(g.p0, w.p0, atol=1e-9)
        assert np.allclose(g.p1, w.p1, atol=1e-9)
        assert (g.ex is None) == (w.ex is None)


@pytest.mark.parametrize("n", [3, 4, 5, 6, 8])
def test_any_n_closes_and_conserves_the_perimeter(n):
    side = 12.0
    wires = chamfered_loop(n, side, 10.0)
    assert len(wires) == 2 * n
    # A closed chain: each wire starts where the one before ended.
    for a, b in zip(wires, wires[1:] + wires[:1], strict=True):
        assert np.allclose(a.p1, b.p0, atol=1e-12)
    length = sum(np.linalg.norm(np.subtract(w.p1, w.p0)) for w in wires)
    assert length == pytest.approx(n * side, abs=1e-9)
    assert sum(w.ex is not None for w in wires) == 1
    # The apex chamfer is centred on the origin.
    assert np.allclose(np.add(wires[0].p0, wires[0].p1) / 2, (0, 0, 10.0))
