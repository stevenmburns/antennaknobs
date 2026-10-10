"""Where the power goes, band by band, for a station whose tuner retunes on
every band — and the knob setting that makes the worst band least bad.

A station design with a self-tuning tuner (`auto_match`; e.g.
`wire.doublet_remote_tuner`, whose manual tuner the command puts in its auto
mode through the design's ``band_loss_params``) matches the rig on every
band it can reach, so SWR at the rig says nothing about which line length or
balun is better: the answer is in the LOSSES — the feedline (its matched
loss plus the extra the SWR on it costs), the balun, the tuner's coil — and
what is left reaches the antenna. Those are the power budget's rows (issue #299): every network
branch's dissipation from the same excited-state solve that normalises the
gain (`NetworkReducer.excited_state`), plus the engine's ohmic wire loss
row when the antenna wire is lossy, and "antenna" is the remainder
``p_in − Σ losses``, the power the antenna port accepts (radiated, plus any
ground loss inside the MoM solve). Nothing here is a new calculation of
loss; it reads those rows at each band.

Every share is of the power AVAILABLE from a 50 Ω rig (``z0``), not of the
power the station accepts: the solve drives the rig port from an ideal
voltage source, so ``p_in`` is whatever the station draws, and a mismatched
band (a tuner whose parts cannot reach the match) would otherwise score as
well as a matched one. A share of the available power is the accepted share
times 1 − |Γ|², Γ the reflection at the rig against ``z0``, and the reflected
power is its own column ("mismatch"), so the columns of a row add to 100 %.

Each band is its own engine at its own ``freq``, so the tuner retunes there,
as an auto-tuner does when you key it on a new band. That is also why the
multi-band optimizer (`web.optimize_bands`) cannot serve this question: it
solves every band on ONE engine whose tuner tunes once and holds, and its
objectives are impedance objectives (SWR, resonance, match), which a
retuning tuner meets at every band whatever the knobs do (AK#1664). So the
search here is an outer one (`search`): a grid over one knob, each point
every band, then a bounded refinement around the best grid point, the
objective the worst band's fraction reaching the antenna (a max-min).

The search is cheap when the knob is a network knob (a line length, a
balun ratio): the antenna does not move, so each band's port admittance Y
is solved once and every later point reuses it, and only the network
reduction runs again. A solved admittance is reused only under the same
`antenna_key`: everything the engine builds the antenna's MoM problem from
(the meshed wires, the wire material, the antenna's own feed ports and where
they sit, any legacy TLs), read off the builder after each engine is built,
so a knob that moves a feed along a wire (``dipoles.ocf_dipole``'s
``feed_frac``) gets a fresh solve at every value. An engine whose wire is
lossy takes the slow path (its ohmic loss needs the excited currents), and
reuses nothing.

Command line: ``antennaknobs band-loss`` (``cli.py``).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np


_TRUE = ("true", "1", "yes", "on")
_FALSE = ("false", "0", "no", "off")


def parse_knob_value(default, text: str):
    """``text`` (a command line's ``KNOB=VALUE``) as a value of the knob whose
    default is ``default``: a string stays a string, a bool reads true/false
    (``bool("False")`` is True, so never by the type's constructor), and a
    number is its type's."""
    if isinstance(default, str):
        return text
    if isinstance(default, bool):
        low = text.strip().lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        raise ValueError(f"{text!r} is not true or false")
    return type(default)(text)


def group_of(label: str) -> str:
    """The budget row's owner, for a table column: an instance's rows carry
    its path before a colon ("tuner: TwoPort rig→tuner" → "tuner"),
    a bare branch its class ("BalancedLine liL,liR→…" → "BalancedLine"), and
    the engine's ohmic row ("wire loss (I²R)") is "wire loss"."""
    if label.startswith("wire loss"):
        return "wire loss"
    head, sep, _ = label.partition(":")
    return head.strip() if sep else label.split()[0]


@dataclass(frozen=True)
class BandLoss:
    """One band: the power the station draws from the ideal rig source
    (``p_in``), the losses grouped by owner (watts, in branch order), what
    the self-tuning tuner tuned to there (None without one), and the
    impedance at the rig, against ``z0``, the rig's own impedance."""

    f_mhz: float
    p_in: float
    losses: tuple[tuple[str, float], ...]
    tuning: object | None = None
    z_rig: complex = complex(math.nan, math.nan)
    z0: float = 50.0

    @property
    def gamma2(self) -> float:
        """|Γ|² at the rig against ``z0``: the share of the available power
        reflected (0 when the tuner matches; 0 when z_rig is unknown)."""
        z = self.z_rig
        if not np.isfinite(z):
            return 0.0
        return float(abs((z - self.z0) / (z + self.z0)) ** 2)

    @property
    def swr(self) -> float:
        g = math.sqrt(self.gamma2)
        return math.inf if g >= 1.0 else (1.0 + g) / (1.0 - g)

    @property
    def antenna(self) -> float:
        """Watts reaching the antenna of the ``p_in`` drawn: less every loss."""
        return self.p_in - sum(w for _, w in self.losses)

    @property
    def antenna_fraction(self) -> float:
        """The share of the rig's AVAILABLE power reaching the antenna: the
        accepted share times 1 − |Γ|²."""
        if not self.p_in > 0:
            return math.nan
        return (1.0 - self.gamma2) * self.antenna / self.p_in

    def fraction(self, group: str) -> float:
        """A loss group's share of the rig's available power."""
        w = sum(w for g, w in self.losses if g == group)
        return (1.0 - self.gamma2) * w / self.p_in


def _grouped(rows) -> tuple[tuple[str, float], ...]:
    out: dict[str, float] = {}
    for label, w in rows:
        # The excited state reports a lossless branch as float noise (±1e-18 W).
        out[group_of(label)] = out.get(group_of(label), 0.0) + max(0.0, float(w))
    return tuple(out.items())


def _fast(eng) -> bool:
    """Whether the budget can be read off ``eng``'s network path directly
    (momwire): its reducer, its port admittance, its wavelength, and NO ohmic
    wire loss — that row needs the excited currents, which only the engine's
    own excited solve computes (`cli._solve_for_budget`)."""
    return (
        getattr(eng, "_network", None) is not None
        and getattr(eng, "_reducer", None) is not None
        and callable(getattr(eng, "_wavelength_for", None))
        and not getattr(eng, "_loading_kwargs", None)
    )


def station_budget(eng, y=None):
    """``(p_in, rows, z_rig, Y)`` at the engine's own ``freq``: the power
    budget's rows (``(label, watts)``, issue #299), the driven port's
    impedance, and the port admittance it came from. ``y`` reuses an
    admittance already solved for this antenna at this frequency. Otherwise
    (another engine, or a lossy wire) it runs the solve that stamps the
    budget (`cli._solve_for_budget`), wire-loss row included, and Y is None."""
    if _fast(eng):
        wl = eng._wavelength_for(eng.builder.freq)
        Y = eng._compute_y_matrix(wl) if y is None else y
        # Tunes a self-tuning tuner from this Y, as `impedance()` does.
        z = eng._reducer.driven_impedance(Y, wl)
        _v, _eff, p_in, rows = eng._reducer.excited_state(Y, wl)
        return float(p_in), list(rows), complex(np.atleast_1d(z)[0]), Y
    from .cli import _solve_for_budget

    z = eng.impedance()
    _solve_for_budget(eng)
    rows = getattr(eng, "_excited_power_budget", None) or []
    return float(eng._excited_p_in), list(rows), complex(np.atleast_1d(z)[0]), None


def engine_band_loss(eng, y=None, z0: float = 50.0) -> tuple[BandLoss, object]:
    """One engine's band: its `BandLoss` and the Y it used (None when it
    solved without one to reuse)."""
    from .auto_match import tuner_design

    p_in, rows, z, Y = station_budget(eng, y)
    f = float(eng.builder.freq)
    return BandLoss(f, p_in, _grouped(rows), tuner_design(eng), z, z0), Y


def antenna_key(builder) -> str:
    """Everything the engine builds the antenna's MoM problem from, as one
    string: two settings with the same key have the same port admittance at
    a frequency. The meshed wires (counts resolved), the wire material, the
    antenna's own feed ports (every non-virtual port, with where it sits on
    its wire), and any legacy TLs. The ground and the engine are the
    factory's, fixed for a run."""
    from .network import PortVirtual

    net = (
        builder.build_network()
        if callable(getattr(builder, "build_network", None))
        else None
    )
    ports = (
        sorted(
            (name, repr(p))
            for name, p in net.ports.items()
            if not isinstance(p, PortVirtual)
        )
        if net is not None
        else None
    )
    tls = getattr(builder, "build_tls", None)
    return repr(
        (
            builder.build_wires(),
            builder.build_wire_material(),
            ports,
            list(tls()) if callable(tls) else None,
        )
    )


def band_losses(
    builder,
    factory: Callable,
    freqs: Sequence[float],
    y_cache: dict | None = None,
    z0: float = 50.0,
) -> list[BandLoss]:
    """Every band of ``freqs``: ``builder.freq`` set to it, a fresh engine
    (so a self-tuning tuner retunes there), its budget. ``y_cache`` holds
    solved port admittances keyed by (`antenna_key`, frequency), filled as
    bands solve, and reused only under the same key."""
    out = []
    for f in freqs:
        builder.freq = float(f)
        eng = factory(builder)
        key = None if y_cache is None else (antenna_key(builder), float(f))
        y = None if key is None else y_cache.get(key)
        band, Y = engine_band_loss(eng, y, z0)
        if key is not None and Y is not None:
            if y is not None:
                y_cache["hits"] = y_cache.get("hits", 0) + 1
            y_cache[key] = Y
        out.append(band)
        del eng
    return out


def worst(bands: Sequence[BandLoss]) -> BandLoss:
    """The band where the least of the available power reaches the antenna."""
    return min(bands, key=lambda b: b.antenna_fraction)


@dataclass(frozen=True)
class SearchResult:
    knob: str
    best: float
    bands: tuple[BandLoss, ...]
    #: Every point tried, in order: (knob value, worst band's antenna fraction).
    tried: tuple[tuple[float, float], ...]
    #: How many band solves reused an admittance (same `antenna_key`).
    reused: int

    @property
    def reused_y(self) -> bool:
        return self.reused > 0

    @property
    def worst(self) -> BandLoss:
        return worst(self.bands)


def search(
    builder,
    factory: Callable,
    freqs: Sequence[float],
    knob: str,
    lo: float,
    hi: float,
    *,
    step: float,
    z0: float = 50.0,
) -> SearchResult:
    """The ``knob`` value in [lo, hi] that maximises the worst band's share
    of the available power reaching the antenna: a grid every ``step``, then
    a bounded scalar refinement within one step either side of the best grid
    point (the worst-band curve is ragged, a max-min across bands, so the
    grid finds the basin and the refinement its floor). Leaves ``builder``
    at the best value."""
    from scipy.optimize import minimize_scalar

    if not (hi > lo and step > 0):
        raise ValueError(f"search {knob}: need lo < hi and step > 0")
    cache: dict = {}
    tried: list[tuple[float, float]] = []
    memo: dict[float, list[BandLoss]] = {}

    def evaluate(x: float) -> float:
        x = float(x)
        setattr(builder, knob, x)
        bands = band_losses(builder, factory, freqs, cache, z0)
        memo[x] = bands
        v = worst(bands).antenna_fraction
        tried.append((x, v))
        return v

    grid = np.arange(lo, hi + 0.5 * step, step)
    scores = [evaluate(x) for x in grid]
    i = int(np.argmax(scores))
    a, b = max(lo, grid[i] - step), min(hi, grid[i] + step)
    res = minimize_scalar(
        lambda x: -evaluate(x),
        bounds=(a, b),
        method="bounded",
        options={"xatol": step * 1e-3},
    )
    best = float(res.x) if -res.fun > scores[i] else float(grid[i])
    setattr(builder, knob, best)
    return SearchResult(
        knob, best, tuple(memo[best]), tuple(tried), int(cache.get("hits", 0))
    )


def out_of_reach(bands: Sequence[BandLoss], xs=None, x_name: str = "MHz") -> list[str]:
    """One line per band whose tuner did not match: a part out of its range
    (tuned for best effort) or no match at all (bypassed), with why."""
    xs = [b.f_mhz for b in bands] if xs is None else list(xs)
    lines = []
    for x, b in zip(xs, bands, strict=True):
        d = b.tuning
        if d is None or d.matched:
            continue
        what = (
            f"tuned for best effort, SWR {b.swr:.2f}:1 at the rig"
            if not d.bypass
            else f"bypassed, SWR {b.swr:.2f}:1 at the rig"
        )
        lines.append(
            f"!! {x_name} {x:g}: the tuner cannot match ({d.no_match}); {what}"
        )
    return lines


def format_table(
    bands: Sequence[BandLoss], xs: Sequence[float] | None = None, x_name: str = "MHz"
) -> list[str]:
    """Per band: the load the tuner saw and its parts (when it has one), the
    SWR at the rig, then each share of the rig's AVAILABLE power — reflected
    at the rig ("mismatch"), each loss group's, and the antenna's — which add
    to 100 %, and a line per band the tuner could not match. ``xs`` /
    ``x_name`` label the rows with a swept knob instead of the band's
    frequency."""
    groups: list[str] = []
    for b in bands:
        for g, _ in b.losses:
            if g not in groups:
                groups.append(g)
    xs = [b.f_mhz for b in bands] if xs is None else list(xs)
    head = f"{x_name:>8} {'load at tuner (Ω)':>22}  {'parts':<44} {'SWR':>6}"
    head += f" {'mismatch':>9}" + "".join(f" {g[:13]:>13}" for g in groups)
    head += f" {'antenna':>8}"
    lines = [head]
    for x, b in zip(xs, bands, strict=True):
        d = b.tuning
        if d is None:
            load, parts = "-", "-"
        else:
            z = d.z_load
            load = f"{z.real:.1f} {'+' if z.imag >= 0 else '-'} j{abs(z.imag):.1f}"
            parts = ", ".join(
                f"{n} {v * 1e6:.3g} µH" if k == "L" else f"{n} {v * 1e12:.4g} pF"
                for n, k, v in d.parts
            )
            side = getattr(d, "shunt_at", None)
            if side:
                parts += f" (C at {side})"
            if d.best_swr is not None:
                parts += " best effort"
            elif d.bypass:
                parts += " bypassed"
        row = f"{x:>8.4g} {load:>22}  {parts:<44} {b.swr:>6.2f}"
        row += f" {100 * b.gamma2:>8.2f}%"
        row += "".join(f" {100 * b.fraction(g):>12.2f}%" for g in groups)
        row += f" {100 * b.antenna_fraction:>7.2f}%"
        lines.append(row)
    lines += out_of_reach(bands, xs, x_name)
    i = min(range(len(bands)), key=lambda k: bands[k].antenna_fraction)
    lines.append(
        f"least reaches the antenna at {x_name} {xs[i]:g}: "
        f"{100 * bands[i].antenna_fraction:.2f}% of the rig's available power"
    )
    return lines
