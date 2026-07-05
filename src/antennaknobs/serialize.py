"""Serialise a Builder's knob values back to paste-ready Python source.

After a UI tuning session or a CLI ``optimize`` run you hold a set of knob
values you want to commit into a design's ``default_params`` (or a named
variant). This turns those values into a copy-pasteable assignment block — the
missing piece that hand-rolled tuning scripts used to format inline.

The public entry points are :func:`params_source` (format any param mapping)
and :func:`builder_params_source` (pull the live params off a Builder instance,
drop framework-only keys, and apply each knob's ``ui_params`` display
precision).

Floats default to the shortest round-tripping ``repr`` so the emitted source is
paste-safe — it never silently rounds an optimiser result away. A knob that
declares ``precision`` or ``step`` in ``ui_params`` is rendered at that display
precision instead, which keeps tuned knobs clean without losing the others.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def _precision_for_step(step: float) -> int:
    """Decimal places for a value stepped by ``step``.

    Mirror of ``web.adapter._precision_for_step``, duplicated here so this
    module stays free of the web/solver import chain.
    """
    if step <= 0.0:
        return 3
    return min(6, max(0, -math.floor(math.log10(step))) + 1)


def _precision_map(ui_params: Any) -> dict[str, int]:
    """Per-knob decimal precision derived from a design's ``ui_params``.

    An explicit ``precision`` wins; otherwise it's inferred from the knob's
    ``step``. Knobs with neither (and the reserved non-knob ``ui_params`` keys,
    which aren't mappings) are omitted, so they fall back to the caller's
    default.
    """
    out: dict[str, int] = {}
    if not isinstance(ui_params, Mapping):
        return out
    for key, spec in ui_params.items():
        if not isinstance(spec, Mapping):
            continue
        if "precision" in spec:
            out[key] = int(spec["precision"])
        elif "step" in spec:
            out[key] = _precision_for_step(float(spec["step"]))
    return out


def _fmt_float(value: float, precision: int | None) -> str:
    """Render a float as Python source. ``None`` precision keeps the shortest
    round-tripping repr; an int rounds to that many decimals, trimming trailing
    zeros but always leaving one (so it still reads as a float)."""
    if precision is None:
        return repr(float(value))
    s = f"{value:.{precision}f}"
    if "." in s:
        s = s.rstrip("0")
        if s.endswith("."):
            s += "0"
    return s


def _fmt_value(value: Any, *, precision: int | None, indent: int, level: int) -> str:
    """Recursively format an arbitrary param value as indented Python source.

    Mappings, lists and tuples are expanded one item per line; scalars fall
    back to ``repr`` (which is already valid source for str/complex/bool/int).
    """
    # bool is an int subclass — check it first so True/False don't render as 1/0.
    if isinstance(value, bool):
        return repr(value)
    if isinstance(value, int):
        return repr(value)
    if isinstance(value, float):
        return _fmt_float(value, precision)

    inner = " " * (indent * (level + 1))
    closing = " " * (indent * level)

    if isinstance(value, Mapping):
        if not value:
            return "{}"
        lines = ["{"]
        for k, v in value.items():
            rendered = _fmt_value(
                v, precision=precision, indent=indent, level=level + 1
            )
            lines.append(f"{inner}{k!r}: {rendered},")
        lines.append(f"{closing}}}")
        return "\n".join(lines)

    if isinstance(value, (list, tuple)):
        if not value:
            return "[]" if isinstance(value, list) else "()"
        open_b, close_b = ("[", "]") if isinstance(value, list) else ("(", ")")
        lines = [open_b]
        for v in value:
            rendered = _fmt_value(
                v, precision=precision, indent=indent, level=level + 1
            )
            lines.append(f"{inner}{rendered},")
        lines.append(f"{closing}{close_b}")
        return "\n".join(lines)

    return repr(value)


def params_source(
    params: Mapping[str, Any],
    *,
    name: str = "default_params",
    precision: Mapping[str, int] | None = None,
    default_precision: int | None = None,
    include_ui: bool = True,
    indent: int = 4,
    wrap: str = "dict",
) -> str:
    """Format a param mapping as a paste-ready ``<name> = {...}`` block.

    ``precision`` maps individual top-level knob names to a decimal precision;
    knobs absent from it use ``default_precision`` (``None`` → shortest
    round-trip). Set ``include_ui=False`` to drop the reserved ``ui_params``
    block. ``wrap="mappingproxy"`` emits ``MappingProxyType({...})`` to match
    the catalog's frozen-params convention (the caller must import it).
    """
    precision = precision or {}
    pad = " " * indent
    body_lines = []
    for k, v in params.items():
        if k == "ui_params" and not include_ui:
            continue
        if isinstance(v, float) and not isinstance(v, bool):
            rendered = _fmt_float(v, precision.get(k, default_precision))
        else:
            rendered = _fmt_value(
                v, precision=default_precision, indent=indent, level=1
            )
        body_lines.append(f"{pad}{k!r}: {rendered},")
    body = "\n".join(body_lines)
    if wrap == "mappingproxy":
        return f"{name} = MappingProxyType({{\n{body}\n}})"
    if wrap != "dict":
        raise ValueError(f"unknown wrap {wrap!r}; expected 'dict' or 'mappingproxy'")
    return f"{name} = {{\n{body}\n}}"


def builder_params_source(
    builder: Any,
    *,
    name: str = "default_params",
    include_ui: bool = True,
    default_precision: int | None = None,
    wrap: str = "dict",
    base: Mapping[str, Any] | None = None,
) -> str:
    """Serialise a live Builder instance's knobs to paste-ready source.

    Framework-only params (``nominal_nsegs`` & friends) are dropped — they're
    not design knobs — and each knob's ``ui_params`` display precision is
    applied so tuned values read cleanly. ``default_precision`` rounds the knobs
    that *don't* declare a display precision: leave it ``None`` to dump existing
    literals losslessly, or set it (e.g. 6 after an optimise run) to trim the
    optimiser's sub-tolerance digits.

    ``base``: if given (a params mapping, typically ``default_params``), emit
    only the *deltas* of the builder's params from it — the minimal overlay a
    ``<variant>_params`` block takes (the inverse of ``builder.merge_params``).
    Display precision is still taken from the builder's full ``ui_params``.
    ``None`` (default) emits the complete param set.
    """
    framework = type(builder).FRAMEWORK_PARAMS
    params = {k: v for k, v in builder._params.items() if k not in framework}
    precision = _precision_map(params.get("ui_params"))
    if base is not None:
        from .builder import diff_params

        params = diff_params(dict(base), params)
    return params_source(
        params,
        name=name,
        precision=precision,
        default_precision=default_precision,
        include_ui=include_ui,
        wrap=wrap,
    )
