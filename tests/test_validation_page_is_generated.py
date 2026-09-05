"""The validation page is generated, and this is what makes that true.

`site/src/content/docs/reference/validation.md` carries a GENERATED banner
telling you to edit `scripts/build_validation_report.py` instead. Twice now
that banner has been ignored and content edited straight into the `.md` —
most recently two hexbeam verdicts and a contributor's attribution
("submitted by Ward Harriman, AE6TY"), which the next regeneration silently
reverted. Nobody was careless; the banner simply has no teeth, and a
generated file that is *sometimes* hand-maintained is a file whose history
quietly eats contributions.

So the banner is a test now. Regenerate the page body from the committed
artifacts and compare: if they differ, either the generator changed without
the page being rebuilt, or the page was edited by hand.

Deliberately cheap — this rebuilds only the MARKDOWN, from the committed
JSON ladders. It renders no figures and runs no solver, so it costs a JSON
load and a string compare and can sit in the default lane. What it cannot
catch is a stale FIGURE; that needs the real regeneration and its momwire
dependency, and is the honest limit of this gate rather than an oversight.

The figures lagging the generator is a STATED property, not an accident
(#1126): a plain run of the generator rebuilds the markdown only, and the
PNGs are re-rendered on `--figures` (or `--recompute`), so they change in a
PR only when someone meant them to. The last test below holds that.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PAGE = ROOT / "site" / "src" / "content" / "docs" / "reference" / "validation.md"


@pytest.fixture(scope="module")
def builder():
    sys.path.insert(0, str(SCRIPTS))
    try:
        import build_validation_report as mod
    except ImportError as exc:  # pragma: no cover - defensive
        pytest.skip(f"the generator is not importable: {exc}")
    return mod


def test_the_committed_page_matches_a_fresh_render(builder):
    """`validation.md` == `build_page()` over the committed artifacts.

    A failure here means one of two things, and the message says which to
    look for: the generator moved and the page was not rebuilt (run
    `python scripts/build_validation_report.py`), or someone edited the
    generated file directly and their words are about to be lost.
    """
    for path in (
        builder.LADDERS,
        builder.FREE_LADDERS,
        builder.PULSE_LADDER,
        builder.ANCHORS,
        builder.LEESON,
        builder.PHASE2,
        builder.VOTES,
    ):
        if not path.exists():  # pragma: no cover - artifacts are committed
            pytest.skip(f"missing committed artifact {path.name}")

    rendered = builder.build_page(
        json.loads(builder.LADDERS.read_text()),
        json.loads(builder.FREE_LADDERS.read_text()),
        json.loads(builder.PULSE_LADDER.read_text()),
        json.loads(builder.PHASE2.read_text()),
        json.loads(builder.VOTES.read_text()),
        json.loads(builder.LEESON.read_text()),
        json.loads(builder.ANCHORS.read_text()),
    )
    committed = PAGE.read_text()
    if rendered == committed:
        return

    import difflib

    diff = "\n".join(
        list(
            difflib.unified_diff(
                committed.splitlines(),
                rendered.splitlines(),
                "committed validation.md",
                "freshly generated",
                lineterm="",
            )
        )[:40]
    )
    pytest.fail(
        "validation.md is not what the generator produces.\n\n"
        "Either the generator changed and the page was not rebuilt (run "
        "`python scripts/build_validation_report.py`), or the page was "
        "edited by hand — in which case move the edit INTO "
        "`build_page()` first, or regenerating will discard it. That has "
        "already cost one contributor attribution.\n\n" + diff
    )


def test_a_plain_run_writes_the_markdown_and_never_the_figures(
    builder, tmp_path, monkeypatch
):
    """#1126: the figures are rendered only on request.

    `bydipole1-convergence.png` and `leeson-case5.png` are not byte-stable
    across matplotlib patch versions (3.11.0 -> 3.11.1 is one pixel taller and
    different pixel data, not just metadata), so a prose edit that regenerated
    them silently replaced the committed render with the contributor's
    toolchain. The decision made once, here: a plain run rebuilds the MARKDOWN
    only; the figures move with `--figures` (or `--recompute`, whose new
    ladders the figures must follow) and arrive in a PR as a deliberate
    binary change, never as a side effect of editing words.
    """
    calls: list[str] = []
    monkeypatch.setattr(
        builder, "render_figure", lambda *a, **k: calls.append("figure")
    )
    monkeypatch.setattr(
        builder, "render_leeson_figure", lambda *a, **k: calls.append("leeson")
    )
    page = tmp_path / "validation.md"
    monkeypatch.setattr(builder, "PAGE", page)

    assert builder.main([]) == 0
    assert calls == [], "a plain run rendered figures; #1126 is back"
    assert page.read_text() == PAGE.read_text()

    assert builder.main(["--figures"]) == 0
    assert calls == ["figure", "leeson"]
