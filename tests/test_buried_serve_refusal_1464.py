"""AK#1464: the construction-time buried pre-flight is momwire's own verdict.

`_below_reach_refusal` used to pass polyline VERTICES to momwire's
`below_reach_refusal`. A crossing node's vertex sits exactly in the plane, so
two nodes at different places paired at theta = 0. Every multi-node deck was
refused on the grazing floor for the wrong reason, while the fill's interior
nodes read 0.0967 deg on the deck below.

With a solver that can say (momwire#1055, `BSplineSolver.buried_serve_refusal`),
the engine asks it and gets the fill's own sentence. The vertex helper stays
the fallback for a solver that cannot.
"""

import numpy as np
import pytest

from antennaknobs.engines.momwire import MomwireEngine, _below_reach_refusal
from antennaknobs.file_designs import builder_from_file

momwire = pytest.importorskip("momwire")

SOIL_A = ("finite", 13.0, 0.005)
SOIL_A_EPS = (13.0, 0.005)

TWO_NODE = """CM two base-fed verticals 12 m apart, each over its own crossing node
CE
GW 1 10 0 0 0 0 0 20 .001
GW 2 1 0 0 0 0 0 -0.3 .001
GW 3 5 0 0 -0.3 5 0 -0.3 .001
GW 4 5 0 0 -0.3 -5 0 -0.3 .001
GW 5 5 0 0 -0.3 0 5 -0.3 .001
GW 6 5 0 0 -0.3 0 -5 -0.3 .001
GW 11 10 0 12 0 0 12 20 .001
GW 12 1 0 12 0 0 12 -0.3 .001
GW 13 5 0 12 -0.3 5 12 -0.3 .001
GW 14 5 0 12 -0.3 -5 12 -0.3 .001
GW 15 5 0 12 -0.3 0 17 -0.3 .001
GW 16 5 0 12 -0.3 0 7 -0.3 .001
GE -1
GN 2 0 0 0 13 .005
EX 0 1 1 0 1 0
FR 0 1 0 0 3.5 0
EN
"""

TWO_CONTACT = """CM two ground-contact verticals 12 m apart, nothing buried
CE
GW 1 10 0 0 0 0 0 20 .001
GW 2 10 0 12 0 0 12 20 .001
GE 1
GN 2 0 0 0 13 .005
EX 0 1 1 0 1 0
FR 0 1 0 0 3.5 0
EN
"""

# The same two nodes as polylines, for the vertex fallback.
TWO_NODE_POLYLINES = [
    np.array([(0.0, 0.0, 20.0), (0.0, 0.0, 0.0)]),
    np.array([(0.0, 0.0, 0.0), (0.0, 0.0, -0.3), (5.0, 0.0, -0.3)]),
    np.array([(0.0, 12.0, 20.0), (0.0, 12.0, 0.0)]),
    np.array([(0.0, 12.0, 0.0), (0.0, 12.0, -0.3), (5.0, 12.0, -0.3)]),
]


def _builder(tmp_path, text, name):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    b = builder_from_file(str(p))
    return b() if isinstance(b, type) else b


def test_the_submodule_carries_the_exact_preflight():
    """These gates exercise the exact path only if the pointer has it."""
    assert hasattr(momwire.BSplineSolver, "buried_serve_refusal")


def test_a_two_node_deck_is_refused_for_its_real_reason(tmp_path):
    """The engine names the crossing scope (momwire#1054), not a grazing
    floor that the fill's own nodes clear."""
    b = _builder(tmp_path, TWO_NODE, "two_node.nec")
    with pytest.raises(ValueError) as exc:
        MomwireEngine(b, ground=SOIL_A)
    why = str(exc.value)
    assert "ONE crossing node per deck" in why, why
    assert "grazing floor" not in why, why


def test_the_vertex_fallback_still_over_refuses_the_same_deck():
    """The hole the exact path closes, pinned on the fallback a solver without
    the method still takes: two in-plane nodes pair at theta = 0 deg."""
    why = _below_reach_refusal(
        TWO_NODE_POLYLINES,
        0.0,
        SOIL_A_EPS,
        "sommerfeld",
        3.5,
        solver_factory=object,
    )
    assert why is not None and "theta = 0 deg" in why, why


def test_nothing_strictly_below_is_never_asked(tmp_path):
    """Two ground-contact verticals have in-plane vertices and no buried wire,
    so there is no below/below pair to bound on either path."""
    b = _builder(tmp_path, TWO_CONTACT, "two_contact.nec")
    MomwireEngine(b, ground=SOIL_A)
    polylines = [
        np.array([(0.0, 0.0, 20.0), (0.0, 0.0, 0.0)]),
        np.array([(0.0, 12.0, 20.0), (0.0, 12.0, 0.0)]),
    ]
    assert _below_reach_refusal(polylines, 0.0, SOIL_A_EPS, "sommerfeld", 3.5) is None
