"""The momwire version triple (issue #737): pyproject.toml's exact pin,
Dockerfile's `pip install` pin, and the `momwire` submodule pointer are
hand-maintained in three separate files with a documented failure history
(PRs #268/#270 — a stale submodule pointer silently loses a dev clone's
editable momwire to the PyPI wheel; see .claude/skills/release/SKILL.md's
three-place checklist). Nothing previously asserted the three agree.

This test does NOT pin a specific version — momwire's own version marches
forward on its own release cadence, independent of when antennaknobs bumps
its pin (a momwire 0.23.0 release and the antennaknobs pin-bump PR that
adopts it are deliberately separate events, per the release skill). It only
asserts the three recorded locations still agree with each other, so it
stays green across a correctly-executed bump and fails the moment one of the
three places is missed.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

_RUNBOOK_HINT = (
    "the momwire version triple disagrees; see .claude/skills/release/SKILL.md's "
    "three-place checklist (pyproject.toml pin / Dockerfile pin / momwire "
    "submodule pointer) — a stale submodule pointer bit PRs #268/#270"
)


def _pyproject_pin() -> str:
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    for dep in data["project"]["dependencies"]:
        m = re.fullmatch(r"momwire==([\w.]+)", dep)
        if m:
            return m.group(1)
    raise AssertionError(
        "pyproject.toml has no exact `momwire==X.Y.Z` dependency pin — " + _RUNBOOK_HINT
    )


def _dockerfile_pin() -> str:
    text = (REPO / "Dockerfile").read_text()
    m = re.search(r'pip install "momwire==([\w.]+)"', text)
    if not m:
        raise AssertionError(
            'Dockerfile has no `pip install "momwire==X.Y.Z"` line — ' + _RUNBOOK_HINT
        )
    return m.group(1)


def _submodule_version() -> str:
    submodule_pyproject = REPO / "momwire" / "pyproject.toml"
    data = tomllib.loads(submodule_pyproject.read_text())
    return data["project"]["version"]


def test_momwire_version_triple_agrees():
    submodule_dir = REPO / "momwire"
    submodule_pyproject = submodule_dir / "pyproject.toml"
    if not submodule_dir.is_dir() or not submodule_pyproject.is_file():
        pytest.skip(
            "momwire submodule directory is absent/empty (a non-submodule "
            "clone) — nothing to compare the pin against"
        )

    pyproject_pin = _pyproject_pin()
    dockerfile_pin = _dockerfile_pin()
    submodule_version = _submodule_version()

    assert pyproject_pin == dockerfile_pin == submodule_version, (
        f"momwire version triple disagrees: pyproject.toml pins "
        f"{pyproject_pin!r}, Dockerfile pins {dockerfile_pin!r}, the "
        f"momwire submodule is at {submodule_version!r} — " + _RUNBOOK_HINT
    )
