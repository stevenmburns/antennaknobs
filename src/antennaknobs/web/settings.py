"""Startup settings for the web workbench (AK#1492).

A local ``settings.toml`` says where the workbench STARTS: the Settings-menu
switches, the Antenna view's orientation, the ground slots, and the A/B/C
solver slots. It is read on every ``/capabilities`` request, so an edit
applies at the next page load, and it is validated here, once, against the catalogs the
UI itself renders from: the solver roster and its knob specs, and the soil
and terrain presets. A problem
never stops the server. It comes back as a sentence beside the values that did
apply, and the entry it names keeps its built-in default.

    [switches]
    freq_sweep = false

    [antenna_view]
    orientation = "iso"      # auto | top | front | side | iso

    [ground]
    enabled = true
    type = "finite"          # finite | pec | terrain
    method = "sommerfeld"    # fast | sommerfeld | mininec
    soil = "average"         # a soil preset name, or eps_r = ... and sigma = ...
    terrain_preset = "levee"

    [grounds.3]              # ground slots (AK#1794); [ground] is slot 1
    method = "fast"

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
from dataclasses import dataclass, replace
from pathlib import Path

from ..settings_file import SETTINGS_ENV, settings_path

__all__ = ["SETTINGS_ENV", "settings_path"]

_logger = logging.getLogger(__name__)

# (key, label, built-in default). The one copy of these defaults: the frontend
# starts every switch from the served value, and the fallback in the frontend's
# lib/settings.ts is pinned to this table by tests/test_settings_toml_1492.py.
#
# `freq_sweep` and `convergence_sweep` were the Smith view's "freq sweep" and
# "param sweep" checkboxes. Since AK#1757 (sweep-framework step 5 unit 3) the
# workbench has neither checkbox: each analysis chart has its own dwell switch
# ("auto re-run"), and these two keys seed it for a new chart, `freq_sweep`
# for a frequency sweep and `convergence_sweep` for a knob or density sweep.
# They stay valid keys, so an existing file keeps loading without a problem,
# and a save writes back what the file said, never a chart's switch (the
# chart's state is the session's alone).
SWITCHES: tuple[tuple[str, str, bool], ...] = (
    ("live", "Live", True),
    ("freq_sweep", "frequency charts re-run by themselves", True),
    ("convergence_sweep", "knob and density charts re-run by themselves", False),
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
# The Antenna view's orientation on every design load (AK#1737). "auto" is
# the per-design guess (adapter._auto_default_view, or a design's own
# ui_params["default_view"]), which is today's behaviour and the default, so a
# save leaves it out; any other value wins over that guess at EVERY load.
ORIENTATIONS = ("auto", "top", "front", "side", "iso")
ANTENNA_VIEW_BUILTIN: dict = {"orientation": "auto"}
GROUND_TYPES = ("finite", "pec", "terrain")
GROUND_METHODS = ("fast", "sommerfeld", "mininec")
SLOTS = ("A", "B", "C")
# The stock ground slots (AK#1794), the twin of the A/B/C solver slots: each
# row is a [grounds.N] table applied over GROUND_BUILTIN, so it goes through
# the same validation as a file's. Ids are the slot numbers; a file's own
# [grounds.N] tables can change these and add slots past the last one.
#   1: the session default (GROUND_BUILTIN, or the file's [ground]); the page
#      seeds it from a design's own ground (GE/GN) on load.
#   2: free space.
#   3: Sommerfeld over average soil, by preset name so it stays average if the
#      served soil default ever moves.
STOCK_GROUNDS: tuple[tuple[str, dict], ...] = (
    ("1", {}),
    ("2", {"enabled": False}),
    ("3", {"method": "sommerfeld", "soil": "average"}),
)

_TABLES = ("switches", "antenna_view", "ground", "grounds", "slots")
# Tables only a person editing the file sets (antennaknobs.settings_file): a
# path the server executes must never be settable by a web request.
_FILE_TABLES = ("engines", "capture")
_ENGINE_KEYS = ("nec5_exe", "nec2_exe", "nec42_exe")
# The one [engines] entry that is a choice rather than a path.
_ENGINE_CHOICE_KEYS = ("nec42_sommerfeld",)
_CAPTURE_KEYS = ("dir",)
_GROUND_KEYS = ("enabled", "type", "method", "soil", "eps_r", "sigma", "terrain_preset")
_SLOT_KEYS = ("backend", "n_per_wire", "model")
_ANTENNA_VIEW_KEYS = ("orientation",)


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
    # Where a session starts, for a save to leave out (#1497).
    soil_default: tuple[float, float]  # the served soil (eps_r, sigma)
    terrain_default: str | None  # the terrain panel's first preset
    knob_defaults: Mapping[str, object]  # knob -> its served default
    n_per_wire_defaults: Mapping[str, int]  # backend name -> default_n_per_wire
    # The resolved stock ground slots, each {"id": ..., **ground} (AK#1794).
    stock_grounds: tuple[dict, ...] = ()


def catalog(
    *, have_pynec: bool, have_nec5: bool, have_nec2: bool, have_nec42: bool = False
) -> Catalog:
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
        soil_ranges_schema,
        terrain_presets_schema,
    )

    roster = backend_roster(
        have_pynec=have_pynec,
        have_nec5=have_nec5,
        have_nec2=have_nec2,
        have_nec42=have_nec42,
    )
    specs = model_option_specs()
    terrains = [p["name"] for p in terrain_presets_schema()]
    ranges = soil_ranges_schema()
    cat = Catalog(
        backends={b["name"]: tuple(b.get("model_kwargs") or ()) for b in roster},
        aliases=backend_aliases(),
        option_keys=frozenset(specs),
        soils={
            name: (float(eps), float(sig)) for name, _, eps, sig, _ in _SOIL_PRESETS
        },
        eps_r_range=tuple(SOIL_EPS_R_RANGE),
        sigma_range=tuple(SOIL_SIGMA_RANGE),
        terrains=frozenset(terrains),
        stock_slots=tuple(default_slots()),
        soil_default=(
            float(ranges["eps_r"]["default"]),
            float(ranges["sigma"]["default"]),
        ),
        terrain_default=terrains[0] if terrains else None,
        knob_defaults={key: spec["default"] for key, spec in specs.items()},
        n_per_wire_defaults={b["name"]: b["default_n_per_wire"] for b in roster},
    )
    return replace(cat, stock_grounds=stock_grounds(cat))


def stock_grounds(cat: Catalog) -> tuple[dict, ...]:
    """STOCK_GROUNDS resolved against this catalog. A stock row the catalog
    cannot resolve (a renamed soil preset) is logged and keeps what did
    resolve; tests/test_ground_slots_1794.py holds the table clean."""
    problems: list[str] = []
    out = []
    for sid, table in STOCK_GROUNDS:
        ground, _ = _resolve_ground(
            table, GROUND_BUILTIN, f"stock [grounds.{sid}]", cat, problems
        )
        out.append({"id": sid, **ground})
    for problem in problems:
        _logger.warning("settings: %s", problem)
    return tuple(out)


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
    antenna_view = dict(ANTENNA_VIEW_BUILTIN)
    ground = dict(GROUND_BUILTIN)
    ground_set: list[str] = []
    slots: dict[str, dict] = {}

    if not isinstance(data, Mapping):
        return _resolved(
            switches,
            switches_set,
            ground,
            ground_set,
            slots,
            antenna_view,
            grounds=[dict(g) for g in cat.stock_grounds],
        ), [
            "settings must be a table of [switches], [antenna_view], [ground], "
            "[grounds] and [slots]"
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

    table = data.get("antenna_view", {})
    if not isinstance(table, Mapping):
        problems.append("[antenna_view] must be a table")
        table = {}
    for key, value in table.items():
        if key not in _ANTENNA_VIEW_KEYS:
            problems.append(
                f"[antenna_view] {key}: not an antenna view setting "
                f"(known: {_known(_ANTENNA_VIEW_KEYS)})"
            )
        elif value not in ORIENTATIONS:
            problems.append(
                f"[antenna_view] {key} = {value!r}: must be one of {_known(ORIENTATIONS)}"
            )
        else:
            antenna_view[key] = value

    table = data.get("ground", {})
    if not isinstance(table, Mapping):
        problems.append("[ground] must be a table")
        table = {}
    ground, ground_set = _resolve_ground(
        table, GROUND_BUILTIN, "[ground]", cat, problems
    )
    grounds, spelling, ground_set = _resolve_grounds(
        data, table, ground, ground_set, cat, problems
    )
    ground = {k: v for k, v in grounds[0].items() if k != "id"}

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
    if from_file:
        engines.update(_engine_choices(data, problems))
    capture = (
        _paths(data, "capture", _CAPTURE_KEYS, "a capture", problems)
        if from_file
        else {}
    )
    return (
        _resolved(
            switches,
            switches_set,
            ground,
            ground_set,
            slots,
            antenna_view,
            engines,
            capture,
            grounds=grounds,
            ground_spelling=spelling,
        ),
        problems,
    )


def _resolve_ground(table, base, where, cat: Catalog, problems) -> tuple[dict, list]:
    """One ground (``[ground]`` or a ``[grounds.N]`` table) applied over
    ``base``. Returns the ground and the keys the table set."""
    ground = dict(base)
    ground_set: list[str] = []
    for key in table:
        if key not in _GROUND_KEYS:
            problems.append(
                f"{where} {key}: not a ground setting (known: {_known(_GROUND_KEYS)})"
            )
    if "enabled" in table:
        if isinstance(table["enabled"], bool):
            ground["enabled"] = table["enabled"]
            ground_set.append("enabled")
        else:
            problems.append(
                f"{where} enabled = {table['enabled']!r}: must be true or false"
            )
    for key, allowed in (("type", GROUND_TYPES), ("method", GROUND_METHODS)):
        if key in table:
            if table[key] in allowed:
                ground[key] = table[key]
                ground_set.append(key)
            else:
                problems.append(
                    f"{where} {key} = {table[key]!r}: must be one of {_known(allowed)}"
                )
    has_pair = "eps_r" in table or "sigma" in table
    if "soil" in table:
        if has_pair:
            problems.append(
                f"{where} soil and eps_r/sigma both given: the soil preset is used"
            )
        name = table["soil"]
        if name in cat.soils:
            eps, sig = cat.soils[name]
            ground["soil"] = {"eps_r": eps, "sigma": sig}
            ground_set.append("soil")
        else:
            problems.append(
                f"{where} soil = {name!r}: not a soil preset (known: {_known(cat.soils)})"
            )
    elif has_pair:
        eps, sig = table.get("eps_r"), table.get("sigma")
        lo_e, hi_e = cat.eps_r_range
        lo_s, hi_s = cat.sigma_range
        if eps is None or sig is None:
            problems.append(
                f"{where} eps_r and sigma go together: give both, or neither"
            )
        elif not (_is_number(eps) and lo_e <= eps <= hi_e):
            problems.append(
                f"{where} eps_r = {eps!r}: must be a number from {lo_e:g} to {hi_e:g}"
            )
        elif not (_is_number(sig) and lo_s <= sig <= hi_s):
            problems.append(
                f"{where} sigma = {sig!r}: must be a number from {lo_s:g} to {hi_s:g} S/m"
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
                f"{where} terrain_preset = {table['terrain_preset']!r}: not a terrain preset "
                f"(known: {_known(sorted(cat.terrains))})"
            )
    return ground, ground_set


def _ground_id(key) -> int | None:
    """A ``[grounds.N]`` key as its slot number, or None: a whole number from
    1 written without a sign or leading zeros, so ids and keys are one fact."""
    if isinstance(key, str) and key.isdigit() and key[0] != "0":
        return int(key)
    return None


def _resolve_grounds(data, legacy, legacy_ground, legacy_set, cat: Catalog, problems):
    """The ground slots (AK#1794): the stock set with the file's
    ``[grounds.N]`` tables applied, as a list ordered by id. Slot 1 is also
    what the older ``[ground]`` table means; with both, ``[grounds.1]`` is
    used and the clash is named. Returns the slots, which table spelled
    slot 1 (``"grounds"`` or ``"ground"``), so a save writes it back the same
    way it came, and the keys slot 1's table set."""
    table = data.get("grounds", {})
    if not isinstance(table, Mapping):
        problems.append("[grounds] must be a table of [grounds.1], [grounds.2], ...")
        table = {}
    stock = {g["id"]: g for g in cat.stock_grounds}
    wanted: dict[int, Mapping] = {}
    for key, entry in table.items():
        n = _ground_id(key)
        if n is None:
            problems.append(
                f"[grounds.{key}]: not a ground slot (slots are numbered 1, 2, 3, ...)"
            )
        elif not isinstance(entry, Mapping):
            problems.append(f"[grounds.{key}] must be a table")
        else:
            wanted[n] = entry
    # Ids run 1..N without a gap: the tab strip numbers them, and a gap would
    # be a slot nobody can see the settings of. Past the first gap nothing
    # applies, and each table dropped there is named.
    ids = {1} | {int(k) for k in stock} | set(wanted)
    top = 0
    while top + 1 in ids:
        top += 1
    for n in sorted(i for i in wanted if i > top):
        problems.append(
            f"[grounds.{n}]: ground slots are numbered without gaps, and there is "
            f"no slot {top + 1}; this table is not used"
        )
    grounds = []
    spelling = "ground"
    slot1_set = legacy_set
    for n in range(1, top + 1):
        sid = str(n)
        base = {k: v for k, v in stock.get(sid, {}).items() if k != "id"}
        if n == 1 and 1 not in wanted:
            ground = legacy_ground
        elif n in wanted:
            if n == 1:
                spelling = "grounds"
                if legacy:
                    problems.append(
                        "[ground] and [grounds.1] both given: [grounds.1] is used "
                        "([ground] is the older spelling of ground slot 1)"
                    )
            ground, keys = _resolve_ground(
                wanted[n], base or GROUND_BUILTIN, f"[grounds.{sid}]", cat, problems
            )
            if n == 1:
                slot1_set = keys
        else:
            ground = base
        grounds.append({"id": sid, **ground})
    return grounds, spelling, slot1_set


def _paths(data, table_name, keys, what, problems) -> dict:
    """A table of path strings (``[engines]``, ``[capture]``)."""
    table = data.get(table_name, {})
    if not isinstance(table, Mapping):
        problems.append(f"[{table_name}] must be a table")
        return {}
    out = {}
    for key, value in table.items():
        if table_name == "engines" and key in _ENGINE_CHOICE_KEYS:
            continue  # validated by `_engine_choices`
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
            if table_name == "engines" and not _is_program(value):
                # Named, and kept all the same: a drive that is not mounted
                # today may be back tomorrow, and a save must not drop it.
                problems.append(
                    f"[engines] {key} = '{value}': no program at that path, so "
                    "this entry finds no engine"
                )
    return out


def _engine_choices(data, problems) -> dict:
    """The ``[engines]`` entries that are a choice, not a path: today
    ``nec42_sommerfeld`` = 2 or 3. A bad value is named and dropped."""
    table = data.get("engines", {})
    if not isinstance(table, Mapping) or "nec42_sommerfeld" not in table:
        return {}
    value = table["nec42_sommerfeld"]
    if isinstance(value, bool) or value not in (2, 3):
        problems.append(
            f"[engines] nec42_sommerfeld = {value!r}: must be 2 or 3 "
            "(NEC-4.2's Sommerfeld ground card, GN 2 or GN 3)"
        )
        return {}
    return {"nec42_sommerfeld": int(value)}


def _is_program(path: str) -> bool:
    """The test find_exe applies to a candidate (engines/_external.py)."""
    p = Path(path).expanduser()
    return p.is_file() and os.access(p, os.X_OK)


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
    switches,
    switches_set,
    ground,
    ground_set,
    slots,
    antenna_view=None,
    engines=None,
    capture=None,
    *,
    grounds,
    ground_spelling="ground",
) -> dict:
    return {
        "switches": switches,
        "switches_set": switches_set,
        "antenna_view": antenna_view or dict(ANTENNA_VIEW_BUILTIN),
        # Ground slot 1, as a server before AK#1794 served it.
        "ground": ground,
        "ground_set": ground_set,
        # Every ground slot, slot 1 first (AK#1794).
        "grounds": grounds,
        # Which table spelled slot 1, for the save to write it the same way.
        "_ground_spelling": ground_spelling,
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
    # The engine and capture paths are the library's, not the page's, and a
    # leading underscore marks what only a save reads.
    resolved = {
        k: v
        for k, v in resolved.items()
        if k not in _FILE_TABLES and not k.startswith("_")
    }
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


_MISSING = object()


def _differences(resolved: dict, cat: Catalog) -> dict:
    """What a save writes (#1497): only the settings that differ from where
    this version starts a session. A value left at its built-in default stays
    out of the file, so it follows the defaults of a later release instead of
    pinning today's. A save that wrote everything would freeze every default
    the user never touched, and nothing would ever say so."""
    switches = {
        key: resolved["switches"][key]
        for key, _, default in SWITCHES
        if resolved["switches"][key] != default
    }
    # "auto" is the built-in, so it is never written (AK#1737).
    antenna_view = {
        key: value
        for key, value in resolved["antenna_view"].items()
        if value != ANTENNA_VIEW_BUILTIN[key]
    }
    # Each ground slot against the slot it starts as (AK#1794). A stock slot
    # left as it was writes nothing; a slot past the stock set is written even
    # when empty, since the table's presence is what makes the slot exist.
    stock_grounds = {g["id"]: g for g in cat.stock_grounds}
    grounds: dict[str, dict] = {}
    for given in resolved.get("grounds") or [{"id": "1", **resolved["ground"]}]:
        sid = given["id"]
        start = stock_grounds.get(sid)
        diff = _ground_differences(given, start or GROUND_BUILTIN, cat)
        if diff or start is None:
            grounds[sid] = diff
    ground = {}
    if resolved.get("_ground_spelling", "ground") == "ground":
        ground = grounds.pop("1", {})
    stock = {s["slot"]: s for s in cat.stock_slots}
    slots = {}
    for slot in SLOTS:
        if resolved["slots"].get(slot):
            diff = _slot_differences(resolved["slots"][slot], stock.get(slot), cat)
            if diff:
                slots[slot] = diff
    return {
        "switches": switches,
        "antenna_view": antenna_view,
        "ground": ground,
        "grounds": grounds,
        "slots": slots,
    }


def _ground_differences(given: Mapping, start: Mapping, cat: Catalog) -> dict:
    """A ground's entries that differ from the ground it starts as. A soil or
    terrain preset left at None starts at the served soil / the terrain
    panel's first preset, as the page seeds it."""
    out = {
        key: given[key]
        for key in ("enabled", "type", "method")
        if given[key] != start[key]
    }

    def pair(g):
        soil = g.get("soil")
        return (
            (float(soil["eps_r"]), float(soil["sigma"])) if soil else cat.soil_default
        )

    if pair(given) != pair(start):
        # A preset by its name, so a corrected preset reaches the file.
        name = next((n for n, p in cat.soils.items() if p == pair(given)), None)
        if name:
            out["soil"] = name
        else:
            out["eps_r"], out["sigma"] = pair(given)
    terrain = given.get("terrain_preset") or cat.terrain_default
    if terrain != (start.get("terrain_preset") or cat.terrain_default):
        out["terrain_preset"] = terrain
    return out


def _slot_differences(entry: Mapping, seed: Mapping | None, cat: Catalog) -> dict:
    """A slot's entries that differ from what the page starts it on: the
    seed's solver (the roster's first when this server does not offer it, as
    the frontend falls back), that solver's defaults, and the seed's own
    n_per_wire and knobs on top. A different solver starts from its own
    defaults, the way overlay_slots serves it."""
    first = next(iter(cat.backends), None)
    start = seed["backend"] if seed and seed["backend"] in cat.backends else first
    backend = entry.get("backend", start)
    out: dict = {}
    n_start, model_start = None, {}
    if backend != start:
        out["backend"] = backend
    elif seed:
        n_start, model_start = seed.get("n_per_wire"), seed.get("model") or {}
    if n_start is None:
        n_start = cat.n_per_wire_defaults.get(backend)
    knobs = {key: cat.knob_defaults.get(key) for key in cat.backends.get(backend, ())}
    knobs.update({k: v for k, v in model_start.items() if k in knobs})
    if "n_per_wire" in entry and entry["n_per_wire"] != n_start:
        out["n_per_wire"] = entry["n_per_wire"]
    model = {
        key: value
        for key, value in (entry.get("model") or {}).items()
        if knobs.get(key, _MISSING) != value
    }
    if model:
        out["model"] = model
    return out


def dump(settings: dict, kept: Mapping | None = None) -> str:
    """TOML text for what a save writes (``_differences``): its switches,
    antenna view, ground and slots, then the hand-edited tables carried over verbatim. A
    table with nothing in it is left out."""
    stamp = _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        "# antennaknobs workbench startup settings (AK#1492).",
        f"# Written by the Settings menu's 'Save as my defaults' on {stamp}.",
        "# Only what differs from the built-in defaults is written; the rest",
        "# follows the version you run. Hand edits are fine, and the file is",
        "# re-read at every page load.",
    ]
    for table_name in ("switches", "antenna_view", "ground"):
        if settings.get(table_name):
            lines += ["", f"[{table_name}]"]
            lines += [
                f"{k} = {_toml_value(v)}" for k, v in settings[table_name].items()
            ]
    # Written even when empty: a slot past the stock set exists by its table.
    for sid, entry in sorted(
        (settings.get("grounds") or {}).items(), key=lambda kv: int(kv[0])
    ):
        lines += ["", f"[grounds.{sid}]"]
        lines += [f"{k} = {_toml_value(v)}" for k, v in entry.items()]
    for slot, entry in settings["slots"].items():
        lines += ["", f"[slots.{slot}]"]
        lines += [
            f"{key} = {_toml_value(entry[key])}"
            for key in ("backend", "n_per_wire")
            if key in entry
        ]
        if entry.get("model"):
            inner = ", ".join(
                f"{k} = {_toml_value(v)}" for k, v in entry["model"].items()
            )
            lines.append(f"model = {{ {inner} }}")
    # The hand-edited tables the page never writes, carried over verbatim.
    for table_name in _FILE_TABLES:
        table = (kept or {}).get(table_name) or {}
        if table:
            lines += ["", f"[{table_name}]"]
            lines += [f"{k} = {_toml_value(v)}" for k, v in table.items()]
    return "\n".join(lines) + "\n"


def save(body, cat: Catalog, *, path: Path | None = None) -> dict:
    """Validate a posted body and write what differs from the built-in
    defaults as the settings file (#1497). The previous file, if any, is kept
    beside it as ``settings.toml.bak``; the write goes through a temporary
    file and a rename, so a crash never leaves half a file. Returns the payload
    as read back from disk."""
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
            fh.write(dump(_differences(resolved, cat), kept))
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return load(cat, hosted=False, path=p)
