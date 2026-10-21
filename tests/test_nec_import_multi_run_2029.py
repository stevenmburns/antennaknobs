"""A later run's EX cards are a later case, not more ports (AK#2029).

SimNEC's fieldSensing decks solve one structure twice: run 1 drives the
antenna's feed with the probe wire's segment at a token 1e-10 V, then XQ, then
run 2 swaps the two amplitudes. NEC starts a new excitation set at an EX card
read after an execute request (XQ, RP, NE, NH), so the deck holds two cases of
two sources each, not four sources. The importer used to collect every EX card
into one list, so each segment got two ports and the solve refused the
duplicate under the AK#1469 guard (Ward's launch-angle decks, 2026-10-19).

The app models one case. The first run's sources become the ports; the later
runs' EX cards are counted and named in the import note. The strong gate is
that a two-run deck solves to exactly what its first run alone solves to.
"""

import numpy as np
import pytest

from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec

# A dipole and a short probe wire beside it, in free space: small enough to
# solve in a test, the same two-run shape as the reported decks.
GEOMETRY = """\
CM two-run fieldSensing shape (AK#2029)
CE
GW 1 21 0 -5 10 0 5 10 0.001
GW 2 11 30 0 9 30 0 11 0.001
GE 0
FR 0 1 0 0 14.0 1
"""

# I4 = 0 is NEC-2's centre gap; I4 = 2 is NEC-5's segment-end source, which
# the importer reads through a different port plan (knots, not segments).
RUN = "EX 0 1 11 {i4} {a}\nEX 0 2 6 {i4} {b}\nRP 0 1 1 1000 80 0 0 0\nXQ\n"


def _two_runs(i4):
    return (
        GEOMETRY
        + RUN.format(i4=i4, a="1.0", b="1e-10")
        + RUN.format(i4=i4, a="1e-10", b="1.0")
        + "EN\n"
    )


def _first_run_only(i4):
    return GEOMETRY + RUN.format(i4=i4, a="1.0", b="1e-10") + "EN\n"


def _solve(text, tmp_path, name):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    cls = builder_from_file(str(path))
    return MomwireEngine(cls(), ground=cls.file_ground)


@pytest.mark.parametrize("i4", [0, 2])
def test_the_first_runs_sources_are_the_ports(i4):
    deck = parse_nec(_two_runs(i4), name="two.nec", network=True)
    assert [(f.wire, f.seg, f.voltage) for f in deck.feeds] == [
        (0, 11, 1.0),
        (1, 6, 1e-10),
    ]
    assert [r for r, _ in deck.later_run_ex] == [2, 2]
    assert len(deck.network().ports) == 2


@pytest.mark.parametrize("i4", [0, 2])
def test_the_import_note_says_only_run_one_is_modelled(i4):
    note = parse_nec(_two_runs(i4), name="two.nec", network=True).skipped_note()
    assert "in 2 runs" in note
    assert "only the first run's sources are modelled" in note
    assert "the 2 EX cards after its first XQ, RP or NE" in note


@pytest.mark.parametrize("i4", [0, 2])
def test_a_two_run_deck_solves_as_its_first_run(i4, tmp_path):
    z_two = np.asarray(_solve(_two_runs(i4), tmp_path, "two.nec").impedance())
    z_one = np.asarray(_solve(_first_run_only(i4), tmp_path, "one.nec").impedance())
    assert z_two.shape == (2,)
    assert np.array_equal(z_two, z_one)


def test_a_one_run_deck_is_untouched():
    deck = parse_nec(_first_run_only(0), name="one.nec", network=True)
    assert len(deck.feeds) == 2
    assert deck.later_run_ex == ()
    assert "runs" not in (deck.skipped_note() or "")


def test_an_rp_alone_ends_the_run():
    """RP executes as XQ does, so an EX after it is the next run's."""
    text = (
        GEOMETRY
        + "EX 0 1 11 0 1.0\nRP 0 1 1 1000 80 0 0 0\n"
        + "EX 0 2 6 0 1.0\nRP 0 1 1 1000 80 0 0 0\nEN\n"
    )
    deck = parse_nec(text, name="rp.nec", network=True)
    assert [(f.wire, f.seg) for f in deck.feeds] == [(0, 11)]
    assert [r for r, _ in deck.later_run_ex] == [2]


def test_one_run_still_refuses_two_ex_cards_on_one_segment():
    """The guard this change must not weaken: within ONE run, two EX cards on
    one segment are still refused by name."""
    text = GEOMETRY + "EX 0 1 11 0 1.0\nEX 0 1 11 0 0.5\nXQ\nEN\n"
    with pytest.raises(ValueError, match="more than one EX card"):
        parse_nec(text, name="dup.nec", network=True).network()


def test_over_buried_radials():
    """The reported shape: NEC-5 end sources, a vertical over buried radials
    on Sommerfeld ground, a far probe wire. Parse only; the buried solve is
    too slow for the default lane and nothing in it depends on the runs."""
    text = """\
CM NEC5
CE
GW 1 20 -642.79 0 768.04 -642.79 0 766.04 6.45e-4
GW 2 20 0 0 -0.1 5 0 -0.1 6.45e-4
GW 3 20 0 0 -0.1 -5 0 -0.1 6.45e-4
GW 6 2 0 0 0 0 0 -0.1 6.45e-4
GW 7 20 0 0 5 0 0 0.1 6.45e-4
GW 8 2 0 0 0.1 0 0 0 6.45e-4
GE -1
GN 2 0 0 0 13.0 0.005 0 0 NOFILE
FR 0 1 0 0 29.7 1
EX 0 1 10 2 1e-10
EX 0 8 1 2 1.0
RP 0 46 181 1001 0 0 2 2 1000
XQ
EX 0 1 10 2 1.0
EX 0 8 1 2 1e-10
RP 0 46 181 1001 0 0 2 2 1000
XQ
EN
"""
    deck = parse_nec(text, name="buried.nec", network=True)
    assert [(f.wire, f.seg, f.edge) for f in deck.feeds] == [(0, 10, 2), (5, 1, 2)]
    assert [f.voltage for f in deck.feeds] == [1e-10, 1.0]
    assert [r for r, _ in deck.later_run_ex] == [2, 2]
    assert len(deck.network().ports) == 2
