"""The two moved corpus modules may skip — but only for their one reason.

antennaknobs#1299 moved `test_deck_nec2_corpus.py` and
`test_deck_nec2_xnec2c_corpus.py` here from momwire, where they ran in no CI
lane (momwire#988). Both still carry a module-level `pytestmark` skip, for
causes that are real and that this repo cannot remove:

  * the nec2 corpus is momwire's own `tests/fixtures/nec_portal` — TEN other
    momwire modules read it, so it cannot travel with the test. It is reached
    through the installed momwire, which under this repo's test lane is the
    submodule at the recorded pointer. A wheel-only momwire has no `tests/`
    beside the package and the corpus is simply absent.
  * the xnec2c corpus is a third-party tree at a recorded revision. momwire
    deliberately does not vendor or pin it, and that decision is argued in the
    module itself; moving the file here does not change it.

WHY THIS FILE EXISTS. A module-level skip is a place failures can hide. Both
modules apply `pytestmark` at module scope, so a tripwire written INSIDE
either would be skipped along with everything else — precisely when it is
needed. So it lives out here and imports them, which makes an ImportError a
hard failure rather than a silent skip, and pins each module's skip reason to
its documented cause and nothing else.

That distinction is the whole point. Without it, a renamed fixture directory,
a moved submodule, a broken import in the module body, or a typo in the env
var all present identically to "the corpus is not installed" — which is the
shape momwire#988 was about, and the shape the `slow`-marker deselection
turned out to have as well.

TO RUN THE SKIPPED MODULES LOCALLY:

  * nec2 corpus: nothing to do — momwire is installed editable from the
    submodule, so the corpus is at `momwire/tests/fixtures/nec_portal`.
  * xnec2c corpus: check out xnec2c at the revision the module records
    (`CENSUS_REVISION`) and point `MOMWIRE_XNEC2C_EXAMPLES` at its
    `examples/` directory, or leave it unset and accept the skip.
"""

from __future__ import annotations

import test_deck_nec2_corpus_1299 as nec2_mod
import test_deck_nec2_xnec2c_corpus_1299 as xnec2c_mod


def _skip_reason(module) -> str:
    """The module's `pytestmark` skip reason, or "" if it does not skip."""
    mark = module.pytestmark
    if not mark.args or not mark.args[0]:
        return ""
    return str(mark.kwargs.get("reason", ""))


def test_the_nec2_corpus_module_skips_only_when_the_corpus_is_absent():
    reason = _skip_reason(nec2_mod)
    if not reason:
        # Running: then the corpus must be the one the module measures.
        assert nec2_mod.CORPUS_DIR.is_dir()
        assert len(nec2_mod.CORPUS) == 65, len(nec2_mod.CORPUS)
        return
    # Skipping: the ONLY acceptable cause is the directory not being there.
    assert not nec2_mod.CORPUS_DIR.is_dir(), (
        f"{nec2_mod.CORPUS_DIR} exists but yielded no decks — a corpus that is "
        "present and unreadable is a failure, not a skip"
    )
    assert reason == nec2_mod.CORPUS_SKIP_REASON


def test_the_nec2_corpus_is_reached_through_the_submodule_not_a_copy():
    """A duplicated corpus would stop covering decks momwire adds, silently.
    The path must resolve through the installed momwire."""
    import momwire
    import pathlib

    expected = (
        pathlib.Path(momwire.__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "nec_portal"
    )
    assert nec2_mod.CORPUS_DIR == expected
    assert "antennaknobs/tests/fixtures" not in str(nec2_mod.CORPUS_DIR).replace(
        "\\", "/"
    ), "the corpus has been copied into this repo; it must stay momwire's"


def test_the_xnec2c_module_skips_only_for_a_missing_or_mismatched_corpus():
    reason = _skip_reason(xnec2c_mod)
    if not reason:
        assert xnec2c_mod.CORPUS.is_dir()
        return
    documented = (
        f"the xnec2c example corpus is not at {xnec2c_mod.CORPUS}",
        f"the corpus at {xnec2c_mod.CORPUS} is xnec2c",
    )
    assert reason.startswith(documented), reason
    # Whichever branch fired, it must name the way back in.
    assert xnec2c_mod.CORPUS_ENV in reason or "revision" in reason.lower(), reason


def test_both_modules_import_cleanly():
    """An ImportError here is a hard failure. Inside a skipped module it would
    be indistinguishable from the skip — which is the whole reason this file
    is separate."""
    assert nec2_mod.CORPUS_SKIP_REASON
    assert xnec2c_mod.CORPUS_ENV == "MOMWIRE_XNEC2C_EXAMPLES"
    assert callable(nec2_mod._corpus)
