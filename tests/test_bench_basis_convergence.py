"""Basis-convergence census classifier (issue #477).

The census's claims rest on ``classify``: a design only enters the scored
class when the two bases actually meet (the mutual-limit criterion), errors
and conv@N are measured against that mutual value, and everything else is
reported as no-mutual or incomplete rather than silently scored. These tests
pin that reduction on synthetic rows — no solver runs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_BBC = Path(__file__).resolve().parent.parent / "scripts" / "bench_basis_convergence.py"
_spec = importlib.util.spec_from_file_location("bench_basis_convergence", _BBC)
bbc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bbc)


def _row(sin, bs2, skipped=None):
    return {
        "design": "synthetic",
        "series": {"sin": sin, "bs2": bs2},
        "skipped": skipped or {"sin": [], "bs2": []},
        "error": None,
    }


def test_mutual_limit_conv_and_coarse_error():
    """sin creeps toward the limit (converged only at the mid rung on), bs2
    is flat from the coarsest — conv@N and coarse-rung errors say exactly
    that, and the mutual limit is the mean of the two finest values."""
    row = _row(
        sin=[
            [21, 40.0, 0.0, 0.1, 100],
            [61, 49.5, 0.0, 0.1, 300],
            [161, 49.9, 0.0, 0.1, 800],
        ],
        bs2=[
            [21, 50.0, 0.0, 0.1, 100],
            [61, 50.0, 0.0, 0.1, 300],
            [161, 50.1, 0.0, 0.1, 800],
        ],
    )
    kind, st = bbc.classify(row)
    assert kind == "mutual"
    assert st["zstar"] == complex(50.0, 0.0)  # mean of 49.9 and 50.1
    assert st["conv"] == {"sin": 61, "bs2": 21}
    assert st["err_coarse"]["sin"] > 0.15 and st["err_coarse"]["bs2"] < 0.01


def test_no_mutual_limit_when_bases_disagree_at_finest():
    """Bases 20% apart at the finest rung: the design must land in the
    no-mutual class — neither basis gets scored against the other."""
    row = _row(
        sin=[[21, 100.0, 0.0, 0.1, 100], [61, 110.0, 0.0, 0.1, 300]],
        bs2=[[21, 90.0, 0.0, 0.1, 100], [61, 90.0, 0.0, 0.1, 300]],
    )
    kind, st = bbc.classify(row)
    assert kind == "no_mutual"
    assert st["agree"] > 0.2


def test_never_converged_reported_not_crashed():
    """Both bases agree at the finest rung but neither coarser rung is within
    tolerance — conv@N is None (printed as '>finest'), not an exception."""
    row = _row(
        sin=[
            [21, 30.0, 0.0, 0.1, 100],
            [61, 40.0, 0.0, 0.1, 300],
            [161, 50.0, 0.0, 0.1, 800],
        ],
        bs2=[
            [21, 70.0, 0.0, 0.1, 100],
            [61, 60.0, 0.0, 0.1, 300],
            [161, 50.5, 0.0, 0.1, 800],
        ],
    )
    kind, st = bbc.classify(row)
    assert kind == "mutual"
    assert st["conv"]["sin"] == 161 and st["conv"]["bs2"] == 161


def test_incomplete_when_an_engine_has_too_few_rungs():
    """A seg-capped engine (every rung skipped) makes the row incomplete,
    carrying the first skip reason instead of a bogus score."""
    row = _row(
        sin=[[21, 50.0, 0.0, 0.1, 100], [61, 50.0, 0.0, 0.1, 300]],
        bs2=[],
        skipped={"sin": [], "bs2": [[21, "seg-cap 9999"], [61, "seg-cap 9999"]]},
    )
    kind, why = bbc.classify(row)
    assert kind == "incomplete"
    assert "seg-cap 9999" in why
