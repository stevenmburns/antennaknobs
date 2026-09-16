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


def _print_convergence_table(per_engine, estimates, z0):
    """The stdout table for ``sweep --param nominal_nsegs`` (#1554): grouped
    per engine so a single-engine study reads like a plain ladder printout,
    and a multi-engine one reads as N of those back to back. ΔΓ is against
    that engine's own FINEST rung (issue #1525's ladder metric — the density
    records are judged on ΔΓ against the finest rung, not against Z* itself,
    since Z* is itself only an estimate)."""
    for name, rows in per_engine.items():
        print(f"== nominal_nsegs convergence: {name} ==")
        print(f"{'nominal_N':>9} {'N_ach':>6} {'R (Ω)':>9} {'X (Ω)':>9} {'|ΔΓ|':>9}")
        finest_gamma = _reflection(rows[-1][2], z0)
        for nominal_n, achieved_n, z in rows:
            dgamma = abs(_reflection(z, z0) - finest_gamma)
            print(
                f"{nominal_n:>9} {achieved_n:>6} {z.real:>9.3f} {z.imag:>+9.3f} "
                f"{dgamma:>9.4f}"
            )
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
    antenna_builder, engines, *, rng, npoints, use_smithchart, z0, fn
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

    rungs = _nominal_nsegs_rungs(rng, npoints)

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

    estimates = {
        name: ladder_estimate([(achieved, z) for _, achieved, z in rows])
        or (None, None)
        for name, rows in per_engine.items()
    }

    _print_convergence_table(per_engine, estimates, z0)

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
        fig, ax0 = plt.subplots(figsize=(7.0, 4.5))
        for i, (name, rows) in enumerate(per_engine.items()):
            color = f"C{i}"
            ns = [achieved for _, achieved, _ in rows]
            re = [z.real for _, _, z in rows]
            im = [z.imag for _, _, z in rows]
            ax0.plot(
                ns, re, color=color, linestyle="-", marker="o", ms=3, label=f"{name} R"
            )
            ax0.plot(
                ns, im, color=color, linestyle="--", marker="^", ms=3, label=f"{name} X"
            )
            z_star, _shrinking = estimates[name]
            if z_star is not None:
                ax0.axhline(
                    z_star.real, color=color, linestyle=":", linewidth=1.0, alpha=0.7
                )
                ax0.axhline(
                    z_star.imag, color=color, linestyle=":", linewidth=1.0, alpha=0.7
                )
        ax0.set_xscale("log")
        ax0.set_xlabel("segments achieved (log)")
        ax0.set_ylabel("Ω")
        _polish_axes(ax0, title=title)
        ax0.legend(loc="best", frameon=False, fontsize=7)
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
        )
        return

    if npoints is None:
        npoints = 21
    xs = gen_xs(getattr(antenna_builder, nm), rng, center, fraction, npoints)
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

    if use_smithchart:
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

        _polish_axes(ax0, title=_z_title(antenna_builder, nm))
        ax0.legend(loc="best", frameon=False, fontsize=8)
        fig.tight_layout()

    save_or_show(plt, fn)
