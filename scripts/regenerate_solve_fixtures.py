"""Regenerate the `/solve` response-contract fixtures (issue #737).

Nothing pins the server's `solve()` dict against the frontend's `SolveResponse`
type: no pydantic response models exist anywhere in server.py, so a
server-side rename ships `undefined` to the client with no failing test and no
type error. This script is the single source of truth for both halves of the
guard:

- `tests/fixtures/solve_keys_<design>.json` — the response's KEY STRUCTURE
  only (dotted paths, arrays flattened to a trailing "[]" whose element
  structure comes from the array's first element; leaf values replaced by a
  type marker: "number" / "string" / "bool" / "null" / "empty_array"). Values
  are deliberately erased — physics numbers move with every legitimate
  solver change; the contract is the SHAPE, and `tests/test_solve_contract.py`
  diffs a fresh `key_structure()` against this file.
- `src/antennaknobs/web/frontend/src/__tests__/fixtures/solveShapes.ts` — the
  same three responses, this time with representative real VALUES (arrays
  trimmed to a couple of elements), so `SolveResponse.satisfies` vitest test
  gives a tsc-level check: a key the TS type doesn't know, or a type
  mismatch, fails compilation.

Usage:
    python scripts/regenerate_solve_fixtures.py           # rewrite both files
    python scripts/regenerate_solve_fixtures.py --check    # exit 1 if stale

Picked designs (one of each response shape currently in play):
    dipoles.invvee              — plain build_wires antenna, no network/rig.
    wire.doublet_ladder_tuner   — networked station: power_budget/plane/planes.
    dipoles.invvee_catenary     — rig_report()/readout_rows(): rig + readouts.

Request frequencies are deliberately NOT the ones other tests solve at (the
solve-cache trap documented on
`test_web_server.py::test_rig_report_failure_never_fails_the_solve`): a cache
hit here would silently serve whatever some other test last cached under
that exact request, rather than the genuine live shape.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO / "tests" / "fixtures"
TS_FIXTURE = (
    REPO
    / "src"
    / "antennaknobs"
    / "web"
    / "frontend"
    / "src"
    / "__tests__"
    / "fixtures"
    / "solveShapes.ts"
)

# name -> (geometry, request, exported TS identifier)
DESIGNS: dict[str, dict[str, Any]] = {
    "invvee": {
        "geometry": "dipoles.invvee",
        "request": {
            "measurement_freq_mhz": 28.481,
            "design_freq_mhz": 28.47,
            "momwire_model": "bspline",
        },
        "ts_export": "invveeShape",
    },
    "doublet_ladder_tuner": {
        "geometry": "wire.doublet_ladder_tuner",
        "request": {
            "measurement_freq_mhz": 7.15,
            "design_freq_mhz": 7.1,
            "momwire_model": "bspline",
        },
        "ts_export": "doubletLadderTunerShape",
    },
    "invvee_catenary": {
        "geometry": "dipoles.invvee_catenary",
        "request": {
            "measurement_freq_mhz": 28.489,
            "design_freq_mhz": 28.47,
            "momwire_model": "bspline",
        },
        "ts_export": "invveeCatenaryShape",
    },
}


def type_marker(value: Any) -> str:
    """The leaf type marker a response value collapses to. Bool is checked
    before int — in Python `bool` is an `int` subclass, so the reverse order
    would mark every boolean "number"."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    raise TypeError(f"solve() response leaf of unsupported type: {value!r}")


def key_structure(obj: Any, prefix: str = "") -> dict[str, str]:
    """Flatten a solve() response into {dotted.path: type-marker}.

    Dicts recurse key by key (`rig.apex_tension_n`). Lists collapse to a
    trailing "[]" on the path; a non-empty list's structure comes from its
    first element (`power_budget[].watts`), matching how every element of a
    given response array shares one schema. An empty list has no element to
    sample, so it gets its own marker ("empty_array") rather than silently
    contributing nothing — dipoles.invvee's empty power_budget[] exercises
    exactly this branch.
    """
    out: dict[str, str] = {}
    if isinstance(obj, dict):
        for k in sorted(obj):
            child = f"{prefix}.{k}" if prefix else k
            out.update(key_structure(obj[k], child))
    elif isinstance(obj, list):
        arr = f"{prefix}[]"
        if not obj:
            out[arr] = "empty_array"
        else:
            out.update(key_structure(obj[0], arr))
    else:
        out[prefix] = type_marker(obj)
    return out


# Keys whose value is a fixed-size coordinate tuple ([x, y] or [x, y, z]),
# never a variable-length collection — trimming these would silently change
# their arity and break the `[number, number, number]` tuple types in
# SolveResponse. Keys whose value is a *list* of such tuples: the list of
# points itself is fair game to trim (fewer points), but each kept point
# must keep every one of its own numbers.
_VECTOR_KEYS = {"position", "feed_position"}
_POINT_LIST_KEYS = {"knot_positions", "sample_positions"}

# Response fields whose SolveResponse type is a string-literal union rather
# than plain `string` — a live solve's value type-checks fine on its own,
# but a bare object literal infers plain `string`, so it needs an explicit
# cast to narrow back down. Extend this (and TS_FIXTURE_EXTRA_IMPORTS below)
# if a future fixture design touches another such field.
_STRING_LITERAL_CASTS = {"default_view": "Projection"}
TS_FIXTURE_EXTRA_IMPORTS = 'import type { Projection } from "../../lib/view";\n'


def _trim(obj: Any, key: str | None = None, list_cap: int = 2) -> Any:
    """Cap variable-length collections in `obj` to `list_cap` elements
    (recursively), so the generated TS fixture stays small while keeping
    real, representative values and every field name. Coordinate tuples
    (`_VECTOR_KEYS`) and the individual points inside `_POINT_LIST_KEYS`
    arrays are left at their real arity — only the number of *points* (not
    their length) is capped."""
    if isinstance(obj, dict):
        return {k: _trim(v, key=k, list_cap=list_cap) for k, v in obj.items()}
    if isinstance(obj, list):
        if key in _VECTOR_KEYS:
            return obj
        if key in _POINT_LIST_KEYS:
            return obj[:list_cap]
        return [_trim(v, key=key, list_cap=list_cap) for v in obj[:list_cap]]
    return obj


def _ts_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError(f"non-finite solve() response value: {value!r}")
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise TypeError(f"solve() response leaf of unsupported type: {value!r}")


def _ts_literal(
    value: Any, key: str | None = None, indent: int = 0, force_tuple: bool = False
) -> str:
    """Render `value` as a TS literal (JSON-superset syntax).

    Differs from plain `json.dumps` in one way: a fixed-size coordinate
    array — `_VECTOR_KEYS`, or an element of a `_POINT_LIST_KEYS` array —
    gets a trailing `as [number, number, ...]` so TS infers a tuple instead
    of widening it to `number[]`; SolveResponse's `Wire.knot_positions:
    [number, number, number][]` (and `feed_position`, `feed_positions[].
    position`) would otherwise never `satisfies`-check against a bare object
    literal, whose array types always widen to the mutable-length form.
    """
    pad, pad_in = "  " * indent, "  " * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"

        def _field(k: str, v: Any) -> str:
            rendered = _ts_literal(v, key=k, indent=indent + 1)
            cast = _STRING_LITERAL_CASTS.get(k)
            if cast is not None and isinstance(v, str):
                rendered += f" as {cast}"
            return f'{pad_in}"{k}": {rendered}'

        body = ",\n".join(_field(k, v) for k, v in value.items())
        return "{\n" + body + "\n" + pad + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        point_list = key in _POINT_LIST_KEYS
        body = ",\n".join(
            f"{pad_in}"
            + _ts_literal(v, key=None, indent=indent + 1, force_tuple=point_list)
            for v in value
        )
        text = "[\n" + body + "\n" + pad + "]"
        want_tuple = force_tuple or key in _VECTOR_KEYS
        if want_tuple and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
        ):
            text += f" as [{', '.join(['number'] * len(value))}]"
        return text
    return _ts_scalar(value)


def solve_design(spec: dict[str, Any]) -> dict:
    from antennaknobs.web import server

    req = {"geometry": spec["geometry"], **spec["request"]}
    return server.solve(req)


def render_fixtures() -> tuple[dict[str, dict[str, str]], str]:
    """Return (name -> key_structure dict, full solveShapes.ts source)."""
    keys_by_design: dict[str, dict[str, str]] = {}
    ts_blocks = []
    for name, spec in DESIGNS.items():
        out = solve_design(spec)
        keys_by_design[name] = key_structure(out)
        trimmed = _trim(out)
        literal = _ts_literal(trimmed)
        ts_blocks.append(
            f"// {spec['geometry']} (tests/fixtures/solve_keys_{name}.json is "
            "the same solve's key-structure sibling).\n"
            # `satisfies` ON THE LITERAL, not on a later reference: TS only
            # performs excess-property checking against fresh object
            # literals, so this placement is what makes a server key the
            # type doesn't declare FAIL compilation (review finding, #737 —
            # a reference-site `satisfies` in the test caught only the
            # missing/mistyped directions).
            f"export const {spec['ts_export']} = {literal} satisfies SolveResponse;\n"
        )
    header = (
        "// GENERATED by scripts/regenerate_solve_fixtures.py — do not hand-edit.\n"
        "// Representative /solve responses (issue #737), one real solve per\n"
        "// design, arrays trimmed to a couple of elements. The companion\n"
        "// vitest test (SolveResponse.contract.test.ts) asserts each of these\n"
        'import type { SolveResponse } from "../../lib/api";\n\n'
        + "// `satisfies SolveResponse` — a key this file has that the type\n"
        "// doesn't (or a type mismatch) fails `tsc --noEmit`. Re-run the\n"
        "// script and update SolveResponse together when the server's shape\n"
        "// changes on purpose.\n" + TS_FIXTURE_EXTRA_IMPORTS + "\n"
    )
    return keys_by_design, header + "\n".join(ts_blocks)


def main() -> int:
    check = "--check" in sys.argv[1:]

    keys_by_design, ts_source = render_fixtures()
    stale = []

    for name, structure in keys_by_design.items():
        path = FIXTURES_DIR / f"solve_keys_{name}.json"
        fresh = json.dumps(structure, indent=2, sort_keys=True) + "\n"
        if check:
            current = path.read_text() if path.exists() else ""
            if current != fresh:
                stale.append(path)
        else:
            path.write_text(fresh)

    if check:
        current_ts = TS_FIXTURE.read_text() if TS_FIXTURE.exists() else ""
        if current_ts != ts_source:
            stale.append(TS_FIXTURE)
        if stale:
            sys.stderr.write(
                "solve-contract fixtures are stale — regenerate with "
                "`python scripts/regenerate_solve_fixtures.py` and commit the "
                f"result (and update SolveResponse to match): {stale}\n"
            )
            return 1
        print("solve-contract fixtures are up to date")
        return 0

    TS_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    TS_FIXTURE.write_text(ts_source)
    print(
        f"wrote {len(keys_by_design)} key-structure fixtures + {TS_FIXTURE.relative_to(REPO)}"
    )
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO / "src"))
    raise SystemExit(main())
