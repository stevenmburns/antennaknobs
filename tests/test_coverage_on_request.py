"""Coverage runs only on request, and commits nothing (Steve, 2026-11-03).

It used to run on every push to main and push its HTML report and badge to the
`python-coverage-comment-action-data` branch: 1,383 commits of `htmlcov/`,
about 250 MB that every clone of this repo downloaded, for a PR comment nobody
read any more. Now `coverage.yml` runs by hand, uploads the report as an
expiring artifact, and writes nowhere. This file keeps it that way: it greps
rather than parsing YAML (pyyaml is not a declared test dependency here).
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def test_coverage_runs_only_by_hand():
    body = (WORKFLOWS / "coverage.yml").read_text()
    on = body.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert "workflow_dispatch" in on
    for trigger in ("push:", "pull_request", "schedule"):
        assert trigger not in on, f"coverage.yml must not run on {trigger}"


def test_coverage_writes_nothing_back():
    body = (WORKFLOWS / "coverage.yml").read_text()
    assert "contents: read" in body and "contents: write" not in body
    # The action that pushed to the branch, by its `uses:` line: the header
    # comment may still name the branch to say why it is gone.
    assert "py-cov-action" not in body
    # The report is an artifact that expires, not a commit.
    assert "retention-days:" in body


def test_nothing_else_writes_the_old_branch_or_reads_its_badge():
    for wf in WORKFLOWS.glob("*.yml"):
        text = wf.read_text()
        assert "py-cov-action" not in text, wf.name
        assert "coverage run" not in text or wf.name == "coverage.yml", wf.name
    assert "python-coverage-comment-action-data" not in (ROOT / "README.md").read_text()
