"""AK#1678: the NEC-2 engine solves the networks NEC-5 solves.

AC6LA switched the solver from NEC-5 to NEC-2 on two designs with a matching
network (QRZ 1003328 #140) and got "a NEC-2 deck cannot express TL/virtual-
driver networks ... The NEC-5 deck cannot express them either", one click
after NEC-5 had solved the same design. `NEC2Engine` built every run through
`nec_export.export_nec`, the download writer, which refuses a network no
single deck expresses; NEC-5 had solved those since #1280 by its multiport-Y
route, and PyNEC since #575.

The fix gives NEC-2 that route: one structure deck per real port (its segment
centre at 1 V, the others shorted), the segment currents read into Y, and the
shared `NetworkReducer` on top — with the downstream arithmetic in
`engines/_multiport.py`, shared with NEC-5 rather than copied. The download
still refuses, in words that are now true for either reader.

WHAT GATES WHAT. The route decision, the deck text and the refusal need no
binary and run everywhere. The NUMBERS need a NEC-2: on a box with nec2c they
are checked against PyNEC (nec2++, the same formulation in process, so the bar
is tight), and on every box against momwire's portal stand-in, which writes a
nec2c-format printout from momwire's own solve (so that bar is an engine
agreement, not a round trip).
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

import antennaknobs.web.server  # noqa: F401 — must load before adapter (import cycle)
from antennaknobs.engines import _multiport
from antennaknobs.engines import nec2 as m
from antennaknobs.engines.nec2 import NEC2Engine, NEC2Error, find_nec2
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_export import export_nec

pytestmark = pytest.mark.filterwarnings("ignore")

FIX = Path(__file__).parent / "fixtures"
LNET = FIX / "ac6la_1678" / "dan118-eznec-lnet.nec"
C1L1 = FIX / "ac6la_1678" / "snBydipole1-C1-L1.ssn"
XMATCH = FIX / "simnec_ac6la_1679" / "snBydipole1-LC1.ssn"

_HAVE_PYNEC = importlib.util.find_spec("PyNEC") is not None
needs_pynec = pytest.mark.skipif(not _HAVE_PYNEC, reason="PyNEC not installed")


def _nec2c():
    return find_nec2() or shutil.which("nec2c")


needs_nec2 = pytest.mark.skipif(
    _nec2c() is None, reason="no NEC-2 binary: set NEC2_EXE, or put nec2c on PATH"
)


@pytest.fixture(scope="module")
def stub_exe(tmp_path_factory):
    """An executable the route-decision tests never run: `NEC2Engine` resolves
    its binary at construction, and the route, the ports and the deck text are
    all properties of the model, not of a solve."""
    p = tmp_path_factory.mktemp("nec2") / "nec2c"
    p.write_text("#!/bin/sh\nexit 1\n")
    p.chmod(0o755)
    return str(p)


def _file(path):
    cls = builder_from_file(str(path))
    return cls, cls.file_ground


def _z(zs):
    return complex(np.atleast_1d(zs)[0])


# ---------------------------------------------------------------------------
# the route decision, no binary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [LNET, C1L1], ids=["eznec-lnet", "simnec-C1-L1"])
def test_dans_designs_take_the_route(path, stub_exe):
    """The premise: both designs AC6LA reported are ones the download writer
    refuses, and the engine now reduces them rather than refusing with it."""
    cls, ground = _file(path)
    with pytest.raises(NotImplementedError, match="TL/virtual-driver"):
        export_nec(cls(), ground=ground)
    eng = NEC2Engine(cls(), ground=ground, nec2_exe=stub_exe)
    assert eng._use_reducer
    assert eng._real_port_names


@pytest.mark.antenna_computation_check
def test_the_route_takes_exactly_the_designs_the_writer_refused(stub_exe):
    """Over the whole catalog, both directions: a design reduces on NEC-2 iff
    `export_nec` refuses its network. So nothing the engine solved before
    moved route, and nothing it refused is still refused for the network."""
    import antennaknobs.web.examples  # noqa: F401
    from antennaknobs.web.examples import REGISTRY

    disagree, reduced = [], 0
    for name in sorted(REGISTRY):
        cls = getattr(REGISTRY[name], "builder_cls", None)
        if cls is None:
            continue
        try:
            export_nec(cls(), ground="free")
            refused = False
        except NotImplementedError as e:
            refused = "TL/virtual-driver" in str(e)
        except Exception:  # noqa: BLE001 — geometry refusals are other rows
            continue
        try:
            eng = NEC2Engine(cls(), ground="free", nec2_exe=stub_exe)
        except Exception:  # noqa: BLE001 — same: not the network question
            continue
        reduced += eng._use_reducer
        if eng._use_reducer != refused:
            disagree.append((name, eng._use_reducer, refused))
    assert not disagree, disagree
    # 25 on 2026-09-23; a collapse to none would pass the loop vacuously.
    assert reduced >= 20, reduced


def test_a_design_without_a_reducer_network_keeps_its_deck(stub_exe):
    """The native route is `export_nec`'s deck, byte for byte, and refuses
    the route's `sources=` rather than silently ignoring it."""
    from antennaknobs.designs.dipoles.invvee import Builder

    b = Builder()
    eng = NEC2Engine(b, ground="free", nec2_exe=stub_exe)
    assert not eng._use_reducer
    assert eng.deck(b.freq) == export_nec(b, ground="free", include_rp=False)
    assert eng._excitation(b.freq) == (None, None)
    with pytest.raises(ValueError, match="sources="):
        eng.deck(b.freq, sources=[(1, 1, 1.0)])


def test_a_current_source_only_network_keeps_the_gyrator_deck(stub_exe):
    """AK#1597's exemption survives: a network whose ONLY reducer reason is a
    current source has a single-deck spelling, so it stays on `export_nec`.
    AC6LA's `Cardioidmodnec2.nec` is two current sources and nothing else."""
    cls, ground = _file(FIX / "eznec_gyrator_1595" / "Cardioidmodnec2.nec")
    b = cls()
    eng = NEC2Engine(b, ground=ground, nec2_exe=stub_exe)
    assert not eng._use_reducer
    deck = eng.deck(b.freq)
    assert deck == export_nec(b, ground=ground, include_rp=False)
    assert "NT " in deck


def test_a_structure_deck_carries_the_antenna_and_no_network(stub_exe):
    """One EX per drive point, at a segment centre, and not one card for the
    network: its branches are the reducer's to stamp (PyNEC's real-geometry
    context carries none either). The source sits on the middle segment of
    an odd count, NEC-2's centre-feed convention."""
    cls, ground = _file(C1L1)
    eng = NEC2Engine(cls(), ground=ground, nec2_exe=stub_exe)
    ((tag, seg, w),) = eng._port_drive[eng._real_port_names[0]]
    deck = eng.deck(14.175, sources=[(tag, seg, 1.0 + 0j)])
    cards = [ln.split()[0] for ln in deck.splitlines()]
    assert "NT" not in cards and "TL" not in cards
    assert [ln for ln in deck.splitlines() if ln.startswith("EX")] == [
        f"EX 0 {tag} {seg} 0 1 0"
    ]
    n_seg = [t for t in eng.tups][tag - 1][2]
    assert n_seg % 2 == 1 and seg == (n_seg + 1) // 2, (n_seg, seg)
    assert w == 1.0


# ---------------------------------------------------------------------------
# the refusal wording (AK#1678 item 2)
# ---------------------------------------------------------------------------


def test_the_download_refusal_is_true_for_either_reader():
    """It refuses a single DECK, and must not say anything a user who just
    solved the design on NEC-5 (or now NEC-2) knows to be false."""
    cls, ground = _file(C1L1)
    with pytest.raises(NotImplementedError) as exc:
        export_nec(cls(), ground=ground)
    msg = str(exc.value)
    assert "The NEC-5 deck cannot express them either" not in msg
    assert "single NEC-2 deck" in msg and "single NEC-5 deck" in msg
    assert "engines still solve" in msg, msg
    # A download reader has chosen no engine, so PyNEC stays unnamed (#1389).
    assert "PyNEC" not in msg, msg


# ---------------------------------------------------------------------------
# the shared arithmetic
# ---------------------------------------------------------------------------


def test_nec2s_formulation_asymmetry_is_information_not_a_refusal():
    """AK#1689. NEC-2's point-matched Y is not symmetric: `multiband.
    hexbeam_5band` reads 1.85e-2 of the ports' scale on nec2c AND on PyNEC
    (1.96e-2 when #1678 measured it). No per-engine bar: that asymmetry, and even a 10 % misread on a coupled
    pair, pass the shared backstop and are returned as information. The port
    bookkeeping is checked directly per run (`_check_port_run`, below). Only a
    gross asymmetry — a transposed pair of rows, 1.2 of the ports' scale —
    refuses."""
    Y = np.array(
        [[2.2e-3 - 8.2e-3j, 5.0e-3 - 2.0e-3j], [5.0e-3 - 2.0e-3j, 8.7e-3 - 9.5e-3j]]
    )
    asym = Y.copy()
    asym[0, 1] *= 1.0 + 0.04  # hexbeam_5band's size: ~2e-2
    assert (
        1e-2 < _multiport.check_reciprocity(asym, ["a", "b"], NEC2Error, "NEC-2") < 5e-2
    )
    misread = Y.copy()
    misread[0, :] *= 1.1
    assert _multiport.check_reciprocity(misread, ["a", "b"], NEC2Error, "NEC-2") < 0.5
    with pytest.raises(NEC2Error, match="not reciprocal"):
        _multiport.check_reciprocity(Y[::-1, :].copy(), ["a", "b"], NEC2Error, "NEC-2")


# One nec2c run (2026-10-16): two wires, 5 and 7 segments, EX 0 2 3 at 1 V. The
# source row prints the ABSOLUTE segment (8 = 5 + 3); the CURRENTS table holds
# the same current at tag 2's third segment.
_ONE_PORT_RUN = """
                        --------- ANTENNA INPUT PARAMETERS ---------
  TAG   SEG       VOLTAGE (VOLTS)         CURRENT (AMPS)         IMPEDANCE (OHMS)        ADMITTANCE (MHOS)     POWER
  No:   No:     REAL      IMAGINARY     REAL      IMAGINARY     REAL      IMAGINARY    REAL       IMAGINARY   (WATTS)
    2     8  1.0000E+00  0.0000E+00  4.1706E-03 -1.1296E-02  2.8765E+01  7.7908E+01  4.1706E-03 -1.1296E-02  2.0853E-03


                           -------- CURRENTS AND LOCATION --------
                                  DISTANCES IN WAVELENGTHS

   SEG  TAG    COORDINATES OF SEGM CENTER     SEGM    ------------- CURRENT (AMPS) -------------
   No:  No:       X         Y         Z      LENGTH     REAL      IMAGINARY    MAGN        PHASE
     1    1    0.0000    0.0000    0.0500   0.10007  2.4169E-04  3.5460E-03  3.5543E-03   86.101
     2    1    0.0000    0.0000    0.1501   0.10007  5.5359E-04  9.0011E-03  9.0181E-03   86.481
     3    1    0.0000    0.0000    0.2502   0.10007  6.5655E-04  1.1068E-02  1.1088E-02   86.605
     4    1    0.0000    0.0000    0.3502   0.10007  5.5093E-04  9.0321E-03  9.0489E-03   86.509
     5    1    0.0000    0.0000    0.4503   0.10007  2.3948E-04  3.5610E-03  3.5691E-03   86.153
     6    2    0.1001    0.0000    0.0357   0.07148  1.1165E-03 -3.0711E-03  3.2677E-03  -70.021
     7    2    0.1001    0.0000    0.1072   0.07148  2.9523E-03 -8.0569E-03  8.5808E-03  -69.876
     8    2    0.1001    0.0000    0.1787   0.07148  4.1706E-03 -1.1296E-02  1.2041E-02  -69.735
     9    2    0.1001    0.0000    0.2502   0.07148  4.6000E-03 -1.3019E-02  1.3808E-02  -70.540
    10    2    0.1001    0.0000    0.3216   0.07148  4.1684E-03 -1.2147E-02  1.2843E-02  -71.060
    11    2    0.1001    0.0000    0.3931   0.07148  2.9491E-03 -8.7283E-03  9.2131E-03  -71.331
    12    2    0.1001    0.0000    0.4646   0.07148  1.1146E-03 -3.3197E-03  3.5018E-03  -71.441
"""


def _port_run(text, sources):
    NEC2Engine._check_port_run("p", sources, text, NEC2Engine._parse_currents(text)[0])


def test_a_port_run_that_drove_its_own_port_passes():
    _port_run(_ONE_PORT_RUN, [(2, 3, 1.0 + 0j)])


@pytest.mark.parametrize(
    "sources",
    [
        [(2, 4, 1.0 + 0j)],  # the next segment of the same wire
        [(1, 3, 1.0 + 0j)],  # the same relative segment on another wire
        [(2, 3, 0.5 + 0j)],  # the right segment at the wrong voltage
        [(2, 3, 1.0 + 0j), (1, 2, 1.0 + 0j)],  # a source the run never had
    ],
)
def test_a_port_run_that_drove_anything_else_refuses(sources):
    """AK#1689's direct check: what the run DROVE must be what the column is
    for. No tolerance — a port addressed one segment off fails outright."""
    with pytest.raises(NEC2Error, match="did not drive"):
        _port_run(_ONE_PORT_RUN, sources)


@needs_nec2
def test_a_swapped_port_assignment_fails_on_a_real_nec2(monkeypatch):
    """AK#1689 item 4: drive the WRONG port in each run — the bookkeeping slip
    the old gate was for — and the direct check refuses on the first column,
    whatever the coupling. Unpatched, the same design solves, and hexbeam's
    1.85e-2 asymmetry is reported rather than refused."""
    import importlib

    monkeypatch.setenv("NEC2_EXE", _nec2c())
    cls = importlib.import_module(
        "antennaknobs.designs.multiband.hexbeam_5band"
    ).Builder
    eng = NEC2Engine(cls())
    assert eng._use_reducer and len(eng._real_port_names) >= 2
    wl = m.C_LIGHT / (eng.builder.freq * 1e6)
    eng._compute_y_matrix(wl)
    assert 1e-2 < eng._y_reciprocity_rel < 3e-2

    a, b = eng._real_port_names[:2]
    real_deck = eng.deck

    def deck(freq, *, sources=None, **kw):
        if sources == [(t, g, complex(w)) for t, g, w in eng._port_drive[a]]:
            sources = [(t, g, complex(w)) for t, g, w in eng._port_drive[b]]
        return real_deck(freq, sources=sources, **kw)

    monkeypatch.setattr(eng, "deck", deck)
    with pytest.raises(NEC2Error, match="did not drive"):
        eng._compute_y_matrix(wl)


@needs_nec2
@needs_pynec
def test_the_reported_asymmetry_is_the_formulations(monkeypatch):
    """AK#1689 item 4, the validation the runtime gate is not: the asymmetry
    NEC-2 reports is the one PyNEC (nec2++, the same formulation, in process)
    has on the same design — 1.8531e-2 vs 1.8536e-2 on hexbeam_5band, the two
    Y agreeing to 9.6e-5. Ours, not a bookkeeping residue."""
    import importlib

    from antennaknobs.engines.pynec import PyNECEngine

    monkeypatch.setenv("NEC2_EXE", _nec2c())
    cls = importlib.import_module(
        "antennaknobs.designs.multiband.hexbeam_5band"
    ).Builder
    eng = NEC2Engine(cls())
    wl = m.C_LIGHT / (eng.builder.freq * 1e6)
    eng._compute_y_matrix(wl)
    ref, _pair = _multiport.y_asymmetry(
        PyNECEngine(cls())._compute_y_matrix(wl), eng._real_port_names
    )
    assert ref > 1e-2
    assert eng._y_reciprocity_rel == pytest.approx(ref, rel=1e-2)


def test_the_source_gain_factor_is_structure_over_source_power():
    assert _multiport.source_gain_factor(25.0, None, NEC2Error) == 1.0
    assert _multiport.source_gain_factor(25.0, 50.0, NEC2Error) == pytest.approx(0.5)
    with pytest.raises(NEC2Error, match="per source watt"):
        _multiport.source_gain_factor(25.0, 0.0, NEC2Error)


def test_the_wire_loss_folds_into_the_reducers_budget():
    eff, rows = _multiport.fold_wire_loss(0.9, 2.0, [("TL a→b", 0.2)], 0.1)
    assert eff == pytest.approx(0.85)
    assert rows == [("TL a→b", 0.2), ("Wire loss", 0.1)]


# ---------------------------------------------------------------------------
# the numbers, on a real NEC-2 against PyNEC (the same formulation)
# ---------------------------------------------------------------------------


@needs_nec2
@needs_pynec
@pytest.mark.parametrize("path", [LNET, C1L1], ids=["eznec-lnet", "simnec-C1-L1"])
def test_dans_designs_solve_and_agree_with_pynec(path):
    """nec2c and nec2++ are the same formulation, so this is tight. Measured
    2026-09-23 over the file grounds: 52.945+3.871j vs 52.952+3.885j (lnet),
    54.840+15.545j vs 54.848+15.560j (C1-L1: its JamSegments(12) wire, split
    at the centre feed as a segment-centre engine feeds it, AK#1679), 3e-4 at
    worst. Also measured over the catalog's 25 reduced designs: 3.6e-3 at
    worst (wire.efhw_sloper)."""
    from antennaknobs.engines.pynec import PyNECEngine

    cls, ground = _file(path)
    e2 = NEC2Engine(cls(), ground=ground, nec2_exe=_nec2c())
    ep = PyNECEngine(cls(), ground=ground)
    z2, currents, budget = e2.solve_snapshot()
    zp = _z(ep.impedance())
    ep.current_distribution()  # stamps PyNEC's efficiency and input power
    assert abs(z2[0] - zp) / abs(zp) < 2e-3, (z2, zp)
    assert e2._excited_efficiency == pytest.approx(ep._excited_efficiency, abs=1e-3)
    assert e2._excited_p_in == pytest.approx(ep._excited_p_in, rel=2e-3)
    # One WireCurrents per AUTHORED wire: a wire split at its feed (C1-L1's
    # jammed 12 segments, AK#1679) joins back into one (AK#1510).
    assert len(currents) == len(cls().build_wires())
    # The reducer's rows, then NEC-2's conductor loss: LOSSES ONLY.
    assert e2._excited_power_budget[-1][0] == "Wire loss"
    assert [r for r, _w in e2._excited_power_budget[:-1]] == [
        r for r, _w in ep._excited_power_budget if not r.startswith("wire loss")
    ]
    # impedance() and the snapshot are one answer.
    assert _z(e2.impedance()) == pytest.approx(z2[0], abs=1e-9)


@needs_nec2
def test_the_eznec_decks_current_source_reads_back_in_amps():
    """The per-feed readout on this route is the network's SOURCE, not the
    resolved port voltage the structure deck is driven with: EZNEC's deck
    drives its virtual segment with EX 4, 1.414214 A (AK#1657's unit)."""
    cls, ground = _file(LNET)
    eng = NEC2Engine(cls(), ground=ground, nec2_exe=_nec2c())
    eng.solve_snapshot()
    assert eng._excited_feed_units == ["A"]
    assert eng._excited_feed_values[0] == pytest.approx(1.414214)


@needs_nec2
@needs_pynec
def test_the_pattern_is_excited_and_per_source_watt():
    """The pattern deck drives every real port at its resolved voltage, and the
    gain is per SOURCE watt as NEC-5's and PyNEC's are (AK#1637).
    `dipoles.invvee_coax_station`'s feedline burns 31 % of the source power, so
    an unscaled pattern would sit 1.6 dB high; measured 0.327 vs PyNEC's 0.328
    dBi on this grid in free space."""
    from antennaknobs.designs.dipoles.invvee_coax_station import Builder
    from antennaknobs.engines.pynec import PyNECEngine

    grid = {"n_theta": 18, "n_phi": 36, "del_theta": 5, "del_phi": 10}
    e2 = NEC2Engine(Builder(), ground="free", nec2_exe=_nec2c())
    assert e2._use_reducer
    ff2 = e2.far_field(**grid)
    ffp = PyNECEngine(Builder(), ground="free").far_field(**grid)
    deck = e2.io_runs[-1]["deck"]
    assert "RP " in deck and any(ln.startswith("EX ") for ln in deck.splitlines())
    assert ff2.max_gain == pytest.approx(ffp.max_gain, abs=0.02)


@needs_nec2
@pytest.mark.parametrize(
    ("path", "planes"),
    [(LNET, [None, "rig", "nt1b"]), (C1L1, [None, "feed", "L1", "C1", "rig"])],
    ids=["eznec-lnet", "simnec-C1-L1"],
)
def test_the_web_lane_solves_every_plane(path, planes, monkeypatch):
    """The user story, through the app's own solve body and pattern endpoint:
    no plane errors any more (AK#1678's reproduction raised on each of these)."""
    from antennaknobs.web import adapter

    monkeypatch.setenv("NEC2_EXE", _nec2c())
    cls, _ground = _file(path)
    ex = adapter._make_example(path.stem, cls)
    f = cls().freq
    for plane in planes:
        req = {"measurement_freq_mhz": f, "design_freq_mhz": f}
        if plane:
            req["plane"] = plane
        out = ex.nec2_solve(dict(req))
        assert out["z_in_re"] > 0, (plane, out["z_in_re"])
        assert out["power_budget"], plane
    pat = ex.nec2_pattern({"measurement_freq_mhz": f, "design_freq_mhz": f})
    assert max(max(r) for r in pat["gain_dbi"]) > -10.0


# ---------------------------------------------------------------------------
# self-tuning tuners tune on NEC-2 (AK#1646, #1661)
# ---------------------------------------------------------------------------


def _tuned_skyloop():
    """The catalog skyloop with its fixed L-match swapped for the tuner, the
    design `test_l_tuner_tune_1646` tunes on momwire and PyNEC."""
    from antennaknobs.station import l_network_tuner
    from antennaknobs.designs.loops.skyloop_lmatch import Builder as Skyloop
    from antennaknobs.network import (
        Driven,
        Instance,
        Network,
        PortOnWire,
        PortVirtual,
    )

    class Tuned(Skyloop):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "in": PortVirtual("in")},
                branches=[
                    Instance(
                        "match",
                        l_network_tuner(tune_to=50.0, mode="low", ql=200.0, qc=2000.0),
                        rig="in",
                        out="feed",
                    )
                ],
                sources=[Driven(port="in", voltage=1 + 0j)],
            )

    return Tuned()


@needs_nec2
def test_an_l_tuner_tunes_on_nec2_and_holds():
    b = _tuned_skyloop()
    eng = NEC2Engine(b, ground=None, nec2_exe=_nec2c())
    f0 = b.design_freq
    z = complex(eng.impedance_sweep(np.array([f0]))[0][0])
    assert z == pytest.approx(50.0, abs=1e-6)
    z_off = complex(eng.impedance_sweep(np.array([1.03 * f0]))[0][0])
    assert abs(z_off - 50.0) > 1.0
    rows = {r["label"]: r["value"] for r in eng._reducer.tuner_rows()}
    assert rows["series L"] > 0 and rows["shunt C"] > 0


@needs_nec2
def test_dans_imported_xmatch_tunes_exactly_on_nec2():
    """AC6LA's own self-tuning XMATCH (AK#1662), tuned from NEC-2's Y."""
    cls, ground = _file(XMATCH)
    eng = NEC2Engine(cls(), ground=ground, nec2_exe=_nec2c())
    assert _z(eng.impedance()) == pytest.approx(50.0, abs=1e-6)


# ---------------------------------------------------------------------------
# every box: momwire's portal stand-in
# ---------------------------------------------------------------------------

_PORTAL_STANDIN = """
import sys
from pathlib import Path

argv = sys.argv[1:]
inp = argv[argv.index("-i") + 1]
outp = argv[argv.index("-o") + 1]
from momwire.portal import run_deck

out, _err = run_deck(Path(inp).read_text())
Path(outp).write_text(out)
"""


@pytest.fixture()
def portal_exe(tmp_path):
    pytest.importorskip("momwire.portal")
    script = tmp_path / "standin.py"
    script.write_text(textwrap.dedent(_PORTAL_STANDIN))
    exe = tmp_path / "nec2"
    exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    exe.chmod(0o755)
    return str(exe)


def test_the_route_runs_end_to_end_through_the_portal_standin(portal_exe):
    """Deck writer, one run per port, the currents parser, Y and the reducer,
    against a printout nobody wrote to make this pass. The NUMBER is momwire's
    (the stand-in solves the deck itself), so the bar is an engine agreement:
    measured 55.62+26.88j through the portal against momwire's 54.83+27.11j on
    the C1-L1 in free space (nec2c: 54.72+26.58j); 5 % is the bar, as in
    #1354's portal test."""
    from antennaknobs.engines.momwire import MomwireEngine

    m._FORM_CACHE.clear()
    cls, _ground = _file(C1L1)
    z2 = _z(NEC2Engine(cls(), ground="free", nec2_exe=portal_exe).impedance())
    zm = _z(MomwireEngine(cls(), ground=None).impedance())
    assert abs(z2 - zm) / abs(zm) < 0.05, (z2, zm)
