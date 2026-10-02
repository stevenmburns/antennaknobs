"""Startup settings for the web workbench (AK#1492).

A local ``settings.toml`` says where the workbench STARTS: the Settings-menu
switches, the Antenna view's orientation, the ground slots, and the solver
slots. It is read on every ``/capabilities`` request, so an edit
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

    [grounds.Z]              # ground slots X, Y, Z (AK#1794, AK#1801);
    method = "fast"          # [ground] is the older spelling of slot X

    [slots.A]                # solver slots A, B, C; D and E when added (AK#1801)
    backend = "bspline"
    n_per_wire = 15
    model = { degree = 2 }

    [workbench.run_on_pick]  # does picking an analysis start it?
    knob = true              # frequency, pattern, knob, held, convergence, map

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
# starts every switch from the served value and restates none (AK#1858); its
# lib/settings.ts names the keys, pinned to this table by
# tests/test_settings_toml_1492.py.
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
# Sommerfeld, not refl-coef, since AK#1856: the catalog run (2026-10-02, 101
# designs) put refl-coef 10 % off Sommerfeld at the median for antennas whose
# lowest point is under 0.05 wavelength (62 % on verticals.m0agp_invl), for a
# warm per-drag cost of 3 ms at the median. The CLI's default is the same
# ground (cli.CLI_DEFAULT_GROUND).
GROUND_BUILTIN: dict = {
    "enabled": True,
    "type": "finite",
    "method": "sommerfeld",
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
# The solver slots' names, in order (AK#1801): A, B and C are the stock set
# (adapter._DEFAULT_SLOTS), and the workbench's + adds D, then E. Five at most,
# so the family never reaches the ground slots' last chunk (F G H). A slot past
# the stock set exists by its [slots.D] table, empty or not, and starts on the
# roster's first solver. The twin of SOLVER_SLOT_IDS in the frontend's
# lib/backends.ts, pinned to this by tests/test_slot_add_remove_1801.py.
SOLVER_SLOT_IDS: tuple[str, ...] = ("A", "B", "C", "D", "E")
# The ground slots' names, in order (AK#1801): letters, so they read as their
# own family beside the A/B/C solver slots. Chunks of three, each read
# forwards, stepping back through the alphabet: X Y Z, then U V W, then R S T,
# ... down to F G H. The chunk after that would reach the solver slots' A-E,
# so the family stops at 21. The one copy of the sequence in Python; its twin
# is GROUND_SLOT_IDS in the frontend's lib/groundSlots.ts, pinned to this by
# tests/test_ground_slots_1794.py.
GROUND_SLOT_IDS: tuple[str, ...] = tuple(
    chr(ord("X") - 3 * chunk + k) for chunk in range(7) for k in range(3)
)
# The stock ground slots (AK#1794), the twin of the A/B/C solver slots: each
# row is a [grounds.X] table applied over GROUND_BUILTIN, so it goes through
# the same validation as a file's. A file's own [grounds.X] tables can change
# these and add slots past the last one (U, V, W, ...).
#   X: the session default (GROUND_BUILTIN, or the file's [ground]); the page
#      seeds it from a design's own ground (GE/GN) on load.
#   Y: free space.
#   Z: the reflection-coefficient approximation over average soil, by preset
#      name so it stays average if the served soil default ever moves. It was
#      Sommerfeld until AK#1856 made Sommerfeld the default (slot X), and the
#      slots stay three distinct grounds.
STOCK_GROUNDS: tuple[tuple[str, dict], ...] = (
    ("X", {}),
    ("Y", {"enabled": False}),
    ("Z", {"method": "fast", "soil": "average"}),
)

# Does picking an analysis in a chart's picker start it (AC6LA, QRZ 1003328
# #179)? Per KIND of analysis, as the frontend classifies it
# (lib/analysisChart.ts runOnPickKind): a study counts as the kind of analysis
# it is. A frequency sweep and a pattern are a few seconds and start at once,
# as they always have; a knob sweep, a held one (an optimisation at every
# point), a density ladder and a 2-D map are minutes, so the pick only selects
# them and the chart waits for Run, where its settings can be changed first.
# `map` is a valid key before the workbench draws a map (sweep-framework step
# 5), so a file can say it now. A deep link's run=1 always runs (AK#1838).
# The one copy of these defaults (AK#1858); lib/settings.ts's
# RUN_ON_PICK_KINDS names the keys, pinned to this by
# tests/test_settings_run_on_pick.py.
RUN_ON_PICK: tuple[tuple[str, bool], ...] = (
    ("frequency", True),
    ("pattern", True),
    ("knob", False),
    ("held", False),
    ("convergence", False),
    ("map", False),
)
_RUN_ON_PICK_KINDS = tuple(k for k, _ in RUN_ON_PICK)
_WORKBENCH_KEYS = ("run_on_pick",)

_TABLES = ("switches", "antenna_view", "ground", "grounds", "slots", "workbench")
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


def resolve(
    data, cat: Catalog, *, from_file: bool = True, source: Path | str | None = None
) -> tuple[dict, list[str]]:
    """Validate a settings mapping (a parsed file or, with ``from_file=False``,
    a posted body). Returns the resolved settings and the problems found; every
    entry a problem names is dropped, so what comes back is always safe to
    apply. A posted body may not carry ``[engines]`` or ``[capture]``.
    ``source`` (the file's path) is named by the problems that name a file."""
    problems: list[str] = []
    run_on_pick = dict(RUN_ON_PICK)
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
            run_on_pick=run_on_pick,
        ), [
            "settings must be a table of [switches], [antenna_view], [ground], "
            "[grounds], [slots] and [workbench]"
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
        data, table, ground, ground_set, cat, problems, from_file=from_file
    )
    ground = {k: v for k, v in grounds[0].items() if k != "id"}

    slots = _resolve_slots(data, cat, problems)

    run_on_pick.update(_run_on_pick(data, source, problems))

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
            run_on_pick=run_on_pick,
        ),
        problems,
    )


def _resolve_ground(table, base, where, cat: Catalog, problems) -> tuple[dict, list]:
    """One ground (``[ground]`` or a ``[grounds.X]`` table) applied over
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


def _ground_slot_index(key) -> tuple[int, bool] | None:
    """A ``[grounds.X]`` key as its place in GROUND_SLOT_IDS and whether it
    was the older numeric spelling, or None. Before AK#1801 the slots were
    numbered (``[grounds.1]``, ...), on main though in no release; a whole
    number from 1, without a sign or leading zeros, still names the slot at
    that place, so 1, 2, 3 are X, Y, Z and 4 is U."""
    key = str(key)
    if key in GROUND_SLOT_IDS:
        return GROUND_SLOT_IDS.index(key), False
    if key.isdigit() and key[0] != "0" and int(key) <= len(GROUND_SLOT_IDS):
        return int(key) - 1, True
    return None


def _resolve_grounds(
    data, legacy, legacy_ground, legacy_set, cat: Catalog, problems, *, from_file
):
    """The ground slots (AK#1794): the stock set with the file's
    ``[grounds.X]`` tables applied, as a list in GROUND_SLOT_IDS order. Slot X
    is also what the older ``[ground]`` table means; with both, ``[grounds.X]``
    is used and the clash is named. A numeric key is read as its letter
    (AK#1801), with a note when it came from the file; a slot spelled both
    ways is refused by name rather than guessed. Returns the slots, which
    table spelled slot X (``"grounds"`` or ``"ground"``), so a save writes it
    back the same way it came, and the keys slot X's table set."""
    table = data.get("grounds", {})
    if not isinstance(table, Mapping):
        problems.append("[grounds] must be a table of [grounds.X], [grounds.Y], ...")
        table = {}
    stock = {g["id"]: g for g in cat.stock_grounds}
    spellings: dict[int, list[tuple[str, bool, Mapping]]] = {}
    for key, entry in table.items():
        found = _ground_slot_index(key)
        if found is None:
            problems.append(
                f"[grounds.{key}]: not a ground slot (slots are X, Y, Z, then "
                f"U, V, W, then R, S, T, ...: {len(GROUND_SLOT_IDS)} at most)"
            )
        elif not isinstance(entry, Mapping):
            problems.append(f"[grounds.{key}] must be a table")
        else:
            spellings.setdefault(found[0], []).append((str(key), found[1], entry))
    wanted: dict[int, Mapping] = {}
    for i, given in sorted(spellings.items()):
        if len(given) > 1:
            names = " and ".join(f"[grounds.{key}]" for key, _, _ in given)
            problems.append(
                f"{names} both given: they name the same ground slot "
                f"{GROUND_SLOT_IDS[i]}, so neither is used"
            )
        else:
            wanted[i] = given[0][2]
    # Slots run X, Y, Z, U, ... without a gap: a gap would be a slot nobody
    # can see the settings of. Past the first gap nothing applies, and each
    # table dropped there is named.
    ids = {0} | {GROUND_SLOT_IDS.index(k) for k in stock} | set(wanted)
    top = 0
    while top in ids:
        top += 1
    for i in sorted(i for i in wanted if i >= top):
        key = spellings[i][0][0]
        problems.append(
            f"[grounds.{key}]: ground slots run X, Y, Z, U, V, W, ... without "
            f"gaps, and there is no slot {GROUND_SLOT_IDS[top]}; this table is "
            "not used"
        )
    # A numbered table that does apply says what it is read as.
    for i in sorted(i for i in wanted if i < top):
        key, numeric, _ = spellings[i][0]
        if numeric and from_file:
            problems.append(
                f"[grounds.{key}] is read as [grounds.{GROUND_SLOT_IDS[i]}]: ground "
                "slots are named X, Y, Z, ... now, and a save writes the letter"
            )
    grounds = []
    spelling = "ground"
    first_set = legacy_set
    for i in range(top):
        sid = GROUND_SLOT_IDS[i]
        base = {k: v for k, v in stock.get(sid, {}).items() if k != "id"}
        if i == 0 and 0 not in wanted:
            ground = legacy_ground
        elif i in wanted:
            if i == 0:
                spelling = "grounds"
                if legacy:
                    problems.append(
                        f"[ground] and [grounds.{spellings[0][0][0]}] both given: "
                        f"[grounds.{sid}] is used ([ground] is the older spelling "
                        f"of ground slot {sid})"
                    )
            ground, keys = _resolve_ground(
                wanted[i], base or GROUND_BUILTIN, f"[grounds.{sid}]", cat, problems
            )
            if i == 0:
                first_set = keys
        else:
            ground = base
        grounds.append({"id": sid, **ground})
    return grounds, spelling, first_set


def _run_on_pick(data, source, problems) -> dict:
    """The ``[workbench.run_on_pick]`` entries that are valid: a kind of
    analysis (RUN_ON_PICK) set to true or false. An unknown kind or a value
    that is not a boolean is named, with the file, and keeps its default,
    so a typo never silently starts (or stops starting) a sweep."""
    where = f" in {source}" if source else ""
    workbench = data.get("workbench", {})
    if not isinstance(workbench, Mapping):
        problems.append(f"[workbench] must be a table{where}")
        return {}
    for key in workbench:
        if key not in _WORKBENCH_KEYS:
            problems.append(
                f"[workbench] {key}{where}: not a workbench setting "
                f"(known: {_known(_WORKBENCH_KEYS)})"
            )
    table = workbench.get("run_on_pick", {})
    if not isinstance(table, Mapping):
        problems.append(
            f"[workbench] run_on_pick{where} must be a table, "
            "e.g. [workbench.run_on_pick] with knob = true"
        )
        return {}
    out = {}
    for key, value in table.items():
        if key not in _RUN_ON_PICK_KINDS:
            problems.append(
                f"[workbench.run_on_pick] {key}{where}: not a kind of analysis "
                f"(known: {_known(_RUN_ON_PICK_KINDS)})"
            )
        elif not isinstance(value, bool):
            problems.append(
                f"[workbench.run_on_pick] {key} = {value!r}{where}: must be true or false"
            )
        else:
            out[key] = value
    return out


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


def _resolve_slots(data, cat: Catalog, problems) -> dict[str, dict]:
    """The file's ``[slots.A]`` ... tables, each as its override of the slot's
    seed, in SOLVER_SLOT_IDS order. A stock slot appears only when its table
    changes something; a slot past the stock set (AK#1801) appears whenever
    its table is given, empty or not, since the table is what makes it exist.
    Slots run A, B, C, D, E without a gap, as the ground slots do: a table
    past the first gap is named and not used."""
    table = data.get("slots", {})
    if not isinstance(table, Mapping):
        problems.append("[slots] must be a table of [slots.A], [slots.B], ...")
        return {}
    stock = {s["slot"]: s for s in cat.stock_slots}
    wanted: dict[str, Mapping] = {}
    for slot, entry in table.items():
        if slot not in SOLVER_SLOT_IDS:
            problems.append(
                f"[slots.{slot}]: not a solver slot (known: {_known(SOLVER_SLOT_IDS)})"
            )
        elif not isinstance(entry, Mapping):
            problems.append(f"[slots.{slot}] must be a table")
        else:
            wanted[slot] = entry
    top = 0
    while top < len(SOLVER_SLOT_IDS) and (
        SOLVER_SLOT_IDS[top] in stock or SOLVER_SLOT_IDS[top] in wanted
    ):
        top += 1
    out: dict[str, dict] = {}
    for slot in SOLVER_SLOT_IDS:
        if slot not in wanted:
            continue
        if SOLVER_SLOT_IDS.index(slot) >= top:
            problems.append(
                f"[slots.{slot}]: solver slots run A, B, C, D, E without gaps, and "
                f"there is no slot {SOLVER_SLOT_IDS[top]}; this table is not used"
            )
            continue
        override = _resolve_slot(slot, wanted[slot], stock.get(slot), cat, problems)
        if override or slot not in stock:
            out[slot] = override
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
    run_on_pick=None,
) -> dict:
    return {
        "switches": switches,
        "switches_set": switches_set,
        "antenna_view": antenna_view or dict(ANTENNA_VIEW_BUILTIN),
        # Ground slot X, as a server before AK#1794 served it.
        "ground": ground,
        "ground_set": ground_set,
        # Every ground slot, slot X first (AK#1794, AK#1801).
        "grounds": grounds,
        # Which table spelled slot X, for the save to write it the same way.
        "_ground_spelling": ground_spelling,
        "slots": slots,
        # Does picking an analysis start it, per kind (AC6LA #179): always
        # every kind, the file's over the defaults.
        "workbench": {"run_on_pick": run_on_pick or dict(RUN_ON_PICK)},
        "engines": engines or {},
        "capture": capture or {},
    }


def overlay_slots(
    stock: list[dict], overrides: Mapping[str, dict], first: str | None = None
) -> list[dict]:
    """The served solver-slot seeds with the file's slots applied. A new
    backend starts from that backend's own defaults; the same backend keeps
    the stock seed's knobs and takes the file's on top. A slot past the stock
    set (AK#1801) is seeded as the roster's ``first`` solver, as a save
    measures it (``_slot_differences``), with the file's entries on top."""
    have = {seed["slot"] for seed in stock}
    extra = [
        {"slot": slot, "backend": first, "n_per_wire": None, "model": {}}
        for slot in SOLVER_SLOT_IDS
        if slot in overrides and slot not in have
    ]
    out = []
    for seed in [*stock, *extra]:
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
            resolved, problems = resolve(data, cat, source=p)
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
    for given in resolved.get("grounds") or [{"id": "X", **resolved["ground"]}]:
        sid = given["id"]
        start = stock_grounds.get(sid)
        diff = _ground_differences(given, start or GROUND_BUILTIN, cat)
        if diff or start is None:
            grounds[sid] = diff
    ground = {}
    if resolved.get("_ground_spelling", "ground") == "ground":
        ground = grounds.pop("X", {})
    # Each solver slot against its seed, the same way: a slot past the stock
    # set (AK#1801) is written even when empty.
    stock = {s["slot"]: s for s in cat.stock_slots}
    slots = {}
    for slot in SOLVER_SLOT_IDS:
        if slot in resolved["slots"]:
            diff = _slot_differences(resolved["slots"][slot], stock.get(slot), cat)
            if diff or slot not in stock:
                slots[slot] = diff
    run_on_pick = {
        key: resolved["workbench"]["run_on_pick"][key]
        for key, default in RUN_ON_PICK
        if resolved["workbench"]["run_on_pick"][key] != default
    }
    return {
        "switches": switches,
        "antenna_view": antenna_view,
        "ground": ground,
        "grounds": grounds,
        "slots": slots,
        "run_on_pick": run_on_pick,
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
    antenna view, ground and slots, which kinds of analysis a pick starts,
    then the hand-edited tables carried over verbatim. A
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
        (settings.get("grounds") or {}).items(),
        key=lambda kv: GROUND_SLOT_IDS.index(kv[0]),
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
    if settings.get("run_on_pick"):
        lines += ["", "[workbench.run_on_pick]"]
        lines += [f"{k} = {_toml_value(v)}" for k, v in settings["run_on_pick"].items()]
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
