"""Calibrate model parameters against a measured VNA sweep (issue #639).

The measured overlay (``measured.py``, issue #595) answers "does the model
match the bench?". This module inverts the question: given a measurement,
**what would the model have to believe** to reproduce it? The free parameters
worth fitting are the ones a tape measure can't give you — the ground constants
under *this* yard, the as-built length after sag and end effects, the electrical
length of a feedline, a stray feedpoint reactance. The output is a calibrated
design plus a residual that says how much of the measurement the model can
account for.

Three deliberate choices shape the implementation:

**Fit complex Γ, not SWR.** Phase is what separates causes: a length error and
a ground error both widen |Γ|, but they rotate it differently. Fitting |Γ| (or
SWR) throws away exactly the information that makes the parameters
distinguishable.

**Identifiability is the hard part, not the optimizer.** Length, ground, and
line length all bend S11 in similar ways, so a fit over four free parameters
and one narrow band is usually under-determined even when it converges
beautifully. :func:`fit` caps the free-parameter count and reports the
conditioning of the solution — the near-degenerate *combination* of parameters
by name, not just a warning — so an under-determined fit announces itself
instead of looking like an answer.

**Report the residual honestly.** Common-mode current on a real feedline
perturbs a measurement in ways a differential model cannot reproduce; so does
anything the design omits. The final RMS misfit is part of the result, and
structured residual (a systematic tilt or offset rather than noise) is a
diagnostic pointer, not a number to optimize away by letting parameters wander
somewhere nonphysical. Bounds keep them physical.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from . import Antenna
from .measured import MeasuredTrace
from .opt import _get_path, _set_path

__all__ = ["fit", "FitResult", "LineEmbedding", "MAX_FREE_PARAMS", "plot_fit"]

logger = logging.getLogger(__name__)

# Upper bound on simultaneously fitted parameters. Not an optimizer limit — a
# scientific one: past three or four knobs, a single-band S11 curve simply does
# not carry enough independent information, and the fit starts trading one
# physical explanation against another (see the module docstring).
MAX_FREE_PARAMS = 4

# Condition number of the Jacobian above which the fit is reported as
# under-determined. The Jacobian is column-scaled first, so this is a pure
# collinearity measure: 100 means the weakest parameter combination moves the
# residual 100× less than the strongest.
ILL_CONDITIONED = 100.0


@dataclass(frozen=True)
class LineEmbedding:
    """A known feedline between the model's port and the measurement plane.

    A VNA calibrated at the shack end sees the antenna *through* the feedline.
    When the design itself models that line (a ``TL`` in ``build_network()``),
    nothing is needed here — the model's port already is the station plane.
    This is for the other case: an antenna-only model and a measurement taken
    at the far end of a line whose type and length are known.

    ``k1``/``k2`` are the cable-table matched-loss coefficients
    (dB/100 ft = k1·√f_MHz + k2·f_MHz), the same model ``network.TL`` uses, so
    a catalog cable embeds here exactly as it would inside the network.
    """

    z0: float
    length_m: float
    vf: float = 1.0
    k1: float = 0.0
    k2: float = 0.0

    @classmethod
    def from_cable(cls, cable: str, length_m: float) -> "LineEmbedding":
        """Look ``cable`` up in ``network.CABLES`` (``"RG-213"``, …)."""
        from .network import CABLES

        if cable not in CABLES:
            raise KeyError(
                f"unknown cable {cable!r}; available: {', '.join(sorted(CABLES))}"
            )
        c = CABLES[cable]
        return cls(z0=c.z0, length_m=length_m, vf=c.vf, k1=c.k1, k2=c.k2)

    @classmethod
    def parse(cls, spec: str) -> "LineEmbedding":
        """``"RG-213:30.5"`` → 30.5 m of RG-213 (the CLI spelling)."""
        cable, _, length = spec.partition(":")
        if not length:
            raise ValueError(
                f"line spec {spec!r} should be '<cable>:<length_m>', e.g. 'RG-213:30.5'"
            )
        return cls.from_cable(cable.strip(), float(length))

    def embed(self, z_load: np.ndarray, freqs_mhz: np.ndarray) -> np.ndarray:
        """Impedance seen through the line, ``Z₀(Z+Z₀·tanh γl)/(Z₀+Z·tanh γl)``."""
        from .network_reduce import C_LIGHT, FEET_PER_M, NEPER_PER_DB

        f = np.asarray(freqs_mhz, dtype=float)
        beta = 2.0 * np.pi * (f * 1e6) / (self.vf * C_LIGHT)
        alpha = (self.k1 * np.sqrt(f) + self.k2 * f) * NEPER_PER_DB * FEET_PER_M / 100.0
        t = np.tanh((alpha + 1j * beta) * self.length_m)
        return self.z0 * (z_load + self.z0 * t) / (self.z0 + z_load * t)


@dataclass
class FitResult:
    """Outcome of a fit: what moved, how far, and how much is left over."""

    names: tuple[str, ...]
    nominal: tuple[float, ...]
    fitted: tuple[float, ...]
    bounds: tuple[tuple[float, float], ...]
    freqs: np.ndarray
    gamma_measured: np.ndarray
    gamma_nominal: np.ndarray
    gamma_fitted: np.ndarray
    z0: float
    builder: object
    label: str = "measured"
    #: Column-scaled Jacobian condition number; ``inf`` when it is singular.
    condition: float = float("nan")
    #: Parameter weights of the least-identifiable combination (see `report`).
    weakest: tuple[float, ...] = ()
    nfev: int = 0
    #: Set when the measured band sits far from what the design is cut for.
    band_note: str = ""
    message: str = ""
    _rms: dict = field(default_factory=dict, repr=False)

    @staticmethod
    def _rms_of(delta: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.abs(delta) ** 2)))

    @property
    def rms_nominal(self) -> float:
        """RMS |ΔΓ| of the *starting* model against the measurement."""
        return self._rms_of(self.gamma_nominal - self.gamma_measured)

    @property
    def rms_fitted(self) -> float:
        """RMS |ΔΓ| left after fitting — the honest bottom line."""
        return self._rms_of(self.gamma_fitted - self.gamma_measured)

    @property
    def at_bound(self) -> tuple[str, ...]:
        """Parameters that ended pinned against a bound.

        A pinned parameter means the fit wanted to go somewhere the bounds
        forbade: either the bound is too tight, or the model is absorbing
        something physical (common mode, a missing element) into the wrong
        knob. Either way the value is not a measurement.
        """
        out = []
        for nm, v, (lo, hi) in zip(self.names, self.fitted, self.bounds, strict=True):
            span = hi - lo
            if span > 0 and (v - lo < 1e-6 * span or hi - v < 1e-6 * span):
                out.append(nm)
        return tuple(out)

    def report(self) -> str:
        """A human-readable summary — what the CLI prints."""
        lines = [
            f"fit against {self.label!r}: {self.freqs.size} points, "
            f"{self.freqs[0]:.4g}–{self.freqs[-1]:.4g} MHz, z0 = {self.z0:g} Ω",
            "",
            f"{'parameter':<28} {'nominal':>12} {'fitted':>12} {'shift':>12}",
        ]
        for nm, a, b in zip(self.names, self.nominal, self.fitted, strict=True):
            pct = f"{100.0 * (b - a) / a:+.2f}%" if a else "—"
            lines.append(f"{nm:<28} {a:>12.6g} {b:>12.6g} {b - a:>+12.6g}  {pct}")
        lines += [
            "",
            f"RMS |ΔΓ|   nominal {self.rms_nominal:.4f}  →  fitted {self.rms_fitted:.4f}"
            f"   ({self.nfev} model evaluations)",
        ]
        if pinned := self.at_bound:
            lines.append(
                f"WARNING: {', '.join(pinned)} ended at a bound — the fit wanted to "
                "go further than you allowed. Widen the bound, or ask whether the "
                "model is missing something this knob is standing in for."
            )
        if not np.isfinite(self.condition) or self.condition > ILL_CONDITIONED:
            combo = "  ".join(
                f"{w:+.2f}·{nm}" for w, nm in zip(self.weakest, self.names, strict=True)
            )
            lines += [
                f"WARNING: under-determined (Jacobian condition {self.condition:.3g}). "
                "These data barely constrain the combination",
                f"         {combo}",
                "         — its fitted value is close to arbitrary. Fit fewer "
                "parameters, or measure a wider / second band.",
            ]
        if self.band_note:
            lines.append(self.band_note)
        if self.rms_fitted > 0.05:
            lines.append(
                f"NOTE: {self.rms_fitted:.3f} RMS |ΔΓ| is a large residual. Look at "
                "its shape before trusting the parameters: a systematic tilt or "
                "offset means something physical is missing from the model "
                "(commonly common-mode current on the feedline), not that the "
                "knobs are wrong."
            )
        return "\n".join(lines)


def _fit_grid(measured: MeasuredTrace, npoints: int, band=None) -> np.ndarray:
    """Frequencies to compare on: the measured grid, thinned to ``npoints``.

    Comparison points are *measured* frequencies, so neither side is
    interpolated where it matters — the model is solved exactly there, and the
    measurement is used as recorded. A VNA's few hundred points would make
    every optimizer step a few hundred solves for information a couple of dozen
    already carry.

    The subsample takes every k-th point rather than ``npoints`` evenly spaced
    ones: on the uniform grid every analyzer writes, a constant stride keeps the
    result exactly evenly spaced (which ``PyNECEngine.impedance_sweep``
    requires), at the cost of landing a little under ``npoints`` rather than
    exactly on it.
    """
    freqs = measured.freqs
    if band is not None:
        lo, hi = float(band[0]), float(band[1])
        inside = (freqs >= lo) & (freqs <= hi)
        if not inside.any():
            from .measured import BandOverlapError

            raise BandOverlapError(
                f"fit range [{lo:.6g}, {hi:.6g}] MHz does not overlap the measured "
                f"band [{freqs[0]:.6g}, {freqs[-1]:.6g}] MHz"
            )
        freqs = freqs[inside]
    if npoints < 2:
        raise ValueError("a fit needs at least 2 comparison frequencies")
    if freqs.size <= npoints:
        return freqs
    stride = int(np.ceil(freqs.size / npoints))
    return freqs[::stride]


def _resolve_bounds(x0, bounds, fractions):
    """Bounds per parameter, in ``optimize()``'s conventions.

    Explicit ``bounds`` win; otherwise each parameter gets a multiplicative
    window from ``fractions`` (scalar or per-parameter), defaulting to ±10%
    — a deliberately tighter default than ``optimize()``'s ±67%, because a
    calibration is a *correction* to a known design, and a wide window invites
    the optimizer to explain a bad measurement with an absurd antenna.
    """
    if bounds is not None:
        if len(bounds) != len(x0):
            raise ValueError(
                f"got {len(bounds)} bound pairs for {len(x0)} free parameters"
            )
        return tuple((float(lo), float(hi)) for lo, hi in bounds)
    if fractions is None:
        fracs = [0.10] * len(x0)
    elif np.isscalar(fractions):
        fracs = [float(fractions)] * len(x0)
    else:
        fracs = [float(f) for f in fractions]
        if len(fracs) == 1:
            fracs *= len(x0)  # one value broadcasts to every parameter
        elif len(fracs) != len(x0):
            raise ValueError(
                f"got {len(fracs)} fractions for {len(x0)} free parameters "
                "(pass one value, or one per parameter)"
            )
    out = []
    for x, f in zip(x0, fracs, strict=True):
        # A parameter nominally 0 (a stray reactance, a length correction) has
        # no multiplicative window; give it an absolute one instead.
        lo, hi = (-f, f) if x == 0 else sorted((x * (1 - f), x * (1 + f)))
        out.append((float(lo), float(hi)))
    return tuple(out)


def _band_note(antenna_builder, freqs: np.ndarray) -> str:
    """A note when the measurement sits nowhere near what the design is cut for.

    Deliberately a note and not an error. The obvious gate — "refuse when the
    measured band misses the design band" — would reject the legitimate case of
    fitting a design on a *harmonic* band, which is ordinary practice (a 40 m
    dipole worked on 15 m) and something this tool should support. Nor is a
    remote band meaningless: an off-band measurement genuinely constrains
    length and ground. What it usually means is that the wrong file got picked,
    so say so and let the residual speak.
    """
    bands = getattr(antenna_builder, "bands", None)
    if bands:
        centers = [
            float(b["freq"]) for b in bands if isinstance(b, dict) and "freq" in b
        ]
    else:
        centers = []
    if not centers:
        f0 = getattr(antenna_builder, "design_freq", None) or getattr(
            antenna_builder, "freq", None
        )
        if not f0:
            return ""
        centers = [float(f0)]
    fc = float(np.sqrt(freqs[0] * freqs[-1]))  # geometric centre of the measurement
    for c in centers:
        ratio = fc / c
        if 1 / 1.4 <= ratio <= 1.4:
            return ""
        # Harmonic operation is a real use of a design, not a mistake.
        n = round(ratio)
        if 2 <= n <= 9 and abs(ratio - n) / n < 0.1:
            return (
                f"NOTE: the measurement ({fc:.4g} MHz) is near the {n}th harmonic of "
                f"the {c:.4g} MHz design — fitting off-band is fine, but remember "
                "the model must be right there too."
            )
    near = min(centers, key=lambda c: abs(np.log(fc / c)))
    return (
        f"NOTE: the measurement is centred at {fc:.4g} MHz while the design is cut "
        f"for {near:.4g} MHz. That is a long way off-band — if this is not the file "
        "you meant to fit, the parameter values below are meaningless."
    )


def _conditioning(jac: np.ndarray) -> tuple[float, tuple[float, ...]]:
    """Column-scaled condition number and the weakest parameter combination.

    Scaling each column to unit norm first removes the units — otherwise a
    parameter measured in metres and one in siemens/metre would look
    "ill-conditioned" purely from their magnitudes. What is left is genuine
    collinearity: how nearly two knobs bend Γ the same way over this band.
    """
    if jac.size == 0:
        return float("nan"), ()
    norms = np.linalg.norm(jac, axis=0)
    if not np.all(norms > 0):
        # A column of zeros: that parameter does not move the model at all here.
        weakest = np.zeros(jac.shape[1])
        weakest[int(np.argmin(norms))] = 1.0
        return float("inf"), tuple(weakest)
    scaled = jac / norms
    _, sv, vt = np.linalg.svd(scaled, full_matrices=False)
    cond = float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf")
    return cond, tuple(float(v) for v in vt[-1])


def fit(
    antenna_builder,
    measured: MeasuredTrace,
    names,
    *,
    z0: float = 50.0,
    engine=Antenna,
    bounds=None,
    fractions=None,
    npoints: int = 21,
    band=None,
    port: int = 0,
    line: LineEmbedding | None = None,
    weights=None,
) -> FitResult:
    """Fit ``names`` (dotted paths) of ``antenna_builder`` to ``measured``.

    Paths are resolved by the same ``opt.py`` machinery ``optimize()`` uses, so
    builder attributes, the bands tuple, and per-band dicts are all reachable
    (``length_top``, ``terrain.facets.0.eps_r``, ``bands.1.halfdriver_factor``).

    The objective is the complex-Γ misfit at ``z0`` over a subsample of the
    measured grid (see :func:`_fit_grid`); ``line`` moves the comparison to the
    far end of a known feedline. Returns a :class:`FitResult` — the builder it
    carries has been left at the fitted values.
    """
    names = tuple(names)
    if not names:
        raise ValueError("fit needs at least one free parameter")
    if len(names) > MAX_FREE_PARAMS:
        raise ValueError(
            f"{len(names)} free parameters is more than a single measured sweep can "
            f"identify; fit at most {MAX_FREE_PARAMS} at a time. Length, ground, and "
            "line length all bend S11 in similar ways — fitting them together makes "
            "the answer depend on the starting point rather than on the data. Fit "
            "the ones you cannot measure, hold the rest at their as-built values, "
            "and use a wider or a second band when you need more."
        )

    grid = _fit_grid(measured, npoints, band)
    _, gamma_meas = measured.renormalized(z0).align(grid)
    w = np.ones(grid.size) if weights is None else np.asarray(weights, dtype=float)
    if w.shape != grid.shape:
        raise ValueError(f"weights must have {grid.size} entries, one per fit point")
    sw = np.sqrt(w)

    x0 = np.array([float(_get_path(antenna_builder, nm)) for nm in names], dtype=float)
    bnds = _resolve_bounds(x0, bounds, fractions)
    lo = np.array([b[0] for b in bnds])
    hi = np.array([b[1] for b in bnds])
    if np.any(x0 < lo) or np.any(x0 > hi):
        # least_squares rejects an out-of-bounds start outright; nudging in is
        # friendlier than refusing, and says so.
        logger.info("starting values clipped into the requested bounds")
        x0 = np.clip(x0, lo, hi)

    evals = {"n": 0}

    def model_gamma(x) -> np.ndarray:
        for v, nm in zip(x, names, strict=True):
            _set_path(antenna_builder, nm, float(v))
        a = engine(antenna_builder)
        zs = np.asarray(a.impedance_sweep(grid))
        del a
        zs = zs[:, port] if zs.ndim > 1 else zs
        if line is not None:
            zs = line.embed(zs, grid)
        evals["n"] += 1
        return (zs - z0) / (zs + z0)

    def residual(x) -> np.ndarray:
        d = (model_gamma(x) - gamma_meas) * sw
        # least_squares wants a real vector: real and imaginary parts are two
        # independent residuals, which is exactly the point of fitting complex Γ.
        return np.concatenate([d.real, d.imag])

    gamma_nominal = model_gamma(x0)
    res = least_squares(
        residual,
        x0=x0,
        bounds=(lo, hi),
        # Jacobian columns scaled by their own sensitivity: without it a
        # metres-scale knob and a conductivity-scale one get the same step.
        x_scale="jac",
        diff_step=1e-4,
        xtol=1e-10,
        ftol=1e-8,
    )
    gamma_fitted = model_gamma(res.x)  # also leaves the builder at the fit
    cond, weakest = _conditioning(np.asarray(res.jac))

    return FitResult(
        names=names,
        nominal=tuple(float(v) for v in x0),
        fitted=tuple(float(v) for v in res.x),
        bounds=bnds,
        freqs=grid,
        gamma_measured=gamma_meas,
        gamma_nominal=gamma_nominal,
        gamma_fitted=gamma_fitted,
        z0=float(z0),
        builder=antenna_builder,
        label=measured.label,
        condition=cond,
        weakest=weakest,
        nfev=evals["n"],
        band_note=_band_note(antenna_builder, grid),
        message=str(res.message),
    )


def plot_fit(result: FitResult, *, fn=None):
    """Two-panel comparison: SWR of all three traces, and the residual.

    The top panel is the familiar view (measured, nominal model, fitted model)
    and answers "did it get closer?". The bottom panel is the one worth reading
    carefully: |ΔΓ| versus frequency, before and after. Residual that is flat
    and small is noise — the fit is done. Residual with *shape* — a tilt, a
    bump at one end, a peak at resonance — is structure the model does not
    contain, and no amount of parameter fitting will remove it honestly.
    """
    import matplotlib.pyplot as plt

    from .core import save_or_show
    from .measured import RHO_MAX
    from .sweep import _polish_axes

    def swr(g):
        rho = np.minimum(np.abs(g), RHO_MAX)
        return (1.0 + rho) / (1.0 - rho)

    f = result.freqs
    fig, (ax0, ax1) = plt.subplots(
        2, 1, figsize=(7.5, 6.4), sharex=True, height_ratios=(2, 1)
    )
    ax0.plot(
        f, swr(result.gamma_measured), color="0.25", linestyle="--", marker="x",
        ms=4, linewidth=1.3, label=f"measured ({result.label})",
    )  # fmt: skip
    ax0.plot(
        f, swr(result.gamma_nominal), color="tab:orange", linestyle=":",
        marker="o", ms=3, label="model (nominal)",
    )  # fmt: skip
    ax0.plot(
        f, swr(result.gamma_fitted), color="tab:blue", marker="o", ms=3,
        label="model (fitted)",
    )  # fmt: skip
    ax0.set_ylabel(f"SWR (z0 = {result.z0:g} Ω)")
    ax0.legend(loc="best", frameon=False, fontsize=8)
    _polish_axes(ax0, title=f"fit to {result.label!r}")

    ax1.plot(
        f, np.abs(result.gamma_nominal - result.gamma_measured),
        color="tab:orange", linestyle=":", marker="o", ms=3,
        label=f"nominal (RMS {result.rms_nominal:.4f})",
    )  # fmt: skip
    ax1.plot(
        f, np.abs(result.gamma_fitted - result.gamma_measured),
        color="tab:blue", marker="o", ms=3,
        label=f"fitted (RMS {result.rms_fitted:.4f})",
    )  # fmt: skip
    ax1.set_ylabel("residual |ΔΓ|")
    ax1.set_xlabel("freq (MHz)")
    ax1.set_ylim(bottom=0)
    ax1.legend(loc="best", frameon=False, fontsize=8)
    _polish_axes(ax1)

    fig.tight_layout()
    save_or_show(plt, fn)
