"""A built design as plain data, and back (AK#2149, unit 1).

A design ``.py`` is code. To run a stranger's on the hosted app, only the
design's own code may run untrusted -- in a sandboxed child process -- and
what crosses back to the server must be DATA the server can check, never
objects or code. This module is that boundary:

- `snapshot(builder)` calls every hook a builder answers (`HOOKS`: wires,
  network, analyses, studies, wire material, bands, planes, ...) and
  `encode`s the results;
- `encode(obj)` turns those results into JSON-able data that still says
  exactly what they were: tuples stay tuples, numpy scalars and arrays keep
  their dtype, complex numbers and non-finite floats are tagged, and every
  spec object carries its type's name;
- `decode(data)` rebuilds them, constructing ONLY the types in an allowlist
  (`allowed_types`): the dataclasses, namedtuples and enums of the modules a
  design's hooks return (`ALLOWED_MODULES`), plus `network.Instance`. A type
  name outside it is refused; decode never imports anything. Objects are
  rebuilt through their constructors, so a frozen spec's ``__post_init__``
  re-checks what the sandbox sent.

The census that fixed the allowlist (2026-11-04): every catalog design and up
to three variants each, 177 builds, return nothing outside these modules.
"""

from __future__ import annotations

import dataclasses
import enum
import importlib
import math
import types
from collections.abc import Mapping

import numpy as np

# The modules whose types a design's hooks return. Only their own classes
# (``cls.__module__`` equal to the module) are admitted, so a re-export cannot
# smuggle in a type from elsewhere.
ALLOWED_MODULES = (
    "antennaknobs.wire_catalog",
    "antennaknobs.analyses",
    "antennaknobs.network",
    "antennaknobs.schematic",
    "antennaknobs.auto_match",
    "antennaknobs.touchstone",
    "momwire.networks._spec",
)

# The instance hooks a builder may answer, all argument-free and returning
# data. `snapshot` calls each one the builder has.
HOOKS = (
    "build_wires",
    "build_tls",
    "build_network",
    "build_analyses",
    "build_studies",
    "build_wire_material",
    "operating_bands",
    "plane_labels",
    "smith_targets",
    "rig_report",
    "readout_rows",
)

_TYPES: dict[str, type] | None = None

# Dataclass fields a constructor DERIVES and refuses to be passed: they are
# encoded beside the init fields and restored after construction, once their
# shape is checked (`_restore_derived`). antennaknobs' Network flattens its
# `Instance` items in __post_init__, so what a design returns holds the FLAT
# branches plus the paths and composites flattening computed; rebuilding from
# the flat branches re-validates the network, and the derived fields bring
# back the power-budget attribution and the schematic's composites.
_DERIVED = {
    "antennaknobs.network:Network": ("branch_paths", "composites", "composite_nodes")
}


def _make_state(cls, f):
    # analyses.State takes its knobs as keyword arguments and stores them as
    # (name, value) pairs; its own checks re-validate every one.
    return cls(f["name"], f.get("design"), variant=f.get("variant"), **dict(f["knobs"]))


# Dataclasses whose constructor is not their fields: how to call it.
_CONSTRUCT = {"antennaknobs.analyses:State": _make_state}


def _is_namedtuple(cls) -> bool:
    return isinstance(cls, type) and issubclass(cls, tuple) and hasattr(cls, "_fields")


def _key(cls) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def allowed_types() -> dict[str, type]:
    """The constructible types, by ``module:qualname``."""
    global _TYPES
    if _TYPES is None:
        out: dict[str, type] = {}
        for name in ALLOWED_MODULES:
            mod = importlib.import_module(name)
            for obj in vars(mod).values():
                if not isinstance(obj, type) or obj.__module__ != name:
                    continue
                if (
                    dataclasses.is_dataclass(obj)
                    or _is_namedtuple(obj)
                    or issubclass(obj, enum.Enum)
                ):
                    out[_key(obj)] = obj
        from .network import Instance

        out[_key(Instance)] = Instance
        _TYPES = out
    return _TYPES


class DesignDataError(ValueError):
    """Data that does not describe a design this module can rebuild."""


# --- encode ------------------------------------------------------------------


def _float(x: float):
    return x if math.isfinite(x) else {"__float__": repr(x)}


def encode(o):
    """JSON-able data for ``o``; refuses (TypeError) anything it cannot
    describe exactly."""
    if o is None or isinstance(o, (bool, str)):
        return o
    if isinstance(o, int) and not isinstance(o, bool) and type(o) is int:
        return o
    if type(o) is float:
        return _float(o)
    if type(o) is complex:
        return {"__complex__": [_float(o.real), _float(o.imag)]}
    if isinstance(o, np.generic):
        v = o.item()
        if isinstance(v, complex):
            v = [_float(v.real), _float(v.imag)]
        elif isinstance(v, float):
            v = _float(v)
        return {"__npscalar__": o.dtype.str, "v": v}
    if isinstance(o, np.ndarray):
        if o.dtype.kind not in "biufc":
            raise TypeError(f"array of dtype {o.dtype} is not design data")
        flat = o.ravel().tolist()
        if o.dtype.kind == "c":
            flat = [[_float(z.real), _float(z.imag)] for z in flat]
        elif o.dtype.kind == "f":
            flat = [_float(x) for x in flat]
        return {"__ndarray__": o.dtype.str, "shape": list(o.shape), "data": flat}
    cls = type(o)
    key = _key(cls)
    allowed = allowed_types()
    if key in allowed and allowed[key] is cls:
        if issubclass(cls, enum.Enum):
            return {"__enum__": key, "value": encode(o.value)}
        if _is_namedtuple(cls):
            return {"__nt__": key, "values": [encode(v) for v in o]}
        if dataclasses.is_dataclass(cls):
            derived = _DERIVED.get(key, ())
            out = {
                "__dc__": key,
                "fields": {
                    f.name: encode(getattr(o, f.name))
                    for f in dataclasses.fields(cls)
                    if f.init and f.name not in derived
                },
            }
            if derived:
                out["derived"] = {name: encode(getattr(o, name)) for name in derived}
            return out
        # network.Instance: a name, the Composite, the port map.
        return {
            "__instance__": key,
            "name": o.name,
            "of": encode(o.of),
            "portmap": {k: encode(v) for k, v in o.portmap.items()},
        }
    if isinstance(o, tuple) and cls is tuple:
        return {"__tuple__": [encode(v) for v in o]}
    if isinstance(o, list) and cls is list:
        return [encode(v) for v in o]
    if isinstance(o, (dict, types.MappingProxyType)) and cls in (
        dict,
        types.MappingProxyType,
    ):
        tag = "__mappingproxy__" if cls is types.MappingProxyType else "__dict__"
        if tag == "__dict__" and all(
            type(k) is str and not k.startswith("__") for k in o
        ):
            return {k: encode(v) for k, v in o.items()}
        return {tag: [[encode(k), encode(v)] for k, v in o.items()]}
    raise TypeError(f"{cls.__module__}.{cls.__qualname__} is not design data")


# --- decode ------------------------------------------------------------------

_MAX_DEPTH = 200


def _unfloat(x):
    if isinstance(x, dict) and set(x) == {"__float__"}:
        s = x["__float__"]
        if s not in ("inf", "-inf", "nan"):
            raise DesignDataError(f"bad non-finite float {s!r}")
        return float(s)
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    raise DesignDataError(f"expected a number, got {type(x).__name__}")


def _dtype(s) -> np.dtype:
    if not isinstance(s, str):
        raise DesignDataError("dtype must be a string")
    dt = np.dtype(s)
    if dt.kind not in "biufc":
        raise DesignDataError(f"dtype {s!r} is not design data")
    return dt


def _type(key) -> type:
    if not isinstance(key, str):
        raise DesignDataError("a type name must be a string")
    cls = allowed_types().get(key)
    if cls is None:
        raise DesignDataError(f"type {key!r} is not one a design may return")
    return cls


def decode(d, _depth: int = 0):
    """Rebuild what `encode` described, constructing allowlisted types only."""
    if _depth > _MAX_DEPTH:
        raise DesignDataError("design data nests too deeply")
    n = _depth + 1
    if d is None or isinstance(d, (bool, str)):
        return d
    if isinstance(d, int):
        return d
    if isinstance(d, float):
        return d
    if isinstance(d, list):
        return [decode(v, n) for v in d]
    if not isinstance(d, dict):
        raise DesignDataError(f"unexpected {type(d).__name__} in design data")
    tags = [k for k in d if k.startswith("__")]
    if not tags:
        return {k: decode(v, n) for k, v in d.items()}
    tag = tags[0]
    try:
        if tag == "__float__":
            return _unfloat(d)
        if tag == "__complex__":
            re, im = d["__complex__"]
            return complex(_unfloat(re), _unfloat(im))
        if tag == "__npscalar__":
            dt = _dtype(d["__npscalar__"])
            v = d["v"]
            if dt.kind == "c":
                v = complex(_unfloat(v[0]), _unfloat(v[1]))
            elif dt.kind == "f":
                v = _unfloat(v)
            return dt.type(v)
        if tag == "__ndarray__":
            dt = _dtype(d["__ndarray__"])
            shape = tuple(int(s) for s in d["shape"])
            data = d["data"]
            if dt.kind == "c":
                data = [complex(_unfloat(a), _unfloat(b)) for a, b in data]
            elif dt.kind == "f":
                data = [_unfloat(x) for x in data]
            arr = np.array(data, dtype=dt)
            if arr.size != math.prod(shape):
                raise DesignDataError("array data does not fill its shape")
            return arr.reshape(shape)
        if tag == "__tuple__":
            return tuple(decode(v, n) for v in d["__tuple__"])
        if tag in ("__dict__", "__mappingproxy__"):
            out = {}
            for k, v in d[tag]:
                k = decode(k, n)
                if isinstance(k, (list, dict)):
                    raise DesignDataError("a mapping key must be hashable")
                out[k] = decode(v, n)
            return types.MappingProxyType(out) if tag == "__mappingproxy__" else out
        if tag == "__enum__":
            return _type(d["__enum__"])(decode(d["value"], n))
        if tag == "__nt__":
            cls = _type(d["__nt__"])
            return cls(*[decode(v, n) for v in d["values"]])
        if tag == "__dc__":
            cls = _type(d["__dc__"])
            if not dataclasses.is_dataclass(cls):
                raise DesignDataError(f"{d['__dc__']!r} is not a dataclass")
            key = d["__dc__"]
            derived = _DERIVED.get(key, ())
            names = {f.name for f in dataclasses.fields(cls) if f.init} - set(derived)
            fields = d["fields"]
            if not isinstance(fields, dict) or not set(fields) <= names:
                raise DesignDataError(f"{key!r}: unknown fields")
            values = {k: decode(v, n) for k, v in fields.items()}
            make = _CONSTRUCT.get(key)
            obj = make(cls, values) if make else cls(**values)
            if derived:
                _restore_derived(obj, key, d.get("derived", {}), n)
            return obj
        if tag == "__instance__":
            cls = _type(d["__instance__"])
            portmap = {str(k): decode(v, n) for k, v in d["portmap"].items()}
            return cls(str(d["name"]), decode(d["of"], n), **portmap)
    except DesignDataError:
        raise
    except (KeyError, TypeError, ValueError, IndexError) as e:
        raise DesignDataError(f"malformed {tag} in design data: {e}") from e
    raise DesignDataError(f"unknown tag {tag!r} in design data")


def _restore_derived(obj, key, data, depth):
    """Put back a Network's flattening results, checking their shape: a path
    string per branch, Composite values, {formal: node} string maps."""
    from .network import Composite

    if key != "antennaknobs.network:Network" or not isinstance(data, dict):
        raise DesignDataError(f"{key!r}: bad derived fields")
    paths = decode(data.get("branch_paths", []), depth)
    comps = decode(data.get("composites", {}), depth)
    nodes = decode(data.get("composite_nodes", {}), depth)
    if not (
        isinstance(paths, list)
        and all(type(p) is str for p in paths)
        and len(paths) == len(obj.branches)
    ):
        raise DesignDataError("branch_paths must be one string per branch")
    if not (
        isinstance(comps, dict)
        and all(type(k) is str and isinstance(v, Composite) for k, v in comps.items())
    ):
        raise DesignDataError("composites must map instance paths to Composites")
    if not (
        isinstance(nodes, dict)
        and all(
            type(k) is str
            and isinstance(v, dict)
            and all(type(a) is str and type(b) is str for a, b in v.items())
            for k, v in nodes.items()
        )
    ):
        raise DesignDataError("composite_nodes must map paths to {formal: node}")
    obj.branch_paths, obj.composites, obj.composite_nodes = paths, comps, nodes


# --- a builder's snapshot -------------------------------------------------------


def snapshot(builder) -> dict:
    """Every hook the builder answers, encoded: ``{hook: data}``. A hook the
    builder does not have is absent; one that raises is recorded as
    ``{"__error__": "<Type>: <message>"}`` so the server can show it."""
    out = {}
    for h in HOOKS:
        f = getattr(builder, h, None)
        if f is None or not callable(f):
            continue
        try:
            out[h] = encode(f())
        except TypeError as e:
            if "is not design data" in str(e):
                raise
            out[h] = {"__error__": f"{type(e).__name__}: {e}"}
        except Exception as e:  # noqa: BLE001 — a design's hook failing is reported, not fatal
            out[h] = {"__error__": f"{type(e).__name__}: {e}"}
    return out


def static(cls) -> dict:
    """The class-level part of a design: its label, docstring, defaults,
    variants and speed of light, encoded."""
    from .cli import list_variants

    variants = {}
    for v in list_variants(cls):
        if v == "default":
            continue
        p = getattr(cls, f"{v}_params", None)
        if isinstance(p, Mapping):
            variants[v] = encode(
                p if isinstance(p, (dict, types.MappingProxyType)) else dict(p)
            )
    return {
        "label": encode(getattr(cls, "label", None)),
        "doc": cls.__doc__ or "",
        "default_params": encode(cls.default_params),
        "variants": variants,
        "c_light_mhz_m": encode(float(cls.c_light_mhz_m)),
    }
