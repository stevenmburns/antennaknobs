"""The MMANA-GAL corpus module may skip -- but only for its one reason.

`test_maa_corpus_1897.py` reads a third-party tree (handiko/AntennaFiles-OLD,
GPL-3.0) that this repo deliberately does not vendor, so it carries a
module-level ``pytestmark`` skip. A module-level skip is a place failures can
hide: a renamed variable, a broken import in the module body or a typo in
the env var all present as "the corpus is not installed". So this tripwire
lives outside it (AK#1299's pattern): importing the module makes an
ImportError a hard failure, and the skip is pinned to its documented causes.
"""

from __future__ import annotations

import test_maa_corpus_1897 as corpus_mod


def _skip_reason() -> str:
    mark = corpus_mod.pytestmark
    if not mark.args or not mark.args[0]:
        return ""
    return str(mark.kwargs.get("reason", ""))


def test_the_maa_corpus_module_skips_only_for_its_documented_reasons():
    reason = _skip_reason()
    if not reason:
        # Running: then it is the checkout the census was recorded against.
        assert corpus_mod.CORPUS.is_dir()
        assert (
            corpus_mod.CORPUS_REVISION is None
            or corpus_mod.CENSUS_REVISION.startswith(corpus_mod.CORPUS_REVISION[:7])
        )
        return
    if not corpus_mod.CORPUS.is_dir():
        assert "is not at" in reason and corpus_mod.CORPUS_ENV in reason
    else:
        # Present at another revision: both hashes named.
        assert corpus_mod.CENSUS_REVISION in reason
        assert str(corpus_mod.CORPUS_REVISION) in reason


def test_the_census_names_every_category_it_expects():
    names = {name for name, _ in corpus_mod._CATEGORIES} | {"imported"}
    assert set(corpus_mod._EXPECTED) <= names
