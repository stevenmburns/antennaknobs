"""AK#1850: `n_radials` on the catalog verticals, and `inverted_l` dropping a
0 top wire.

- the defaults build the same wires as before the knob (4 radials on the
  inverted L, 3 on the vertical), so no catalog number moves;
- the knob moves the radial count, spread evenly from the feed;
- `horiz_frac = 0` leaves no top wire (a zero-length wire would not mesh),
  and that state solves as the plain vertical: the feed, the riser and the
  same radials.
"""

from __future__ import annotations

import math

import pytest

from antennaknobs.cli import get_builder
from antennaknobs.engines.momwire import MomwireEngine

INVL = "verticals.inverted_l"
VERT = "verticals.vertical"


def _builder(design, **knobs):
    cls = get_builder(design)
    return cls(dict(cls.default_params, **knobs))


def _radials(b):
    """Wires lying in the feed plane: the counterpoise."""
    z = b.base
    return [
        w
        for w in b.build_wires()
        if abs(w.p0[2] - z) < 1e-12 and abs(w.p1[2] - z) < 1e-12
    ]


@pytest.mark.parametrize(("design", "n"), [(INVL, 4), (VERT, 3)])
def test_the_default_is_the_old_hard_coded_count(design, n):
    b = get_builder(design)()
    assert b.n_radials == n
    assert b.build_wires() == _builder(design, n_radials=n).build_wires()
    assert len(_radials(b)) == n


@pytest.mark.parametrize("design", [INVL, VERT])
@pytest.mark.parametrize("n", [1, 2, 6, 16])
def test_n_radials_moves_the_radial_count(design, n):
    b = _builder(design, n_radials=n)
    radials = _radials(b)
    assert len(radials) == n
    # Spread evenly from the feed, the first along +x.
    az = [math.atan2(w.p1[1], w.p1[0]) % (2 * math.pi) for w in radials]
    want = [2 * math.pi * i / n for i in range(n)]
    assert sorted(az) == pytest.approx(want, abs=1e-12)
    ui = get_builder(design).default_params["ui_params"]["n_radials"]
    assert (ui["min"], ui["max"], ui["step"]) == (1, 16, 1)


def test_a_zero_top_wire_is_no_wire():
    b = _builder(INVL, horiz_frac=0.0)
    wires = b.build_wires()
    # Feed gap, riser and the 4 radials; nothing leaves the x = 0, y = 0 axis
    # above the feed plane.
    assert len(wires) == 2 + 4
    assert all(math.dist(w.p0, w.p1) > 0 for w in wires)
    above = [w for w in wires if max(w.p0[2], w.p1[2]) > b.base]
    assert all(abs(p[0]) + abs(p[1]) == 0.0 for w in above for p in (w.p0, w.p1))
    assert get_builder(INVL).default_params["ui_params"]["horiz_frac"]["min"] == 0.0


def test_a_zero_top_wire_solves_as_the_plain_vertical():
    """The riser alone is 0.17 wavelength: a short monopole on its radials,
    strongly capacitive, where the default L with its top wire sits near
    resonance."""
    z_l = complex(MomwireEngine(get_builder(INVL)(), ground=None).impedance()[0])
    z_v = complex(
        MomwireEngine(_builder(INVL, horiz_frac=0.0), ground=None).impedance()[0]
    )
    assert math.isfinite(z_v.real) and math.isfinite(z_v.imag)
    assert 0.0 < z_v.real < z_l.real
    assert z_v.imag < -100.0 < z_l.imag
