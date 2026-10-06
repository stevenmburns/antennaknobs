"""The MMANA-GAL corpus parses, or refuses by name (AK#1897).

The public ``.maa`` files are third-party and mostly GPL-3.0; none is vendored
here. Most of them -- and most of MMANA-GAL's own ``ANT\\`` library -- are in
handiko's AntennaFiles-OLD, which this module reads from a local checkout at
the revision every count below was recorded against.

TO RUN IT: ``git clone https://github.com/handiko/AntennaFiles-OLD``, check
out ``CENSUS_REVISION``, and either put it at ``~/antennas/AntennaFiles-OLD``
or point ``ANTENNAKNOBS_MAA_CORPUS`` at it. Without it the module SKIPS, and
that is its only legitimate skip (`test_maa_corpus_skip_1897.py` pins the
reason). A checkout at a different revision skips with both hashes named;
drift within the recorded revision fails.

Two claims, over every ``.maa`` in the tree (935 files, duplicates by content
included):

1. **Nothing crashes and nothing is silently guessed.** Every file either
   imports -- its deck builds wires and a network -- or raises a
   ``ValueError`` whose message is one of the named refusals below. An
   exception of any other type, or a refusal no category knows, fails.
2. **The census is the one recorded.** ``_EXPECTED`` is the outcome by
   category, so a change in what parses or why is visible in review.
"""

from __future__ import annotations

import collections
import os
import re
import subprocess
from pathlib import Path

import pytest

from antennaknobs.maa_import import decode_maa, read_maa

CORPUS_ENV = "ANTENNAKNOBS_MAA_CORPUS"
CORPUS = Path(
    os.environ.get(CORPUS_ENV) or Path.home() / "antennas" / "AntennaFiles-OLD"
)
CENSUS_REVISION = "be3efdce335f"


def _corpus_revision() -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(CORPUS), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - defensive
        return None
    return out.stdout.strip() or None


CORPUS_REVISION = _corpus_revision() if CORPUS.is_dir() else None

if not CORPUS.is_dir():
    _skip_reason = (
        f"the MMANA-GAL corpus is not at {CORPUS} -- set ${CORPUS_ENV} to a "
        "checkout of handiko/AntennaFiles-OLD to run these"
    )
elif CORPUS_REVISION is not None and not CENSUS_REVISION.startswith(
    CORPUS_REVISION[:7]
):
    _skip_reason = (
        f"the corpus at {CORPUS} is AntennaFiles-OLD {CORPUS_REVISION}; every "
        f"count in this module was recorded against {CENSUS_REVISION}. Check "
        "that revision out to run these, or re-record _EXPECTED against yours"
    )
else:
    _skip_reason = ""

pytestmark = pytest.mark.skipif(bool(_skip_reason), reason=_skip_reason)

# The named refusals, by the words each one's message carries.
_CATEGORIES = (
    ("offset on an automatically meshed wire", r"on an automatically segmented wire"),
    ("offset from an odd wire's centre (E4)", r"odd segment count"),
    ("free wire end", r"at a free wire end"),
    ("ground pulse under an added height (E2)", r"meets the ground at z \+ H"),
    ("stack", r"Make Stack"),
    ("Laplace load", r"Laplace \(S\) form"),
    ("starred taper type (E10)", r"taper wire set type"),
    ("manual count on a taper wire", r"stepped-radius taper"),
    ("insulator wire", r"insulator wire"),
    ("iron", r"MMANA's iron"),
    ("user-defined material", r"user-defined material"),
    ("no frequency", r"built-in 14\.15 MHz"),
    ("no source", r"has no source"),
    ("position off the model", r"names wire \d+; the model has"),
    ("incomplete ground line", r"the line is incomplete"),
    ("not an MMANA file", r"not an MMANA-GAL"),
    ("end on a wire's interior", r"between its ends; MMANA joins"),
    ("wires cross", r"cross between their ends"),
    ("zero-length wire", r"zero length"),
    ("objects at one junction (AK#1886)", r"sit at one junction of \d+ wire ends"),
    ("port model cannot place them", r"cannot be placed here"),
)

# Recorded 2026-10-05 against CENSUS_REVISION (935 files).
_EXPECTED = {
    "imported": 852,
    "offset on an automatically meshed wire": 30,
    "wires cross": 17,
    "starred taper type (E10)": 8,
    "objects at one junction (AK#1886)": 7,
    "stack": 5,
    "end on a wire's interior": 3,
    "no frequency": 2,
    "Laplace load": 2,
    "no source": 2,
    "port model cannot place them": 2,
    "not an MMANA file": 1,
    "insulator wire": 1,
    "offset from an odd wire's centre (E4)": 1,
    "iron": 1,
    "zero-length wire": 1,
}


def _category(message: str) -> str | None:
    for name, pattern in _CATEGORIES:
        if re.search(pattern, message):
            return name
    return None


def _census():
    paths = sorted(
        p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() == ".maa"
    )
    outcome: dict[str, list[str]] = collections.defaultdict(list)
    for p in paths:
        rel = str(p.relative_to(CORPUS))
        text = decode_maa(p.read_bytes())
        try:
            read_maa(text, name=p.name)
        except ValueError as e:
            cat = _category(str(e))
            outcome[cat or f"UNNAMED: {e}"].append(rel)
            continue
        except Exception as e:  # noqa: BLE001 — a crash is the finding; it is recorded, then failed on
            outcome[f"CRASH {type(e).__name__}: {e}"].append(rel)
            continue
        outcome["imported"].append(rel)
    return outcome


@pytest.fixture(scope="module")
def census():
    return _census()


def test_nothing_crashes_and_every_refusal_is_named(census):
    bad = {k: v[:3] for k, v in census.items() if k.startswith(("CRASH", "UNNAMED"))}
    assert not bad, bad


def test_the_census_is_the_one_recorded(census):
    got = {k: len(v) for k, v in census.items()}
    assert got == _EXPECTED
    assert sum(got.values()) == 935


def test_a_refusal_names_the_file(census):
    """Spot-check: a refusal carries the file name and, where one line is
    the cause, the line."""
    for cat, files in census.items():
        if cat == "imported":
            continue
        p = CORPUS / files[0]
        with pytest.raises(ValueError, match=re.escape(p.name)):
            read_maa(decode_maa(p.read_bytes()), name=p.name)
