"""Optimise one design across several frequencies at once (AK#1901).

`optimize.optimize` measures at ONE frequency. A multiband antenna is tuned
against a LIST of bands, and its knobs are rarely independent per band: on
Dan's 40/80/160 m vertical plus a capacitively coupled inverted L the height
mostly sets 40 m, but it moves the other two as well. So each evaluation here
is ONE rebuild of the design solved at EVERY band's frequency, and the
objective is read off all of them together.

**One build per evaluation, one mesh across the bands.** The injected
``sweep_fn(req, freqs)`` builds the design once and solves it at each
frequency (momwire: the frequency sweep's own ``impedance_sweep``, the
"one build solved across the band" path). The geometry is built at the
request's own measurement frequency, the same for every band and every eval,
so a band's residual never mixes discretisations and a band's own ``freq``
param (the multiband designs' per-band sizing anchor) never moves when another
band is evaluated -- the band list names solve frequencies, not knob values.

Three forms (``mode``):

- **MINIMAX** -- the default, with each band's default objective ``swr``.
  Minimise ``J = (1 - w) * worst + w * mean`` of the bands' values (SWR,
  or ohms for ``resonance`` / ``match_z0`` bands): the worst band leads, as the
  multi-feed minimax (#785) scores the worst feed, and ``w`` (``mean_weight``,
  default `DEFAULT_MEAN_WEIGHT`) keeps the easy bands from drifting up to the
  hardest one's value. J, its worst term and its mean term are all reported.
  Solved as the smooth epigraph problem (minimise ``(1 - w) t + w mean`` with
  every band's value ``<= t``) by SLSQP on finite-difference gradients inside
  a moving trust region, started from the better of the knobs' values and a
  bounded least-squares fit of every band's reactance to zero (the resonance
  root as an accelerator for the start).
  It is a LOCAL search from the knobs' current values, like the single-band
  optimizer. Exact resonance or an exact match
  on every band generally has no solution with the knobs given (R on a band is
  rarely under the knobs' control, a root may sit outside the box), so this,
  not a root, is what a band list asks for unless it says otherwise.
- **ROOT** -- opt-in, when every band is a root (``resonance``: X = 0, one
  equation; ``match_z0``: R = Z0 and X = 0, two) and the equations number
  exactly the knobs. Newton on the stacked residual, `optimize._newton_root`
  (the two-knob tuner's Newton, n-dimensional). It reports honestly whether a
  root was found (``root_status``: "root", "no root in the box", "singular",
  "parallel resonance", "out of evals"); a near miss is never presented as a
  root, and there is no fallback to another form -- a gap is a gap, as for a
  held sweep (`antennaknobs.hold`).
- **SEQUENTIAL** -- opt-in block coordinate descent with an explicit knob ->
  band assignment (each band's ``knobs``): tune band i with its own knobs,
  the others held, for every band in turn, in passes. This is how
  ``scripts/tune_hexbeam_5band_coupled.py`` tuned the stacked hexbeam and how
  Dan proposed tuning his antenna. It converges when each knob mostly drives
  its own band, and not otherwise.

Per band: its frequency, its objective, its Z0 (the request's when it names
none) and WHICH FEED it is read at -- a multi-feed design (hexbeam_5band
without its TL jumpers) drives one feed per band. Default feed 0. Bands
compare in one unit, so ``swr`` (a ratio) is not mixed with ``resonance`` /
``match_z0`` (ohms) in one run.

Framework-free like `optimize`: the ``/optimize`` endpoint passes the slot's
engine as ``sweep_fn``; the CLI passes a builder + engine factory.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.optimize import least_squares, minimize

from .optimize import (
    _ROOT_FTOL,
    DegenerateObjective,
    _bracket_brent,
    _fd_jacobian,
    _fd_step,
    _get_knob,
    _newton_root,
    _swr,
    _with_knob,
)

BAND_OBJECTIVES = ("resonance", "match_z0", "swr")
MODES = ("minimax", "root", "sequential")

#: A band's objective when it names none: the SWR the minimax form minimises.
DEFAULT_OBJECTIVE = "swr"

#: The spellings a band's objective may take (the CLI's short forms).
_OBJECTIVE_ALIASES = {
    "resonance": "resonance",
    "res": "resonance",
    "x0": "resonance",
    "match_z0": "match_z0",
    "match": "match_z0",
    "z0": "match_z0",
    "swr": "swr",
}

#: Most bands one request may carry. Each eval solves every band, so the band
#: count multiplies a run's cost exactly as the eval budget does.
MAX_BANDS = 8

#: A residual the engine could not read (an open-circuited sample comes back
#: NaN) scores as this, so a line search steps away from it instead of NaN
#: poisoning every comparison.
_UNREADABLE = 1e6

#: The minimax form's default tradeoff ``w`` in ``J = (1 - w) * worst + w *
#: mean`` of the bands' values. Plain max (w = 0) is flat in every band but
#: the worst, so the easy bands may be made as bad as the hardest one at no
#: cost, which is what Steve asked the sum term to prevent (AK#1901). A small
#: w does not prevent it either: on UR0GT's three-band vertical, w = 0.2
#: still chose SWR 1.86 / 1.86 / 1.86 (J = 1.86) over 1.93 / 1.93 / 1.34
#: (J = 1.89), dragging 40 m from 1.16 to 1.86; at w = 0.5 the order flips
#: and the run keeps 40 m at 1.34 for 0.07 on the worst band. Measured in
#: scratch/1901-multiband/probe_ur0gt.py.
DEFAULT_MEAN_WEIGHT = 0.5

#: Newton's step-size stop on the unit cube. `optimize._ROOT_XTOL` (1e-4 knob
#: units) is the single-band path's and stays there; on the five-band fan a
#: length_factor step of 1e-4 moves X by ~3 ohm, so that stop called a
#: converging Newton "no-crossing" at |F| = 0.09 ohm. The stall detector,
#: not this, is what ends a run that cannot reach a root.
_NEWTON_XTOL_U = 1e-9

#: Condition number (of the Jacobian on the unit cube) past which the start is
#: called singular.
_COND_MAX = 1e10

#: The minimax form's finite-difference step on the unit cube (a millionth of
#: each knob's range): far above a MoM solve's round-off, far below any
#: curvature the bands' values have.
_FD_U = 1e-6


class _OutOfEvals(Exception):
    """The eval budget is spent mid-search (SLSQP has no budget of its own)."""


class _OutOfTime(Exception):
    """The run's wall-time budget is spent (``time_budget_s``): every form
    stops at its next fresh solve and answers with the best point solved."""


#: A worst-band SWR past this at the answer is no match at all: the run says
#: so instead of presenting the optimum of a design nowhere near one (AK#1909:
#: a capacitor bounded in farads where the knob is in pF opened the circuit,
#: and the run "improved" SWR 2.3e6 to 2.2e4).
FAR_FROM_MATCH_SWR = 100.0

#: A knob within this fraction of its range from a bound at the answer is
#: reported as pinned there: the optimum may lie outside the range.
_AT_BOUND_U = 1e-3


class BandsRefused(ValueError):
    """A band list this module cannot serve, refused by name before (or at)
    the first solve: the request's shape, not the design's physics."""


@dataclass(frozen=True)
class Band:
    """One band of a multi-frequency objective."""

    freq_mhz: float
    objective: str = "swr"
    feed: int = 0
    z0: float | None = None
    knobs: tuple[str, ...] = field(default=())

    @property
    def n_equations(self) -> int:
        return {"resonance": 1, "match_z0": 2}.get(self.objective, 0)

    @property
    def unit(self) -> str:
        return "swr" if self.objective == "swr" else "ohm"

    def label(self, i: int) -> str:
        return f"band {i} ({self.freq_mhz:g} MHz)"


def _positive(name: str, raw) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise BandsRefused(f"{name} must be a number (got {raw!r})") from None
    if not math.isfinite(v) or v <= 0:
        raise BandsRefused(f"{name} must be a positive, finite number (got {raw!r})")
    return v


def _band_from_dict(i: int, d) -> Band:
    if not isinstance(d, dict):
        raise BandsRefused(f"band {i}: expected an object, got {d!r}")
    unknown = set(d) - {"freq", "freq_mhz", "objective", "feed", "z0", "knobs"}
    if unknown:
        raise BandsRefused(f"band {i}: unknown field(s) {', '.join(sorted(unknown))}")
    raw_f = d.get("freq_mhz", d.get("freq"))
    if raw_f is None:
        raise BandsRefused(f"band {i}: no frequency (give 'freq' in MHz)")
    f = _positive(f"band {i}'s frequency", raw_f)
    obj_raw = str(d.get("objective", DEFAULT_OBJECTIVE)).strip().lower()
    obj = _OBJECTIVE_ALIASES.get(obj_raw)
    if obj is None:
        raise BandsRefused(
            f"band {i}: unknown objective {obj_raw!r} (resonance, match_z0 or swr)"
        )
    feed_raw = d.get("feed", 0)
    try:
        feed = int(feed_raw)
    except (TypeError, ValueError):
        raise BandsRefused(f"band {i}: feed must be an integer (got {feed_raw!r})")
    if feed < 0 or feed != float(feed_raw):
        raise BandsRefused(f"band {i}: feed must be an index >= 0 (got {feed_raw!r})")
    z0 = d.get("z0")
    z0 = None if z0 is None else _positive(f"band {i}'s z0", z0)
    knobs = d.get("knobs") or ()
    if isinstance(knobs, str):
        knobs = [k for k in knobs.replace("+", " ").split() if k]
    if not all(isinstance(k, str) and k for k in knobs):
        raise BandsRefused(f"band {i}: knobs must be knob names (got {knobs!r})")
    return Band(f, obj, feed, z0, tuple(knobs))


def parse_bands(spec) -> list[Band]:
    """A band list from the request's JSON (a list of objects) or the CLI's
    string. Refused by name on any malformed band.

    The CLI string is comma-separated bands, each ``FREQ[:OBJECTIVE][:key=val
    ...]`` with keys ``feed``, ``z0`` and ``knobs`` (``+``-joined names), e.g.
    ``24.97:res:knobs=bands.0.length,28.57:res:knobs=bands.1.length``. The
    objective defaults to ``swr``. A string starting with ``[`` is read as the
    JSON form instead."""
    if isinstance(spec, str):
        text = spec.strip()
        if text.startswith("["):
            try:
                spec = json.loads(text)
            except ValueError as e:
                raise BandsRefused(f"--bands JSON: {e}") from None
        else:
            items = []
            for i, chunk in enumerate(c for c in text.split(",") if c.strip()):
                fields = [x.strip() for x in chunk.split(":")]
                d: dict = {"freq": fields[0]}
                for fld in fields[1:]:
                    if "=" in fld:
                        k, v = (s.strip() for s in fld.split("=", 1))
                        d[k] = v
                    elif "objective" not in d:
                        d["objective"] = fld
                    else:
                        raise BandsRefused(f"band {i}: unexpected field {fld!r}")
                items.append(d)
            spec = items
    if not isinstance(spec, (list, tuple)) or not spec:
        raise BandsRefused("bands must be a non-empty list")
    if len(spec) > MAX_BANDS:
        raise BandsRefused(f"at most {MAX_BANDS} bands per run (got {len(spec)})")
    bands = [_band_from_dict(i, d) for i, d in enumerate(spec)]
    seen: dict[tuple, int] = {}
    for i, b in enumerate(bands):
        key = (b.freq_mhz, b.feed)
        if key in seen:
            raise BandsRefused(
                f"band {i} repeats band {seen[key]}: the same frequency read at "
                "the same feed is one equation, not two"
            )
        seen[key] = i
    return bands


def _band_record(band: Band, z: complex, z0: float) -> dict:
    """What one band reads at one solve: its Z, SWR and the residual its
    objective drives (|X|, |Z - Z0|; None for swr)."""
    finite = math.isfinite(z.real) and math.isfinite(z.imag)
    swr = _swr(z.real, z.imag, z0) if finite else math.inf
    if band.objective == "resonance":
        resid = abs(z.imag) if finite else math.inf
        value = resid
    elif band.objective == "match_z0":
        resid = abs(z - z0) if finite else math.inf
        value = resid
    else:
        resid = None
        value = swr
    return {
        "freq_mhz": band.freq_mhz,
        "objective": band.objective,
        "feed": band.feed,
        "z0_ohms": z0,
        "z_re": float(z.real),
        "z_im": float(z.imag),
        "swr": swr,
        "residual": resid,
        "value": value,
    }


def _equations(band: Band, rec: dict) -> list[float]:
    """The band's signed residual components: [X] or [R - Z0, X]."""
    x = rec["z_im"]
    if not math.isfinite(x) or not math.isfinite(rec["z_re"]):
        return [_UNREADABLE] * band.n_equations
    if band.objective == "resonance":
        return [x]
    return [rec["z_re"] - rec["z0_ohms"], x]


#: The minimax search's smoothing of a band's value through a perfect match
#: (|Gamma| for swr, ohms for match_z0 and resonance). SWR = (1 + |G|) /
#: (1 - |G|) and |Z - Z0| are cones at the match, and a gradient search
#: stalls on a cone: on the one-coax hexbeam, where every band can reach SWR
#: 1, SLSQP spent its whole budget at 1.003. The search reads sqrt(v^2 + e^2)
#: - e instead (a C1 bowl, within e of the value); everything REPORTED is the
#: true value.
_SMOOTH_GAMMA = 1e-3
_SMOOTH_OHM = 1e-2


def _smooth_value(band: Band, rec: dict) -> float:
    """``rec``'s value for the minimax search: smooth through a perfect
    match (see `_SMOOTH_GAMMA`), large where the engine read nothing."""
    z = complex(rec["z_re"], rec["z_im"])
    if not (math.isfinite(z.real) and math.isfinite(z.imag)):
        return _UNREADABLE
    z0 = rec["z0_ohms"]
    if band.objective == "swr":
        g = abs((z - z0) / (z + z0)) if z + z0 != 0 else 1.0
        g = math.sqrt(g * g + _SMOOTH_GAMMA**2) - _SMOOTH_GAMMA
        g = min(g, 1.0 - 1e-9)
        return (1.0 + g) / (1.0 - g)
    d = abs(z.imag) if band.objective == "resonance" else abs(z - z0)
    return math.sqrt(d * d + _SMOOTH_OHM**2) - _SMOOTH_OHM


def _worst(recs: list[dict]) -> tuple[int, float]:
    i = max(range(len(recs)), key=lambda k: recs[k]["value"])
    return i, recs[i]["value"]


def json_safe(obj):
    """``obj`` with every non-finite float as None. A band the engine could not
    read has SWR inf (and Z NaN); ``json.dumps`` writes those as bare
    ``Infinity`` / ``NaN``, which a browser's JSON.parse rejects, and the
    plain-JSON response path refuses them outright. None is "no reading"."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj


def _band_metrics(rec: dict) -> dict:
    """The single-band readout's four-key shape, for a client that shows one
    Z (the worst band's)."""
    return {
        "z_in_re": rec["z_re"],
        "z_in_im": rec["z_im"],
        "z0_ohms": rec["z0_ohms"],
        "swr": rec["swr"],
    }


def _singular_words(Js: np.ndarray, names: list[str]) -> str | None:
    """Why the start's Jacobian is singular, or None. ``Js`` is taken on the
    unit cube, so knobs in metres, factors and farads compare fairly."""
    norms = np.linalg.norm(Js, axis=0)
    if not np.all(np.isfinite(Js)):
        return "the engine returned no impedance at a probe of the start"
    top = float(norms.max()) if norms.size else 0.0
    dead = [names[j] for j in range(len(names)) if norms[j] <= 1e-9 * max(top, 1e-300)]
    if dead:
        return (
            f"{', '.join(dead)} {'moves' if len(dead) == 1 else 'move'} no band's "
            "residual: the bands cannot be solved for "
            f"{'it' if len(dead) == 1 else 'them'}"
        )
    cond = float(np.linalg.cond(Js))
    if not math.isfinite(cond) or cond > _COND_MAX:
        _u, _s, vt = np.linalg.svd(Js)
        v = np.abs(vt[-1])
        together = [names[j] for j in np.argsort(-v) if v[j] > 0.25 * v.max()]
        return (
            f"{' and '.join(together)} move the bands' residuals only together "
            f"(Jacobian condition {cond:.3g}): there is no one setting that zeroes "
            "every band from here"
        )
    return None


def default_budget(n_knobs: int) -> int:
    """Distinct points a band run may solve when the request names no
    ``max_evals``: 60 per knob plus 40, at most 400."""
    return min(400, 60 * n_knobs + 40)


def objective_terms(recs: list[dict], mean_weight: float) -> tuple[float, float, float]:
    """``(J, worst, mean)`` of the bands' values: ``J = (1 - w) * worst + w *
    mean``. The minimax form minimises J (see `DEFAULT_MEAN_WEIGHT`)."""
    vals = [r["value"] for r in recs]
    worst = max(vals)
    mean = sum(vals) / len(vals)
    return (1.0 - mean_weight) * worst + mean_weight * mean, worst, mean


#: What a failed Newton's last word means for the root form's verdict.
_ROOT_STATUS = {
    "stalled": "no root in the box",
    "no-crossing": "no root in the box",
    "singular": "singular",
    "budget": "out of evals",
    "time": "out of time",
}


def optimize_bands(
    base_req: dict,
    free: list[dict],
    bands: list[Band],
    *,
    sweep_fn: Callable[[dict, list[float]], dict],
    mode: str = "minimax",
    max_evals: int | None = None,
    tol: float = 0.5,
    max_passes: int = 8,
    mean_weight: float = DEFAULT_MEAN_WEIGHT,
    on_progress: Callable[[dict], None] | None = None,
    time_budget_s: float | None = None,
    knob_units: dict[str, str] | None = None,
) -> dict:
    """Tune ``free`` (``[{name, min, max}]``, flat or dotted group-leaf names)
    so the bands in ``bands`` meet their objectives. See the module docstring.

    ``sweep_fn(req, freqs)`` builds ``req``'s design ONCE and returns
    ``{"zs": (len(freqs), n_feeds) complex, "z0_ohms": float, "tuner":
    [per-freq tuner_holds_match or None] (optional), "solve_ms": float
    (optional)}``.

    ``tol`` (ohm) is the ROOT and SEQUENTIAL forms' verdict on root bands:
    every residual under it at the answer and no resonance at a parallel
    resonance (Newton itself stops far tighter, at `optimize._ROOT_FTOL` on
    the stacked residual's norm). ``mean_weight`` is the MINIMAX form's one
    tradeoff, ``J = (1 - w) * worst + w * mean``.

    ``time_budget_s`` bounds the run's wall time (the hosted server's, so a
    slow design cannot hold a machine): past it no fresh point is solved, and
    the answer is the best full-band point solved so far, with ``stopped:
    "time"``. ``knob_units`` (knob name -> unit) only words the refusals.
    """
    if not free:
        raise BandsRefused("no free params selected to optimise")
    if not bands:
        raise BandsRefused("bands must be a non-empty list")
    if mode not in MODES:
        raise BandsRefused(f"unknown mode {mode!r} ({', '.join(MODES)})")
    try:
        w_mean = float(mean_weight)
    except (TypeError, ValueError):
        raise BandsRefused(f"mean_weight must be a number (got {mean_weight!r})")
    if not 0.0 <= w_mean <= 1.0:
        raise BandsRefused(f"mean_weight must be within 0..1 (got {mean_weight!r})")

    names = [f["name"] for f in free]
    if len(set(names)) != len(names):
        raise BandsRefused("a knob is listed twice among the free knobs")
    lo = np.array([float(f["min"]) for f in free])
    hi = np.array([float(f["max"]) for f in free])
    if np.any(~(lo < hi)):
        bad = [nm for nm, a, b in zip(names, lo, hi, strict=True) if not a < b]
        raise BandsRefused(f"{', '.join(bad)}: min must be below max")
    span = hi - lo
    n = len(names)

    n_eq = sum(b.n_equations for b in bands)
    all_roots = all(b.n_equations for b in bands)
    units = {b.unit for b in bands}

    # --- what the request asks for, refused by name before any solve -------
    for i, b in enumerate(bands):
        for k in b.knobs:
            if k not in names:
                raise BandsRefused(
                    f"{b.label(i)} names knob {k!r}, which is not a free knob"
                )
    if len(units) > 1:
        raise BandsRefused(
            "the bands compare in one unit: swr bands (a ratio) cannot share a "
            "run with resonance / match_z0 bands (ohms)"
        )
    if mode == "root" and not (all_roots and n_eq == n):
        raise BandsRefused(
            f"a root needs as many equations as knobs: the bands make {n_eq} "
            f"(resonance 1 each, match_z0 2, swr none) for {n} knobs"
        )
    if mode == "sequential":
        problem = _assignment_problem(bands, names)
        if problem is not None:
            raise BandsRefused(problem)
    form = mode
    w_run = w_mean if form == "minimax" else 0.0

    # The default budget, in distinct points solved: the minimax pays for a
    # least-squares start and a finite-difference gradient (n points) per
    # SLSQP step, so it is not the single-band 40 per knob.
    budget = int(max_evals) if max_evals else default_budget(n)

    # A range that excludes the knob's own value is refused, not clipped
    # into (AK#1909): clipping moved a 340 pF capacitor to 1e-10 pF under a
    # bound written in farads, and the run optimised an open circuit.
    x0 = []
    outside = []
    for name, a, b in zip(names, lo, hi, strict=True):
        cur = _get_knob(base_req, name)
        cur = float(0.5 * (a + b) if cur is None else cur)
        if not a <= cur <= b:
            u = f" {knob_units[name]}" if knob_units and knob_units.get(name) else ""
            msg = f"{name} = {cur:g}{u} is outside its range {a:g}..{b:g}"
            mid = 0.5 * (a + b)
            ratio = cur / mid if mid else 0.0
            if ratio > 0 and abs(math.log10(ratio)) >= 2.5:
                msg += (
                    f" (the value is about 1e{round(math.log10(ratio))} times the "
                    "range: is the range in another unit?)"
                )
            outside.append(msg)
        x0.append(min(max(cur, a), b))
    if outside:
        raise BandsRefused(
            "; ".join(outside)
            + ". Widen the range to include the current value (check its unit)."
        )
    x0 = np.array(x0)

    # Every search works on the unit cube: knobs in metres, factors and
    # farads then step, difference and converge alike, and a step's size
    # means the same fraction of its range on every knob.
    def to_x(u):
        return lo + np.clip(np.asarray(u, float), 0.0, 1.0) * span

    def to_u(x):
        return np.clip((np.asarray(x, float) - lo) / span, 0.0, 1.0)

    all_idx = tuple(range(len(bands)))
    n_evals = 0
    # The budget counts FRESH evaluations (memo misses): SLSQP asks for the
    # same point's value, constraints and gradient base separately, and the
    # memo answering them must not spend the run.
    fresh = 0
    n_solves = 0
    n_freq_solves = 0
    last_ms: float | None = None
    phase = "start"
    pass_no = 0
    band_now: int | None = None
    hard_cap = False
    # Where `hard_cap` stops a search: the budget, or a stage's own share of it.
    cap_now = budget
    memo: dict[tuple, tuple[list[dict], dict]] = {}
    t_end = None if time_budget_s is None else time.monotonic() + float(time_budget_s)
    timed_out = False
    # The best full-band point solved, by the run's own score: the answer
    # when the time budget ends a run mid-search.
    best_full: list = [math.inf, None]

    def _req_at(x) -> tuple[dict, dict]:
        req = dict(base_req)
        params = {}
        for name, v in zip(names, x, strict=True):
            val = float(v)
            _with_knob(req, name, val)
            params[name] = val
        return req, params

    def _sweep(x, freqs):
        """One build at ``x`` solved at ``freqs``: (len(freqs), n_feeds)."""
        nonlocal n_solves, n_freq_solves, last_ms
        req, _ = _req_at(x)
        t0 = time.perf_counter()
        out = sweep_fn(req, list(freqs))
        n_solves += 1
        n_freq_solves += len(freqs)
        ms = out.get("solve_ms")
        last_ms = (
            float(ms)
            if isinstance(ms, (int, float))
            else (time.perf_counter() - t0) * 1e3
        )
        zs = np.asarray(out["zs"], dtype=complex)
        if zs.ndim == 1:
            zs = zs.reshape(len(freqs), -1)
        return zs, out

    def score(recs) -> float:
        return objective_terms(recs, w_run)[0]

    def evaluate(x, idx=all_idx) -> list[dict]:
        """Solve at the bands ``idx`` (one build, every band's frequency),
        returning their records in ``idx`` order."""
        nonlocal n_evals, fresh
        x = np.asarray(x, dtype=float)
        freqs = sorted({bands[i].freq_mhz for i in idx})
        key = (tuple(float(v) for v in x), tuple(freqs))
        hit = memo.get(key)
        if hit is None and hard_cap and fresh >= cap_now:
            raise _OutOfEvals
        if hit is None and t_end is not None and fresh and time.monotonic() > t_end:
            raise _OutOfTime
        n_evals += 1
        if hit is None:
            fresh += 1
            zs, out = _sweep(x, freqs)
            z0_req = float(out.get("z0_ohms") or 50.0)
            tuner = out.get("tuner") or [None] * len(freqs)
            recs = []
            for i in idx:
                b = bands[i]
                row = freqs.index(b.freq_mhz)
                if b.feed >= zs.shape[1]:
                    raise BandsRefused(
                        f"{b.label(i)} is read at feed {b.feed}, but this design "
                        f"has {zs.shape[1]} feed{'s' if zs.shape[1] != 1 else ''} "
                        f"(feeds 0..{zs.shape[1] - 1})"
                    )
                held = tuner[row]
                if held:
                    raise DegenerateObjective(
                        f"{b.label(i)}: tuner {held['name']} retunes on every "
                        f"solve to present its target at {held['f_mhz']:g} MHz, "
                        "this band's frequency, so the band's match is met "
                        "whatever the knobs do. Drop that band, give the tuner "
                        "fixed part values instead of tune_to, or optimise "
                        "something other than the match."
                    )
                z = complex(zs[row, b.feed])
                recs.append(_band_record(b, z, b.z0 if b.z0 else z0_req))
            hit = (recs, _req_at(x)[1])
            memo[key] = hit
            if idx == all_idx:
                sc = score(recs)
                if sc < best_full[0]:
                    best_full[:] = [sc, x.copy()]
        recs, params = hit
        if on_progress is not None:
            wi, _ = _worst(recs)
            jv, mx, mn = objective_terms(recs, w_run)
            on_progress(
                json_safe(
                    {
                        "n_evals": n_evals,
                        "n_solves": n_solves,
                        "params": params,
                        "phase": phase,
                        "form": form,
                        "pass": pass_no,
                        "band_index": band_now,
                        # Only the bands this eval solved: a sequential step
                        # solves its own band; every other eval solves them all.
                        "bands": [
                            {"index": i, **r} for i, r in zip(idx, recs, strict=True)
                        ],
                        "objective": jv,
                        "objective_worst": mx,
                        "objective_mean": mn,
                        "mean_weight": w_run,
                        "worst_band": idx[wi],
                        "metrics": _band_metrics(recs[wi]),
                        "residual": max(
                            (r["residual"] for r in recs if r["residual"] is not None),
                            default=None,
                        ),
                        "solve_ms": last_ms,
                    }
                )
            )
        return recs

    def F_of(recs, idx=all_idx) -> np.ndarray:
        out = []
        for i, r in zip(idx, recs, strict=True):
            out.extend(_equations(bands[i], r))
        return np.array(out, dtype=float)

    def slopes(x, idx) -> dict[int, float]:
        """dX/df (ohm/MHz) at each resonance band of ``idx``: one build."""
        idx = [i for i in idx if bands[i].objective == "resonance"]
        if not idx:
            return {}
        d = 1e-3
        freqs = []
        for i in idx:
            f = bands[i].freq_mhz
            freqs += [f * (1 - d), f * (1 + d)]
        zs, _ = _sweep(x, freqs)
        out = {}
        for k, i in enumerate(idx):
            f = bands[i].freq_mhz
            dz = zs[2 * k + 1, bands[i].feed] - zs[2 * k, bands[i].feed]
            out[i] = float(dz.imag) / (2 * d * f)
        return out

    def antiresonant(x, idx=all_idx) -> list[int]:
        """A resonance's X = 0 is met at a PARALLEL resonance too (R in the
        kilohms; measured on the two-band fan from a start beside one), and no
        residual built from Z alone tells the two apart. The slope does: X
        rises with frequency through a series resonance and falls through a
        parallel one. One build, two frequencies per resonance band."""
        return [i for i, s in slopes(x, idx).items() if not s > 0]

    # --- the start: every band, one build ---------------------------------
    recs0 = evaluate(x0)
    for i, r in enumerate(recs0):
        if not (math.isfinite(r["z_re"]) and math.isfinite(r["z_im"])):
            raise BandsRefused(
                f"{bands[i].label(i)}: the engine returned no impedance at the "
                "start (an open-circuited port or a solve it cannot make there)"
            )

    def newton_u(probe_u, u_start, k, cap, *, J0=None, ftol=_ROOT_FTOL):
        """`_newton_root` on the unit cube [0, 1]^k."""
        return _newton_root(
            probe_u,
            list(np.clip(u_start, 0.0, 1.0)),
            [(0.0, 1.0)] * k,
            max(cap, 2),
            J0=J0,
            ftol=ftol,
            xtol=_NEWTON_XTOL_U,
        )

    def run_root(xs) -> tuple[np.ndarray, str | None, str | None]:
        """Newton from ``xs``: (best solved point, Newton's last word, why
        singular or None)."""
        nonlocal phase
        phase = "jacobian"

        def probe(u):
            return F_of(evaluate(to_x(u)))

        us = to_u(xs)
        F0 = probe(us)
        J0 = _fd_jacobian(
            probe, us, F0, np.zeros(n), np.ones(n), _fd_step([(0.0, 1.0)] * n)
        )
        why = _singular_words(J0, names)
        if why is not None:
            return np.asarray(xs, float), "singular", why
        phase = "newton"
        ur, ok, reason = newton_u(probe, us, n, budget - fresh, J0=J0)
        return to_x(ur), ("ftol" if ok else reason), None

    def run_minimax(xs) -> tuple[np.ndarray, bool, str]:
        """A least-squares start, then the epigraph form by SLSQP in a moving
        trust region. (answer, whether the minimax converged, its message)."""
        nonlocal phase, hard_cap, cap_now
        seen: list[tuple[float, np.ndarray]] = []

        def vals(recs) -> list[float]:
            return [_smooth_value(b, r) for b, r in zip(bands, recs, strict=True)]

        def stage_score(recs) -> float:
            v = vals(recs)
            return (1.0 - w_run) * max(v) + w_run * sum(v) / len(v)

        def recs_at(u):
            recs = evaluate(to_x(u))
            seen.append((stage_score(recs), np.clip(np.asarray(u, float), 0.0, 1.0)))
            return recs

        def comps(recs) -> np.ndarray:
            """What t bounds from above: each band's value, smoothed through
            its kink at a perfect match (`_smooth_value`), a resonance's as
            +X and -X so the constraint is smooth through X = 0."""
            out = []
            for b, r, v in zip(bands, recs, vals(recs), strict=True):
                if b.objective == "resonance":
                    x = r["z_im"] if math.isfinite(r["z_im"]) else _UNREADABLE
                    out += [x, -x]
                else:
                    out.append(v)
            return np.array(out)

        def mean_of(recs) -> float:
            v = vals(recs)
            return sum(v) / len(v)

        grads: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}

        def grad(u):
            """Forward differences of (comps, mean) on the unit cube, stepped
            inward at a bound; one per distinct point and stage, shared by the
            objective and the constraints."""
            u = np.clip(np.asarray(u, float), 0.0, 1.0)
            key = tuple(u)
            if key in grads:
                return grads[key]
            r0 = recs_at(u)
            c0, m0 = comps(r0), mean_of(r0)
            Jc = np.zeros((len(c0), n))
            Jm = np.zeros(n)
            for j in range(n):
                h = _FD_U if u[j] + _FD_U <= 1.0 else -_FD_U
                up = u.copy()
                up[j] += h
                r1 = recs_at(up)
                Jc[:, j] = (comps(r1) - c0) / h
                Jm[j] = (mean_of(r1) - m0) / h
            grads[key] = (Jc, Jm)
            return grads[key]

        def fun(z):
            return (1.0 - w_run) * z[-1] + w_run * mean_of(recs_at(z[:-1]))

        def fun_jac(z):
            _Jc, Jm = grad(z[:-1])
            return np.append(w_run * Jm, 1.0 - w_run)

        def con(z):
            return z[-1] - comps(recs_at(z[:-1]))

        def con_jac(z):
            Jc, _Jm = grad(z[:-1])
            return np.hstack([-Jc, np.ones((Jc.shape[0], 1))])

        def trust_region(u_c) -> tuple[np.ndarray, bool, str]:
            """SLSQP inside a TRUST REGION that moves. Unbounded, its first
            quasi-Newton step reads a linearisation of every band at once and
            leaps across the knobs' range; a multiband antenna's bands are
            full of parallel resonances (poles in SWR), and the leap lands in
            another basin -- measured on the five-band fan from +/-5 % starts,
            plain SLSQP "converged" at worst-band SWR 8 to 19 where the bands'
            own resonances read 1.21. So each round searches +/- r of the
            knobs' ranges around the incumbent: an answer on the box's edge
            re-centres and widens it, a round that does not improve narrows
            it, and an answer strictly inside ends the search."""
            seen.clear()
            j_c = stage_score(recs_at(u_c))
            r = 0.1
            for _round in range(40):
                lb = np.maximum(u_c - r, 0.0)
                ub = np.minimum(u_c + r, 1.0)
                t0 = max(comps(recs_at(u_c)).max(), 0.0)
                res = minimize(
                    fun,
                    np.append(u_c, t0),
                    jac=fun_jac,
                    method="SLSQP",
                    bounds=list(zip(lb, ub, strict=True)) + [(0.0, None)],
                    constraints=[{"type": "ineq", "fun": con, "jac": con_jac}],
                    options={"maxiter": 100, "ftol": 1e-5 * max(1.0, t0)},
                )
                u_n = np.clip(res.x[:-1], lb, ub)
                j_n = stage_score(recs_at(u_n))
                # The round's best SOLVED point, which may not be res.x.
                j_b, u_b = min(seen, key=lambda t: t[0])
                if j_b < j_n:
                    j_n, u_n = j_b, u_b
                if j_n < j_c - 1e-9 * max(1.0, abs(j_c)):
                    edge = np.any(
                        ((np.abs(u_n - lb) < 1e-6) & (lb > 0.0))
                        | ((np.abs(u_n - ub) < 1e-6) & (ub < 1.0))
                    )
                    u_c, j_c = u_n, j_n
                    if not edge and res.success:
                        return u_c, True, str(res.message)
                    r = min(2.0 * r, 0.5) if edge else r
                else:
                    if res.success and r <= 1e-3:
                        return u_c, True, str(res.message)
                    r *= 0.25
                    if r < 1e-4:
                        return u_c, bool(res.success), str(res.message)
            return u_c, False, "round limit"

        # Two stages. First a bounded least-squares fit of every band's
        # REACTANCE to zero (the resonance root as an accelerator for the
        # start; Newton's own residual, which it solves in a few dozen builds
        # on the five-band fan from starts where the bands read SWR up to
        # 524). X is the coordinate a band's own knob moves almost linearly
        # near its series resonance; SWR and Gamma wrap round near |Gamma| = 1
        # and are a poor guide there: the minimax alone, and a least-squares
        # fit of Gamma, both settled in neighbouring basins (worst-band SWR 2
        # to 28 on the five-band fan from +/-5 % starts). Then the epigraph
        # minimax on J itself, from the better of the start and that fit.
        u_best = to_u(xs)
        ok, msg = False, "out of evals"
        hard_cap = True
        try:
            phase = "least squares"

            def reactances(u):
                out = []
                for r in recs_at(u):
                    x = r["z_im"]
                    out.append(x if math.isfinite(x) else _UNREADABLE)
                return np.array(out)

            # A third of the budget at most, and a loose stop: this is a start
            # for the minimax, not an answer. With more knobs than bands the
            # fit is underdetermined and trf would otherwise spend the whole
            # run creeping along the X = 0 manifold (measured: the one-coax
            # hexbeam, ten knobs, five bands, the minimax never started).
            ls_seen: list[tuple[float, np.ndarray]] = []

            def reactances_logged(u):
                xv = reactances(u)
                ls_seen.append((float(np.sum(xv * xv)), np.clip(u, 0.0, 1.0)))
                return xv

            cap_now = min(budget, fresh + max(budget // 3, 3 * (n + 1)))
            try:
                ls = least_squares(
                    reactances_logged,
                    u_best,
                    bounds=(np.zeros(n), np.ones(n)),
                    method="trf",
                    diff_step=_FD_U * 10,
                    x_scale=1.0,
                    xtol=1e-6,
                    ftol=1e-4,
                )
                u_ls = np.clip(ls.x, 0.0, 1.0)
            except _OutOfEvals:
                u_ls = min(ls_seen, key=lambda t: t[0])[1] if ls_seen else u_best
            finally:
                cap_now = budget
            if score(evaluate(to_x(u_ls))) < score(evaluate(to_x(u_best))):
                u_best = u_ls
            phase = "minimax"
            u_best, ok, msg = trust_region(u_best)
        except _OutOfEvals:
            if seen:
                # The budget ran out mid-search: the best SOLVED point by the
                # objective itself.
                u_best = min(
                    ((score(evaluate(to_x(u))), u) for _j, u in seen),
                    key=lambda t: t[0],
                )[1]
        finally:
            hard_cap = False
        return to_x(u_best), ok, msg

    def series_root_1d(i, j, x, cap, ftol) -> np.ndarray:
        """Band ``i``'s resonance on knob ``j`` alone: Newton, then -- when it
        misses or lands on a parallel resonance -- a scan of the knob's range
        for every sign change of X, each bracketed to its root, keeping the
        SERIES resonance (dX/df > 0) nearest the start."""

        def at(v):
            xx = x.copy()
            xx[j] = lo[j] + min(max(v, 0.0), 1.0) * span[j]
            return xx

        def signed(v):
            r = evaluate(at(v), (i,))[0]
            return _equations(bands[i], r)[0]

        def probe(u):
            return np.array([signed(float(u[0]))])

        u0 = float(to_u(x)[j])
        ur, ok, _why = newton_u(probe, [u0], 1, cap, ftol=ftol)
        v = float(ur[0])
        if ok and not antiresonant(at(v), (i,)):
            return at(v)
        # The scan: 9 points across the range (one band, one frequency each).
        grid = np.linspace(0.0, 1.0, 9)
        fs = [signed(float(g)) for g in grid]
        roots = []
        for a, b, fa, fb in zip(grid[:-1], grid[1:], fs[:-1], fs[1:], strict=True):
            if fa * fb < 0 and fresh < budget:
                vr, ok2, _ = _bracket_brent(
                    signed, float(a), float(b), max(budget - fresh, 4), n_scan=2
                )
                if ok2 or abs(signed(vr)) < 10 * tol:
                    roots.append(float(vr))
        series = [r for r in roots if not antiresonant(at(r), (i,))]
        if series:
            return at(min(series, key=lambda r: abs(r - u0)))
        return at(v)

    def run_sequential(xs) -> tuple[np.ndarray, int, bool]:
        """Block coordinate descent: (best pass's answer, passes run, whether
        the passes reached a fixed point)."""
        nonlocal phase, pass_no, band_now
        x = np.asarray(xs, float).copy()
        best = (score(evaluate(x)), x.copy())
        prev = best[0]
        flat = 0
        done = 0
        fixed = False
        for p in range(max_passes):
            pass_no = p + 1
            for i, b in enumerate(bands):
                if fresh >= budget:
                    break
                band_now = i
                phase = "sequential"
                idx = [names.index(k) for k in b.knobs]
                cap = min(budget - fresh, 20 * len(idx) + 6)

                def full(u, idx=idx, x=x):
                    xx = x.copy()
                    xx[idx] = lo[idx] + np.clip(u, 0.0, 1.0) * span[idx]
                    return xx

                def val(u, i=i, full=full):
                    return evaluate(full(u), (i,))[0]["value"]

                u0 = to_u(x)[idx]
                if b.objective == "resonance" and len(idx) == 1:
                    u_best = to_u(series_root_1d(i, idx[0], x, cap, 0.1 * tol))[idx]
                    take = True  # the series root, even a hair worse
                elif b.n_equations == len(idx):

                    def probe(u, i=i, full=full):
                        return F_of(evaluate(full(u), (i,)), (i,))

                    # Each band's own solve stops well inside the pass
                    # tolerance: the other bands' turns move it again.
                    ur, _ok, _why = newton_u(probe, u0, len(idx), cap, ftol=0.1 * tol)
                    u_best = np.asarray(ur, float)
                    take = val(u_best) <= val(u0)
                else:
                    simplex = [u0] + [
                        u0 + np.where(np.arange(len(idx)) == k, 0.05, 0.0)
                        for k in range(len(idx))
                    ]
                    res = minimize(
                        lambda u, val=val: val(np.clip(u, 0.0, 1.0)),
                        u0,
                        method="Nelder-Mead",
                        bounds=[(0.0, 1.0)] * len(idx),
                        options={
                            "maxfev": max(1, cap),
                            "xatol": 1e-6,
                            "fatol": 1e-6,
                            "initial_simplex": np.clip(np.array(simplex), 0.0, 1.0),
                        },
                    )
                    u_best = np.clip(np.asarray(res.x, float), 0.0, 1.0)
                    take = val(u_best) <= val(u0)
                if take:
                    x = full(u_best)
            band_now = None
            phase = "pass check"
            recs = evaluate(x)
            done = p + 1
            cur = score(recs)
            if cur < best[0]:
                best = (cur, x.copy())
            resid = [r["residual"] for r in recs if r["residual"] is not None]
            if resid and len(resid) == len(recs) and max(resid) < tol:
                return x, done, True
            # A pass that moves J by under 0.1 % is a fixed point; two passes
            # in a row that read worse than the pass before are the descent
            # not converging (a coupled pair whose cross terms outweigh their
            # own). Either ends the run. The first pass is judged against the
            # second, not against the start: tuning one band at a time can
            # throw the others further off than they began, and a contracting
            # descent still recovers from there.
            if abs(cur - prev) <= 1e-3 * max(abs(prev), 1e-12):
                fixed = True
                break
            flat = flat + 1 if (p > 0 and cur >= prev) else 0
            if fresh >= budget or flat >= 2:
                break
            prev = cur
        return best[1], done, fixed

    method = form
    root_reason = None
    root_status = None
    singular_words = None
    converged = False
    passes = 0
    fixed = False
    try:
        if form == "root":
            method = "newton"
            x_best, root_reason, singular_words = run_root(x0)
        elif form == "sequential":
            method = "sequential"
            x_best, passes, fixed = run_sequential(x0)
        else:
            method = "slsqp minimax (trust region)"
            x_best, converged, _msg = run_minimax(x0)
    except _OutOfTime:
        timed_out = True
        x_best = best_full[1]
        root_reason = "time" if form == "root" else None
        # Every check after this point (the answer's own read, the slope
        # checks) solves again; the budget has done its job.
        t_end = None

    # The answer is a SOLVED point (each path returns one). A minimax or
    # sequential run that made things worse hands back the start; a root run's
    # best solved point stands, with its verdict.
    phase = "result"
    band_now = None
    recs_end = evaluate(x_best)
    if form != "root" and score(recs_end) > score(recs0):
        x_best, recs_end = x0, recs0

    def max_resid(recs):
        rs = [r["residual"] for r in recs if r["residual"] is not None]
        return max(rs) if rs else None

    anti_end: list[int] = []
    if form != "minimax":
        anti_end = antiresonant(x_best)
        mr = max_resid(recs_end)
        if form == "root":
            if singular_words is not None:
                root_status = "singular"
            elif mr is not None and mr <= tol and not anti_end:
                root_status = "root"
            elif anti_end:
                root_status = "parallel resonance"
            elif root_reason == "ftol":
                # Newton's norm stop met but a band still over tol: cannot
                # happen with tol above _ROOT_FTOL; named rather than assumed.
                root_status = "no root in the box"
            else:
                root_status = _ROOT_STATUS.get(root_reason, "no root in the box")
            converged = root_status == "root"
        elif mr is not None:
            converged = mr <= tol and not anti_end
        else:
            converged = fixed
    jb, mxb, mnb = objective_terms(recs0, w_run)
    ja, mxa, mna = objective_terms(recs_end, w_run)
    wb, _ = _worst(recs0)
    wa, _ = _worst(recs_end)
    u_end = (np.asarray(x_best, float) - lo) / span
    at_bound = [
        {"name": nm, "bound": "min" if u <= _AT_BOUND_U else "max", "value": float(v)}
        for nm, u, v in zip(names, u_end, x_best, strict=True)
        if u <= _AT_BOUND_U or u >= 1.0 - _AT_BOUND_U
    ]
    worst_after = max(r["swr"] for r in recs_end)
    return json_safe(
        {
            "objective": "bands",
            "form": form,
            "method": method,
            "params": {k: float(v) for k, v in zip(names, x_best, strict=True)},
            "params_before": {k: float(v) for k, v in zip(names, x0, strict=True)},
            "bands_before": [{"index": i, **r} for i, r in enumerate(recs0)],
            "bands_after": [{"index": i, **r} for i, r in enumerate(recs_end)],
            # What the run minimised, J = (1 - w) * worst + w * mean of the bands'
            # values (w is 0 outside the minimax form), and both of its terms, so
            # nothing is hidden in the scalar.
            "objective_before": jb,
            "objective_after": ja,
            "objective_worst_before": mxb,
            "objective_worst_after": mxa,
            "objective_mean_before": mnb,
            "objective_mean_after": mna,
            "mean_weight": w_run,
            "unit": next(iter(units)),
            # Read off the bands, never tracked separately: the worst SWR IS the
            # max of the per-band SWRs reported beside it.
            "worst_swr_before": max(r["swr"] for r in recs0),
            "worst_swr_after": max(r["swr"] for r in recs_end),
            "residual_before": max_resid(recs0),
            "residual_after": max_resid(recs_end),
            "worst_band_before": wb,
            "worst_band_after": wa,
            # The single-band readout's shape, at the worst band, so a client that
            # shows one Z shows the one that limits the run.
            "metrics_before": _band_metrics(recs0[wb]),
            "metrics_after": _band_metrics(recs_end[wa]),
            "n_evals": n_evals,
            # Distinct points solved (the budget's unit), builds (each a fresh
            # point or a slope check), and single-frequency solves inside them.
            "n_fresh": fresh,
            "n_solves": n_solves,
            "n_freq_solves": n_freq_solves,
            "passes": passes,
            "improved": ja < jb,
            # Root: a root was found (root_status "root"). Sequential: every root
            # band under tol, or for swr bands a fixed point. Minimax: SLSQP's own
            # convergence test.
            "converged": bool(converged),
            # The root form's verdict: "root", "no root in the box", "singular",
            # "parallel resonance" or "out of evals"; None for the other forms.
            "root_status": root_status,
            "root_reason": root_reason if singular_words is None else singular_words,
            # Resonance bands whose X = 0 is a parallel resonance (dX/df <= 0).
            "antiresonant_bands": anti_end,
            "tol": tol,
            # "time" when the wall-time budget ended the run (the answer is
            # then the best point solved by then), else None.
            "stopped": "time" if timed_out else None,
            "time_budget_s": time_budget_s,
            # Knobs that ended at a bound of their range ({name, bound
            # "min"/"max", value}): the optimum may lie past it (AK#1909).
            "at_bound": at_bound,
            # No band is anywhere near a match at the answer (AK#1909).
            "far_from_match": not worst_after <= FAR_FROM_MATCH_SWR,
        }
    )


def _assignment_problem(bands: list[Band], names: list[str]) -> str | None:
    """Why the bands' knob assignment cannot drive a sequential run, or None:
    every band names knobs, no knob serves two bands, every free knob serves
    one."""
    missing = [b.label(i) for i, b in enumerate(bands) if not b.knobs]
    if missing:
        return (
            "sequential tuning needs each band's own knobs; "
            f"{', '.join(missing)} names none"
        )
    owner: dict[str, int] = {}
    for i, b in enumerate(bands):
        for k in b.knobs:
            if k in owner:
                return (
                    f"knob {k!r} is assigned to both band {owner[k]} and band "
                    f"{i}: sequential tuning gives each knob one band"
                )
            owner[k] = i
    unowned = [k for k in names if k not in owner]
    if unowned:
        return (
            f"{', '.join(unowned)} is free but no band tunes it in sequential "
            "mode; assign it to a band or fix it"
        )
    return None


def bands_from_solves(outs: list[dict]) -> dict:
    """The ``sweep_fn`` answer from one single-frequency solve response per
    band, for an engine with no one-build sweep of its own (the external
    engines, which solve per frequency as their frequency sweep does)."""
    from .optimize import _feed_zs

    zs = [_feed_zs(o) for o in outs]
    width = max(len(r) for r in zs)
    arr = np.full((len(zs), width), complex(math.nan, math.nan))
    for k, r in enumerate(zs):
        arr[k, : len(r)] = r
    ms = [o.get("solve_ms") for o in outs]
    return {
        "zs": arr,
        "z0_ohms": float(outs[0].get("z0_ohms") or 50.0),
        "tuner": [o.get("tuner_holds_match") for o in outs],
        "solve_ms": sum(m for m in ms if isinstance(m, (int, float))) or None,
    }
