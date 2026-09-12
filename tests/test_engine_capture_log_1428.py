"""AK#1428 — what the external engines saw: the capture dir and the run log.

A user whose NEC-5 or NEC-2 run disagrees with ours sends us the deck the
engine was given and the printout it returned. Two knobs (`antennaknobs.
engine_capture`) serve that: `ANTENNAKNOBS_CAPTURE_DIR` writes
`<engine>/<hash>.nec` + `<hash>.out` per run, `ANTENNAKNOBS_LOG_LEVEL=DEBUG`
puts both texts in the log. The frozen workbench maps `--capture-dir` and
`--log-level` onto them.

No binary runs here: each engine's run method is stubbed to return a canned
printout, so the gates are about the plumbing — the files land where the
variable says, the log carries the deck before and the printout after, and
an unset environment changes nothing.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pytest

from antennaknobs import engine_capture
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines import nec2 as nec2_mod
from antennaknobs.engines.nec2 import NEC2Engine
from antennaknobs.engines.nec5 import NEC5Engine

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "scripts" / "freeze_workbench")
)
import entry  # noqa: E402

DECK = "CM stub\nCE\nGW 1 3 0 0 1 0 0 2 0.001\nGE 0\nEX 0 1 2 0 1 0\nFR 0 1 0 0 14.1 0\nXQ 0\nEN\n"
PRINTOUT = "STUB PRINTOUT\n" * 3


# ---------------------------------------------------------------------------
# the knobs themselves
# ---------------------------------------------------------------------------


def test_g1428_1_unset_environment_is_a_no_op(monkeypatch):
    monkeypatch.delenv(engine_capture.LOG_LEVEL_ENV, raising=False)
    monkeypatch.delenv(engine_capture.CAPTURE_DIR_ENV, raising=False)
    assert engine_capture.configure_logging_from_env() is None
    assert engine_capture.capture_dir_from_env("nec5") is None


def test_g1428_2_log_level_applies_to_the_antennaknobs_tree_only(monkeypatch):
    monkeypatch.setenv(engine_capture.LOG_LEVEL_ENV, "debug")
    ak = logging.getLogger("antennaknobs")
    before = ak.level
    try:
        assert engine_capture.configure_logging_from_env() == logging.DEBUG
        assert ak.level == logging.DEBUG
        # the root's level is untouched — uvicorn / matplotlib keep theirs
        assert logging.getLogger().level != logging.DEBUG
        # idempotent: a second call installs no second handler
        n = len(logging.getLogger().handlers)
        engine_capture.configure_logging_from_env()
        assert len(logging.getLogger().handlers) == n
    finally:
        ak.setLevel(before)


def test_g1428_3_a_misspelt_level_raises_rather_than_logging_nothing(monkeypatch):
    monkeypatch.setenv(engine_capture.LOG_LEVEL_ENV, "VERBOSE")
    with pytest.raises(ValueError, match="VERBOSE"):
        engine_capture.configure_logging_from_env()


def test_g1428_4_capture_dir_is_per_engine(monkeypatch, tmp_path):
    monkeypatch.setenv(engine_capture.CAPTURE_DIR_ENV, str(tmp_path))
    assert engine_capture.capture_dir_from_env("nec5") == tmp_path / "nec5"
    assert engine_capture.capture_dir_from_env("nec2") == tmp_path / "nec2"


# ---------------------------------------------------------------------------
# NEC-5: the env var reaches the engine's own capture_dir; the log carries the texts
# ---------------------------------------------------------------------------


def _nec5(monkeypatch, **kw):
    e = NEC5Engine(Builder(), require_exe=False, **kw)
    monkeypatch.setattr(e, "_run_binary", lambda deck: PRINTOUT)
    e._exe = "stub-nec5"
    return e


def test_g1428_5_nec5_capture_from_env_writes_the_pair(monkeypatch, tmp_path):
    monkeypatch.setenv(engine_capture.CAPTURE_DIR_ENV, str(tmp_path))
    e = _nec5(monkeypatch)
    assert e._capture_dir == tmp_path / "nec5"
    assert e._run(DECK) == PRINTOUT
    h = NEC5Engine._deck_hash(DECK)
    assert (tmp_path / "nec5" / f"{h}.nec").read_text() == DECK
    assert (tmp_path / "nec5" / f"{h}.out").read_text() == PRINTOUT
    # and the #872 cache semantics stand: the same deck is served from disk
    e2 = _nec5(monkeypatch)
    monkeypatch.setattr(e2, "_run_binary", lambda deck: pytest.fail("binary ran"))
    assert e2._run(DECK) == PRINTOUT
    assert e2.run_log[-1]["cached"] is True


def test_g1428_6_nec5_explicit_capture_dir_beats_the_env(monkeypatch, tmp_path):
    monkeypatch.setenv(engine_capture.CAPTURE_DIR_ENV, str(tmp_path / "env"))
    e = _nec5(monkeypatch, capture_dir=tmp_path / "explicit")
    assert e._capture_dir == tmp_path / "explicit"


def test_g1428_7_nec5_debug_log_carries_deck_then_printout(monkeypatch, caplog):
    monkeypatch.delenv(engine_capture.CAPTURE_DIR_ENV, raising=False)
    e = _nec5(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger="antennaknobs.engines.nec5"):
        e._run(DECK)
    msgs = [r.getMessage() for r in caplog.records]
    deck_at = next(i for i, m in enumerate(msgs) if DECK in m)
    out_at = next(i for i, m in enumerate(msgs) if PRINTOUT in m)
    assert deck_at < out_at, "the deck is logged before the run, the printout after"
    assert any(
        r.levelno == logging.INFO and "printout 3 lines" in r.getMessage()
        for r in caplog.records
    )
    assert e._capture_dir is None  # unset env, no files


# ---------------------------------------------------------------------------
# NEC-2: the same, write-only
# ---------------------------------------------------------------------------


def _nec2(monkeypatch, **kw):
    monkeypatch.setattr(nec2_mod, "find_nec2", lambda explicit=None: "stub-nec2")
    monkeypatch.setattr(
        nec2_mod, "run_deck", lambda exe, deck, *, timeout, form=None: PRINTOUT
    )
    return NEC2Engine(Builder(), **kw)


def test_g1428_8_nec2_capture_from_env_writes_the_pair(monkeypatch, tmp_path):
    monkeypatch.setenv(engine_capture.CAPTURE_DIR_ENV, str(tmp_path))
    e = _nec2(monkeypatch)
    assert e._capture_dir == tmp_path / "nec2"
    # PRINTOUT carries no ANTENNA INPUT PARAMETERS and no engine error line,
    # so _run returns it untouched
    assert e._run(DECK) == PRINTOUT
    pair = sorted(p.name for p in (tmp_path / "nec2").iterdir())
    assert len(pair) == 2 and pair[0][-4:] == ".nec" and pair[1][-4:] == ".out"
    assert (tmp_path / "nec2" / pair[0]).read_text() == DECK


def test_g1428_9_nec2_debug_log_carries_deck_then_printout(monkeypatch, caplog):
    monkeypatch.delenv(engine_capture.CAPTURE_DIR_ENV, raising=False)
    e = _nec2(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger="antennaknobs.engines.nec2"):
        e._run(DECK)
    msgs = [r.getMessage() for r in caplog.records]
    assert next(i for i, m in enumerate(msgs) if DECK in m) < next(
        i for i, m in enumerate(msgs) if PRINTOUT in m
    )
    assert e._capture_dir is None


# ---------------------------------------------------------------------------
# the frozen workbench's flags become the variables
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["--log-level", "DEBUG", "--capture-dir", "/tmp/caps"],
        ["--log-level=DEBUG", "--capture-dir=/tmp/caps"],
    ],
)
def test_g1428_10_entry_flags_map_onto_the_variables(monkeypatch, argv):
    # setenv, not delenv: `_apply_capture_opts` writes os.environ directly, and
    # a delenv on an absent name records nothing to restore — the first run of
    # this file leaked /tmp/caps into test_nec5_engine's no-cache test.
    monkeypatch.setenv(engine_capture.LOG_LEVEL_ENV, "")
    monkeypatch.setenv(engine_capture.CAPTURE_DIR_ENV, "")
    opts = entry._parse(argv)
    assert opts["log_level"] == "DEBUG" and opts["capture_dir"] == "/tmp/caps"
    entry._apply_capture_opts(opts)
    assert engine_capture.capture_dir_from_env("nec5") == Path("/tmp/caps") / "nec5"
    assert engine_capture.configure_logging_from_env() == logging.DEBUG
    logging.getLogger("antennaknobs").setLevel(logging.NOTSET)


def test_g1428_11_entry_without_the_flags_sets_nothing(monkeypatch):
    monkeypatch.setenv(engine_capture.LOG_LEVEL_ENV, "")
    monkeypatch.setenv(engine_capture.CAPTURE_DIR_ENV, "")
    entry._apply_capture_opts(entry._parse(["--no-browser"]))
    assert engine_capture.capture_dir_from_env("nec5") is None
    assert engine_capture.configure_logging_from_env() is None


def test_g1428_12_the_deck_hash_names_the_pair():
    # the file name is the deck's own hash, so the same deck shares one pair
    assert NEC5Engine._deck_hash(DECK) == NEC5Engine._deck_hash(DECK)
    assert NEC5Engine._deck_hash(DECK) != NEC5Engine._deck_hash(DECK + "CM x\n")
    assert np.all([c in "0123456789abcdef" for c in NEC5Engine._deck_hash(DECK)])
