"""multiband.twoband_fan_dipole ``uniform_cores``: both bands' arms on one core.

The longer band's arm becomes a core wire as long as the shorter band's arm,
then a collinear extension out to its own tip. At equal droop the four cores
(two bands, two sides) are mirror images of one another and mesh equally, so
pair_reuse copies the pairs between all four, not only between a band's two
sides. The option changes the mesh, not the antenna.
"""

import math

import pytest

from test_fill_report_2327 import needs_report

from antennaknobs.designs.multiband.twoband_fan_dipole import Builder as _Builder


def Builder(**kw):  # noqa: N802 — reads as the class it wraps
    """The builder takes a whole parameter dict; fill in the defaults."""
    return _Builder({**_Builder.default_params, **kw})


def _length(w):
    return math.dist(w.p0, w.p1)


def _points(wires):
    return sorted({tuple(round(c, 12) for c in p) for w in wires for p in (w.p0, w.p1)})


def test_off_by_default_and_the_default_layout_is_unchanged():
    assert _Builder.default_params["uniform_cores"] is False
    assert len(Builder().build_wires()) == 9


def test_the_antenna_is_the_same_wire():
    base = Builder().build_wires()
    uni = Builder(uniform_cores=True).build_wires()
    # Two extra wires, the longer arm's extensions, one per side.
    assert len(uni) == len(base) + 2
    assert sum(map(_length, uni)) == pytest.approx(sum(map(_length, base)), abs=1e-12)
    # Every end point of the default layout is still one, and the two new
    # ones are the joints.
    assert set(_points(base)) <= set(_points(uni))
    assert len(_points(uni)) == len(_points(base)) + 2


def test_the_four_cores_are_mirror_images():
    wires = Builder(uniform_cores=True).build_wires()
    bands = Builder().bands
    short = min(float(b["length"]) for b in bands)
    s = Builder().s
    core = (short - 2 * s) / 2
    cores = [w for w in wires if _length(w) == pytest.approx(core, abs=1e-12)]
    assert len(cores) == 4
    # Same y and z ends; x and y flip only in sign: exact mirrors.
    ends = sorted(
        (abs(w.p0[0]), abs(w.p0[1]), w.p0[2], abs(w.p1[0]), abs(w.p1[1]), w.p1[2])
        for w in cores
    )
    assert all(e == ends[0] for e in ends)


def test_one_band_ignores_it():
    assert (
        Builder(n_bands=1, uniform_cores=True).build_wires()
        == Builder(n_bands=1).build_wires()
    )


@needs_report
@pytest.mark.parametrize("model", ["bs2", "sinusoidal", "razor2p"])
def test_reuse_shares_the_cores_and_the_answer_holds(model):
    import numpy as np

    import antennaknobs.web.server  # noqa: F401 — registers the designs
    from antennaknobs.cli import resolve_class
    from antennaknobs.web.adapter import _build_builder, _make_momwire_engine

    geo = "multiband.twoband_fan_dipole"
    out = {}
    for uc in (False, True):
        req = {
            "geometry": geo,
            "solver": "momwire",
            "momwire_model": model,
            "model_options": {"pair_reuse": True},
            "n_per_wire": 101,
            "uniform_cores": uc,
            "ground": False,
        }
        eng = _make_momwire_engine(req, _build_builder(resolve_class(geo), req))
        z = complex(np.asarray(eng.impedance(), dtype=complex).ravel()[0])
        r = eng.fill_report()["reuse"]
        out[uc] = (z, r["pairs"] / r["computed"])
    # Measured 2.1x more compression on all three engines (bs2 5.1x -> 10.6x,
    # sinusoidal and razor2p 2.6x -> 5.5x); the mesh moves Z by 1e-4 ohm.
    assert out[True][1] > 1.8 * out[False][1]
    assert abs(out[True][0] - out[False][0]) < 1e-3
