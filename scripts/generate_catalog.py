"""Generate the design-catalog listings from the design tree (issue #292).

The catalog page (site/src/content/docs/reference/catalog.md) is curated
prose (intro, family blurbs) wrapping GENERATED per-family tables. This
script rewrites only what sits between the marker pairs

    <!-- catalog:begin <family> -->
    ...
    <!-- catalog:end <family> -->

so the listings can never drift from the code: every design enumerated by
`python -m antennaknobs list` appears exactly once, its description is the
first sentence of its module docstring (mandatory — this script fails on a
design without one), and its variants come from the `*_params`
class-attribute convention via the web adapter's `_discover_variants`.

Usage:
    python scripts/generate_catalog.py           # rewrite the page in place
    python scripts/generate_catalog.py --check   # exit 1 if the committed
                                                 # page is stale (CI mode —
                                                 # also run by the test suite)
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "site" / "src" / "content" / "docs" / "reference" / "catalog.md"

# Page order; every family in the design tree must be listed here (the
# script fails on a new family so it gets a curated section deliberately).
FAMILIES = [
    "dipoles",
    "loops",
    "beams",
    "verticals",
    "wire",
    "broadband",
    "multiband",
    "arrays",
    "specialty",
]


def _description(design: str) -> str:
    """First sentence of the design module's docstring, collapsed to one
    line, trailing period dropped (table-note style)."""
    mod = importlib.import_module(f"antennaknobs.designs.{design}")
    doc = (mod.__doc__ or "").strip()
    if not doc:
        raise SystemExit(
            f"error: {design} has no module docstring — the catalog "
            "description is its first sentence, so every design needs one"
        )
    first_para = doc.split("\n\n", 1)[0]
    one_line = " ".join(first_para.split())
    # First sentence: split at a period followed by whitespace, but not
    # after an initial ("L. B. Cebik") — a single capital letter before
    # the period is not a sentence end.
    sentence = re.split(r"(?<![A-Z]\.)(?<=\.)\s", one_line, maxsplit=1)[0]
    return sentence.rstrip(".")


def _variants(design: str) -> tuple[str, ...]:
    from antennaknobs.cli import resolve_class
    from antennaknobs.web.adapter import _discover_variants

    cls = resolve_class(design)
    return tuple(v for v in _discover_variants(cls) if v != "default")


def _family_table(designs: list[str]) -> str:
    rows = ["| Design | Notes |", "| --- | --- |"]
    for d in designs:
        note = _description(d)
        variants = _variants(d)
        if variants:
            note += " · variants: " + ", ".join(f"`{v}`" for v in variants)
        rows.append(f"| `{d}` | {note} |")
    return "\n".join(rows)


def render(page: str) -> str:
    """Return `page` with every marker block regenerated."""
    # Import the server first: adapter has an import cycle with .examples
    # when it is the entry module.
    import antennaknobs.web.server  # noqa: F401

    from antennaknobs.cli import list_builtin_designs

    by_family: dict[str, list[str]] = {}
    for name in list_builtin_designs():
        by_family.setdefault(name.split(".", 1)[0], []).append(name)

    unknown = set(by_family) - set(FAMILIES)
    if unknown:
        raise SystemExit(
            f"error: design families {sorted(unknown)} are not in "
            "generate_catalog.FAMILIES — add them (and a curated section "
            "with markers to catalog.md)"
        )

    out = page
    for family in FAMILIES:
        designs = by_family.get(family)
        if not designs:
            raise SystemExit(f"error: no designs found for family {family!r}")
        pattern = re.compile(
            rf"<!-- catalog:begin {family} -->\n?.*?<!-- catalog:end {family} -->",
            re.DOTALL,
        )
        if not pattern.search(out):
            raise SystemExit(
                f"error: catalog.md has no marker block for family {family!r}"
            )
        block = (
            f"<!-- catalog:begin {family} -->\n"
            + _family_table(designs)
            + f"\n<!-- catalog:end {family} -->"
        )
        out = pattern.sub(lambda _m: block, out)
    return out


def main() -> int:
    page = CATALOG.read_text()
    fresh = render(page)
    if "--check" in sys.argv[1:]:
        if fresh != page:
            sys.stderr.write(
                "catalog.md is stale — regenerate with "
                "`python scripts/generate_catalog.py` and commit the result\n"
            )
            return 1
        print("catalog.md is up to date")
        return 0
    if fresh != page:
        CATALOG.write_text(fresh)
        print(f"rewrote {CATALOG.relative_to(REPO)}")
    else:
        print("catalog.md already up to date")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO / "src"))
    raise SystemExit(main())
