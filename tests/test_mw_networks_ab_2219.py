"""AK#2219 stage 1: antennaknobs' copy of the general network reducer
(`antennaknobs.mw.networks`) answers bit for bit what momwire's own
`momwire.networks` answers.

The copy was taken from momwire commit 03a2357e (0.89.0) and moved no
behaviour, so this A/B is the stage's whole acceptance. Every case below is
ONE description built twice, once from each namespace's own classes (each
reducer's `isinstance` stamps recognise only its own), reduced over the same
synthetic antenna Y at a few frequencies, and compared byte for byte:

* the driven impedance and reflection on the referenced (`Z_REF_DEFAULT`)
  stamp, and the impedance on an explicit reference;
* `apply_branches`' assembled system: the MNA matrix, its right-hand side,
  the terminations, the reference map and the probes (labels, kinds,
  payloads, structured keys), at both the ideal and the referenced source;
* `excited_state`: the forced port voltages, efficiency, input power, and
  every power-budget row's label, watts and key;
* refusals: the same exception class name and the same message, both at
  construction and at solve.

"Bit for bit" means `tobytes()` equality of complex128 arrays and of float
scalars, so a signed zero or a NaN payload that differed would fail too.

When the copy is MEANT to move a number (a fix, a new model, AK#2241's
sparse path above its threshold), the case that moves is updated here on
purpose, and the PR says which.
"""

from __future__ import annotations

import math
import struct

import momwire.networks as core
import numpy as np
import pytest

import antennaknobs.mw.networks as ak

C = 299_792_458.0
F_MHZ = (1.83, 7.1, 14.2, 28.5)


def _wl(f_mhz):
    return C / (f_mhz * 1e6)


def _antenna_y(n, seed):
    """A synthetic passive n-port short-circuit admittance: Z = R + jX with R
    symmetric positive definite and X symmetric, inverted. Deterministic."""
    if n == 0:
        return np.zeros((0, 0), dtype=np.complex128)
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n))
    r = a @ a.T + n * np.eye(n) * 20.0
    b = rng.normal(size=(n, n)) * 40.0
    x = (b + b.T) / 2.0
    return np.linalg.inv(r + 1j * x)


class _Measured:
    """A synthetic `AdmittanceData`: an RLC-ish frequency-dependent Y, the
    same object handed to both reducers (the protocol is duck-typed)."""

    def __init__(self, nports, seed):
        self.nports = nports
        rng = np.random.default_rng(seed)
        self._g = rng.uniform(0.002, 0.02, size=(nports, nports))
        self._g = (self._g + self._g.T) / 2.0 + np.eye(nports) * 0.02
        self._b = rng.normal(size=(nports, nports)) * 1e-9
        self._b = (self._b + self._b.T) / 2.0

    def y_at(self, f_hz):
        return self._g + 1j * (2 * math.pi * f_hz) * self._b


class _Core:
    """A synthetic ferrite core (`magnetizing_impedance`'s `core`)."""

    def impedance(self, f_mhz):
        return complex(3.0 * f_mhz, 120.0 * math.sqrt(f_mhz))


_MEASURED_1 = _Measured(1, seed=11)
_MEASURED_2 = _Measured(2, seed=12)
_CORE = _Core()


# --- the cases: one description, built from either namespace ----------------
#
# Each returns (ports, branches, sources, branch_paths, n_real). Ports are
# listed real first, then virtual; the port index map follows that order.


def _feed(ns, *extra):
    return {"ant": ns.PortOnWire("ant"), "rig": ns.PortVirtual("rig"), **dict(extra)}


def case_tl_lossless(ns):
    return (
        _feed(ns),
        [ns.TL("rig", "ant", z0=50.0, length=7.3)],
        [ns.Driven("rig")],
    )


def case_tl_lossy_vf(ns):
    return (
        _feed(ns),
        [ns.TL("rig", "ant", z0=75.0, length=21.0, vf=0.66, k1=0.42, k2=0.0031)],
        [ns.Driven("rig")],
    )


def case_tl_k0(ns):
    return (
        _feed(ns),
        [ns.TL("rig", "ant", z0=50.0, length=12.0, vf=0.8, k0=0.05, k1=0.3, k2=0.01)],
        [ns.Driven("rig")],
    )


def case_tl_skin(ns):
    return (
        _feed(ns),
        [
            ns.TL(
                "rig",
                "ant",
                z0=450.0,
                length=33.0,
                vf=0.91,
                k0=0.02,
                k1=0.11,
                k2=0.004,
                skin=True,
            )
        ],
        [ns.Driven("rig")],
    )


def case_tl_transposed_pair(ns):
    return (
        {**_feed(ns), "m": ns.PortVirtual("m")},
        [
            ns.TL("rig", "m", z0=50.0, length=5.0, transposed=True),
            ns.TL("m", "ant", z0=100.0, length=9.0, vf=0.7, k1=0.2),
        ],
        [ns.Driven("rig")],
    )


def case_tl_half_wave(ns):
    # A lossless line exactly λ/2 at 14.2 MHz: no admittance matrix, a fine
    # chain matrix (issue #746).
    return (
        _feed(ns),
        [ns.TL("rig", "ant", z0=50.0, length=_wl(14.2) / 2.0)],
        [ns.Driven("rig")],
    )


def case_tl_from_cable(ns):
    cable = ns.Cable(z0=50.0, vf=0.78, k1=0.33, k2=0.0012)
    return (
        _feed(ns),
        [ns.TL.from_cable(cable, "rig", "ant", 30.48)],
        [ns.Driven("rig")],
    )


def case_load_series_driven(ns):
    return (
        {"ant": ns.PortOnWire("ant")},
        [ns.Load("ant", r=12.0, l=2.2e-6, c=150e-12, ql=180.0, qc=900.0)],
        [ns.Driven("ant")],
    )


def case_load_parallel_undriven(ns):
    return (
        {"ant": ns.PortOnWire("ant"), "trap": ns.PortOnWire("trap")},
        [ns.Load("trap", r=8000.0, l=4.7e-6, c=47e-12, parallel=True, ql=150.0)],
        [ns.Driven("ant")],
    )


def case_load_fixed_z(ns):
    return (
        {"ant": ns.PortOnWire("ant"), "far": ns.PortOnWire("far")},
        [ns.Load("far", z=30.0 - 40.0j), ns.Load("ant", z=5.0 + 2.0j)],
        [ns.Driven("ant")],
    )


def case_twoport_rlc(ns):
    return (
        _feed(ns),
        [ns.TwoPort("rig", "ant", r=3.0, l=1.1e-6, c=220e-12, ql=250.0, qc=2000.0)],
        [ns.Driven("rig")],
    )


def case_twoport_short(ns):
    return (_feed(ns), [ns.TwoPort("rig", "ant")], [ns.Driven("rig")])


def case_shunt_series(ns):
    return (
        _feed(ns),
        [
            ns.TwoPort("rig", "ant", l=0.8e-6),
            ns.Shunt("rig", r=2.0, l=1.5e-6, c=330e-12, ql=200.0),
        ],
        [ns.Driven("rig")],
    )


def case_shunt_parallel(ns):
    return (
        _feed(ns),
        [
            ns.TwoPort("rig", "ant", c=150e-12),
            ns.Shunt("ant", r=5000.0, l=3.3e-6, c=68e-12, parallel=True, qc=1500.0),
        ],
        [ns.Driven("rig")],
    )


def case_transformer_lmag(ns):
    return (
        _feed(ns),
        [ns.Transformer("rig", "ant", n=0.5, r=0.4, lmag=40e-6, qlmag=60.0)],
        [ns.Driven("rig")],
    )


def case_transformer_core(ns):
    return (
        _feed(ns),
        [ns.Transformer("rig", "ant", n=2.0, core=_CORE)],
        [ns.Driven("rig")],
    )


def case_autotransformer(ns):
    return (
        _feed(ns),
        [
            ns.Autotransformer(
                "rig", "ant", l_lower=2e-6, l_upper=6e-6, k=0.97, ql=120.0
            )
        ],
        [ns.Driven("rig")],
    )


def case_balanced_line_cm_open(ns):
    # Two real feeds at the far end (an antenna Y row grounds each), a
    # CM-open line, its near pair driven differentially by two sources.
    return (
        {
            "w1": ns.PortOnWire("w1"),
            "w2": ns.PortOnWire("w2"),
            "p": ns.PortVirtual("p"),
            "q": ns.PortVirtual("q"),
        },
        [ns.BalancedLine("p", "q", "w1", "w2", zdiff=450.0, length=14.0, vf=0.9)],
        [ns.Driven("p", voltage=0.5 + 0j), ns.Driven("q", voltage=-0.5 + 0j)],
    )


def case_balanced_line_zcomm(ns):
    return (
        {
            "w1": ns.PortOnWire("w1"),
            "w2": ns.PortOnWire("w2"),
            "p": ns.PortVirtual("p"),
            "q": ns.PortVirtual("q"),
        },
        [
            ns.BalancedLine(
                "p",
                "q",
                "w1",
                "w2",
                zdiff=300.0,
                length=20.0,
                vf=0.85,
                k1=0.1,
                k2=0.002,
                zcomm=150.0,
            ),
            ns.Shunt("q", r=50.0),
        ],
        [ns.Driven("p")],
    )


def case_floating_balun(ns):
    return (
        {
            "w1": ns.PortOnWire("w1"),
            "w2": ns.PortOnWire("w2"),
            "rig": ns.PortVirtual("rig"),
            "r2": ns.PortVirtual("r2"),
        },
        [
            ns.FloatingBalun(primary="rig", a="w1", b="w2", n=2.0, r=0.3, lmag=20e-6),
            ns.FloatingBalun(primary="r2", a="w1", b="w2", n=0.5, core=_CORE),
            ns.Shunt("r2", r=75.0),
        ],
        [ns.Driven("rig")],
    )


def case_floating_gap_twoport(ns):
    # A floating gap's two terminals bridged by a series RLC, fed from a
    # second, grounded gap.
    return (
        {"ant": ns.PortOnWire("ant"), "gap": ns.PortOnWireFloating("gap")},
        [
            ns.TwoPort("gap.p", "gap.n", r=20.0, l=1e-6),
            # The pair's common-mode return: without one, gap.p and gap.n
            # float together and the MNA is singular.
            ns.Shunt("gap.n", r=1000.0, c=5e-12),
        ],
        [ns.Driven("ant")],
    )


def case_admittance_1port(ns):
    return (
        {"ant": ns.PortOnWire("ant"), "far": ns.PortOnWire("far")},
        [ns.Admittance(ports=("far",), y=((0.01 - 0.004j,),))],
        [ns.Driven("ant")],
    )


def case_admittance_2port(ns):
    return (
        _feed(ns),
        [
            ns.Admittance(
                ports=("rig", "ant"),
                y=((0.02 - 0.01j, -0.015 + 0.002j), (-0.015 + 0.002j, 0.03 + 0.004j)),
            )
        ],
        [ns.Driven("rig")],
    )


def case_admittance_nt_inverter(ns):
    # The NT-card idiom from tests/test_nec5_station_deck_2209: a pure
    # imaginary off-diagonal (an impedance inverter) to a virtual node.
    return (
        {"ant": ns.PortOnWire("ant"), "v": ns.PortVirtual("v")},
        [
            ns.Admittance(ports=("v", "ant"), y=((0j, 0.02j), (0.02j, 0j))),
            ns.Shunt("v", r=50.0),
        ],
        [ns.Driven("ant")],
    )


def case_touchstone_load(ns):
    return (
        {"ant": ns.PortOnWire("ant"), "far": ns.PortOnWire("far")},
        [ns.TouchstoneLoad("far", data=_MEASURED_1)],
        [ns.Driven("ant")],
    )


def case_touchstone_twoport(ns):
    return (
        _feed(ns),
        [ns.TouchstoneTwoPort("rig", "ant", data=_MEASURED_2)],
        [ns.Driven("rig")],
    )


def case_driven_current(ns):
    return (
        {"ant": ns.PortOnWire("ant"), "b": ns.PortOnWire("b")},
        [ns.Load("ant", r=4.0, l=0.5e-6)],
        [ns.DrivenCurrent("ant", current=0.7 - 0.2j), ns.Driven("b", voltage=2.0 + 0j)],
    )


def case_port_at_end_and_vertex(ns):
    return (
        {
            "tip": ns.PortAtEnd("w", end="p1"),
            "apex": ns.PortAtVertex("arm", end="p0"),
            "rig": ns.PortVirtual("rig"),
        },
        [
            ns.TL("rig", "apex", z0=50.0, length=3.0),
            ns.Load("apex", r=2.0),
            ns.Shunt("tip", r=10.0, c=40e-12),
        ],
        [ns.Driven("rig")],
    )


def case_phased_pair(ns):
    # Two driven elements fed in quadrature through lines of different
    # length, a load on each, and a coupling capacitor between the feeds.
    return (
        {
            "e1": ns.PortOnWire("e1"),
            "e2": ns.PortOnWire("e2"),
            "s1": ns.PortVirtual("s1"),
            "s2": ns.PortVirtual("s2"),
        },
        [
            ns.TL("s1", "e1", z0=75.0, length=_wl(7.1) / 4.0, vf=0.66, k1=0.4),
            ns.TL("s2", "e2", z0=75.0, length=_wl(7.1) / 2.0, vf=0.66, k1=0.4),
            ns.TwoPort("e1", "e2", c=10e-12),
            ns.Load("e1", r=1.5),
            ns.Load("e2", r=1.5),
        ],
        [ns.Driven("s1"), ns.Driven("s2", voltage=0 + 1j)],
    )


def case_l_tuner_station(ns):
    # rig - coax - L tuner (series L, shunt C) - balun - ladder line - the
    # two halves of a dipole feed,
    # with an inline loss TwoPort and a measured dummy load teed off the rig.
    return (
        {
            "w1": ns.PortOnWire("w1"),
            "w2": ns.PortOnWire("w2"),
            "rig": ns.PortVirtual("rig"),
            "t_in": ns.PortVirtual("t_in"),
            "t_mid": ns.PortVirtual("t_mid"),
            "bal": ns.PortVirtual("bal"),
            "l1": ns.PortVirtual("l1"),
            "l2": ns.PortVirtual("l2"),
        },
        [
            ns.TL("rig", "t_in", z0=50.0, length=15.0, vf=0.82, k1=0.25, k2=0.0009),
            ns.TwoPort("t_in", "t_mid", l=2.7e-6, ql=300.0),
            ns.Shunt("t_mid", c=410e-12, qc=1200.0),
            ns.TwoPort("t_mid", "bal", r=0.05),
            ns.FloatingBalun(primary="bal", a="l1", b="l2", n=2.0),
            ns.BalancedLine(
                "l1",
                "l2",
                "w1",
                "w2",
                zdiff=450.0,
                length=18.0,
                vf=0.91,
                k1=0.05,
                zcomm=600.0,
            ),
            ns.TouchstoneLoad("rig", data=_MEASURED_1),
        ],
        [ns.Driven("rig")],
        ["", "tuner.", "tuner.", "", "", "", ""],
    )


def case_nec_card_subset(ns):
    # What a NEC deck can say: real ports only, TL + NT + a lumped port load.
    return (
        {
            "a": ns.PortOnWire("a"),
            "b": ns.PortOnWire("b"),
            "c": ns.PortOnWire("c"),
        },
        [
            ns.TL("a", "b", z0=300.0, length=4.0, transposed=True),
            ns.Admittance(ports=("b", "c"), y=((0.01j, -0.004j), (-0.004j, 0.01j))),
            ns.Load("c", z=50.0 + 0j),
        ],
        [ns.Driven("a")],
    )


CASES = {
    name[len("case_") :]: fn
    for name, fn in sorted(globals().items())
    if name.startswith("case_") and callable(fn)
}

# The SI c, and NEC's 299.8 metre-megahertz product a deck-derived design
# passes (antennaknobs#1685): its parts read the deck's f off NEC's wavelength.
_C_LIGHT_VARIANTS = (None, 299.8)


def _build(ns, case):
    spec = case(ns)
    ports, branches, sources = spec[:3]
    paths = spec[3] if len(spec) > 3 else []
    net = ns.Network(
        ports=ports, branches=branches, sources=sources, branch_paths=paths
    )
    real = [
        n
        for n, p in ports.items()
        if isinstance(
            p, (ns.PortOnWire, ns.PortOnWireFloating, ns.PortAtEnd, ns.PortAtVertex)
        )
    ]
    virtual = [n for n in ports if n not in real]
    idx = {n: i for i, n in enumerate(real + virtual)}
    return net, idx, len(real)


# --- comparison --------------------------------------------------------------


def _b(x):
    """Bytes of a value, for bit-for-bit comparison."""
    if isinstance(x, (float, int)) and not isinstance(x, bool):
        return struct.pack("<d", float(x))
    if isinstance(x, complex):
        return struct.pack("<dd", x.real, x.imag)
    return np.ascontiguousarray(np.asarray(x)).tobytes()


def _same(a, b, what):
    a_arr, b_arr = np.asarray(a), np.asarray(b)
    assert a_arr.shape == b_arr.shape, f"{what}: shape {a_arr.shape} vs {b_arr.shape}"
    assert a_arr.dtype == b_arr.dtype, f"{what}: dtype {a_arr.dtype} vs {b_arr.dtype}"
    assert _b(a) == _b(b), f"{what}: not bit-identical\n ak  ={a!r}\n core={b!r}"


def _norm_payload(kind, payload):
    if kind == "group1":
        nodes, block = payload
        return (tuple(int(n) for n in nodes), np.asarray(block))
    if kind == "termination_share":
        node, z = payload
        return (int(node), complex(z))
    return payload


def _same_system(sa, sb, what):
    _same(sa.A, sb.A, f"{what}: A")
    _same(sa.rhs, sb.rhs, f"{what}: rhs")
    assert sa.n_nodes == sb.n_nodes
    assert sorted(sa.terminations) == sorted(sb.terminations)
    for k in sa.terminations:
        ta, tb = sa.terminations[k], sb.terminations[k]
        assert ta[0] == tb[0] and ta[2] == tb[2], f"{what}: termination {k}"
        _same(complex(ta[1]), complex(tb[1]), f"{what}: termination {k} value")
        _same(complex(ta[3]), complex(tb[3]), f"{what}: termination {k} z_chain")
    assert sa.z_ref_at.keys() == sb.z_ref_at.keys()
    for k in sa.z_ref_at:
        _same(complex(sa.z_ref_at[k]), complex(sb.z_ref_at[k]), f"{what}: z_ref_at")
    assert len(sa.probes) == len(sb.probes), f"{what}: probe count"
    for pa, pb in zip(sa.probes, sb.probes, strict=True):
        assert pa[0] == pb[0], f"{what}: probe label {pa[0]!r} vs {pb[0]!r}"
        assert pa[1] == pb[1], f"{what}: probe kind"
        assert getattr(pa, "key", None) == getattr(pb, "key", None), f"{what}: key"
        na, nb = _norm_payload(pa[1], pa[2]), _norm_payload(pb[1], pb[2])
        if pa[1] == "group1":
            assert na[0] == nb[0]
            _same(na[1], nb[1], f"{what}: probe {pa[0]} block")
        elif pa[1] == "termination_share":
            assert na[0] == nb[0]
            _same(na[1], nb[1], f"{what}: probe {pa[0]} z")
        else:
            assert na == nb, f"{what}: probe {pa[0]} payload"
    va, ja = sa.solve()
    vb, jb = sb.solve()
    _same(va, vb, f"{what}: v")
    _same(ja, jb, f"{what}: j")


def _outcome(fn):
    """`fn()`'s value, or the refusal it raised as (class name, message)."""
    try:
        return ("ok", fn())
    except (ValueError, NotImplementedError, ZeroDivisionError) as e:
        return ("refused", type(e).__name__, str(e))


def _same_outcome(oa, ob, what, compare):
    assert oa[0] == ob[0], f"{what}: ak {oa[:1] + oa[1:2]} vs core {ob[:1] + ob[1:2]}"
    if oa[0] == "refused":
        assert oa[1:] == ob[1:], f"{what}: refusals differ\n ak  ={oa}\n core={ob}"
    else:
        compare(oa[1], ob[1])
    return oa[0]


def _ab(case, f_mhz, c_light_mhz_m):
    built = {}
    for tag, ns in (("ak", ak), ("core", core)):
        built[tag] = _outcome(lambda ns=ns: _build(ns, case))
    if (
        _same_outcome(built["ak"], built["core"], "construction", lambda a, b: None)
        != "ok"
    ):
        return ("refused at construction",)
    outcomes = []
    (net_a, idx_a, n_real), (net_b, idx_b, _n) = built["ak"][1], built["core"][1]
    assert idx_a == idx_b
    y = _antenna_y(n_real, seed=n_real * 7 + len(idx_a))
    wl = _wl(f_mhz) if c_light_mhz_m is None else c_light_mhz_m / f_mhz
    red_a = ak.NetworkReducer(net_a, idx_a, len(idx_a), c_light_mhz_m=c_light_mhz_m)
    red_b = core.NetworkReducer(net_b, idx_b, len(idx_b), c_light_mhz_m=c_light_mhz_m)
    assert red_a.port_to_idx == red_b.port_to_idx
    assert red_a.n_nodes == red_b.n_nodes

    def cmp_list(a, b, what):
        assert len(a) == len(b), what
        for x, z in zip(a, b, strict=True):
            _same(complex(x), complex(z), what)

    outcomes.append(
        _same_outcome(
            _outcome(lambda: red_a.driven_impedance(y, wl)),
            _outcome(lambda: red_b.driven_impedance(y, wl)),
            "driven_impedance",
            lambda a, b: cmp_list(a, b, "driven_impedance"),
        )
    )
    outcomes.append(
        _same_outcome(
            _outcome(lambda: red_a.driven_impedance(y, wl, z_ref=75.0 + 5j)),
            _outcome(lambda: red_b.driven_impedance(y, wl, z_ref=75.0 + 5j)),
            "driven_impedance(z_ref=75+5j)",
            lambda a, b: cmp_list(a, b, "driven_impedance z_ref"),
        )
    )
    outcomes.append(
        _same_outcome(
            _outcome(lambda: red_a.driven_reflection(y, wl)),
            _outcome(lambda: red_b.driven_reflection(y, wl)),
            "driven_reflection",
            lambda a, b: cmp_list(a, b, "driven_reflection"),
        )
    )
    for z_ref in (0j, core.Z_REF_DEFAULT):

        def solved(red, z_ref=z_ref):
            s = red.apply_branches(y, wl, z_ref=z_ref)
            s.solve()
            return s

        outcomes.append(
            _same_outcome(
                _outcome(lambda: solved(red_a)),
                _outcome(lambda: solved(red_b)),
                f"apply_branches(z_ref={z_ref})",
                lambda a, b, z=z_ref: _same_system(a, b, f"apply_branches z_ref={z}"),
            )
        )

    def cmp_excited(a, b):
        va, eff_a, pin_a, bud_a = a
        vb, eff_b, pin_b, bud_b = b
        _same(va, vb, "excited V_full")
        _same(eff_a, eff_b, "efficiency")
        _same(pin_a, pin_b, "p_in")
        assert [r[0] for r in bud_a] == [r[0] for r in bud_b], "budget labels"
        assert [r.key for r in bud_a] == [r.key for r in bud_b], "budget keys"
        for ra, rb in zip(bud_a, bud_b, strict=True):
            _same(ra[1], rb[1], f"budget watts {ra[0]!r}")

    outcomes.append(
        _same_outcome(
            _outcome(lambda: red_a.excited_state(y, wl)),
            _outcome(lambda: red_b.excited_state(y, wl)),
            "excited_state",
            cmp_excited,
        )
    )
    return tuple(outcomes)


@pytest.mark.parametrize("c_light_mhz_m", _C_LIGHT_VARIANTS, ids=["si-c", "nec-c"])
@pytest.mark.parametrize("f_mhz", F_MHZ)
@pytest.mark.parametrize("name", sorted(CASES))
def test_the_copy_reduces_bit_for_bit_as_momwire_does(name, f_mhz, c_light_mhz_m):
    # Every case is written to answer on every path at every frequency, so
    # a pass here is a comparison of two answers, never of two refusals.
    assert _ab(CASES[name], f_mhz, c_light_mhz_m) == ("ok",) * 6


# --- refusals ------------------------------------------------------------------


def refusal_isolated_island(ns):
    # Two virtual nodes joined only to each other: rank-deficient MNA.
    return (
        {**_feed(ns), "m": ns.PortVirtual("m"), "n": ns.PortVirtual("n")},
        [ns.TL("rig", "ant", z0=50.0, length=3.0), ns.TwoPort("m", "n", r=10.0)],
        [ns.Driven("rig")],
    )


def refusal_unknown_port(ns):
    return (_feed(ns), [ns.TwoPort("rig", "nowhere", r=1.0)], [ns.Driven("rig")])


def refusal_cm_floating(ns):
    # A CM-open line's far pair touches nothing else: common-mode floating.
    return (
        {
            "ant": ns.PortOnWire("ant"),
            "p": ns.PortVirtual("p"),
            "q": ns.PortVirtual("q"),
            "r1": ns.PortVirtual("r1"),
            "r2": ns.PortVirtual("r2"),
        },
        [
            ns.TwoPort("ant", "p", r=1.0),
            ns.TwoPort("ant", "q", r=1.0),
            ns.BalancedLine("p", "q", "r1", "r2", zdiff=300.0, length=2.0),
        ],
        [ns.Driven("ant")],
    )


def refusal_drives_a_floating_gap(ns):
    return (
        {"ant": ns.PortOnWire("ant"), "gap": ns.PortOnWireFloating("gap")},
        [ns.TwoPort("gap.p", "gap.n", r=5.0)],
        [ns.Driven("ant"), ns.Driven("gap")],
    )


def refusal_no_sources(ns):
    return (_feed(ns), [ns.TL("rig", "ant", z0=50.0, length=1.0)], [])


def refusal_open_driven_stub(ns):
    # A lossless λ/4 open stub across the driven port shorts it at 14.2 MHz:
    # the impedance path answers Z = 0, the ideal-generator excited path has
    # no finite solution (`excited_state`'s docstring).
    return (
        {**_feed(ns), "stub": ns.PortVirtual("stub")},
        [
            ns.TL("rig", "ant", z0=50.0, length=4.0),
            ns.TL("rig", "stub", z0=50.0, length=_wl(14.2) / 4.0),
        ],
        [ns.Driven("rig")],
    )


REFUSALS = {
    name[len("refusal_") :]: fn
    for name, fn in sorted(globals().items())
    if name.startswith("refusal_") and callable(fn)
}


@pytest.mark.parametrize("name", sorted(REFUSALS))
def test_the_copy_refuses_what_momwire_refuses(name):
    """Each of these is refused somewhere (at construction, at the solve, or
    on one path only); `_ab` asserts both reducers refuse at the same point,
    with the same class name and the same message, and agree bit for bit
    wherever they answer."""
    outcomes = _ab(REFUSALS[name], 14.2, None)
    assert any(o != "ok" for o in outcomes), outcomes


def test_the_refusals_are_refusals():
    """Pin that each refusal case actually refuses on the copy, so the A/B
    above cannot pass by both reducers happily answering."""
    wl = _wl(14.2)

    def refused(case):
        try:
            net, idx, n_real = _build(ak, case)
        except (ValueError, NotImplementedError):
            return "construction"
        red = ak.NetworkReducer(net, idx, len(idx))
        y = _antenna_y(n_real, seed=3)
        try:
            red.excited_state(y, wl)
        except ak.SingularNetworkError:
            return "solve"
        return None

    assert refused(refusal_isolated_island) == "solve"
    assert refused(refusal_unknown_port) == "construction"
    assert refused(refusal_cm_floating) == "construction"
    assert refused(refusal_drives_a_floating_gap) == "construction"
    assert refused(refusal_no_sources) == "construction"
    assert refused(refusal_open_driven_stub) == "solve"


def test_every_branch_type_is_covered():
    """The case list covers every branch, port and source class the copy
    defines, so a new one added without a case fails here."""
    seen = set()
    for case in CASES.values():
        ports, branches, sources = case(ak)[:3]
        seen.update(type(x).__name__ for x in (*ports.values(), *branches, *sources))
    want = {
        "TL", "Load", "TwoPort", "Shunt", "Transformer", "Autotransformer",
        "BalancedLine", "FloatingBalun", "Admittance", "TouchstoneLoad",
        "TouchstoneTwoPort", "Driven", "DrivenCurrent", "PortOnWire",
        "PortOnWireFloating", "PortVirtual", "PortAtEnd", "PortAtVertex",
    }  # fmt: skip
    assert want <= seen, sorted(want - seen)
    import dataclasses

    defined = {
        n
        for n in ak.__all__
        if isinstance(getattr(ak, n), type) and dataclasses.is_dataclass(getattr(ak, n))
    }
    # PortAtEdge is an abstract base the engines never hand a reducer; Cable
    # is a line spec (covered through TL.from_cable); Network is the container.
    assert defined - seen <= {"PortAtEdge", "Cable", "Network"}, sorted(defined - seen)


def test_the_two_namespaces_are_different_classes():
    """The A/B is between two implementations, not one object twice."""
    assert ak.NetworkReducer is not core.NetworkReducer
    assert ak.TL is not core.TL
    assert ak.MNASystem is not core.MNASystem
    assert ak.NetworkReducer.__module__ == "antennaknobs.mw.networks._reducer"
