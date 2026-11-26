"""Each block template against its catalog twin, at the same knobs
(docs/design/block-builder.md, "Testing").

The tolerance, and why: a template is written to be the SAME model as its
twin (the same wires, the same mesh, the same feed), so the only difference
allowed is floating-point evaluation order. The dipole template builds one
arm and mirrors it, so that arm runs the other way from the twin's and the
system is assembled in a different order; momwire's eval-order drift is
~1e-15 relative and bounded near 1e-12 (the perf eval-order tolerance the
repo already uses). So ``REL_TOL = 1e-12``. That bound is sharp: a one part
per million change of one knob moves Z by 7.5e-7 to 2.1e-5 relative on
these three (measured 2026-11-25, momwire bs2, free space; pinned below),
five orders above it, so any modelling difference (a segment more, a moved
feed, a wrong sign) fails. Measured agreement on 2026-11-25 is exactly 0.0
in all twelve cases here, free space and refl-coef ground, at the defaults
and at moved knobs.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs import as_wire
from antennaknobs.block_design import blocks_builder
from antennaknobs.block_templates import NAMES, template
from antennaknobs.cli import get_builder
from antennaknobs.engines.momwire import MomwireEngine

REL_TOL = 1e-12

TWINS = {
    "dipole": ("dipoles.invvee:dipole", {"length_factor": 1.03, "base": 9.0}),
    "invvee": ("dipoles.invvee", {"angle_deg": 12.0, "length_factor": 0.93}),
    "hentenna": ("specialty.hentenna", {"width_factor": 0.16, "base": 12.0}),
}
GROUNDS = ("free", ("finite-fast", 13.0, 0.005))


def test_every_template_has_a_twin():
    assert set(TWINS) == set(NAMES)


def _pair(name, knobs):
    twin, _ = TWINS[name]
    cls = blocks_builder(template(name))
    ours = cls({**cls.default_params, **knobs})
    theirs = get_builder(twin)()
    for k, v in knobs.items():
        setattr(theirs, k, v)
    return ours, theirs


@pytest.mark.parametrize("moved", [False, True], ids=["defaults", "moved"])
@pytest.mark.parametrize("name", NAMES)
def test_the_template_is_its_twins_geometry(name, moved):
    ours, theirs = _pair(name, TWINS[name][1] if moved else {})
    a = ours.build_wires()
    b = [as_wire(w) for w in theirs.build_wires()]
    assert len(a) == len(b)

    def key(w):
        # A wire, either way round: the dipole's mirrored arm runs reversed.
        ends = sorted([tuple(map(float, w.p0)), tuple(map(float, w.p1))])
        return (*ends, w.n_seg, w.ex is not None)

    ka, kb = sorted(map(key, a)), sorted(map(key, b))
    for x, y in zip(ka, kb, strict=True):
        assert np.allclose(x[0] + x[1], y[0] + y[1], rtol=0, atol=4 * np.spacing(20.0))
        assert x[2:] == y[2:]


@pytest.mark.parametrize("ground", GROUNDS, ids=["free", "refl-coef"])
@pytest.mark.parametrize("moved", [False, True], ids=["defaults", "moved"])
@pytest.mark.parametrize("name", NAMES)
def test_the_template_impedance_is_its_twins(name, moved, ground):
    ours, theirs = _pair(name, TWINS[name][1] if moved else {})
    za = MomwireEngine(ours, ground=ground).impedance()[0]
    zb = MomwireEngine(theirs, ground=ground).impedance()[0]
    assert abs(za - zb) <= REL_TOL * abs(zb), (za, zb)


@pytest.mark.parametrize("name", NAMES)
def test_the_tolerance_is_sharp(name):
    """One ppm on the last knob moves Z far past REL_TOL, so the bound
    above cannot pass a model that differs."""
    cls = blocks_builder(template(name))
    key = template(name)["params"][-1]["name"]
    nudged = {**cls.default_params, key: cls.default_params[key] * (1 + 1e-6)}
    z0 = MomwireEngine(cls(), ground="free").impedance()[0]
    z1 = MomwireEngine(cls(nudged), ground="free").impedance()[0]
    assert abs(z1 - z0) > 1e4 * REL_TOL * abs(z0)
