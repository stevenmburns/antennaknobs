"""NEC-5 drives a network-driven design's single-deck readings at its ports'
resolved voltages (AK#1627).

The multiport-Y route (#1280) writes no EX of its own. That is right for the Y
runs, which bring their own, but every single-deck reading (the pattern, the
currents, the power budget, the whole web solve) went out with NO EX, so NEC-5
solved an unexcited structure. AC6LA's failEZN5 failed on NEC-5 with its
printout ending `***** INPUT LINE 6 EN`.

Every real port is now driven at the voltage the network resolves for it, as
PyNEC's `_excited_real_context` does.

NEC-5's OWN gain on this route stays what NEC-5 reports: per watt into the
structure, which excludes what the network burns (failEZN5's lossy line and
transformer take 48 %). Rescaling it to the app's per-source-watt convention
was measured and HELD (USER DECISION 2026-09-21), so the pattern test here
pins its SHAPE against the licensed printout, not its level.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from conftest import needs_nec5

from antennaknobs.engines.nec5 import NEC5Engine, NEC5Error
from antennaknobs.file_designs import builder_from_file

FAIL = Path(__file__).parent / "fixtures" / "eznec_virtual_wire_1577" / "failEZN5.nec"
FAIL_OUT = FAIL.with_suffix(".out")


def _engine():
    cls = builder_from_file(str(FAIL))
    return NEC5Engine(cls(), ground=cls.file_ground, require_exe=False)


def _ex_cards(deck):
    return [ln.split() for ln in deck.splitlines() if ln.startswith("EX ")]


# ---------------------------------------------------------------------------
# no binary
# ---------------------------------------------------------------------------


def test_the_network_route_writes_no_ex_of_its_own():
    """The premise: without `_drive_sources` the deck is unexcited."""
    eng = _engine()
    assert eng._use_reducer and eng._sources == []
    assert _ex_cards(eng.deck([eng.builder.freq])) == []


def test_every_single_deck_reading_is_excited(monkeypatch):
    """Each reading that writes one deck (the web solve, the currents, the
    pattern, the budget, the average gain) now carries an EX per driven port.
    The Y is fixed here so no binary runs; each reading stops at its deck."""
    eng = _engine()
    n = len(eng._real_port_names)
    Y = np.eye(n) * (0.01 - 0.02j) + 0.002
    monkeypatch.setattr(eng, "_compute_y_matrix", lambda _wl: Y)

    class _Stop(Exception):
        pass

    decks = []

    def run(deck):
        decks.append(deck)
        raise _Stop

    monkeypatch.setattr(eng, "_run", run)
    readings = (
        eng.solve_snapshot,
        eng.current_distribution,
        eng.far_field,
        eng.power_budget,
        eng.average_power_gain,
    )
    for reading in readings:
        with pytest.raises(_Stop):
            reading()
    assert len(decks) == len(readings)
    assert all(_ex_cards(d) for d in decks), [d for d in decks if not _ex_cards(d)]


def test_the_web_nec_rp_trace_is_excited(monkeypatch):
    """The app's NEC rp trace writes its own RP deck in the adapter rather
    than through `far_field`, and missed the fix above: on this route it
    printed no pattern at all (`no RADIATION PATTERNS in NEC-5 printout`)."""
    import antennaknobs.web.examples  # noqa: F401  (before the adapter)
    from antennaknobs.web import adapter

    real_make = adapter._make_nec5_engine
    real_init = NEC5Engine.__init__
    monkeypatch.setattr(
        NEC5Engine,
        "__init__",
        lambda self, *a, **kw: real_init(self, *a, **{**kw, "require_exe": False}),
    )

    def make(req, builder):
        eng = real_make(req, builder)
        n = len(eng._real_port_names)
        Y = np.eye(n) * (0.01 - 0.02j) + 0.002
        monkeypatch.setattr(eng, "_compute_y_matrix", lambda _wl: Y)
        monkeypatch.setattr(eng, "_run", run)
        return eng

    class _Stop(Exception):
        pass

    decks = []

    def run(deck):
        decks.append(deck)
        raise _Stop

    monkeypatch.setattr(adapter, "_make_nec5_engine", make)
    cls = builder_from_file(str(FAIL))
    ex = adapter._make_example("failEZN5", cls)
    f = cls().freq
    with pytest.raises(_Stop):
        ex.nec5_pattern({"measurement_freq_mhz": f, "design_freq_mhz": f})
    (deck,) = decks
    assert "RP " in deck and _ex_cards(deck)


def test_every_real_port_is_driven_at_its_resolved_voltage():
    eng = _engine()
    V = [0.3 - 0.2j, 1.1 + 0.4j]
    sources = eng._real_port_sources(V)
    assert [(idx, knot) for idx, _t, _v, knot in sources] == [
        eng._port_attach[n] for n in eng._real_port_names
    ]
    cards = _ex_cards(eng.deck([eng.builder.freq], sources=sources))
    assert [complex(float(f[5]), float(f[6])) for f in cards] == [
        pytest.approx(v) for v in V
    ]


def test_a_port_at_zero_volts_gets_no_card():
    """NEC-5 reads a zero-amplitude EX as 1 V, and an unfed knot already IS
    the 0 V short."""
    eng = _engine()
    (only,) = eng._real_port_sources([0.0, 2.0 + 0j])
    assert only[2] == 2.0 and only[3] == eng._port_attach[eng._real_port_names[1]][1]
    with pytest.raises(NEC5Error, match="0 V"):
        eng._real_port_sources([0.0, 0.0])


def test_the_native_route_is_unchanged():
    from antennaknobs import resolve_variant_params
    from antennaknobs.designs.dipoles.invvee import Builder

    eng = NEC5Engine(
        Builder(resolve_variant_params(Builder, "dipole")), require_exe=False
    )
    assert eng._drive_sources(eng.builder.freq) is eng._sources


# ---------------------------------------------------------------------------
# the licensed binary
# ---------------------------------------------------------------------------


def _licensed_theta76_row():
    """The licensed engine on EZNEC's OWN deck, which carries the network as
    native cards and an RP cut at theta 76: the committed printout."""
    gains = NEC5Engine._parse_radiation_patterns(FAIL_OUT.read_text(errors="replace"))
    return {ph: v for (th, ph), v in gains.items() if th == 76.0}


@needs_nec5
def test_failEZN5_has_a_pattern_with_the_licensed_engines_shape():
    """Its SHAPE, peak-relative: the level on this route is NEC-5's gain per
    structure watt, which is held as reported (see the module docstring)."""
    cls = builder_from_file(str(FAIL))
    eng = NEC5Engine(cls(), ground=cls.file_ground)
    ff = eng.far_field(n_theta=90, n_phi=36, del_theta=1, del_phi=10)
    ref = _licensed_theta76_row()
    assert max(ref.values()) == pytest.approx(-0.86, abs=0.005)  # the control
    ours = np.asarray(ff.rings[76])
    theirs = np.asarray([ref[float(ph)] for ph in ff.phis])
    # The printout carries two decimals.
    assert ours - ours.max() == pytest.approx(theirs - theirs.max(), abs=0.02)


@needs_nec5
def test_failEZN5_web_snapshot_solves():
    cls = builder_from_file(str(FAIL))
    eng = NEC5Engine(cls(), ground=cls.file_ground)
    zs, currents, _budget = eng.solve_snapshot()
    assert complex(zs[0]) == pytest.approx(48.919 + 103.89j, rel=1e-4)
    assert max(float(np.max(np.abs(w.knot_currents))) for w in currents) > 0.1
    # The network's source power, not the structure's.
    assert eng._excited_p_in == pytest.approx(0.5 * 48.919 * 1.414214**2, rel=1e-3)
    assert 0.0 < eng._excited_efficiency < 0.6
    assert eng._excited_power_budget[-1][0] == "Wire loss"


@needs_nec5
def test_the_native_cardioid_is_untouched(tmp_path, monkeypatch):
    """A design with its own EX cards writes the same deck as before."""
    cls = builder_from_file(
        str(Path(__file__).parent / "fixtures/eznec_gyrator_1595/Cardioidmodnec5.nec")
    )
    eng = NEC5Engine(cls(), ground=cls.file_ground)
    seen = []
    real = eng._run
    monkeypatch.setattr(eng, "_run", lambda d: (seen.append(d), real(d))[1])
    eng.current_distribution()
    assert seen == [eng.deck([eng.builder.freq])]
