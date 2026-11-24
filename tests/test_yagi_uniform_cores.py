"""beams.yagi ``uniform_cores``: every element built on the director's core.

Each element is a centre wire of +-eps and core arms out to the director's
half-length; the driver and reflector reach their own lengths through
extension wires. Equal wires mesh equally, so the pairs between elements
repeat and pair_reuse copies them. The option changes the mesh, not the
antenna: the element extents are the default layout's.
"""

import math

import numpy as np
import pytest

from test_fill_report_2327 import needs_report

from antennaknobs.designs.beams.yagi import Builder as _Builder


def Builder(**kw):  # noqa: N802 — reads as the class it wraps
    """The builder takes a whole parameter dict; fill in the defaults."""
    return _Builder({**_Builder.default_params, **kw})


def _length(w):
    return math.dist(w.p0, w.p1)


def _elements(wires):
    """Group wires by boom position x."""
    by_x = {}
    for w in wires:
        by_x.setdefault(round(w.p0[0], 9), []).append(w)
    return [by_x[x] for x in sorted(by_x)]


def _extent(ws):
    ys = [p[1] for w in ws for p in (w.p0, w.p1)]
    return min(ys), max(ys)


def test_flat_elements_match_default_layout():
    base = _elements(Builder(n_directors=4).build_wires())
    uni = _elements(Builder(n_directors=4, uniform_cores=True).build_wires())
    assert len(base) == len(uni) == 6
    for a, b in zip(base, uni, strict=True):
        assert _extent(a) == pytest.approx(_extent(b), abs=1e-12)
        assert sum(map(_length, a)) == pytest.approx(sum(map(_length, b)), abs=1e-12)


def test_drooped_elements_bend_at_eps():
    """At a droop angle every element bends at +-eps, as the default driver
    does: the driver is unchanged, and the passive tips move out by
    eps * (1 - cos) and up by eps * sin, keeping their wire length."""
    angle, eps = 30.0, 0.05
    shift = eps * (1 - math.cos(math.radians(angle)))
    lift = eps * math.sin(math.radians(angle))
    base = _elements(Builder(n_directors=4, angle_deg=angle).build_wires())
    uni = _elements(
        Builder(n_directors=4, angle_deg=angle, uniform_cores=True).build_wires()
    )
    for a, b in zip(base, uni, strict=True):
        driver = any(w.ex is not None for w in a)
        lo, hi = _extent(a)
        want = (lo, hi) if driver else (lo - shift, hi + shift)
        assert _extent(b) == pytest.approx(want, abs=1e-12)
        assert sum(map(_length, a)) == pytest.approx(sum(map(_length, b)), abs=1e-12)
        low = min(p[2] for w in a for p in (w.p0, w.p1))
        want_low = low if driver else low + lift
        assert min(p[2] for w in b for p in (w.p0, w.p1)) == pytest.approx(
            want_low, abs=1e-12
        )


def test_every_element_shares_the_core():
    elems = _elements(Builder(n_directors=4, uniform_cores=True).build_wires())
    cores = [sorted(round(_length(w), 12) for w in ws[:3]) for ws in elems]
    assert all(c == cores[0] for c in cores)
    # Directors are the bare core; driver and reflector add two extensions.
    assert sorted(len(ws) for ws in elems) == [3, 3, 3, 3, 5, 5]


def test_driver_fed_on_its_centre_wire():
    wires = Builder(uniform_cores=True).build_wires()
    fed = [w for w in wires if w.ex is not None]
    assert len(fed) == 1
    (x0, y0, _), (x1, y1, _) = fed[0].p0, fed[0].p1
    assert x0 == x1 == 0.0
    assert y0 == pytest.approx(-0.05) and y1 == pytest.approx(0.05)


def test_impedance_matches_default_layout():
    """Both layouts converge to the same antenna; at a modest mesh they
    already agree to well under an ohm (the ladder study's N=120 rung
    agrees to 0.02 ohm)."""
    from antennaknobs.engines.momwire import MomwireEngine

    z = [
        complex(
            np.asarray(MomwireEngine(Builder(uniform_cores=u)).impedance()).ravel()[0]
        )
        for u in (False, True)
    ]
    assert abs(z[1] - z[0]) < 1.0, z


@needs_report
def test_uniform_cores_raise_reuse_compression():
    """The point of the option: on the 10-element Yagi at 121 segments per
    wire, Sinusoidal's pair reuse compresses the fill about 5x with the
    default layout and about 45x with uniform cores (pairs over computed
    plus near entries: 5.4 and 46 when written)."""
    from momwire.sinusoidal import SinusoidalSolver

    from antennaknobs.engines.momwire import MomwireEngine

    ratio = {}
    for u in (False, True):
        b = Builder(n_directors=8, uniform_cores=u, nominal_nsegs=121)
        e = MomwireEngine(b, solver=SinusoidalSolver, pair_reuse=True)
        e.impedance()
        r = e.fill_report()["reuse"]
        assert r["state"] == "served", r
        ratio[u] = r["pairs"] / (r["computed"] + r["near"])
    assert ratio[False] < 10 < 30 < ratio[True], ratio
