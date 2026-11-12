"""The optimizer's opt-in moved-load fast path (momwire#1915, `port_sites`).

A trial that moves only one load's position along one wire is served from a
cached `PortSites` per (everything else, frequency) instead of a rebuild. The
oracle is the full AK rebuild of the same engine (whole-wire, the load at that
position), solved through ``impedance_sweep`` with ``port_sites`` forbidden.

Every geometry and value here is invented. The design is an inverted L in
free space: a vertical wire fed at its middle, a horizontal top
wire carrying a coil, and a 50 ohm line from the rig to the feed (the station
network, stamped on the antenna's port Y by the trial's own reducer). The coil
position is a knob in two spellings: a percentage of the top wire's length,
and an absolute arclength in metres from the top wire's start.

Skips by name where the installed momwire has no ``port_sites`` (the 0.90.0
submodule pointer and PyPI pin): there this path declines every trial and
nothing here can be checked.
"""

from types import MappingProxyType

import numpy as np
import pytest
from momwire import BSplineSolver

from antennaknobs import AntennaBuilder, port_sites
from antennaknobs.band_opt import builder_sweep_fn
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import TL, Driven, Load, Network, PortOnWire, PortVirtual
from antennaknobs.network import Wire as W

needs_port_sites = pytest.mark.skipif(
    not port_sites.available(), reason=port_sites.NO_PORT_SITES
)

H = 7.3  # vertical height, m
TOP = 9.1  # top wire length, m
FREQS = [6.95, 7.12, 7.27]
# Off-knot on the top wire's 23 segments (knots at k/23), and off-centre.
PCTS = [21.37, 38.11, 55.62, 71.94]
RTOL = 1e-9


class _CoilL(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 7.12,
            "design_freq": 7.12,
            "coil_pct": 30.0,
            "coil_m": None,
            "coil_uh": 4.7,
            "line_m": 6.4,
            "foot_z": 0.4,
        }
    )

    def build_wires(self):
        return [
            W((0.0, 0.0, self.foot_z), (0.0, 0.0, H), n_seg=17, name="vert"),
            W((0.0, 0.0, H), (TOP, 0.0, H), n_seg=23, name="top"),
        ]

    def coil_at(self) -> float:
        if self.coil_m is not None:
            return float(self.coil_m) / TOP
        return float(self.coil_pct) / 100.0

    def build_network(self):
        return Network(
            ports={
                "feed": PortOnWire("feed", wire="vert"),
                "coil": PortOnWire("coil", wire="top", at=self.coil_at()),
                "rig": PortVirtual("rig"),
            },
            branches=[
                Load(port="coil", r=1.3, l=self.coil_uh * 1e-6),
                TL("rig", "feed", z0=50.0, length=self.line_m, vf=0.66),
            ],
            sources=[Driven(port="rig")],
        )


def _builder(**params):
    return _CoilL(dict(_CoilL.default_params, **params))


@pytest.fixture
def forbid_port_sites(monkeypatch):
    """``port_sites`` counted, and refused while ``state["forbid"]``."""
    real = BSplineSolver.port_sites
    state = {"calls": 0, "forbid": False}

    def spy(self, *a, **k):
        if state["forbid"]:
            raise AssertionError("the rebuild side reached port_sites")
        state["calls"] += 1
        return real(self, *a, **k)

    monkeypatch.setattr(BSplineSolver, "port_sites", spy)
    return state


def _rebuild(state, **params):
    """The oracle: a whole-wire engine's own ``impedance_sweep``."""
    state["forbid"] = True
    try:
        eng = MomwireEngine(_builder(**params), **port_sites.engine_kwargs())
        assert not getattr(eng, "_split_wires", None)
        return np.asarray(eng.impedance_sweep(FREQS))
    finally:
        state["forbid"] = False


def _served(session) -> int:
    """Trials answered by PortSites: from the cache, or by building their base."""
    return session.counts["fast"] + session.counts["first"]


def _fast(session, state, **params):
    eng = MomwireEngine(_builder(**params), **port_sites.engine_kwargs())
    before = _served(session)
    zs = session.sweep(eng, FREQS)
    return zs, _served(session) > before


def _rel(a, b):
    return float(np.max(np.abs(a - b) / np.abs(b)))


@needs_port_sites
def test_fast_path_matches_the_rebuild_at_off_knot_percentages(forbid_port_sites):
    """Per band, the driven Z at the rig (after the line) via the cache equals
    the rebuild with the coil there, at four off-knot positions."""
    s = port_sites.PortSitesSession()
    _z, fast = _fast(s, forbid_port_sites, coil_pct=PCTS[0])
    assert not fast  # nothing to compare with yet: a rebuild
    worst = 0.0
    for pct in PCTS[1:] + PCTS[:1]:
        zs, fast = _fast(s, forbid_port_sites, coil_pct=pct)
        assert fast, s.summary()
        worst = max(worst, _rel(zs, _rebuild(forbid_port_sites, coil_pct=pct)))
    assert worst <= RTOL, worst
    # One factorisation per band, built by the second trial as its own solve
    # (no rebuild beside it), then served three more times.
    assert s.counts == {"fast": 3, "first": 1, "rebuild": 1, "built": len(FREQS)}
    assert forbid_port_sites["calls"] == len(FREQS)


@needs_port_sites
def test_an_arclength_knob_in_metres_is_the_same_load(forbid_port_sites):
    """The metres spelling of the same positions gives the percentage's Z, on
    the fast path and against the rebuild."""
    s = port_sites.PortSitesSession()
    _fast(s, forbid_port_sites, coil_m=0.2 * TOP)
    for pct in PCTS:
        m = pct / 100.0 * TOP
        zs, fast = _fast(s, forbid_port_sites, coil_m=m)
        assert fast
        assert _rel(zs, _rebuild(forbid_port_sites, coil_pct=pct)) <= RTOL


@needs_port_sites
def test_the_position_is_read_and_from_the_wire_start(forbid_port_sites):
    """Adversarial: a fast path that kept the first position, or measured the
    arclength from the wire's far end, fails here. The two mirror positions
    differ by far more than the gate, so the gate can tell them apart."""
    s = port_sites.PortSitesSession()
    _fast(s, forbid_port_sites, coil_pct=50.0)
    near, _ = _fast(s, forbid_port_sites, coil_pct=17.3)
    far, fast = _fast(s, forbid_port_sites, coil_pct=82.7)
    assert fast and _served(s) == 2
    z_near = _rebuild(forbid_port_sites, coil_pct=17.3)
    z_far = _rebuild(forbid_port_sites, coil_pct=82.7)
    assert _rel(z_near, z_far) > 1e-3
    assert _rel(near, z_near) <= RTOL and _rel(far, z_far) <= RTOL
    assert _rel(near, far) > 1e-3


@needs_port_sites
def test_another_knob_moving_builds_its_own_base(forbid_port_sites):
    """The network-only knob (the line) keeps the cached base, because the
    antenna's solver inputs did not move; a geometry knob gives a new base,
    which the trial builds as its own solve, and the oracle still holds."""
    s = port_sites.PortSitesSession()
    _fast(s, forbid_port_sites, coil_pct=30.0)
    _fast(s, forbid_port_sites, coil_pct=40.0)
    assert s.counts["first"] == 1 and s.counts["fast"] == 0
    zs, fast = _fast(s, forbid_port_sites, coil_pct=45.0, line_m=7.9)
    assert fast and s.counts["fast"] == 1  # the line is the reducer's
    assert _rel(zs, _rebuild(forbid_port_sites, coil_pct=45.0, line_m=7.9)) <= RTOL

    class _Taller(_CoilL):
        def build_wires(self):
            w = super().build_wires()
            return [w[0]._replace(p0=(0.0, 0.0, 0.3)), w[1]]

    def taller():
        return MomwireEngine(
            _Taller(dict(_CoilL.default_params, coil_pct=45.0)),
            **port_sites.engine_kwargs(),
        )

    zs = s.sweep(taller(), FREQS)
    assert s.counts == {"fast": 1, "first": 2, "rebuild": 1, "built": 2 * len(FREQS)}
    forbid_port_sites["forbid"] = True
    try:
        ref = np.asarray(taller().impedance_sweep(FREQS))
    finally:
        forbid_port_sites["forbid"] = False
    assert _rel(zs, ref) <= RTOL


@needs_port_sites
def test_declines_by_name_off_the_bspline_basis(forbid_port_sites):
    from momwire import SinusoidalGalerkinSolver

    s = port_sites.PortSitesSession()
    for pct in (30.0, 40.0):
        s.sweep(
            MomwireEngine(_builder(coil_pct=pct), solver=SinusoidalGalerkinSolver),
            FREQS,
        )
    assert s.counts["fast"] == 0 and s.counts["rebuild"] == 2
    (why,) = s.declined
    assert "B-spline basis only" in why


@needs_port_sites
def test_the_default_engine_splits_and_the_session_declines_it():
    """Off the fast path nothing changed: the default engine still splits the
    top wire at an off-site coil (AK#1519), and a session handed such an
    engine rebuilds and names why, instead of keying a moving mesh."""
    eng = MomwireEngine(_builder(coil_pct=38.11))
    assert "top" in eng._split_wires
    s = port_sites.PortSitesSession()
    s.sweep(eng, FREQS)
    assert s.counts["fast"] == 0
    assert any("AK#1519" in r for r in s.declined)


@needs_port_sites
def test_on_a_segment_centre_the_whole_wire_is_the_default_mesh():
    """At a site of the top wire's count the default engine keeps it whole
    too, so there the continuous model is main's model, bit for bit."""
    pct = 100.0 * 7.5 / 23  # the centre of segment 8 of 23
    a = MomwireEngine(_builder(coil_pct=pct))
    b = MomwireEngine(_builder(coil_pct=pct), **port_sites.engine_kwargs())
    assert not a._split_wires
    np.testing.assert_array_equal(a.impedance_sweep(FREQS), b.impedance_sweep(FREQS))


@needs_port_sites
def test_optimize_bands_takes_the_fast_path_and_counts_it(forbid_port_sites):
    """End to end through the CLI's sweep_fn: a three-band run on the coil
    position alone serves most trials from the cache."""
    from antennaknobs.web.optimize_bands import optimize_bands, parse_bands

    b = _builder()
    s = port_sites.PortSitesSession()
    res = optimize_bands(
        {"coil_pct": 30.0},
        [{"name": "coil_pct", "min": 10.0, "max": 90.0}],
        parse_bands(",".join(str(f) for f in FREQS)),
        sweep_fn=builder_sweep_fn(b, MomwireEngine, 50.0, port_sites=s),
        max_evals=14,
    )
    assert s.counts["fast"] >= 5, s.summary()
    assert s.counts["fast"] > s.counts["rebuild"]
    assert res["n_solves"] == _served(s) + s.counts["rebuild"]


@needs_port_sites
def test_slsqp_probes_from_a_base_find_the_position_and_reuse_it(forbid_port_sites):
    """A finite-difference stencil steps each knob from a common base, so no
    two consecutive trials differ in the position alone. The geometry knob
    (``foot_z``), the position (``coil_pct``) and a network value
    (``line_m``) are probed from base 0, then from base 1, then base 1 and a
    base-0 probe come round again. The position probe of base 0 fixes the
    moving port against base 0 (two trials back); after that every trial is
    answered by PortSites, and every one matches its own rebuild."""
    b0 = {"foot_z": 0.4, "coil_pct": 30.0, "line_m": 6.4}
    b1 = {"foot_z": 0.42, "coil_pct": 33.0, "line_m": 6.45}
    steps = {"foot_z": 0.01, "coil_pct": 0.5, "line_m": 0.1}

    def probe(base, knob):
        return {**base, knob: base[knob] + steps[knob]}

    seq = [
        ("rebuild", b0),
        ("rebuild", probe(b0, "foot_z")),
        ("first", probe(b0, "coil_pct")),
        ("fast", probe(b0, "line_m")),
        ("first", b1),
        ("first", probe(b1, "foot_z")),
        ("fast", probe(b1, "coil_pct")),
        ("fast", probe(b1, "line_m")),
        ("fast", b1),
        ("fast", {**b0, "coil_pct": 41.7}),
    ]
    s = port_sites.PortSitesSession()
    worst = 0.0
    for want, params in seq:
        before = dict(s.counts)
        zs = s.sweep(
            MomwireEngine(_builder(**params), **port_sites.engine_kwargs()), FREQS
        )
        moved = [k for k in ("fast", "first", "rebuild") if s.counts[k] != before[k]]
        assert moved == [want], (want, params, s.summary())
        worst = max(worst, _rel(zs, _rebuild(forbid_port_sites, **params)))
    assert worst <= RTOL, worst
    # Three antenna bases (b0, b1, b1 + foot), one factorisation per band each.
    assert s.counts["built"] == 3 * len(FREQS)


@needs_port_sites
def test_no_base_is_both_rebuilt_and_built(monkeypatch, forbid_port_sites):
    """A three-knob optimize run (geometry, position, network): builds never
    exceed the distinct (base, band) pairs, no key is built twice, and every
    rebuild is a trial from before the moving port was known, so a trial is
    never rebuilt AND built."""
    from antennaknobs.web.optimize_bands import optimize_bands, parse_bands

    built = []
    real = port_sites.PortSitesSession._build

    def spy(self, cls, kwargs, moving, wl):
        built.append((port_sites._sig(cls, kwargs, moving), float(wl)))
        return real(self, cls, kwargs, moving, wl)

    monkeypatch.setattr(port_sites.PortSitesSession, "_build", spy)
    s = port_sites.PortSitesSession()
    res = optimize_bands(
        {"foot_z": 0.4, "coil_pct": 30.0, "line_m": 6.4},
        [
            {"name": "foot_z", "min": 0.2, "max": 0.8},
            {"name": "coil_pct", "min": 10.0, "max": 90.0},
            {"name": "line_m", "min": 4.0, "max": 9.0},
        ],
        parse_bands(",".join(str(f) for f in FREQS)),
        sweep_fn=builder_sweep_fn(_builder(), MomwireEngine, 50.0, port_sites=s),
        max_evals=24,
    )
    assert len(built) == len(set(built)) == s.counts["built"]
    assert s.counts["built"] == len(FREQS) * s.counts["first"]
    assert set(s.declined) == {
        "no earlier trial differs from this one in one port's position only"
    }
    assert res["n_solves"] == _served(s) + s.counts["rebuild"]
    assert s.counts["fast"] > 0 and s.counts["rebuild"] <= 3, s.summary()


def test_off_unless_asked(monkeypatch):
    monkeypatch.delenv(port_sites.SEED_ENV, raising=False)
    assert not port_sites.asked(None)
    monkeypatch.setenv(port_sites.SEED_ENV, "1")
    assert port_sites.asked(None)
    assert not port_sites.asked(False)  # an explicit off wins over the seed
    assert port_sites.asked(True)


def test_without_a_session_the_sweep_is_the_engines_own(monkeypatch):
    """port_sites=None (the default) never builds a whole-wire engine nor
    reaches the session: the engine's own impedance_sweep, as on main."""
    seen = []

    def factory(builder, **kw):
        seen.append(kw)
        return MomwireEngine(builder, **kw)

    out = builder_sweep_fn(_builder(), factory, 50.0)({}, FREQS[:1])
    assert seen == [{}]
    ref = MomwireEngine(_builder()).impedance_sweep(FREQS[:1])
    np.testing.assert_array_equal(out["zs"], ref)


_JOIN, _FAR, _FOOT = (0.0, 0.0, H), (TOP, 0.0, H), (0.0, 0.0, 0.4)


class _CoilFirst(_CoilL):
    """The coil is the FIRST of three ports (coil, feed, a fixed trap), so the
    cached Y's moved row must be put back in front; ``top_rev`` / ``vert_rev``
    choose each wire's authored direction, so the moving port's walk sign
    differs from the feed's (issue #580)."""

    top_rev = False
    vert_rev = True
    link = False

    def build_wires(self):
        top = (_FAR, _JOIN) if self.top_rev else (_JOIN, _FAR)
        vert = (_JOIN, _FOOT) if self.vert_rev else (_FOOT, _JOIN)
        return [W(*top, n_seg=23, name="top"), W(*vert, n_seg=17, name="vert")]

    def build_network(self):
        return Network(
            ports={
                "coil": PortOnWire("coil", wire="top", at=self.coil_at()),
                "feed": PortOnWire("feed", wire="vert"),
                "trap": PortOnWire("trap", wire="vert", at=13.5 / 17),
                "rig": PortVirtual("rig"),
            },
            branches=[
                Load(port="coil", r=1.3, l=self.coil_uh * 1e-6),
                Load(port="trap", r=0.4, l=1.1e-6),
                TL("rig", "feed", z0=50.0, length=self.line_m, vf=0.66),
            ]
            # A line from the moving port to the trap's: a branch across two
            # antenna ports, the one place a port's walk sign shows in Z.
            + ([TL("coil", "trap", z0=300.0, length=2.3)] if self.link else []),
            sources=[Driven(port="rig")],
        )


@needs_port_sites
@pytest.mark.parametrize(
    ("top_rev", "vert_rev", "coil_dir", "link"),
    [(False, True, -1, False), (True, False, 1, False), (False, True, -1, True)],
)
def test_a_moving_port_ahead_of_the_others_and_walked_backwards(
    forbid_port_sites, top_rev, vert_rev, coil_dir, link
):
    """The oracle on a design whose moving port is feed 0 of 3, walked against
    (or with) its authored direction while the feed wire is walked the other
    way: the reorder and the walk signs are both exercised. With ``link`` a
    line joins the moving port to the trap's, which turns a dropped walk sign
    into a wrong Z (a one-port load is blind to it)."""
    cls = type(
        "_Variant",
        (_CoilFirst,),
        {"top_rev": top_rev, "vert_rev": vert_rev, "link": link},
    )

    def eng(pct):
        return MomwireEngine(
            cls(dict(_CoilL.default_params, coil_pct=pct)),
            **port_sites.engine_kwargs(),
        )

    e = eng(30.0)
    assert e._feed_names == ["coil", "feed", "trap"]
    assert e._feed_dirs[0] == coil_dir and e._feed_dirs[1] == -coil_dir
    s = port_sites.PortSitesSession()
    s.sweep(e, FREQS)
    worst = 0.0
    for pct in PCTS:
        zs = s.sweep(eng(pct), FREQS)
        forbid_port_sites["forbid"] = True
        try:
            ref = np.asarray(eng(pct).impedance_sweep(FREQS))
        finally:
            forbid_port_sites["forbid"] = False
        worst = max(worst, _rel(zs, ref))
    assert s._moving == 0
    assert s.counts == {
        "fast": len(PCTS) - 1,
        "first": 1,
        "rebuild": 1,
        "built": len(FREQS),
    }
    assert worst <= RTOL, worst


def _example():
    import antennaknobs.web.examples  # noqa: F401 — the registry first; it imports the adapter
    from antennaknobs.web.adapter import _make_example

    return _make_example("test.port_sites_coil_l", _CoilL)


@needs_port_sites
def test_the_workbench_seam_serves_moved_coils_from_the_cache(forbid_port_sites):
    """``momwire_bands`` (what /optimize evaluates) with a session: the second
    position is served fast, and equals a fresh session's first trial there,
    which is the adapter's own whole-wire rebuild."""
    ex = _example()
    s = port_sites.PortSitesSession()
    ex.momwire_bands({"coil_pct": 30.0}, FREQS, port_sites=s)
    out = ex.momwire_bands({"coil_pct": 61.3}, FREQS, port_sites=s)
    assert s.counts["first"] == 1
    forbid_port_sites["forbid"] = True
    ref_s = port_sites.PortSitesSession()
    ref = ex.momwire_bands({"coil_pct": 61.3}, FREQS, port_sites=ref_s)
    assert ref_s.counts == {"fast": 0, "first": 0, "rebuild": 1, "built": 0}
    assert _rel(np.asarray(out["zs"]), np.asarray(ref["zs"])) <= RTOL


@needs_port_sites
@pytest.mark.parametrize("ask", [None, True, False])
def test_optimize_endpoint_is_off_unless_asked(monkeypatch, forbid_port_sites, ask):
    """/optimize with bands: the tally rides on the result only when the
    request (or the server seed, here unset) asks; asked, trials go fast."""
    from fastapi.testclient import TestClient

    from antennaknobs.web import server

    monkeypatch.delenv(port_sites.SEED_ENV, raising=False)
    monkeypatch.setitem(server.EXAMPLES, "test.port_sites_coil_l", _example())
    opt = {
        "free": [{"name": "coil_pct", "min": 10.0, "max": 90.0}],
        "bands": [{"freq": f} for f in FREQS],
        "max_evals": 10,
    }
    if ask is not None:
        opt["port_sites"] = ask
    body = {"geometry": "test.port_sites_coil_l", "coil_pct": 30.0, "optimize": opt}
    res = TestClient(server.app).post("/optimize", json=body).json()
    assert "error" not in res, res
    if ask:
        assert res["port_sites"]["fast"] >= 3, res["port_sites"]
        assert forbid_port_sites["calls"] == len(FREQS)
    else:
        assert "port_sites" not in res
        assert forbid_port_sites["calls"] == 0
