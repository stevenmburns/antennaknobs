"""NEC5Engine (issue #825, stages 1+2): deck writer, grounds, printout
parsers, and — where a licensed binary is present — live differential
checks vs momwire.

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


class _ElevatedDipole(AntennaBuilder):
    """Horizontal 10m dipole at z=0.5 — legal over a NEC-5 ground (the
    vertical _Dipole spans z<0 and rightly refuses there)."""

    default_params = {"freq": 28.5}

    def build_wires(self):
        return [Wire((0, -2.5, 0.5), (0, 2.5, 0.5), n_seg=10, ex=1 + 0j)]


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


# ------------------------------------------------------------------ grounds


def test_ground_deck_lines(monkeypatch):
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    lines = NEC5Engine(_ElevatedDipole(), ground="pec").deck([28.5]).splitlines()
    assert "GE 1 0" in lines
    assert any(ln.startswith("GN 1") for ln in lines)
    lines = (
        NEC5Engine(_ElevatedDipole(), ground=("finite", 13.0, 0.005))
        .deck([28.5])
        .splitlines()
    )
    gn = [ln for ln in lines if ln.startswith("GN")][0].split()
    # IPERF 0 = NEC-5's native Sommerfeld; explicit FMUR/FMUI keep the
    # NOFILE token (skip table-cache files) out of the permeability slots.
    assert gn[1] == "0"
    assert float(gn[5]) == 13.0 and float(gn[6]) == 0.005
    assert gn[-1] == "NOFILE"


def test_finite_fast_refuses(monkeypatch):
    # NEC-2's GN 0 is the reflection-coefficient approximation; NEC-5's
    # IPERF 0 is full Sommerfeld and it has no refl-coef option — a silent
    # physics upgrade would corrupt cross-engine comparisons.
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    with pytest.raises(NotImplementedError, match="reflection-coefficient"):
        NEC5Engine(_ElevatedDipole(), ground=("finite-fast", 13.0, 0.005))


def test_near_unity_epsilon_refuses(monkeypatch):
    # Captured live: eps_r -> 1 degenerates NEC-5's Sommerfeld tables into
    # 1e5-ohm nonsense; the engine refuses the corner.
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    with pytest.raises(ValueError, match="too close to free space"):
        NEC5Engine(_ElevatedDipole(), ground=("finite", 1.0001, 1e-9))


class _BuriedDipole(AntennaBuilder):
    default_params = {"freq": 28.5}

    def build_wires(self):
        return [Wire((0, -2.5, -0.1), (0, 2.5, 0.5), n_seg=10, ex=1 + 0j)]


class _InPlaneDipole(AntennaBuilder):
    default_params = {"freq": 28.5}

    def build_wires(self):
        return [Wire((0, -2.5, 0.0), (0, 2.5, 0.0), n_seg=10, ex=1 + 0j)]


def test_below_ground_geometry_refuses(monkeypatch):
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    with pytest.raises(NotImplementedError, match="below z=0"):
        NEC5Engine(_BuriedDipole(), ground="pec")
    with pytest.raises(ValueError, match="lies in the ground plane"):
        NEC5Engine(_InPlaneDipole(), ground="pec")
    # The same geometries are fine in free space.
    NEC5Engine(_BuriedDipole())


def test_parse_ground_fixtures():
    for name, expect_z in [
        ("invvee_dipole_pec", 60.72 + 0.51j),
        ("invvee_dipole_sommerfeld", 65.48 - 3.04j),
    ]:
        text = (FIXTURES / f"{name}.out").read_text()
        rows = NEC5Engine._parse_input_parameters(text)[0]
        assert rows[0][2] == pytest.approx(expect_z, abs=0.01)


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


def test_deck_rp_line(monkeypatch):
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    lines = NEC5Engine(_dipole_builder()).deck([28.5], rp=(90, 360, 1, 1)).splitlines()
    assert not any(ln.startswith("XQ") for ln in lines)
    rp = [ln for ln in lines if ln.startswith("RP")][0].split()
    # NTH=90, NPH=361 (phi seam duplicated), XNDA=0, dth/dph as floats.
    assert rp[1:5] == ["0", "90", "361", "0"]


def test_parse_pattern_fixture():
    text = (FIXTURES / "invvee_dipole_pattern.out").read_text()
    gains = NEC5Engine._parse_radiation_patterns(text)
    assert len(gains) == 15  # 3 thetas x 5 phis (seam duplicated)
    assert gains[(0.0, 0.0)] == pytest.approx(2.14, abs=0.01)
    # The phi seam duplicates the phi=0 column.
    for th in (0.0, 30.0, 60.0):
        assert gains[(th, 360.0)] == gains[(th, 0.0)]


def test_parse_pattern_null_rows():
    # Vertical dipole: theta=0 rows are true nulls printed as -999.99 with
    # a BLANK SENSE column (11 tokens instead of 12) — both row shapes
    # must parse.
    text = (FIXTURES / "vertical_dipole_pattern.out").read_text()
    gains = NEC5Engine._parse_radiation_patterns(text)
    assert len(gains) == 15
    assert gains[(0.0, 0.0)] == -999.99
    assert gains[(60.0, 90.0)] > -10.0


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
@pytest.mark.parametrize("ground", ["pec", ("finite", 13.0, 0.005)])
def test_live_ground_impedance_within_cross_engine_bars(ground):
    b = _invvee_builder()
    z5 = NEC5Engine(b, ground=ground).impedance()[0]
    zm = MomwireEngine(b, ground=ground).impedance()[0]
    assert abs(z5 - zm) < 5.0


@needs_nec5
def test_live_low_height_sommerfeld_documented_gap():
    """At 0.048 wavelengths over Sommerfeld ground, NEC-5 sits ~7 ohm from
    the NEC-2 lineage (momwire 63.16-21.64j, nec2c 63.20-21.97j, NEC-5
    62.14-28.61j, all captured 2026-08-10): the resistances agree to ~1 ohm
    while the reactances split — a genuine formulation difference in the
    close-ground interaction, recorded here as the third-oracle data point
    #825 set out to collect, not averaged away with a loose bar."""

    class LowDipole(AntennaBuilder):
        default_params = {"freq": 28.5}

        def build_wires(self):
            return [Wire((0, -2.5, 0.5), (0, 2.5, 0.5), n_seg=20, ex=1 + 0j)]

    g = ("finite", 13.0, 0.005)
    z5 = NEC5Engine(LowDipole(), ground=g).impedance()[0]
    zm = MomwireEngine(LowDipole(), ground=g).impedance()[0]
    assert abs(z5.real - zm.real) < 3.0
    assert 4.0 < (zm.imag - z5.imag) < 10.0


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
def test_live_far_field_matches_momwire():
    b = _invvee_builder()
    f5 = NEC5Engine(b).far_field(n_theta=9, n_phi=36, del_theta=10, del_phi=10)
    fm = MomwireEngine(b).far_field(n_theta=9, n_phi=36, del_theta=10, del_phi=10)
    assert abs(f5.max_gain - fm.max_gain) < 0.5
    r5, rm = np.array(f5.rings), np.array(fm.rings)
    mask = (r5 > -900) & (rm > -900)
    assert np.sqrt(np.mean((r5[mask] - rm[mask]) ** 2)) < 0.5


@needs_nec5
def test_live_compare_patterns_gate(tmp_path):
    """The issue's stage gate: compare_patterns accepts an NEC5Engine and
    prints a sane row."""
    import matplotlib

    matplotlib.use("Agg")
    import antennaknobs as ant

    b = _invvee_builder()
    out = tmp_path / "cmp.png"
    ant.compare_patterns(
        [NEC5Engine(b), MomwireEngine(b)],
        fn=str(out),
        builder_names=["nec5", "momwire"],
    )
    assert out.stat().st_size > 0


@needs_nec5
def test_live_cli_roster_includes_nec5():
    from antennaknobs.cli import ENGINE_CLASSES

    assert ENGINE_CLASSES.get("nec5") is NEC5Engine
    assert find_nec5() is not None
