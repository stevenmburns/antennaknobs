"""The numbers behind `analyses`' metrics (AK#1828, sweep-framework step 8).

`analyses` declares WHAT a metric reads (`analyses.ElevationWindow`,
`analyses.GainAt`, the pattern table's columns); this
module reads it off one solved engine. Everything goes through a `Source`,
the engine's far field as a function of direction:

- **momwire** evaluates gain off its solve at any direction
  (`MomwireEngine.gain_evaluator`), so a window 0.1 degree apart is read
  exactly, and the table's columns are `far_field.refined_pattern_metrics`
  on that evaluator: exactly what ``/pattern_metrics`` computes;
- **NEC-5** runs one ``RP`` card per request on exactly the grid asked for
  (`NEC5Engine.gain_grid`), and the table's columns are
  `far_field.pattern_metrics` on its 1-degree pattern, as ``compare_patterns``
  reads them;
- any other engine is read off its 1-degree far-field grid: a metric whose
  angles are on that grid is read exactly, and any other is refused by name.

`table_values` is the pattern table (`analyses.TABLE_METRICS`): the same dict
``far_field.engine_pattern_metrics`` returns, key for key and bit for bit,
because each column is the one function's own number. That is the one path
the design note asks for.

Rules every metric shares, in degrees:

- an elevation cut at a number reads that azimuth; at `PEAK_AZ`, the azimuth
  of the pattern's peak gain (the table's ``azimuth_deg``); at `MEAN_AZ`,
  each elevation's power average over the azimuth ring 0..359, 1 degree
  apart;
- a grid of angles ``lo``..``hi`` ``step`` apart is ``lo + i * step``,
  rounded to 1e-9 degree, so the same window reads the same directions
  wherever it is asked (a window and a callable written to equal it are
  ``==``, the gate).
"""

from __future__ import annotations

import numpy as np

from . import analyses as an

#: The azimuth ring `MEAN_AZ` averages over: 1 degree apart, all the way round.
MEAN_AZ_RING = np.arange(0.0, 360.0, 1.0)

#: The far-field grid the table's grid measure reads (`far_field.compare_patterns`'
#: and `analysis_run.PATTERN_GRID`).
_GRID = {"n_theta": 90, "n_phi": 360, "del_theta": 1, "del_phi": 1}


class MetricError(ValueError):
    """A metric this engine cannot read, in words for the run's output."""


def angle_grid(lo: float, hi: float, step: float) -> np.ndarray:
    """``lo + i * step`` up to ``hi`` inclusive, rounded to 1e-9 degree (the
    module docstring's shared rule)."""
    n = round((hi - lo) / step)
    return np.round(lo + step * np.arange(n + 1), 9)


def _db(power: np.ndarray) -> np.ndarray:
    return 10.0 * np.log10(power)


def _power(dbi: np.ndarray) -> np.ndarray:
    return 10.0 ** (np.asarray(dbi, float) / 10.0)


# ── sources ──────────────────────────────────────────────────────────────────


class Source:
    """One solved pattern, read as a function of direction: ``gain(thetas,
    phis)``, the (n_theta, n_phi) grid of total gain in dBi (theta from the
    zenith, phi from +x, degrees); ``polarized`` the same grid as its
    vertical and horizontal parts; ``table()`` the pattern table's dict."""

    freq_mhz: float

    def gain(self, thetas, phis) -> np.ndarray:
        raise NotImplementedError

    def polarized(self, thetas, phis) -> tuple[np.ndarray, np.ndarray] | None:
        """``(vertical, horizontal)`` dBi on the grid, or None where the
        engine cannot split them."""
        return None

    def table(self) -> dict:
        raise NotImplementedError


class EvaluatorSource(Source):
    """momwire: a gain evaluator off one solve (`gain_evaluator`)."""

    def __init__(self, gain, freq_mhz: float):
        self._gain = gain
        self.freq_mhz = float(freq_mhz)
        self._table: dict | None = None

    def gain(self, thetas, phis) -> np.ndarray:
        return np.asarray(self._gain(thetas, phis), float)

    def polarized(self, thetas, phis):
        split = getattr(self._gain, "polarized", None)
        if split is None:
            return None
        try:
            return split(thetas, phis)
        except NotImplementedError:
            return None

    def table(self) -> dict:
        # The workbench's own: `far_field.engine_pattern_metrics` on momwire,
        # what ``/pattern_metrics`` computes (`adapter._metrics_from_gain`).
        if self._table is None:
            from .far_field import refined_pattern_metrics

            self._table = refined_pattern_metrics(self._gain)
        return self._table


class GridSource(Source):
    """An engine read off its 1-degree far-field grid: exact at the grid's
    directions (theta 0..89, phi 0..360), refused by name anywhere else."""

    def __init__(self, engine, ff=None):
        self._engine = engine
        self._ff = ff
        self.freq_mhz = float(engine.builder.freq)
        self._table: dict | None = None

    @property
    def ff(self):
        if self._ff is None:
            self._ff = self._engine.far_field(**_GRID)
        return self._ff

    def _index(self, axis, values, what: str) -> np.ndarray:
        axis = np.asarray(axis, float)
        out = []
        for v in np.atleast_1d(np.asarray(values, float)):
            hit = np.flatnonzero(np.isclose(axis, v, atol=1e-9))
            if hit.size == 0:
                raise MetricError(
                    f"{type(self._engine).__name__} gives its far field on a "
                    f"1-degree grid (theta 0..89 from the zenith), and the metric "
                    f"asks for {what} {v:g}; on this engine give whole degrees "
                    "above the horizon (step=1), or run momwire or nec5, which "
                    "read any direction"
                )
            out.append(int(hit[0]))
        return np.array(out, int)

    def gain(self, thetas, phis) -> np.ndarray:
        rings = np.asarray(self.ff.rings, float)
        ti = self._index(self.ff.thetas, thetas, "theta")
        pi = self._index(self.ff.phis, np.mod(phis, 360.0), "phi")
        return rings[np.ix_(ti, pi)]

    def table(self) -> dict:
        if self._table is None:
            from .far_field import _engine_has_ground, pattern_metrics

            self._table = pattern_metrics(
                self.ff, has_ground=_engine_has_ground(self._engine)
            )
        return self._table


class NecSource(GridSource):
    """NEC-5: an ``RP`` run on exactly the directions asked for
    (`NEC5Engine.gain_grid`), the table off its 1-degree pattern."""

    def gain(self, thetas, phis) -> np.ndarray:
        return self._engine.gain_grid(thetas, phis)[0]

    def polarized(self, thetas, phis):
        _total, v, h = self._engine.gain_grid(thetas, phis)
        return v, h


def source_for(engine, ff=None) -> Source:
    """The `Source` an engine is read through (module docstring): its gain
    evaluator, its ``RP`` runs, else its far-field grid (``ff`` when the
    caller has it already)."""
    if hasattr(engine, "gain_evaluator"):
        return EvaluatorSource(engine.gain_evaluator(), engine.builder.freq)
    if hasattr(engine, "gain_grid"):
        return NecSource(engine, ff)
    return GridSource(engine, ff)


# ── cuts ─────────────────────────────────────────────────────────────────────


def resolve_az(az, source: Source) -> float | None:
    """An elevation cut's azimuth: a number as given, `PEAK_AZ` the table's
    ``azimuth_deg``, `MEAN_AZ` None (averaged)."""
    if az is None or az == an.PEAK_AZ:
        return float(source.table()["azimuth_deg"])
    if az == an.MEAN_AZ:
        return None
    return float(az)


def elevation_cut(
    source: Source, els, az, *, polarized: bool = False
) -> tuple[np.ndarray, tuple | None]:
    """Total dBi at elevations ``els`` on the cut ``az`` picks, and, with
    ``polarized``, its ``(vertical, horizontal)`` dBi (None when the engine
    cannot split them)."""
    els = np.asarray(els, float)
    thetas = 90.0 - els
    fixed = resolve_az(az, source)
    phis = MEAN_AZ_RING if fixed is None else np.array([fixed])

    def reduce(grid):
        g = np.asarray(grid, float)
        return g[:, 0] if fixed is not None else _db(_power(g).mean(axis=1))

    total = reduce(source.gain(thetas, phis))
    pol = None
    if polarized:
        split = source.polarized(thetas, phis)
        if split is not None:
            pol = (reduce(split[0]), reduce(split[1]))
    return total, pol


def _peak_on_cut(metric, source: Source) -> tuple[float, float]:
    """``(peak dBi, its elevation)`` on the cut ``metric.az`` picks, over
    0..90 ``metric.step`` apart; the first of equal maxima (the highest
    elevation, as the table breaks ties) wins."""
    els = angle_grid(0.0, 90.0, metric.step)
    g, _ = elevation_cut(source, els, metric.az)
    top = np.flatnonzero(g >= g.max())
    i = int(top[-1])
    return float(g[i]), float(els[i])


# ── evaluating ───────────────────────────────────────────────────────────────


def evaluate(metric: an.PatternMetric, source: Source) -> float | None:
    """``metric`` read off ``source``: a float, or None where the table
    itself has none (the RDF of a free-space pattern on a hemisphere grid).
    A metric this engine cannot read is a `MetricError` naming why."""
    key = metric.table_key
    if key is not None:
        v = source.table()[key]
        return None if v is None else float(v)
    if isinstance(metric, an.ElevationWindow):
        g, _ = elevation_cut(source, angle_grid(metric.lo, metric.hi, metric.step),
                             metric.az)  # fmt: skip
        if metric.mean == "power":
            return float(_db(_power(g).mean()))
        if metric.mean == "db":
            return float(np.mean(g))
        return float(np.max(g))
    if isinstance(metric, an.GainAt):
        g, _ = elevation_cut(source, np.array([float(metric.el)]), metric.az)
        return float(g[0])
    if isinstance(metric, an.TakeOff):
        return _peak_on_cut(metric, source)[1]
    if isinstance(metric, an.PeakGain):
        return _peak_on_cut(metric, source)[0]
    raise MetricError(f"no way to read the metric {metric!r}")


def table_values(source: Source) -> dict:
    """The pattern table (`analyses.TABLE_METRICS`) as ``engine_pattern_metrics``
    keys it, each column read through `evaluate`."""
    return {m.key: evaluate(m, source) for m in an.TABLE_METRICS}


def values(metrics, source: Source) -> dict[str, float | None]:
    """``{name: value}`` for user ``metrics`` on one pattern."""
    return {m.name: evaluate(m, source) for m in metrics}


def column_heading(metric: an.PatternMetric) -> str:
    """A metric's table heading and CSV column: its name and unit."""
    return f"{metric.name} ({metric.unit})" if metric.unit else metric.name
