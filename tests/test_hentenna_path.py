"""The hentenna written with ``st.path`` is the hentenna that was written with
its own ``build_path`` helper: same wires, same order, same bits."""

import itertools

import pytest

from antennaknobs import Transform, TransformStack
from antennaknobs.designs.specialty.hentenna import Builder
from antennaknobs.network import Wire


def _reference(b):
    """The design as it was before ``st.path`` (its helper, verbatim)."""
    wavelength = b.design_wavelength

    def ry(p):
        return p[0], -p[1], p[2]

    B = (
        0,
        wavelength * b.width_factor / 2,
        wavelength * (b.mid_height_factor - b.top_height_factor),
    )
    A = (0, wavelength * b.width_factor / 2, 0)
    F = (0, wavelength * b.width_factor / 2, wavelength * (-b.top_height_factor))
    C, D = ry(A), ry(B)
    E = ry(F)
    st = TransformStack()
    st.push(Transform.translate(0, 0, b.base))

    def build_path(lst, ex=None):
        return (Wire(st.hit(a), st.hit(c), ex=ex) for a, c in itertools.pairwise(lst))

    tups = []
    tups.extend(build_path([B, A, C, D]))
    tups.extend(build_path([B, F, E, D]))
    tups.extend(build_path([D, B], ex=1 + 0j))
    return tups


@pytest.mark.parametrize("variant", ["default_params", "z100_params"])
def test_the_hentenna_is_unchanged_by_st_path(variant):
    params = dict(Builder.default_params)
    if variant == "z100_params":
        params.update(Builder.z100_params)
    b = Builder(params)
    got = b.build_wires()
    assert len(got) == 7
    # `build_wires` meshes the wires (n_seg); the geometry and the feed are
    # compared exactly.
    assert [(w.p0, w.p1, w.ex) for w in got] == [
        (w.p0, w.p1, w.ex) for w in _reference(b)
    ]
