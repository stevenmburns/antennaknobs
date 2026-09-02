"""#1087: the jobs that write to a SHARED destination must be serialised.

Three merges inside ~70 seconds put three `Test Python package` runs on main at
once. `coverage-comment` pushes the badge and coverage data to a branch it
shares with every other run of itself, so the overlapping runs computed their
pushes from different tips and the loser was rejected — a `GitError` out of the
action's own `git.push`. Nothing was broken, but main carried a red run against
a healthy commit, and this repo's standing rule is to check whether main is
already red before blaming your branch (#748). A false red costs exactly the
time that rule exists to save.

The fix is a `concurrency` group with **`cancel-in-progress: false`**, and that
second half is an asymmetry: `fly-deploy.yml` and `deploy-docs.yml` are the
repo's other shared-destination writers and both cancel in progress, because a
superseded deploy is replaced wholesale by the next one. A superseded coverage
run is not — each push's data is its own artifact — so those must queue rather
than drop.

An asymmetry between three jobs that otherwise look alike is precisely the kind
of thing a later reader tidies into consistency. Hence this file. It greps
rather than parsing YAML: `pyyaml` is not a declared test dependency here, and
the claim is about literal lines being present.
"""

from __future__ import annotations

import pathlib

WORKFLOWS = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _text(name: str) -> str:
    path = WORKFLOWS / name
    assert path.exists(), f"{name} is missing from {WORKFLOWS}"
    return path.read_text()


def test_coverage_comment_is_serialised():
    """It must declare a concurrency group at all."""
    body = _text("test.yml")
    assert "group: coverage-comment-data" in body, (
        "coverage-comment pushes to the shared "
        "python-coverage-comment-action-data branch; without a concurrency "
        "group, two main pushes close together race and one run goes red "
        "against a commit that is not broken (#1087)"
    )


def test_coverage_comment_queues_rather_than_cancels():
    """The half that differs from the deploy workflows, and why.

    A cancelled deploy is harmless because the next one supersedes it. A
    cancelled coverage run silently discards that push's data, so this one
    must queue.
    """
    body = _text("test.yml")
    head, _, tail = body.partition("group: coverage-comment-data")
    assert tail, "concurrency group missing (see the test above)"
    window = tail[:200]
    assert "cancel-in-progress: false" in window, (
        "coverage-comment must QUEUE, not cancel: each push's coverage data is "
        "its own artifact, unlike a superseded deploy. Do not make this match "
        "fly-deploy.yml / deploy-docs.yml just because they look alike (#1087)"
    )
