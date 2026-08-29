"""PyNEC as the import-divergence canary (issue #946).

PyNEC/nec2++ and nec2c are near enough to the same physics that a large
PyNEC ΔΓ does not mean the solvers disagree — it means the geometry the
importer handed PyNEC is not the deck nec2c read. The corpus baseline is
a 0.0002 median with p90 0.0077, so a deck at 0.08 is orders out of
family.

The live example is ``k9ay_orig``: a GX-symmetric deck whose LD lands on
the symmetry cell, so NEC also loads the driven image while our importer
loads one tag. Its recorded benchmark row is 0.0838 / 0.0837 / 0.0899 /
0.0892 — every engine the same distance out, which is the signature no
solver-physics story explains.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bench_nec_corpus import (
    _CANARY_FLOOR,
    _CANARY_MIN_BASELINE,
    clean_deck,
    import_canary,
)

ENGINES = ("pynec", "sin", "bs1", "bs2")


def row(deck, dgammas, **flags):
    """A minimal bench row: one feed, one ΔΓ per engine."""
    r = {
        "deck": deck,
        "nec2c": {"z": [[50.0, 0.0]]},
        "engines": {
            e: {"cmp": [{"dgamma": dg, "abs": 0.0, "engine": [50.0, 0.0]}]}
            for e, dg in zip(ENGINES, dgammas)
        },
    }
    r.update(flags)
    return r


def quiet(n, dg=0.0002):
    return [row(f"quiet{i}", [dg, 0.005, 0.01, 0.01]) for i in range(n)]


def test_clustered_outlier_is_flagged():
    """k9ay_orig's real numbers: flagged, and marked clustered."""
    k9ay = row("k9ay_orig", [0.0838, 0.0837, 0.0899, 0.0892])
    median, threshold, suspects, n = import_canary(quiet(20) + [k9ay], ENGINES)

    assert median == 0.0002
    assert n >= _CANARY_MIN_BASELINE
    assert threshold == _CANARY_FLOOR  # floor dominates a quiet corpus
    assert [s[0]["deck"] for s in suspects] == ["k9ay_orig"]
    assert suspects[0][1] == 0.0838
    assert suspects[0][2] is True, "all four engines within 50% — clustered"


def test_quiet_corpus_flags_nothing():
    assert import_canary(quiet(20), ENGINES)[2] == []


def test_pynec_only_outlier_is_not_clustered():
    """PyNEC far out while the others sit close is NOT the import signature —
    it is the #448 Sommerfeld-unreliability shape, and must be reported as
    such rather than blamed on the importer."""
    odd = row("pynec_only", [0.30, 0.004, 0.006, 0.005])
    *_, suspects, _ = import_canary(quiet(20) + [odd], ENGINES)

    assert [s[0]["deck"] for s in suspects] == ["pynec_only"]
    assert suspects[0][2] is False


def test_suspects_are_worst_first():
    rows = quiet(20) + [
        row("mild", [0.03, 0.031, 0.032, 0.030]),
        row("severe", [0.5, 0.51, 0.52, 0.50]),
    ]
    assert [s[0]["deck"] for s in import_canary(rows, ENGINES)[2]] == [
        "severe",
        "mild",
    ]


def test_labeled_decks_cannot_inflate_the_threshold():
    """A noisy cohort that is already labeled (unsupported ground, partial
    network, ...) is excluded from the baseline — otherwise a handful of
    known-special decks would raise the median enough to hide a real
    suspect."""
    noisy = [
        row(f"ground{i}", [0.4, 0.4, 0.4, 0.4], ground_supported=False)
        for i in range(20)
    ]
    median, _, suspects, _ = import_canary(
        quiet(5) + noisy + [row("s", [0.08] * 4)], ENGINES
    )

    assert median == 0.0002, "baseline ignores the labeled decks"
    assert "s" in [x[0]["deck"] for x in suspects]


def test_threshold_scales_with_a_noisy_baseline():
    """When the whole corpus is genuinely noisy the absolute floor would flag
    everything, so the multiple takes over."""
    median, threshold, suspects, _ = import_canary(quiet(20, dg=0.01), ENGINES)

    assert median == 0.01
    assert threshold == 25.0 * 0.01 > _CANARY_FLOOR
    assert suspects == []


def test_short_run_uses_the_floor_so_the_suspect_cannot_hide():
    """Regression for the shape found in review: on a 3-deck run the suspect
    dominates its own baseline (median 0.0424 → 25× → threshold 1.06) and
    would be missed. Below the sample gate the median says nothing about
    corpus noise, so the floor is the honest test."""
    rows = [
        row("2m_bigwheel", [0.0001, 0.0002, 0.1590, 0.1596]),
        row("40m-moxon", [0.0003, 0.0010, 0.0087, 0.0065], stepped_radius=True),
        row("k9ay_orig", [0.0848, 0.0767, 0.0899, 0.0892]),
    ]
    _, threshold, suspects, n = import_canary(rows, ENGINES)

    assert n < _CANARY_MIN_BASELINE
    assert threshold == _CANARY_FLOOR
    assert [s[0]["deck"] for s in suspects] == ["k9ay_orig"]


def test_engine_without_pynec_is_inert():
    rows = [row("d", [0.9, 0.9, 0.9, 0.9])]
    assert import_canary(rows, ("sin", "bs2")) == (None, None, [], 0)


def test_errored_and_missing_results_are_skipped():
    r = row("half", [0.0002, 0.005, 0.01, 0.01])
    r["engines"]["pynec"] = {"error": "boom"}
    assert import_canary(quiet(5) + [r], ENGINES)[2] == []


def test_clean_deck_excludes_every_labeled_cohort():
    base = row("x", [0.0] * 4)
    assert clean_deck(base)
    for flag, value in (
        ("ground_supported", False),
        ("partial_net", True),
        ("virtualized_anchors", True),
        ("stepped_radius", True),
    ):
        assert not clean_deck(row("x", [0.0] * 4, **{flag: value})), flag

    resolved = row("x", [0.0] * 4)
    resolved["nec2c"]["resolved_deck"] = True
    assert not clean_deck(resolved)
