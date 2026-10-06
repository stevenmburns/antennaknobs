"""The command line's side of a multi-band optimize (AK#1901).

`web.optimize_bands` is framework-free and takes a ``sweep_fn``; this is the
CLI's one: a builder and an engine factory, each evaluation ONE engine built
from the builder at its own ``freq`` and solved at every band's frequency by
the engine's ``impedance_sweep`` (the frequency sweep's one-build path, as
``sweep.swr_curve`` sweeps ``freq``). The builder's ``freq`` is never moved
to evaluate a band, so every band of an evaluation sees one geometry and one
mesh, and a band's own ``freq`` param (a multiband design's sizing anchor)
stays where the design put it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from .opt import _get_path, _set_path

#: The default search box around a knob with no ui_params range of its own:
#: +/- this fraction of its current value. The workbench's Optimize range
#: defaults to the same (frontend ``lib/params.ts`` OPT_SPAN), so the two
#: search the same box (AK 0.97.2).
DEFAULT_SPAN = 0.2


def _ui_meta(builder, name: str) -> Mapping | None:
    """A knob's ``ui_params`` entry: a flat knob's own, a group leaf's
    (``bands.0.length``) in its group's entry under the leaf name."""
    params = getattr(builder, "_params", None)
    ui = params.get("ui_params") if isinstance(params, Mapping) else None
    if not isinstance(ui, Mapping):
        return None
    parts = name.split(".")
    meta = ui.get(parts[0])
    if len(parts) > 1 and isinstance(meta, Mapping):
        meta = meta.get(parts[-1])
    return meta if isinstance(meta, Mapping) else None


def ui_unit(builder, name: str) -> str | None:
    """A knob's unit as its ``ui_params`` names it (an opened deck's SY
    capacitor reads ``pF``), or None."""
    meta = _ui_meta(builder, name)
    unit = meta.get("unit") if meta is not None else None
    return str(unit) if unit else None


def _ui_range(builder, name: str) -> tuple[float, float] | None:
    """A knob's ``ui_params`` min/max, or None."""
    meta = _ui_meta(builder, name)
    if meta is None:
        return None
    lo, hi = meta.get("min"), meta.get("max")
    if lo is None or hi is None or not float(lo) < float(hi):
        return None
    return float(lo), float(hi)


def parse_bounds(specs: Sequence[str]) -> dict[str, tuple[float, float]]:
    """``["NAME=LO:HI", ...]`` -> ``{name: (lo, hi)}``; ValueError by name."""
    out = {}
    for spec in specs:
        name, sep, rng = spec.partition("=")
        lo, sep2, hi = rng.partition(":")
        try:
            a, b = float(lo), float(hi)
        except ValueError:
            a = b = float("nan")
        if not (sep and sep2 and name.strip()) or not a < b:
            raise ValueError(f"{spec!r}: expected NAME=LO:HI with LO < HI")
        out[name.strip()] = (a, b)
    return out


def free_for(
    builder,
    names: Sequence[str],
    span: float = DEFAULT_SPAN,
    bounds: Mapping[str, tuple[float, float]] | None = None,
) -> list[dict]:
    """``[{name, min, max}]`` for ``names`` on ``builder``: an explicit
    ``bounds`` entry, else each knob's ``ui_params`` range when it declares
    both ends, else +/- ``span`` of its current value: the workbench's
    default Optimize range by the same rule (``ParamSpec.auto_range``)."""
    bounds = dict(bounds or {})
    stray = sorted(set(bounds) - set(names))
    if stray:
        raise SystemExit(
            f"optimize --bound: {', '.join(stray)} is not a knob being varied"
        )
    out = []
    for nm in names:
        try:
            v = float(_get_path(builder, nm))
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            raise SystemExit(f"optimize: {nm!r} is not a numeric knob of this design")
        rng = bounds.get(nm) or _ui_range(builder, nm)
        if rng is None:
            if v == 0.0:
                raise SystemExit(
                    f"optimize: {nm} is 0 and has no ui_params min/max to search "
                    "around; give the design a range for it"
                )
            a, b = sorted((v * (1 - span), v * (1 + span)))
            rng = (a, b)
        out.append({"name": nm, "min": rng[0], "max": rng[1]})
    return out


def fixed_frequency_refusal(builder, freqs_mhz) -> str | None:
    """AK#1681: a NEC deck whose reactive NT cards hold at one frequency is
    not modelled at the others; tuning against it would tune a wrong model."""
    deck = getattr(builder, "file_deck_parsed", None)
    advise = getattr(deck, "fixed_frequency_advisory", None)
    note = advise(list(freqs_mhz)) if advise is not None else None
    return None if note is None else note["text"]


def builder_sweep_fn(builder, factory: Callable, z0: float) -> Callable:
    """The CLI's ``sweep_fn``: each knob of the request set on ``builder``
    (dotted group leaves through `opt._set_path`, which rebuilds the group
    rather than mutating the class's defaults), one engine, every band."""
    from .auto_match import tuner_holding_match

    def sweep(req: dict, freqs: list[float]) -> dict:
        for k, v in req.items():
            _set_path(builder, k, v)
        eng = factory(builder)
        zs = eng.impedance_sweep(list(freqs))
        tuner = [tuner_holding_match(eng, float(f)) for f in freqs]
        del eng
        return {"zs": zs, "z0_ohms": float(z0), "tuner": tuner}

    return sweep


def report_lines(res: dict) -> list[str]:
    """The run's per-band before/after table and its verdict."""
    lines = [
        f"# {res['form']} ({res['method']}): "
        f"{'converged' if res['converged'] else 'not converged'}"
        + (f", root: {res['root_status']}" if res.get("root_status") else "")
        + (f" ({res['root_reason']})" if res.get("root_reason") else "")
        + f"; {res['n_evals']} evals, {res['n_solves']} builds, "
        f"{res['n_freq_solves']} band solves"
        + (f", {res['passes']} passes" if res.get("passes") else ""),
        f"{'band':>4} {'MHz':>9} {'objective':>9} {'feed':>4} "
        f"{'Z before':>20} {'Z after':>20} {'SWR':>13} {'residual':>15}",
    ]
    for i, (a, b) in enumerate(
        zip(res["bands_before"], res["bands_after"], strict=True)
    ):

        def z(r):
            return f"{r['z_re']:8.2f}{r['z_im']:+8.2f}j"

        def rr(r):
            v = r["residual"]
            return "-" if v is None else f"{v:.3g}"

        lines.append(
            f"{i:>4} {a['freq_mhz']:>9.4g} {a['objective']:>9} {a['feed']:>4} "
            f"{z(a):>20} {z(b):>20} {a['swr']:>6.3f}>{b['swr']:<6.3f} "
            f"{rr(a):>7}>{rr(b):<7}"
        )
    lines.append(
        f"worst band {res['objective_worst_before']:.4g} -> "
        f"{res['objective_worst_after']:.4g} {res['unit']}, mean "
        f"{res['objective_mean_before']:.4g} -> {res['objective_mean_after']:.4g}"
        + (
            f"; J = (1 - {res['mean_weight']:g}) worst + {res['mean_weight']:g} "
            f"mean {res['objective_before']:.4g} -> {res['objective_after']:.4g}"
            if res["form"] == "minimax"
            else ""
        )
        + f"; worst SWR {res['worst_swr_before']:.4f} -> "
        f"{res['worst_swr_after']:.4f}"
    )
    if res.get("stopped") == "time":
        lines.append(
            f"stopped at the time limit ({res['time_budget_s']:g} s): the answer "
            "is the best point solved by then"
        )
    for b in res.get("at_bound") or []:
        lines.append(
            f"{b['name']} ended at its {b['bound']} ({b['value']:.6g}): the "
            "optimum may lie outside the range; widen it and run again"
        )
    if res.get("far_from_match"):
        lines.append(
            "no band is near a match at the answer (worst SWR "
            f"{res['worst_swr_after']:.4g}): check the knobs' ranges and units "
            "before trusting this optimum"
        )
    if res.get("antiresonant_bands"):
        lines.append(
            "parallel resonance (X = 0 with dX/df < 0) at band(s) "
            + ", ".join(str(i) for i in res["antiresonant_bands"])
        )
    return lines


def apply(builder, params: Mapping[str, float]) -> None:
    """Leave ``builder`` at the run's answer."""
    for k, v in params.items():
        _set_path(builder, k, float(v))
