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


def gen_xs(default_value, rng, center, fraction, npoints):
    rng = resolve_range(default_value, rng, center, fraction)
    if npoints == 1 and rng[0] < rng[1]:
        print(
            "Range includes more than just a point and npoints == 1. Using the lower range bound."
        )
    return np.linspace(rng[0], rng[1], npoints)


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
):
    import matplotlib.pyplot as plt

    xs = gen_xs(getattr(antenna_builder, nm), rng, center, fraction, npoints)
    # Align first so a disjoint measured band errors before any solving.
    meas = _align_measured(measured, nm, xs, z0)

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
        ax0.set_title(f"feedpoint impedance vs {nm}", fontsize=11)
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

        _polish_axes(ax0, title=f"feedpoint impedance vs {nm}")
        ax1.spines["top"].set_visible(False)
        fig.tight_layout()

    save_or_show(plt, fn)
