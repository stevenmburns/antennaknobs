"""NEC5Engine (issue #825, stages 1-5): deck writer, grounds, patterns,
network ports, loads and printout parsers — plus, where a licensed binary
is present, live differential checks vs momwire.

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


class _StraddlingDipole(AntennaBuilder):
    """Crosses the plane mid-span — the geometry the binary runs without
    complaint and prints garbage for (stage-1 capture)."""

    default_params = {"freq": 28.5}

    def build_wires(self):
        return [Wire((0, -2.5, -0.1), (0, 2.5, 0.5), n_seg=10, ex=1 + 0j)]


class _InPlaneDipole(AntennaBuilder):
    default_params = {"freq": 28.5}

    def build_wires(self):
        return [Wire((0, -2.5, 0.0), (0, 2.5, 0.0), n_seg=10, ex=1 + 0j)]


class _ContactMonopoleOverBuriedRadials(AntennaBuilder):
    """The momwire#567 anchor class: a fed 10 m contact monopole over four
    detached radials 15 cm down — wholly-below wires plus a legal contact
    end at z=0."""

    default_params = {"freq": 7.0}

    def build_wires(self):
        mono = Wire((0, 0, 10.0), (0, 0, 0.0), n_seg=14, ex=1 + 0j)
        radials = [
            Wire((0, 0, -0.15), (5 * dx, 5 * dy, -0.15), n_seg=10)
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
        ]
        return [mono, *radials]


class _FullyBuriedFedDipole(AntennaBuilder):
    """The antennaknobs#1025 class: wire AND excitation below the interface,
    nothing touching z=0 — `specialty.buried_dipole`'s geometry, meshed
    verbatim so the gate does not move when auto_mesh does."""

    default_params = {"freq": 7.1}

    def build_wires(self):
        z, half, gap = -0.15, 2.9557, 0.025
        return [
            Wire((-half, 0.0, z), (-gap, 0.0, z), n_seg=25),
            Wire((-gap, 0.0, z), (gap, 0.0, z), n_seg=2, ex=1 + 0j),
            Wire((gap, 0.0, z), (half, 0.0, z), n_seg=25),
        ]


def test_ground_geometry_refusals(monkeypatch):
    """What still refuses after the buried stage, each by name: mid-span
    straddles (the binary runs them and prints garbage), in-plane wires,
    and buried wires under a PEC ground (image theory has no buried
    side)."""
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    with pytest.raises(NotImplementedError, match="mid-span"):
        NEC5Engine(_StraddlingDipole(), ground="pec")
    with pytest.raises(NotImplementedError, match="mid-span"):
        NEC5Engine(_StraddlingDipole(), ground=("finite", 13.0, 0.005))
    with pytest.raises(ValueError, match="lies in the ground plane"):
        NEC5Engine(_InPlaneDipole(), ground="pec")
    with pytest.raises(NotImplementedError, match="Sommerfeld"):
        NEC5Engine(_ContactMonopoleOverBuriedRadials(), ground="pec")
    # The same geometries are fine in free space (no ground, no rules).
    NEC5Engine(_StraddlingDipole())
    NEC5Engine(_ContactMonopoleOverBuriedRadials())


def test_buried_deck_ground_flag_follows_the_deck(monkeypatch):
    """The ground flag is decided by BURIAL, not by contact (#1025).

    The flag lives in GE's FIRST field; the second is the segment-check flag
    and is physics-irrelevant here (-1, 0 and 2 print the same impedance to
    every digit on both classes). This wrapper once wrote `GE 1 -1` for every
    buried deck, reading that -1 as "buried support".

    The rule went through one wrong intermediate worth recording, because the
    measurement that settled it is subtle. It briefly keyed on whether a wire
    END touched z=0, on the evidence that flag -1 made the binary refuse such
    a deck. That refusal is real but it is not a reason to reach for flag 1:
    it means the deck has no basis function at that node, and the fix is to
    continue the conductor BELOW the plane, not to change the flag. Keyed on
    burial, the connected screen tracks momwire to 2.6 % in R where flag 1 was
    34.6 % off.

    So: buried wires anywhere -> -1. No buried wires -> 1, untouched.
    """
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    ground = ("finite", 13.0, 0.005)

    from antennaknobs.designs.verticals.buried_radial_vertical import (
        Builder as BuriedRadialVertical,
    )

    # Buried wires with a conductor crossing the plane: flag -1.
    lines = NEC5Engine(BuriedRadialVertical(), ground=ground).deck([7.1]).splitlines()
    assert "GE -1 0" in lines

    # Buried wires, nothing touching the plane at all: also -1.
    lines_below = (
        NEC5Engine(_FullyBuriedFedDipole(), ground=ground).deck([7.1]).splitlines()
    )
    assert "GE -1 0" in lines_below

    # No buried wires: flag 1, exactly as stage 1 wrote it.
    lines_above = NEC5Engine(_ElevatedDipole(), ground=ground).deck([28.5]).splitlines()
    assert "GE 1 0" in lines_above
    gn = [ln for ln in lines_above if ln.startswith("GN")][0].split()
    assert gn[1] == "0" and float(gn[5]) == 13.0


def test_terminating_on_the_plane_over_buried_wires_is_refused(monkeypatch):
    """The refusal names the geometry and the way out (#1025).

    `_ContactMonopoleOverBuriedRadials` is the shape: a monopole whose base
    END sits at z=0, buried radials underneath, nothing continuing below the
    node. Flag -1 gives that node no basis function, so the conductor reads as
    open-circuited (598.320-54434.000j on the catalog's detached variant);
    flag 1 bonds it and prints a plausible number that is 34.6 % from momwire
    on the connected screen. Neither is a serve, so it refuses.

    Free space is untouched — the rule is about the ground card, and there is
    no ground card."""
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    with pytest.raises(NotImplementedError, match="ends ON the ground plane"):
        NEC5Engine(_ContactMonopoleOverBuriedRadials(), ground=("finite", 13.0, 0.005))
    NEC5Engine(_ContactMonopoleOverBuriedRadials())


# The momwire#567 four-radial anchor deck, verbatim from momwire
# tests/golden_buried_anchor_nec5.py (generated by
# scripts/capture_buried_anchor_nec5.py; NEC-5 is (c) LLNL,
# LLNL-CODE-746721). The banked literal below is what the binary PRINTS
# for it — same binary, same cards, same print.
#
# Kept verbatim, INCLUDING its `GE 1,-1`, even though antennaknobs#1025
# stopped the wrapper writing that flag: this gates the parser and the
# binary plumbing on a buried printout, and a golden that reproduces is
# doing its job whatever the deck says. What the number may be CITED as is
# a separate question, on momwire#925 — that deck is the contact class with
# nothing continuing below the plane, which the wrapper now refuses to
# build.
_ANCHOR_FOUR_RADIAL_DECK = (
    "CM momwire#567 anchor four-radial\n"
    "CE\n"
    "GW 1,15,0.,0.,10.,0.,0.,0.,.001\n"
    "GW 2,10,0.,0.,-0.15,5.,0.,-0.15,.001\n"
    "GW 3,10,0.,0.,-0.15,0.,5.,-0.15,.001\n"
    "GW 4,10,0.,0.,-0.15,-5.,0.,-0.15,.001\n"
    "GW 5,10,0.,0.,-0.15,0.,-5.,-0.15,.001\n"
    "GE 1,-1\n"
    "FR 0,1,0,0,7.\n"
    "GN 0,0,0,0,13.,.005\n"
    "EX 4,1,7,0,1.,0.\n"
    "PQ 0\n"
    "XQ 0\n"
    "EN\n"
)
_ANCHOR_FOUR_RADIAL = 90.0510 - 70.7310j


def test_coincident_wires_refuse_by_name(monkeypatch):
    """The buried-radial catalog design's N-coincident-rise bundle is
    momwire's spelling; NEC-5 prints garbage for the overlap silently
    (measured: 3271-3374j with a 2e+25 % radiated power), so the wrapper
    refuses at construction — in free space too, the overlap is what is
    pathological, not the ground."""
    monkeypatch.setenv("NEC5_EXE", sys.executable)

    class _CoincidentRises(AntennaBuilder):
        default_params = {"freq": 7.0}

        def build_wires(self):
            return [
                Wire((0, 0, 10.0), (0, 0, 0.0), n_seg=14, ex=1 + 0j),
                Wire((0, 0, -0.15), (0, 0, 0.0), n_seg=2),
                Wire((0, 0, -0.15), (0, 0, 0.0), n_seg=2),
            ]

    with pytest.raises(NotImplementedError, match="coincident"):
        NEC5Engine(_CoincidentRises())


@needs_nec5
def test_buried_anchor_print_reproduces_through_the_wrapper():
    """The banked four-radial anchor, end to end through the wrapper's
    binary plumbing and printout parser: run_deck on the verbatim anchor
    cards must hand back the impedance the capture banked. This gates the
    wrapper on a BURIED printout (parser + plumbing), not physics — the
    print tolerance is the golden's own 4-decimal rounding."""
    e = NEC5Engine(_dipole_builder())
    rows = e.run_deck(_ANCHOR_FOUR_RADIAL_DECK)
    assert len(rows) == 1 and len(rows[0]) == 1
    z = rows[0][0][2]
    assert abs(z - _ANCHOR_FOUR_RADIAL) < 1e-3


@needs_nec5
def test_buried_radial_catalog_detached_variant_solves():
    """The catalog's stake-convention variant is now REFUSED (#1025).

    It used to solve, and the number it gave was the problem: its monopole
    stands its lower end IN the plane with no rise while four radials sit
    15 cm down, which is the combination with no defensible spelling."""
    from antennaknobs.designs.verticals.buried_radial_vertical import (
        Builder as BuriedRadialVertical,
    )

    b = BuriedRadialVertical(
        params=resolve_variant_params(BuriedRadialVertical, "detached")
    )
    with pytest.raises(NotImplementedError, match="ends ON the ground plane"):
        NEC5Engine(b, ground=("finite", 13.0, 0.005))


@needs_nec5
def test_the_connected_spelling_is_the_way_out_and_tracks_momwire(record_property):
    """The refusal above says to continue the conductor below the plane; this
    is that deck, which is why the refusal redirects rather than dead-ends.

    The catalog's CONNECTED buried-radial screen has a rise from the buried
    hub up to the node, so the conductor crosses the interface instead of
    stopping on it — and it then agrees with momwire to a few percent. Under
    the flag this wrapper used to write, the same deck read 49.620+20.877j,
    34.6 % from momwire in R."""
    from antennaknobs.designs.verticals.buried_radial_vertical import (
        Builder as BuriedRadialVertical,
    )

    b = BuriedRadialVertical()
    ground = ("finite", 13.0, 0.005)
    assert "GE -1 0" in NEC5Engine(b, ground=ground).deck([b.freq]).splitlines()
    (z5,) = NEC5Engine(b, ground=ground).impedance()
    (zm,) = MomwireEngine(b, ground=ground).impedance()
    record_property("nec5", f"{z5:.4f}")
    record_property("momwire", f"{zm:.4f}")
    assert abs(z5.real - zm.real) / abs(zm.real) < 0.05, (z5, zm)
    assert abs(z5.imag - zm.imag) / abs(zm.imag) < 0.15, (z5, zm)


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
    """At 0.048 wavelengths over Sommerfeld ground, NEC-5 at NS=20 sits
    ~7 ohm from the NEC-2 lineage in X (momwire 63.16-21.64j, nec2c
    63.20-21.97j, NEC-5 62.14-28.61j, captured 2026-08-10). Originally
    recorded as "a genuine formulation difference in the close-ground
    interaction" — RESOLVED by #872 phase 3a (2026-08-12): the gap is the
    knot-source mesh march of phase 1, and the (40, 80) Richardson pair
    dissolves it to ~0.1 ohm (nec5_extrap 62.81-21.62j vs nec2c
    62.89-21.56j, bs2 62.86-21.52j — bench_nec5_ground.py). This test now
    pins BOTH halves: the raw NS=20 march (stable, reproducible — the
    trap a single-mesh comparison falls into) and its extrapolated
    resolution (close ground does NOT break the recipe)."""

    class LowDipole(AntennaBuilder):
        default_params = {"freq": 28.5}

        def __init__(self, n=20, params=None):
            super().__init__(params)
            self._n = n

        def build_wires(self):
            return [Wire((0, -2.5, 0.5), (0, 2.5, 0.5), n_seg=self._n, ex=1 + 0j)]

    g = ("finite", 13.0, 0.005)
    z5 = NEC5Engine(LowDipole(), ground=g).impedance()[0]
    zm = MomwireEngine(LowDipole(), ground=g).impedance()[0]
    assert abs(z5.real - zm.real) < 3.0
    assert 4.0 < (zm.imag - z5.imag) < 10.0  # the raw NS=20 knot-source march
    z40 = NEC5Engine(LowDipole(40), ground=g).impedance()[0]
    z80 = NEC5Engine(LowDipole(80), ground=g).impedance()[0]
    z_inf = 2 * z80 - z40  # phase-1 recipe, order ~1
    assert abs(z_inf.imag - zm.imag) < 1.5  # the march extrapolates away


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


# ------------------------------------------------------------ network ports


class _PortDipole(AntennaBuilder):
    """Dipole fed through a named 2-segment bridge wire and a
    build_network() spec — stage 4's PortOnWire-at-knot mapping."""

    default_params = {"freq": 28.5}

    def build_wires(self):
        from antennaknobs.network import Wire

        return [
            Wire((0, -2.5, 7), (0, -0.05, 7), n_seg=10),
            Wire((0, -0.05, 7), (0, 0.05, 7), n_seg=2, name="feed"),
            Wire((0, 0.05, 7), (0, 2.5, 7), n_seg=10),
        ]

    def build_network(self):
        from antennaknobs.network import Driven, Network, PortOnWire

        return Network(
            ports={"feed": PortOnWire(name="feed")},
            sources=[Driven(port="feed")],
        )


def test_network_port_deck(monkeypatch):
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    lines = NEC5Engine(_PortDipole()).deck([28.5]).splitlines()
    ex = [ln for ln in lines if ln.startswith("EX")]
    assert len(ex) == 1
    # Voltage source (EX 0) at the feed wire's center knot: tag 2, end 2 of
    # relative segment 1.
    assert ex[0].split()[1:5] == ["0", "2", "1", "2"]


def test_network_current_source_deck(monkeypatch):
    from antennaknobs.network import DrivenCurrent, Network, PortOnWire

    monkeypatch.setenv("NEC5_EXE", sys.executable)

    class B(_PortDipole):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire(name="feed")},
                sources=[DrivenCurrent(port="feed", current=2j)],
            )

    lines = NEC5Engine(B()).deck([28.5]).splitlines()
    ex = [ln for ln in lines if ln.startswith("EX")][0].split()
    # NEC-5's native current source — EX 4, no NEC-2 counterpart.
    assert ex[1] == "4"
    assert float(ex[5]) == 0.0 and float(ex[6]) == 2.0


def test_network_refusals(monkeypatch):
    from antennaknobs.network import (
        Driven,
        Load,
        Network,
        PortOnWire,
        PortVirtual,
    )

    monkeypatch.setenv("NEC5_EXE", sys.executable)

    class Branchy(_PortDipole):
        # A TL branch has no NEC-5 native card on this path (stage 5 serves
        # Load only) — the refusal names the branch type.
        def build_network(self):
            from antennaknobs.network import TL, PortVirtual

            return Network(
                ports={
                    "feed": PortOnWire(name="feed"),
                    "v": PortVirtual(name="v"),
                },
                branches=[TL(a="feed", b="v", z0=50.0, length=1.0)],
                sources=[Driven(port="feed")],
            )

    with pytest.raises(NotImplementedError, match="TL"):
        NEC5Engine(Branchy())

    class QLoad(_PortDipole):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire(name="feed")},
                branches=[Load(port="feed", l=2e-6, ql=200.0)],
                sources=[Driven(port="feed")],
            )

    with pytest.raises(NotImplementedError, match="ql/qc"):
        NEC5Engine(QLoad())

    class Virtual(_PortDipole):
        def build_network(self):
            return Network(
                ports={"v": PortVirtual(name="v")}, sources=[Driven(port="v")]
            )

    with pytest.raises(NotImplementedError, match="virtual"):
        NEC5Engine(Virtual())

    class Distributed(_PortDipole):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire(name="feed", distributed=True)},
                sources=[Driven(port="feed")],
            )

    with pytest.raises(NotImplementedError, match="distributed"):
        NEC5Engine(Distributed())


@needs_nec5
def test_live_network_port_impedance():
    b = _PortDipole()
    z5 = NEC5Engine(b).impedance()[0]
    zm = MomwireEngine(b).impedance()[0]
    assert abs(z5 - zm) < 10.0


@needs_nec5
def test_live_phased_current_pair():
    from antennaknobs.network import DrivenCurrent, Network, PortOnWire, Wire

    class PhasedPair(AntennaBuilder):
        default_params = {"freq": 28.5}

        def build_wires(self):
            w = []
            for k, x in enumerate((0.0, 2.63)):
                w += [
                    Wire((x, -2.5, 7), (x, -0.05, 7), n_seg=10),
                    Wire((x, -0.05, 7), (x, 0.05, 7), n_seg=2, name=f"f{k}"),
                    Wire((x, 0.05, 7), (x, 2.5, 7), n_seg=10),
                ]
            return w

        def build_network(self):
            return Network(
                ports={
                    "f0": PortOnWire(name="f0"),
                    "f1": PortOnWire(name="f1"),
                },
                sources=[
                    DrivenCurrent(port="f0", current=1),
                    DrivenCurrent(port="f1", current=1j),
                ],
            )

    p = PhasedPair()
    z5s = NEC5Engine(p).impedance()
    zms = MomwireEngine(p).impedance()
    assert len(z5s) == 2
    for a, m in zip(z5s, zms, strict=True):
        assert abs(a - m) < 10.0


# ------------------------------------------------------- loads and material


class _LoadedDipole(_PortDipole):
    """_PortDipole plus a series 2uH coil load on the feed port wire."""

    def build_network(self):
        from antennaknobs.network import Driven, Load, Network, PortOnWire

        return Network(
            ports={"feed": PortOnWire(name="feed")},
            branches=[Load(port="feed", l=2e-6)],
            sources=[Driven(port="feed")],
        )


def test_load_deck_lines(monkeypatch):
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    lines = NEC5Engine(_LoadedDipole()).deck([28.5]).splitlines()
    ld = [ln for ln in lines if ln.startswith("LD")]
    assert len(ld) == 1
    toks = ld[0].split()
    # Series RLC (LD 0) at the feed wire's center knot: tag 2, segment 1,
    # end 2 — the same knot the source occupies (series-with-source
    # semantics).
    assert toks[1:5] == ["0", "2", "1", "2"]
    assert float(toks[6]) == pytest.approx(2e-6)


def test_fixed_z_load_deck_line(monkeypatch):
    from antennaknobs.network import Driven, Load, Network, PortOnWire

    monkeypatch.setenv("NEC5_EXE", sys.executable)

    class B(_PortDipole):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire(name="feed")},
                branches=[Load(port="feed", z=50 - 25j)],
                sources=[Driven(port="feed")],
            )

    ld = [
        ln for ln in NEC5Engine(B()).deck([28.5]).splitlines() if ln.startswith("LD")
    ][0].split()
    assert ld[1] == "4"
    assert float(ld[5]) == 50.0 and float(ld[6]) == -25.0


def test_material_deck_lines(monkeypatch):
    from momwire import insulation_inductance

    from antennaknobs.network import WireSpec

    monkeypatch.setenv("NEC5_EXE", sys.executable)

    class Lossy(_Dipole):
        def build_wire_material(self):
            return WireSpec(
                radius=0.0005,
                conductivity=5.8e7,
                insulation_radius=0.0009,
                insulation_eps_r=3.5,
            )

    lines = NEC5Engine(Lossy()).deck([28.5]).splitlines()
    ld5 = [ln for ln in lines if ln.startswith("LD 5")]
    ld2 = [ln for ln in lines if ln.startswith("LD 2")]
    assert len(ld5) == 1 and len(ld2) == 1
    assert float(ld5[0].split()[5]) == pytest.approx(5.8e7)
    # NEC-5 has no native insulated-wire card (no IS in the command
    # roster) — the jacket rides the same King L' LD 2 emulation momwire
    # and export_nec use.
    expected = insulation_inductance(0.0005, 0.0009, 3.5)
    assert float(ld2[0].split()[6]) == pytest.approx(expected, rel=1e-5)


def test_parse_power_budget_fixture():
    text = (FIXTURES / "invvee_dipole_single.out").read_text()
    pb = NEC5Engine._parse_power_budget(text)
    assert pb["efficiency_pct"] == pytest.approx(100.0)
    assert pb["input_w"] == pytest.approx(pb["radiated_w"])
    assert pb["wire_loss_w"] == 0.0


@needs_nec5
def test_live_loaded_dipole_matches_momwire():
    b = _LoadedDipole()
    z5 = NEC5Engine(b).impedance()[0]
    zm = MomwireEngine(b).impedance()[0]
    # Loaded impedances run large; the bar is relative.
    assert abs(z5 - zm) / abs(zm) < 0.05


@needs_nec5
def test_live_power_budget_lossy_wire():
    from antennaknobs.network import WireSpec

    class Lossy(_ElevatedDipole):
        def build_wire_material(self):
            return WireSpec(radius=0.0005, conductivity=5.8e7)

    pb = NEC5Engine(Lossy()).power_budget()
    assert 90.0 < pb["efficiency_pct"] < 100.0
    assert pb["wire_loss_w"] > 0.0
    assert pb["input_w"] == pytest.approx(
        pb["radiated_w"] + pb["wire_loss_w"], rel=1e-3
    )


@needs_nec5
def test_live_average_gain_reads_ground_absorption():
    # Lossless dipole over lossy Sommerfeld ground: the hemisphere average
    # power gain must fall below the lossless-over-ground value of 2.0 —
    # that shortfall IS the ground absorption (the plain power budget
    # cannot see it: radiated == input on an XQ run, pinned by fixture).
    e = NEC5Engine(_ElevatedDipole(), ground=("finite", 13.0, 0.005))
    avg, omega = e.average_power_gain()
    assert 0.2 < avg < 2.0
    assert 0.9 * np.pi < omega < 2.1 * np.pi


# ------------------------------------------------- capture cache (#872 ph 0)


def test_capture_cache_hit_skips_binary(monkeypatch, tmp_path):
    """A printout already captured for this exact deck is served from disk:
    NEC5_EXE points at python (which could never produce a printout), so a
    successful impedance() proves the binary was not invoked."""
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    eng = NEC5Engine(_invvee_builder(), capture_dir=tmp_path)
    deck = eng.deck([eng.builder.freq])
    h = NEC5Engine._deck_hash(deck)
    (tmp_path / f"{h}.out").write_text(
        (FIXTURES / "invvee_dipole_single.out").read_text()
    )
    (z,) = eng.impedance()
    assert z == pytest.approx(70.746 - 8.5699j, rel=1e-3)
    assert eng.run_log == [{"hash": h, "cached": True, "seconds": 0.0}]


def test_capture_writes_deck_and_printout(monkeypatch, tmp_path):
    """A fresh run captures <hash>.nec + <hash>.out and logs its solve time;
    a second engine over the same capture dir is then served from cache.
    The 'binary' is a stub that copies the pinned fixture printout."""
    fixture_out = FIXTURES / "invvee_dipole_single.out"
    stub = tmp_path / "nec5-stub.sh"
    stub.write_text(
        f'#!/bin/sh\nread inp\nread outp\ncp "{fixture_out.resolve()}" "$outp"\n'
    )
    stub.chmod(0o755)
    captures = tmp_path / "captures"

    eng = NEC5Engine(_invvee_builder(), nec5_exe=str(stub), capture_dir=captures)
    (z,) = eng.impedance()
    assert z == pytest.approx(70.746 - 8.5699j, rel=1e-3)
    h = NEC5Engine._deck_hash(eng.deck([eng.builder.freq]))
    assert (captures / f"{h}.nec").read_text() == eng.deck([eng.builder.freq])
    assert (captures / f"{h}.out").read_text() == fixture_out.read_text()
    assert len(eng.run_log) == 1
    (entry,) = eng.run_log
    assert entry["hash"] == h and entry["cached"] is False
    assert entry["seconds"] > 0.0

    # Re-analysis path: a second engine never re-solves.
    eng2 = NEC5Engine(_invvee_builder(), nec5_exe=str(stub), capture_dir=captures)
    eng2.impedance()
    assert eng2.run_log[0]["cached"] is True


def test_no_capture_dir_means_no_cache(monkeypatch, tmp_path):
    """Without capture_dir the engine behaves exactly as before: every run
    invokes the binary and nothing is written anywhere."""
    fixture_out = FIXTURES / "invvee_dipole_single.out"
    stub = tmp_path / "nec5-stub.sh"
    stub.write_text(
        f'#!/bin/sh\nread inp\nread outp\ncp "{fixture_out.resolve()}" "$outp"\n'
    )
    stub.chmod(0o755)
    eng = NEC5Engine(_invvee_builder(), nec5_exe=str(stub))
    eng.impedance()
    eng.impedance()
    assert [e["cached"] for e in eng.run_log] == [False, False]
    assert list(tmp_path.iterdir()) == [stub]


# ----------------------------------------- EX source semantics (#872 phase 1)


def _stub_engine(tmp_path, capture_dir=None):
    """NEC5Engine with a stub 'binary' that copies the pinned invvee
    printout — enough to exercise run_deck's plumbing without a license."""
    fixture_out = FIXTURES / "invvee_dipole_single.out"
    stub = tmp_path / "nec5-stub.sh"
    stub.write_text(
        f'#!/bin/sh\nread inp\nread outp\ncp "{fixture_out.resolve()}" "$outp"\n'
    )
    stub.chmod(0o755)
    return NEC5Engine(_invvee_builder(), nec5_exe=str(stub), capture_dir=capture_dir)


def test_run_deck_returns_parsed_sections(tmp_path):
    eng = _stub_engine(tmp_path, capture_dir=tmp_path / "cap")
    per_freq = eng.run_deck("CM raw\nCE\nGW 1 2 0 0 0 0 0 1 .001\nEN\n")
    assert len(per_freq) == 1
    (tag, seg, z) = per_freq[0][0]
    assert (tag, seg) == (3, 41)  # the fixture's feed row, verbatim
    assert z == pytest.approx(70.746 - 8.5699j, rel=1e-3)
    # Raw decks ride the capture cache like any other run.
    eng.run_deck("CM raw\nCE\nGW 1 2 0 0 0 0 0 1 .001\nEN\n")
    assert [e["cached"] for e in eng.run_log] == [False, True]


@needs_nec5
def test_live_ex_sources_live_at_knots():
    """The #872 phase-1 dialect pin, measured: NEC-5 voltage sources sit at
    segment ENDS only. (a) The three spellings of one knot — end 2 of seg
    k, end 1 of seg k+1, negative-I3 — are identical; (b) a vanilla NEC-2
    ``EX 0 tag seg 0`` card is reinterpreted as END 2 of seg (NOT the
    segment center nec2c feeds), identical to the explicit end-2 form and
    far from the knot on the other side. Guards the backward-compatibility
    trap: a NEC-2 deck runs through NEC-5 unwarned with its feed shifted
    half a segment."""
    deck = (
        "CM ex semantics\nCE\nGW 1 8 0. 0. 10. 0. 0. 15.2 1.000000E-03\nGE 0 0\n"
        "{ex}\nFR 0 1 0 0 27.0 0.\nXQ 0\nEN\n"
    )
    eng = NEC5Engine(_dipole_builder())

    def z(ex):
        return eng.run_deck(deck.format(ex=ex))[0][0][2]

    z_k2_e2 = z("EX 0 1 2 2 1. 0.")  # knot at 0.25L
    z_k3_e1 = z("EX 0 1 3 1 1. 0.")  # same knot, other spelling
    z_k3_neg = z("EX 0 1 -3 0 1. 0.")  # same knot, negative-I3 spelling
    z_nec2_style = z("EX 0 1 3 0 1. 0.")  # NEC-2 card: nec2c feeds seg-3 CENTER
    z_k3_e2 = z("EX 0 1 3 2 1. 0.")  # knot at 0.375L
    assert z_k3_e1 == pytest.approx(z_k2_e2, rel=1e-6)
    assert z_k3_neg == pytest.approx(z_k2_e2, rel=1e-6)
    assert z_nec2_style == pytest.approx(z_k3_e2, rel=1e-6)
    # The two knots bracket a steep dZ/ds region — they must differ a lot,
    # or the identity assertions above would be vacuous.
    assert abs(z_k3_e2 - z_k2_e2) > 0.1 * abs(z_k2_e2)


@needs_nec5
def test_live_ex0_ex4_identical_impedance():
    """#890 discriminator pin: the same knot driven as a voltage source
    (EX 0) and as NEC-5's native current source (EX 4) reads the identical
    impedance at fixed mesh — and the EX 4 row carries no readout
    convention at all (its AIP current is the driven 1 A exactly). The
    O(1/N) mesh march being common to both is what pronounces it NEC-5's
    own knot discretization rather than a harness-side gap or readout
    artifact (docs/status/2026-08-12-nec5-pair-extrapolation-why.md)."""
    deck = (
        "CM ex0 vs ex4\nCE\nGW 1 8 0. 0. 10. 0. 0. 15.2 1.000000E-03\nGE 0 0\n"
        "{ex}\nFR 0 1 0 0 27.0 0.\nXQ 0\nEN\n"
    )
    eng = NEC5Engine(_dipole_builder())

    def z(ex):
        return eng.run_deck(deck.format(ex=ex))[0][0][2]

    z_volt = z("EX 0 1 4 2 1. 0.")
    z_amp = z("EX 4 1 4 2 1. 0.")
    assert z_amp == pytest.approx(z_volt, rel=1e-6)


# --------------------------------- corpus feed-position exactness (#872 ph 1)


def _deck_feed_positions(deck_text: str):
    """The NEC-5 source's z position for a corpus-style deck translated
    through the census pipeline (parse_nec -> wire_tuples ->
    NEC5Engine.deck). Vertical single-axis geometry so z alone locates
    the feed."""
    from types import MappingProxyType

    from antennaknobs.nec_import import parse_nec

    deck = parse_nec(deck_text, name="t.nec", network=True)
    net = deck.network()
    tups = deck.wire_tuples(specs=True)

    class _B(AntennaBuilder):
        default_params = MappingProxyType({"freq": 27.0})

        def build_wires(self):
            return tups

        def build_network(self):
            return net

    eng = NEC5Engine(_B())
    lines = eng.deck([27.0]).splitlines()
    gw = {}
    for ln in lines:
        t = ln.split()
        if t[0] == "GW":
            gw[int(t[1])] = (int(t[2]), float(t[5]), float(t[8]))  # n_seg, z1, z2
    ex = next(t for t in map(str.split, lines) if t[0] == "EX")
    tag, seg, end = int(ex[2]), int(ex[3]), int(ex[4])
    assert end == 2
    n_seg, z1, z2 = gw[tag]
    return z1 + (z2 - z1) * seg / n_seg


def test_corpus_offcenter_feed_lands_on_exact_gap_position(monkeypatch):
    """#872 phase 1: the importer isolates an off-center fed segment on its
    own 1-segment wire, and even-parity coercion makes that segment's
    center a knot — so the NEC-5 source sits at EXACTLY the NEC-2
    delta-gap position. Census comparisons carry no feed-position offset;
    the residual NEC-5 systematic is the knot-source feed-MODEL march
    alone (bench_nec5_feed_model.py measures it)."""
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    z = _deck_feed_positions(
        "CM x\nCE\nGW 1 9 0 0 10. 0 0 15.2 .001\nGE 0\n"
        "EX 0 1 3 0 1. 0.\nFR 0 1 0 0 27. 0\nXQ\nEN\n"
    )
    # abs tolerance = the deck text's %.6E print granularity (~1e-5 m
    # here), not solver precision: the geometry is exact, the printed
    # coordinate is rounded.
    assert z == pytest.approx(10 + (3 - 0.5) / 9 * 5.2, abs=1e-4)


def test_corpus_middle_feed_of_odd_wire_lands_on_exact_gap_position(monkeypatch):
    """The stays-whole case: a feed at the middle segment of an odd-count
    wire keeps the wire intact; parity coercion (9 -> 10) puts a knot at
    the wire's physical middle = the original segment's center."""
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    z = _deck_feed_positions(
        "CM x\nCE\nGW 1 9 0 0 10. 0 0 15.2 .001\nGE 0\n"
        "EX 0 1 5 0 1. 0.\nFR 0 1 0 0 27. 0\nXQ\nEN\n"
    )
    assert z == pytest.approx(12.6, abs=1e-4)


# --------------------------------------------------------------------------
# antennaknobs#1025 — the fully-buried FED class
# --------------------------------------------------------------------------


def test_buried_fed_below_captures_pin_the_ground_flag():
    """The banked printouts for `specialty.buried_dipole`, whose wire AND
    excitation are both below the interface.

    Two captures of the SAME deck differing only in GE's ground flag. The
    witness is the point: flag 1 does not merely shift the answer, it
    collapses it to milliohms, which is what antennaknobs#1025 reported. The
    parse is identical across both — the wrapper was reading the binary's own
    columns faithfully all along, so this was never a parser bug.
    """
    served = NEC5Engine._parse_input_parameters(
        (FIXTURES / "buried_dipole_fed_below.out").read_text()
    )
    assert served == [[(2, 26, 146.39 + 44.382j)]]

    witness = NEC5Engine._parse_input_parameters(
        (FIXTURES / "buried_dipole_fed_below_ge1.out").read_text()
    )
    assert witness == [[(2, 26, 0.00036644 + 0.84588j)]]

    # A milliohm resistance on a 5.9 m buried dipole is a broken-class print,
    # not a physics disagreement — three orders under the served answer.
    assert witness[0][0][2].real < served[0][0][2].real / 1000

    # The decks differ in exactly one card, and it is the GE one.
    a = (FIXTURES / "buried_dipole_fed_below.nec").read_text().splitlines()
    b = (FIXTURES / "buried_dipole_fed_below_ge1.nec").read_text().splitlines()
    differing = [(x, y) for x, y in zip(a, b, strict=True) if x != y]
    assert differing == [("GE -1 0", "GE 1 -1")]


@needs_nec5
def test_buried_fed_below_tracks_momwire(record_property):
    """The cross-engine check the class never had: a fully-buried fed dipole,
    swept in depth so the comparison is a curve rather than one point.

    Depth is the discriminator. Under the pre-#1025 flag NEC-5 printed the
    same 0.85j at every depth — an impedance that does not know how deep the
    antenna is buried is not an answer about a buried antenna."""
    from antennaknobs.designs.specialty.buried_dipole import Builder as BuriedDipole

    ground = ("finite", 13.0, 0.005)
    seen = []
    for depth in (0.15, 1.0, 2.0):
        b = BuriedDipole()
        b.depth = depth
        z5 = complex(NEC5Engine(b, ground=ground).impedance()[0])
        zm = complex(MomwireEngine(b, ground=ground).impedance()[0])
        seen.append((depth, z5, zm))
        record_property(f"nec5_{depth}", f"{z5:.4f}")
        record_property(f"momwire_{depth}", f"{zm:.4f}")
        assert abs(z5.real - zm.real) / abs(zm.real) < 0.02, (depth, z5, zm)
        assert abs(z5.imag - zm.imag) / abs(zm.imag) < 0.06, (depth, z5, zm)

    # Both engines must move with depth, and in the same direction: the
    # shallow deck is the most resistive on both.
    r5 = [z5.real for _, z5, _ in seen]
    rm = [zm.real for _, _, zm in seen]
    assert r5[0] > r5[1] > r5[2], r5
    assert rm[0] > rm[1] > rm[2], rm
    assert (r5[0] - r5[2]) > 5.0, r5


def test_contact_class_captures_pin_the_ground_flag():
    """The contact class's banked pair (antennaknobs#1025 follow-up).

    Same deck, same mesh, differing in one card. The witness is the point:
    the flag this wrapper used to write does not merely shift the answer, it
    is the whole of what looked like an interface-node convention difference.
    49.620+20.877j sits 34.58 % from momwire in R; 77.805+44.468j sits 2.58 %.

    Kept as a capture rather than a live solve so it gates without the
    binary, and so a revert to the old flag fails here rather than quietly
    re-publishing the old number.
    """
    served = NEC5Engine._parse_input_parameters(
        (FIXTURES / "brv_connected_minus1.out").read_text()
    )
    witness = NEC5Engine._parse_input_parameters(
        (FIXTURES / "brv_connected_ge1_witness.out").read_text()
    )
    assert served == [[(8, 223, 77.805 + 44.468j)]]
    assert witness == [[(8, 223, 49.62 + 20.877j)]]

    a = (FIXTURES / "brv_connected_minus1.nec").read_text().splitlines()
    b = (FIXTURES / "brv_connected_ge1_witness.nec").read_text().splitlines()
    differing = [(x, y) for x, y in zip(a, b, strict=True) if x != y]
    assert differing == [("GE -1 0", "GE 1 0")]


@needs_nec5
def test_the_old_flag_prints_negative_resistance_when_fed_below_ground():
    """The other witness for the old flag, and the sharpest one.

    Under the flag the wrapper used to write, moving the source to a
    BELOW-ground segment of the same screen prints NEGATIVE resistance — the
    same broken class as the milliohms this issue opened on, and impossible
    for a passive antenna. Under the flag keyed on burial the answer is
    instead stable across source placement, moving by ~0.04 ohm when the feed
    moves one segment.

    Hand cards, because the wrapper cannot be asked to write the old flag any
    more, which is the point.
    """
    import re
    import subprocess
    import tempfile

    exe = find_nec5()
    gw = "GW 1 70 0. 0. -1.500000E-01 0. 0. 1.035000E+01 5.000000E-04\n" + "".join(
        f"GW {i + 2} 54 0. 0. -1.500000E-01 "
        f"{6.3336 * dx:.6E} {6.3336 * dy:.6E} -1.500000E-01 5.000000E-04\n"
        for i, (dx, dy) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1)))
    )
    gn = "GN 0 0 0 0 1.300000E+01 5.000000E-03 1.000000E+00 0.000000E+00 NOFILE\n"
    fr = "FR 0 1 0 0 7.100000E+00 0.000000E+00\n"

    def z_of(ge, seg):
        deck = f"CM witness\nCE\n{gw}{ge}\n{gn}EX 0 1 {seg} 0 1.0 0.\n{fr}XQ 0\nEN\n"
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "m.nec").write_text(deck)
            subprocess.run(
                [exe],
                input="m.nec\nm.out\n\n",
                text=True,
                capture_output=True,
                cwd=td,
                timeout=600,
            )
            text = (Path(td) / "m.out").read_text(errors="replace")
        m = re.search(
            r"- - - ANTENNA INPUT PARAMETERS - - -(.*?)(?:\n\s*\n\s*\n|$)", text, re.S
        )
        for line in m.group(1).splitlines():
            t = line.split()
            if len(t) >= 12 and re.fullmatch(r"\d+", t[0]):
                return complex(float(t[7]), float(t[8]))
        raise AssertionError("no impedance row")

    # segment 1 is below the interface; segment 2 is the first above it.
    assert z_of("GE 1 0", 1).real < 0.0
    assert z_of("GE -1 0", 1).real > 70.0
    # and under the served flag the answer barely notices the feed moving.
    assert abs(z_of("GE -1 0", 1).real - z_of("GE -1 0", 2).real) < 0.5


# --------------------------------------------------------------------------
# antennaknobs#1190 — card-field witnesses
# --------------------------------------------------------------------------


def test_1190_ex_end_field_is_live_and_pinned():
    """EX's I4 selects the segment END, and #1025 got this wrong.

    That issue measured I4 = 0, 1 and 2 giving one answer and recorded the
    field as physics-irrelevant. Two things were wrong with that. I4 = 0 and
    I4 = 2 are the SAME REQUEST by documentation — 0 defers to the sign of I3,
    which this wrapper always writes positive, and that is end 2 — so two
    spellings of one thing were read as evidence the field did nothing. And
    the measurement was taken on a deck under the pre-#1025 ground card, whose
    answer was degenerate milliohms; a broken answer is insensitive to
    everything.

    On a healthy deck the ends differ by 0.07 ohm in R and 0.31 in X. Nothing
    would notice that but this pair.
    """
    end1 = NEC5Engine._parse_input_parameters(
        (FIXTURES / "witness_ex_end1.out").read_text()
    )
    end2 = NEC5Engine._parse_input_parameters(
        (FIXTURES / "witness_ex_end2.out").read_text()
    )
    assert end1 == [[(2, 26, 146.46 + 44.696j)]]
    assert end2 == [[(2, 26, 146.39 + 44.382j)]]
    assert end1 != end2, "the EX end field stopped mattering — audit it again"

    a = (FIXTURES / "witness_ex_end1.nec").read_text().splitlines()
    b = (FIXTURES / "witness_ex_end2.nec").read_text().splitlines()
    differing = [(x, y) for x, y in zip(a, b, strict=True) if x != y]
    assert differing == [
        ("EX 0 2 1 1 1.000000E+00 0.000000E+00", "EX 0 2 1 2 1.000000E+00 0.000000E+00")
    ]


def test_1190_ld_discrete_end_field_is_live_and_pinned():
    """LD's LDTAGT means two different things by type: the last element of a
    range for DISTRIBUTED loads, the segment END for discrete ones. One slot,
    two meanings, chosen by the leading type digit — the same shape as the GE
    bug. A 50 ohm load on the wrong end of one segment moves R by 2 ohm and
    nothing else."""
    e1 = NEC5Engine._parse_input_parameters(
        (FIXTURES / "witness_ld_discrete_end1.out").read_text()
    )
    e2 = NEC5Engine._parse_input_parameters(
        (FIXTURES / "witness_ld_discrete_end2.out").read_text()
    )
    assert e1 == [[(2, 26, 50.6 - 1586.1j)]]
    assert e2 == [[(2, 26, 52.578 - 1586.1j)]]
    assert abs(e1[0][0][2] - e2[0][0][2]) > 1.0


def test_1190_ld_distributed_inductance_is_per_metre():
    """LDTYP=2 takes henries per METRE. `momwire.insulation_inductance` is
    documented [H/m] and matches — but a per-SEGMENT value in the same slot
    also solves, 20 ohm off in X.

    The reason this pair is banked rather than trusted to review: the error is
    wrong BY THE SEGMENT LENGTH, so it shrinks as the mesh refines. It would
    present as a convergence effect, which is the most expensive way for a
    units bug to hide.
    """
    per_m = NEC5Engine._parse_input_parameters(
        (FIXTURES / "witness_ld_henries_per_m.out").read_text()
    )
    per_seg = NEC5Engine._parse_input_parameters(
        (FIXTURES / "witness_ld_henries_per_seg.out").read_text()
    )
    assert per_m == [[(2, 26, 38.915 - 1563.5j)]]
    assert per_seg == [[(2, 26, 38.771 - 1583.1j)]]
    assert abs(per_m[0][0][2].imag - per_seg[0][0][2].imag) > 10.0

    from momwire import insulation_inductance

    assert "H/m" in insulation_inductance.__doc__, (
        "insulation_inductance stopped documenting its units as H/m — LDTYP=2 "
        "needs henries per metre and this test is what ties the two"
    )
