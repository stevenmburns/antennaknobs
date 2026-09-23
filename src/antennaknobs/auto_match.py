"""The tuners that tune themselves: ``station.l_network_tuner(tune_to=...)``
(AK#1646) and ``station.t_network_tuner(tune_to=...)`` (AK#1661, `TTuner`,
whose rule for its third part is documented there). Both take component
ranges (`Ranges`): a tuning that needs a part a real box does not have is not
a match. The rest of this note is the L tuner's.

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
    """A tuner found no match at its tune frequency: bypassed, or tuned for
    best effort (AK#1663)."""


@dataclass(frozen=True)
class Ranges:
    """What a real tuner's parts can reach (AK#1661), in SI units (farads,
    henries); None is unbounded. A tuning that needs a part outside its
    range is not a match: the algebra will happily ask for a 900 pF
    capacitor nobody owns."""

    c_min: float | None = None
    c_max: float | None = None
    l_min: float | None = None
    l_max: float | None = None

    def __post_init__(self):
        for kind in ("c", "l"):
            lo, hi = getattr(self, f"{kind}_min"), getattr(self, f"{kind}_max")
            for v in (lo, hi):
                if v is not None and not float(v) > 0.0:
                    raise ValueError(f"a component range must be positive, got {v!r}")
            if lo is not None and hi is not None and lo > hi:
                raise ValueError(
                    f"{kind}_min {_value_str(kind.upper(), lo)} is above "
                    f"{kind}_max {_value_str(kind.upper(), hi)}"
                )

    def outside(self, kind: str, value: float) -> str | None:
        """Why ``value`` (a part of ``kind`` "L" or "C") is out of range, or
        None when it is in."""
        lo = self.l_min if kind == "L" else self.c_min
        hi = self.l_max if kind == "L" else self.c_max
        if lo is not None and value < lo * (1.0 - 1e-12):
            return (
                f"{_value_str(kind, value)} is below its minimum {_value_str(kind, lo)}"
            )
        if hi is not None and value > hi * (1.0 + 1e-12):
            return (
                f"{_value_str(kind, value)} is above its maximum {_value_str(kind, hi)}"
            )
        return None

    @classmethod
    def from_radio_units(cls, c_min_pF, c_max_pF, l_min_uH, l_max_uH) -> Ranges:
        def si(v, scale):
            return None if v is None else float(v) * scale

        return cls(
            si(c_min_pF, 1e-12), si(c_max_pF, 1e-12),
            si(l_min_uH, 1e-6), si(l_max_uH, 1e-6),
        )  # fmt: skip


def _value_str(kind: str, value: float) -> str:
    """A part's value in radio units, for what the tuner says."""
    if kind == "L":
        return f"{value * 1e6:.4g} µH"
    return f"{value * 1e12:.4g} pF"


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
    (`find_tuners`). Another mechanism — the T network, `TTuner` — is any
    object with this `body`, a ``describe``, and a ``f_mhz`` of its own.
    """

    target: float
    mode: str = "low"
    shunt_at: str = "out"
    f_mhz: float | None = None
    qc: float | None = None
    ql: float | None = None
    ranges: Ranges = Ranges()
    #: What to do when the target is out of reach but the topology could
    #: match in principle (AK#1663): "best", the lowest SWR the parts give,
    #: or "bypass", the box out of circuit.
    on_no_match: str = "best"

    def __post_init__(self):
        if self.on_no_match not in ON_NO_MATCH:
            raise ValueError(
                f"on_no_match={self.on_no_match!r} is not one of {ON_NO_MATCH}"
            )
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
                ranges=self.ranges,
            )
        except NoMatch as exc:
            why = str(exc)
            design = None
            if exc.reachable and self.on_no_match == "best":
                design = best_l_match(
                    z_load, self.target, f_mhz, self.mode, shunt_at=self.shunt_at,
                    qc=self.qc, ql=self.ql, ranges=self.ranges, why=why,
                )  # fmt: skip
                worse = _no_better_than_bypass(design, self.target)
                if worse:
                    why, design = f"{why}, and {worse}", None
            if design is None:
                side = "out" if self.shunt_at == "auto" else self.shunt_at
                design = LMatchDesign(
                    self.mode, side, 0.0, 0.0, f_mhz, z_load,
                    matched=False, bypass=True, no_match=why,
                )  # fmt: skip
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

    def describe(self) -> str:
        """What the box is, for the advisory: "low L network with its shunt
        at out"."""
        where = (
            "with its shunt on either side"
            if self.shunt_at == "auto"
            else f"with its shunt at {self.shunt_at}"
        )
        return f"{self.mode} L network {where}"


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
    #: The SWR a best-effort tuning reached (AK#1663); None for an exact
    #: match or a bypass. With it set, the parts are in circuit and
    #: ``no_match`` says why the target was out of reach.
    best_swr: float | None = None

    @property
    def series_kind(self) -> str:
        return _KINDS[self.mode][0]

    @property
    def shunt_kind(self) -> str:
        return _KINDS[self.mode][1]

    @property
    def parts(self) -> list[tuple[str, str, float]]:
        """(readout label, kind, SI value) for each part it tuned."""
        return [
            (f"series {self.series_kind}", self.series_kind, self.series),
            (f"shunt {self.shunt_kind}", self.shunt_kind, self.shunt),
        ]

    @property
    def summary(self) -> str:
        return (
            f"{self.mode} at {self.f_mhz:g} MHz, shunt at {self.shunt_at}"
            + _best_effort_note(self)
        )


class NoMatch(ValueError):
    """No network of the allowed kinds presents the target.

    ``reachable`` says whether the topology could in principle: True when a
    lossless solution exists but a part's range (or the parts' loss) rules
    it out, which is where a best-effort tuning is worth having (AK#1663);
    False when there is no solution at all, and the tuner can do nothing."""

    def __init__(self, message: str, *, reachable: bool = False):
        super().__init__(message)
        self.reachable = reachable


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
    ranges: Ranges | None = None,
) -> LMatchDesign:
    """The L network of ``mode``'s kinds, with its shunt at ``shunt_at``,
    that presents ``target`` ohms when ``z_load`` hangs on its output, at
    ``f_mhz``, with the components' finite Q included. ``shunt_at="auto"``
    tries the side the load calls for first (``"out"`` when its resistance
    is above the target, ``"rig"`` when below) and the other only if that
    one cannot match. A solution with a part outside ``ranges`` is not one.
    Raises `NoMatch` when there is no solution."""
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
    ranges = ranges or Ranges()
    out_of_range: list[str] = []
    reachable = False
    for side in sides:
        # At most one start per side satisfies the parts' signs: the series
        # reactance and the total shunt susceptance share a sign.
        for start in _lossless_starts(kinds, side, z_load, r_t, omega):
            reachable = True

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
            why = [
                f"its {where} {kind} {reason}"
                for where, kind, value in (
                    ("series", kinds[0], series),
                    ("shunt", kinds[1], shunt),
                )
                if (reason := ranges.outside(kind, value))
            ]
            if why:
                out_of_range.append(f"with its shunt at {side}, " + " and ".join(why))
                continue
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
        + (
            " within its component ranges (" + "; ".join(out_of_range) + ")"
            if out_of_range
            else ""
        ),
        reachable=reachable,
    )


def bypass_body(rig: str, out: str):
    """A tuner out of circuit: one 0 H series arm, which is a wire (issue
    #285's degenerate values). The body an untuned unit carries."""
    return (TwoPort(a=rig, b=out, l=0.0),)


# --- the T network (AK#1661) -------------------------------------------------

T_PARTS = ("c1", "l", "c2")
PINS = ("c1", "c2", "auto")
#: Which capacitor a T with all three parts free holds at its maximum: both,
#: keeping the less lossy tuning. Measured (AK#1661,
#: ``scratch/1661-t-tuner/pin_loss.py``; 625 loads, R 5-2000 ohm, X +-1500
#: ohm, 3.6-28.5 MHz, c_max 250 / 500 pF, Ql 75-300, Qc 500-5000): the pin
#: barely moves the LOSS (where both match, at most 0.14 dB apart) but it
#: decides the REACH, and the two pins reach different loads. C2 at its
#: maximum matches 2-7x as many loads as C1 does, yet C1 alone reaches up to
#: 221 of them (3.6 MHz, 250 pF), so either pin by itself gives up loads the
#: other would match.
DEFAULT_PIN = "auto"


@dataclass(frozen=True)
class TMatchDesign:
    """What a T tuner tuned to: C1 (rig side), L (the shunt coil at the tee
    midpoint) and C2 (antenna side) in SI units, and which of them were not
    tuned: ``given`` (the design fixed them) and ``pinned`` (the capacitor a
    fully free T held at its maximum, or None). ``bypass`` and ``matched``
    mean what they do on `LMatchDesign`."""

    c1: float
    l: float
    c2: float
    f_mhz: float
    z_load: complex
    given: tuple[str, ...] = ()
    pinned: str | None = None
    #: The fraction of the rig's power that reaches the load, from the
    #: parts' Q's (1.0 when lossless).
    efficiency: float = 1.0
    matched: bool = True
    bypass: bool = False
    no_match: str | None = None
    best_swr: float | None = None

    @property
    def parts(self) -> list[tuple[str, str, float]]:
        return [("C1", "C", self.c1), ("L", "L", self.l), ("C2", "C", self.c2)]

    @property
    def summary(self) -> str:
        held = [f"{p.upper()} given" for p in self.given]
        if self.pinned:
            held.append(f"{self.pinned.upper()} at its maximum")
        return (
            f"T at {self.f_mhz:g} MHz"
            + (", " + ", ".join(held) if held else "")
            + _best_effort_note(self)
        )


def _t_z_in(c1, l, c2, z_load, omega, qc, ql) -> complex:
    z_m = 1.0 / (
        1.0 / _element_z("L", l, omega, qc, ql)
        + 1.0 / (_element_z("C", c2, omega, qc, ql) + z_load)
    )
    return _element_z("C", c1, omega, qc, ql) + z_m


def _t_efficiency(c1, l, c2, z_load, omega, qc, ql) -> float:
    """The fraction of the power into the rig side that reaches the load."""
    z_in = _t_z_in(c1, l, c2, z_load, omega, qc, ql)
    i1 = 1.0 / z_in
    v_m = 1.0 - i1 * _element_z("C", c1, omega, qc, ql)
    i2 = v_m / (_element_z("C", c2, omega, qc, ql) + z_load)
    return float(abs(i2) ** 2 * z_load.real / (abs(i1) ** 2 * z_in.real))


def _t_lossless_starts(fixed: dict, z_load: complex, r_t: float, omega: float):
    """The lossless T solutions with the one part in ``fixed`` held, as
    (c1, l, c2) triples with every part's reactance of the right sign
    (capacitors negative, the coil positive)."""
    r_l, x_l = z_load.real, z_load.imag
    cands = []
    if "c2" in fixed:
        # Series C1 and a shunt L across (C2 + load): the high-pass L with
        # its shunt at out, for the load as C2 leaves it.
        x2 = -1.0 / (omega * fixed["c2"])
        z_a = complex(r_l, x_l + x2)
        for c1, l in _lossless_starts(("C", "L"), "out", z_a, r_t, omega):
            cands.append((c1, l, fixed["c2"]))
    elif "c1" in fixed:
        # Looking into the tee midpoint the rig side must see r_t minus C1's
        # reactance, a COMPLEX target the shunt L and series C2 reach.
        y_m = 1.0 / complex(r_t, 1.0 / (omega * fixed["c1"]))
        g_t, b_t = y_m.real, y_m.imag
        disc = r_l / g_t - r_l * r_l
        if disc >= 0.0:
            for u in (math.sqrt(disc), -math.sqrt(disc)):
                x2 = u - x_l
                b_sh = b_t - (1.0 / complex(r_l, u)).imag
                if x2 < 0.0 and b_sh < 0.0:
                    cands.append(
                        (fixed["c1"], -1.0 / (omega * b_sh), -1.0 / (omega * x2))
                    )
    else:
        # The coil held: with u = X_load + X2 the condition Re Z_m = r_t is a
        # quartic in u, R (R^2 + u^2) = r_t (R^2 + (B u^2 - u + B R^2)^2),
        # B the coil's susceptance.
        b = -1.0 / (omega * fixed["l"])
        r2 = r_l * r_l
        # (B u^2 - u + B R^2)^2 expanded, highest power first.
        sq = np.polymul([b, -1.0, b * r2], [b, -1.0, b * r2])
        poly = r_t * np.polyadd(sq, [r2]) - np.array([0.0, 0.0, r_l, 0.0, r_l * r2])
        for u in np.roots(poly):
            if abs(u.imag) > 1e-9 * max(1.0, abs(u.real)):
                continue
            u = float(u.real)
            x2 = u - x_l
            if x2 >= 0.0:
                continue
            z_m = 1.0 / (1.0 / complex(r_l, u) + 1j * b)
            x1 = -z_m.imag
            if x1 < 0.0:
                cands.append((-1.0 / (omega * x1), fixed["l"], -1.0 / (omega * x2)))
    return cands


def design_t_match(
    z_load: complex,
    target: float,
    f_mhz: float,
    *,
    c1: float | None = None,
    l: float | None = None,
    c2: float | None = None,
    pin: str = DEFAULT_PIN,
    qc: float | None = None,
    ql: float | None = None,
    ranges: Ranges | None = None,
) -> TMatchDesign:
    """The T network (series C1 from the rig, shunt L at the tee midpoint,
    series C2 to the load) that presents ``target`` ohms when ``z_load`` hangs
    on its output, at ``f_mhz``, with the parts' finite Q included.

    A T has three parts for two conditions (R and X at the rig), so exactly
    one must be held: give one of ``c1`` / ``l`` / ``c2`` (SI units), or give
    none and the capacitor ``pin`` names ("c1", "c2", or "auto", the less
    lossy of the two) is held at ``ranges.c_max``. Where two tunings exist,
    the less lossy one is taken. A solution with a part outside ``ranges``
    is not one. Raises `NoMatch` when there is no solution."""
    from scipy.optimize import fsolve

    if pin not in PINS:
        raise ValueError(f"pin={pin!r} is not one of {PINS}")
    ranges = ranges or Ranges()
    given = {k: v for k, v in (("c1", c1), ("l", l), ("c2", c2)) if v is not None}
    if len(given) > 1:
        raise ValueError(
            "a T with two parts given has one left to tune for two conditions; "
            "give at most one of c1 / l / c2"
        )
    z_load, r_t = complex(z_load), float(target)
    omega = 2.0 * math.pi * f_mhz * 1e6
    if abs(z_load - r_t) <= 1e-9 * r_t:
        return TMatchDesign(
            0.0, 0.0, 0.0, f_mhz, z_load, given=tuple(given), bypass=True
        )
    if given:
        holds = [(given, None)]
    else:
        if ranges.c_max is None:
            raise ValueError(
                "a T with all three parts free holds a capacitor at its "
                "maximum, so it needs c_max"
            )
        pins = ("c1", "c2") if pin == "auto" else (pin,)
        holds = [({p: ranges.c_max}, p) for p in pins]

    found: list[TMatchDesign] = []
    out_of_range: list[str] = []
    reachable = False
    for fixed, pinned in holds:
        free = [p for p in T_PARTS if p not in fixed]
        for start in _t_lossless_starts(fixed, z_load, r_t, omega):
            reachable = True
            vals = dict(zip(T_PARTS, start, strict=True))

            def parts(x, fixed=fixed, free=free):
                v = dict(fixed)
                # Clamped so a wandering step cannot underflow a part to 0.
                v.update(
                    {
                        p: math.exp(min(max(xi, -60.0), 5.0))
                        for p, xi in zip(free, x, strict=True)
                    }
                )
                return v["c1"], v["l"], v["c2"]

            def residual(x, parts=parts):
                d = (_t_z_in(*parts(x), z_load, omega, qc, ql) - r_t) / r_t
                return [d.real, d.imag]

            x, _info, ok, _msg = fsolve(
                residual,
                np.log([vals[p] for p in free]),
                full_output=True,
                xtol=1e-13,
            )
            if ok != 1 or max(abs(v) for v in residual(x)) > 1e-9:
                continue
            c1_v, l_v, c2_v = parts(x)
            why = [
                f"{name} {reason}"
                for name, kind, value in (
                    ("C1", "C", c1_v), ("L", "L", l_v), ("C2", "C", c2_v)
                )
                if (reason := ranges.outside(kind, value))
            ]  # fmt: skip
            if why:
                out_of_range.append(" and ".join(why))
                continue
            eff = _t_efficiency(c1_v, l_v, c2_v, z_load, omega, qc, ql)
            found.append(
                TMatchDesign(
                    c1_v, l_v, c2_v, f_mhz, z_load,
                    given=tuple(given), pinned=pinned, efficiency=eff,
                )
            )  # fmt: skip
    if found:
        return max(found, key=lambda d: d.efficiency)
    held = (
        f"with {next(iter(given)).upper()} given"
        if given
        else f"with {'either capacitor' if pin == 'auto' else pin.upper()} at its maximum"
    )
    raise NoMatch(
        f"no T network {held} presents {r_t:g} ohm for a load of "
        f"{z_load.real:.4g} {'+' if z_load.imag >= 0 else '-'} "
        f"j{abs(z_load.imag):.4g} ohm at {f_mhz:g} MHz"
        + (
            " within its component ranges (" + "; ".join(out_of_range) + ")"
            if out_of_range
            else ""
        ),
        reachable=reachable,
    )


def t_bypass_body(rig: str, out: str, mid: str = "m"):
    """A T out of circuit: its two series arms at 0 H (wires) through the tee
    midpoint, and no shunt (an open). Declaring the midpoint here is what
    makes the flattened network carry it as a `PortVirtual`, so the tuned
    body has a node to hang its coil on."""
    return (TwoPort(a=rig, b=mid, l=0.0), TwoPort(a=mid, b=out, l=0.0))


@dataclass(frozen=True)
class TTuner:
    """The tuning MECHANISM of a T network (AK#1661): present ``target`` ohms
    at ``f_mhz`` (None: the design frequency). Any ONE of ``c1`` / ``l`` /
    ``c2`` (SI) may be given and the other two are tuned; with none given,
    the capacitor ``pin`` names is held at ``ranges.c_max``, as a real T
    autotuner holds one capacitor and searches the other two.

    Which capacitor to pin by default was measured, not assumed
    (``scratch/1661-t-tuner/pin_loss.py``): both, as `DEFAULT_PIN` records —
    the choice barely moves the loss but decides which loads can be matched
    at all.
    """

    target: float
    f_mhz: float | None = None
    c1: float | None = None
    l: float | None = None
    c2: float | None = None
    pin: str = DEFAULT_PIN
    qc: float | None = None
    ql: float | None = None
    ranges: Ranges = Ranges()
    on_no_match: str = "best"

    def __post_init__(self):
        if self.on_no_match not in ON_NO_MATCH:
            raise ValueError(
                f"on_no_match={self.on_no_match!r} is not one of {ON_NO_MATCH}"
            )
        if isinstance(self.target, complex) or not float(self.target) > 0.0:
            raise ValueError(
                f"tune_to={self.target!r}: a tuner tunes to a positive resistance "
                "in ohms"
            )
        if self.f_mhz is not None and not float(self.f_mhz) > 0.0:
            raise ValueError(f"tune_at_mhz={self.f_mhz!r} must be positive")
        if self.pin not in PINS:
            raise ValueError(f"pin={self.pin!r} is not one of {PINS}")
        given = [p for p in T_PARTS if getattr(self, p) is not None]
        if len(given) == 3:
            raise ValueError(
                "a T tuner with C1, L and C2 all given has nothing left to "
                "tune; drop tune_to for a fixed T"
            )
        if len(given) == 2 and self.on_no_match == "bypass":
            raise ValueError(
                f"a T tuner with {' and '.join(p.upper() for p in given)} given "
                "has one part for two conditions (R and X at the rig), so it "
                "can only tune for best effort; on_no_match='bypass' would "
                "never tune"
            )
        if not given and self.ranges.c_max is None:
            raise ValueError(
                "a T tuner with all three parts free holds a capacitor at its "
                "maximum, so it needs c_max_pF"
            )

    def body(self, rig: str, out: str, z_load: complex, f_mhz: float, mid: str):
        """``(branches, design)`` for this load: the real T, or the bypass
        when nothing matches."""
        given = tuple(p for p in T_PARTS if getattr(self, p) is not None)
        kw = dict(
            c1=self.c1, l=self.l, c2=self.c2, pin=self.pin,
            qc=self.qc, ql=self.ql, ranges=self.ranges,
        )  # fmt: skip
        design, why = None, None
        if len(given) == 2:
            # One part for two conditions: never exact by algebra, so the
            # search is the tuning (AK#1663).
            why = (
                f"with {' and '.join(p.upper() for p in given)} given, one part "
                "cannot set both R and X"
            )
            design = best_t_match(z_load, self.target, f_mhz, why=why, **kw)
        else:
            try:
                design = design_t_match(z_load, self.target, f_mhz, **kw)
            except NoMatch as exc:
                why = str(exc)
                if exc.reachable and self.on_no_match == "best":
                    design = best_t_match(z_load, self.target, f_mhz, why=why, **kw)
        if design is not None and (
            worse := _no_better_than_bypass(design, self.target)
        ):
            why, design = f"{why}, and {worse}", None
        if design is None:
            design = TMatchDesign(
                0.0, 0.0, 0.0, f_mhz, z_load, given=given,
                matched=False, bypass=True, no_match=why,
            )  # fmt: skip
        if design.bypass:
            return (t_bypass_body(rig, out, mid), design)
        return (
            (
                TwoPort(a=rig, b=mid, c=design.c1, qc=self.qc),
                Shunt(port=mid, l=design.l, ql=self.ql),
                TwoPort(a=mid, b=out, c=design.c2, qc=self.qc),
            ),
            design,
        )

    def describe(self) -> str:
        given = [p for p in T_PARTS if getattr(self, p) is not None]
        if given:
            return f"T network with {given[0].upper()} given"
        which = "either capacitor" if self.pin == "auto" else self.pin.upper()
        return f"T network with {which} at its maximum"


# --- best effort (AK#1663) --------------------------------------------------
#
# What an operator does with a box that cannot reach the target: tune the parts
# that move for the lowest SWR they give, and leave it there. It is used where
# the topology could match in principle (a lossless solution exists) but a
# part's range or the parts' loss rules the exact answer out, and where a T has
# two parts given and one left to tune. A topology with no solution at all is
# still bypassed: there is nothing for its parts to do.

ON_NO_MATCH = ("best", "bypass")
#: How far past a part's characteristic value (reactance = the target) the
#: search runs on a side its range leaves open, as a ratio each way.
_OPEN_SPAN = 1e4
#: The grid the search starts from, per free part: dense enough that the
#: local refinement starts inside the right basin on the loads we measured.
_GRID = {1: 801, 2: 81}
#: A best effort this close to the target is the exact match, reached by
#: search rather than algebra (a T with two parts given, say).
_EXACT_GAMMA = 1e-9


def _gamma(z, r_t):
    return np.abs((z - r_t) / (z + r_t))


def _swr(gamma: float) -> float:
    gamma = min(float(gamma), 1.0 - 1e-12)
    return (1.0 + gamma) / (1.0 - gamma)


def _log_box(kind: str, ranges: Ranges, omega: float, r_t: float):
    """The search interval for one part, in log(SI value): its range, and on
    a side the range leaves open, ``_OPEN_SPAN`` past the value whose
    reactance equals the target."""
    char = r_t / omega if kind == "L" else 1.0 / (omega * r_t)
    lo = ranges.l_min if kind == "L" else ranges.c_min
    hi = ranges.l_max if kind == "L" else ranges.c_max
    lo = char / _OPEN_SPAN if lo is None else lo
    hi = char * _OPEN_SPAN if hi is None else hi
    return math.log(lo), math.log(hi)


def _minimise_gamma(gamma_of, boxes, seeds=()):
    """The parts (SI values) minimising ``gamma_of(*values)`` over the log
    ``boxes``, and the |Γ| there. Deterministic: a fixed grid, then a
    bounded quasi-Newton refinement from its best point and from each seed
    (clipped into the box), keeping the lowest."""
    from scipy.optimize import minimize

    n = len(boxes)
    axes = [np.linspace(lo, hi, _GRID[n]) for lo, hi in boxes]
    mesh = np.meshgrid(*axes, indexing="ij")
    g = gamma_of(*(np.exp(m) for m in mesh))
    g = np.where(np.isfinite(g), g, np.inf)
    best = np.unravel_index(int(np.argmin(g)), g.shape)
    starts = [np.array([axes[i][best[i]] for i in range(n)])]
    for seed in seeds:
        x = np.log(np.asarray(seed, float))
        starts.append(np.clip(x, [b[0] for b in boxes], [b[1] for b in boxes]))

    def obj(x):
        v = gamma_of(*np.exp(x))
        v = float(v)
        return v * v if math.isfinite(v) else 1.0

    best_x, best_g = starts[0], math.sqrt(obj(starts[0]))
    for x0 in starts:
        res = minimize(
            obj,
            x0,
            method="L-BFGS-B",
            bounds=boxes,
            options={"ftol": 1e-15, "gtol": 1e-12, "maxiter": 500},
        )
        gx = math.sqrt(obj(res.x))
        if gx < best_g - 1e-15:
            best_x, best_g = res.x, gx
    return np.exp(best_x), best_g


def _no_better_than_bypass(design, target: float) -> str | None:
    """Why a best effort is worse than leaving the box out of circuit, or
    None when it helps. A box whose parts are held can make a load WORSE
    (a pinned capacitor and a short-ranged coil measured 763:1 on a load
    that is 2.9:1 bypassed), and a real tuner's bypass relay is always there,
    so a best effort only goes in circuit when it beats the bypass."""
    if design.best_swr is None:
        return None
    bypass_swr = _swr(float(_gamma(design.z_load, float(target))))
    if design.best_swr < bypass_swr:
        return None
    return (
        f"the best its parts reach, SWR {design.best_swr:.2f}:1, is no better "
        f"than the load's own {bypass_swr:.2f}:1"
    )


def _best_effort_note(design) -> str:
    return (
        f", best effort: SWR {design.best_swr:.2f}:1"
        if design.best_swr is not None
        else ""
    )


def best_l_match(
    z_load,
    target,
    f_mhz,
    mode="low",
    *,
    shunt_at="out",
    qc=None,
    ql=None,
    ranges=None,
    why="",
) -> LMatchDesign:
    """The L network of ``mode``'s kinds, parts inside ``ranges``, with the
    lowest reflection at ``target`` for ``z_load`` (AK#1663). ``shunt_at``
    "auto" searches both sides and keeps the better. ``why`` is the exact
    solver's reason, carried as the design's ``no_match``."""
    z_load, r_t = complex(z_load), float(target)
    omega = 2.0 * math.pi * f_mhz * 1e6
    kinds = _KINDS[mode]
    ranges = ranges or Ranges()
    boxes = [_log_box(k, ranges, omega, r_t) for k in kinds]
    best = None
    for side in ("out", "rig") if shunt_at == "auto" else (shunt_at,):

        def gamma_of(series, shunt, side=side):
            return _gamma(_z_in(kinds, side, series, shunt, z_load, omega, qc, ql), r_t)

        seeds = _lossless_starts(kinds, side, z_load, r_t, omega)
        (series, shunt), g = _minimise_gamma(gamma_of, boxes, seeds)
        if best is None or g < best[0]:
            best = (g, side, float(series), float(shunt))
    g, side, series, shunt = best
    if g < _EXACT_GAMMA:
        return LMatchDesign(mode, side, series, shunt, f_mhz, z_load)
    return LMatchDesign(
        mode, side, series, shunt, f_mhz, z_load,
        matched=False, no_match=why or None, best_swr=_swr(g),
    )  # fmt: skip


def best_t_match(
    z_load,
    target,
    f_mhz,
    *,
    c1=None,
    l=None,
    c2=None,
    pin=DEFAULT_PIN,
    qc=None,
    ql=None,
    ranges=None,
    why="",
) -> TMatchDesign:
    """The T with the given parts held (SI; with none given, a capacitor at
    ``ranges.c_max`` as ``pin`` says), the rest inside ``ranges``, with the
    lowest reflection at ``target`` for ``z_load`` (AK#1663). Two parts given
    leave one to tune; ``pin`` "auto" tries both capacitors."""
    z_load, r_t = complex(z_load), float(target)
    omega = 2.0 * math.pi * f_mhz * 1e6
    ranges = ranges or Ranges()
    given = {k: v for k, v in (("c1", c1), ("l", l), ("c2", c2)) if v is not None}
    if given:
        holds = [(given, None)]
    else:
        pins = ("c1", "c2") if pin == "auto" else (pin,)
        holds = [({p: ranges.c_max}, p) for p in pins]
    best = None
    for fixed, pinned in holds:
        free = [p for p in T_PARTS if p not in fixed]
        boxes = [_log_box("L" if p == "l" else "C", ranges, omega, r_t) for p in free]

        def gamma_of(*vals, fixed=fixed, free=free):
            v = dict(fixed)
            v.update(zip(free, vals, strict=True))
            return _gamma(_t_z_in(v["c1"], v["l"], v["c2"], z_load, omega, qc, ql), r_t)

        seeds = (
            [
                [t[T_PARTS.index(p)] for p in free]
                for t in _t_lossless_starts(fixed, z_load, r_t, omega)
            ]
            if len(fixed) == 1
            else []
        )
        vals, g = _minimise_gamma(gamma_of, boxes, seeds)
        if best is None or g < best[0]:
            parts = dict(fixed)
            parts.update(zip(free, (float(x) for x in vals), strict=True))
            best = (g, parts, pinned)
    g, parts, pinned = best
    exact = g < _EXACT_GAMMA
    return TMatchDesign(
        parts["c1"], parts["l"], parts["c2"], f_mhz, z_load,
        given=tuple(given), pinned=pinned,
        efficiency=_t_efficiency(
            parts["c1"], parts["l"], parts["c2"], z_load, omega, qc, ql
        ),
        matched=exact,
        no_match=None if exact else (why or None),
        best_swr=None if exact else _swr(g),
    )  # fmt: skip


# --- finding the tuner in a network -----------------------------------------


@dataclass(frozen=True)
class _Tuner:
    path: str
    mechanism: object
    indices: tuple[int, ...]
    rig: str
    out: str
    #: Nodes internal to the box, passed on to the mechanism's `body`.
    inner: tuple[str, ...] = ()

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
        # The bypass is a chain of series arms, rig -> ... -> out; the nodes
        # between them are the box's own (a T's tee midpoint).
        chain = [net.branches[i] for i in idx]
        inner = tuple(br.b for br in chain[:-1])
        found.append(_Tuner(path, mechanism, idx, chain[0].a, chain[-1].b, inner))
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
        self._wl_for = wl_for
        self._wavelength = float(wl_for(self.f_mhz))
        self._structural = NetworkReducer(net, port_to_idx, n_total_ports)
        self._last = self._structural
        self._tuned: NetworkReducer | None = None
        self._body: tuple = ()
        self.design: LMatchDesign | TMatchDesign | None = None
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

    def tune(self, y_real=None) -> LMatchDesign | TMatchDesign:
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
            t.rig, t.out, z_load, C_LIGHT / self._wavelength / 1e6, *t.inner
        )
        design = replace(design, f_mhz=self.f_mhz)
        if design.no_match:
            then = (
                f"tuned for best effort, SWR {design.best_swr:.2f}:1"
                if design.best_swr is not None
                else "bypassed"
            )
            warnings.warn(
                f"tuner {t.name}: {design.no_match}; {then}",
                TunerAdvisory,
                stacklevel=2,
            )
        self.design, self._body = design, body
        return design

    def tunes_at(self, f_mhz) -> bool:
        """Whether a solve at ``f_mhz`` is at the tune frequency, by the same
        rule `_reducer_for` uses to reuse the tuning: there the port
        impedance IS the target, whatever the rest of the design does."""
        return math.isclose(
            float(self._wl_for(float(f_mhz))), self._wavelength, rel_tol=1e-12
        )

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
        rows = [
            {
                "label": label,
                "value": round(value * (1e6 if kind == "L" else 1e12), 6),
                "unit": "µH" if kind == "L" else "pF",
                "group": group,
            }
            for label, kind, value in d.parts
        ]
        if d.best_swr is not None:
            rows.append(
                {
                    "label": "SWR reached",
                    "value": round(d.best_swr, 3),
                    "unit": ":1",
                    "group": group,
                }
            )
        rows.append(
            {"label": "tuned", "value": d.summary, "unit": None, "group": group}
        )
        return rows

    def tuner_advisories(self) -> list[dict]:
        d = self.design
        if d is None or d.matched:
            return []
        t = self._tuner.mechanism
        z = d.z_load
        if d.best_swr is not None:
            return [
                {
                    "category": "tuner",
                    "text": (
                        f"Tuner {self._tuner.name} cannot present {t.target:g} Ω "
                        f"for the {z.real:.4g} {'+' if z.imag >= 0 else '−'} "
                        f"j{abs(z.imag):.4g} Ω it sees at {d.f_mhz:g} MHz "
                        f"({d.no_match}), so it is tuned as close as its parts "
                        f"allow: SWR {d.best_swr:.2f}:1, and the readout shows "
                        "that mismatch."
                    ),
                }
            ]
        return [
            {
                "category": "tuner",
                "text": (
                    f"Tuner {self._tuner.name} found no {t.describe()} that "
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
    `AutoMatchReducer` when the network holds a self-tuning tuner."""
    tuners = find_tuners(net)
    if not tuners:
        return NetworkReducer(net, port_to_idx, n_total_ports)
    if len(tuners) > 1:
        raise NotImplementedError(
            "a network with more than one self-tuning tuner is not supported: "
            "each one's load would include the other's tuning"
        )
    if y_at is None:
        raise NotImplementedError(
            "this engine cannot tune a tuner: it has no port admittance to tune it from"
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


def tuner_holding_match(eng) -> dict | None:
    """``{"name", "f_mhz"}`` of the self-tuning tuner when the engine's
    solve frequency is its tune frequency, else None (AK#1664).

    There the driven port reads the tuner's target on every solve, so a
    match objective (SWR, resonance, match to Z0) is met whatever the knobs
    do: the optimizer and the tracker refuse on this rather than descend a
    flat surface. Off the tune frequency the tuner holds its parts and the
    match responds again."""
    red = getattr(eng, "_reducer", None)
    f = getattr(getattr(eng, "builder", None), "freq", None)
    if not isinstance(red, AutoMatchReducer) or not f or not red.tunes_at(f):
        return None
    return {"name": red._tuner.name, "f_mhz": red.f_mhz}


def tuner_advisories(eng) -> list[dict]:
    """The engine's "no match, bypassed" advisory, [] otherwise."""
    red = getattr(eng, "_reducer", None)
    return red.tuner_advisories() if isinstance(red, AutoMatchReducer) else []
