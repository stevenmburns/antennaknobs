from . import Antenna
from .core import save_or_show
from .engine import SimulationEngine

import numpy as np

# matplotlib.pyplot is imported lazily inside the plotting functions below
# (plot_patterns / pattern / pattern3d) — it costs ~0.1 s to import and only the
# plotting paths need it, so it stays off `import antennaknobs` and web startup.


def _as_engine(obj):
    """Accept either an AntennaBuilder (legacy path; wrap with the default
    Antenna alias, the momwire engine since #1323) or an already-constructed SimulationEngine
    instance (lets callers pick the backend and any ground/options)."""
    if isinstance(obj, SimulationEngine):
        return obj
    return Antenna(obj)


def _engine_has_ground(engine):
    """Whether this engine solves over a ground: its pattern's lower
    hemisphere is then empty, and a θ ≤ 90° grid is the whole sphere's
    integral (`average_gain`). The momwire engine keeps it as `_ground`
    (None in free space), the NEC wrappers as `ground` ("free" or None)."""
    g = getattr(engine, "ground", getattr(engine, "_ground", None))
    return g is not None and g != "free"


def _whole_sphere_rdf(gain):
    """RDF at the whole-sphere 1° grid's peak, off a gain evaluator
    (`MomwireEngine.gain_evaluator`): the free-space case a NEC-convention
    hemisphere grid cannot answer."""
    thetas = np.arange(0.0, 180.5, 1.0)
    phis = np.arange(0.0, 360.0, 1.0)
    grid = gain(thetas, phis)
    return rdf_db(float(grid.max()), grid, thetas, phis)


def _default_name(obj):
    if isinstance(obj, SimulationEngine):
        return type(obj).__name__
    return "Unknown"


# Visual floor for dBi polar plots. Without an explicit rmin matplotlib
# autoscales to data extent, so a constant-radius cut (e.g. an elevation
# slice along a horizontal dipole's broadside direction, gain ≈ const)
# gets smeared across the entire radial range and a 0.02 dBi difference
# between two engines reads as "one curve is at the rim, the other at
# the centre". Pinning the floor to the lowest labelled tick keeps
# constant curves at their actual dBi position.
_DBI_FLOOR = -12


def _init_dbi_polar(ax):
    ax.set_rticks([-12, -6, 0, 6, 12])
    ax.set_rmin(_DBI_FLOOR)


def _finalise_dbi_polar(ax, title=None):
    # Let the top expand if data exceeds the highest labelled tick, but
    # never shrink below it — otherwise a low-gain pattern looks identical
    # in shape to a high-gain one because both fill the axis.
    top = max(12, ax.get_ylim()[1])
    ax.set_ylim(_DBI_FLOOR, top)
    ax.grid(alpha=0.45, linewidth=0.6)
    ax.spines["polar"].set_color("0.5")
    ax.spines["polar"].set_linewidth(0.8)
    ax.tick_params(labelsize=8)
    if title is not None:
        ax.set_title(title, fontsize=11, pad=14)


def get_pattern_rings(builder_or_engine):
    a = _as_engine(builder_or_engine)
    ff = a.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    del a
    return ff.rings, ff.max_gain, ff.min_gain, ff.thetas, ff.phis


def get_elevation(a):
    ff = a.far_field(n_theta=90, n_phi=1, del_theta=1, del_phi=360)
    return ff.rings, ff.max_gain, ff.min_gain, ff.thetas, ff.phis


def _beamwidth_wrapped(angles, gains, peak_idx, threshold):
    """−3 dB-style width through a peak in a *wrapped* cut (azimuth: φ 0→360
    with a duplicated endpoint). Returns the angular width (deg) where the
    trace stays at/above `threshold` either side of the peak, the crossings
    found by linear interpolation between 1° samples. A trace that never drops
    below threshold (omnidirectional) returns the full 360°."""
    g = np.asarray(gains[:-1], float)  # drop the duplicated φ=360 sample
    ang = np.asarray(angles[:-1], float)
    n = len(g)
    if n == 0 or np.all(g >= threshold):
        return 360.0
    pk = int(peak_idx) % n

    def walk(direction):
        dist = 0.0
        i = pk
        for _ in range(n):
            j = (i + direction) % n
            step = ((ang[j] - ang[i]) * direction) % 360.0 or 360.0 / n
            if g[j] < threshold:
                frac = (g[i] - threshold) / (g[i] - g[j])
                return dist + frac * step
            dist += step
            i = j
        return None

    right, left = walk(+1), walk(-1)
    if right is None or left is None:
        return 360.0
    return right + left


def _beamwidth_linear(angles, gains, peak_idx, threshold):
    """−3 dB-style width through a peak in a *non-wrapped* cut (elevation:
    bounded to the 0°–90° hemisphere). Same interpolation as the wrapped case,
    but a side that runs into the array edge without crossing returns the
    distance to the edge, so the result is a lower bound for a lobe that hugs
    the horizon or zenith."""
    g = np.asarray(gains, float)
    ang = np.asarray(angles, float)
    n = len(g)
    if n == 0 or np.all(g >= threshold):
        return abs(float(ang[-1] - ang[0])) if n else 0.0

    def walk(direction):
        dist = 0.0
        i = int(peak_idx)
        while 0 <= i + direction < n:
            j = i + direction
            step = abs(float(ang[j] - ang[i]))
            if g[j] < threshold:
                frac = (g[i] - threshold) / (g[i] - g[j])
                return dist + frac * step
            dist += step
            i = j
        return dist  # ran into the edge — truncated lower bound

    return walk(+1) + walk(-1)


def average_gain(gain_dbi, thetas_deg, phis_deg):
    """The pattern's AVERAGE GAIN, linear: (1/4π)∬ G(θ, φ) dΩ over the grid.

    `gain_dbi` is the (n_theta, n_phi) grid in dBi, θ from the zenith and φ
    from +x, both in degrees. The φ grid must go all the way round: either a
    CLOSED ring (0 ... 360, the duplicated endpoint the far-field grids carry)
    or an OPEN one (0 ... 359, which is wrapped here). Trapezoid in both
    angles, weighted by sin θ.

    The normalisation is ALWAYS the full sphere, 4π, whatever the θ grid
    covers. Over a ground the lower hemisphere carries no radiation, so a grid
    that stops at the horizon is the whole integral and the missing half
    contributes zero — this is EZNEC's "Average Gain", the one the published
    RDF figures (W8JI, ON4UN) subtract. Normalising by the upper hemisphere's
    2π instead would read 3.01 dB higher and is NOT what those figures mean.
    It follows that a free-space pattern must be sampled over the whole
    sphere (θ to 180°) for this to be its average gain.

    Since gain is power density per INPUT watt, the average gain is also
    P_radiated / P_input — the same integral `radiated_fraction` takes.
    """
    g = 10.0 ** (np.asarray(gain_dbi, float) / 10.0)
    th = np.radians(np.asarray(thetas_deg, float))
    ph = np.asarray(phis_deg, float)
    if g.shape != (th.size, ph.size):
        raise ValueError(
            f"gain grid {g.shape} does not match {th.size} thetas x {ph.size} phis"
        )
    span = float(ph[-1] - ph[0])
    if abs(span - 360.0) > 1e-6:
        # An open ring: close it with its own first column, one step on.
        step = float(ph[1] - ph[0]) if ph.size > 1 else 360.0
        if abs(span + step - 360.0) > 1e-6:
            raise ValueError(
                f"the phi grid spans {span:g} deg; an average gain needs the "
                "whole ring (0..360 closed, or 0..360-step open)"
            )
        g = np.concatenate([g, g[:, :1]], axis=1)
        ph = np.append(ph, ph[0] + 360.0)
    ring = np.trapezoid(g, np.radians(ph), axis=1)
    return float(np.trapezoid(ring * np.sin(th), th) / (4.0 * np.pi))


def rdf_db(target_gain_dbi, gain_dbi, thetas_deg, phis_deg):
    """Receiving Directivity Factor, dB (AK#1707).

        RDF = G(target) − 10·log10( (1/4π) ∬ G(θ, φ) dΩ )

    the forward gain in dBi minus the average gain in dB (`average_gain`,
    normalised by the FULL sphere, with the lower hemisphere contributing
    nothing over a ground). This is the figure of merit W8JI and ON4UN use for
    receiving antennas: on a band limited by atmospheric noise arriving from
    every direction, the signal-to-noise ratio the antenna delivers depends on
    how much it favours the wanted direction over the average of all of them,
    not on its absolute gain — a Beverage at −10 dBi and a dipole at +6 dBi are
    judged on the same scale.

    Two properties worth knowing. Loss cancels: gain and average gain carry
    the same efficiency, so RDF is the DIRECTIVITY in the target direction,
    4π·U/P_rad, and ground or terminator loss does not move it. And the full-
    sphere normalisation makes a lossless antenna over perfect ground read its
    ordinary directivity: a short monopole over PEC reads 4.77 dB (3x), an
    isotropic radiator in free space 0 dB.
    """
    return float(target_gain_dbi) - 10.0 * np.log10(
        average_gain(gain_dbi, thetas_deg, phis_deg)
    )


def pattern_metrics(ff, *, beamwidth_db=3.0, has_ground=None):
    """Summarise a `FarField` into scalar metrics for comparing antennas.

    Returns a dict with:
      * `peak_gain_dbi`    — maximum gain over the whole pattern (dBi)
      * `takeoff_deg`      — elevation angle of the peak (90 − θ)
      * `azimuth_deg`      — azimuth of the peak
      * `front_to_back_db` — peak minus the gain at the same elevation, 180°
                             away in azimuth
      * `az_beamwidth_deg` — −`beamwidth_db` width through the peak in the
                             azimuth ring at the peak's elevation
      * `el_beamwidth_deg` — −`beamwidth_db` width through the peak in the
                             elevation column at the peak's azimuth (a lower
                             bound when the lobe meets the 0°/90° limit)
      * `rdf_db`           — receiving directivity factor at the peak (`rdf_db`,
                             the function). NEC-convention grids stop at
                             θ = 89°, so this is only the whole integral when
                             the lower hemisphere is known to be empty: pass
                             `has_ground=True` for a pattern over a ground.
                             None when the grid is a hemisphere and
                             `has_ground` is not True — a free-space pattern
                             sampled over half the sphere has no average gain.
    """
    rings = np.asarray(ff.rings, float)
    thetas = np.asarray(ff.thetas, float)
    phis = np.asarray(ff.phis, float)
    ti, pi = np.unravel_index(int(np.argmax(rings)), rings.shape)
    peak = float(rings[ti, pi])
    ring = rings[ti]

    back_az = (float(phis[pi]) + 180.0) % 360.0
    bi = int(np.argmin(np.abs(((phis - back_az + 180.0) % 360.0) - 180.0)))
    front_to_back = peak - float(ring[bi])

    thr = peak - beamwidth_db
    return {
        "peak_gain_dbi": peak,
        "takeoff_deg": float(90.0 - thetas[ti]),
        # Wrapped into [0, 360): the azimuth grid carries a DUPLICATED
        # endpoint (φ = 0 and φ = 360 are one direction, both sampled), and
        # the two copies differ at the last bit — 1.0744769060050083 against
        # 1.074476906005009 on the pota_performer pattern. Reporting the raw
        # grid value therefore let a 1-ULP tie decide between "0" and "360"
        # for the same bearing, which is a property of the build rather than
        # of the antenna (issue #958). Canonicalise the answer, not the grid:
        # the ring is closed on purpose, for the polar plots.
        "azimuth_deg": float(phis[pi]) % 360.0,
        "front_to_back_db": front_to_back,
        "az_beamwidth_deg": _beamwidth_wrapped(phis, ring, pi, thr),
        "el_beamwidth_deg": _beamwidth_linear(90.0 - thetas, rings[:, pi], ti, thr),
        "rdf_db": (
            rdf_db(peak, rings, thetas, phis)
            if has_ground or float(np.max(thetas)) > 90.0
            else None
        ),
    }


# Samples within this many dB of the grid maximum count as tied with it. The
# FIRST of them wins, in θ-then-φ order: the highest elevation, then the
# smallest azimuth. An omnidirectional ring or a pattern symmetric about the
# horizon then reports one direction by construction, rather than whichever
# sample a last-bit difference happened to favour (the #958 lesson).
_PEAK_TIE_DB = 1e-9


def refined_pattern_metrics(gain, *, beamwidth_db=3.0, tol_deg=0.01):
    """`pattern_metrics`, measured off a gain evaluator instead of a fixed
    grid (issue #1669).

    `gain` is a callable ``gain(theta_deg, phi_deg) -> dBi grid`` carrying
    ``has_ground`` (`MomwireEngine.gain_evaluator`). NEC's far-field grid runs
    θ 0..89°, so it never samples the horizon and never the lower hemisphere,
    and its maximum is the best 1° × 1° sample. This one:

      * samples elevation 0° itself, and in free space the whole sphere, so a
        lobe pointing down is found and reports a negative `takeoff_deg`;
      * refines the best sample by a pattern search, to about `tol_deg` in
        each angle, so the peak gain is the lobe's and not its nearest sample;
      * takes F/B and both beamwidths through the REFINED direction: the
        azimuth ring at its elevation, and the elevation column at its
        azimuth, running to the horizon (to the nadir in free space);
      * takes the RDF (AK#1707) as the refined peak gain over the average
        gain of the 1° search grid — the upper hemisphere to the horizon over
        a ground, the whole sphere in free space, normalised by 4π either way
        (`rdf_db`).

    Returns the same keys as `pattern_metrics`.
    """
    theta_max = 90.0 if gain.has_ground else 180.0
    thetas = np.arange(0.0, theta_max + 0.5, 1.0)
    phis = np.arange(0.0, 360.0, 1.0)
    grid = gain(thetas, phis)
    best = int(np.flatnonzero(grid.ravel() >= grid.max() - _PEAK_TIE_DB)[0])
    ti, pi = np.unravel_index(best, grid.shape)
    th, ph, peak = float(thetas[ti]), float(phis[pi]), float(grid[ti, pi])

    # Compass search: step to the best of the eight neighbours at spacing h
    # when it beats the centre, halve h when none does. Moving only on a
    # strict gain means a flat ring leaves the centre where the grid put it.
    h = 0.5
    for _ in range(400):
        if h < tol_deg:
            break
        cand_t = np.clip(th + np.array([-h, 0.0, h]), 0.0, theta_max)
        cand_p = ph + np.array([-h, 0.0, h])
        local = gain(cand_t, cand_p)
        li, lj = np.unravel_index(int(np.argmax(local)), local.shape)
        if local[li, lj] > peak + _PEAK_TIE_DB:
            th, ph, peak = float(cand_t[li]), float(cand_p[lj]), float(local[li, lj])
        else:
            h /= 2.0
    ph %= 360.0

    # The azimuth ring through the peak, starting AT it and closed as the
    # plots' rings are, so index 0 is the peak and index 180 the back.
    ring_phis = ph + np.arange(0.0, 361.0, 1.0)
    ring = gain([th], ring_phis)[0]
    # The elevation column through the peak, on 1° steps from it, with the
    # column's two ends added so a lobe that runs into one is measured to it.
    col_thetas = np.unique(
        np.concatenate(
            [
                [0.0],
                th + np.arange(-np.floor(th), np.floor(theta_max - th) + 1.0),
                [theta_max],
            ]
        )
    )
    col = gain(col_thetas, [ph])[:, 0]
    ci = int(np.argmin(np.abs(col_thetas - th)))

    thr = peak - beamwidth_db
    return {
        "peak_gain_dbi": peak,
        "takeoff_deg": 90.0 - th,
        "azimuth_deg": ph,
        "front_to_back_db": peak - float(ring[180]),
        "az_beamwidth_deg": float(_beamwidth_wrapped(ring_phis, ring, 0, thr)),
        "el_beamwidth_deg": float(_beamwidth_linear(90.0 - col_thetas, col, ci, thr)),
        "rdf_db": rdf_db(peak, grid, thetas, phis),
    }


def radiated_fraction(ff):
    """Fraction of input power that leaves as far-field radiation.

    Gain is power density per *input* watt, so the average of linear gain
    over the full sphere is exactly P_radiated / P_input. Over a ground
    the lower hemisphere contributes nothing, so integrating the upper
    hemisphere alone is the whole integral; what's missing from 1.0 is
    conductor/component loss plus ground absorption. This is the honest
    "where do the watts go" number — distinct from the *structural*
    efficiency usually quoted for antennas (conductor + component loss
    only), which ignores the ground's share entirely. A quarter-wave
    vertical over average earth radiates ~30% by this measure while
    being ">90% efficient" structurally; both are true, in different
    ledgers.

    Accuracy note: the integral is a trapezoid over the sampled grid, so
    patterns with significant energy at the horizon (verticals over PEC
    ground peak exactly there) lose a few percent to grid clipping;
    over lossy ground the horizon gain is ~0 and the integral is clean.
    """
    g = 10.0 ** (np.asarray(ff.rings, float) / 10.0)
    th = np.radians(np.asarray(ff.thetas, float))
    ph = np.radians(np.asarray(ff.phis, float))
    integ = np.trapezoid(np.trapezoid(g, ph, axis=1) * np.sin(th), th)
    return float(integ / (4.0 * np.pi))


def plot_patterns(
    rings_lst,
    names,
    thetas,
    phis,
    elevation_angle=15,
    fn=None,
    azimuth_f=0,
    azimuth_r=180,
):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        ncols=2, subplot_kw={"projection": "polar"}, figsize=(12, 6.5)
    )

    _init_dbi_polar(axes[0])

    for nm, rings in zip(names, rings_lst, strict=True):
        for theta, ring in list(zip(thetas, rings, strict=True)):
            if abs(theta - (90 - elevation_angle)) < 0.1:
                axes[0].plot(np.deg2rad(phis), ring, marker="", label=str(nm))

    _finalise_dbi_polar(
        axes[0], title=f"azimuth cut @ {elevation_angle:g}° elevation (dBi)"
    )

    n = len(rings_lst[0][0])
    assert (n - 1) % 2 == 0

    assert 0 <= azimuth_f < n - 1
    assert 0 <= azimuth_r < n - 1

    elevations = [
        list(reversed([ring[azimuth_f] for ring in rings]))
        + [ring[azimuth_r] for ring in rings]
        for rings in rings_lst
    ]
    el_thetas = list(reversed(list(90 - thetas))) + list(90 + thetas)

    _init_dbi_polar(axes[1])

    for elevation in elevations:
        axes[1].plot(np.deg2rad(el_thetas), elevation, marker="")

    # Elevation data spans 0°–180° (forward horizon → zenith → rear horizon),
    # so show the classic half-disc instead of an empty lower hemisphere.
    axes[1].set_thetamin(0)
    axes[1].set_thetamax(180)
    _finalise_dbi_polar(
        axes[1],
        title=f"elevation cut, az {phis[azimuth_f]:g}°→{phis[azimuth_r]:g}° (dBi)",
    )

    # One shared legend below both cuts (trace colors line up across them);
    # on-axes legends sit on top of the polar grid and the traces.
    handles, labels = axes[0].get_legend_handles_labels()
    if labels:
        fig.legend(
            handles,
            labels,
            loc="lower center",
            ncol=min(len(labels), 4),
            frameon=False,
            fontsize=9,
        )
        fig.subplots_adjust(bottom=0.14)

    save_or_show(plt, fn)


def _print_metrics_table(names, metrics_lst):
    """Print an aligned metrics table comparing the antennas, so a
    `compare_patterns` run (and the optimize before/after) reports the numbers
    that make the overlaid plot actionable, not just the shapes."""
    cols = [
        ("peak dBi", "peak_gain_dbi", "{:.2f}"),
        ("takeoff°", "takeoff_deg", "{:.0f}"),
        ("F/B dB", "front_to_back_db", "{:.1f}"),
        ("az bw°", "az_beamwidth_deg", "{:.0f}"),
        ("el bw°", "el_beamwidth_deg", "{:.0f}"),
        ("RDF dB", "rdf_db", "{:.1f}"),
    ]
    name_w = max([len("design")] + [len(str(n)) for n in names])
    header = "design".ljust(name_w) + "  " + "  ".join(h.rjust(8) for h, _, _ in cols)
    print(header)
    print("-" * len(header))
    for nm, m in zip(names, metrics_lst, strict=True):
        row = str(nm).ljust(name_w)
        for _, key, fmt in cols:
            v = m.get(key)
            row += "  " + ("—" if v is None else fmt.format(v)).rjust(8)
        print(row)


def compare_patterns(
    builders_or_engines,
    elevation_angle=15,
    fn=None,
    builder_names=None,
    azimuth_f=0,
    azimuth_r=180,
    show_metrics=True,
):
    """Plot azimuth + elevation cuts for a sequence of antennas.

    Each item may be either an AntennaBuilder (uses the default PyNEC
    engine) or a pre-constructed SimulationEngine instance — the latter
    is how you pick a non-default backend or ground configuration. Pass
    an explicit `builder_names=[...]` to control legend labels; absent
    that, engine instances get their class name (e.g. "PyNECEngine",
    "MomwireEngine") and bare builders fall back to "Unknown" for
    backwards compatibility. With `show_metrics` (default) a peak-gain /
    takeoff / F-B / beamwidth / RDF table is printed alongside the plot."""
    if builder_names is None:
        builder_names = [_default_name(b) for b in builders_or_engines]

    rings_lst = []
    metrics_lst = []
    thetas = phis = None

    for item in builders_or_engines:
        a = _as_engine(item)
        ff = a.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
        has_ground = _engine_has_ground(a)
        m = pattern_metrics(ff, has_ground=has_ground)
        if m["rdf_db"] is None and hasattr(a, "gain_evaluator"):
            # Free space on an engine that can look below the horizon: take
            # the RDF over the whole sphere rather than leave it blank.
            m["rdf_db"] = _whole_sphere_rdf(a.gain_evaluator())
        del a
        rings_lst.append(ff.rings)
        metrics_lst.append(m)
        thetas, phis = ff.thetas, ff.phis

    if show_metrics:
        _print_metrics_table(builder_names, metrics_lst)

    plot_patterns(
        rings_lst,
        builder_names,
        thetas,
        phis,
        elevation_angle,
        fn,
        azimuth_f,
        azimuth_r,
    )


def pattern(builder_or_engine, elevation_angle=15, fn=None):
    import matplotlib.pyplot as plt

    rings, max_gain, min_gain, thetas, phis = get_pattern_rings(builder_or_engine)

    fig, axes = plt.subplots(
        ncols=2, subplot_kw={"projection": "polar"}, figsize=(11, 5)
    )

    _init_dbi_polar(axes[0])

    for theta, ring in list(zip(thetas, rings, strict=True)):
        if abs(theta - (90 - elevation_angle)) < 0.1:
            axes[0].plot(np.deg2rad(phis), ring, marker="")

    # The cut angle lives in the title now — a legend reading just "15"
    # obscured the grid without explaining itself.
    _finalise_dbi_polar(
        axes[0], title=f"azimuth cut @ {elevation_angle:g}° elevation (dBi)"
    )

    n = len(rings[0])
    assert (n - 1) % 2 == 0
    elevation = list(reversed([ring[0] for ring in rings])) + [
        ring[(n - 1) // 2] for ring in rings
    ]
    el_thetas = list(reversed(list(90 - thetas))) + list(90 + thetas)

    _init_dbi_polar(axes[1])

    axes[1].plot(np.deg2rad(el_thetas), elevation, marker="")

    axes[1].set_thetamin(0)
    axes[1].set_thetamax(180)
    _finalise_dbi_polar(axes[1], title="elevation cut, az 0°→180° (dBi)")
    save_or_show(plt, fn)


def pattern3d(builder_or_engine, fn=None):
    import matplotlib.pyplot as plt

    a = _as_engine(builder_or_engine)
    ff = a.far_field(n_theta=30, n_phi=60, del_theta=3, del_phi=6)
    del a

    rhos = [
        [ff.rings[theta_index][phi_index] for theta_index, _ in enumerate(ff.thetas)]
        for phi_index, _ in enumerate(ff.phis)
    ]

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")

    Theta, Phi = np.meshgrid(np.deg2rad(ff.thetas), np.deg2rad(ff.phis))
    Rho = 10 ** (np.array(rhos) / 10)

    X = Rho * np.sin(Theta) * np.cos(Phi)
    Y = Rho * np.sin(Theta) * np.sin(Phi)
    Z = Rho * np.cos(Theta)

    ax.plot_wireframe(X, Y, Z, rstride=2, cstride=2)
    ax.set_aspect("equal")

    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")

    save_or_show(plt, fn)
