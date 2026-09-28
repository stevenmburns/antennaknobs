"""The frequency sweep's default range: ONE precedence (AK#1757, step 4).

`design_range` is the rule every tool reads when a frequency sweep names no
range of its own: ``antennaknobs sweep --swr``, ``antennaknobs analyze`` (a
`analyses.FREQUENCY` sweep with no ``lo``/``hi``), the workbench's
``/analyses``, and ``/examples`` (whose ``sweep_range`` is `declared`, the
rungs a design states outright). First match wins:

1. ``"file"``: a file design's own sweep, ``ui_params["sweep_range"]`` with
   source "file" (a ``.nec`` FR card, a ``.ssn`` Generator sweep).
2. ``"design"``: a design's ``ui_params["sweep_range"]``, else its
   ``meas_freq_range`` (the dial span it has always declared).
3. ``"policy"``: its ``sweep_policy``: the band holding the anchor when
   band-locked, else the policy's factors around it.
4. ``"default"``: ×1/1.25–×1.25 of the measurement frequency, the CLI's
   historical window.

Rungs 1–2 are the design's own and absolute, so every tool sweeps the same
span. Rungs 3–4 are relative to an anchor. Here the anchor is the design's
own frequency; the workbench's frequency is session state (the band tab, the
dial lock), so its copy of rungs 3–4 stays in ``lib/sweep.ts``, where that
state lives, and ``/analyses`` serves no range for them.

A density or spacing the design does not state is each tool's own:
``spacing`` / ``step`` / ``points`` None here. The CLI's own is 21 linear
points; the workbench's is its adaptive log grid.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

#: The CLI's frequency sweep count when neither the flags nor the design say.
CLI_POINTS = 21

# The CLI's historical relative window (`sweep.resolve_range`'s fraction).
_DEFAULT_FRACTION = 1.25

# ── the design's inputs: its band table and its sweep policy ─────────────


@dataclass(frozen=True)
class BandSpec:
    """A frequency-preset tab the UI offers as a design-frequency selector.

    The solver only sees the resulting `design_freq_mhz` float; bands are
    purely a UI affordance. Examples that target HF amateur bands reuse
    `DEFAULT_AMATEUR_BANDS`; others can supply their own list, or set bands=()
    to suppress the row entirely (fan_dipole does this — its per-band
    schema-driven controls own the design frequency).
    """

    key: str  # stable identifier; also used as the visible tab label today
    label: str
    freq_mhz: float  # tab default — slider snaps here when the band is selected
    min_mhz: float  # slider lower bound while this band is active
    max_mhz: float


@dataclass(frozen=True)
class SweepPolicy:
    """Where to centre the freq sweep and how wide to make it.

    `anchor` picks which scalar the sweep range is anchored to:
      - "design_freq": sweep around the antenna's design frequency
        (the wider out-of-band picture; default for single-band antennas).
      - "meas_freq":   sweep around the current measurement frequency
        (multi-band antennas like fan_dipole — keeps the trace focused
        on the band the user is currently tuning, since the design
        frequency stays pinned to band 0).

    `lo_factor` / `hi_factor` are multiplicative bounds applied to the
    anchor. Defaults give a broad resonance/out-of-band view; multi-band
    antennas narrow to ±5% so the trace doesn't cross into neighbouring
    bands the user isn't tuning.
    """

    anchor: str = "design_freq"  # "design_freq" | "meas_freq"
    lo_factor: float = 0.8
    hi_factor: float = 1.25
    # When True, the frontend snaps the sweep range to the [min_mhz,
    # max_mhz] of the band whose range contains the current anchor
    # frequency (typically measFreq for multi-band antennas). Falls
    # back to lo_factor/hi_factor multiplicatively if the anchor sits
    # outside every band. Used by fandipole so the sweep trace stays
    # inside the amateur band the user is currently tuning instead of
    # bleeding into the adjacent bands.
    band_locked: bool = False


DEFAULT_SWEEP_POLICY = SweepPolicy()


DEFAULT_AMATEUR_BANDS: tuple[BandSpec, ...] = (
    # Full HF amateur set + 6m/2m/70cm, low to high (issue #497; formerly
    # DEFAULT_HF_BANDS). The band dropdown scales to any number, so designs
    # (especially design_freq-scaled ones) can be placed and tuned anywhere
    # from 160m through UHF. Edges are US/ITU Region 2 (Region 1's 2m/70cm
    # allocations fit inside them); snap freqs are the customary mid-band
    # picks. (key, label, snap-freq, slider-min, -max MHz)
    BandSpec("160m", "160m", 1.900, 1.800, 2.000),
    BandSpec("80m", "80m", 3.750, 3.500, 4.000),
    BandSpec("40m", "40m", 7.150, 7.000, 7.300),
    BandSpec("30m", "30m", 10.125, 10.100, 10.150),
    BandSpec("20m", "20m", 14.300, 14.000, 14.350),
    BandSpec("17m", "17m", 18.1575, 18.068, 18.168),
    BandSpec("15m", "15m", 21.383, 21.000, 21.450),
    BandSpec("12m", "12m", 24.970, 24.890, 24.990),
    BandSpec("10m", "10m", 28.470, 28.000, 29.700),
    BandSpec("6m", "6m", 50.150, 50.000, 54.000),
    BandSpec("2m", "2m", 146.000, 144.000, 148.000),
    BandSpec("70cm", "70cm", 435.000, 420.000, 450.000),
)


def sweep_policy(ui: Mapping) -> SweepPolicy:
    """Build a SweepPolicy from a `ui_params` dict's `sweep_policy` entry.

    Accepts the positional 3-tuple `(anchor, lo_factor, hi_factor)` form or the
    mapping form (which can opt into named fields like `band_locked` without
    supplying every positional; missing fields fall back to the dataclass
    defaults). The mapping form is any Mapping: a design that freezes its
    ui_params spells it as a MappingProxyType. No entry yields the default
    policy; any other spelling — another type, or a key SweepPolicy does not
    have — raises. A dict-only check once dropped Dominator's and Challenger's
    band lock without a word (2026-07-12 to 2026-09-23), and a misspelt key
    would do the same. Takes any ui dict, so the same derivation runs for the
    default's ui_params and for each variant's deep-merged ui_params (see
    `variant_ui` in `_make_example`)."""
    raw = ui.get("sweep_policy")
    if raw is None:
        return DEFAULT_SWEEP_POLICY
    if isinstance(raw, (tuple, list)) and len(raw) == 3:
        return SweepPolicy(
            anchor=str(raw[0]),
            lo_factor=float(raw[1]),
            hi_factor=float(raw[2]),
        )
    if isinstance(raw, Mapping):
        unknown = set(raw) - {"anchor", "lo_factor", "hi_factor", "band_locked"}
        if unknown:
            raise ValueError(
                f"sweep_policy has unknown keys {sorted(unknown)}; "
                "expected anchor, lo_factor, hi_factor, band_locked"
            )
        d = DEFAULT_SWEEP_POLICY
        return SweepPolicy(
            anchor=str(raw.get("anchor", d.anchor)),
            lo_factor=float(raw.get("lo_factor", d.lo_factor)),
            hi_factor=float(raw.get("hi_factor", d.hi_factor)),
            band_locked=bool(raw.get("band_locked", d.band_locked)),
        )
    raise ValueError(
        f"sweep_policy must be a mapping or an (anchor, lo_factor, hi_factor) "
        f"triple, got {type(raw).__name__}: {raw!r}"
    )


# ── the range ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FrequencyRange:
    """A frequency sweep's span in MHz, the precedence rung it came from, and
    the density the design states: ``step`` (MHz, lin) or ``points`` (the
    total count), at most one; ``spacing`` "lin" / "log", or None when the
    design states none."""

    lo: float
    hi: float
    level: str
    spacing: str | None = None
    step: float | None = None
    points: int | None = None

    def count(self, default: int = CLI_POINTS) -> int:
        """How many points the range asks for: its own density, else
        ``default``. A step that does not divide the span still closes on
        ``hi`` (``lib/sweep.ts``'s ``sweepPointCount``, the same rule)."""
        if self.step is not None:
            span = self.hi - self.lo
            n = math.floor(span / self.step + 1e-9) + 1
            return n + 1 if self.lo + (n - 1) * self.step < self.hi - span * 1e-9 else n
        return self.points if self.points is not None else default

    def grid(self, points: int | None = None) -> np.ndarray:
        """The frequencies swept. ``points`` given replaces the range's own
        density (``sweep --npoints``); else its own, else `CLI_POINTS`. An
        unstated spacing is the CLI's own, linear. A step that divides the
        span is ``linspace`` over it, so the grid equals the one
        ``--range lo hi --npoints n`` sweeps, bit for bit."""
        if points is None and self.step is not None:
            n = self.count()
            if not math.isclose(self.lo + (n - 1) * self.step, self.hi, rel_tol=1e-9):
                return np.array(
                    [*(self.lo + i * self.step for i in range(n - 1)), self.hi]
                )
            return np.linspace(self.lo, self.hi, n)
        n = points if points is not None else self.count()
        if self.spacing == "log":
            return np.geomspace(self.lo, self.hi, n)
        return np.linspace(self.lo, self.hi, n)

    def as_spec(self) -> dict:
        """The wire shape (``/examples`` ``sweep_range``, ``/analyses``):
        ``{lo, hi, spacing, source}`` plus ``step`` or ``points``. An unstated
        spacing is served as "log", the workbench's own."""
        out: dict = {
            "lo": self.lo,
            "hi": self.hi,
            "spacing": self.spacing or "log",
            "source": "file" if self.level == "file" else "design",
        }
        if self.step is not None:
            out["step"] = self.step
        elif self.points is not None:
            out["points"] = self.points
        return out


def _positive(raw: Mapping, key: str) -> float | None:
    try:
        v = float(raw[key])
    except (KeyError, TypeError, ValueError):
        return None
    return v if v > 0.0 and math.isfinite(v) else None


def normalise_sweep_range(raw) -> FrequencyRange | None:
    """``ui_params["sweep_range"]`` as a range, or None when absent or
    malformed (AK#1682). One density survives, in the order step >
    points_per_decade > points; a ``step`` on a log range becomes
    ``points``, and ``points_per_decade`` (accepted for backward
    compatibility) always does: round(ppd · log10(hi/lo)) + 1, at least 2."""
    if not isinstance(raw, Mapping):
        return None
    try:
        lo, hi = float(raw["lo"]), float(raw["hi"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (0.0 < lo < hi and math.isfinite(hi)):
        return None
    spacing = str(raw.get("spacing", "lin")).lower()
    if spacing not in ("lin", "log"):
        return None
    level = "file" if raw.get("source") == "file" else "design"
    step, ppd, points = (
        _positive(raw, "step"),
        _positive(raw, "points_per_decade"),
        _positive(raw, "points"),
    )
    kw: dict = {}
    if step is not None:
        if spacing == "lin":
            kw["step"] = step
        else:
            kw["points"] = int(math.floor((hi - lo) / step + 1e-9)) + 1
    elif ppd is not None:
        kw["points"] = max(2, round(ppd * math.log10(hi / lo)) + 1)
    elif points is not None and points >= 2:
        kw["points"] = int(points)
    return FrequencyRange(lo, hi, level, spacing, **kw)


def _ui(params: Mapping) -> Mapping:
    ui = params.get("ui_params")
    return ui if isinstance(ui, Mapping) else {}


def declared(params: Mapping) -> FrequencyRange | None:
    """Rungs 1–2: the range a design states outright, or None."""
    ui = _ui(params)
    own = normalise_sweep_range(ui.get("sweep_range"))
    if own is not None:
        return own
    dial = ui.get("meas_freq_range")
    if isinstance(dial, (tuple, list)) and len(dial) == 2:
        try:
            lo, hi = float(dial[0]), float(dial[1])
        except (TypeError, ValueError):
            return None
        if 0.0 < lo < hi and math.isfinite(hi):
            return FrequencyRange(lo, hi, "design")
    return None


def _bands(ui: Mapping) -> tuple[BandSpec, ...]:
    # A Mapping under "bands" is a repeat group's config, not a band table
    # (the adapter's reading, `_make_example`).
    raw = ui.get("bands")
    if raw is not None and not isinstance(raw, Mapping):
        return tuple(BandSpec(*b) for b in raw)
    return DEFAULT_AMATEUR_BANDS


def design_range(params: Mapping) -> FrequencyRange:
    """The frequency sweep's range on a design with ``params`` (a builder's
    ``_params``: its knobs and ``ui_params``), rungs 1–4 (module doc)."""
    own = declared(params)
    if own is not None:
        return own
    freq = float(params["freq"])
    ui = _ui(params)
    policy = sweep_policy(ui)
    if policy != DEFAULT_SWEEP_POLICY:
        anchor = (
            float(params.get("design_freq", freq))
            if policy.anchor == "design_freq"
            else freq
        )
        if policy.band_locked:
            for band in _bands(ui):
                if band.min_mhz <= anchor <= band.max_mhz:
                    return FrequencyRange(band.min_mhz, band.max_mhz, "policy")
        if (policy.lo_factor, policy.hi_factor) != (0.8, 1.25):
            return FrequencyRange(
                anchor * policy.lo_factor, anchor * policy.hi_factor, "policy"
            )
    return FrequencyRange(freq / _DEFAULT_FRACTION, freq * _DEFAULT_FRACTION, "default")


def level_words(r: FrequencyRange) -> str:
    """Where a range came from, for a summary line."""
    return {
        "file": "the file's own",
        "design": "the design's own",
        "policy": "the design's band policy",
        "default": "the default ×0.8–×1.25 window",
    }[r.level]
