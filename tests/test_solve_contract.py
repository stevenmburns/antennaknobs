"""The /solve response-shape contract (issue #737).

No pydantic response models exist anywhere in server.py — the TS
`SolveResponse` type hand-mirrors ad-hoc adapter dicts, so a server-side
rename ships `undefined` to the client with no failing test and no type
error. This is the Python half of the guard: re-derive the live key
structure from a real `server.solve()` call for three representative
designs and diff it against the fixture `scripts/regenerate_solve_fixtures.py`
recorded (`tests/fixtures/solve_keys_<design>.json`). The TS half
(`src/antennaknobs/web/frontend/src/__tests__/SolveResponse.contract.test.ts`)
does the complementary `satisfies SolveResponse` compile-time check against
the same script's `solveShapes.ts` output.

Deliberately structural, not value-based: physics numbers legitimately move
with solver changes, so only KEY PATHS + leaf type markers are compared
("rig.apex_tension_n" -> "number"), never the numbers themselves. This is
NOT a regex-over-generated-TS tripwire (the class that broke on the #642 lib
move) — it calls the real solver and inspects the real dict.

Request frequencies match scripts/regenerate_solve_fixtures.py exactly and
are deliberately NOT the ones other test modules solve at (the solve-cache
trap documented on
test_web_server.py::test_rig_report_failure_never_fails_the_solve): a cache
hit here would silently return whatever some other test's monkeypatched or
error-path solve last cached under the same request, rather than this
design's genuine shape.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO / "tests" / "fixtures"

# regenerate_solve_fixtures lives in scripts/, not on the package path — load
# it by file, same idiom as test_bench_catalog.py's bench_catalog import.
_SPEC = importlib.util.spec_from_file_location(
    "regenerate_solve_fixtures", REPO / "scripts" / "regenerate_solve_fixtures.py"
)
regen = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(regen)


@pytest.mark.parametrize("name", sorted(regen.DESIGNS))
def test_solve_response_shape_matches_fixture(name):
    spec = regen.DESIGNS[name]
    fixture_path = FIXTURES_DIR / f"solve_keys_{name}.json"
    recorded = json.loads(fixture_path.read_text())

    live = regen.key_structure(regen.solve_design(spec))

    recorded_keys = set(recorded)
    live_keys = set(live)
    missing = sorted(recorded_keys - live_keys)  # fixture has it, live doesn't
    added = sorted(live_keys - recorded_keys)  # live has it, fixture doesn't
    retyped = sorted(k for k in recorded_keys & live_keys if recorded[k] != live[k])

    assert not missing and not added and not retyped, (
        f"{spec['geometry']!r} solve() response shape drifted from "
        f"{fixture_path.relative_to(REPO)}: "
        f"missing keys (fixture has, live doesn't) = {missing}; "
        f"added keys (live has, fixture doesn't) = {added}; "
        f"retyped keys (same key, different marker) = "
        f"{[(k, recorded[k], live[k]) for k in retyped]}; "
        "if this is intentional, run "
        "`python scripts/regenerate_solve_fixtures.py` and update the TS "
        "SolveResponse type (src/antennaknobs/web/frontend/src/lib/api.ts) "
        "to match"
    )
