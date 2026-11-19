"""What a momwire fill did, packed for the workbench (AK#2327).

momwire's ``solver.fill_report()`` (momwire#2016) describes ONE solver. A web
solve can build several: a network design's port solver fills, and its excited
solver reads the same matrix back. This module adds those up into one bounded,
JSON-ready payload.

Reading is all it does. ``fill_report()`` runs no census, and nothing here
asks for analysis the request did not ask for, so with reuse off the report
costs a few dictionary reads.

THE PAYLOAD (``version`` 1)::

    {
      "version": 1,
      "scope": "solve" | "sweep",
      "source": "fresh" | "cached" | "refused",
      "solved_at": unix seconds of the solve the numbers describe,
      "solver": "RazorSolver",
      "fills", "frequencies",        # totals over this request's solvers
      "times": {"fill_s", "factor_s", "census_s"},   # totals, likewise
      "no_fill": bool,               # the matrix came from memory: no counts
      "points_cached": int,          # a sweep's points no solver ran for
      "route": "dense" | "sector" | ... | None,      # the last real fill's
      "reuse_asked": bool,
      "reuse": None | {...},         # momwire's block, less its wire lists
      "sector": None | {"n_sectors", "axial", "blocks": [{"size", "count"}],
                        "computed_pairs", "pairs", "declined"},
      "map": None | {"kind": "reuse", "rows", "computed", "reused", "near"}
                  | {"kind": "sector", "rows"}
                  | {"kind": "unavailable", "reason"},
    }

THE BOUND. A map never has more than `MAX_MAP_ROWS` rows: past that, contiguous
wires share a row and their counts add. `computed + reused + near == pairs`
still holds in every cell. Past `MAX_MAP_WIRES` momwire's map is not read at
all, because the lists it builds grow as the square of the wire count.
"""

from __future__ import annotations

import time
from collections import Counter
from itertools import pairwise

import numpy as np

#: The most rows (and columns) a map carries to the browser.
MAX_MAP_ROWS = 32
#: The most wires whose map is read from momwire at all.
MAX_MAP_WIRES = 400
#: A row label's longest spelling.
MAX_LABEL = 28

_REUSE_KEYS = (
    "state",
    "declined",
    "pairs",
    "computed",
    "reused",
    "near",
    "kernel_evals",
    "families",
    "uncounted",
    "plan_bytes",
    "census_peak_bytes",
)


def reads_fill_report(solver_cls) -> bool:
    """Whether the installed momwire's ``solver_cls`` reports its fill: a live
    probe of the class, never a version comparison."""
    return callable(getattr(solver_cls, "fill_report", None))


def _short(label: str) -> str:
    return label if len(label) <= MAX_LABEL else label[: MAX_LABEL - 1] + "…"


def _point_key(p) -> tuple:
    return tuple(round(float(x), 6) for x in p)


def polyline_names(polylines, authored) -> list[str]:
    """One display name per solved wire. ``authored`` is the design's wires as
    ``(p0, p1, name, tag)``: a wire the design named reads by that name, an
    opened deck's by its GW tag, and any other by its number.

    The walk merges straight runs, so one solved wire can hold several authored
    ones; they are matched on their end points."""
    owner = {}
    for index, polyline in enumerate(polylines):
        points = [_point_key(p) for p in polyline]
        for a, b in pairwise(points):
            owner[frozenset((a, b))] = index
    names: list[list[str]] = [[] for _ in polylines]
    tags: list[list[str]] = [[] for _ in polylines]
    for p0, p1, name, tag in authored:
        index = owner.get(frozenset((_point_key(p0), _point_key(p1))))
        if index is None:
            continue
        if name and name not in names[index]:
            names[index].append(str(name))
        if tag is not None and str(tag) not in tags[index]:
            tags[index].append(str(tag))
    out = []
    for index in range(len(polylines)):
        if names[index]:
            out.append(_short("+".join(names[index])))
        elif tags[index]:
            word = "tag" if len(tags[index]) == 1 else "tags"
            out.append(_short(f"{word} {'+'.join(tags[index])}"))
        else:
            out.append(f"wire {index + 1}")
    return out


def _spans(n: int) -> list[tuple[int, int]]:
    """``n`` wires as at most `MAX_MAP_ROWS` contiguous half-open spans."""
    if n <= MAX_MAP_ROWS:
        return [(i, i + 1) for i in range(n)]
    edges = np.linspace(0, n, MAX_MAP_ROWS + 1).round().astype(int)
    return [(int(a), int(b)) for a, b in pairwise(edges)]


def _row_label(names, a: int, b: int) -> str:
    return names[a] if b - a == 1 else f"{names[a]} – {names[b - 1]}"


def _reuse_map(wires, names, segments) -> dict:
    labels = [int(w) for w in wires["labels"]]
    shown = [names[w] if w < len(names) else f"wire {w + 1}" for w in labels]
    sizes = [segments[w] if w < len(segments) else 0 for w in labels]
    spans = _spans(len(labels))
    starts = [a for a, _b in spans]

    def binned(key):
        grid = np.asarray(wires[key], dtype=np.int64)
        grid = np.add.reduceat(np.add.reduceat(grid, starts, axis=0), starts, axis=1)
        return grid.tolist()

    return {
        "kind": "reuse",
        "rows": [
            {
                "label": _short(_row_label(shown, a, b)),
                "first": labels[a],
                "last": labels[b - 1],
                "wires": b - a,
                "segments": int(sum(sizes[a:b])),
            }
            for a, b in spans
        ],
        "computed": binned("computed"),
        "reused": binned("reused"),
        "near": binned("near"),
    }


def _sector_row(label, members, segments, sectors) -> dict:
    return {
        "label": _short(label),
        "first": min(members),
        "last": max(members),
        "wires": len(members),
        "segments": int(sum(segments[w] for w in members if w < len(segments))),
        "sector_first": min(sectors),
        "sector_last": max(sectors),
        # Sector 0 and the axis are the rows the fill computed.
        "role": "computed" if max(sectors) <= 0 else "rotation",
    }


def _sector_map(wire_sector, names, segments) -> dict:
    if len(wire_sector) <= MAX_MAP_ROWS:
        return {
            "kind": "sector",
            "rows": [
                _sector_row(
                    names[w] if w < len(names) else f"wire {w + 1}",
                    [w],
                    segments,
                    [s],
                )
                for w, s in enumerate(wire_sector)
            ],
        }
    # Too many wires for a row each: a row per sector, the axis first, and
    # past the row bound the rotated sectors share rows.
    members: dict[int, list[int]] = {}
    for w, s in enumerate(wire_sector):
        members.setdefault(int(s), []).append(w)
    rows = []
    if -1 in members:
        rows.append(_sector_row("axis", members[-1], segments, [-1]))
    if 0 in members:
        rows.append(_sector_row("sector 1", members[0], segments, [0]))
    rotated = sorted(s for s in members if s > 0)
    room = MAX_MAP_ROWS - len(rows)
    edges = np.linspace(0, len(rotated), min(room, len(rotated)) + 1).round()
    for a, b in pairwise(edges.astype(int).tolist()):
        run = rotated[a:b]
        wires = [w for s in run for w in members[s]]
        label = (
            f"sector {run[0] + 1}"
            if len(run) == 1
            else f"sectors {run[0] + 1} – {run[-1] + 1}"
        )
        rows.append(_sector_row(label, wires, segments, run))
    return {"kind": "sector", "rows": rows}


def _pack_map(raw: dict, names, segments) -> dict | None:
    sector = raw.get("sector")
    if sector and sector.get("wire_sector"):
        return _sector_map(sector["wire_sector"], names, segments)
    reuse = raw.get("reuse")
    wires = reuse.get("wires") if reuse else None
    if not wires:
        return None
    if "unavailable" in wires:
        return {"kind": "unavailable", "reason": str(wires["unavailable"])}
    return _reuse_map(wires, names, segments)


def _pack_sector(sector: dict | None) -> dict | None:
    if sector is None:
        return None
    blocks = Counter(int(b) for b in sector.get("blocks") or ())
    return {
        "n_sectors": sector.get("n_sectors"),
        "axial": sector.get("axial"),
        "blocks": [{"size": s, "count": blocks[s]} for s in sorted(blocks)],
        "computed_pairs": sector.get("computed_pairs"),
        "pairs": sector.get("pairs"),
        "declined": sector.get("declined"),
    }


def _pack_reuse(reuse: dict | None) -> dict | None:
    return None if reuse is None else {k: reuse.get(k) for k in _REUSE_KEYS}


class FillTally:
    """One engine's fills, added up across the solvers one request built."""

    __slots__ = ("fills", "frequencies", "fill_s", "factor_s", "census_s", "last")

    def __init__(self):
        self.fills = 0
        self.frequencies = 0
        self.fill_s = 0.0
        self.factor_s = 0.0
        self.census_s = 0.0
        self.last = None

    def note(self, solver, n_wires: int, describe) -> None:
        """Add one finished solver. A solver handed a matrix from memory
        reports no fill of its own, so it adds its factor time and leaves the
        last real fill's description standing. ``describe()`` gives the wires'
        names and segment counts, asked for only when a map will use them."""
        raw = solver.fill_report(wires=False)
        times = raw["times"]
        self.fills += int(raw["fills"])
        self.frequencies += int(raw["frequencies"])
        self.fill_s += float(times["fill_s"])
        self.factor_s += float(times["factor_s"])
        self.census_s += float(times["census_s"])
        if self.last is None:
            self.last = {"solver": raw["solver"]}
        if raw["fills"] <= 0:
            return
        too_many = None
        if raw.get("reuse") is not None and raw["reuse"]["state"] != "declined":
            if n_wires <= MAX_MAP_WIRES:
                raw = solver.fill_report()
            else:
                too_many = {
                    "kind": "unavailable",
                    "reason": f"{n_wires} wires is more than the map draws "
                    f"({MAX_MAP_WIRES})",
                }
        mapped = too_many
        if mapped is None and (
            raw.get("sector") or (raw.get("reuse") or {}).get("wires")
        ):
            mapped = _pack_map(raw, *describe())
        self.last = {
            "solver": raw["solver"],
            "route": raw["route"],
            "reuse": _pack_reuse(raw.get("reuse")),
            "sector": _pack_sector(raw.get("sector")),
            "map": mapped,
        }

    def payload(self, *, reuse_asked: bool) -> dict | None:
        """The packed report, or None when no solver reported."""
        if self.last is None:
            return None
        return {
            "version": 1,
            "scope": "solve",
            "source": "fresh",
            "solved_at": time.time(),
            "solver": self.last.get("solver"),
            "fills": self.fills,
            "frequencies": self.frequencies,
            "times": {
                "fill_s": self.fill_s,
                "factor_s": self.factor_s,
                "census_s": self.census_s,
            },
            "no_fill": self.fills == 0,
            "points_cached": 0,
            "route": self.last.get("route"),
            "reuse_asked": bool(reuse_asked),
            "reuse": self.last.get("reuse"),
            "sector": self.last.get("sector"),
            "map": self.last.get("map"),
        }


def merge_sweep(total: dict | None, chunk: dict | None) -> dict | None:
    """A sweep's report so far, with one more chunk's added: times and counts
    are totals, and `route`, `reuse`, `sector` and `map` stay the last real
    fill's, which on a sweep is the last frequency filled."""
    if chunk is None:
        return total
    if total is None:
        return {**chunk, "scope": "sweep"}
    merged = dict(total)
    merged["fills"] = total["fills"] + chunk["fills"]
    merged["frequencies"] = total["frequencies"] + chunk["frequencies"]
    merged["times"] = {
        key: total["times"][key] + chunk["times"][key] for key in total["times"]
    }
    merged["solved_at"] = chunk["solved_at"]
    merged["no_fill"] = merged["fills"] == 0
    if not chunk["no_fill"]:
        for key in ("solver", "route", "reuse", "sector", "map"):
            merged[key] = chunk[key]
    return merged


def refused_payload(report: dict, sentence: str) -> dict:
    """The payload of a deck `rotational_symmetry=True` refused at
    construction: ``report`` is `momwire.refused_fill_report`'s, and
    ``sentence`` the refusal as the workbench words it."""
    sector = _pack_sector(report.get("sector")) or {}
    return {
        "version": 1,
        "scope": "solve",
        "source": "refused",
        "solved_at": time.time(),
        "solver": report.get("solver"),
        "fills": 0,
        "frequencies": 0,
        "times": {"fill_s": 0.0, "factor_s": 0.0, "census_s": 0.0},
        "no_fill": True,
        "points_cached": 0,
        "route": None,
        "reuse_asked": False,
        "reuse": None,
        "sector": {**sector, "declined": sentence},
        "map": None,
    }
