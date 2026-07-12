"""In-house matplotlib Smith-chart rendering for CLI sweep mode.

This replaces the two scikit-rf plotting helpers (``skrf.plotting.smith`` and
``skrf.plotting.plot_smith``) that were antennaknobs' only use of scikit-rf
(issue #332) — depending on all of scikit-rf (plus the pandas it drags in) for
one chart background wasn't worth the install weight. The geometry is
elementary:

- constant-resistance circles: centre ``(r/(1+r), 0)``, radius ``1/(1+r)``
- constant-reactance arcs:     centre ``(1, ±1/x)``, radius ``1/x``, clipped
  to the unit disc (matplotlib's clip path does the clipping — no arc-angle
  math needed)

All grid values are normalized to the reference impedance z0; the chart is
the familiar impedance ("z") chart.
"""

import numpy as np

# Normalized r and |x| values for the labelled grid — the same set scikit-rf
# drew by default, so the chart reads like the one it replaces.
MAJOR_GRID = (0.2, 0.5, 1.0, 2.0, 5.0)
# Extra unlabelled circles that fill the chart out; drawn thinner and lighter.
MINOR_GRID = (0.1, 0.3, 1.5, 3.0, 10.0)

_BOUNDARY_COLOR = "0.25"
_MAJOR_COLOR = "0.60"
_MINOR_COLOR = "0.82"
_LABEL_COLOR = "0.35"


def _add_circle(ax, center, radius, *, color, lw, clip=None, zorder=1):
    from matplotlib.patches import Circle

    patch = Circle(
        center, radius, fill=False, edgecolor=color, linewidth=lw, zorder=zorder
    )
    ax.add_patch(patch)
    if clip is not None:
        patch.set_clip_path(clip)
    return patch


def draw_smith_chart(ax, *, draw_labels=True, z0=None):
    """Draw an impedance Smith-chart background onto ``ax``.

    ``z0``, if given, is only annotated in the corner (the grid itself is
    normalized). Returns ``ax`` so callers can chain trace plotting.
    """
    boundary = _add_circle(ax, (0, 0), 1.0, color=_BOUNDARY_COLOR, lw=1.2, zorder=2)
    ax.plot([-1, 1], [0, 0], color=_MAJOR_COLOR, lw=0.7, zorder=1)

    for values, color, lw in (
        (MINOR_GRID, _MINOR_COLOR, 0.5),
        (MAJOR_GRID, _MAJOR_COLOR, 0.7),
    ):
        for v in values:
            _add_circle(ax, (v / (1 + v), 0), 1 / (1 + v), color=color, lw=lw)
            for sign in (1.0, -1.0):
                _add_circle(
                    ax, (1.0, sign / v), 1 / v, color=color, lw=lw, clip=boundary
                )

    if draw_labels:
        text_kw = dict(fontsize=7, color=_LABEL_COLOR, zorder=3)
        for r in MAJOR_GRID:
            g = (r - 1) / (r + 1)
            ax.text(g + 0.01, 0.02, f"{r:g}", ha="left", va="bottom", **text_kw)
        ax.text(-1.04, 0, "0", ha="right", va="center", **text_kw)
        ax.text(1.04, 0, "∞", ha="left", va="center", **text_kw)
        for x in MAJOR_GRID:
            # Where the constant-x arc meets the rim; nudge the label outward.
            g = (1j * x - 1) / (1j * x + 1)
            for sign, prefix in ((1.0, "+"), (-1.0, "-")):
                ax.text(
                    g.real * 1.08,
                    sign * g.imag * 1.08,
                    f"{prefix}j{x:g}",
                    ha="center",
                    va="center",
                    **text_kw,
                )
        if z0 is not None:
            ax.text(
                -1.12,
                -1.12,
                f"grid normalized to z0 = {z0:g} Ω",
                ha="left",
                va="bottom",
                fontsize=8,
                color=_LABEL_COLOR,
            )

    pad = 1.16 if draw_labels else 1.03
    ax.set_aspect("equal")
    ax.set_xlim(-pad, pad)
    ax.set_ylim(-pad, pad)
    ax.set_axis_off()
    return ax


def plot_reflection(ax, gamma, **plot_kwargs):
    """Plot complex reflection coefficient(s) as a trace on a Smith chart."""
    gamma = np.asarray(gamma)
    plot_kwargs.setdefault("zorder", 4)
    return ax.plot(gamma.real, gamma.imag, **plot_kwargs)
