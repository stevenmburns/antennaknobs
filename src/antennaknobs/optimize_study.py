"""A multi-band optimize run kept as a study, and run again (AK#1906).

`analyses.Optimize` is the spec VALUE: the design and knobs the run started
from, the knobs it moved with their ranges, the bands, the form, and what it
found (`analyses.Result`). This module is the seam between that value and
the band optimizer (`web.optimize_bands`, which both the CLI's ``optimize
--bands`` and the workbench's ``/optimize`` call):

- `from_run` makes the value from a finished run (the CLI's ``optimize
  --bands --keep``, the workbench's Keep), so what is kept is always
  ``to_code`` of a value, never text a page sent;
- `run` searches again from the kept start (``analyze --study``), and
  `compare_lines` says what moved against the stored result, which is how a
  newer momwire is checked against an older answer;
- `apply` loads the stored answer without searching (``analyze --study
  --apply``, the workbench's "jump to this"): the stored knob values exactly,
  and each band read once there.

Framework-free: the CLI passes a builder and an engine factory.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence

import numpy as np

from . import analyses as an
from .opt import _get_path, _set_path


def bands_of(o: an.Optimize) -> list:
    """``o``'s bands as the optimizer takes them (`optimize_bands.Band`), a
    band naming no objective at the run's own, SWR."""
    from .web.optimize_bands import Band

    return [
        Band(b.freq, b.objective_in("swr"), b.feed, b.z0, tuple(b.knobs))
        for b in o.bands
    ]


def spec_bands(bands: Sequence) -> tuple[an.Band, ...]:
    """The optimizer's bands (`optimize_bands.Band`) as spec values: SWR,
    the default, is written as no objective at all."""
    return tuple(
        an.Band(
            b.freq_mhz,
            None if b.objective == "swr" else b.objective,
            b.feed,
            b.z0,
            tuple(b.knobs),
        )
        for b in bands
    )


def _z(rec: Mapping) -> tuple[float, float] | None:
    re, im = rec.get("z_re"), rec.get("z_im")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (re, im)):
        return None
    return (float(re), float(im))


def _swr(rec: Mapping) -> float | None:
    v = rec.get("swr")
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


def result_of(res: Mapping, names: Sequence[str]) -> an.Result:
    """What the optimizer's answer ``res`` found, as a spec value: each knob
    in ``names`` (the run's order) at its answer, and the per-band table."""
    params = res.get("params") or {}
    before = res.get("bands_before") or []
    after = res.get("bands_after") or []
    rows = []
    for i, a in enumerate(after):
        b = before[i] if i < len(before) else {}
        rows.append(
            an.BandResult(
                float(a["freq_mhz"]),
                z_before=_z(b),
                z_after=_z(a),
                swr_before=_swr(b),
                swr_after=_swr(a),
            )
        )
    return an.Result(tuple((n, float(params[n])) for n in names), tuple(rows))


def from_run(
    name: str,
    *,
    start: an.State,
    free: Sequence[Mapping],
    bands: Sequence,
    res: Mapping,
    mode: str = "minimax",
    mean_weight: float | None = None,
    tol: float = 0.5,
    max_evals: int | None = None,
    z0: float = 50.0,
    engine: str | None = None,
    ground: str | None = None,
) -> an.Optimize:
    """The kept run: ``start`` (the design and knobs it started from), the
    ``free`` knobs (``[{name, min, max}]``), the optimizer's ``bands`` and
    its answer ``res``. ``mean_weight`` None is the answer's own (what the
    run used)."""
    # The run's own balance, which only the minimax form reads (the others
    # report 0); a run that read none keeps the default.
    w = mean_weight
    if w is None and mode == "minimax":
        w = res.get("mean_weight")
    if w is None:
        w = an.BANDS_MEAN_WEIGHT
    names = [str(f["name"]) for f in free]
    return an.Optimize(
        name,
        start,
        knobs=tuple(
            an.Knob(n, float(f["min"]), float(f["max"]))
            for n, f in zip(names, free, strict=True)
        ),
        bands=spec_bands(bands),
        mode=mode,
        mean_weight=float(w),
        tol=float(tol),
        max_evals=max_evals,
        z0=float(z0),
        engine=engine,
        ground=ground,
        result=result_of(res, names),
    )


def start_state(design: str, builder, fresh) -> an.State:
    """``builder``'s knobs that differ from ``fresh`` (the same design at its
    defaults), as the `an.State` a kept run starts from. ``design`` is the
    registry's spelling, ``family.design[:variant]`` or ``@path``."""
    from .keep import _plain, _same

    if design.startswith("@"):
        name, variant = design, None
    else:
        name, _, variant = design.partition(":")
        variant = None if variant in ("", "default") else variant
    params, defaults = an._params(builder), an._params(fresh)
    # Never the density knob: a run's density is the run's own
    # (``--nominal-nsegs``), as a kept chart's state leaves it out.
    skip = {"ui_params", "nominal_nsegs", an.density_knob(fresh)}
    knobs = {
        k: _plain(v)
        for k, v in params.items()
        if k not in skip and k in defaults and not _same(v, defaults[k])
    }
    return an.State("start", name, variant=variant, **knobs)


def prepared(o: an.Optimize, get_builder: Callable) -> object:
    """``o``'s design at its kept start: the registry's (or the deck's)
    builder, the start's knobs set over its defaults."""
    b = get_builder(o.design)()
    for k, v in o.start.settings.items():
        setattr(b, k, v)
    return b


def free_of(o: an.Optimize) -> list[dict]:
    return [{"name": k.name, "min": k.min, "max": k.max} for k in o.knobs]


def run(
    o: an.Optimize,
    builder,
    factory: Callable,
    *,
    on_progress: Callable[[dict], None] | None = None,
    knob_units: Mapping[str, str] | None = None,
) -> dict:
    """Search again from ``o``'s start on ``builder`` (`prepared`), each
    evaluation one ``factory`` engine solved at every band, as ``optimize
    --bands`` runs; the optimizer's answer, unchanged in shape."""
    from . import band_opt
    from .web.optimize_bands import optimize_bands

    base = {k.name: float(_get_path(builder, k.name)) for k in o.knobs}
    return optimize_bands(
        base,
        free_of(o),
        bands_of(o),
        sweep_fn=band_opt.builder_sweep_fn(builder, factory, o.z0),
        mode=o.mode,
        max_evals=o.max_evals,
        tol=o.tol,
        mean_weight=o.mean_weight,
        on_progress=on_progress,
        knob_units=dict(knob_units or {}),
    )


def apply(o: an.Optimize, builder, factory: Callable) -> dict:
    """``o``'s stored answer on ``builder`` (`prepared`), no search: every
    knob set to exactly the stored value, then ONE build solved at every
    band. ``{params, bands}``, ``bands`` each band's reading there in the
    optimizer's record shape. A run with no stored result is refused."""
    from . import band_opt
    from .web.optimize_bands import _band_record

    if o.result is None:
        raise ValueError(f"{o.name!r} has no stored result to apply")
    values = o.result.values
    for k, v in values.items():
        _set_path(builder, k, v)
    bands = bands_of(o)
    out = band_opt.builder_sweep_fn(builder, factory, o.z0)(
        {}, [b.freq_mhz for b in bands]
    )
    # As the optimizer reads a solve (`optimize_bands.evaluate`): a row per
    # band, a column per feed.
    zs = np.asarray(out["zs"], dtype=complex)
    if zs.ndim == 1:
        zs = zs.reshape(len(bands), -1)
    recs = []
    for i, b in enumerate(bands):
        if b.feed >= zs.shape[1]:
            raise ValueError(
                f"the {b.freq_mhz:g} MHz band is read at feed {b.feed}, but this "
                f"design has {zs.shape[1]}"
            )
        z = complex(zs[i, b.feed])
        recs.append({"index": i, **_band_record(b, z, b.z0 or o.z0)})
    return {"params": dict(values), "bands": recs}


def _fmt_swr(v) -> str:
    return "-" if v is None or not math.isfinite(v) else f"{v:.3f}"


def compare_lines(
    o: an.Optimize, params: Mapping, bands: Sequence[Mapping]
) -> list[str]:
    """What a run (or an `apply`) reads now against ``o``'s stored result:
    each knob and each band's SWR, stored -> now, and the change."""
    if o.result is None:
        return ["(no stored result to compare against)"]
    lines = ["# against the stored result:"]
    stored = o.result.values
    for k in o.knobs:
        was, now = stored.get(k.name), params.get(k.name)
        if was is None or now is None:
            continue
        lines.append(f"  {k.name}: {was:.6g} stored, {now:.6g} now ({now - was:+.3g})")
    rows = {r.freq: r for r in o.result.bands}
    for b in bands:
        r = rows.get(float(b["freq_mhz"]))
        if r is None:
            continue
        now = b.get("swr")
        now = float(now) if isinstance(now, (int, float)) else None
        was = r.swr_after
        delta = (
            f" ({now - was:+.3g})"
            if now is not None and was is not None and math.isfinite(now)
            else ""
        )
        lines.append(
            f"  {b['freq_mhz']:g} MHz: SWR {_fmt_swr(was)} stored, "
            f"{_fmt_swr(now)} now{delta}"
        )
    return lines


def apply_lines(o: an.Optimize, got: Mapping) -> list[str]:
    """``analyze --study --apply``'s printout: the stored knobs and each
    band read there."""
    lines = [f"# {o.name}: the stored result, applied (no search)"]
    for k in o.knobs:
        lines.append(f"{k.name} = {got['params'][k.name]!r}")
    lines.append(f"{'band':>4} {'MHz':>9} {'Z':>20} {'SWR':>8}")
    for r in got["bands"]:
        z = f"{r['z_re']:8.2f}{r['z_im']:+8.2f}j"
        lines.append(
            f"{r['index']:>4} {r['freq_mhz']:>9.4g} {z:>20} {_fmt_swr(r['swr']):>8}"
        )
    return lines
