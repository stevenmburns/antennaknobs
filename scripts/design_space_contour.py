"""Two-knob design-space contour maps: |Γ| level curves, optionally with the
R=1 / X=0 families overlaid.

Optimizers report a point. This reports the *shape of the space around it*,
which answers questions a point cannot:

  1. **How many answers are there?** A design whose |Γ| basins are two closed
     regions joined by a saddle (``verticals.stub_matched_vertical``) has two
     genuine matches, and an optimizer slides to whichever one it started
     nearest. The map counts them; the optimizer never mentions the other.
  2. **Which knobs is the answer trustworthy on?** A basin shaped like a cigar
     rather than a bowl means one knob is pinned and the other is nearly free.
     For ``dipoles.invvee`` the ``length_factor`` at the optimum is determined
     to under 1 % while ``angle_deg`` wanders ~15° for the same SWR — so a
     returned droop angle is close to arbitrary, and two optimizer runs from
     different starts will disagree on it while agreeing on length.
  3. **Why?** ``--rx`` overlays the two level sets whose intersection *is* the
     match: R/Z₀ = 1 and X/Z₀ = 0. Their geometry shows the mechanism the |Γ|
     map only shows the consequence of — for the inv-vee, X=0 runs almost
     vertically (resonance is set by length alone, indifferent to droop) while
     R=1 sweeps diagonally (resistance depends on both), which is exactly why
     the basin is a near-vertical canyon.

``--rx`` is opt-in rather than the default because the R=1 ∩ X=0 reading is
only valid for a pure impedance-match objective. Add a gain term — as
``antennaknobs.opt.optimize(opt_gain=True)`` does — and the optimum leaves the
intersection entirely, at which point the overlay is actively misleading. The
|Γ| map stays honest either way.

Cost. Every grid point is a solve, so an N×N map is N² of them: at ~20 ms for
``dipoles.invvee`` an 81×81 map is ~30 s, but at ~0.85 s for
``arrays.bowtie16x1`` the same map is over three hours. Start coarse.

The exception is a design whose knobs are *network-only* — ``line_wl`` and
``stub_wl`` on the stub-matched vertical change no wire — where the geometry
solve is identical at every grid point. This script detects that case by
comparing ``build_wires()`` across the corners of the sweep, and when it holds
solves the wire ONCE and re-reduces the network per point: 14641 points in
~3 s rather than the ~3 min the same grid costs the slow way.

Usage:
    python scripts/design_space_contour.py --builder dipoles.invvee \
        --params length_factor angle_deg --n 81 --ground pec
    python scripts/design_space_contour.py --builder dipoles.invvee \
        --params length_factor angle_deg --rx --out invvee.png
    python scripts/design_space_contour.py \
        --builder verticals.stub_matched_vertical \
        --params line_wl stub_wl --n 121 --rx
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from antennaknobs.cli import get_builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network_reduce import NetworkReducer
from antennaknobs.opt import _get_path, _set_path

# The SWR values an operator actually thinks in. Labelling contours "2:1"
# rather than "-9.5 dB" is the difference between a chart you read and a
# chart you decode.
SWR_LEVELS = (3.0, 2.0, 1.5, 1.25, 1.1, 1.05, 1.02, 1.01)


def swr_to_db(swr: float) -> float:
    return float(20 * np.log10((swr - 1) / (swr + 1)))


def db_to_swr(db: float) -> float:
    rho = 10 ** (db / 20)
    return float("inf") if rho >= 1 else (1 + rho) / (1 - rho)


def parse_ground(spec: str):
    """'free' | 'pec' | 'finite:<eps>:<sigma>' -> a MomwireEngine ground arg."""
    if spec in ("free", "pec"):
        return None if spec == "free" else "pec"
    kind, _, rest = spec.partition(":")
    if kind in ("finite", "finite-fast"):
        try:
            eps, sigma = (float(v) for v in rest.split(":"))
        except ValueError:
            raise SystemExit(f"bad ground spec {spec!r}: want '{kind}:<eps>:<sigma>'")
        return (kind, eps, sigma)
    raise SystemExit(
        f"unknown ground {spec!r}: want free, pec, or finite:<eps>:<sigma>"
    )


def axis_range(builder, name, explicit):
    """Sweep bounds for one knob: --range if given, else the design's own
    ui_params min/max (the slider range it ships to the workbench, which is
    the author's statement of what values are meaningful), else ±25 %."""
    if explicit is not None:
        return float(explicit[0]), float(explicit[1])
    ui = getattr(builder, "ui_params", {}) or {}
    spec = ui.get(name.split(".")[-1])
    if isinstance(spec, dict) and "min" in spec and "max" in spec:
        return float(spec["min"]), float(spec["max"])
    v = float(_get_path(builder, name))
    return (v * 0.75, v * 1.25) if v else (-1.0, 1.0)


def _wires_of(factory, names, values):
    b = factory()
    for nm, v in zip(names, values, strict=True):
        _set_path(b, nm, float(v))
    return repr(b.build_wires())


def network_only(factory, names, xs, ys) -> bool:
    """True when neither knob moves a wire, so the geometry solve is shared.

    Compared across all four corners of the sweep, not just one pair: a knob
    that happens to leave the geometry alone at one corner but not another
    would otherwise be misread as network-only and silently produce a map of
    the wrong design.
    """
    try:
        ref = _wires_of(factory, names, (xs[0], ys[0]))
        corners = ((xs[-1], ys[0]), (xs[0], ys[-1]), (xs[-1], ys[-1]))
        return all(_wires_of(factory, names, c) == ref for c in corners)
    except Exception:  # noqa: BLE001 — probe harness — a failing case is recorded and the sweep continues
        return False


def sweep(factory, names, xs, ys, ground, *, verbose=True):
    """Z over the (ys, xs) grid — fast path when the knobs are network-only."""
    Z = np.empty((len(ys), len(xs)), dtype=complex)
    t0 = time.time()

    fast = network_only(factory, names, xs, ys)
    if fast:
        b0 = factory()
        for nm, v in zip(names, (xs[0], ys[0]), strict=True):
            _set_path(b0, nm, float(v))
        eng = MomwireEngine(b0, ground=ground)
        if eng._network is None:
            fast = False  # network-only knobs but no network to re-stamp
        else:
            wl = eng._wavelength_for(b0.freq)
            Y = eng._compute_y_matrix(wl)
            port_to_idx, n_total = eng._reducer.port_to_idx, eng._reducer.n_total_ports
            if verbose:
                print(
                    "network-only knobs: solving the wire once, re-reducing per point"
                )
            for j, x in enumerate(xs):
                for i, y in enumerate(ys):
                    b = factory()
                    for nm, v in zip(names, (x, y), strict=True):
                        _set_path(b, nm, float(v))
                    red = NetworkReducer(b.build_network(), port_to_idx, n_total)
                    Z[i, j] = red.driven_impedance(Y, wl)[0]

    if not fast:
        if verbose:
            print(f"full solve per point: {len(xs) * len(ys)} solves")
        for j, x in enumerate(xs):
            for i, y in enumerate(ys):
                b = factory()
                for nm, v in zip(names, (x, y), strict=True):
                    _set_path(b, nm, float(v))
                Z[i, j] = MomwireEngine(b, ground=ground).impedance()[0]
            if verbose and len(xs) > 20 and j % max(1, len(xs) // 8) == 0:
                print(f"  column {j}/{len(xs)}  {time.time() - t0:.0f} s", flush=True)

    if verbose:
        print(f"{len(xs) * len(ys)} points in {time.time() - t0:.1f} s")
    return Z


def plot(xs, ys, Z, names, *, z0, title, rx, out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gdb = 20 * np.log10(np.abs((Z - z0) / (Z + z0)))
    levels = sorted(swr_to_db(s) for s in SWR_LEVELS)
    label = {swr_to_db(s): f"{s:g}:1" for s in SWR_LEVELS}

    fig, ax = plt.subplots(figsize=(8.5, 7))
    ax.contourf(
        xs, ys, gdb, levels=[*levels, 0], cmap="Blues_r", alpha=0.35, extend="min"
    )
    # Every level is negative dB, which matplotlib would dash by default.
    cs = ax.contour(
        xs, ys, gdb, levels=levels, colors="#14507a", linewidths=1.1, linestyles="solid"
    )
    ax.clabel(
        cs,
        fontsize=7.5,
        fmt=lambda v: label.get(min(label, key=lambda k: abs(k - v)), ""),
    )

    if rx:
        R, X = Z.real / z0, Z.imag / z0
        ax.contour(xs, ys, R, levels=[1.0], colors="#1a7f37", linewidths=2.6)
        ax.contour(
            xs,
            ys,
            X,
            levels=[0.0],
            colors="#b3541e",
            linewidths=2.6,
            linestyles="dashed",
        )
        ax.plot([], [], color="#1a7f37", lw=2.6, label="R/Z₀ = 1")
        ax.plot([], [], color="#b3541e", lw=2.6, ls="--", label="X/Z₀ = 0")

    i, j = np.unravel_index(np.argmin(gdb), gdb.shape)
    ax.plot(
        xs[j],
        ys[i],
        "*",
        ms=17,
        color="crimson",
        mec="k",
        mew=0.6,
        zorder=6,
        label="best grid point",
    )
    ax.legend(loc="best", fontsize=8, framealpha=0.92)
    ax.set_xlabel(names[0])
    ax.set_ylabel(names[1])
    ax.set_title(
        f"{title}\nbest ({xs[j]:.4g}, {ys[i]:.4g}) → "
        f"{Z[i, j].real:.1f}{Z[i, j].imag:+.1f}j Ω, "
        f"SWR {db_to_swr(gdb[i, j]):.2f}:1",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")
    return (xs[j], ys[i], Z[i, j], gdb[i, j])


def conditioning(xs, ys, gdb, threshold_swr=2.0):
    """Extent of the sub-threshold region through the best point, per axis.

    This is the number the map exists to produce: a knob whose span is a large
    fraction of its swept range is not actually determined by the optimum, and
    an optimizer's value for it should not be quoted as though it were.
    """
    lim = swr_to_db(threshold_swr)
    i, j = np.unravel_index(np.argmin(gdb), gdb.shape)
    out = {}
    for name, axis, vals, sl in (("x", 0, xs, gdb[i, :]), ("y", 1, ys, gdb[:, j])):
        inside = vals[sl < lim]
        span = float(inside.max() - inside.min()) if inside.size else 0.0
        full = float(vals[-1] - vals[0])
        out[name] = (span, span / full if full else 0.0)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--builder", default="dipoles.invvee", help="design spec, name[:variant]"
    )
    p.add_argument(
        "--params",
        nargs=2,
        default=["length_factor", "angle_deg"],
        metavar=("X", "Y"),
        help="the two knobs (dotted paths allowed)",
    )
    p.add_argument("--xrange", nargs=2, type=float, default=None)
    p.add_argument("--yrange", nargs=2, type=float, default=None)
    p.add_argument("--n", type=int, default=61, help="grid points per axis")
    p.add_argument("--ground", default="free", help="free | pec | finite:<eps>:<sigma>")
    p.add_argument("--z0", type=float, default=50.0)
    p.add_argument("--rx", action="store_true", help="overlay the R=1 and X=0 families")
    p.add_argument("--out", default="design_space.png")
    p.add_argument(
        "--save-grid", default=None, help="also write the raw grid to a .npz"
    )
    a = p.parse_args(argv)

    factory = get_builder(a.builder)
    b = factory()
    ground = parse_ground(a.ground)
    x0, x1 = axis_range(b, a.params[0], a.xrange)
    y0, y1 = axis_range(b, a.params[1], a.yrange)
    xs, ys = np.linspace(x0, x1, a.n), np.linspace(y0, y1, a.n)
    print(
        f"{a.builder}: {a.params[0]} {x0:g}..{x1:g}  {a.params[1]} {y0:g}..{y1:g}  "
        f"{a.n}x{a.n}  ground={a.ground}"
    )

    Z = sweep(factory, a.params, xs, ys, ground)
    if a.save_grid:
        np.savez(a.save_grid, xs=xs, ys=ys, Z=Z, params=np.array(a.params))
        print(f"wrote {a.save_grid}")

    title = f"{a.builder} — {a.params[1]} vs {a.params[0]} (ground={a.ground})"
    plot(xs, ys, Z, a.params, z0=a.z0, title=title, rx=a.rx, out=a.out)

    gdb = 20 * np.log10(np.abs((Z - a.z0) / (Z + a.z0)))
    cond = conditioning(xs, ys, gdb)
    print("\nconditioning at the optimum (extent of the SWR<2 region):")
    for key, name in (("x", a.params[0]), ("y", a.params[1])):
        span, frac = cond[key]
        note = "  <-- weakly determined" if frac > 0.5 else ""
        print(f"  {name:<20s} {span:.4g} ({frac:.0%} of the swept range){note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
