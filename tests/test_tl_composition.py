"""The transmission-line network composition must match NEC's native tl_card.

antennaknobs can drive a transmission line two ways:
  * the legacy `build_tls()` path -> a native NEC `tl_card` on PyNECEngine
    (the line is solved SIMULTANEOUSLY with the MoM currents -- the gold
    standard for how a line shapes the RADIATING currents), and
  * the `build_network()` spec path -> the engine-agnostic NetworkReducer
    (extract the multiport Y at the real ports, reduce, re-excite), used by
    BOTH MomwireEngine and PyNECEngine.

If the reducer reproduces native `tl_card`, then composing an ideal line is
faithful -- the line loads the driving point AND shapes the far field
correctly. This test pins that equivalence on a minimal two-dipoles-through-
a-line array (front driven; rear reachable only through the line), which is
the smallest geometry that exercises current transfer through the element.

History: this was written to chase a suspected far-field composition bug in
the reducer. There was none -- reducer == native tl_card to <0.1 dB. Keep it
so a future refactor of NetworkReducer can't silently regress that.
"""

import numpy as np
import pytest

pytest.importorskip("PyNEC")

from antennaknobs import AntennaBuilder  # noqa: E402
from antennaknobs.network import Driven, Network, PortAtEdge, TL  # noqa: E402
from antennaknobs.engines import MomwireEngine, PyNECEngine  # noqa: E402
from momwire import BSplineSolver  # noqa: E402

FREQ = 28.57
WL = 299.792458 / FREQ
SPACING = 0.13 * WL
Z0 = 50.0
LEN = SPACING
Q = 0.25 * WL
BASE = 7.0
EPS = 0.05
DEG2 = {"degree": 2}


class _NetBuilder(AntennaBuilder):
    """build_network single-ended TL -> shared NetworkReducer (both engines)."""

    default_params = {"design_freq": FREQ, "freq": FREQ}

    def build_wires(self):
        tups = []
        for x, name in ((-SPACING, "rear"), (0.0, "front")):
            L, C0, C1, R = (x, -Q, BASE), (x, -EPS, BASE), (x, EPS, BASE), (x, Q, BASE)
            tups += [
                (L, C0, 11, None, None),
                (C0, C1, 1, None, name),
                (C1, R, 11, None, None),
            ]
        return tups

    def build_network(self):
        return Network(
            ports={"rear": PortAtEdge("rear"), "front": PortAtEdge("front")},
            branches=[TL(a="front", b="rear", z0=Z0, length=LEN, transposed=False)],
            sources=[Driven(port="front", voltage=1 + 0j)],
        )


class _TlsBuilder(AntennaBuilder):
    """legacy build_tls -> native NEC tl_card (oracle) / momwire _apply_tls."""

    default_params = {"design_freq": FREQ, "freq": FREQ}

    def build_wires(self):
        tups = []
        for x, name in ((-SPACING, "rear"), (0.0, "front")):
            L, C0, C1, R = (x, -Q, BASE), (x, -EPS, BASE), (x, EPS, BASE), (x, Q, BASE)
            exc = (1 + 0j) if name == "front" else None
            tups += [(L, C0, 11, None), (C0, C1, 1, exc), (C1, R, 11, None)]
        self.tls = [(5, 1, 2, 1, Z0, LEN)]  # front-center seg -> rear-center seg
        return tups

    def build_tls(self):
        return self.tls


def _pattern(eng):
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    rings = np.array(ff.rings)
    return ff.max_gain, rings[89, 0], rings[89, 180]  # peak, horizon +x, horizon -x


def _momwire(b):
    return MomwireEngine(b, solver=BSplineSolver, solver_kwargs=DEG2, ground=None)


def test_reducer_matches_native_tl_card_same_engine():
    """On PyNEC, the NetworkReducer TL and the native tl_card must agree to a
    tight tolerance -- same MoM, so any gap is the composition itself."""
    g_red, f_red, b_red = _pattern(PyNECEngine(_NetBuilder(), ground=None))
    g_nat, f_nat, b_nat = _pattern(PyNECEngine(_TlsBuilder(), ground=None))
    assert abs(g_red - g_nat) < 0.1, (g_red, g_nat)
    assert abs(f_red - f_nat) < 0.15
    assert abs(b_red - b_nat) < 0.15


def test_reducer_matches_native_tl_card_impedance():
    """The native tl_card driving-point impedance must equal the reducer's —
    the strict cross-validation dropped back in issue #63, restored by the
    input-parameters readout fix (issue #283). The TL terminates on the
    DRIVEN segment here, so a wire-only current readout would be off by ~3×
    (105+2j vs the true 36−29j): most of the source current leaves through
    the line, and NEC's ANTENNA INPUT PARAMETERS account for it."""
    z_red = PyNECEngine(_NetBuilder(), ground=None).impedance()[0]
    z_nat = PyNECEngine(_TlsBuilder(), ground=None).impedance()[0]
    # Reducer Y comes from N separate NEC solves vs native's single baked
    # context; they match to ~1e-5 relative, far below any physical scale.
    assert abs(z_red - z_nat) / abs(z_nat) < 1e-4, (z_red, z_nat)


def test_momwire_reducer_matches_native_tl_card_reference():
    """MomwireEngine's reducer TL far field must match NEC's native tl_card
    reference within a cross-engine MoM tolerance."""
    g_mom, f_mom, b_mom = _pattern(_momwire(_NetBuilder()))
    g_nat, f_nat, b_nat = _pattern(PyNECEngine(_TlsBuilder(), ground=None))
    assert abs(g_mom - g_nat) < 0.4, (g_mom, g_nat)
    assert abs(f_mom - f_nat) < 0.4
    assert abs(b_mom - b_nat) < 0.5


def test_momwire_two_tl_paths_agree():
    """MomwireEngine's own reducer and _apply_tls paths must give one answer."""
    g_red, f_red, _ = _pattern(_momwire(_NetBuilder()))
    g_tls, f_tls, _ = _pattern(_momwire(_TlsBuilder()))
    assert abs(g_red - g_tls) < 0.1, (g_red, g_tls)
    assert abs(f_red - f_tls) < 0.15
