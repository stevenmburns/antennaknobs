import logging

from . import Antenna
from .core import save_or_show
from .far_field import get_elevation, get_pattern_rings, plot_patterns

import numpy as np

logger = logging.getLogger(__name__)

# NOTE: matplotlib.pyplot (and the smith_chart helpers built on it) are
# imported lazily inside the plotting functions below, not at module top.
# matplotlib is import-heavy (~0.1 s) and only needed when actually drawing —
# loading it here would tax every `import antennaknobs`, every CLI command,
# and web startup (which never plots) for a feature most runs never touch.

# Linestyles used to tell multi-port traces apart while keeping the
# red/blue axis-colour scheme of the twin-axis charts readable.
_PORT_LINESTYLES = ("-", "--", ":", "-.")


def _port_style(i):
    return _PORT_LINESTYLES[i % len(_PORT_LINESTYLES)]


def _param_label(nm):
    """Axis label for a swept knob; only freq has a unit we can know here."""
    return "freq (MHz)" if nm == "freq" else nm


def _z_title(antenna_builder, nm):
    """Title for an impedance sweep, naming the plane it is drawn at.

    "feedpoint" is only true for a bare antenna. A station design is solved
    at the port its source sits on — ``Driven(port="rig")`` — and with a
    measured trace on the same axes (#595) calling that the feedpoint
    actively invites comparing a VNA calibrated at the wrong plane (#652).
    """
    build = getattr(antenna_builder, "build_network", None)
    net = build() if callable(build) else None
    sources = getattr(net, "sources", None) if net is not None else None
    if sources:
        return f"impedance at {sources[0].port} vs {nm}"
    return f"feedpoint impedance vs {nm}"


def _polish_axes(ax, title=None):
    """Shared look-and-feel for the rectangular CLI charts."""
    ax.grid(True, alpha=0.3, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    if title is not None:
        ax.set_title(title, fontsize=11)


# A measured trace (issue #595) is drawn dashed with 'x' markers, against the
# solid 'o' of the modeled curve, in whatever colour the axis already uses —
# so the eye reads "same quantity, other source" rather than "another port".
_MEASURED_KW = dict(linestyle="--", marker="x", ms=4, linewidth=1.3, alpha=0.75)


def _align_measured(measured, nm, xs, z0):
    """``(xs, gamma)`` of a measured overlay on the sweep grid, or ``None``.

    Measured data is indexed by frequency, so it can only be overlaid on a
    frequency sweep; any other knob gets a clear error rather than a chart
    whose two traces share an axis by accident.
    """
    if measured is None:
        return None
    if nm != "freq":
        raise ValueError(
            f"a measured overlay is frequency data — it cannot be drawn against "
            f"a {nm!r} sweep; sweep --param freq to compare against it"
        )
    return measured.renormalized(z0).align(xs)


def _measured_legend(ax, label):
    """Legend keying the solid/dashed convention, drawn in neutral grey."""
    ax.plot([], [], color="0.35", linestyle="-", marker="o", ms=3, label="modeled")
    ax.plot([], [], color="0.35", label=label, **_MEASURED_KW)
    ax.legend(loc="best", frameon=False, fontsize=8)


_R_COLOR = "tab:red"
_X_COLOR = "tab:blue"


def _fmt_x(x):
    return f"{int(x)}" if float(x).is_integer() else f"{x:.4g}"


def _callout(ax, x, y, text, color, *, last, dx=None, stagger=0):
    """A SimNEC-style value box with an arrow to the point. The box goes to
    the point's right (first point) or left (``last``), and below a point in
    the upper half of the axis or above one in the lower half, so it stays
    inside the axes; X boxes sit further out than R boxes so the two do not
    stack when the curves cross. Call after the y limits are final.

    ``dx`` overrides that horizontal offset; ``stagger`` pushes the box a
    further box-height away from the point per step, so several engines'
    boxes at one end of an overlay stack instead of covering each other."""
    lo, hi = ax.get_ylim()
    upper = y > 0.5 * (lo + hi)
    if dx is None:
        dx = 60 if color == _X_COLOR else 12
    dy = (-30 - 26 * stagger) if upper else (16 + 26 * stagger)
    ax.annotate(
        text,
        xy=(x, y),
        xytext=(-dx if last else dx, dy),
        textcoords="offset points",
        ha="right" if last else "left",
        fontsize=7,
        color=color,
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=color, lw=0.6),
        arrowprops=dict(arrowstyle="->", color=color, lw=0.7),
    )


def _pivot(xs, log_x):
    """The middle of the x span: a callout right of it gets its box on the
    left, so first/last-point boxes both stay inside the axes."""
    lo, hi = float(np.min(xs)), float(np.max(xs))
    return float(np.sqrt(lo * hi)) if log_x and lo > 0 else 0.5 * (lo + hi)


def _annotate_rx(ax_r, ax_x, xs, zs, positions, xname, pivot):
    """Callouts on R (``ax_r``) and X (``ax_x``) at the given indices."""
    for k in positions:
        z = complex(zs[k])
        label = f"{xname}={_fmt_x(xs[k])}"
        last = xs[k] > pivot
        _callout(ax_r, xs[k], z.real, f"{label}\nR {z.real:.4g} Ω", _R_COLOR, last=last)
        _callout(ax_x, xs[k], z.imag, f"{label}\nX {z.imag:.4g} Ω", _X_COLOR, last=last)


def _log_x_axis(ax):
    """Log x with plain-number ticks at 1-2-5 per decade (10 20 50 100 200
    500), since matplotlib's default labels only the decades."""
    from matplotlib.ticker import LogLocator, NullFormatter, ScalarFormatter

    ax.set_xscale("log")
    ax.xaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.xaxis.set_minor_formatter(NullFormatter())


CALLOUT_MODES = ("ends", "markers", "all")


def _callout_mode(callouts):
    """``callouts`` as one of CALLOUT_MODES, or None for none. ``True`` (the
    bare flag) is ``"ends"``: the first and last points only."""
    if not callouts:
        return None
    if callouts is True:
        return "ends"
    if callouts not in CALLOUT_MODES:
        raise ValueError(f"callouts must be one of {CALLOUT_MODES}, got {callouts!r}")
    return callouts


def _callout_indices(mode, n, marked_idx):
    """Which of ``n`` points get a value box: ``ends`` the first and last,
    ``markers`` those plus every marked point, ``all`` every point."""
    if mode is None or n == 0:
        return []
    if mode == "all":
        return list(range(n))
    idx = {0, n - 1}
    if mode == "markers":
        idx |= set(marked_idx)
    return sorted(idx)


def _set_ylim(ax, rng):
    if rng is not None:
        ax.set_ylim(*rng)


def _rx_panels(
    panels,
    *,
    xlabel,
    title,
    log_x=False,
    r_range=None,
    x_range=None,
    callouts=False,
    xname=None,
):
    """R and X against a swept value, one panel per engine (Dan AC6LA's
    SimNEC layout, QRZ 1003328 #163): R in red on the LEFT axis and X in blue
    on a twin RIGHT axis, each auto-ranged on its own unless ``r_range`` /
    ``x_range`` pin it, circles at every point, and value boxes where
    ``callouts`` says (``_callout_indices``).

    ``panels`` is ``[(name, xs, zs, marked_idx, z_star), ...]``: ``zs`` one
    complex value per x (port 0), ``marked_idx`` the indices drawn as squares
    (``--markers``), ``z_star`` an optional Richardson estimate drawn as a
    dotted line on each axis. Returns the figure's ``[(ax_r, ax_x), ...]``.
    """
    import matplotlib.pyplot as plt

    n = len(panels)
    fig, axes = plt.subplots(1, n, figsize=(6.2 * n, 4.6), squeeze=False)
    out = []
    for ax0, (name, xs, zs, marked_idx, z_star) in zip(axes[0], panels, strict=True):
        xs = np.asarray(xs)
        zs = np.asarray(zs, dtype=complex)
        ax1 = ax0.twinx()
        style = dict(marker="o", ms=4, markerfacecolor="none", linewidth=1.3)
        ax0.plot(xs, zs.real, color=_R_COLOR, label="R", **style)
        ax1.plot(xs, zs.imag, color=_X_COLOR, label="X", **style)
        for k in marked_idx:
            for ax, v, c in ((ax0, zs[k].real, _R_COLOR), (ax1, zs[k].imag, _X_COLOR)):
                ax.plot(
                    [xs[k]],
                    [v],
                    marker="s",
                    ms=7,
                    markerfacecolor="none",
                    markeredgecolor=c,
                    linestyle="None",
                )
        if z_star is not None:
            ax0.axhline(z_star.real, color=_R_COLOR, linestyle=":", lw=1.0, alpha=0.7)
            ax1.axhline(z_star.imag, color=_X_COLOR, linestyle=":", lw=1.0, alpha=0.7)
        if log_x:
            _log_x_axis(ax0)
        ax0.set_xlabel(xlabel)
        ax0.set_ylabel("R (Ω)", color=_R_COLOR)
        ax0.tick_params(axis="y", labelcolor=_R_COLOR)
        ax1.set_ylabel("X (Ω)", color=_X_COLOR)
        ax1.tick_params(axis="y", labelcolor=_X_COLOR)
        # A narrow R range (72.00..72.15) otherwise reads as "+7.2e1" offsets.
        for ax in (ax0, ax1):
            ax.yaxis.get_major_formatter().set_useOffset(False)
        _set_ylim(ax0, r_range)
        _set_ylim(ax1, x_range)
        idx = _callout_indices(_callout_mode(callouts), len(xs), marked_idx)
        if idx:
            _annotate_rx(ax0, ax1, xs, zs, idx, xname or xlabel, _pivot(xs, log_x))
        panel_title = title if name is None else f"{name}: {title}"
        _polish_axes(ax0, title=panel_title)
        ax1.spines["top"].set_visible(False)
        out.append((ax0, ax1))
    fig.tight_layout()
    return out


def _spread(ys, gap, lo=0.04, hi=0.96):
    """Box centres (axes fraction) as close to their targets ``ys`` as they
    can be while at least ``gap`` apart and inside [lo, hi]. Returns them in
    the order given."""
    order = sorted(range(len(ys)), key=lambda k: ys[k])
    placed = []
    for k in order:
        y = min(max(ys[k], lo), hi)
        if placed and y < placed[-1] + gap:
            y = placed[-1] + gap
        placed.append(y)
    overflow = placed[-1] - hi if placed else 0.0
    if overflow > 0:
        placed = [max(lo, y - overflow) for y in placed]
        for n in range(1, len(placed)):
            placed[n] = max(placed[n], placed[n - 1] + gap)
    out = [0.0] * len(ys)
    for k, y in zip(order, placed, strict=True):
        out[k] = y
    return out


def _overlay_callouts(ax0, ax1, panels, mode, xname, log_x):
    """Value boxes for an overlay. Each engine's first and last points get
    ONE box (R and X together, in its colour), stacked in a column in a
    margin opened beyond the data on that side, ordered by the R value and
    spread so no two overlap; arrows run to the R point (solid) and the X
    point (dashed). ``markers`` / ``all`` points inside the range get
    ordinary staggered point callouts."""
    xs_all = np.concatenate([np.asarray(p[1], dtype=float) for p in panels])
    xmin, xmax = float(xs_all.min()), float(xs_all.max())
    # Open a margin of ~24 % of the axis width on each side for the columns.
    m = 0.24
    if log_x and xmin > 0:
        span = np.log10(xmax / xmin) or 1.0
        pad = 10 ** (span * m / (1 - 2 * m))
        ax0.set_xlim(xmin / pad, xmax * pad)
    else:
        span = (xmax - xmin) or 1.0
        pad = span * m / (1 - 2 * m)
        ax0.set_xlim(xmin - pad, xmax + pad)
    ax0.get_ylim()  # settle the lazy autoscale before reading transData
    to_frac = ax0.transAxes.inverted()
    gap = 0.1
    for last in (False, True):
        entries = []
        for i, (name, xs, zs, _marked, _z) in enumerate(panels):
            if len(xs) == 0:
                continue
            k = len(xs) - 1 if last else 0
            z = complex(zs[k])
            fy = to_frac.transform(ax0.transData.transform((xs[k], z.real)))[1]
            entries.append((i, name, xs[k], z, fy))
        ys = _spread([e[4] for e in entries], gap)
        for (i, name, x, z, _fy), by in zip(entries, ys, strict=True):
            color = f"C{i % 10}"
            box = (0.99, by) if last else (0.01, by)
            text = f"{name} {xname}={_fmt_x(x)}\nR {z.real:.4g}  X {z.imag:.4g} Ω"
            ax0.annotate(
                text,
                xy=(x, z.real),
                xytext=box,
                textcoords="axes fraction",
                ha="right" if last else "left",
                va="center",
                fontsize=6.5,
                color=color,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=color, lw=0.6),
                arrowprops=dict(arrowstyle="->", color=color, lw=0.6),
            )
            ax1.annotate(
                "",
                xy=(x, z.imag),
                xytext=box,
                textcoords="axes fraction",
                arrowprops=dict(arrowstyle="->", color=color, lw=0.6, ls="--"),
            )
    if mode == "ends":
        return
    pivot = _pivot(xs_all, log_x)
    for i, (name, xs, zs, marked_idx, _z) in enumerate(panels):
        color = f"C{i % 10}"
        inner = [
            k
            for k in _callout_indices(mode, len(xs), marked_idx)
            if 0 < k < len(xs) - 1
        ]
        for k in inner:
            z = complex(zs[k])
            head = f"{name} {xname}={_fmt_x(xs[k])}"
            last = xs[k] > pivot
            _callout(
                ax0,
                xs[k],
                z.real,
                f"{head}\nR {z.real:.4g} Ω",
                color,
                last=last,
                dx=12,
                stagger=i,
            )
            _callout(
                ax1,
                xs[k],
                z.imag,
                f"{head}\nX {z.imag:.4g} Ω",
                color,
                last=last,
                dx=90,
                stagger=i,
            )


# One marker per engine on an overlay, so the curves stay apart in a
# greyscale printout where the tab10 colours do not.
_OVERLAY_MARKERS = ("o", "s", "^", "D", "v", "P", "X", "<", ">", "h")


def _rx_overlay(
    panels,
    *,
    xlabel,
    title,
    log_x=False,
    r_range=None,
    x_range=None,
    callouts=False,
    xname=None,
):
    """Every engine of ``panels`` (the ``_rx_panels`` rows) on ONE chart: R
    on the left axis (solid) and X on a twin right axis (dashed), each axis
    shared by all engines, so its range is the union and the curves compare
    directly unless ``r_range`` / ``x_range`` pin it. Each engine has its own
    colour and marker; its Richardson ``z_star`` is a dotted line in its
    colour on each axis. Callouts label each engine's points (named), with
    one engine's boxes staggered past the previous one's. Returns
    ``(ax_r, ax_x)``."""
    import matplotlib.pyplot as plt

    fig, ax0 = plt.subplots(figsize=(9.0, 5.6))
    ax1 = ax0.twinx()
    handles = []
    for i, (name, xs, zs, marked_idx, z_star) in enumerate(panels):
        xs = np.asarray(xs)
        zs = np.asarray(zs, dtype=complex)
        color = f"C{i % 10}"
        mk = _OVERLAY_MARKERS[i % len(_OVERLAY_MARKERS)]
        style = dict(color=color, marker=mk, ms=4, markerfacecolor="none", lw=1.3)
        handles += ax0.plot(xs, zs.real, linestyle="-", label=f"{name} R", **style)
        handles += ax1.plot(xs, zs.imag, linestyle="--", label=f"{name} X", **style)
        for k in marked_idx:
            for ax, v in ((ax0, zs[k].real), (ax1, zs[k].imag)):
                ax.plot(
                    [xs[k]],
                    [v],
                    marker="s",
                    ms=8,
                    markerfacecolor="none",
                    markeredgecolor=color,
                    linestyle="None",
                )
        if z_star is not None:
            ax0.axhline(z_star.real, color=color, linestyle=":", lw=1.0, alpha=0.8)
            ax1.axhline(z_star.imag, color=color, linestyle=":", lw=1.0, alpha=0.8)
    if log_x:
        _log_x_axis(ax0)
    ax0.set_xlabel(xlabel)
    ax0.set_ylabel("R (Ω), solid")
    ax1.set_ylabel("X (Ω), dashed")
    for ax in (ax0, ax1):
        ax.yaxis.get_major_formatter().set_useOffset(False)
    _set_ylim(ax0, r_range)
    _set_ylim(ax1, x_range)
    mode = _callout_mode(callouts)
    if mode:
        _overlay_callouts(ax0, ax1, panels, mode, xname or xlabel, log_x)
    # Below the axes, one column per engine (its R above its X), so it
    # never sits on the curves or the callout columns.
    ax0.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        frameon=False,
        fontsize=7,
        ncol=len(panels),
    )
    _polish_axes(ax0, title=title)
    ax1.spines["top"].set_visible(False)
    fig.tight_layout()
    return ax0, ax1


def build_and_get_elevation(antenna_builder, *, engine=Antenna):
    a = engine(antenna_builder)
    return get_elevation(a)


def resolve_range(default_value, rng, center, fraction):
    if rng is None:
        if fraction is None:
            fraction = 1.25

        if center is None:
            center = default_value

        rng = (center / fraction, center * fraction)

    return rng


def _is_int_knob(value):
    return isinstance(value, (int, np.integer)) and not isinstance(value, bool)


def gen_xs(default_value, rng, center, fraction, npoints, log=False):
    """The swept values. Linear by default; ``log=True`` spaces them
    geometrically (a fixed step in log x, SimNEC's ``logStep``), and then an
    INTEGER knob — one whose default is an int, like a segment count — is
    rounded to ints and deduplicated, since rounding can collide two points
    at the coarse end. A linear sweep is left exactly as it always was."""
    rng = resolve_range(default_value, rng, center, fraction)
    if npoints == 1 and rng[0] < rng[1]:
        print(
            "Range includes more than just a point and npoints == 1. Using the lower range bound."
        )
    if not log:
        return np.linspace(rng[0], rng[1], npoints)
    if min(rng) <= 0:
        raise ValueError(
            f"--log needs a range above zero; got {rng[0]:g} .. {rng[1]:g}"
        )
    xs = np.geomspace(rng[0], rng[1], npoints)
    if _is_int_knob(default_value):
        xs = np.array(sorted({int(round(x)) for x in xs}))
    return xs


def sweep_swr(
    antenna_builder,
    nm="freq",
    *,
    z0=50,
    rng=None,
    center=None,
    fraction=None,
    npoints=21,
    fn=None,
    engine=Antenna,
    measured=None,
):
    """SWR + reflection magnitude against any swept knob.

    Sweeping `freq` uses the engine's vectorized impedance_sweep (one build,
    one matrix per frequency); any other knob changes the geometry, so the
    engine is rebuilt per point like the other parameter sweeps.

    `measured` is an optional `MeasuredTrace` (a VNA `.s1p`, issue #595) drawn
    as a second, dashed trace on both axes over the band it covers.
    """
    import matplotlib.pyplot as plt

    xs = gen_xs(getattr(antenna_builder, nm), rng, center, fraction, npoints)
    # Align before solving: a disjoint measured band should fail immediately,
    # not after a full sweep's worth of matrix solves.
    meas = _align_measured(measured, nm, xs, z0)

    if nm == "freq":
        a = engine(antenna_builder)
        zs = a.impedance_sweep(xs)
        del a
    else:
        zs = []
        for x in xs:
            setattr(antenna_builder, nm, x)
            zs.append(engine(antenna_builder).impedance())
        zs = np.array(zs)

    reflection_coefficient = (zs - z0) / (zs + z0)
    rho = np.abs(reflection_coefficient)
    swr = (1 + rho) / (1 - rho)

    rho_db = np.log10(rho) * 10.0

    fig, ax0 = plt.subplots(figsize=(7.0, 4.5))
    color = "tab:red"
    ax0.set_xlabel(_param_label(nm))
    ax0.set_ylabel("reflection 10·log₁₀|Γ| (dB)", color=color)
    ax0.tick_params(axis="y", labelcolor=color)
    for i in range(rho_db.shape[1]):
        ax0.plot(
            xs, rho_db[:, i], color=color, linestyle=_port_style(i), marker="o", ms=3
        )
    if meas is not None:
        mxs, mgamma = meas
        mrho = np.abs(mgamma)
        ax0.plot(mxs, np.log10(mrho) * 10.0, color=color, **_MEASURED_KW)

    color = "tab:blue"
    ax1 = ax0.twinx()
    ax1.set_ylabel("SWR", color=color)
    ax1.tick_params(axis="y", labelcolor=color)
    for i in range(swr.shape[1]):
        ax1.plot(xs, swr[:, i], color=color, linestyle=_port_style(i), marker="o", ms=3)
    if meas is not None:
        from .measured import RHO_MAX

        mrho_c = np.minimum(mrho, RHO_MAX)  # see MeasuredTrace.swr
        ax1.plot(mxs, (1.0 + mrho_c) / (1.0 - mrho_c), color=color, **_MEASURED_KW)
        _measured_legend(ax0, measured.label)

    _polish_axes(ax0, title=f"SWR vs {nm} (z0 = {z0:g} Ω)")
    ax1.spines["top"].set_visible(False)
    fig.tight_layout()

    save_or_show(plt, fn)


def sweep_freq(antenna_builder, **kwargs):
    """Backwards-compatible alias: the SWR chart swept over frequency."""
    sweep_swr(antenna_builder, "freq", **kwargs)


def sweep_patterns(
    antenna_builder,
    nm,
    *,
    rng=None,
    center=None,
    fraction=None,
    npoints=3,
    fn=None,
    elevation_angle=15,
    azimuth_f=0,
    azimuth_r=180,
    engine=Antenna,
):

    xs = gen_xs(getattr(antenna_builder, nm), rng, center, fraction, npoints)

    rings_lst = []

    for x in xs:
        setattr(antenna_builder, nm, x)
        rings, max_gain, min_gain, thetas, phis = get_pattern_rings(
            engine(antenna_builder)
        )
        rings_lst.append(rings)

    plot_patterns(
        rings_lst,
        (f"{x:.3f}" for x in xs),
        thetas,
        phis,
        fn=fn,
        elevation_angle=elevation_angle,
        azimuth_f=azimuth_f,
        azimuth_r=azimuth_r,
    )


def sweep_gain(
    antenna_builder,
    nm,
    *,
    rng=None,
    center=None,
    fraction=None,
    npoints=21,
    fn=None,
    engine=Antenna,
):
    import matplotlib.pyplot as plt

    xs = gen_xs(getattr(antenna_builder, nm), rng, center, fraction, npoints)

    gs = []
    for x in xs:
        setattr(antenna_builder, nm, x)
        _, max_gain, _, _, _ = build_and_get_elevation(antenna_builder, engine=engine)
        gs.append(max_gain)

    gs = np.array(gs)

    fig, ax0 = plt.subplots(figsize=(7.0, 4.5))
    color = "tab:red"
    ax0.set_xlabel(_param_label(nm))
    ax0.set_ylabel("max gain (dBi)", color=color)
    ax0.tick_params(axis="y", labelcolor=color)
    ax0.plot(xs, gs, color=color, marker="o", ms=3)

    _polish_axes(ax0, title=f"max gain vs {nm}")
    fig.tight_layout()

    save_or_show(plt, fn)


def ladder_estimate(rungs):
    """First-order Richardson from a refinement ladder's last two rungs.

    ``rungs`` is [(refinement factor, Z), ...] in ascending factor order. Returns
    ``(Z_inf, shrinking)``, or None with fewer than two rungs. ``Z_inf`` is
    Z_hi + (Z_hi - Z_lo) / (r_hi / r_lo - 1), the first-order extrapolation in
    the segment length. ``shrinking`` is False when the ladder has three or more
    rungs and the last step is no smaller than the one before it. That means the
    ladder is not yet in its asymptotic range and the extrapolation should not
    be trusted. With two rungs there is nothing to compare, so it is True.

    Shared by the CLI ``ladder`` subcommand (a card deck's own GW refinement)
    and ``sweep --param nominal_nsegs`` (#1554, a catalog design's density
    ladder) — the extrapolation is the same math over either refinement
    axis, so it lives once, next to the convergence-sweep code that is its
    other caller.
    """
    if len(rungs) < 2:
        return None
    (r_lo, z_lo), (r_hi, z_hi) = rungs[-2], rungs[-1]
    z_inf = z_hi + (z_hi - z_lo) / (r_hi / r_lo - 1)
    shrinking = True
    if len(rungs) >= 3:
        prev_step = abs(rungs[-2][1] - rungs[-3][1])
        last_step = abs(z_hi - z_lo)
        shrinking = last_step < prev_step
    return z_inf, shrinking


# The app's own convergence ladder (`CONVERGE_N_VALUES`,
# useAnalysisRunners.ts). A CLI study run with no --range reproduces exactly
# the rungs the UI's convergence overlay solves, so a number quoted from
# either side is the same measurement (#1554).
NOMINAL_NSEGS_LADDER = (8, 12, 17, 24, 34, 48, 68)


def _nominal_nsegs_rungs(rng, npoints):
    """Integer ``nominal_nsegs`` rungs for a convergence sweep (#1554).

    Neither ``--range`` nor ``--npoints``: the app's own ladder, above.
    ``npoints`` is None when the flag was not given (the CLI's ``sweep``
    parser leaves it unset so this study can tell). A ``--range lo hi`` is
    spaced geometrically instead of linearly — a fixed step in log N puts
    every rung at the same relative mesh refinement, which is what a
    convergence study is supposed to sample — then rounded to ints,
    deduplicated and sorted ascending, since rounding can collide two
    rungs at a narrow range or a large ``--npoints``.
    """
    if rng is None and npoints is None:
        return list(NOMINAL_NSEGS_LADDER)
    # Either flag alone spans the other's default: `--npoints k` walks the
    # app ladder's own 8..68 in k geometric steps, and `--range lo hi` alone
    # takes the ladder's seven rungs rather than the frequency sweep's 21.
    lo, hi = (
        rng if rng is not None else (NOMINAL_NSEGS_LADDER[0], NOMINAL_NSEGS_LADDER[-1])
    )
    n = max(int(npoints), 2) if npoints is not None else len(NOMINAL_NSEGS_LADDER)
    return sorted({int(round(x)) for x in np.geomspace(lo, hi, n)})


def _achieved_n(eng, builder):
    """Total segments THIS engine actually meshed at one rung (#1554).

    Read from the coerced wire list — the same private seam
    ``SimulationEngine.fed_segments`` itself falls back to for an
    end-ported wire, and the one ``scratch/1525-razor-density/run_density.py``
    calls ``built_segs`` — rather than ``fed_segments()``'s own count, which
    is the fed EDGE alone. A house dipole's fed edge is one to a handful of
    segments almost regardless of the ladder rung (the gap wire is short),
    so it never tracks the density knob; the mesh total does, and it is
    what shows the parity rounding: an odd-parity engine (bspline, the
    framework default) and an even-parity engine (razor-2p, nec5) round the
    same nominal count to totals one segment apart.
    """
    from .network import as_wire
    from .wire_catalog import GradedSegments

    coerced = eng._coerce_wire_tuples(builder.build_wires())
    total = 0
    for t in coerced:
        n_seg = as_wire(t).n_seg
        total += sum(n_seg.counts) if isinstance(n_seg, GradedSegments) else int(n_seg)
    return total


def _reflection(z, z0):
    return (z - z0) / (z + z0)


def _print_convergence_table(
    per_engine, estimates, z0, marked=frozenset(), ground_label=None
):
    """The stdout table for ``sweep --param nominal_nsegs`` (#1554): grouped
    per engine so a single-engine study reads like a plain ladder printout,
    and a multi-engine one reads as N of those back to back. ΔΓ is against
    that engine's own FINEST rung (issue #1525's ladder metric — the density
    records are judged on ΔΓ against the finest rung, not against Z* itself,
    since Z* is itself only an estimate)."""
    for name, rows in per_engine.items():
        print(f"== nominal_nsegs convergence: {name} ==")
        if ground_label is not None:
            # Every engine of a CLI study runs on the SAME ground (AK#1563);
            # it is printed under each header so a table pasted on its own
            # still says which physics the numbers are.
            print(f"ground: {ground_label}")
        print(f"{'nominal_N':>9} {'N_ach':>6} {'R (Ω)':>9} {'X (Ω)':>9} {'|ΔΓ|':>9}")
        finest_gamma = _reflection(rows[-1][2], z0)
        for nominal_n, achieved_n, z in rows:
            dgamma = abs(_reflection(z, z0) - finest_gamma)
            star = " *" if nominal_n in marked else ""
            print(
                f"{nominal_n:>9} {achieved_n:>6} {z.real:>9.3f} {z.imag:>+9.3f} "
                f"{dgamma:>9.4f}{star}"
            )
        if marked:
            print("  * = a --markers rung")
        z_star, shrinking = estimates[name]
        if z_star is None:
            print(f"{name}  Z* unavailable (need >= 2 rungs)")
        else:
            verdict = "yes" if shrinking else "no"
            print(
                f"{name}  Z* = {z_star.real:.3f}{z_star.imag:+.3f}j  "
                f"(shrinking: {verdict})"
            )


def _sweep_convergence(
    antenna_builder,
    engines,
    *,
    rng,
    npoints,
    use_smithchart,
    z0,
    fn,
    markers=(),
    ground_label=None,
    r_range=None,
    x_range=None,
    callouts=False,
    overlay=False,
):
    """``sweep --param nominal_nsegs`` (#1554): one cold solve per rung per
    engine, port 0 only (multi-port trajectories are the app's own overlay,
    out of scope here — see the title note when a design has more than one).

    ``engines`` is ``[(name, factory), ...]``. The density wrapper from
    #1543 must already have stood down in the caller (``mesh_density=False``
    in ``cli.engine_factories_from_args``) — this function is the one thing
    allowed to move ``antenna_builder.nominal_nsegs`` for the duration.
    """
    import matplotlib.pyplot as plt

    # `--markers` on a density study are rungs at exactly the densities named
    # (the served 15 / 16 / 20, say): solved like any rung, starred in the
    # table and squared on the chart. Beside a ladder (--range / --npoints, or
    # the default one) they are observations only, not rungs of the Richardson
    # estimate (see `estimates` below); alone, they are the whole ladder.
    marked = {int(round(m)) for m in markers}
    if marked and rng is None and npoints is None:
        # `--markers` alone IS the ladder: "just these densities". Richardson
        # then reads them as its rungs, since they are the only rungs.
        ladder_rungs = set(marked)
        # ...and then they are not observations beside it: no squares, and
        # callouts treat the rungs as ordinary points, so a 20-rung
        # --markers ladder with --callouts gets its two end boxes, not 20.
        drawn_marks = set()
    else:
        drawn_marks = marked
        ladder_rungs = set(_nominal_nsegs_rungs(rng, npoints))
    rungs = sorted(ladder_rungs | marked)

    per_engine = {}
    nports = 1
    for name, factory in engines:
        rows = []
        for n in rungs:
            antenna_builder.nominal_nsegs = n
            eng = factory(antenna_builder)
            z = eng.impedance()
            nports = max(nports, len(z))
            rows.append((n, _achieved_n(eng, antenna_builder), complex(z[0])))
        per_engine[name] = rows

    # Richardson reads the GEOMETRIC ladder only: a marker dropped between two
    # rungs would shrink one step and grow the next, and the "shrinking"
    # verdict compares adjacent steps. Markers are observations on the
    # trajectory, not rungs of the extrapolation.
    estimates = {
        name: ladder_estimate(
            [(achieved, z) for n, achieved, z in rows if n in ladder_rungs]
        )
        or (None, None)
        for name, rows in per_engine.items()
    }

    _print_convergence_table(
        per_engine, estimates, z0, marked=marked, ground_label=ground_label
    )

    title = "impedance vs nominal_nsegs, Richardson Z*"
    if nports > 1:
        title += f" (port 0 of {nports})"

    if use_smithchart:
        from .smith_chart import draw_smith_chart, plot_reflection

        fig, ax0 = plt.subplots(figsize=(6.8, 6.8))
        draw_smith_chart(ax0, z0=z0)
        for i, (name, rows) in enumerate(per_engine.items()):
            color = f"C{i}"
            zs = np.array([z for _, _, z in rows])
            gamma = _reflection(zs, z0)
            plot_reflection(
                ax0, gamma, color=color, marker="o", ms=3, linewidth=1.4, label=name
            )
            # Coarsest rung: hollow ring. Finest: filled disc. Matches
            # SmithChart.tsx's convergence overlay conventions.
            ax0.plot(
                [gamma[0].real],
                [gamma[0].imag],
                marker="o",
                ms=7,
                markerfacecolor="none",
                markeredgecolor=color,
                linestyle="None",
            )
            ax0.plot(
                [gamma[-1].real],
                [gamma[-1].imag],
                marker="o",
                ms=7,
                markerfacecolor=color,
                markeredgecolor=color,
                linestyle="None",
            )
            for k, (nominal_n, _achieved, _z) in enumerate(rows):
                if nominal_n in marked:
                    ax0.plot(
                        [gamma[k].real],
                        [gamma[k].imag],
                        marker="s",
                        ms=6,
                        markerfacecolor="none",
                        markeredgecolor=color,
                        linestyle="None",
                    )
            z_star, _shrinking = estimates[name]
            if z_star is not None:
                g = _reflection(z_star, z0)
                # Clip to the unit disc: an early-ladder Richardson estimate
                # can fly past |Γ|=1, same as the app's drawing does.
                mag = abs(g)
                if mag > 0.98:
                    g = g * (0.98 / mag)
                ax0.plot(
                    [g.real], [g.imag], marker="D", ms=8, color=color, linestyle="None"
                )
        ax0.legend(loc="upper left", frameon=False, fontsize=8)
        ax0.set_title(title, fontsize=11)
        fig.tight_layout()
    else:
        # One twin-axis panel per engine (R left, X right, each auto-ranged):
        # on a shared Ω axis a ~70 Ω R flattened a few-ohm X into a line.
        panels = []
        for name, rows in per_engine.items():
            panels.append(
                (
                    name,
                    [achieved for _, achieved, _ in rows],
                    [z for _, _, z in rows],
                    [k for k, (n, _, _) in enumerate(rows) if n in drawn_marks],
                    estimates[name][0],
                )
            )
        (_rx_overlay if overlay else _rx_panels)(
            panels,
            xlabel="segments achieved (log)",
            title=title,
            log_x=True,
            r_range=r_range,
            x_range=x_range,
            callouts=callouts,
            xname="N",
        )

    save_or_show(plt, fn)


def sweep(
    antenna_builder,
    nm,
    *,
    rng=None,
    center=None,
    fraction=None,
    npoints=21,
    use_smithchart=False,
    z0=50,
    markers=[],
    fn=None,
    engine=Antenna,
    measured=None,
    ground_label=None,
    log=False,
    r_range=None,
    x_range=None,
    callouts=False,
    panels=False,
    overlay=False,
):
    """Impedance against a swept knob (or frequency).

    The keyword-only chart options (Dan AC6LA's SimNEC charts, QRZ 1003328
    #163) all default off, and leave the chart exactly as it was when off:

    - ``log``: geometric spacing and a log x axis; an int knob's points are
      rounded to ints (``gen_xs``).
    - ``r_range`` / ``x_range``: pin the R (left) / X (right) axis.
    - ``callouts``: value boxes, ``"ends"`` (or ``True``) at the first and
      last points, ``"markers"`` also at every ``markers`` point, ``"all"``
      at every point.
    - ``panels``: several engines drawn one twin-axis R/X panel each (port 0),
      instead of one shared-axis chart coloured by engine.
    - ``overlay``: several engines on ONE twin-axis R/X chart (port 0), each
      axis shared, one colour and marker per engine (``_rx_overlay``).

    ``nominal_nsegs`` is always log-spaced, and drawn as panels unless
    ``overlay``.
    """
    import matplotlib.pyplot as plt

    engines = list(engine.items()) if isinstance(engine, dict) else [(None, engine)]

    if nm == "nominal_nsegs":
        # A first-class case (#1554): int rungs, not gen_xs's float linspace,
        # and a fundamentally different table/chart — factored out entirely
        # rather than threaded through the branches below.
        _sweep_convergence(
            antenna_builder,
            engines,
            rng=rng,
            npoints=npoints,
            use_smithchart=use_smithchart,
            z0=z0,
            fn=fn,
            markers=markers,
            ground_label=ground_label,
            r_range=r_range,
            x_range=x_range,
            callouts=callouts,
            overlay=overlay,
        )
        return

    if npoints is None:
        npoints = 21
    xs = gen_xs(getattr(antenna_builder, nm), rng, center, fraction, npoints, log=log)
    # Align first so a disjoint measured band errors before any solving.
    meas = _align_measured(measured, nm, xs, z0)

    if len(engines) == 1 and engines[0][0] is None:
        # The pre-#1554 single-engine path, UNCHANGED — pinned byte-identical
        # by test_cli_sweep_single_engine_output_is_unchanged (#1554).
        engine = engines[0][1]

        zs = []
        for x in xs:
            setattr(antenna_builder, nm, x)
            zs.append(engine(antenna_builder).impedance())

        marker_zs = []
        for x in markers:
            setattr(antenna_builder, nm, x)
            marker_zs.append(engine(antenna_builder).impedance())

        zs = np.array(zs)
        marker_xs = np.array(markers)
        marker_zs = np.array(marker_zs)

        nwidth = zs.shape[1] if npoints > 0 else marker_zs.shape[1]
        logger.debug(
            "smith sweep: nwidth=%s npoints=%s markers=%s zs.shape=%s marker_zs.shape=%s",
            nwidth,
            npoints,
            markers,
            zs.shape,
            marker_zs.shape,
        )

        if use_smithchart:
            # Lazy import (see the note at the top of the module): our own
            # matplotlib renderer — scikit-rf was dropped in #332.
            from .smith_chart import draw_smith_chart, plot_reflection

            fig, ax0 = plt.subplots(figsize=(6.8, 6.8))
            draw_smith_chart(ax0, z0=z0)
            for i in range(nwidth):
                color = f"C{i}"
                if nwidth > 1:
                    label = f"port {i + 1}"
                else:
                    label = "modeled" if meas is not None else None
                if zs.shape[0] > 0:
                    gamma = (zs[:, i] - z0) / (zs[:, i] + z0)
                    plot_reflection(ax0, gamma, color=color, linewidth=1.8, label=label)
                    label = None
                if marker_zs.shape[0] > 0:
                    gamma = (marker_zs[:, i] - z0) / (marker_zs[:, i] + z0)
                    plot_reflection(
                        ax0,
                        gamma,
                        color=color,
                        marker="s",
                        ms=6,
                        linestyle="None",
                        label=label,
                    )
            if meas is not None:
                plot_reflection(
                    ax0,
                    meas[1],
                    color="0.25",
                    label=measured.label,
                    **_MEASURED_KW,
                )
            if nwidth > 1 or meas is not None:
                # Upper left keeps clear of the z0 note in the lower-left corner.
                ax0.legend(loc="upper left", frameon=False, fontsize=8)
            # Same title as the rectangular branch — the chart form says "Smith".
            ax0.set_title(_z_title(antenna_builder, nm), fontsize=11)
            fig.tight_layout()

        else:
            fig, ax0 = plt.subplots(figsize=(7.0, 4.5))
            color = "tab:red"
            ax0.set_xlabel(_param_label(nm))
            ax0.set_ylabel("resistance R (Ω)", color=color)
            ax0.tick_params(axis="y", labelcolor=color)
            for i in range(nwidth):
                if zs.shape[0] > 0:
                    ax0.plot(
                        xs,
                        np.real(zs)[:, i],
                        color=color,
                        linestyle=_port_style(i),
                        marker="o",
                        ms=3,
                    )
                if marker_zs.shape[0] > 0:
                    ax0.plot(
                        marker_xs,
                        np.real(marker_zs)[:, i],
                        color=color,
                        marker="s",
                        linestyle="None",
                    )
            if meas is not None:
                mxs, mz = meas[0], z0 * (1.0 + meas[1]) / (1.0 - meas[1])
                ax0.plot(mxs, np.real(mz), color=color, **_MEASURED_KW)

            color = "tab:blue"
            ax1 = ax0.twinx()
            ax1.set_ylabel("reactance X (Ω)", color=color)
            ax1.tick_params(axis="y", labelcolor=color)
            for i in range(nwidth):
                if zs.shape[0] > 0:
                    ax1.plot(
                        xs,
                        np.imag(zs)[:, i],
                        color=color,
                        linestyle=_port_style(i),
                        marker="o",
                        ms=3,
                    )
                if marker_zs.shape[0] > 0:
                    ax1.plot(
                        marker_xs,
                        np.imag(marker_zs)[:, i],
                        color=color,
                        marker="s",
                        linestyle="None",
                    )
            if meas is not None:
                ax1.plot(mxs, np.imag(mz), color=color, **_MEASURED_KW)
                _measured_legend(ax0, measured.label)

            if log:
                _log_x_axis(ax0)
            _set_ylim(ax0, r_range)
            _set_ylim(ax1, x_range)
            mode = _callout_mode(callouts)
            if mode:
                pivot = _pivot(np.concatenate([xs, marker_xs]), log)
                for i in range(nwidth):
                    if zs.shape[0] > 0:
                        idx = _callout_indices(mode, zs.shape[0], ())
                        _annotate_rx(ax0, ax1, xs, zs[:, i], idx, nm, pivot)
                    if marker_zs.shape[0] > 0 and mode != "ends":
                        _annotate_rx(
                            ax0,
                            ax1,
                            marker_xs,
                            marker_zs[:, i],
                            range(marker_zs.shape[0]),
                            nm,
                            pivot,
                        )
            _polish_axes(ax0, title=_z_title(antenna_builder, nm))
            ax1.spines["top"].set_visible(False)
            fig.tight_layout()

        save_or_show(plt, fn)
        return

    # Multi-engine path (#1554): same xs, one trajectory/line per engine.
    # Colour now keys the ENGINE (one axis, not the twin-axis red/blue
    # R/X split the single-engine rectangular chart uses) — R solid, X
    # dashed, so a port still reads within an engine via `_port_style`.
    per_engine = []
    for name, factory in engines:
        zs = []
        for x in xs:
            setattr(antenna_builder, nm, x)
            zs.append(factory(antenna_builder).impedance())
        marker_zs = []
        for x in markers:
            setattr(antenna_builder, nm, x)
            marker_zs.append(factory(antenna_builder).impedance())
        per_engine.append((name, np.array(zs), np.array(marker_zs)))

    marker_xs = np.array(markers)
    nwidth = 1
    for _name, zs, marker_zs in per_engine:
        if zs.shape[0] > 0:
            nwidth = zs.shape[1]
            break
        if marker_zs.shape[0] > 0:
            nwidth = marker_zs.shape[1]
            break

    if (panels or overlay) and not use_smithchart:
        # One twin-axis panel per engine, port 0. Markers join each engine's
        # points (sorted into place) so a panel is one R and one X line.
        rows = []
        for name, zs, marker_zs in per_engine:
            px = list(xs) + list(marker_xs)
            pz = list(zs[:, 0] if zs.shape[0] else []) + list(
                marker_zs[:, 0] if marker_zs.shape[0] else []
            )
            order = np.argsort(px, kind="stable")
            px = np.asarray(px)[order]
            pz = np.asarray(pz, dtype=complex)[order]
            marked = [k for k, j in enumerate(order) if j >= len(xs)]
            rows.append((name, px, pz, marked, None))
        title = _z_title(antenna_builder, nm)
        if nwidth > 1:
            title += f" (port 1 of {nwidth})"
        (_rx_overlay if overlay else _rx_panels)(
            rows,
            xlabel=_param_label(nm),
            title=title,
            log_x=log,
            r_range=r_range,
            x_range=x_range,
            callouts=callouts,
            xname=nm,
        )

    elif use_smithchart:
        from .smith_chart import draw_smith_chart, plot_reflection

        fig, ax0 = plt.subplots(figsize=(6.8, 6.8))
        draw_smith_chart(ax0, z0=z0)
        for ei, (name, zs, marker_zs) in enumerate(per_engine):
            color = f"C{ei}"
            for i in range(nwidth):
                label = f"{name} port {i + 1}" if nwidth > 1 else name
                if zs.shape[0] > 0:
                    gamma = (zs[:, i] - z0) / (zs[:, i] + z0)
                    plot_reflection(
                        ax0,
                        gamma,
                        color=color,
                        linewidth=1.8,
                        linestyle=_port_style(i),
                        label=label,
                    )
                    label = None
                if marker_zs.shape[0] > 0:
                    gamma = (marker_zs[:, i] - z0) / (marker_zs[:, i] + z0)
                    plot_reflection(
                        ax0,
                        gamma,
                        color=color,
                        marker="s",
                        ms=6,
                        linestyle="None",
                        label=label,
                    )
        if meas is not None:
            plot_reflection(
                ax0, meas[1], color="0.25", label=measured.label, **_MEASURED_KW
            )
        ax0.legend(loc="upper left", frameon=False, fontsize=8)
        ax0.set_title(_z_title(antenna_builder, nm), fontsize=11)
        fig.tight_layout()

    else:
        fig, ax0 = plt.subplots(figsize=(7.0, 4.5))
        ax0.set_xlabel(_param_label(nm))
        ax0.set_ylabel("R solid / X dashed (Ω)")
        for ei, (name, zs, marker_zs) in enumerate(per_engine):
            color = f"C{ei}"
            for i in range(nwidth):
                label = f"{name} port {i + 1}" if nwidth > 1 else name
                if zs.shape[0] > 0:
                    ax0.plot(
                        xs,
                        np.real(zs)[:, i],
                        color=color,
                        linestyle=_port_style(i),
                        marker="o",
                        ms=3,
                        label=label,
                    )
                    ax0.plot(
                        xs,
                        np.imag(zs)[:, i],
                        color=color,
                        linestyle="--",
                        marker="^",
                        ms=3,
                    )
                if marker_zs.shape[0] > 0:
                    ax0.plot(
                        marker_xs,
                        np.real(marker_zs)[:, i],
                        color=color,
                        marker="s",
                        linestyle="None",
                    )
                    ax0.plot(
                        marker_xs,
                        np.imag(marker_zs)[:, i],
                        color=color,
                        marker="s",
                        linestyle="None",
                    )
        if meas is not None:
            mxs, mz = meas[0], z0 * (1.0 + meas[1]) / (1.0 - meas[1])
            ax0.plot(mxs, np.real(mz), color="0.25", **_MEASURED_KW)
            _measured_legend(ax0, measured.label)

        if log:
            _log_x_axis(ax0)
        _polish_axes(ax0, title=_z_title(antenna_builder, nm))
        ax0.legend(loc="best", frameon=False, fontsize=8)
        fig.tight_layout()

    save_or_show(plt, fn)
