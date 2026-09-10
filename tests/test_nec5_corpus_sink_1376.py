"""The corpus tool's fetch sink writes only under raw/<source>/ (#1376).

Found by the 1.3 security review: a zip member named `../../x.nec` at one of
the fetch sources — a compromised GitHub repository, a replaced ARRL zip —
wrote a deck two directories above the output folder. The names are the
archive's to choose; the sink keeps only their plain path components.
"""

from __future__ import annotations

import importlib.util
import io
import pathlib
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"

DECK = "CM x\nCE\nGW 1 5 0 0 0 0 0 1 .001\nGE\nEX 0 1 3 0 1 0\nXQ\nEN\n"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_sink_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _zip(members: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in members.items():
            z.writestr(name, text)
    return buf.getvalue()


@pytest.mark.parametrize(
    "hostile",
    [
        "repo-HEAD/../../escaped.nec",
        "repo-HEAD/sub/../../../escaped.nec",
        "repo-HEAD//../escaped.nec",
        "repo-HEAD/..\\..\\escaped.nec",
    ],
)
def test_a_hostile_member_name_stays_under_the_source_dir(tool, tmp_path, hostile):
    out = tmp_path / "raw"
    sink = tool._Sink(out, "src")
    tool._fetch_zip_members(
        _zip({hostile: DECK, "repo-HEAD/fine.nec": DECK + "CM fine\n"}),
        sink,
        1,
        "",
        False,
    )
    written = sorted(
        p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.nec")
    )
    assert all(w.startswith("raw/src/") for w in written), written
    assert "raw/src/fine.nec" in written
    # The hostile member is not silently lost either: same bytes as fine.nec,
    # so it is a duplicate; with distinct bytes it lands under raw/src/.
    sink2 = tool._Sink(tmp_path / "raw2", "src")
    tool._fetch_zip_members(_zip({hostile: DECK + "CM y\n"}), sink2, 1, "", False)
    inside = sorted(
        p.relative_to(tmp_path).as_posix() for p in (tmp_path / "raw2").rglob("*.nec")
    )
    assert len(inside) == 1 and inside[0].startswith("raw2/src/"), inside
    assert inside[0].endswith("/escaped.nec")


def test_an_absolute_member_name_is_relative_to_the_source_dir(tool, tmp_path):
    sink = tool._Sink(tmp_path / "raw", "src")
    sink.put("/etc/escaped.nec", DECK.encode())
    written = sorted(
        p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.nec")
    )
    assert written == ["raw/src/etc/escaped.nec"], written


def test_the_security_review_names_the_current_version(tool):
    """The review ships beside the exe and speaks for one version of the
    script. Bumping VERSION without re-reading the review is how it goes
    stale — so the version it names must be the one it ships with."""
    review = (SCRIPT.parent / "SECURITY-REVIEW.md").read_text(encoding="utf-8")
    assert f"nec5_corpus.py version {tool.VERSION}" in review
