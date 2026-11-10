"""AK#2241: the network reducer's sparse MNA path, for large circuit-only
networks, and its parity with the dense path every shipped design stays on.

`antennaknobs.mw.networks` assembles its MNA system dense and solves it with
LAPACK `zgesvx` below `_reduce.SPARSE_MIN_UNKNOWNS` (an n + m matrix
dimension), and sparse with SuperLU at and above it. The gates here:

* the A/B cases (`test_mw_networks_ab_2219.py`, bit for bit against momwire)
  all sit below the threshold, so that A/B is still of the dense path;
* an RLCG ladder (a synthetic RG-58-like line as N symmetric T sections in
  front of a fixed antenna Y) on the sparse path converges to the uniform
  line's analytic input impedance as 1/N², at N up to 4000 (16002 unknowns)
  in well under a second and a few tens of MB, where a dense A alone is
  3.8 GB;
* every A/B case, a chain of station-like networks and every catalog
  design's network, each FORCED through both paths, agree to 1e-12 relative
  (Z, Γ, excited voltages, p_in, budget watts), with rcond in the same decade;
* every refusal refuses identically on the sparse path, and a suspect solve
  warns identically;
* mutation controls: the parity checks fail when the sparse path drops
  equilibration's column scaling or mis-stamps one Group-2 term;
* end to end, a builder whose network is a ladder in front of a dipole
  solves through the momwire engine, single point and sweep, on the sparse
  path, matching the forced-dense answer.

Synthetic fixtures throughout.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import os
import pkgutil
import subprocess
import sys
import textwrap
import time
import warnings
from types import MappingProxyType

import numpy as np
import pytest
import test_mw_networks_ab_2219 as ab

import antennaknobs.mw.networks as ak
from antennaknobs.mw.networks import _reduce

C = 299_792_458.0
EPS = np.finfo(float).eps
#: The relative agreement asserted between the two paths.
TOL = 1e-12


@contextlib.contextmanager
def forced(path):
    """Force every MNA system built inside onto ``path``."""
    old = _reduce.SPARSE_MIN_UNKNOWNS
    _reduce.SPARSE_MIN_UNKNOWNS = 0 if path == "sparse" else 10**12
    try:
        yield
    finally:
        _reduce.SPARSE_MIN_UNKNOWNS = old


# --- fixtures: the ladder and a station chain ---------------------------------

F_LADDER = 7.1  # MHz
C_MHZ_M = 299.792458
LINE_M = 30.0
L_PM, C_PM, R_PM, G_PM = 250e-9, 100e-12, 0.06, 2e-6
Z_ANT = 73.0 + 42.0j


def line_input_impedance():
    """The analytic input impedance of the uniform RLCG line the ladder
    discretises, terminated in ``Z_ANT``."""
    w = 2 * np.pi * F_LADDER * 1e6
    z = R_PM + 1j * w * L_PM
    y = G_PM + 1j * w * C_PM
    zc = np.sqrt(z / y)
    t = np.tanh(np.sqrt(z * y) * LINE_M)
    return zc * (Z_ANT + zc * t) / (zc + Z_ANT * t)


def ladder_branches(ns, n, rig, feed):
    """N symmetric T sections (half series arm, shunt, half series arm) from
    ``rig`` to ``feed``: the ports it adds, and its branches."""
    dz = LINE_M / n
    ports, branches = {}, []
    left = rig
    for k in range(n):
        mid = f"m{k}"
        right = feed if k == n - 1 else f"n{k + 1}"
        ports[mid] = ns.PortVirtual(mid)
        if right != feed:
            ports[right] = ns.PortVirtual(right)
        branches.append(ns.TwoPort(left, mid, r=R_PM * dz / 2, l=L_PM * dz / 2))
        branches.append(ns.Shunt(mid, r=1.0 / (G_PM * dz), c=C_PM * dz, parallel=True))
        branches.append(ns.TwoPort(mid, right, r=R_PM * dz / 2, l=L_PM * dz / 2))
        left = right
    return ports, branches


def ladder(n):
    ports = {"feed": ak.PortOnWire("feed"), "rig": ak.PortVirtual("rig")}
    more, branches = ladder_branches(ak, n, "rig", "feed")
    ports.update(more)
    net = ak.Network(ports=ports, branches=branches, sources=[ak.Driven("rig")])
    red = ak.NetworkReducer(
        net, {p: i for i, p in enumerate(ports)}, len(ports), c_light_mhz_m=C_MHZ_M
    )
    return red, np.array([[1.0 / Z_ANT]], dtype=np.complex128)


def station_chain(k):
    """K copies of rig - coax - L tuner - balun - ladder line, each copy's far
    pair feeding the next copy's rig through a 1:4 floating balun, the last
    one a two-terminal antenna: the catalog's stamp mix (TL, TwoPort, series
    and parallel Shunt, FloatingBalun, BalancedLine with a common mode),
    grown to any size."""
    ports = {"w1": ak.PortOnWire("w1"), "w2": ak.PortOnWire("w2")}
    branches = []
    rig = "rig0"
    ports[rig] = ak.PortVirtual(rig)
    for s in range(k):
        t_in, t_mid, bal, l1, l2 = (f"{x}{s}" for x in ("ti", "tm", "bal", "l1", "l2"))
        for nm in (t_in, t_mid, bal, l1, l2):
            ports[nm] = ak.PortVirtual(nm)
        last = s == k - 1
        o1, o2 = ("w1", "w2") if last else (f"o1_{s}", f"o2_{s}")
        if not last:
            ports[o1], ports[o2] = ak.PortVirtual(o1), ak.PortVirtual(o2)
        branches += [
            ak.TL(rig, t_in, z0=50.0, length=15.0, vf=0.82, k1=0.25, k2=0.0009),
            ak.TwoPort(t_in, t_mid, l=2.7e-6, ql=300.0),
            ak.Shunt(t_mid, c=410e-12, qc=1200.0),
            ak.TwoPort(t_mid, bal, r=0.05),
            ak.FloatingBalun(primary=bal, a=l1, b=l2, n=2.0),
            ak.BalancedLine(
                l1, l2, o1, o2, zdiff=450.0, length=18.0, vf=0.91, k1=0.05, zcomm=600.0
            ),
        ]
        if not last:
            nxt = f"rig{s + 1}"
            ports[nxt] = ak.PortVirtual(nxt)
            branches += [
                ak.FloatingBalun(primary=nxt, a=o1, b=o2, n=0.5),
                ak.Shunt(o2, r=1000.0),
            ]
            rig = nxt
    net = ak.Network(ports=ports, branches=branches, sources=[ak.Driven("rig0")])
    red = ak.NetworkReducer(net, {p: i for i, p in enumerate(ports)}, len(ports))
    z = np.array([[60.0 + 20j, 5.0 - 3j], [5.0 - 3j, 60.0 + 20j]])
    return red, np.linalg.inv(z)


# --- the parity check both paths are held to ----------------------------------


def _reduce_all(red, y, wl):
    """Everything downstream reads, or the refusal as (class, message)."""
    try:
        s = red.apply_branches(y, wl, z_ref=ak.Z_REF_DEFAULT)
        z = np.array(red.impedance_from_y(s))
        g = np.array(red.reflection_from_y(s))
        z75 = np.array(red.driven_impedance(y, wl, z_ref=75.0 + 5j))
        ideal = red.apply_branches(y, wl)
        v_ideal = red.resolve_voltages(ideal)
        v, eff, p_in, budget = red.excited_state(y, wl)
    except (ValueError, NotImplementedError) as e:
        return ("refused", type(e).__name__, str(e))
    return dict(
        sparse=s.sparse,
        n=s.A.shape[0],
        rcond=s.rcond,
        rcond_ideal=ideal.rcond,
        z=z,
        g=g,
        z75=z75,
        v=v,
        v_ideal=v_ideal,
        eff=eff,
        p_in=p_in,
        labels=[r[0] for r in budget],
        keys=[r.key for r in budget],
        w=np.array([r[1] for r in budget]),
    )


def _rel(a, b, scale=None):
    a, b = np.atleast_1d(a), np.atleast_1d(b)
    if a.size == 0:
        return 0.0
    s = float(np.max(np.abs(b))) if scale is None else scale
    d = float(np.max(np.abs(a - b)))
    return d / s if s else d


def both_paths(red, y, wl):
    with forced("dense"):
        d = _reduce_all(red, y, wl)
    with forced("sparse"):
        s = _reduce_all(red, y, wl)
    return d, s


def check_parity(d, s, *, v_tol=None):
    """Assert the sparse answer ``s`` matches the dense ``d``; return the
    worst relative difference and the worst rcond ratio, in decades.

    Every quantity is held to `TOL` relative except the excited port
    voltages, which ``v_tol`` may widen for an ill-conditioned network:
    there the two paths agree only to the problem's own κ·ε (see
    `test_catalog_networks_agree_on_both_paths`).
    """
    if isinstance(d, tuple) or isinstance(s, tuple):
        assert d == s, f"refusals differ:\n dense  {d}\n sparse {s}"
        return 0.0, 0.0
    assert d["sparse"] is False and s["sparse"] is True
    assert d["labels"] == s["labels"] and d["keys"] == s["keys"]
    p_scale = max(abs(d["p_in"]), 1e-300)
    errs = {
        "z": _rel(s["z"], d["z"]),
        "g": _rel(s["g"], d["g"]),
        "z75": _rel(s["z75"], d["z75"]),
        "p_in": _rel(s["p_in"], d["p_in"]),
        "w": _rel(s["w"], d["w"], scale=p_scale),
        "eff": abs(s["eff"] - d["eff"]),
    }
    for what, e in errs.items():
        assert e <= TOL, f"{what}: sparse vs dense {e:.2e} > {TOL:g}"
    v_err = max(_rel(s["v"], d["v"]), _rel(s["v_ideal"], d["v_ideal"]))
    v_bound = TOL if v_tol is None else max(TOL, v_tol)
    assert v_err <= v_bound, f"voltages: {v_err:.2e} > {v_bound:.2e}"
    decades = max(
        abs(np.log10(s["rcond"] / d["rcond"])),
        abs(np.log10(s["rcond_ideal"] / d["rcond_ideal"])),
    )
    assert decades < 1.0, (
        f"rcond not in the same decade: dense {d['rcond']:.2e} / "
        f"{d['rcond_ideal']:.2e}, sparse {s['rcond']:.2e} / {s['rcond_ideal']:.2e}"
    )
    return max(*errs.values(), v_err), decades


def _ab_reducer(case):
    net, idx, n_real = ab._build(ak, case)
    y = ab._antenna_y(n_real, seed=n_real * 7 + len(idx))
    return ak.NetworkReducer(net, idx, len(idx)), y


# --- the threshold --------------------------------------------------------------


def test_the_threshold_is_the_mna_dimension():
    assert _reduce.use_sparse(_reduce.SPARSE_MIN_UNKNOWNS)
    assert not _reduce.use_sparse(_reduce.SPARSE_MIN_UNKNOWNS - 1)
    red, y = ladder(50)  # n+m 202: n = 101 nodes would read as dense
    s = red.apply_branches(y, C_MHZ_M / F_LADDER)
    assert red.n_nodes < _reduce.SPARSE_MIN_UNKNOWNS <= s.A.shape[0]
    assert s.sparse


@pytest.mark.parametrize("name", sorted(ab.CASES))
def test_every_ab_case_is_on_the_dense_path(name):
    """The bit-for-bit A/B against momwire is of the dense path: none of its
    cases reaches the threshold, at the default setting."""
    red, y = _ab_reducer(ab.CASES[name])
    for z_ref in (0j, ak.Z_REF_DEFAULT):
        s = red.apply_branches(y, ab._wl(7.1), z_ref=z_ref)
        assert not s.sparse
        assert isinstance(s.A, np.ndarray)
        assert s.A.shape[0] < _reduce.SPARSE_MIN_UNKNOWNS


# --- the ladder oracle ------------------------------------------------------------


def test_the_ladder_converges_to_the_line_as_one_over_n_squared():
    """T sections discretise the uniform line with an O(Δz²) error, so
    err·N² is a constant (measured 25.6 at N = 100 and 1000, 25.6 at 4000).
    Asserting it lies in [20, 30] at every N is the 1/N² law itself: a solver
    adding its own error, or a sparse path not taken, would break it at
    N = 4000, where the target is 1.6e-6."""
    ze = line_input_impedance()
    wl = C_MHZ_M / F_LADDER
    errs = {}
    for n in (100, 1000, 4000):
        red, y = ladder(n)
        s = red.apply_branches(y, wl, z_ref=ak.Z_REF_DEFAULT)
        assert s.sparse and s.A.shape[0] == 4 * n + 2
        z = red.impedance_from_y(s)[0]
        errs[n] = abs(z - ze) / abs(ze)
        assert 20.0 <= errs[n] * n * n <= 30.0, (n, errs[n])
    assert errs[100] / errs[1000] == pytest.approx(100.0, rel=0.02)
    assert errs[1000] / errs[4000] == pytest.approx(16.0, rel=0.02)


def test_the_large_ladder_solves_fast():
    """N = 4000 (16002 unknowns), one frequency: stamping, assembly, factor,
    refinement and condition estimate. Measured about 0.13 s on the
    development laptop; dense would be over an hour. 1 s leaves a slow CI
    runner its margin and still fails anything dense-shaped."""
    red, y = ladder(4000)
    wl = C_MHZ_M / F_LADDER
    best = float("inf")
    for _ in range(2):
        t0 = time.perf_counter()
        z = red.driven_impedance(y, wl)[0]
        best = min(best, time.perf_counter() - t0)
    assert np.isfinite(z)
    assert best < 1.0, f"{best:.3f} s per frequency"


def test_the_large_ladder_stays_small_in_memory():
    """Peak RSS of a fresh process solving N = 4000, against the same process
    before it builds anything. A dense A would be (16002)²·16 B = 3.8 GB
    before LAPACK's copies; measured here, about 30 MB. A fresh process,
    because ``ru_maxrss`` is a process high-water mark and this one's may
    already sit above anything the test does."""
    code = textwrap.dedent(
        """
        import resource, sys
        import numpy as np
        import scipy.sparse.linalg  # noqa: F401 -- loaded before the baseline
        sys.path.insert(0, sys.argv[1])
        import test_sparse_mna_2241 as t
        before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        red, y = t.ladder(4000)
        s = red.apply_branches(y, t.C_MHZ_M / t.F_LADDER, z_ref=50.0)
        z = red.impedance_from_y(s)[0]
        after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(int(s.sparse), s.A.shape[0], s.A.nnz, (after - before) / 1024.0)
        """
    )
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    out = subprocess.run(
        [sys.executable, "-c", code, os.path.dirname(__file__)],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=True,
    )
    sparse, n, nnz, delta_mb = out.stdout.split()
    assert sparse == "1" and int(n) == 16002
    # Three or so stamps per unknown: the matrix itself is O(n+m).
    assert int(nnz) < 4 * int(n)
    dense_mb = int(n) ** 2 * 16 / 2**20
    assert float(delta_mb) < 300.0, f"peak RSS grew {delta_mb} MB"
    assert float(delta_mb) < dense_mb / 10.0


# --- forced dense vs forced sparse ------------------------------------------------


@pytest.mark.parametrize("c_light_mhz_m", ab._C_LIGHT_VARIANTS, ids=["si-c", "nec-c"])
@pytest.mark.parametrize("name", sorted(ab.CASES))
def test_the_ab_cases_agree_on_both_paths(name, c_light_mhz_m):
    net, idx, n_real = ab._build(ak, ab.CASES[name])
    y = ab._antenna_y(n_real, seed=n_real * 7 + len(idx))
    red = ak.NetworkReducer(net, idx, len(idx), c_light_mhz_m=c_light_mhz_m)
    for f in ab.F_MHZ:
        wl = ab._wl(f) if c_light_mhz_m is None else c_light_mhz_m / f
        d, s = both_paths(red, y, wl)
        assert not isinstance(d, tuple), d
        check_parity(d, s)


@pytest.mark.parametrize("name", sorted(ab.CASES))
def test_the_assembled_matrix_is_the_same_matrix(name):
    """The sparse assembly writes the dense one's entries, not merely an
    equivalent system: equal to the last bit but where a node sums three or
    more stamps, whose order COO summation does not keep."""
    red, y = _ab_reducer(ab.CASES[name])
    for z_ref in (0j, ak.Z_REF_DEFAULT):
        with forced("dense"):
            d = red.apply_branches(y, ab._wl(14.2), z_ref=z_ref)
        with forced("sparse"):
            s = red.apply_branches(y, ab._wl(14.2), z_ref=z_ref)
        a = s.A.toarray()
        assert np.array_equal(a != 0, d.A != 0)
        np.testing.assert_allclose(a, d.A, rtol=4 * EPS, atol=0)
        np.testing.assert_array_equal(s.rhs, d.rhs)
        assert s.terminations == d.terminations
        assert s.z_ref_at == d.z_ref_at


@pytest.mark.parametrize("k", [1, 3, 12, 40])
def test_station_chains_agree_on_both_paths(k):
    red, y = station_chain(k)
    for f in (3.6, 7.1, 14.2):
        d, s = both_paths(red, y, C / (f * 1e6))
        check_parity(d, s)


def test_ladders_agree_on_both_paths():
    for n in (10, 100, 300):
        red, y = ladder(n)
        d, s = both_paths(red, y, C_MHZ_M / F_LADDER)
        check_parity(d, s)


def _catalog_networks():
    """Every catalog design's network as its momwire engine builds it: the
    engine is constructed (geometry and the reducer, no solve) with
    `make_reducer` intercepted so a self-tuning tuner is not tuned."""
    import antennaknobs.designs as designs_pkg
    import antennaknobs.engines.momwire as em

    captured = []

    def capture(net, port_to_idx, n_total, **kw):
        c = kw.get("c_light_mhz_m")
        captured.append((net, dict(port_to_idx), n_total, c))
        return ak.NetworkReducer(net, port_to_idx, n_total, c_light_mhz_m=c)

    real = em.make_reducer
    em.make_reducer = capture
    try:
        for m in pkgutil.walk_packages(
            designs_pkg.__path__, designs_pkg.__name__ + "."
        ):
            if m.ispkg:
                continue
            try:
                builder = importlib.import_module(m.name).Builder
            except Exception:  # noqa: BLE001 — an unimportable design is gated elsewhere
                continue
            captured.clear()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                b = builder()
                em.MomwireEngine(b)
            if captured:
                yield m.name.split("antennaknobs.designs.")[-1], b.freq, captured[-1]
    finally:
        em.make_reducer = real


def test_catalog_networks_agree_on_both_paths():
    """Every catalog design's network over a synthetic passive antenna Y,
    forced through both paths at three frequencies.

    Measured (46 designs, 138 rows): worst 2.1e-14 relative in every
    quantity but one design's voltages, and rcond within 0.16 decades. The
    one is ``arrays.bowtie1x2_bl`` (rcond 5-9e-7: its floating gaps' common
    mode is pinned only through 1e8 Ω shunts), whose excited node voltages
    differ by up to 5.4e-11 of the largest. Both answers there have a
    componentwise backward error of 1.3-1.5e-16, so that is the problem's own
    κ·ε, not either solver's: its voltages are held to ε/rcond instead
    (2.9e-10 there), while its Z, Γ, p_in and budget meet 1e-12 like
    everything else. The largest catalog network is 34 unknowns."""
    rows = worst = worst_dec = 0
    largest = 0
    for name, f_mhz, (net, idx, n_total, c_light) in _catalog_networks():
        n_virtual = sum(isinstance(p, ak.PortVirtual) for p in net.ports.values())
        red = ak.NetworkReducer(net, idx, n_total, c_light_mhz_m=c_light)
        y = ab._antenna_y(n_total - n_virtual, seed=n_total)
        for f in (0.9 * f_mhz, f_mhz, 1.1 * f_mhz):
            wl = C / (f * 1e6) if c_light is None else c_light / f
            d, s = both_paths(red, y, wl)
            assert not isinstance(d, tuple), (name, d)
            err, dec = check_parity(d, s, v_tol=EPS / min(d["rcond"], d["rcond_ideal"]))
            worst, worst_dec = max(worst, err), max(worst_dec, dec)
            largest = max(largest, d["n"])
            rows += 1
    assert rows >= 100, f"only {rows} catalog rows: the census measured nothing"
    assert largest < _reduce.SPARSE_MIN_UNKNOWNS / 4


# --- refusals and warnings -----------------------------------------------------


@pytest.mark.parametrize("name", sorted(ab.REFUSALS))
def test_every_refusal_refuses_identically_on_the_sparse_path(name):
    """Same class, same message to the character (the rcond it quotes
    included: 0.00e+00 for the isolated island, 8.61e-18 for the driven open
    stub on both paths), same `diagnose` attribution."""
    case = ab.REFUSALS[name]
    outcomes = {}
    for path in ("dense", "sparse"):
        with forced(path):
            try:
                net, idx, n_real = ab._build(ak, case)
                red = ak.NetworkReducer(net, idx, len(idx))
            except (ValueError, NotImplementedError) as e:
                outcomes[path] = ("construction", type(e).__name__, str(e))
                continue
            outcomes[path] = _reduce_all(
                red, ab._antenna_y(n_real, seed=3), ab._wl(14.2)
            )
    assert outcomes["dense"] == outcomes["sparse"]
    assert isinstance(outcomes["sparse"], tuple)


def test_the_singular_refusals_reach_the_sparse_solve():
    """The two solve-time refusals really are refused BY the sparse solve."""
    for case in (ab.refusal_isolated_island, ab.refusal_open_driven_stub):
        net, idx, n_real = ab._build(ak, case)
        red = ak.NetworkReducer(net, idx, len(idx))
        with forced("sparse"):
            system = red.apply_branches(ab._antenna_y(n_real, seed=3), ab._wl(14.2))
            assert system.sparse
            with pytest.raises(ak.SingularNetworkError, match="after equilibration"):
                system.solve()


def _suspect_stub():
    """A lossless open stub across the driven port 1e-10 of a quarter-wave off
    resonance: the excited (ideal-generator) solve is nearly singular,
    rcond between RCOND_SINGULAR and RCOND_SUSPECT."""
    wl = ab._wl(14.2)
    ports = {
        "ant": ak.PortOnWire("ant"),
        "rig": ak.PortVirtual("rig"),
        "stub": ak.PortVirtual("stub"),
    }
    net = ak.Network(
        ports=ports,
        branches=[
            ak.TL("rig", "ant", z0=50.0, length=4.0),
            ak.TL("rig", "stub", z0=50.0, length=wl / 4.0 * (1.0 + 1e-10)),
        ],
        sources=[ak.Driven("rig")],
    )
    red = ak.NetworkReducer(net, {p: i for i, p in enumerate(ports)}, len(ports))
    return red, ab._antenna_y(1, seed=3), wl


def test_a_suspect_solve_warns_identically_on_the_sparse_path(caplog):
    red, y, wl = _suspect_stub()
    seen = {}
    for path in ("dense", "sparse"):
        caplog.clear()
        with forced(path), caplog.at_level(logging.WARNING, logger=_reduce.__name__):
            system = red.apply_branches(y, wl)
            system.solve()
        assert system.sparse is (path == "sparse")
        assert _reduce.RCOND_SINGULAR < system.rcond < _reduce.RCOND_SUSPECT
        (rec,) = [r for r in caplog.records if "nearly singular" in r.getMessage()]
        seen[path] = (rec.getMessage(), system.rcond)
    msg_d, rc_d = seen["dense"]
    msg_s, rc_s = seen["sparse"]
    assert abs(np.log10(rc_s / rc_d)) < 1.0
    # The same text, but for the rcond each quotes.
    assert msg_d.replace(f"{rc_d:.2e}", "R") == msg_s.replace(f"{rc_s:.2e}", "R")


# --- mutation controls ----------------------------------------------------------


def _ab_parity_all():
    for name in sorted(ab.CASES):
        red, y = _ab_reducer(ab.CASES[name])
        for f in ab.F_MHZ:
            check_parity(*both_paths(red, y, ab._wl(f)))


def test_the_parity_check_catches_dropped_column_scaling(monkeypatch):
    """With the column factors replaced by ones, the sparse rcond is no
    longer the system zgesvx reports on: measured 1.55 decades low on
    `floating_gap_twoport` and `driven_current`. The answer itself is still
    right, which is why rcond is what the parity check compares."""
    real = _reduce._equilibrate

    def rows_only(A):
        out = real(A)
        return None if out is None else (out[0], np.ones_like(out[1]))

    _ab_parity_all()  # the unmutated control passes
    monkeypatch.setattr(_reduce, "_equilibrate", rows_only)
    with pytest.raises(AssertionError, match="same decade"):
        _ab_parity_all()


def test_the_parity_check_catches_a_mis_stamped_group2_term(monkeypatch):
    """Negate the first coupling triple, the B (Zc·sinh γl) term of the
    line's chain-matrix row, on the sparse path only. Both paths read one
    emitter (`_MNAStamps.triples`), so the mutation goes into `_csc`, the one
    step only the sparse path takes; the couplings are the last triples, and
    this case's one line contributes two."""
    real = _reduce._csc

    def mis_stamped(rows, cols, vals, N):
        vals = vals.copy()
        vals[-2] *= -1.0
        return real(rows, cols, vals, N)

    monkeypatch.setattr(_reduce, "_csc", mis_stamped)
    red, y = _ab_reducer(ab.case_tl_lossy_vf)
    with pytest.raises(AssertionError, match="sparse vs dense"):
        check_parity(*both_paths(red, y, ab._wl(14.2)))


# --- end to end: a design with a large network, through the momwire engine ----


def _ladder_dipole(n_sections):
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, Wire
    import antennaknobs.network as netmod

    class LadderFedDipole(AntennaBuilder):
        """A 7.1 MHz dipole fed through 30 m of RG-58-like line, the line
        written out as N T sections (synthetic)."""

        default_params = MappingProxyType(
            {"freq": 7.1, "design_freq": 7.1, "length_m": 20.0, "height_m": 12.0}
        )

        def build_wires(self):
            a = 0.5 * self.length_m
            return self.auto_mesh(
                [Wire((0.0, -a, self.height_m), (0.0, a, self.height_m), name="feed")]
            )

        def build_network(self):
            more, branches = ladder_branches(netmod, n_sections, "rig", "feed")
            return Network(
                ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig"), **more},
                branches=branches,
                sources=[Driven(port="rig", voltage=1 + 0j)],
            )

    return LadderFedDipole


def _engine(n_sections):
    from antennaknobs.cli import make_engine_factory

    return make_engine_factory("momwire:bspline", None)(_ladder_dipole(n_sections)())


@pytest.mark.parametrize("n_sections", [300, 1000])
def test_a_design_with_a_large_network_solves_through_the_engine(n_sections):
    """The app's way in: a builder whose `build_network` is a dipole behind a
    ladder, `make_engine_factory("momwire:bspline", None)`, `.impedance()`
    and a short `impedance_sweep` (the per-frequency `_reduce_at` over the
    swept Y), at the DEFAULT threshold, which puts both sizes on the sparse
    path by themselves. At 300 sections (1202 unknowns) the same engine is
    then forced dense and must agree to 1e-12; at 1000 (4002 unknowns) dense
    is ~1 GB and seconds per frequency, too heavy for the suite, so that
    comparison was run once by hand (`scratch/2241-sparse-mna/e2e_dense_1000.py`,
    the PR has the number)."""
    freqs = [6.9, 7.1, 7.3]
    e = _engine(n_sections)
    wl = e._wavelength_for(7.1)
    system = e._reducer.apply_branches(e._compute_y_matrix(wl), wl)
    assert system.sparse and system.A.shape[0] == 4 * n_sections + 2
    z = complex(np.atleast_1d(e.impedance())[0])
    zs = np.asarray(e.impedance_sweep(freqs))[:, 0]
    assert np.all(np.isfinite(zs)) and np.isfinite(z)
    # The sweep's 7.1 MHz sample is the single-point solve (swept Y vs
    # single-point Y differ at evaluation order, momwire#1861's 1e-12).
    assert zs[1] == pytest.approx(z, rel=1e-9)
    if n_sections <= 300:
        with forced("dense"):
            assert not e._reducer.apply_branches(e._compute_y_matrix(wl), wl).sparse
            zd = complex(np.atleast_1d(e.impedance())[0])
            zds = np.asarray(e.impedance_sweep(freqs))[:, 0]
        assert abs(z - zd) / abs(zd) <= TOL
        assert np.max(np.abs(zs - zds) / np.abs(zds)) <= TOL
