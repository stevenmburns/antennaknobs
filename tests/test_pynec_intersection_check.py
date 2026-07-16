"""Issue #409: PyNECEngine(check_intersections=False) disables nec2++'s
wire/segment intersection validator.

nec2++ (the PyNEC kernel) fatally rejects a deck whose wires pass within a
radius-sum of one another — a validation NEC-2 / nec2c do not perform, so real
decks with closely-spaced / crossing wires raise on geometry those kernels
solve fine. `check_intersections=False` calls the wrapped
`c_geometry::set_intersection_check(False)` knob (pynec-accel >=1.7.5) to match
that permissiveness.
"""

from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder, Wire, WireSpec
from antennaknobs.engines import MomwireEngine, PyNECEngine
from momwire import SinusoidalSolver

FREQ = 300.0  # MHz -> ~1 m wavelength


def _crossing_builder():
    """A driven half-wave dipole along x with a parasitic wire crossing it at
    right angles in the same z-plane, offset off-centre so the two wires
    genuinely intersect (distance 0 < radius-sum) without sharing a node —
    exactly what trips nec2++'s 'WIRE INTERSECTS WIRE' check."""

    spec = WireSpec(radius=0.005)

    class _X(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ})

        def build_wires(self):
            return [
                # driven dipole: two arms meeting at the fed centre segment
                Wire((-0.25, 0.0, 0.0), (0.0, 0.0, 0.0), 11, None, None, spec),
                Wire((0.0, 0.0, 0.0), (0.25, 0.0, 0.0), 11, 1 + 0j, None, spec),
                # parasitic crossing the +x arm at (0.1, 0, 0)
                Wire((0.1, -0.25, 0.0), (0.1, 0.25, 0.0), 21, None, None, spec),
            ]

    return _X()


def _knob_wrapped():
    """True iff this pynec-accel wraps set_intersection_check (>=1.7.5)."""
    import PyNEC

    return hasattr(PyNEC.nec_context().get_geometry(), "set_intersection_check")


def test_default_rejects_crossing_geometry():
    with pytest.raises(RuntimeError, match="GEOMETRY DATA ERROR"):
        PyNECEngine(_crossing_builder(), ground="free")


def test_check_off_solves_and_tracks_momwire():
    if not _knob_wrapped():
        pytest.skip("pynec-accel <1.7.5: set_intersection_check not wrapped")

    builder = _crossing_builder()
    z_pynec = PyNECEngine(
        builder, ground="free", check_intersections=False
    ).impedance()[0]
    z_sin = MomwireEngine(builder, solver=SinusoidalSolver, ground="free").impedance()[
        0
    ]

    # Finite, and the two NEC-family solves land in the same ballpark on the
    # geometry both now accept (sinusoidal basis ≈ nec2++). Loose bound: the
    # point is that the recovered PyNEC solve is trustworthy, not a wild value.
    assert abs(z_pynec) < 1e5
    assert abs(z_pynec - z_sin) / abs(z_sin) < 0.15
