"""AK#1576: the export -> import -> export SimNEC round trip is a fixed
point, AT THE FEED-POSITION-PRESERVING COUNT the importer's own rule picks.

Dan AC6LA's deck (``tests/fixtures/1576_simnec_deck_segments``) feeds ``GW
2`` — a 2-segment wire — at 50%, the junction between its two segments.
NEC-2 syntax has no end-code (unlike NEC-5's ``EX ... 2``, which addresses a
segment END and so can sit exactly on a knot), so the closest a NEC-2/SimNEC
``EX`` card can put a source is a whole segment. The project's feed-position
rule (AK#1510: keep the exact position; re-mesh <=2x to land a segment
centre under it; never snap) already resolves this on IMPORT — the 2-segment
wire reads as 3 segments with the source on the middle one, exactly on the
physical centre — and ``export_nec`` (which this module's geometry comes
from) writes that resolved mesh verbatim. An EARLIER version of this fix
instead rewrote the export back to the deck's own 2 segments with the source
on segment 1: that is a SNAP (source at 25% of the wire, not the junction),
changes the modelled antenna, and was reverted — see
``simnec_export.build_nec_portal_script``'s docstring and the "Why a written
count can differ..." note in the module docstring.

What's actually fixed here: ``file_designs._ssn_builder`` never set
``file_deck_parsed`` (unlike ``_nec_builder``), so a re-imported ``.ssn``
couldn't carry that fact forward — see the docstring on that kwarg's call
site. The round trip below is a byte-identical fixed point (2 -> 3 -> 3, not
2 -> 3 -> 4), and — the guard the byte comparison alone does not give —
the re-imported design's feed position and driving-point impedance equal
the original's.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from antennaknobs.engines.pynec import PyNECEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.network import PortOnWire
from antennaknobs.simnec_export import export_ssn

FIXTURES = Path(__file__).parent / "fixtures" / "1576_simnec_deck_segments"
AC6LA_DECK = FIXTURES / "2segCtrExample3.nec"
ODD_CENTRE_DECK = FIXTURES / "odd_centre_feed.nec"
EVEN_OFFCENTRE_DECK = FIXTURES / "even_offcentre_feed.nec"

GROUND = ("finite", 14.0, 0.006)

# `nec_export._num` writes coordinates at 6 decimal digits in scientific
# notation (7 significant figures), so a design that round-trips through
# TEXT loses precision there regardless of this issue's fix — confirmed by
# measuring both the AC6LA deck and a free-space case, both ~1e-6 relative.
# 1e-9 is not this writer's precision; this tolerance is.
_Z_REL_TOL = 1e-6


def _gw(text: str, tag: int) -> str:
    return next(s for s in text.splitlines() if s.startswith(f"GW {tag} "))


def _ex(text: str) -> str:
    return next(s for s in text.splitlines() if s.startswith("EX "))


# --- the deck's own count feeds the source off the physical centre ----------


def test_simnec_writes_the_importers_three_segment_remesh():
    """`GW 2` (the deck's own 2 segments) reads back and writes out as 3, the
    source on the middle segment — the AK#1510 re-mesh, not the deck's raw
    count. This is the sanctioned spelling, not a regression: the fixed-point
    and fidelity tests below are what actually gate the issue."""
    b = builder_from_file(str(AC6LA_DECK))()
    ssn = export_ssn(b, freq_mhz=float(b.freq), ground=GROUND)
    assert _gw(ssn, 2).split()[2] == "3"
    # I1 I2 I3: voltage source, tag 2, segment 2 of 3 (the middle segment).
    assert _ex(ssn).split()[1:4] == ["0", "2", "2"]


def test_nec5_deck_keeps_the_decks_own_two_segments():
    """NEC-5's end code addresses the junction directly, so its writer does
    NOT need the re-mesh: `GW 2` stays 2 there. SimNEC and NEC-5 legitimately
    disagree on this wire's segment count — each is faithful to what its OWN
    card format can address, and neither snaps the feed position."""
    from antennaknobs.nec5_export import export_nec5

    b = builder_from_file(str(AC6LA_DECK))()
    nec5 = export_nec5(b, ground=GROUND, design="x", rung="r", ground_name="finite")
    assert _gw(nec5, 2).split()[2] == "2"


def test_pynec_impedance_is_unaffected():
    """This issue's fix touches only text-emission code (`file_designs`); the
    SOLVE this design's impedance comes from (`PyNECEngine`) is untouched.
    Pinned value cross-checked against the pre-fix tree by `git stash` (same
    branch, same commit) rather than re-derived here, so a future numerical
    change to the solver -- a real one -- still fails this test rather than
    silently re-baselining it."""
    b = builder_from_file(str(AC6LA_DECK))()
    (z,) = PyNECEngine(b, ground=GROUND).impedance()
    assert complex(z) == pytest.approx(55.76639472824179 + 19.235500526171688j)


# --- requirement 2: export -> import -> export is a fixed point, AND is the
# same antenna (feed position + impedance), not just the same bytes ---------


def _roundtrip(path: Path, tmp_path: Path):
    """(ssn1, ssn2, b1, b2): one export -> reimport -> export hop."""
    b1 = builder_from_file(str(path))()
    ssn1 = export_ssn(b1, freq_mhz=float(b1.freq), ground=None, name="rt")
    reimported = tmp_path / "rt.ssn"
    reimported.write_text(ssn1)
    b2 = builder_from_file(str(reimported))()
    assert b2.file_deck_parsed is not None  # the file_designs.py fix
    ssn2 = export_ssn(b2, freq_mhz=float(b2.freq), ground=None, name="rt")
    return ssn1, ssn2, b1, b2


def _feed_port(builder):
    net = builder.build_network()
    (port,) = [p for p in net.ports.values() if isinstance(p, PortOnWire)]
    return port


@pytest.mark.parametrize(
    "deck",
    [AC6LA_DECK, ODD_CENTRE_DECK, EVEN_OFFCENTRE_DECK],
    ids=["ac6la_2seg_centre", "odd_centre_noop", "even_offcentre_split"],
)
def test_export_import_export_is_a_fixed_point(deck, tmp_path):
    ssn1, ssn2, _b1, _b2 = _roundtrip(deck, tmp_path)
    assert ssn1 == ssn2


@pytest.mark.parametrize(
    "deck",
    [AC6LA_DECK, ODD_CENTRE_DECK, EVEN_OFFCENTRE_DECK],
    ids=["ac6la_2seg_centre", "odd_centre_noop", "even_offcentre_split"],
)
def test_the_round_trip_preserves_impedance(deck, tmp_path):
    """The byte-equal fixed point above says the WRITER is stable; it says
    nothing about whether the re-imported design is still the same antenna.
    The driving-point impedance on PyNEC is the representation-independent
    invariant that answers that, for all three fixtures (exact for
    even_offcentre_feed's round-number geometry; text-precision-bound
    elsewhere — see `_Z_REL_TOL`)."""
    _ssn1, _ssn2, b1, b2 = _roundtrip(deck, tmp_path)
    (z1,) = PyNECEngine(b1, ground=None).impedance()
    (z2,) = PyNECEngine(b2, ground=None).impedance()
    assert complex(z2) == pytest.approx(complex(z1), rel=_Z_REL_TOL)


@pytest.mark.parametrize(
    "deck",
    [AC6LA_DECK, ODD_CENTRE_DECK],
    ids=["ac6la_2seg_centre", "odd_centre_noop"],
)
def test_the_round_trip_preserves_the_feed_position(deck, tmp_path):
    """For a wire that stays ONE wire through the round trip (no AK#1511
    split), the feed's `at` — its position on that wire, `None` meaning the
    exact centre — is a direct, representation-stable fidelity check: it
    must equal the original's, not drift the way the reverted rewrite drifted
    0.5 to 0.25. `even_offcentre_feed.nec` is excluded here on purpose: its
    feed sits where AK#1510/#1511 SPLITS the wire into two separate `GW`
    cards (pre-existing, untouched by this issue), so on re-import `at` is
    relative to a differently-shaped wire and isn't directly comparable —
    the impedance check above is what proves ITS physics is unchanged
    (exact, 0 relative difference, measured on this fixture's round-number
    geometry)."""
    _ssn1, _ssn2, b1, b2 = _roundtrip(deck, tmp_path)
    port1, port2 = _feed_port(b1), _feed_port(b2)
    assert port2.at == port1.at


def test_ac6la_deck_is_2_to_3_to_3_not_2_to_3_to_4():
    """The issue's own reported numbers, pinned explicitly: `GW 2` exports 3
    with the source on segment 2 (the AK#1510 re-mesh of the deck's 2), and
    a re-export of THAT `.ssn` is still 3 with the source on segment 2 -- a
    fixed point at 3, never growing to 4."""
    b1 = builder_from_file(str(AC6LA_DECK))()
    ssn1 = export_ssn(b1, freq_mhz=float(b1.freq), ground=GROUND, name="rt")
    assert _gw(ssn1, 2).split()[2] == "3"
    assert _ex(ssn1).split()[1:4] == ["0", "2", "2"]

    import tempfile

    with tempfile.TemporaryDirectory() as d:
        reimported = Path(d) / "rt.ssn"
        reimported.write_text(ssn1)
        b2 = builder_from_file(str(reimported))()
        ssn2 = export_ssn(b2, freq_mhz=float(b2.freq), ground=GROUND, name="rt")
    assert _gw(ssn2, 2).split()[2] == "3"
    assert _ex(ssn2).split()[1:4] == ["0", "2", "2"]


# --- requirement 3: the workbench second hop --------------------------------


@pytest.fixture
def userdir(tmp_path, monkeypatch):
    import antennaknobs.web.examples as examples

    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    yield tmp_path
    for key in [k for k in examples.REGISTRY if k.startswith("user.")]:
        del examples.REGISTRY[key]


@pytest.fixture
def client():
    import antennaknobs.web.server as server

    return TestClient(server.app)


def _req(geometry: str, **over) -> dict:
    return {
        "geometry": geometry,
        "solver": "momwire",
        "n_per_wire": 11,
        "design_freq_mhz": 3.68,
        "measurement_freq_mhz": 3.68,
        "wire_radius": 0.001,
        "ground": True,
        "ground_fast": False,
        **over,
    }


def test_workbench_second_hop_pins_three_to_three(userdir, client):
    """Reproduces the issue's reported workbench hop through the SAME
    `/design_ssn` route the Files view uses (`web.adapter.ssn_export`,
    `_build_builder`), not the bare library call. `GW 2` re-meshes 2 -> 3 on
    the FIRST hop (AK#1510, same as the library); the fix under test is that
    it stays 3 on the SECOND hop instead of growing to 4."""
    import antennaknobs.web.user_designs as web_user_designs

    (userdir / "2segCtrExample3.nec").write_bytes(AC6LA_DECK.read_bytes())
    web_user_designs.refresh()

    r1 = client.post("/design_ssn", json=_req("user.2segCtrExample3"))
    assert r1.status_code == 200
    got1 = r1.json()
    assert got1["available"] is True
    assert _gw(got1["text"], 2).split()[2] == "3"

    (userdir / "reimported.ssn").write_text(got1["text"])
    web_user_designs.refresh()

    r2 = client.post("/design_ssn", json=_req("user.reimported"))
    assert r2.status_code == 200
    got2 = r2.json()
    assert got2["available"] is True
    assert _gw(got2["text"], 2).split()[2] == "3"


# --- requirement 4: a catalog (auto-mesh) design's export is untouched ------
# (no dedicated test needed: this issue's fix lives entirely in
# `file_designs._ssn_builder`, which no catalog design's `build_wires()`
# path goes through, and the pre-existing `test_simnec_export.py` suite,
# unchanged by this issue, stays green — see the final report.)
