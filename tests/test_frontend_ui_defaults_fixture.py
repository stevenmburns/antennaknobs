"""The frontend's served `ui_defaults` fixture is what the server serves.

AK#1858 removed the frontend's own copy of the server's startup defaults
(the switches, the orientation, the ground slots, run-on-pick): the page now
takes `ui_defaults` from /capabilities or shows an error. Its session tests
mount on `uiDefaultsFixtures.ts` instead, so that fixture is the one place a
stale default could still hide, and this regenerates it and compares.

A failure here means a server default moved: regenerate the fixture (the
command is in its header) and let the frontend suite say what the move does
to the workbench.
"""

from __future__ import annotations

import json
import pathlib
import re

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web import settings as ui_settings

ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "src/antennaknobs/web/frontend/src"
FIXTURE = FRONTEND / "__tests__/uiDefaultsFixtures.ts"
MARKER = "export const SERVED_UI_DEFAULTS"


def _served() -> dict:
    cat = ui_settings.catalog(have_pynec=True, have_nec5=True, have_nec2=True)
    return ui_settings.load(cat, hosted=True)


def _fixture() -> dict:
    src = FIXTURE.read_text()
    assert MARKER in src, f"{FIXTURE.name} no longer declares {MARKER}"
    body = src[src.index(MARKER) :]
    body = body[body.index("=") + 1 :].strip()
    assert body.endswith(";"), "fixture body is not the expected `= <json>;` shape"
    return json.loads(body[:-1])


def test_the_fixture_is_the_served_payload():
    fx = _fixture()
    assert fx["grounds"], "fixture parsed with no ground slots — a vacuous compare"
    assert fx == _served(), (
        "uiDefaultsFixtures.ts is stale: regenerate it with the command in its header."
    )


# Where a ground method as a value would be a default rather than a choice:
# the startup-settings reader and the solver-slot seeding. (lib/groundSlots.ts
# spells one for a buried design's REQUIREMENT, which is physics, not a
# default.)
_NO_METHOD_LITERAL = ("lib/settings.ts", "lib/backends.ts")


def _default_tables(root: pathlib.Path) -> list[str]:
    """Every line under ``root`` that restates a server default: a
    ``BUILTIN_*`` identifier anywhere in lib/ or components/, or a ground
    method as an object-literal value in the files above."""
    offenders = []
    for sub in ("lib", "components"):
        for path in sorted((root / sub).rglob("*.ts*")):
            rel = path.relative_to(root).as_posix()
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if re.search(r"\bBUILTIN_\w+", line) or (
                    rel in _NO_METHOD_LITERAL
                    and re.search(
                        r"""\bmethod:\s*["'](sommerfeld|fast|mininec)["']""", line
                    )
                ):
                    offenders.append(f"{rel}:{n}: {line.strip()}")
    return offenders


def test_the_frontend_restates_no_default_table():
    """The grep pin (AK#1858): the frontend carries no copy of a server
    default. ``BUILTIN_*`` was the naming of every copy (switches,
    orientation, ground, ground slots, run-on-pick, the whole ui_defaults),
    and a ground method as a value is how the copy and a request literal
    drifted together when AK#1856 moved the default. A vocabulary list, such
    as the method enum, spells the names without the ``method:`` key."""
    offenders = _default_tables(FRONTEND)
    assert not offenders, (
        "the frontend restates a server-owned default; read it from "
        "/capabilities instead:\n" + "\n".join(offenders)
    )


def test_the_grep_pin_sees_a_re_added_table(tmp_path):
    """The pin above is only worth its green if it can go red: the deleted
    tables, put back in a copy of the tree, are each found."""
    lib = tmp_path / "lib"
    lib.mkdir()
    (tmp_path / "components").mkdir()
    (lib / "settings.ts").write_text(
        "export const BUILTIN_SWITCHES = { live: true };\n"
        'const g = { enabled: true, type: "finite", method: "sommerfeld" };\n'
    )
    (lib / "backends.ts").write_text("  { id: \"Z\", method: 'fast' },\n")
    (lib / "groundSlots.ts").write_text('own = { method: "sommerfeld" };\n')
    found = _default_tables(tmp_path)
    assert [f.split(":")[0:2] for f in found] == [
        ["lib/backends.ts", "1"],
        ["lib/settings.ts", "1"],
        ["lib/settings.ts", "2"],
    ]
