import logging

from . import Antenna
from .core import save_or_show
from .far_field import get_elevation, get_pattern_rings, plot_patterns
from .zinf import describe, describe_feed_mesh, feed_mesh_step, zinf_estimate

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
    """Callouts on R (``ax_r``) and X (``ax_x``) at the given indices. An
    axis passed as None (``--only``) gets none; the one left drawn keeps its
    boxes close in, since there is no second box to step around."""
    dx = 12 if ax_r is None or ax_x is None else None
    for k in positions:
        z = complex(zs[k])
        label = f"{xname}={_fmt_x(xs[k])}"
        last = xs[k] > pivot
        if ax_r is not None:
            text = f"{label}\nR {z.real:.4g} Ω"
            _callout(ax_r, xs[k], z.real, text, _R_COLOR, last=last, dx=dx)
        if ax_x is not None:
            text = f"{label}\nX {z.imag:.4g} Ω"
            _callout(ax_x, xs[k], z.imag, text, _X_COLOR, last=last, dx=dx)


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
    if ax is not None and rng is not None:
        ax.set_ylim(*rng)


ONLY_CHOICES = ("r", "x")


def _only_parts(only):
    """``(show_r, show_x)`` for ``only`` (None, ``"r"`` or ``"x"``)."""
    if only is None:
        return True, True
    if only not in ONLY_CHOICES:
        raise ValueError(f"only must be one of {ONLY_CHOICES} or None, got {only!r}")
    return only == "r", only == "x"


def _rx_axes(ax0, only):
    """``(ax_r, ax_x)`` on ``ax0``: R on it and X on a twin right axis, or,
    with ``only``, the one quantity on ``ax0`` itself and None for the
    other (no twin is made)."""
    show_r, show_x = _only_parts(only)
    if show_r and show_x:
        return ax0, ax0.twinx()
    return (ax0, None) if show_r else (None, ax0)


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
    only=None,
):
    """R and X against a swept value, one panel per engine (Dan AC6LA's
    SimNEC layout, QRZ 1003328 #163): R in red on the LEFT axis and X in blue
    on a twin RIGHT axis, each auto-ranged on its own unless ``r_range`` /
    ``x_range`` pin it, circles at every point, and value boxes where
    ``callouts`` says (``_callout_indices``).

    ``panels`` is ``[(name, xs, zs, marked_idx, z_star), ...]``: ``zs`` one
    complex value per x (port 0), ``marked_idx`` the indices drawn as squares
    (``--markers``), ``z_star`` an optional Richardson estimate drawn as a
    dotted line on each axis. ``only`` (``"r"`` / ``"x"``) draws that one
    quantity on a single axis, no twin. Returns the figure's
    ``[(ax_r, ax_x), ...]``, None for an axis ``only`` leaves out.
    """
    import matplotlib.pyplot as plt

    n = len(panels)
    fig, axes = plt.subplots(1, n, figsize=(6.2 * n, 4.6), squeeze=False)
    out = []
    for ax0, (name, xs, zs, marked_idx, z_star) in zip(axes[0], panels, strict=True):
        xs = np.asarray(xs)
        zs = np.asarray(zs, dtype=complex)
        ax_r, ax_x = _rx_axes(ax0, only)
        parts = [
            (ax, vals, c, lab)
            for ax, vals, c, lab in (
                (ax_r, zs.real, _R_COLOR, "R"),
                (ax_x, zs.imag, _X_COLOR, "X"),
            )
            if ax is not None
        ]
        style = dict(marker="o", ms=4, markerfacecolor="none", linewidth=1.3)
        for ax, vals, c, lab in parts:
            ax.plot(xs, vals, color=c, label=lab, **style)
        for k in marked_idx:
            for ax, vals, c, _lab in parts:
                ax.plot(
                    [xs[k]],
                    [vals[k]],
                    marker="s",
                    ms=7,
                    markerfacecolor="none",
                    markeredgecolor=c,
                    linestyle="None",
                )
        if z_star is not None:
            star = {"R": z_star.real, "X": z_star.imag}
            for ax, _vals, c, lab in parts:
                ax.axhline(star[lab], color=c, linestyle=":", lw=1.0, alpha=0.7)
        if log_x:
            _log_x_axis(ax0)
        ax0.set_xlabel(xlabel)
        for ax, _vals, c, lab in parts:
            ax.set_ylabel(f"{lab} (Ω)", color=c)
            ax.tick_params(axis="y", labelcolor=c)
            # A narrow R range (72.00..72.15) otherwise reads as "+7.2e1".
            ax.yaxis.get_major_formatter().set_useOffset(False)
        _set_ylim(ax_r, r_range)
        _set_ylim(ax_x, x_range)
        idx = _callout_indices(_callout_mode(callouts), len(xs), marked_idx)
        if idx:
            _annotate_rx(ax_r, ax_x, xs, zs, idx, xname or xlabel, _pivot(xs, log_x))
        panel_title = title if name is None else f"{name}: {title}"
        _polish_axes(ax0, title=panel_title)
        if ax_x is not None:
            ax_x.spines["top"].set_visible(False)
        out.append((ax_r, ax_x))
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


def _overlay_callouts(ax_r, ax_x, panels, mode, xname, log_x):
    """Value boxes for an overlay. Each engine's first and last points get
    ONE box (R and X together, in its colour), stacked in a column in a
    margin opened beyond the data on that side, ordered by the R value and
    spread so no two overlap; arrows run to the R point (solid) and the X
    point (dashed). ``markers`` / ``all`` points inside the range get
    ordinary staggered point callouts. An axis passed as None (``--only``)
    is left out of the boxes and arrows, and the column orders by the one
    quantity drawn."""
    ax0 = ax_r if ax_r is not None else ax_x
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
            y0 = z.real if ax0 is ax_r else z.imag
            fy = to_frac.transform(ax0.transData.transform((xs[k], y0)))[1]
            entries.append((i, name, xs[k], z, fy))
        ys = _spread([e[4] for e in entries], gap)
        for (i, name, x, z, _fy), by in zip(entries, ys, strict=True):
            color = f"C{i % 10}"
            box = (0.99, by) if last else (0.01, by)
            values = []
            if ax_r is not None:
                values.append(f"R {z.real:.4g}")
            if ax_x is not None:
                values.append(f"X {z.imag:.4g}")
            text = f"{name} {xname}={_fmt_x(x)}\n{'  '.join(values)} Ω"
            ax0.annotate(
                text,
                xy=(x, z.real if ax0 is ax_r else z.imag),
                xytext=box,
                textcoords="axes fraction",
                ha="right" if last else "left",
                va="center",
                fontsize=6.5,
                color=color,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=color, lw=0.6),
                arrowprops=dict(
                    arrowstyle="->",
                    color=color,
                    lw=0.6,
                    **({} if ax0 is ax_r else {"ls": "--"}),
                ),
            )
            if ax_r is not None and ax_x is not None:
                ax_x.annotate(
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
            if ax_r is not None:
                _callout(
                    ax_r,
                    xs[k],
                    z.real,
                    f"{head}\nR {z.real:.4g} Ω",
                    color,
                    last=last,
                    dx=12,
                    stagger=i,
                )
            if ax_x is not None:
                _callout(
                    ax_x,
                    xs[k],
                    z.imag,
                    f"{head}\nX {z.imag:.4g} Ω",
                    color,
                    last=last,
                    dx=90 if ax_r is not None else 12,
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
    only=None,
    refused=(),
):
    """Every engine of ``panels`` (the ``_rx_panels`` rows) on ONE chart: R
    on the left axis (solid) and X on a twin right axis (dashed), each axis
    shared by all engines, so its range is the union and the curves compare
    directly unless ``r_range`` / ``x_range`` pin it. Each engine has its own
    colour and marker; its Richardson ``z_star`` is a dotted line in its
    colour on each axis. Callouts label each engine's points (named), with
    one engine's boxes staggered past the previous one's. ``only``
    (``"r"`` / ``"x"``) draws that one quantity on a single axis, no twin,
    keeping its line style. Returns ``(ax_r, ax_x)``, None for an axis
    ``only`` leaves out.

    A row's name is any label: an engine, a ground, or both (an analysis
    crossed with grounds, AK#1757). ``refused`` names curves that were asked
    for and could not be served: each is a legend entry with no line, so the
    gap is named where the curve would have been."""
    import matplotlib.pyplot as plt

    fig, ax0 = plt.subplots(figsize=(9.0, 5.6))
    ax_r, ax_x = _rx_axes(ax0, only)
    both = ax_r is not None and ax_x is not None
    handles = []
    for i, (name, xs, zs, marked_idx, z_star) in enumerate(panels):
        xs = np.asarray(xs)
        zs = np.asarray(zs, dtype=complex)
        color = f"C{i % 10}"
        mk = _OVERLAY_MARKERS[i % len(_OVERLAY_MARKERS)]
        style = dict(color=color, marker=mk, ms=4, markerfacecolor="none", lw=1.3)
        parts = [
            (ax, vals, ls, lab, star)
            for ax, vals, ls, lab, star in (
                (ax_r, zs.real, "-", "R", None if z_star is None else z_star.real),
                (ax_x, zs.imag, "--", "X", None if z_star is None else z_star.imag),
            )
            if ax is not None
        ]
        for ax, vals, ls, lab, _star in parts:
            handles += ax.plot(xs, vals, linestyle=ls, label=f"{name} {lab}", **style)
        for k in marked_idx:
            for ax, vals, _ls, _lab, _star in parts:
                ax.plot(
                    [xs[k]],
                    [vals[k]],
                    marker="s",
                    ms=8,
                    markerfacecolor="none",
                    markeredgecolor=color,
                    linestyle="None",
                )
        for ax, _vals, _ls, _lab, star in parts:
            if star is not None:
                ax.axhline(star, color=color, linestyle=":", lw=1.0, alpha=0.8)
    if log_x:
        _log_x_axis(ax0)
    ax0.set_xlabel(xlabel)
    if ax_r is not None:
        ax_r.set_ylabel("R (Ω), solid" if both else "R (Ω)")
    if ax_x is not None:
        ax_x.set_ylabel("X (Ω), dashed" if both else "X (Ω)")
    for ax in (ax_r, ax_x):
        if ax is not None:
            ax.yaxis.get_major_formatter().set_useOffset(False)
    _set_ylim(ax_r, r_range)
    _set_ylim(ax_x, x_range)
    mode = _callout_mode(callouts)
    if mode:
        _overlay_callouts(ax_r, ax_x, panels, mode, xname or xlabel, log_x)
    for name in refused:
        handles += ax0.plot(
            [], [], linestyle="None", marker="x", color="0.5", label=f"{name}: refused"
        )
    # Below the axes, one column per engine (its R above its X), so it
    # never sits on the curves or the callout columns.
    ax0.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        frameon=False,
        fontsize=7,
        ncol=max(1, len(panels) + len(refused)),
    )
    _polish_axes(ax0, title=title)
    if both:
        ax_x.spines["top"].set_visible(False)
    fig.tight_layout()
    return ax_r, ax_x


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


def swr_curve(antenna_builder, nm, xs, engine, z0):
    """``(zs, swr)`` at ``xs``, shaped (points, ports): the solve behind
    ``sweep --swr`` and every `analyses.Swr` / `analyses.S11` view
    (``analyze``), so the two are one computation. Sweeping ``freq`` is one
    build and the engine's vectorized impedance_sweep; any other knob
    rebuilds per point."""
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
    return zs, swr_of(zs, z0)


def swr_of(zs, z0):
    """SWR of impedances ``zs`` against ``z0``: (1 + |Γ|)/(1 − |Γ|)."""
    rho = np.abs((zs - z0) / (zs + z0))
    return (1 + rho) / (1 - rho)


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
    xs=None,
):
    """SWR + reflection magnitude against any swept knob.

    Sweeping `freq` uses the engine's vectorized impedance_sweep (one build,
    one matrix per frequency); any other knob changes the geometry, so the
    engine is rebuilt per point like the other parameter sweeps.

    `measured` is an optional `MeasuredTrace` (a VNA `.s1p`, issue #595) drawn
    as a second, dashed trace on both axes over the band it covers.

    `xs` given is the grid itself, and `rng`/`center`/`fraction`/`npoints`
    are not read (the CLI passes a frequency sweep's default range this way,
    `frequency_range.design_range`).
    """
    import matplotlib.pyplot as plt

    if xs is None:
        xs = gen_xs(getattr(antenna_builder, nm), rng, center, fraction, npoints)
    # Align before solving: a disjoint measured band should fail immediately,
    # not after a full sweep's worth of matrix solves.
    meas = _align_measured(measured, nm, xs, z0)

    zs, swr = swr_curve(antenna_builder, nm, xs, engine, z0)
    rho = np.abs((zs - z0) / (zs + z0))

    # |S11| in dB is 20·log10|Γ|, the workbench's S11 chart and every VNA's;
    # this was 10·log10|Γ| (a power quantity's formula on a voltage ratio),
    # which read half the return loss (the sweep inventory, 2026-09-27).
    rho_db = np.log10(rho) * 20.0

    fig, ax0 = plt.subplots(figsize=(7.0, 4.5))
    color = "tab:red"
    ax0.set_xlabel(_param_label(nm))
    ax0.set_ylabel("S11 20·log₁₀|Γ| (dB)", color=color)
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


# The app's own convergence ladder (`DENSITY_LADDER`,
# web/frontend/src/lib/paramSweep.ts). A CLI study run with no --range reproduces exactly
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
    per_engine,
    estimates,
    z0,
    marked=frozenset(),
    ground_label=None,
    reasons=None,
    knob="nominal_nsegs",
):
    """The stdout table for ``sweep --param nominal_nsegs`` (#1554): grouped
    per engine so a single-engine study reads like a plain ladder printout,
    and a multi-engine one reads as N of those back to back. ΔΓ is against
    that engine's own FINEST rung (issue #1525's ladder metric — the density
    records are judged on ΔΓ against the finest rung, not against Z* itself,
    since Z* is itself only an estimate).

    ``knob`` is the knob playing the density role (``nominal_nsegs``, or a
    deck's own, AK#1757). ``ground_label`` is one label for every curve, or a
    ``{name: label}`` dict when the curves differ in ground (an analysis
    crossed with grounds)."""
    head = "nominal_N" if knob == "nominal_nsegs" else knob
    width = max(9, len(head))
    for name, rows in per_engine.items():
        print(f"== {knob} convergence: {name} ==")
        label = (
            ground_label.get(name) if isinstance(ground_label, dict) else ground_label
        )
        if label is not None:
            # Every engine of a CLI study runs on the SAME ground (AK#1563);
            # it is printed under each header so a table pasted on its own
            # still says which physics the numbers are.
            print(f"ground: {label}")
        print(f"{head:>{width}} {'N_ach':>6} {'R (Ω)':>9} {'X (Ω)':>9} {'|ΔΓ|':>9}")
        finest_gamma = _reflection(rows[-1][2], z0)
        for nominal_n, achieved_n, z in rows:
            dgamma = abs(_reflection(z, z0) - finest_gamma)
            star = " *" if nominal_n in marked else ""
            print(
                f"{nominal_n:>{width}} {achieved_n:>6} {z.real:>9.3f} "
                f"{z.imag:>+9.3f} {dgamma:>9.4f}{star}"
            )
        if marked:
            print("  * = a --markers rung")
        print(f"{name}  {describe(estimates[name])}")
        if reasons and name in reasons:
            print(f"{' ' * len(name)}  {reasons[name]}")


def _convergence_rungs(rng, npoints, markers=()):
    """``(rungs, ladder_rungs, marked, drawn_marks)`` for a density study.

    ``rungs`` are every value solved, ascending; ``ladder_rungs`` the ones
    Z∞ reads; ``marked`` the ``--markers`` rungs, starred in the table;
    ``drawn_marks`` the ones squared on the chart."""
    # `--markers` on a density study are rungs at exactly the densities named
    # (the served 15 / 16 / 20, say): solved like any rung, starred in the
    # table and squared on the chart. Beside a ladder (--range / --npoints, or
    # the default one) they are observations only, not rungs of the Richardson
    # estimate (see `_convergence_estimates`); alone, they are the whole ladder.
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
    return sorted(ladder_rungs | marked), ladder_rungs, marked, drawn_marks


def _convergence_rows(antenna_builder, factory, rungs, knob="nominal_nsegs"):
    """One engine's ladder: ``(rows, fed_lengths, nports)``, one cold solve
    per rung with ``knob`` set to it. ``rows`` are ``(rung, N achieved, Z at
    port 0)``; ``fed_lengths`` the fed segment's length at each rung (port
    0), the reason a rough Z∞ gives (AK#1781, feed_mesh_step). The ONE place
    a density study solves: ``sweep --param`` and ``analyze`` both call it."""
    rows = []
    lens = []
    nports = 1
    for n in rungs:
        setattr(antenna_builder, knob, n)
        eng = factory(antenna_builder)
        z = eng.impedance()
        nports = max(nports, len(z))
        rows.append((n, _achieved_n(eng, antenna_builder), complex(z[0])))
        # Optional: an engine that cannot say (a test stub) gives no reason.
        fed_segments = getattr(eng, "fed_segments", None)
        fed = fed_segments() if fed_segments is not None else None
        lens.append(fed[0]["length_m"] if fed else None)
    return rows, lens, nports


def _convergence_estimates(per_engine, fed_len, ladder_rungs):
    """``(estimates, reasons)``: each curve's Z∞, and the feed-mesh reason
    beside a rough one."""
    # Z∞ reads the GEOMETRIC ladder only: a marker dropped between two rungs
    # would shrink one step and grow the next, and the estimator's order
    # comes from the slope of adjacent steps. Markers are observations on
    # the trajectory, not rungs of the extrapolation. The refinement
    # variable is the ACHIEVED segment count, as in the workbench (AK#1781).
    estimates = {}
    reasons = {}
    for name, rows in per_engine.items():
        on = [k for k, (n, _, _) in enumerate(rows) if n in ladder_rungs]
        xs = [rows[k][1] for k in on]
        estimates[name] = zinf_estimate(xs, [rows[k][2] for k in on])
        lens = [fed_len[name][k] for k in on]
        if estimates[name].status == "rough" and None not in lens:
            step = feed_mesh_step(xs, lens)
            if step is not None:
                reasons[name] = describe_feed_mesh(xs, lens, step)
    return estimates, reasons


def _convergence_title(knob, nports):
    title = f"impedance vs {knob}, Richardson Z∞"
    if nports > 1:
        title += f" (port 0 of {nports})"
    return title


def _convergence_panels(per_engine, estimates, drawn_marks):
    """The ``_rx_panels`` / ``_rx_overlay`` rows of a density study: x is
    the achieved segment count."""
    return [
        (
            name,
            [achieved for _, achieved, _ in rows],
            [z for _, _, z in rows],
            [k for k, (n, _, _) in enumerate(rows) if n in drawn_marks],
            estimates[name].z_inf,
        )
        for name, rows in per_engine.items()
    ]


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
    only=None,
    knob="nominal_nsegs",
):
    """``sweep --param nominal_nsegs`` (#1554): one cold solve per rung per
    engine, port 0 only (multi-port trajectories are the app's own overlay,
    out of scope here — see the title note when a design has more than one).

    ``engines`` is ``[(name, factory), ...]``. The density wrapper from
    #1543 must already have stood down in the caller (``mesh_density=False``
    in ``cli.engine_factories_from_args``) — this function is the one thing
    allowed to move the density knob for the duration.

    ``knob`` is the knob playing the density role: ``nominal_nsegs`` on a
    catalog design, or one a design declares (a SimNEC ``JamSegments`` count,
    AK#1757), which gets the same table, Z∞ and feed-mesh reason.
    """
    import matplotlib.pyplot as plt

    rungs, ladder_rungs, marked, drawn_marks = _convergence_rungs(rng, npoints, markers)

    per_engine = {}
    fed_len = {}
    nports = 1
    for name, factory in engines:
        rows, lens, n = _convergence_rows(antenna_builder, factory, rungs, knob)
        per_engine[name] = rows
        fed_len[name] = lens
        nports = max(nports, n)

    estimates, reasons = _convergence_estimates(per_engine, fed_len, ladder_rungs)

    _print_convergence_table(
        per_engine,
        estimates,
        z0,
        marked=marked,
        ground_label=ground_label,
        reasons=reasons,
        knob=knob,
    )

    title = _convergence_title(knob, nports)

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
            z_star = estimates[name].z_inf
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
        panels = _convergence_panels(per_engine, estimates, drawn_marks)
        (_rx_overlay if overlay else _rx_panels)(
            panels,
            xlabel="segments achieved (log)",
            title=title,
            log_x=True,
            r_range=r_range,
            x_range=x_range,
            callouts=callouts,
            xname="N",
            only=only,
        )

    save_or_show(plt, fn)


def _solve_at(antenna_builder, nm, xs, factory):
    """One solve per value of ``xs`` with knob ``nm`` set to it: each
    solve's impedance array (every port). The ONE place a knob sweep solves:
    ``sweep --param`` and ``analyze`` both call it."""
    out = []
    for x in xs:
        setattr(antenna_builder, nm, x)
        out.append(factory(antenna_builder).impedance())
    return out


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
    only=None,
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
    - ``only``: ``"r"`` or ``"x"`` draws just that quantity, on one y axis
      (no twin), in every rectangular layout; its callouts name only it.
      The Smith chart ignores it (the CLI refuses the pair).

    ``nominal_nsegs``, and the knob a design declares for the density role
    (``analyses.density_knob``, AK#1757), is a convergence study: always
    log-spaced, and drawn as panels unless ``overlay``.
    """
    import matplotlib.pyplot as plt

    from .analyses import density_knob

    engines = list(engine.items()) if isinstance(engine, dict) else [(None, engine)]

    if nm == "nominal_nsegs" or nm == density_knob(antenna_builder):
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
            only=only,
            knob=nm,
        )
        return

    show_r, show_x = _only_parts(only)

    if npoints is None:
        npoints = 21
    xs = gen_xs(getattr(antenna_builder, nm), rng, center, fraction, npoints, log=log)
    # Align first so a disjoint measured band errors before any solving.
    meas = _align_measured(measured, nm, xs, z0)

    if len(engines) == 1 and engines[0][0] is None:
        # The pre-#1554 single-engine path, UNCHANGED — pinned byte-identical
        # by test_cli_sweep_single_engine_output_is_unchanged (#1554).
        engine = engines[0][1]

        zs = _solve_at(antenna_builder, nm, xs, engine)
        marker_zs = _solve_at(antenna_builder, nm, markers, engine)

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
            ax0.set_xlabel(_param_label(nm))
            if meas is not None:
                mxs, mz = meas[0], z0 * (1.0 + meas[1]) / (1.0 - meas[1])
            # R in red on the left axis, X in blue on a twin right one; with
            # --only, the one quantity drawn on ax0 alone (no twin).
            ax_r, ax_x = _rx_axes(ax0, only)
            for ax, part, color, label in (
                (ax_r, np.real, _R_COLOR, "resistance R (Ω)"),
                (ax_x, np.imag, _X_COLOR, "reactance X (Ω)"),
            ):
                if ax is None:
                    continue
                ax.set_ylabel(label, color=color)
                ax.tick_params(axis="y", labelcolor=color)
                for i in range(nwidth):
                    if zs.shape[0] > 0:
                        ax.plot(
                            xs,
                            part(zs)[:, i],
                            color=color,
                            linestyle=_port_style(i),
                            marker="o",
                            ms=3,
                        )
                    if marker_zs.shape[0] > 0:
                        ax.plot(
                            marker_xs,
                            part(marker_zs)[:, i],
                            color=color,
                            marker="s",
                            linestyle="None",
                        )
                if meas is not None:
                    ax.plot(mxs, part(mz), color=color, **_MEASURED_KW)
            if meas is not None:
                _measured_legend(ax0, measured.label)

            if log:
                _log_x_axis(ax0)
            _set_ylim(ax_r, r_range)
            _set_ylim(ax_x, x_range)
            mode = _callout_mode(callouts)
            if mode:
                pivot = _pivot(np.concatenate([xs, marker_xs]), log)
                for i in range(nwidth):
                    if zs.shape[0] > 0:
                        idx = _callout_indices(mode, zs.shape[0], ())
                        _annotate_rx(ax_r, ax_x, xs, zs[:, i], idx, nm, pivot)
                    if marker_zs.shape[0] > 0 and mode != "ends":
                        _annotate_rx(
                            ax_r,
                            ax_x,
                            marker_xs,
                            marker_zs[:, i],
                            range(marker_zs.shape[0]),
                            nm,
                            pivot,
                        )
            _polish_axes(ax0, title=_z_title(antenna_builder, nm))
            if ax_r is not None and ax_x is not None:
                ax_x.spines["top"].set_visible(False)
            fig.tight_layout()

        save_or_show(plt, fn)
        return

    # Multi-engine path (#1554): same xs, one trajectory/line per engine.
    # Colour now keys the ENGINE (one axis, not the twin-axis red/blue
    # R/X split the single-engine rectangular chart uses) — R solid, X
    # dashed, so a port still reads within an engine via `_port_style`.
    per_engine = []
    for name, factory in engines:
        zs = _solve_at(antenna_builder, nm, xs, factory)
        marker_zs = _solve_at(antenna_builder, nm, markers, factory)
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
            only=only,
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
        if show_r and show_x:
            ax0.set_ylabel("R solid / X dashed (Ω)")
        else:
            ax0.set_ylabel("resistance R (Ω)" if show_r else "reactance X (Ω)")
        for ei, (name, zs, marker_zs) in enumerate(per_engine):
            color = f"C{ei}"
            for i in range(nwidth):
                label = f"{name} port {i + 1}" if nwidth > 1 else name
                # R solid (per-port style) with circles, X dashed with
                # triangles; --only keeps one. The first drawn carries the
                # engine's legend label.
                parts = [
                    (part, ls, mk)
                    for part, ls, mk, on in (
                        (np.real, _port_style(i), "o", show_r),
                        (np.imag, "--", "^", show_x),
                    )
                    if on
                ]
                if zs.shape[0] > 0:
                    for part, ls, mk in parts:
                        ax0.plot(
                            xs,
                            part(zs)[:, i],
                            color=color,
                            linestyle=ls,
                            marker=mk,
                            ms=3,
                            label=label,
                        )
                        label = None
                if marker_zs.shape[0] > 0:
                    for part, _ls, _mk in parts:
                        ax0.plot(
                            marker_xs,
                            part(marker_zs)[:, i],
                            color=color,
                            marker="s",
                            linestyle="None",
                        )
        if meas is not None:
            mxs, mz = meas[0], z0 * (1.0 + meas[1]) / (1.0 - meas[1])
            mpart = np.real if show_r else np.imag
            ax0.plot(mxs, mpart(mz), color="0.25", **_MEASURED_KW)
            _measured_legend(ax0, measured.label)

        if log:
            _log_x_axis(ax0)
        _polish_axes(ax0, title=_z_title(antenna_builder, nm))
        ax0.legend(loc="best", frameon=False, fontsize=8)
        fig.tight_layout()

    save_or_show(plt, fn)
