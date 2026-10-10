"""The EZNEC oracle module may skip -- but only for its one reason.

`test_ez_oracles_1958.py` reads other people's ``.ez`` files from a private
local tree and carries a module-level ``pytestmark`` skip without it. A
module-level skip is a place failures hide: a broken import in the module
body, a renamed constant or a typo in the env var all present as "the tree is
not here". So this tripwire lives outside it (AK#1299's pattern): importing
the module makes an ImportError a hard failure, and the skip is pinned to its
documented cause.
"""

from __future__ import annotations

import test_ez_oracles_1958 as oracles


def test_the_oracle_module_skips_only_when_its_tree_is_absent():
    mark = oracles.pytestmark
    skipping = bool(mark.args and mark.args[0])
    assert skipping == (not oracles._path(oracles.SENTINEL).is_file())
    if skipping:
        reason = str(mark.kwargs.get("reason", ""))
        assert str(oracles.ROOT) in reason and oracles.ORACLES_ENV in reason


def test_every_pairing_names_a_tolerance_and_a_file_pair():
    for name, (ez, ref, reading, invert, tol) in oracles.PAIRS.items():
        assert ez.lower().endswith(".ez") and ref.lower().endswith(".nec"), name
        assert reading in (None, "nec2", "nec4", "nec5") and isinstance(invert, bool)
        assert 0 < tol <= 5e-3, name
