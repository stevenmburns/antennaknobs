"""The L tuner that tunes itself: ``station.l_network_tuner(tune_to=...)``
(AK#1646).

A fixed ``l_network_tuner`` is a series L and a shunt C with values the design
chooses. Given ``tune_to`` instead, it is an automatic tuner: at its tune
frequency it chooses its own two components to present ``tune_to`` ohms at
its ``rig`` side, from whatever hangs on its ``out`` side (the antenna, and
any line or balun between), and then holds them.

Two options shape the box (USER DECISIONS 2026-09-22):

* ``mode``, the parts: ``"low"`` series L, shunt C (the default; a low-pass
  L), ``"high"`` series C, shunt L, ``"ll"`` both coils, ``"cc"`` both
  capacitors;
* ``shunt_at``, where the shunt part sits: ``"out"`` across the antenna side
  (the default, as on the fixed-value tuner), ``"rig"`` across the
  transmitter side, or ``"auto"``, which takes the side the load calls for,
  as an L autotuner's relay moves its capacitor: ``"out"`` when the load's
  RESISTANCE is above the target (it must come down), ``"rig"`` when it is
  below (it must come up), and the other side only if that one cannot
  match. For ``"low"`` and ``"high"`` the order never matters: no load can be
  matched from both sides. (A lossless low-pass L would need both
  |Z|^2 / R < target and target < R; high pass is the dual. Measured too:
  0 of 7260 loads over R 1-2000 ohm, X +-3000 ohm.) So SimNEC's automatic LC
  match, whose manual gives this rule without saying whether "the impedance
  must be increased or reduced" means R or |Z|, lands on the same side either
  way. The order decides only for ``"ll"`` and ``"cc"``, where 1225 of those
  loads have both.

A fixed side can only step a load one way, so a box with one can meet loads
it cannot match; that is the point of being able to model one.

The tune frequency is ``tune_at_mhz``, else the design frequency. The tuner
does NOT retune as the measurement frequency moves, so a sweep shows the
tuned network's bandwidth. A load no network of the allowed kinds can match
is reported and the tuner bypassed (both elements at zero: a 0 H series arm
is a short, a 0 F shunt an open), so the readout shows the mismatch, as a
real tuner that finds no match leaves it.

The component values are the solving ENGINE's: it tunes from its own antenna
impedance. :func:`make_reducer` finds the tuner in the flattened network (its
`Composite` carries the :class:`Tuning`), derives the circuit on its ``out``
side, and tunes before the first reduction. SimNEC's XMATCH element imports
as this component; solved for SimNEC's own antenna impedance on AC6LA's
``snBydipole1-LC1.ssn`` (76.78 - j65.79 ohm at 14 MHz, Qc 2000, Ql 200), the
low-pass tuning is C = 37.520 pF and L = 731.94 nH, the two values SimNEC
shows greyed for that element.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, replace
from itertools import pairwise

import numpy as np
from momwire.networks import (
    C_LIGHT,
    Driven,
    NetworkReducer,
    PortVirtual,
    Shunt,
    TwoPort,
)

MODES = ("low", "high", "ll", "cc")
SIDES = ("out", "rig", "auto")
# (series kind, shunt kind) per mode.
_KINDS = {"low": ("L", "C"), "high": ("C", "L"), "ll": ("L", "L"), "cc": ("C", "C")}


class TunerAdvisory(UserWarning):
    """A tuner found no match at its tune frequency and was bypassed."""


@dataclass(frozen=True)
class LTuner:
    """The tuning MECHANISM attached to an L-match unit: present ``target``
    ohms at ``f_mhz`` (None: the design frequency), with components of
    ``mode``'s kinds, the shunt at ``shunt_at``, and the given Q's.

    It owns the box's topology. `body` returns the branches for a load — one
    kind pair, one side — and the unit carries a BYPASS (a 0 H series arm, a
    wire) until it is tuned, which is what a tuner is before it tunes. So no
    invented component value is ever in a network: an engine that does not
    tune one sees the box out of circuit, and a tuned one holds the parts the
    mechanism chose, where it put them.

    An engine finds it as the `Composite.tuner` of an instance
    (`find_tuners`). Another mechanism — the T network of AK#1661 — is any
    object with this `body` and a ``f_mhz`` of its own.
    """

    target: float
    mode: str = "low"
    shunt_at: str = "out"
    f_mhz: float | None = None
    qc: float | None = None
    ql: float | None = None

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"tuner mode {self.mode!r} is not one of {MODES}")
        if self.shunt_at not in SIDES:
            raise ValueError(f"shunt_at={self.shunt_at!r} is not one of {SIDES}")
        if isinstance(self.target, complex) or not float(self.target) > 0.0:
            raise ValueError(
                f"tune_to={self.target!r}: a tuner tunes to a positive resistance "
                "in ohms"
            )
        if self.f_mhz is not None and not float(self.f_mhz) > 0.0:
            raise ValueError(f"tune_at_mhz={self.f_mhz!r} must be positive")

    def body(self, rig: str, out: str, z_load: complex, f_mhz: float):
        """``(branches, design)`` for this load: the real L network, or the
        bypass when nothing matches (which `design.matched` records)."""
        try:
            design = design_l_match(
                z_load,
                self.target,
                f_mhz,
                self.mode,
                shunt_at=self.shunt_at,
                qc=self.qc,
                ql=self.ql,
            )
        except NoMatch as exc:
            side = "out" if self.shunt_at == "auto" else self.shunt_at
            design = LMatchDesign(
                self.mode, side, 0.0, 0.0, f_mhz, z_load, matched=False, bypass=True
            )
            design = replace(design, no_match=str(exc))
        if design.bypass:
            return (bypass_body(rig, out), design)
        if design.series_kind == "L":
            series = TwoPort(a=rig, b=out, l=design.series, ql=self.ql)
        else:
            series = TwoPort(a=rig, b=out, c=design.series, qc=self.qc)
        node = out if design.shunt_at == "out" else rig
        if design.shunt_kind == "L":
            shunt = Shunt(port=node, l=design.shunt, ql=self.ql)
        else:
            shunt = Shunt(port=node, c=design.shunt, qc=self.qc)
        return ((series, shunt), design)


@dataclass(frozen=True)
class LMatchDesign:
    """What a tuner tuned to: the kinds it used (a fixed mode's name), which
    side the shunt sits on (``"out"``, across the load, or ``"rig"``), and the
    two values in SI units (henries, farads). ``bypass`` is the tuner out of
    circuit: with ``matched`` True the load was already at the target, with
    ``matched`` False nothing could match it."""

    mode: str
    shunt_at: str
    series: float
    shunt: float
    f_mhz: float
    z_load: complex
    matched: bool = True
    bypass: bool = False
    #: Why nothing matched, for the advisory; None when something did.
    no_match: str | None = None

    @property
    def series_kind(self) -> str:
        return _KINDS[self.mode][0]

    @property
    def shunt_kind(self) -> str:
        return _KINDS[self.mode][1]


class NoMatch(ValueError):
    """No L network of the allowed kinds presents the target."""


def _element_z(kind: str, value: float, omega: float, qc, ql) -> complex:
    """One component's impedance, with the loss the reducer stamps for it, so
    the tuned match is exact in the network that carries it: the public
    `TwoPort` / `Shunt` contract, a coil's series R = omega*L/Q and a
    capacitor's ESR = 1/(omega*C*Q). The engine tests hold the tuned match to
    1e-6 ohm, which is what would notice the two ever parting."""
    if kind == "L":
        z = 1j * omega * value
        return z + (omega * value / ql if ql else 0.0)
    z = 1.0 / (1j * omega * value)
    return z + (1.0 / (omega * value * qc) if qc else 0.0)


def _z_in(kinds, shunt_at, series, shunt, z_load, omega, qc, ql) -> complex:
    z_ser = _element_z(kinds[0], series, omega, qc, ql)
    y_sh = 1.0 / _element_z(kinds[1], shunt, omega, qc, ql)
    if shunt_at == "out":
        return z_ser + 1.0 / (1.0 / z_load + y_sh)
    return 1.0 / (1.0 / (z_ser + z_load) + y_sh)


def _lossless_starts(kinds, shunt_at, z_load, r_t, omega):
    """The lossless solutions for one topology whose reactances have the
    SIGNS ``kinds`` allows, as (series, shunt) component values."""
    roots = []
    if shunt_at == "out":
        y_l = 1.0 / z_load
        g, b_l = y_l.real, y_l.imag
        disc = g / r_t - g * g
        if disc < 0.0:
            return []
        for b_total in (math.sqrt(disc), -math.sqrt(disc)):
            roots.append((-(1.0 / complex(g, b_total)).imag, b_total - b_l))
    else:
        r_l, x_l = z_load.real, z_load.imag
        disc = r_l * r_t - r_l * r_l
        if disc < 0.0:
            return []
        for x_total in (math.sqrt(disc), -math.sqrt(disc)):
            roots.append((x_total - x_l, -(1.0 / complex(r_l, x_total)).imag))
    out = []
    for x_ser, b_sh in roots:
        if kinds[0] == "L" and x_ser > 0.0:
            series = x_ser / omega
        elif kinds[0] == "C" and x_ser < 0.0:
            series = -1.0 / (omega * x_ser)
        else:
            continue
        if kinds[1] == "C" and b_sh > 0.0:
            shunt = b_sh / omega
        elif kinds[1] == "L" and b_sh < 0.0:
            shunt = -1.0 / (omega * b_sh)
        else:
            continue
        out.append((series, shunt))
    return out


def design_l_match(
    z_load: complex,
    target: float,
    f_mhz: float,
    mode: str = "low",
    *,
    shunt_at: str = "out",
    qc: float | None = None,
    ql: float | None = None,
) -> LMatchDesign:
    """The L network of ``mode``'s kinds, with its shunt at ``shunt_at``,
    that presents ``target`` ohms when ``z_load`` hangs on its output, at
    ``f_mhz``, with the components' finite Q included. ``shunt_at="auto"``
    tries the side the load calls for first (``"out"`` when its resistance
    is above the target, ``"rig"`` when below) and the other only if that
    one cannot match. Raises `NoMatch` when there is no solution."""
    from scipy.optimize import fsolve

    if mode not in MODES:
        raise ValueError(f"tuner mode {mode!r} is not one of {MODES}")
    if shunt_at not in SIDES:
        raise ValueError(f"shunt_at={shunt_at!r} is not one of {SIDES}")
    z_load, r_t = complex(z_load), float(target)
    omega = 2.0 * math.pi * f_mhz * 1e6
    if abs(z_load - r_t) <= 1e-9 * r_t:
        # Already at the target: both elements would go to zero, and a zero
        # series C is an open, not a wire. The tuner stays out of circuit.
        side = "out" if shunt_at == "auto" else shunt_at
        return LMatchDesign(mode, side, 0.0, 0.0, f_mhz, z_load, bypass=True)
    if shunt_at == "auto":
        sides = ("out", "rig") if z_load.real >= r_t else ("rig", "out")
    else:
        sides = (shunt_at,)
    kinds = _KINDS[mode]
    for side in sides:
        # At most one start per side satisfies the parts' signs: the series
        # reactance and the total shunt susceptance share a sign.
        for start in _lossless_starts(kinds, side, z_load, r_t, omega):

            def residual(x, kinds=kinds, side=side):
                z = _z_in(
                    kinds, side, math.exp(x[0]), math.exp(x[1]), z_load, omega, qc, ql
                )
                d = (z - r_t) / r_t
                return [d.real, d.imag]

            x, _info, ok, _msg = fsolve(
                residual, np.log(start), full_output=True, xtol=1e-13
            )
            if ok != 1 or max(abs(v) for v in residual(x)) > 1e-9:
                continue
            series, shunt = math.exp(x[0]), math.exp(x[1])
            return LMatchDesign(mode, side, series, shunt, f_mhz, z_load)
    where = {
        "out": "with its shunt at out",
        "rig": "with its shunt at rig",
        "auto": "with its shunt on either side",
    }[shunt_at]
    raise NoMatch(
        f"no {mode} L network {where} presents {r_t:g} ohm for a load of "
        f"{z_load.real:.4g} {'+' if z_load.imag >= 0 else '-'} "
        f"j{abs(z_load.imag):.4g} ohm at {f_mhz:g} MHz"
    )


def bypass_body(rig: str, out: str):
    """A tuner out of circuit: one 0 H series arm, which is a wire (issue
    #285's degenerate values). The body an untuned unit carries."""
    return (TwoPort(a=rig, b=out, l=0.0),)


# --- finding the tuner in a network -----------------------------------------


@dataclass(frozen=True)
class _Tuner:
    path: str
    mechanism: object
    indices: tuple[int, ...]
    rig: str
    out: str

    @property
    def name(self) -> str:
        """The instance name, for what the readout says (paths end in '.')."""
        return self.path.rstrip(".")


def find_tuners(net) -> list[_Tuner]:
    """Every unit in a flattened network with a tuning mechanism attached:
    its instance path, the mechanism, the branches its body currently
    occupies, and the two nodes the box spans."""
    found = []
    composites = getattr(net, "composites", None) or {}
    paths = list(getattr(net, "branch_paths", None) or [])
    for path, comp in composites.items():
        mechanism = getattr(comp, "tuner", None)
        if mechanism is None:
            continue
        idx = tuple(i for i, p in enumerate(paths) if p == path)
        series = net.branches[idx[0]]
        found.append(_Tuner(path, mechanism, idx, series.a, series.b))
    return found


def _load_side(net, tuner: _Tuner):
    """The circuit on the tuner's ``out`` side, driven at ``out``: what the
    tuner sees. Refuses a tuner that is not the only path from its rig side
    to what it drives, or that has a source beyond it."""
    from .schematic import terminals_of

    parent: dict[str, str] = {}

    def find(n):
        while parent.setdefault(n, n) != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    rest = [br for i, br in enumerate(net.branches) if i not in tuner.indices]
    for br in rest:
        nodes = terminals_of(br)
        for a, b in pairwise(nodes):
            parent[find(a)] = find(b)
    side = find(tuner.out)
    if find(tuner.rig) == side:
        raise NotImplementedError(
            f"tuner {tuner.name!r} is not the only path between its rig and out "
            "sides, so there is no load for it to tune to"
        )
    for src in net.sources:
        if find(src.port) == side:
            raise NotImplementedError(
                f"tuner {tuner.name!r} has a source on its out side; a tuner "
                "tunes to a passive load"
            )
    ports = {n: p for n, p in net.ports.items() if find(n) == side}
    branches = [br for br in rest if all(find(n) == side for n in terminals_of(br))]
    return type(net)(
        ports=ports, branches=branches, sources=[Driven(port=tuner.out, voltage=1.0)]
    )


# --- the reducer --------------------------------------------------------------


class AutoMatchReducer:
    """A `NetworkReducer` whose tuner tunes on the way in.

    The first call that carries a wavelength tunes the tuner at its tune
    frequency, builds the network with the tuned branches in place of the
    placeholders, and every such call delegates to an ordinary reducer over
    that network. Everything else delegates to the reducer that served the
    last such call, or to one over the placeholder network, whose ports and
    sources are the same.
    """

    def __init__(
        self,
        net,
        tuner: _Tuner,
        port_to_idx,
        n_total_ports,
        y_at,
        *,
        design_freq_mhz=None,
        wavelength_for=None,
    ):
        self._net = net
        self._tuner = tuner
        self._port_to_idx = dict(port_to_idx)
        self._n_total = n_total_ports
        self._y_at = y_at
        f_mhz = tuner.mechanism.f_mhz or design_freq_mhz
        if not f_mhz:
            raise ValueError(
                f"tuner {tuner.name!r} has no tune_at_mhz and the design no "
                "design frequency to tune at"
            )
        self.f_mhz = float(f_mhz)
        # The engine's own MHz -> metres. SI for a deck-writing engine; an
        # imported deck on momwire solves at NEC's metre-megahertz product
        # (AK#1607), and a tuner tuned at any other wavelength would be tuned
        # for a slightly different frequency than the one it is used at.
        wl_for = wavelength_for or (lambda f: C_LIGHT / (f * 1e6))
        self._wavelength = float(wl_for(self.f_mhz))
        self._structural = NetworkReducer(net, port_to_idx, n_total_ports)
        self._last = self._structural
        self._tuned: NetworkReducer | None = None
        self._body: tuple = ()
        self.design: LMatchDesign | None = None
        n_virtual = sum(isinstance(p, PortVirtual) for p in net.ports.values())
        self._n_real = n_total_ports - n_virtual
        self._load = _load_side(net, tuner)

    def _load_impedance(self, y_real) -> complex:
        side = self._load
        idx = {
            n: self._port_to_idx[n]
            for n, p in side.ports.items()
            if not isinstance(p, PortVirtual)
        }
        nxt = self._n_real
        for n, p in side.ports.items():
            if isinstance(p, PortVirtual):
                idx[n] = nxt
                nxt += 1
        red = NetworkReducer(side, idx, nxt)
        z = red.driven_impedance(y_real, self._wavelength)
        return complex(np.atleast_1d(z)[0])

    def tune(self, y_real=None) -> LMatchDesign:
        """Tune (once): design at the tune wavelength from the load's
        impedance there, or bypass with a warning when nothing matches.

        The components are evaluated at the frequency the REDUCER reads off
        that wavelength, so the match is exact in the network that carries it.
        """
        if self.design is not None:
            return self.design
        if y_real is None:
            y_real = self._y_at(self._wavelength)
        z_load = self._load_impedance(y_real)
        t = self._tuner
        # The mechanism owns the topology: it returns the branches its box
        # holds for this load, and what it tuned to.
        body, design = t.mechanism.body(
            t.rig, t.out, z_load, C_LIGHT / self._wavelength / 1e6
        )
        design = replace(design, f_mhz=self.f_mhz)
        if design.no_match:
            warnings.warn(
                f"tuner {t.name}: {design.no_match}; bypassed",
                TunerAdvisory,
                stacklevel=2,
            )
        self.design, self._body = design, body
        return design

    def _reducer_for(self, y_real, wavelength) -> NetworkReducer:
        same = math.isclose(wavelength, self._wavelength, rel_tol=1e-12)
        self.tune(y_real if same else None)
        if self._tuned is None:
            self._tuned = NetworkReducer(
                self.tuned_network(), self._port_to_idx, self._n_total
            )
        self._last = self._tuned
        return self._tuned

    def tuned_network(self):
        """The network with the unit's tuned body spliced in where its
        bypass was. The body may hold a different number of branches than the
        bypass, so the splice goes by INSTANCE PATH, and the new branches
        carry that path: the power budget still attributes them to the box."""
        t = self._tuner
        at = t.indices[0]
        branches, paths = [], []
        for i, (br, path) in enumerate(
            zip(self._net.branches, self._net.branch_paths, strict=True)
        ):
            if i == at:
                branches.extend(self._body)
                paths.extend([t.path] * len(self._body))
            elif i not in t.indices:
                branches.append(br)
                paths.append(path)
        net = type(self._net)(
            ports=dict(self._net.ports),
            branches=branches,
            sources=list(self._net.sources),
        )
        net.branch_paths = paths
        net.composites = dict(self._net.composites)
        return net

    # -- what the readout reports ------------------------------------------
    def tuner_rows(self) -> list[dict]:
        """Readout rows (the issue #712 shape) for what the tuner tuned to."""
        d = self.design
        group = f"tuner {self._tuner.name}"
        if d is None:
            return []
        if d.bypass:
            why = "already at the target" if d.matched else "no match"
            return [
                {
                    "label": "tuned",
                    "value": f"{why} at {d.f_mhz:g} MHz, bypassed",
                    "unit": None,
                    "group": group,
                }
            ]
        rows = []
        for where, kind, value in (
            ("series", d.series_kind, d.series),
            ("shunt", d.shunt_kind, d.shunt),
        ):
            rows.append(
                {
                    "label": f"{where} {kind}",
                    "value": round(value * (1e6 if kind == "L" else 1e12), 6),
                    "unit": "µH" if kind == "L" else "pF",
                    "group": group,
                }
            )
        rows.append(
            {
                "label": "tuned",
                "value": f"{d.mode} at {d.f_mhz:g} MHz, shunt at {d.shunt_at}",
                "unit": None,
                "group": group,
            }
        )
        return rows

    def tuner_advisories(self) -> list[dict]:
        d = self.design
        if d is None or d.matched:
            return []
        t = self._tuner.mechanism
        z = d.z_load
        return [
            {
                "category": "tuner",
                "text": (
                    f"Tuner {self._tuner.name} found no {t.mode} L network "
                    f"{'with its shunt on either side' if t.shunt_at == 'auto' else f'with its shunt at {t.shunt_at}'} that "
                    f"presents {t.target:g} Ω for the {z.real:.4g} "
                    f"{'+' if z.imag >= 0 else '−'} j{abs(z.imag):.4g} Ω it sees "
                    f"at {d.f_mhz:g} MHz, so it is bypassed and the readout "
                    "shows the mismatch."
                ),
            }
        ]

    # -- the reducer surface -------------------------------------------------
    def apply_branches(self, Y_real, wavelength, **kw):
        red = self._reducer_for(Y_real, wavelength)
        return red.apply_branches(Y_real, wavelength, **kw)

    def driven_impedance(self, Y_real, wavelength, **kw):
        red = self._reducer_for(Y_real, wavelength)
        return red.driven_impedance(Y_real, wavelength, **kw)

    def driven_reflection(self, Y_real, wavelength, **kw):
        red = self._reducer_for(Y_real, wavelength)
        return red.driven_reflection(Y_real, wavelength, **kw)

    def excited_state(self, Y_real, wavelength):
        return self._reducer_for(Y_real, wavelength).excited_state(Y_real, wavelength)

    def resolve_voltages(self, system):
        return self._last.resolve_voltages(system)

    def __getattr__(self, name):
        # Shape-only members (n_driven, the port maps): the same whatever the
        # tuner tuned to, so the placeholder reducer answers them.
        return getattr(self._structural, name)


def design_freq_mhz(builder) -> float | None:
    """A builder's design frequency, the tune frequency a tuner without
    ``tune_at_mhz`` uses: ``design_freq``, else ``freq``."""
    for name in ("design_freq", "freq"):
        f = getattr(builder, name, None)
        if f:
            return float(f)
    return None


def make_reducer(
    net,
    port_to_idx,
    n_total_ports,
    *,
    y_at=None,
    design_freq_mhz=None,
    wavelength_for=None,
):
    """The engine's reducer: a plain `NetworkReducer`, or an
    `AutoMatchReducer` when the network holds a self-tuning L tuner."""
    tuners = find_tuners(net)
    if not tuners:
        return NetworkReducer(net, port_to_idx, n_total_ports)
    if len(tuners) > 1:
        raise NotImplementedError(
            "a network with more than one self-tuning L tuner is not supported: "
            "each one's load would include the other's tuning"
        )
    if y_at is None:
        raise NotImplementedError(
            "this engine cannot tune an L tuner: it has no port admittance to "
            "tune it from"
        )
    return AutoMatchReducer(
        net,
        tuners[0],
        port_to_idx,
        n_total_ports,
        y_at,
        design_freq_mhz=design_freq_mhz,
        wavelength_for=wavelength_for,
    )


def tuner_rows(eng) -> list[dict]:
    """The engine's tuner readout rows, [] when it has no self-tuning tuner."""
    red = getattr(eng, "_reducer", None)
    return red.tuner_rows() if isinstance(red, AutoMatchReducer) else []


def tuner_advisories(eng) -> list[dict]:
    """The engine's "no match, bypassed" advisory, [] otherwise."""
    red = getattr(eng, "_reducer", None)
    return red.tuner_advisories() if isinstance(red, AutoMatchReducer) else []
