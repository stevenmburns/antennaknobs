"""``--csv PATH`` for ``sweep`` and ``analyze``: the numbers the run computed,
one row per swept point.

A file is written wide, like the workbench's Table view: the swept parameter
first, then a column group per curve (per engine, or per analysis cell) --
``R_ohm`` and ``X_ohm``, plus ``SWR`` where the run computes it and, for a
density study, the printed table's ``N_ach`` and ``dGamma``. Curves whose x
values differ (a cell on its own frequency grid) share the rows they have in
common; a cell a curve has no point at is left empty. Numbers are written at
full precision (``repr``), not at the printed table's ``%.3f``.

``-`` writes to stdout. The command's own printed tables would corrupt that,
so the CLI sends them to stderr for the run (``cli.csv_output``).
"""

from __future__ import annotations

import csv
import sys
from collections.abc import Sequence
from typing import TextIO

import numpy as np

# One curve: its label (None: unnamed, columns are bare), its x values, and
# its columns, each (name, values) aligned with the x values.
Curve = tuple[str | None, Sequence[float], Sequence[tuple[str, Sequence[float]]]]

_SAME_X = 1e-9


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= _SAME_X * max(1.0, abs(a), abs(b))


def _cell(v: float | None) -> str:
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f.is_integer() and abs(f) < 1e15 else repr(f)


def table(xname: str, curves: Sequence[Curve]) -> tuple[list[str], list[list[str]]]:
    """``(header, rows)`` for ``curves`` swept over ``xname``."""
    header = [xname]
    for label, _xs, cols in curves:
        header += [f"{label} {c}" if label else c for c, _ in cols]
    every = sorted(float(x) for _l, xs, _c in curves for x in xs)
    row_xs: list[float] = []
    for x in every:
        if not row_xs or not _same(row_xs[-1], x):
            row_xs.append(x)
    rows = []
    for x in row_xs:
        row = [_cell(x)]
        for _label, xs, cols in curves:
            i = next((k for k, v in enumerate(xs) if _same(float(v), x)), None)
            row += [_cell(None if i is None else vals[i]) for _c, vals in cols]
        rows.append(row)
    return header, rows


def impedance_curve(
    label: str | None,
    xs: Sequence[float],
    zs: np.ndarray,
    swr: np.ndarray | None = None,
) -> Curve:
    """A sweep's curve: R and X (and SWR) per port. ``zs`` is (points,) for
    port 0 only, or (points, ports); a second port's columns say so."""
    z = np.asarray(zs)
    z = z[:, None] if z.ndim == 1 else z
    s = None if swr is None else np.asarray(swr).reshape(z.shape)
    cols: list[tuple[str, Sequence[float]]] = []
    for p in range(z.shape[1]):
        tag = f"port{p + 1} " if z.shape[1] > 1 else ""
        cols += [(f"{tag}R_ohm", z[:, p].real), (f"{tag}X_ohm", z[:, p].imag)]
        if s is not None:
            cols.append((f"{tag}SWR", s[:, p]))
    return label, xs, cols


def density_curve(name: str, rows, z0: float) -> Curve:
    """A density study's curve: the printed table's columns, ``rows`` being
    ``(nominal_n, achieved_n, z)`` finest last (``|dGamma|`` is against
    that finest rung, ``sweep._print_convergence_table``)."""
    zs = np.array([z for _n, _a, z in rows])
    gamma = (zs - z0) / (zs + z0)
    return (
        name,
        [n for n, _a, _z in rows],
        [
            ("N_ach", [a for _n, a, _z in rows]),
            ("R_ohm", zs.real),
            ("X_ohm", zs.imag),
            ("dGamma", np.abs(gamma - gamma[-1])),
        ],
    )


class CsvOut:
    """Where ``--csv`` writes: a file, or ``-`` for ``stdout``."""

    def __init__(self, path: str, stdout: TextIO | None = None):
        self.path = path
        self.stdout = stdout if stdout is not None else sys.stdout

    def write(self, xname: str, curves: Sequence[Curve]) -> None:
        header, rows = table(xname, curves)
        if self.path == "-":
            csv.writer(self.stdout, lineterminator="\n").writerows([header, *rows])
            return
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f, lineterminator="\n").writerows([header, *rows])
