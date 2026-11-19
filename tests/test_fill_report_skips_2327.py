"""The fill-report and fill-metric tests may skip, but only for their one reason (AK#2327).

`tests/test_fill_report_2327.py` and `tests/test_fill_metrics_2327.py` need a momwire whose solvers carry
`fill_report()` (momwire#2016). The recorded pointer, momwire 0.94.0, has none,
so on CI those tests skip, and in dev mode (the submodule on momwire main) they
run. A skip is a place a failure can hide: a broken import, a renamed probe or
a momwire that dropped the method would all read as "this momwire has no
report". This file imports the module, so an ImportError fails here rather than
skipping, and pins the skip to the one cause, checked independently of the
module's own probe.
"""

from __future__ import annotations

import momwire
import pytest
import test_fill_metrics_2327 as metrics_mod
import test_fill_report_2327 as fill_mod

MODULES = [fill_mod, metrics_mod]


@pytest.fixture(params=MODULES, ids=lambda m: m.__name__)
def mod(request):
    return request.param


def test_the_modules_import_cleanly(mod):
    assert mod.HAVE_REPORT in (True, False)


def test_it_skips_exactly_when_momwire_has_no_fill_report(mod):
    has_method = callable(getattr(momwire.BSplineSolver, "fill_report", None))
    assert mod.HAVE_REPORT is has_method


def test_the_skip_names_the_missing_method(mod):
    assert "fill_report" in mod.SKIP_REASON
    mark = mod.needs_report.mark
    assert mark.kwargs["reason"] == mod.SKIP_REASON
    assert mark.args == (not mod.HAVE_REPORT,)


def test_every_skip_in_the_module_is_that_one(mod):
    """No test there skips for a reason of its own."""
    for name in dir(mod):
        if not name.startswith("test_"):
            continue
        for mark in getattr(getattr(mod, name), "pytestmark", []):
            if mark.name == "skipif":
                assert mark.kwargs["reason"] in (
                    mod.SKIP_REASON,
                    "this momwire reports its fill",
                ), name
