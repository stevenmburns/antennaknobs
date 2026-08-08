"""momwire against nec2c, fixture by fixture (issue #792, unit 3).

``tests/test_nec_portal.py`` pins the printout's *shape*: same sections, same
columns, same token arity.  This file pins its *numbers*.  Every committed
oracle deck is run through our daemon in-process, both printouts are read by
ONE parser written to ``nec2/Execute``'s token positions, and the parsed values
are compared.

Nothing here needs the oracle binary — the fixtures are committed and the
daemon is a library call.  The whole file is under two seconds.

What "agreement" means
----------------------
nec2c is a pulse-basis point-matched NEC-2 and momwire is a B-spline Galerkin
solver.  They will never agree digit for digit and SimNEC does not need them
to: it reads two numbers per ANTENNA INPUT PARAMETERS row and builds a Y
matrix.  The bar is that a design tuned against one engine behaves the same
against the other, so the default tolerance is **5 % relative** on impedances
and port currents and **±0.5 dB** on pattern gain.

Measured at authoring time (2026-08-08, momwire 0.23.0, nec2c 5b4az.ae6ty.1.17;
the two ``dipole_tl_*`` rows added 2026-08-09 for issue #799) — worst case over
every row of every table in each fixture:

===================================  ======  ======  ======  ======  =====
fixture                               Z err   I err  YY err  I curve  dGain
===================================  ======  ======  ======  ======  =====
catalog_beams_moxon                   1.63%   1.63%       -   0.38%      -
catalog_broadband_t2fd                1.41%   1.40%       -   2.57%      -
catalog_dipoles_invvee                0.63%   0.63%       -   0.18%      -
catalog_dipoles_ocf_dipole            0.99%   0.99%       -   0.25%      -
catalog_dipoles_short_dipole_loaded  45.21%  45.21%       -   2.17%      -   (a)
catalog_loops_delta_loop              1.81%   1.81%       -   0.30%      -
catalog_multiband_trap_dipole         2.66%   2.66%       -   0.68%      -
catalog_specialty_bowtie              1.25%   1.25%       -   0.54%      -
catalog_verticals_vertical            2.79%   2.79%       -   0.18%      -
catalog_wire_w8jk                     1.98%   1.99%       -   0.84%      -
dipole_fr_sweep                       1.29%   1.29%       -   0.96%      -
dipole_free_space                     0.76%   0.76%       -   0.96%      -
dipole_gm_translated_pair             1.10%   1.10%       -   1.13%      -
dipole_gs_scaled                      0.76%   0.76%       -   0.96%      -
dipole_load_ld0                       1.79%   1.79%       -   1.95%      -
dipole_load_ld4                       1.64%   1.64%       -   1.62%      -
dipole_load_ld5_conductivity          0.76%   0.76%       -   0.97%      -
dipole_mp_multiprocessor              0.76%   0.76%       -   0.96%      -   (e)
dipole_mp_single_process              0.76%   0.76%       -   0.96%      -   (e)
dipole_ne_nearfield                   0.76%   0.76%       -   0.96%      -
dipole_nh_nearfield                   0.76%   0.76%       -   0.96%      -
dipole_nt_network                     1.31%   1.31%       -   3.46%      -   (b)
dipole_pec_ground                     2.23%   2.23%       -   4.35%      -
dipole_pt_segment_range               2.47%   2.47%       -   0.52%      -
dipole_pt_toggle                      2.47%   2.47%   2.83%   1.10%      -
dipole_reflection_ground              2.23%   2.23%       -   4.36%      -
dipole_rp_crossed_quadrature          0.76%   0.76%       -   0.96%   0.09
dipole_rp_pattern                     0.76%   0.76%       -   0.96%   0.12
dipole_sommerfeld_ground              2.24%   2.23%       -   4.35%      -
dipole_tl_network                     0.27%   0.26%       -   1.01%      -   (d)
dipole_tl_shunt_crossed               1.14%   1.14%       -   0.89%      -
jar_testdeck                         12.02%  12.02%  12.02%   6.00%      -   (c)
jar_testdeck_daemon_framed           12.02%  12.02%  12.02%   6.00%      -   (c)
resident_two_decks                    0.77%   0.77%       -   0.96%      -
two_source_sensor_lines               2.83%   2.83%       -   1.10%      -
two_source_yy_card                    2.47%   2.47%   2.83%   1.10%      -
===================================  ======  ======  ======  ======  =====

"I curve" is the CURRENTS AND LOCATION table normalised by its own peak ROW,
complex — so it asks whether this is the same current DISTRIBUTION (relative
magnitude and relative phase, segment for segment, in the same tag order) and
leaves the overall complex scale to the port test above.  That split is what
makes (a) legible: the short loaded dipole's distribution agrees to 2.2 %, and
all 45 % of its port disagreement is the one global factor.  Peak-gain
direction agrees exactly (0 steps) on both pattern fixtures.

Three fixtures need more than 5 %, and all three are the same phenomenon —
a small residual between two large, nearly cancelling numbers:

(a) ``catalog_dipoles_short_dipole_loaded``: a 0.25 λ dipole with a 4.65 µH
    coil at the feed.  At 28 MHz that coil is +818 Ω, cancelling almost all of
    the antenna's own capacitive reactance.  ``Re(Z)`` agrees to 1.8 %; the
    reactance differs by 8.4 Ω, which is **1.0 % of the coil**.  The 45 % is
    the residual, not the physics.
(b) ``dipole_nt_network``: the NT branch (j0.02 S) drives most of the current
    that would otherwise flow in the driven segment, so the segment current
    printed in STRUCTURE EXCITATION DATA is a residual and differs by 12 %.
    The number SimNEC actually reads — the ANTENNA INPUT PARAMETERS *source*
    current — agrees to 1.3 %.
(c) ``jar_testdeck``: port 1 is the gap at the centre of a full-wave split
    dipole, a current null with ``|Z| ≈ 3.5 kΩ``.  High-|Z| feeds are the known
    basis-sensitive class (antennaknobs #459); the deck's other two ports agree
    to 0.4 %.

Each of those is asserted at its own tolerance below, WITH the identity that
makes it benign, so a future regression that is not this phenomenon still
fails.

(d) is a *near* miss worth recording rather than an outlier. ``TL`` decks are
    exposed to the same cancellation the three above are: a line at an odd
    quarter wave is an impedance INVERTER, so a small basis difference at the
    far end comes back magnified at the near one, and two branches across one
    pair of gaps make a loop whose port admittance is a residual. The first
    draft of ``dipole_tl_shunt_crossed`` hung its NT back across the same pair
    as the TL and measured 6.6 % — 5× the same deck with the NT chained onto a
    third dipole (1.14 %), for a structure whose printout layout is identical
    either way. The committed decks are the chained ones; nothing here needs a
    widened bar, and if a future TL fixture does, this is the mechanism to
    check first.

(e) is a control rather than a measurement (issue #800). Both ``MP`` fixtures
    are ``dipole_free_space``'s geometry plus one card, and both reproduce its
    row to the digit on BOTH engines — which is the claim the card's whole
    treatment rests on: ``MP`` describes how the oracle fills and factors, not
    what it computes, so there is nothing in it for momwire to honour. If these
    rows ever drift away from ``dipole_free_space``'s, the card has stopped
    being advisory and this engine is wrong to ignore it.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from antennaknobs.nec_portal import main, run_deck

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "nec_portal"
MANIFEST = json.loads((FIXTURE_DIR / "manifest.json").read_text())
NAMES = tuple(entry["name"] for entry in MANIFEST["decks"])

# Default cross-basis bars.
Z_TOL = 0.05
GAIN_TOL_DB = 0.5
CURVE_TOL = 0.08  # CURRENTS AND LOCATION, normalised by each table's peak row

# Per-fixture widenings, each justified in the module docstring and pinned by
# an extra identity in the test that widens it.
Z_TOL_OVERRIDE = {
    "catalog_dipoles_short_dipole_loaded": 0.50,  # (a) coil-cancelled reactance
    "jar_testdeck": 0.15,  # (c) near-open centre feed
    "jar_testdeck_daemon_framed": 0.15,  # (c)
}
# STRUCTURE EXCITATION DATA is a different table with a different bar: it
# reports the SEGMENT current at a network node, which an NT branch can make a
# residual. Execute never reads it (its state machine arms on the ANTENNA INPUT
# PARAMETERS banner alone), so it is checked for sanity, not for agreement.
NETWORK_TOL = 0.15


# --------------------------------------------------------------------------
# one parser, both printouts — written to nec2/Execute's token positions
# --------------------------------------------------------------------------


@dataclass
class Printout:
    """The numbers ``nec2/Execute.processResponse`` extracts from a run."""

    # One list per ANTENNA INPUT PARAMETERS table; each row is (current, Z).
    # Execute keeps only the current (fields 4 and 5, ``samplesOffset``); Z is
    # carried for the differential.
    ports: list[list[tuple[complex, complex]]] = field(default_factory=list)
    # STRUCTURE EXCITATION DATA AT NETWORK CONNECTION POINTS — same row shape,
    # never consumed by Execute.
    network: list[tuple[complex, complex]] = field(default_factory=list)
    # CURRENTS AND LOCATION: (tag, current) per row, ordered by tag.
    currents: list[list[tuple[int, complex]]] = field(default_factory=list)
    # ``-YY`` report rows, one complex per report point.
    yy: list[list[complex]] = field(default_factory=list)
    # RADIATION PATTERNS: (theta, phi, vertc_db, horiz_db, total_db,
    # e_theta, e_phi) per row.
    pattern: list[list[tuple]] = field(default_factory=list)


def _polar(magnitude: str, phase: str) -> complex:
    import cmath

    return cmath.rect(float(magnitude), float(phase) * 3.141592653589793 / 180.0)


def read_printout(text: str) -> Printout:
    """Walk a NEC-2 printout the way ``Execute.processResponse`` does.

    The states that matter here, and what arms each:

    * ``--------- ANTENNA INPUT PARAMETERS ---------`` then ``No: No:``
      -> rows of exactly 11 tokens, current at 4/5.  A row of any other
      arity ends the table.
    * ``-------- CURRENTS AND LOCATION --------`` then ``No: No:``
      -> rows of exactly 10 tokens, tag at 1 and current at 6/7 (REAL and
      IMAGINARY — *not* MAGN/PHASE).
    * ``---------- RADIATION PATTERNS -----------`` then ``DEGREES DEGREES``
      -> ``ptr = 8`` for a 12-token row and ``7`` for an 11-token one, which
      is the SENSE column being present or blank.  Both point at the same
      E(THETA)/E(PHI) magnitude/phase pairs.
    * a line whose first token is ``-YY`` is read wherever it appears.

    The one deliberate departure: STRUCTURE EXCITATION DATA AT NETWORK
    CONNECTION POINTS repeats the ``No: No:`` header with the same 11-token
    rows, and Execute walks straight past it because it never armed.  This
    reader keeps it, separately, so the differential can see it at all.
    """
    out = Printout()
    state: str | None = None
    pending: str | None = None
    for line in text.splitlines():
        parts = line.split()
        if parts[:1] == ["-YY"]:
            values = [float(v) for v in parts[1:]]
            out.yy.append(
                [complex(values[i], values[i + 1]) for i in range(0, len(values), 2)]
            )
            continue
        if parts[:4] == ["---------", "ANTENNA", "INPUT", "PARAMETERS"]:
            pending, state = "ports", None
            continue
        if "STRUCTURE EXCITATION DATA" in line:
            pending, state = "network", None
            continue
        if parts[1:4] == ["CURRENTS", "AND", "LOCATION"]:
            pending, state = "currents", None
            continue
        if parts[1:3] == ["RADIATION", "PATTERNS"]:
            pending, state = "pattern", None
            continue
        if pending in ("ports", "network", "currents") and parts[:2] == ["No:", "No:"]:
            state, pending = pending, None
            if state == "ports":
                out.ports.append([])
            elif state == "currents":
                out.currents.append([])
            continue
        if pending == "pattern" and parts[:2] == ["DEGREES", "DEGREES"]:
            state, pending = "pattern", None
            out.pattern.append([])
            continue
        if state == "ports":
            if len(parts) != 11:
                state = None
                continue
            out.ports[-1].append(
                (
                    complex(float(parts[4]), float(parts[5])),
                    complex(float(parts[6]), float(parts[7])),
                )
            )
        elif state == "network":
            if len(parts) != 11:
                state = None
                continue
            out.network.append(
                (
                    complex(float(parts[4]), float(parts[5])),
                    complex(float(parts[6]), float(parts[7])),
                )
            )
        elif state == "currents":
            if len(parts) != 10:
                state = None
                continue
            out.currents[-1].append(
                (int(parts[1]), complex(float(parts[6]), float(parts[7])))
            )
        elif state == "pattern":
            if len(parts) not in (11, 12):
                state = None
                continue
            ptr = 8 if len(parts) == 12 else 7
            out.pattern[-1].append(
                (
                    float(parts[0]),
                    float(parts[1]),
                    float(parts[2]),
                    float(parts[3]),
                    float(parts[4]),
                    _polar(parts[ptr], parts[ptr + 1]),
                    _polar(parts[ptr + 2], parts[ptr + 3]),
                )
            )
    return out


def relative(ours: complex, theirs: complex) -> float:
    scale = max(abs(ours), abs(theirs))
    return abs(ours - theirs) / scale if scale else 0.0


def our_printout(name: str) -> str:
    """This engine's printout for a fixture deck.

    A fixture holding more than one ``NX`` is a residency transcript and has to
    go through the daemon loop, not the single-deck helper.
    """
    deck = (FIXTURE_DIR / f"{name}.deck").read_text()
    if deck.count("\nNX") > 1:
        buffer = io.StringIO()
        assert (
            main([], stdin=io.StringIO(deck), stdout=buffer, stderr=io.StringIO()) == 0
        )
        return buffer.getvalue()
    return run_deck(deck.split("\nNX")[0])[0]


def oracle_printout(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.out").read_text()


@pytest.fixture(scope="module")
def pair():
    cache: dict[str, tuple[Printout, Printout]] = {}

    def get(name: str) -> tuple[Printout, Printout]:
        if name not in cache:
            cache[name] = (
                read_printout(our_printout(name)),
                read_printout(oracle_printout(name)),
            )
        return cache[name]

    return get


# --------------------------------------------------------------------------
# the support matrix — pinned, not assumed
# --------------------------------------------------------------------------

# Decks the daemon runs end to end. After unit 3 that is the whole corpus; the
# list is written out rather than computed so that a card silently falling back
# to the error path shows up as a failure here instead of as a quiet nothing.
SUPPORTED = NAMES

# Portal-dialect cards no fixture covers, with the substring the error path
# must name. Written as decks rather than fixtures because the oracle's own
# printout for them is either unpinnable or a bare abort (GN 2 with a
# radial screen prints "RADIAL WIRE G.S. APPROXIMATION MAY NOT BE USED WITH
# SOMMERFELD GROUND OPTION" and exits WITHOUT the NX echo — see grammar doc
# §11, which is exactly the readLine() stall §10.1 worries about).
# ``TL`` left this table in issue #799: two fixtures now pin its NETWORK DATA
# layout, so it runs instead of refusing. ``PT`` and ``MP`` left it in #800,
# for the same reason. ``IS`` stays: nothing here models NEC-4.2 insulation,
# and running the deck as a bare wire would be a wrong answer, not a refusal.
_GEOM = "GW 1 9 0. 0. -2.5 0. 0. 2.5 0.001\nGW 2 9 1. 0. -2.5 1. 0. 2.5 0.001\n"
UNSUPPORTED = {
    "IS": f"CE is\n{_GEOM}GE 0\nEX 0 1 5 0 1.\nIS 0 1 1 9 2.3 0.001\nFR 0 1 0 0 30. 0\nXQ\n",
    "SP": f"CE sp\n{_GEOM}GE 0\nEX 0 1 5 0 1.\nSP 0 0 0. 0. 0. 0. 0. 1.\nFR 0 1 0 0 30. 0\nXQ\n",
    "radial ground screen": (
        "CE gn radials\nGW 1 9 0. 0. 0.1 0. 0. 5.2 0.001\nGE -1\n"
        "GN 2 16 0 0 13. 0.005 5.0\nEX 0 1 1 0 1.\nFR 0 1 0 0 14.1 0\nXQ\n"
    ),
    "RP mode": f"CE rp mode\n{_GEOM}GE 0\nEX 0 1 5 0 1.\nFR 0 1 0 0 30. 0\n"
    "RP 4 3 3 1001 0 0 45 45 1000\nXQ\n",
    "spherical": f"CE ne polar\n{_GEOM}GE 0\nEX 0 1 5 0 1.\nFR 0 1 0 0 30. 0\n"
    "NE 1 3 1 3 1. 0. 0. 1. 0. 45.\nXQ\n",
}

NX_ECHO = re.compile(r"^\s*DATA CARD No:\s+\d+ NX\b", re.MULTILINE)


@pytest.mark.parametrize("name", SUPPORTED)
def test_supported_fixtures_run_clean(name):
    """No fixture may quietly fall back to the error path."""
    text = our_printout(name)
    assert "ERROR-NEC2C" not in text, f"{name} took the error path:\n" + "\n".join(
        ln for ln in text.splitlines() if "ERROR-NEC2C" in ln
    )
    assert "ANTENNA INPUT PARAMETERS" in text


def test_the_support_matrix_covers_the_whole_corpus():
    assert set(SUPPORTED) == set(NAMES)


@pytest.mark.parametrize(("marker", "deck"), sorted(UNSUPPORTED.items()))
def test_unsupported_cards_take_the_documented_error_path(marker, deck):
    """Refused by name, and still followed by the sentinel.

    The oracle's own failure mode for one of these (GN 2 + radials) is to stop
    printing entirely — no NX echo, so ``Execute.processResponse`` blocks in
    ``readLine()`` forever. This engine must not inherit that.
    """
    text = run_deck(deck)[0]
    assert "ERROR-NEC2C: " in text
    assert marker in text, f"the error does not name {marker!r}:\n{text[-400:]}"
    assert NX_ECHO.search(text), "no NX sentinel on the error path"


# --------------------------------------------------------------------------
# values
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_port_impedances_and_currents_agree(name, pair):
    """The two numbers SimNEC keeps, plus the impedance they imply."""
    ours, theirs = pair(name)
    assert [len(t) for t in ours.ports] == [len(t) for t in theirs.ports], (
        f"{name}: different ANTENNA INPUT PARAMETERS table shape"
    )
    assert ours.ports, f"{name}: no impedance table"
    tol = Z_TOL_OVERRIDE.get(name, Z_TOL)
    for table_index, (mine, oracle) in enumerate(
        zip(ours.ports, theirs.ports, strict=True)
    ):
        for row, ((i_a, z_a), (i_b, z_b)) in enumerate(zip(mine, oracle, strict=True)):
            where = f"{name} table {table_index} row {row}"
            assert relative(i_a, i_b) <= tol, f"{where}: current {i_a} vs {i_b}"
            assert relative(z_a, z_b) <= tol, f"{where}: impedance {z_a} vs {z_b}"


def test_the_short_loaded_dipole_only_disagrees_in_the_cancelled_reactance():
    """Justifies the 50 % widening above, so it cannot rot into a free pass.

    ``LD 0 1 11 11 0 4.65e-6 0`` is +818 Ω at 28 MHz and cancels nearly all of
    the short dipole's capacitive reactance. The RESISTANCE — which is the
    radiating physics — must still agree at the normal bar, and the reactance
    gap must stay small against the coil it is a residual of.
    """
    ours, theirs = (
        read_printout(our_printout("catalog_dipoles_short_dipole_loaded")),
        read_printout(oracle_printout("catalog_dipoles_short_dipole_loaded")),
    )
    (_ia, z_a), (_ib, z_b) = ours.ports[0][0], theirs.ports[0][0]
    coil_ohms = 2 * 3.141592653589793 * 28.0e6 * 4.65e-6
    assert abs(z_a.real - z_b.real) <= Z_TOL * abs(z_b.real), (
        f"resistance {z_a.real} vs {z_b.real}"
    )
    assert abs(z_a.imag - z_b.imag) <= 0.03 * coil_ohms, (
        f"reactance gap {z_a.imag - z_b.imag:.1f} ohms against a {coil_ohms:.0f} ohm coil"
    )


def test_the_jar_testdecks_low_z_ports_agree_tightly():
    """Justifies the 15 % widening: only the near-open port is loose.

    ``jar_testdeck`` drives three ports of a full-wave split dipole. Port 1 is
    the centre gap — a current null at ``|Z| ~ 3.5 kOhm``, the basis-sensitive
    high-|Z| class of antennaknobs #459. The other two are ordinary ~100 Ω
    feeds and must agree at the normal bar.
    """
    ours, theirs = (
        read_printout(our_printout("jar_testdeck")),
        read_printout(oracle_printout("jar_testdeck")),
    )
    z_open = theirs.ports[0][0][1]
    assert abs(z_open) > 1000.0, "port 1 is supposed to be the near-open one"
    for table in (1, 2):
        (i_a, z_a) = ours.ports[table][0]
        (i_b, z_b) = theirs.ports[table][0]
        assert relative(z_a, z_b) <= Z_TOL, f"port {table + 1}: {z_a} vs {z_b}"
        assert relative(i_a, i_b) <= Z_TOL


def test_the_nt_networks_source_current_agrees_even_though_the_segment_does_not():
    """Justifies the network-table widening.

    The NT branch carries most of what the driven segment would otherwise
    carry, so the segment current in STRUCTURE EXCITATION DATA is a small
    residual of two larger numbers. The ANTENNA INPUT PARAMETERS row — the
    SOURCE current, segment plus network, and the only one SimNEC reads — is
    not a residual and agrees at the normal bar.
    """
    ours, theirs = (
        read_printout(our_printout("dipole_nt_network")),
        read_printout(oracle_printout("dipole_nt_network")),
    )
    (i_a, z_a) = ours.ports[0][0]
    (i_b, z_b) = theirs.ports[0][0]
    assert relative(i_a, i_b) <= Z_TOL, f"source current {i_a} vs {i_b}"
    assert relative(z_a, z_b) <= Z_TOL
    # ... and the segment current it is built from is genuinely the small one.
    assert abs(ours.network[1][0]) < 0.5 * abs(i_a)


MP_FIXTURES = ("dipole_mp_multiprocessor", "dipole_mp_single_process")


@pytest.mark.parametrize("name", MP_FIXTURES)
def test_mp_moves_no_number_on_either_engine(name, pair):
    """Justifies treating ``MP`` as advisory (issue #800).

    The card tells the oracle how many processors to fill and factor with. If
    that were physics, the fixture would differ from ``dipole_free_space`` —
    same geometry, same drive, same frequency, one extra card. It does not, on
    the oracle's side OR ours, so momwire ignoring ``#Proc``/``blockSize`` is a
    faithful reading and not a shortcut.
    """
    ours, theirs = pair(name)
    base_ours, base_theirs = pair("dipole_free_space")
    for mine, base in ((ours, base_ours), (theirs, base_theirs)):
        assert [len(t) for t in mine.ports] == [len(t) for t in base.ports]
        for table, reference in zip(mine.ports, base.ports, strict=True):
            assert table == reference, f"{name}: MP moved an impedance row"
        assert mine.currents == base.currents, f"{name}: MP moved a segment current"


TL_FIXTURES = ("dipole_tl_network", "dipole_tl_shunt_crossed")


def _network_gap_voltages(text: str) -> list[complex]:
    """The VOLTAGE column of STRUCTURE EXCITATION DATA — fields 2 and 3, which
    ``read_printout`` does not keep because ``Execute`` never reads them."""
    out: list[complex] = []
    armed = False
    for line in text.splitlines():
        if "STRUCTURE EXCITATION DATA" in line:
            armed = True
            continue
        if not armed:
            continue
        parts = line.split()
        if len(parts) != 11 or not parts[0].isdigit():
            if out:
                break
            continue
        out.append(complex(float(parts[2]), float(parts[3])))
    return out


@pytest.mark.parametrize("name", TL_FIXTURES)
def test_tl_far_end_gap_voltages_agree(name):
    """The number a TL card's electrical length actually decides.

    A ``TL`` end that nothing drives floats to whatever balances the node
    through the line, so its gap voltage is the reading that would move if βl,
    the crossed-line sign, or the end shunts were wrong — and it is invisible
    to every other assertion here, because ``Execute`` never reads this table
    and the port test only sees the driven end. Both engines must agree at the
    ordinary bar; a quarter-wave line's inversion would amplify anything that
    did not.
    """
    ours = _network_gap_voltages(our_printout(name))
    theirs = _network_gap_voltages(oracle_printout(name))
    assert len(ours) == len(theirs) >= 2
    for row, (a, b) in enumerate(zip(ours, theirs, strict=True)):
        assert relative(a, b) <= Z_TOL, f"{name} network row {row}: {a} vs {b}"


@pytest.mark.parametrize("name", NAMES)
def test_network_excitation_rows_agree_loosely(name, pair):
    ours, theirs = pair(name)
    assert len(ours.network) == len(theirs.network), f"{name}: network table shape"
    for row, ((i_a, _z_a), (i_b, _z_b)) in enumerate(
        zip(ours.network, theirs.network, strict=True)
    ):
        assert relative(i_a, i_b) <= NETWORK_TOL, f"{name} network row {row}"


@pytest.mark.parametrize("name", NAMES)
def test_yy_rows_agree(name, pair):
    """Ward's ``-YY`` report is the same Y matrix by another route."""
    ours, theirs = pair(name)
    assert len(ours.yy) == len(theirs.yy), f"{name}: different -YY row count"
    tol = Z_TOL_OVERRIDE.get(name, Z_TOL)
    for row, (mine, oracle) in enumerate(zip(ours.yy, theirs.yy, strict=True)):
        for k, (a, b) in enumerate(zip(mine, oracle, strict=True)):
            assert relative(a, b) <= tol, f"{name} -YY row {row} point {k}: {a} vs {b}"


@pytest.mark.parametrize("name", NAMES)
def test_current_distributions_track(name, pair):
    """CURRENTS AND LOCATION, each table normalised by its own peak ROW.

    A per-row relative test is meaningless here: the current goes to zero at
    every wire end, so the last row divides by nothing. Dividing each table by
    its largest entry — as a COMPLEX number, so the overall phase goes with it
    — asks the question that matters: is this the same current distribution,
    segment for segment, in the same tag order, with the same relative phases
    and signs. A flipped wire, a mis-ordered tag, or a segment reading another
    wire's current (which is what a crossed pair produced before the
    element match learned to check direction as well as position) shows up
    immediately.

    The overall complex scale is deliberately NOT tested here — it is exactly
    what ``test_port_impedances_and_currents_agree`` covers, and separating the
    two is what makes the short-loaded-dipole outlier legible instead of
    alarming.
    """
    ours, theirs = pair(name)
    assert [len(t) for t in ours.currents] == [len(t) for t in theirs.currents]
    for table, (mine, oracle) in enumerate(
        zip(ours.currents, theirs.currents, strict=True)
    ):
        if not oracle:
            continue
        assert [tag for tag, _c in mine] == [tag for tag, _c in oracle], (
            f"{name} table {table}: tag order differs"
        )
        peak = max(range(len(oracle)), key=lambda i: abs(oracle[i][1]))
        scale_a, scale_b = mine[peak][1], oracle[peak][1]
        assert scale_a and scale_b, f"{name} table {table}: zero peak current"
        for row, ((_ta, a), (_tb, b)) in enumerate(zip(mine, oracle, strict=True)):
            assert abs(a / scale_a - b / scale_b) <= CURVE_TOL, (
                f"{name} table {table} row {row}: "
                f"{a / scale_a} vs {b / scale_b} (normalised)"
            )


PATTERN_FIXTURES = ("dipole_rp_pattern", "dipole_rp_crossed_quadrature")


@pytest.mark.parametrize("name", PATTERN_FIXTURES)
def test_pattern_gain_agrees_at_every_angle(name, pair):
    """TOTAL gain within 0.5 dB, everywhere the oracle reports a real number.

    Rows at nec2c's -999.99 floor are skipped on the oracle side but must be at
    the floor on ours too — that floor is the ``|E|² <= 1e-20`` test, and
    getting it wrong is how a pattern quietly acquires lobes in its own nulls.
    """
    ours, theirs = pair(name)
    assert [len(t) for t in ours.pattern] == [len(t) for t in theirs.pattern]
    assert ours.pattern, f"{name}: no RADIATION PATTERNS table"
    for mine, oracle in zip(ours.pattern, theirs.pattern, strict=True):
        for row_a, row_b in zip(mine, oracle, strict=True):
            assert (row_a[0], row_a[1]) == (row_b[0], row_b[1]), "angle grid differs"
            if row_b[4] <= -900.0:
                assert row_a[4] <= -900.0, f"{name} at {row_b[:2]}: null filled in"
                continue
            assert abs(row_a[4] - row_b[4]) <= GAIN_TOL_DB, (
                f"{name} at theta={row_b[0]} phi={row_b[1]}: "
                f"{row_a[4]:.2f} vs {row_b[4]:.2f} dB"
            )


@pytest.mark.parametrize("name", PATTERN_FIXTURES)
def test_peak_gain_direction_agrees_within_one_step(name, pair):
    ours, theirs = pair(name)
    for mine, oracle in zip(ours.pattern, theirs.pattern, strict=True):
        best_a = max(mine, key=lambda r: r[4])
        best_b = max(oracle, key=lambda r: r[4])
        thetas = sorted({r[0] for r in oracle})
        phis = sorted({r[1] for r in oracle})
        d_theta = thetas[1] - thetas[0] if len(thetas) > 1 else 0.0
        d_phi = phis[1] - phis[0] if len(phis) > 1 else 0.0
        assert abs(best_a[0] - best_b[0]) <= d_theta, (
            f"{name}: peak theta {best_a[0]} vs {best_b[0]}"
        )
        assert abs(best_a[1] - best_b[1]) <= d_phi, (
            f"{name}: peak phi {best_a[1]} vs {best_b[1]}"
        )


@pytest.mark.parametrize("name", PATTERN_FIXTURES)
def test_pattern_polarisation_split_sums_to_the_total(name, pair):
    """VERTC and HORIZ must add up to TOTAL, on our side and the oracle's.

    Reading the two polarisations out of the wrong pair of columns still
    produces a plausible-looking table; only this identity notices.
    """
    ours, _theirs = pair(name)
    for table in ours.pattern:
        for theta, phi, vertc, horiz, total, _et, _ep in table:
            if total <= -900.0:
                continue
            linear = 0.0
            for value in (vertc, horiz):
                if value > -900.0:
                    linear += 10.0 ** (value / 10.0)
            import math

            assert abs(10.0 * math.log10(linear) - total) <= 0.06, (
                f"{name} at theta={theta} phi={phi}: {vertc} + {horiz} != {total} dB"
            )


def test_the_sense_column_is_what_makes_a_row_twelve_tokens():
    """The unknown-list item, resolved against both pattern fixtures.

    ``Execute.processResponse`` reads the E-field pair at ``ptr = 8`` for a
    12-token row and ``ptr = 7`` for an 11-token one. The only thing that
    changes the count is the SENSE column, which nec2c blanks exactly when
    BOTH field components fall under its 1e-20 threshold — the same test that
    prints the -999.99 gain floor. So: a row with a named sense has a real
    field, an 11-token row is a null, and the two forms address the same
    columns. Reproduced on both sides of every pattern fixture.
    """
    seen_words = set()
    arities = {11: 0, 12: 0}
    for name in PATTERN_FIXTURES:
        for text in (our_printout(name), oracle_printout(name)):
            armed = False
            counts = {11: 0, 12: 0}
            for line in text.splitlines():
                parts = line.split()
                if parts[:2] == ["DEGREES", "DEGREES"]:
                    armed = True
                    continue
                if not armed:
                    continue
                if len(parts) not in (11, 12):
                    armed = False
                    continue
                counts[len(parts)] += 1
                if len(parts) == 12:
                    seen_words.add(parts[7])
                    assert float(parts[4]) > -900.0, (
                        f"{name}: a named SENSE on a floored row: {line!r}"
                    )
                else:
                    assert float(parts[4]) <= -900.0, (
                        f"{name}: a blank SENSE on a live row: {line!r}"
                    )
            assert counts[12], f"{name}: no row carries a SENSE word"
            for arity, count in counts.items():
                arities[arity] += count
    # Both arities must occur, but not necessarily in the same table:
    # dipole_rp_pattern is a linear dipole and half its rows are nulls, while
    # every direction off the crossed quadrature pair carries a field, so its
    # rows are all 12 tokens.
    assert arities[11] and arities[12], arities
    # dipole_rp_pattern can only ever say LINEAR; the crossed pair in
    # quadrature is what reaches the circular forms.
    assert seen_words == {"LINEAR", "LEFT"}, seen_words
