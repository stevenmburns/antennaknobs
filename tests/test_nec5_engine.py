"""NEC5Engine (issue #825, stage 1): deck writer, printout parsers, and —
where a licensed binary is present — live differential checks vs momwire.

Parser tests run everywhere, pinned by the captured printouts in
tests/fixtures/nec5/ (End-User Reports; NEC-5 is (c) LLNL,
LLNL-CODE-746721 — the binary itself is user-licensed and never
distributed with antennaknobs)."""

import sys
from pathlib import Path

import numpy as np
import pytest

from antennaknobs import resolve_variant_params
from antennaknobs.builder import AntennaBuilder
from antennaknobs.designs.dipoles.invvee import Builder as InvVee
from antennaknobs.engines import MomwireEngine, NEC5Engine
from antennaknobs.engines.nec5 import NEC5Error, find_nec5
from antennaknobs.network import Wire

from conftest import needs_nec5

FIXTURES = Path(__file__).parent / "fixtures" / "nec5"


class _Dipole(AntennaBuilder):
    """Minimal 10m straight dipole, fed mid-wire with an odd segment count
    so the even-parity coercion is exercised."""

    default_params = {"freq": 28.5}

    def build_wires(self):
        return [Wire((0, 0, -2.5), (0, 0, 2.5), n_seg=9, ex=1 + 0j)]


def _dipole_builder():
    return _Dipole()


def _invvee_builder():
    return InvVee(resolve_variant_params(InvVee, "dipole"))


# --------------------------------------------------------------- deck writer


def test_deck_structure_and_knot_feed(monkeypatch):
    monkeypatch.setenv("NEC5_EXE", sys.executable)  # any executable satisfies the gate
    e = NEC5Engine(_dipole_builder())
    deck = e.deck([28.5])
    lines = deck.strip().splitlines()
    gw = [ln for ln in lines if ln.startswith("GW")]
    assert len(gw) == 1
    # Even-parity coercion: the fed 9-segment wire is bumped to 10, and the
    # source lands on end 2 of segment 5 — the wire's center knot.
    assert gw[0].split()[2] == "10"
    assert "GE 0 0" in lines
    ex = [ln for ln in lines if ln.startswith("EX")][0].split()
    assert ex[1:5] == ["0", "1", "5", "2"]
    assert lines[-1] == "EN"
    assert [ln for ln in lines if ln.startswith("FR")][0].split()[2] == "1"


def test_deck_rejects_ragged_frequency_grid(monkeypatch):
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    e = NEC5Engine(_dipole_builder())
    with pytest.raises(ValueError, match="uniformly spaced"):
        e.deck([28.0, 28.5, 29.5])


def test_missing_binary_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("NEC5_EXE", raising=False)
    with pytest.raises(NEC5Error, match="NEC5_EXE"):
        NEC5Engine(_dipole_builder())


def test_ground_refuses_in_stage_1(monkeypatch):
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    with pytest.raises(NotImplementedError, match="free-space"):
        NEC5Engine(_dipole_builder(), ground=("finite", 10.0, 0.002))


# ------------------------------------------------------------------- parsers


def test_parse_single_frequency_fixture():
    text = (FIXTURES / "invvee_dipole_single.out").read_text()
    per_freq = NEC5Engine._parse_input_parameters(text)
    assert len(per_freq) == 1
    rows = per_freq[0]
    assert len(rows) == 1
    tag, seg, z = rows[0]
    # The invvee dipole feeds its 2-segment bridge wire (tag 3) after two
    # 20-segment arms: the printout's SEG. NO. is ABSOLUTE (41), the pinned
    # dialect fact the engine translates for.
    assert (tag, seg) == (3, 41)
    assert z == pytest.approx(70.746 - 8.5699j, rel=1e-3)


def test_parse_sweep_fixture_has_three_sections():
    text = (FIXTURES / "invvee_dipole_sweep3.out").read_text()
    per_freq = NEC5Engine._parse_input_parameters(text)
    assert len(per_freq) == 3
    zs = [rows[0][2] for rows in per_freq]
    # Reactance must climb through the sweep (27.5 → 28.5 MHz below/near
    # resonance); pins section ordering as much as values.
    assert zs[0].imag < zs[1].imag < zs[2].imag


def test_parse_currents_fixture():
    text = (FIXTURES / "invvee_dipole_single.out").read_text()
    per_tag = NEC5Engine._parse_wire_currents(text)[0]
    assert sorted(per_tag) == [1, 2, 3]
    assert len(per_tag[1]) == 20 and len(per_tag[2]) == 20 and len(per_tag[3]) == 2
    # Feed-bridge current is the drive current: biggest in the model.
    peak = max(abs(c) for curs in per_tag.values() for c in curs)
    assert max(abs(c) for c in per_tag[3]) == pytest.approx(peak)


def test_faulty_deck_printout_raises():
    text = (FIXTURES / "faulty_deck_error.out").read_text()
    with pytest.raises(NEC5Error, match="No model data"):
        NEC5Engine._parse_input_parameters(text)


# ---------------------------------------------------------------- live runs


def _yagi_builder():
    from antennaknobs.designs.beams.yagi import Builder as Yagi

    return Yagi()


@needs_nec5
@pytest.mark.parametrize("make_builder", [_invvee_builder, _yagi_builder])
def test_live_impedance_within_cross_engine_bars(make_builder):
    b = make_builder()
    z5 = NEC5Engine(b).impedance()[0]
    zm = MomwireEngine(b).impedance()[0]
    # Different formulations (NEC-5 mixed-potential vs momwire thin-wire):
    # agreement to a few ohms is the expected bar, not identity.
    assert abs(z5 - zm) < 5.0


@needs_nec5
def test_live_sweep_shape_and_continuity():
    e = NEC5Engine(_invvee_builder())
    zs = e.impedance_sweep(np.array([28.0, 28.25, 28.5]))
    assert zs.shape == (3, 1)
    assert np.all(np.abs(np.diff(zs[:, 0])) < 30.0)


@needs_nec5
def test_live_currents_match_momwire_peak():
    b = _invvee_builder()
    c5 = NEC5Engine(b).current_distribution()
    cm = MomwireEngine(b).current_distribution()
    # Entry counts differ by design: momwire chains tuples into polylines
    # (one entry here), NEC5Engine reports per build_wires() tuple (like
    # PyNEC). Compare the physics, not the packaging.
    assert len(c5) == 3
    p5 = max(abs(w.knot_currents).max() for w in c5)
    pm = max(abs(w.knot_currents).max() for w in cm)
    assert p5 == pytest.approx(pm, rel=0.05)


@needs_nec5
def test_live_cli_roster_includes_nec5():
    from antennaknobs.cli import ENGINE_CLASSES

    assert ENGINE_CLASSES.get("nec5") is NEC5Engine
    assert find_nec5() is not None
