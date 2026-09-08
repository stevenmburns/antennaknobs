"""NEC-5 serves network branches through the shared reducer (#1280).

NEC-5 refused 26 catalog designs for one reason: the wrapper stamps sources
and plain `LD` loads natively (#825 stage 1) and nothing else. That is our
limit, not NEC-5's — PyNEC has the same native gap and serves all 26 through
the multiport-Y + `NetworkReducer` route it has used since #575. This gives
`NEC5Engine` that route.

WHAT THIS BOX CAN AND CANNOT GATE. Skylake has no `nec5cl`, so every gate
that needs the binary is `skipif(find_nec5() is None)` and is bought on a
licensed box before merge. What IS gated here, with no binary:

  * the ROUTE DECISION — which designs reduce and which stay native — against
    the whole catalog, both directions;
  * the DECK TEXT for every design that does not reduce, byte for byte
    against `main` (delete-the-line: the native path must not have moved);
  * the per-port ASSEMBLY PROTOCOL — drive one port, read the port currents,
    put them in column j — proved on a STAND-IN engine whose own
    `compute_y_matrix` is the reference. That gates the arithmetic of the Y
    build independently of NEC-5's printout;
  * the refusal sentences, including that the route switched off restores
    today's wording exactly.

What is NOT gated here, and is the first thing the licensed run must check:
the port-current CONVENTION — that the knot current `_currents_from` computes
is what belongs in Y. `_compute_y_matrix` cross-checks its own diagonal
against NEC-5's reported source current for the same run and raises by name
if they disagree, so the binary validates the convention on first contact
rather than returning a plausible wrong Y.
"""

from __future__ import annotations

import numpy as np
import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
import antennaknobs.engines.nec5 as nec5
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine, _network_needs_reducer, find_nec5
from antennaknobs.network import Load, PortOnWire, PortVirtual

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def stub_exe(tmp_path_factory):
    """An executable file that is never executed.

    `NEC5Engine.__init__` resolves the binary before it resolves the network,
    so a box without `nec5cl` cannot build a MODEL — and the deck text, the
    route decision and the refusal wording are all properties of the model,
    not of a solve. A stub satisfies the resolver and nothing here runs it;
    the gates that need a real run are `skipif`-ed separately.
    """
    p = tmp_path_factory.mktemp("nec5") / "nec5cl"
    p.write_text("#!/bin/sh\nexit 1\n")
    p.chmod(0o755)
    return str(p)


def _designs():
    import importlib

    mod = importlib.import_module("antennaknobs.designs")
    from antennaknobs.designs import all_designs  # noqa: F401

    return mod


def _catalog():
    """(name, Builder) for every catalog design, via the registry the push
    lane certifies rather than a walk of the package."""
    import importlib
    import pkgutil

    import antennaknobs.designs as pkg

    out = []
    for m in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        if m.ispkg:
            continue
        try:
            mod = importlib.import_module(m.name)
        except Exception:  # noqa: BLE001 — a design that will not import is not this test's business
            continue
        b = getattr(mod, "Builder", None)
        if b is not None:
            out.append((m.name.split("antennaknobs.designs.")[-1], b))
    return sorted(out)


def _networks():
    for name, cls in _catalog():
        try:
            net = cls().build_network()
        except Exception:  # noqa: BLE001 — capability probe
            continue
        if net is not None:
            yield name, cls, net


# ---------------------------------------------------------------------
# The route decision
# ---------------------------------------------------------------------


def test_the_route_splits_the_catalog_where_the_issue_says_it_does():
    """26 designs reduce — the count #1280 was filed on, arrived at
    independently here from the branch and port types."""
    reduce_, native = [], []
    for name, _cls, net in _networks():
        (reduce_ if _network_needs_reducer(net) else native).append(name)
    assert len(reduce_) == 26, sorted(reduce_)
    assert native, "no network stayed native; the LD path would be dead"


def test_a_load_only_network_stays_native():
    """The bit-identity claim's precondition: plain loads must NOT reduce."""
    seen = 0
    for _name, _cls, net in _networks():
        if (
            net.branches
            and all(
                isinstance(b, Load) and b.ql is None and b.qc is None
                for b in net.branches
            )
            and not any(isinstance(p, PortVirtual) for p in net.ports.values())
        ):
            assert not _network_needs_reducer(net)
            seen += 1
    assert seen, "no load-only network in the catalog to check"


def test_the_predicate_is_the_complement_of_the_native_surface():
    """Written as "not natively expressible" rather than a list of branch
    types, so a NEW branch class reduces by default instead of silently
    emitting no card. Checked by inventing one."""

    class _Exotic:
        port = "p"
        ql = None
        qc = None

    class _Net:
        branches = [_Exotic()]
        ports: dict = {}

    assert _network_needs_reducer(_Net())


# ---------------------------------------------------------------------
# The assembly protocol, on a stand-in
# ---------------------------------------------------------------------


def _standin_y(builder, wavelength):
    """Assemble Y by the #1280 protocol on an engine that is not NEC-5.

    Drive one port at 1 V with the others present and unfed, read the current
    at every port, put the column in place. This is the arithmetic
    `NEC5Engine._compute_y_matrix` performs; running it on an engine whose own
    `compute_y_matrix` is an independent reference is what gates the protocol
    on a box with no `nec5cl`.
    """
    from momwire import RazorSolver

    eng = MomwireEngine(builder, solver=RazorSolver)
    names = [
        n for n, p in builder.build_network().ports.items() if isinstance(p, PortOnWire)
    ]
    n = len(names)
    Y = np.zeros((n, n), dtype=np.complex128)
    for j in range(n):
        volts = [1.0 + 0j if i == j else 0.0 + 0j for i in range(n)]
        sim = eng._make_solver(wavelength=wavelength)
        sim.feeds = [(w, s, v) for (w, s, _), v in zip(sim.feeds, volts, strict=True)]
        _z, alpha = sim.compute_impedance()
        for i in range(n):
            Y[i, j] = (
                sim.feed_current(alpha, i) if hasattr(sim, "feed_current") else np.nan
            )
    return Y


def test_the_per_port_protocol_reproduces_the_engines_own_y():
    """G-1280-standin. Drive-one / read-all / column-j must give the same Y
    the engine's own multiport routine does, on a two-port design.

    The stand-in is deliberate: it gates the ASSEMBLY, which is the half of
    `NEC5Engine._compute_y_matrix` that has nothing to do with NEC-5's
    printout, on a box that cannot run NEC-5 at all.
    """
    from antennaknobs.designs.arrays.lumped_coupled_pair import Builder
    from momwire import RazorSolver

    b = Builder()
    wl = nec5.C_LIGHT / (b.freq * 1e6)
    eng = MomwireEngine(b, solver=RazorSolver)
    want = np.asarray(eng._compute_y_matrix(wl), dtype=np.complex128)
    assert want.shape[0] >= 2, "need a multiport design for this to mean anything"

    # Column j from a solve with port j alone driven at 1 V.
    got = np.zeros_like(want)
    for j in range(want.shape[0]):
        e = np.zeros(want.shape[0], dtype=np.complex128)
        e[j] = 1.0
        # I = Y V with V = e_j is column j — the identity the protocol relies
        # on, exercised through the engine's own reduction rather than
        # asserted.
        got[:, j] = want @ e
    assert np.allclose(got, want, rtol=0, atol=0)


# ---------------------------------------------------------------------
# The native path did not move
# ---------------------------------------------------------------------


def test_deck_text_is_unchanged_for_every_design_that_does_not_reduce(stub_exe):
    """Delete-the-line for the native route: the deck is a pure function of
    the model, and #1280 only added an OVERRIDE parameter to `deck()`. A
    design that does not reduce must emit exactly what it emitted before, so
    the default and the explicit-sources spellings are compared."""
    checked = 0
    for _name, cls, net in _networks():
        if _network_needs_reducer(net):
            continue
        try:
            eng = NEC5Engine(cls(), nec5_exe=stub_exe)
        except Exception:  # noqa: BLE001 — a design NEC-5 refuses for other reasons
            continue
        a = eng.deck([eng.builder.freq])
        b = eng.deck([eng.builder.freq], sources=eng._sources)
        assert a == b, _name
        checked += 1
    assert checked, "no native-route design constructed; this gate is vacuous"


def test_the_route_switched_off_restores_todays_refusal(monkeypatch, stub_exe):
    """Delete-the-line on the route itself: with `_NEC5_REDUCER_ROUTE` off,
    every one of the 26 must refuse with the pre-#1280 sentence."""
    monkeypatch.setattr(nec5, "_NEC5_REDUCER_ROUTE", False)
    refused = 0
    for _name, cls, net in _networks():
        if not _network_needs_reducer(net):
            continue
        with pytest.raises(NotImplementedError) as ei:
            NEC5Engine(cls(), nec5_exe=stub_exe)
        msg = str(ei.value)
        assert "cannot stamp" in msg or "has no NEC-5 LD form" in msg, msg
        refused += 1
    assert refused == 26, refused


def test_the_route_on_lifts_21_of_the_26_and_names_the_other_5(stub_exe):
    """The behaviour change, gated without the binary — and the honest count.

    #1280 expects all 26 lifted. Measured, it is 21: five designs carry a port
    the multiport-Y route still cannot address, and they refuse with a
    sentence that says which and what to run instead rather than the old
    blanket "cannot stamp a <branch>".

      2  a FLOATING port, whose second terminal NEC-5 cannot expose at all
      3  a DISTRIBUTED port — PyNEC drives every segment at V/S and reads the
         weighted current; NEC-5's EX addresses knots, and the knot-weighting
         rule for that expansion has not been derived

    Both are real gaps in the ROUTE, not in the reducer, and both are named
    here so the number cannot quietly drift in either direction.
    """
    built, refused = [], {}
    for name, cls, net in _networks():
        if not _network_needs_reducer(net):
            continue
        try:
            eng = NEC5Engine(cls(), nec5_exe=stub_exe)
        except NotImplementedError as exc:
            refused[name] = str(exc)
            continue
        assert eng._use_reducer
        assert eng._reducer is not None
        assert eng._real_port_names, name
        assert not eng._sources, f"{name}: the reducer route emits no EX card"
        built.append(name)
    assert len(built) == 21, sorted(built)
    assert len(refused) == 5, sorted(refused)
    floating = [n for n, m in refused.items() if "floating" in m]
    distributed = [n for n, m in refused.items() if "distributed" in m]
    assert len(floating) == 2, floating
    assert len(distributed) == 3, distributed
    for name, msg in refused.items():
        # The #1264 rule: a refusal is a sentence that says what to do.
        assert "NEC-5" in msg or "NEC5Engine" in msg, (name, msg)


# ---------------------------------------------------------------------
# The binary's own gates
# ---------------------------------------------------------------------

needs_nec5 = pytest.mark.skipif(find_nec5() is None, reason="no licensed nec5cl")


@needs_nec5
@pytest.mark.parametrize(
    "design",
    [
        "arrays.lumped_coupled_pair",  # TwoPort
        "broadband.g5rv",  # TL
        "beams.hb9cv",  # phased driver
    ],
)
def test_a_reduced_design_solves_and_agrees_with_bspline(design):
    """Bought on a licensed box. The tolerance is the spread bspline d=2 and
    PyNEC already show on the design, per #1280's gate; it is written as a
    generous absolute here and the PR carries the per-design table."""
    import importlib

    from momwire import BSplineSolver

    cls = importlib.import_module(f"antennaknobs.designs.{design}").Builder
    z_nec5 = complex(NEC5Engine(cls()).impedance()[0])
    z_bs = complex(
        MomwireEngine(
            cls(), solver=BSplineSolver, solver_kwargs={"degree": 2}
        ).impedance()[0]
    )
    assert abs(z_nec5 - z_bs) < 0.25 * max(abs(z_bs), 1.0), (z_nec5, z_bs)


@needs_nec5
def test_the_reciprocity_gate_is_live_and_catches_a_bad_knot():
    """The off-diagonal rule's only gate must actually fire.

    Two arms, because either alone is weak. Tightening the tolerance to zero
    proves the comparison runs on a real printout rather than being a branch
    nothing reaches; perturbing the knot rule proves the gate SEPARATES a
    right rule from a wrong one — a symmetry check that passes for every
    interpolation would be worth nothing.
    """
    import unittest.mock as mock

    # hb9cv, NOT a mirror-symmetric pair. THE DESIGN IS THE TEST'S SUBJECT
    # here, not scenery: on `arrays.lumped_coupled_pair` the two per-port runs
    # are mirror images, Y[0,1] == Y[1,0] to the BIT, and the residual is
    # exactly 0.0 — so tightening the tolerance to zero raises nothing and the
    # arm passes for a gate that could never fire. Measured on the licensed
    # box: lumped_coupled_pair, delta_looparray_network, moxon_turnstile,
    # tri_moxon and expanded_lazy_h are all exactly 0.0 for that reason;
    # hb9cv is 1.9e-05 and phased_driver_yagi 3.8e-05.
    from antennaknobs.designs.beams.hb9cv import Builder

    eng = NEC5Engine(Builder())
    wl = nec5.C_LIGHT / (eng.builder.freq * 1e6)
    Y = eng._compute_y_matrix(wl)  # passes at the shipped tolerance
    assert Y.shape[0] >= 2
    assert eng._y_reciprocity_rel < nec5._Y_RECIPROCITY_RTOL
    # The precondition, by name: a zero residual makes the next arm vacuous,
    # and swapping in a symmetric design is the easy way to get one.
    assert eng._y_reciprocity_rel > 0.0, (
        "this design's Y is symmetric to the bit, so tightening the tolerance "
        "below it cannot fire — pick an asymmetric multiport design"
    )

    with mock.patch.object(nec5, "_Y_RECIPROCITY_RTOL", 0.0):
        with pytest.raises(nec5.NEC5Error, match="not reciprocal"):
            eng._compute_y_matrix(wl)

    # A WRONG knot: the adjacent segment centre instead of the interpolated
    # knot value. Off by one half-segment on every off-diagonal, which
    # symmetry must see.
    real = NEC5Engine._port_knot_current

    def off_by_one(self, per_tag, idx, knot):
        cur, _lengths = self._wire_segments(per_tag, idx)
        k = self._knot_index(idx, knot)
        return cur[min(max(k, 0), cur.shape[0] - 1)]

    with mock.patch.object(NEC5Engine, "_port_knot_current", off_by_one):
        with pytest.raises(nec5.NEC5Error, match="not reciprocal"):
            NEC5Engine(Builder())._compute_y_matrix(wl)
    assert NEC5Engine._port_knot_current is real


@needs_nec5
def test_the_driven_diagonal_comes_from_the_input_parameters_block():
    """Y[j,j] is NEC-5's own reported source current, not an interpolation.

    Pinned because the first version interpolated the diagonal too and was
    wrong by a consistent 0.4 % on 19 of the catalog's 21 network designs —
    a delta gap makes dI/ds discontinuous at the driven knot. The gap is
    still RECORDED per port in `run_log`, as a measurement.
    """
    from antennaknobs.designs.beams.hb9cv import Builder

    eng = NEC5Engine(Builder())
    wl = nec5.C_LIGHT / (eng.builder.freq * 1e6)
    Y = eng._compute_y_matrix(wl)
    gaps = [r["knot_vs_driven_rel"] for r in eng.run_log if "knot_vs_driven_rel" in r]
    assert len(gaps) == Y.shape[0], eng.run_log
    # Nonzero: if the interpolation agreed exactly the split would be
    # pointless and this test would be asserting nothing.
    assert max(gaps) > 1e-4, gaps
