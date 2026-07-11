"""The design-catalog page is generated from the design tree (issue #292):
this is the drift gate. If a design is added, renamed, retired, or its
docstring/variants change without regenerating the page, the suite fails
here with the regeneration command in the message.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "site" / "src" / "content" / "docs" / "reference" / "catalog.md"


def test_catalog_page_is_not_stale():
    """Exactly what CI needs: the committed page equals a fresh render."""
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "generate_catalog.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert proc.returncode == 0, (
        f"{proc.stderr or proc.stdout}\n"
        "fix: python scripts/generate_catalog.py  (then commit catalog.md)"
    )


def test_every_design_listed_exactly_once():
    from antennaknobs.cli import list_builtin_designs

    page = CATALOG.read_text()
    designs = list_builtin_designs()
    for name in designs:
        rows = re.findall(rf"^\| `{re.escape(name)}` \|", page, flags=re.M)
        assert len(rows) == 1, f"{name}: {len(rows)} table rows (want exactly 1)"
    # ...and nothing else: every table row is a real design.
    listed = re.findall(r"^\| `([a-z0-9_]+\.[a-z0-9_]+)` \|", page, flags=re.M)
    assert sorted(listed) == sorted(designs)
