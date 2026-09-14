"""Startup settings for the web workbench (AK#1492).

A local ``settings.toml`` says where the workbench STARTS: the Settings-menu
switches, the ground, and the A/B/C solver slots. It is read on every
``/capabilities`` request, so an edit applies at the next page load, and it is
validated here, once, against the catalogs the UI itself renders from: the
solver roster and its knob specs, and the soil and terrain presets. A problem
never stops the server. It comes back as a sentence beside the values that did
apply, and the entry it names keeps its built-in default.

    [switches]
    freq_sweep = false

    [ground]
    enabled = true
    type = "finite"          # finite | pec | terrain
    method = "sommerfeld"    # fast | sommerfeld
    soil = "average"         # a soil preset name, or eps_r = ... and sigma = ...
    terrain_preset = "levee"

    [slots.A]
    backend = "bspline"
    n_per_wire = 15
    model = { degree = 2 }

The path is ``$ANTENNAKNOBS_SETTINGS`` when set (the packaged workbench's
``--settings PATH`` sets it), else ``~/.antennaknobs/settings.toml``. The hosted
instance reads no file and writes none.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import math
import os
import shutil
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..settings_file import SETTINGS_ENV, settings_path

__all__ = ["SETTINGS_ENV", "settings_path"]

_logger = logging.getLogger(__name__)

# (key, label, built-in default). The one copy of these defaults: the frontend
# starts every switch from the served value, and the fallback in the frontend's
# lib/settings.ts is pinned to this table by tests/test_settings_toml_1492.py.
SWITCHES: tuple[tuple[str, str, bool], ...] = (
    ("live", "Live", True),
    ("freq_sweep", "freq sweep", True),
    ("convergence_sweep", "convergence sweep", False),
    ("pattern_renorm", "norm check", True),
    ("refine", "adaptive resolution", True),
    ("heatmap_currents", "heatmapped currents", True),
    ("current_waveforms", "current waveforms", False),
    ("wire_labels", "wire labels", False),
    ("feed_labels", "feed labels", True),
)
_SWITCH_KEYS = tuple(k for k, _, _ in SWITCHES)

# The ground the workbench starts on when the file says nothing. `soil` and
# `terrain_preset` are None: the soil then starts at the served soil default
# (DEFAULT_GROUND, which the request path also falls back to) and the terrain
# panel at its own first preset.
GROUND_BUILTIN: dict = {
    "enabled": True,
    "type": "finite",
    "method": "fast",
    "soil": None,
    "terrain_preset": None,
}
GROUND_TYPES = ("finite", "pec", "terrain")
GROUND_METHODS = ("fast", "sommerfeld")
SLOTS = ("A", "B", "C")

_TABLES = ("switches", "ground", "slots")
# Tables only a person editing the file sets (antennaknobs.settings_file): a
# path the server executes must never be settable by a web request.
_FILE_TABLES = ("engines", "capture")
_ENGINE_KEYS = ("nec5_exe", "nec2_exe")
_CAPTURE_KEYS = ("dir",)
_GROUND_KEYS = ("enabled", "type", "method", "soil", "eps_r", "sigma", "terrain_preset")
_SLOT_KEYS = ("backend", "n_per_wire", "model")


class SettingsError(ValueError):
    """A save refused because the posted settings do not validate."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Catalog:
    """What the file is checked against, taken from the served catalogs."""

    backends: Mapping[str, tuple[str, ...]]  # backend name -> the kwargs it takes
    aliases: Mapping[str, str]  # retired backend name -> its successor
    option_keys: frozenset[str]
    soils: Mapping[str, tuple[float, float]]  # preset name -> (eps_r, sigma)
    eps_r_range: tuple[float, float]
    sigma_range: tuple[float, float]
    terrains: frozenset[str]
    stock_slots: tuple[dict, ...]


def catalog(*, have_pynec: bool, have_nec5: bool, have_nec2: bool) -> Catalog:
    """The catalog for this request, from the same adapter functions
    ``/capabilities`` serves, so a file can name exactly what the UI offers."""
    from .adapter import (
        _SOIL_PRESETS,
        SOIL_EPS_R_RANGE,
        SOIL_SIGMA_RANGE,
        backend_aliases,
        backend_roster,
        default_slots,
        model_option_specs,
        terrain_presets_schema,
    )

    roster = backend_roster(
        have_pynec=have_pynec, have_nec5=have_nec5, have_nec2=have_nec2
    )
    return Catalog(
        backends={b["name"]: tuple(b.get("model_kwargs") or ()) for b in roster},
        aliases=backend_aliases(),
        option_keys=frozenset(model_option_specs()),
        soils={
            name: (float(eps), float(sig)) for name, _, eps, sig, _ in _SOIL_PRESETS
        },
        eps_r_range=tuple(SOIL_EPS_R_RANGE),
        sigma_range=tuple(SOIL_SIGMA_RANGE),
        terrains=frozenset(p["name"] for p in terrain_presets_schema()),
        stock_slots=tuple(default_slots()),
    )


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _known(keys) -> str:
    return ", ".join(keys)


def resolve(data, cat: Catalog, *, from_file: bool = True) -> tuple[dict, list[str]]:
    """Validate a settings mapping (a parsed file or, with ``from_file=False``,
    a posted body). Returns the resolved settings and the problems found; every
    entry a problem names is dropped, so what comes back is always safe to
    apply. A posted body may not carry ``[engines]`` or ``[capture]``."""
    problems: list[str] = []
    switches = {k: d for k, _, d in SWITCHES}
    switches_set: list[str] = []
    ground = dict(GROUND_BUILTIN)
    ground_set: list[str] = []
    slots: dict[str, dict] = {}

    if not isinstance(data, Mapping):
        return _resolved(switches, switches_set, ground, ground_set, slots), [
            "settings must be a table of [switches], [ground] and [slots]"
        ]
    allowed = _TABLES + _FILE_TABLES if from_file else _TABLES
    for key in data:
        if key in _FILE_TABLES and not from_file:
            problems.append(
                f"[{key}] is set by editing settings.toml by hand, never from the page"
            )
        elif key not in allowed:
            problems.append(f"unknown table [{key}] (known: {_known(allowed)})")

    table = data.get("switches", {})
    if not isinstance(table, Mapping):
        problems.append("[switches] must be a table")
        table = {}
    for key, value in table.items():
        if key not in _SWITCH_KEYS:
            problems.append(
                f"[switches] {key}: not a switch (known: {_known(_SWITCH_KEYS)})"
            )
        elif not isinstance(value, bool):
            problems.append(f"[switches] {key} = {value!r}: must be true or false")
        else:
            switches[key] = value
            switches_set.append(key)

    table = data.get("ground", {})
    if not isinstance(table, Mapping):
        problems.append("[ground] must be a table")
        table = {}
    for key in table:
        if key not in _GROUND_KEYS:
            problems.append(
                f"[ground] {key}: not a ground setting (known: {_known(_GROUND_KEYS)})"
            )
    if "enabled" in table:
        if isinstance(table["enabled"], bool):
            ground["enabled"] = table["enabled"]
            ground_set.append("enabled")
        else:
            problems.append(
                f"[ground] enabled = {table['enabled']!r}: must be true or false"
            )
    for key, allowed in (("type", GROUND_TYPES), ("method", GROUND_METHODS)):
        if key in table:
            if table[key] in allowed:
                ground[key] = table[key]
                ground_set.append(key)
            else:
                problems.append(
                    f"[ground] {key} = {table[key]!r}: must be one of {_known(allowed)}"
                )
    has_pair = "eps_r" in table or "sigma" in table
    if "soil" in table:
        if has_pair:
            problems.append(
                "[ground] soil and eps_r/sigma both given: the soil preset is used"
            )
        name = table["soil"]
        if name in cat.soils:
            eps, sig = cat.soils[name]
            ground["soil"] = {"eps_r": eps, "sigma": sig}
            ground_set.append("soil")
        else:
            problems.append(
                f"[ground] soil = {name!r}: not a soil preset (known: {_known(cat.soils)})"
            )
    elif has_pair:
        eps, sig = table.get("eps_r"), table.get("sigma")
        lo_e, hi_e = cat.eps_r_range
        lo_s, hi_s = cat.sigma_range
        if eps is None or sig is None:
            problems.append(
                "[ground] eps_r and sigma go together: give both, or neither"
            )
        elif not (_is_number(eps) and lo_e <= eps <= hi_e):
            problems.append(
                f"[ground] eps_r = {eps!r}: must be a number from {lo_e:g} to {hi_e:g}"
            )
        elif not (_is_number(sig) and lo_s <= sig <= hi_s):
            problems.append(
                f"[ground] sigma = {sig!r}: must be a number from {lo_s:g} to {hi_s:g} S/m"
            )
        else:
            ground["soil"] = {"eps_r": float(eps), "sigma": float(sig)}
            ground_set.append("soil")
    if "terrain_preset" in table:
        if table["terrain_preset"] in cat.terrains:
            ground["terrain_preset"] = table["terrain_preset"]
            ground_set.append("terrain_preset")
        else:
            problems.append(
                f"[ground] terrain_preset = {table['terrain_preset']!r}: not a terrain preset "
                f"(known: {_known(sorted(cat.terrains))})"
            )

    table = data.get("slots", {})
    if not isinstance(table, Mapping):
        problems.append("[slots] must be a table of [slots.A], [slots.B], [slots.C]")
        table = {}
    stock = {s["slot"]: s for s in cat.stock_slots}
    for slot, entry in table.items():
        if slot not in SLOTS:
            problems.append(
                f"[slots.{slot}]: not a solver slot (known: {_known(SLOTS)})"
            )
            continue
        if not isinstance(entry, Mapping):
            problems.append(f"[slots.{slot}] must be a table")
            continue
        override = _resolve_slot(slot, entry, stock.get(slot), cat, problems)
        if override:
            slots[slot] = override

    engines = (
        _paths(data, "engines", _ENGINE_KEYS, "an engine", problems)
        if from_file
        else {}
    )
    capture = (
        _paths(data, "capture", _CAPTURE_KEYS, "a capture", problems)
        if from_file
        else {}
    )
    return (
        _resolved(switches, switches_set, ground, ground_set, slots, engines, capture),
        problems,
    )


def _paths(data, table_name, keys, what, problems) -> dict:
    """A table of path strings (``[engines]``, ``[capture]``)."""
    table = data.get(table_name, {})
    if not isinstance(table, Mapping):
        problems.append(f"[{table_name}] must be a table")
        return {}
    out = {}
    for key, value in table.items():
        if key not in keys:
            problems.append(
                f"[{table_name}] {key}: not {what} setting (known: {_known(keys)})"
            )
        elif not (isinstance(value, str) and value.strip()):
            problems.append(
                f"[{table_name}] {key} = {value!r}: must be a path (a string)"
            )
        else:
            out[key] = value
    return out


def _resolve_slot(slot, entry, stock, cat: Catalog, problems) -> dict:
    where = f"[slots.{slot}]"
    for key in entry:
        if key not in _SLOT_KEYS:
            problems.append(
                f"{where} {key}: not a slot setting (known: {_known(_SLOT_KEYS)})"
            )
    out: dict = {}
    backend = stock["backend"] if stock else None
    if "backend" in entry:
        name = cat.aliases.get(entry["backend"], entry["backend"])
        if name in cat.backends:
            out["backend"] = backend = name
        else:
            problems.append(
                f"{where} backend = {entry['backend']!r}: not a solver this server offers "
                f"(offered: {_known(cat.backends)}); the slot keeps its stock solver"
            )
            return {}
    if "n_per_wire" in entry:
        n = entry["n_per_wire"]
        if isinstance(n, int) and not isinstance(n, bool) and n >= 1:
            out["n_per_wire"] = n
        else:
            problems.append(
                f"{where} n_per_wire = {n!r}: must be a whole number of at least 1"
            )
    if "model" in entry:
        model = entry["model"]
        if not isinstance(model, Mapping):
            problems.append(
                f"{where} model must be a table, e.g. model = {{ degree = 2 }}"
            )
        else:
            takes = cat.backends.get(backend, ())
            kept = {}
            for key, value in model.items():
                if key not in cat.option_keys or key not in takes:
                    problems.append(
                        f"{where} model.{key}: not a knob the {backend} solver takes"
                    )
                elif not isinstance(value, (bool, int, float, str)):
                    problems.append(
                        f"{where} model.{key} = {value!r}: must be a number, string or true/false"
                    )
                else:
                    kept[key] = value
            out["model"] = kept
    return out


def _resolved(
    switches, switches_set, ground, ground_set, slots, engines=None, capture=None
) -> dict:
    return {
        "switches": switches,
        "switches_set": switches_set,
        "ground": ground,
        "ground_set": ground_set,
        "slots": slots,
        "engines": engines or {},
        "capture": capture or {},
    }


def overlay_slots(stock: list[dict], overrides: Mapping[str, dict]) -> list[dict]:
    """The served A/B/C seeds with the file's slots applied. A new backend
    starts from that backend's own defaults; the same backend keeps the stock
    seed's knobs and takes the file's on top."""
    out = []
    for seed in stock:
        o = overrides.get(seed["slot"])
        s = {**seed, "model": dict(seed.get("model") or {})}
        if o:
            if "backend" in o and o["backend"] != seed["backend"]:
                s.update(backend=o["backend"], n_per_wire=None, model={})
            if "n_per_wire" in o:
                s["n_per_wire"] = o["n_per_wire"]
            if "model" in o:
                s["model"].update(o["model"])
        out.append(s)
    return out


_last_logged: tuple[str, ...] = ()


def load(cat: Catalog, *, hosted: bool, path: Path | None = None) -> dict:
    """The ``ui_defaults`` payload ``/capabilities`` serves."""
    global _last_logged
    p = None if hosted else (path or settings_path())
    resolved, problems = resolve({}, cat)
    exists = bool(p and p.is_file())
    if exists:
        try:
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            problems = [
                f"{p.name} is not valid TOML ({exc}); the built-in defaults apply"
            ]
        except OSError as exc:
            problems = [f"{p} could not be read ({exc}); the built-in defaults apply"]
        else:
            resolved, problems = resolve(data, cat)
    if tuple(problems) != _last_logged:
        for problem in problems:
            _logger.warning("settings: %s", problem)
        _last_logged = tuple(problems)
    # The engine and capture paths are the library's, not the page's.
    resolved = {k: v for k, v in resolved.items() if k not in _FILE_TABLES}
    return {
        "path": str(p) if p else None,
        "exists": exists,
        "writable": not hosted,
        "switch_labels": [
            {"key": k, "label": label, "default": d} for k, label, d in SWITCHES
        ],
        **resolved,
        "problems": problems,
    }


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = repr(value)
        return text if any(c in text for c in ".en") else f"{text}.0"
    return json.dumps(str(value))


def dump(resolved: dict, kept: Mapping | None = None) -> str:
    """TOML text for a resolved settings mapping: every switch, the ground as
    posted, and the slots. A model knob left at null (the solver decides) is
    written as absent, which reads back the same way."""
    stamp = _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        "# antennaknobs workbench startup settings (AK#1492).",
        f"# Written by the Settings menu's 'Save as my defaults' on {stamp}.",
        "# Hand edits are fine: the file is re-read at every page load.",
        "",
        "[switches]",
    ]
    lines += [f"{k} = {_toml_value(resolved['switches'][k])}" for k in _SWITCH_KEYS]
    ground = resolved["ground"]
    lines += ["", "[ground]"]
    for key in ("enabled", "type", "method"):
        lines.append(f"{key} = {_toml_value(ground[key])}")
    if ground.get("soil"):
        lines.append(f"eps_r = {_toml_value(float(ground['soil']['eps_r']))}")
        lines.append(f"sigma = {_toml_value(float(ground['soil']['sigma']))}")
    if ground.get("terrain_preset"):
        lines.append(f"terrain_preset = {_toml_value(ground['terrain_preset'])}")
    for slot in SLOTS:
        entry = resolved["slots"].get(slot)
        if not entry:
            continue
        lines += ["", f"[slots.{slot}]"]
        if "backend" in entry:
            lines.append(f"backend = {_toml_value(entry['backend'])}")
        if entry.get("n_per_wire") is not None:
            lines.append(f"n_per_wire = {_toml_value(entry['n_per_wire'])}")
        model = {k: v for k, v in (entry.get("model") or {}).items() if v is not None}
        if model:
            inner = ", ".join(f"{k} = {_toml_value(v)}" for k, v in model.items())
            lines.append(f"model = {{ {inner} }}")
    # The hand-edited tables the page never writes, carried over verbatim.
    for table_name in _FILE_TABLES:
        table = (kept or {}).get(table_name) or {}
        if table:
            lines += ["", f"[{table_name}]"]
            lines += [f"{k} = {_toml_value(v)}" for k, v in table.items()]
    return "\n".join(lines) + "\n"


def save(body, cat: Catalog, *, path: Path | None = None) -> dict:
    """Validate a posted body and write it as the settings file. The previous
    file, if any, is kept beside it as ``settings.toml.bak``; the write goes
    through a temporary file and a rename, so a crash never leaves half a file.
    Returns the payload as read back from disk."""
    if isinstance(body, Mapping) and isinstance(body.get("slots"), Mapping):
        body = {
            **body,
            "slots": {
                slot: {
                    **entry,
                    "model": {
                        k: v
                        for k, v in (entry.get("model") or {}).items()
                        if v is not None
                    },
                }
                if isinstance(entry, Mapping)
                else entry
                for slot, entry in body["slots"].items()
            },
        }
    resolved, problems = resolve(body, cat, from_file=False)
    if problems:
        raise SettingsError(problems)
    p = path or settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    kept: dict = {}
    if p.is_file():
        shutil.copy2(p, p.with_name(p.name + ".bak"))
        # Keep the hand-edited [engines] and [capture]: the page never sends
        # them, and a save must not drop a path the user set. A file that no
        # longer parses keeps nothing here, but its .bak copy keeps it all.
        try:
            previous, _ = resolve(tomllib.loads(p.read_text(encoding="utf-8")), cat)
        except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError):
            previous = {}
        kept = {t: previous.get(t, {}) for t in _FILE_TABLES}
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".settings-", suffix=".toml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(dump(resolved, kept))
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return load(cat, hosted=False, path=p)
