"""A NEC-2 deck CAN express a current source, so we write one (AK#1597).

`DrivenCurrent` forces the Y-matrix reducer, because NEC's `EX` drives VOLTS.
The writer refused every reducing network with one sentence — "there is no
faithful single-deck representation" — and for a current source that premise
was false, with the reporting deck as the counterexample: Dan AC6LA opened
`Cardioidmodnec2.nec`, a deck EZNEC ITSELF WROTE, and was told we could not
write it back.

NEC-2's spelling of an ideal current source is a GYRATOR: a phantom wire
parked far from the antenna carrying an `EX 0`, tied to the real feed segment
by an `NT` with Y11 = Y22 = 0, Y12 = Y21 = j. EZNEC writes it, 4nec2 builds it
to emulate `EX 6`, and `scripts/bench_nec_corpus.py`'s `gyrator_reference`
(AK#475) is the same construction from the other side.

The gates, in increasing independence:

- the ROUND TRIP, which is the gate the issue asked for and the only honest
  one: export the deck, read it back, require the same impedances. It closes
  the loop with AK#1595's reader, so a sign or scale error in either direction
  fails here;
- `nec2c`, a different NEC-2 implementation entirely, which must both ACCEPT
  the cards and force the currents we asked for.
"""

import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from antennaknobs.engines import MomwireEngine
from antennaknobs.engines.pynec import PyNECEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_export import export_nec

FIXTURES = Path(__file__).parent / "fixtures" / "eznec_gyrator_1595"
NEC2 = FIXTURES / "Cardioidmodnec2.nec"
NEC4 = FIXTURES / "Cardioidmodnec4.nec"

# OUR OWN solve of Dan's NEC-4.2 twin — momwire's default solver on that deck
# through the `@file` route, as the fixture README records. It is a regression
# pin on a cross-dialect identity, NOT an external authority: NEC-4.2 never
# printed these digits for us. The name is historical, and the comment it used
# to carry ("the oracle for this antenna in every dialect") invited reading it
# as NEC-4.2's own answer, which cost real time in AK#1607 — where this moved
# 3.9e-4 and momentarily looked like evidence about NEC-4's speed of light.
# What the NEC-4.2 deck IS the oracle for is the DRIVE the other two dialects
# must deliver (the fixture README's table), and that is unaffected by this
# number's value.
#
# Re-recorded 2026-09-20 for AK#1607 (an imported deck is solved at NEC's
# 299.8, not the SI c); the previous literal was the same solve at the SI c.
# The identity these pin — the NEC-2 gyrator deck against the NEC-4.2 native
# `EX 6` deck — is BIT-IDENTICAL across that change, which is the reason to
# re-record rather than to doubt the change.
ORACLE = np.array(
    [36.43350555306979 - 19.004373849634746j, 67.76101624023624 + 19.980489794638522j]
)
# What the two EX 6 cards ask for, and so what the gyrators must deliver.
EX6_CURRENTS = (complex(1.414214, 0.0), complex(0.0, -1.414214))

needs_nec2c = pytest.mark.skipif(
    shutil.which("nec2c") is None, reason="nec2c not on PATH"
)


def _z(path):
    cls = builder_from_file(str(path))
    return np.asarray(MomwireEngine(cls(), ground=cls.file_ground).impedance())


def _export(path, **kw):
    cls = builder_from_file(str(path))
    return export_nec(cls(), ground=cls.file_ground, include_rp=False, **kw)


def test_the_deck_eznec_wrote_can_be_written_back():
    """The report itself: this used to raise NotImplementedError."""
    deck = _export(NEC2)
    assert [ln for ln in deck.splitlines() if ln.startswith("NT ")]
    assert [ln for ln in deck.splitlines() if ln.startswith("EX 0 ")]


def test_the_round_trip_is_an_identity(tmp_path):
    """THE gate. Export the imported deck, re-import it, and require the same
    impedances — not close, the same. It closes the loop with AK#1595's
    reader, so a sign or scale error in either direction shows here."""
    z_in = _z(NEC2)
    out = tmp_path / "roundtrip.nec"
    out.write_text(_export(NEC2))
    z_out = _z(out)
    assert z_out == pytest.approx(z_in, rel=0, abs=0)
    # ... and that identity is on the right number, not merely self-consistent.
    assert z_out == pytest.approx(ORACLE, rel=1e-6)


def test_the_two_dialects_are_the_same_antenna():
    """What `ORACLE` is really asserting, stated as an identity rather than a
    literal — and the check that makes re-recording that literal safe.

    The claim of this whole fixture is that EZNEC's gyrator construction in
    NEC-2 delivers the drive NEC-4.2's native `EX 6` asks for, so the two
    decks are one antenna. A constant is a poor way to hold that: it also
    pins whatever else moves the number, and cannot tell the two apart. This
    can — it survives any change that moves both decks together, and fails
    for anything that moves one.

    BITWISE, deliberately. These are the same geometry, the same solver and
    the same forced currents; there is no rounding budget to spend."""
    assert _z(NEC2).tolist() == _z(NEC4).tolist()
    # NOTE, measured: neither line above catches a SIGN inversion, and the
    # oracle line does not rescue it. Flip the writer to V = -j*I and the
    # reader flips back (I' = -Y12*V = -I); impedance is invariant under
    # flipping BOTH forced currents, so this test still passes green. Verified
    # by doing it. The sign is held by
    # `test_the_drive_matches_the_one_EZNEC_ITSELF_WROTE` and the two nec2c
    # tests — external authorities — and by nothing in here.


def test_the_gyrator_is_the_one_the_reader_collapses(tmp_path):
    """The re-import must read the phantom as a VIRTUAL wire and collapse it
    to a forced current on real geometry — not carry it as a fourth antenna
    element. If it does not, the driving point comes back as 1/Z (AK#1595)."""
    from antennaknobs.nec_import import parse_nec
    from antennaknobs.network import DrivenCurrent

    deck = parse_nec(_export(NEC2), name="rt.nec", network=True)
    assert len(deck.virtual_segment_wires) == 1
    net = deck.network()
    assert [type(s).__name__ for s in net.sources] == ["DrivenCurrent"] * 2
    got = sorted((complex(s.current) for s in net.sources), key=lambda c: c.real)
    want = sorted(EX6_CURRENTS, key=lambda c: c.real)
    assert got == pytest.approx(want, rel=1e-9)
    assert all(isinstance(s, DrivenCurrent) for s in net.sources)


def test_the_phantom_has_more_than_one_segment():
    """Not cosmetic, and the reason a per-source 1-segment phantom (which is
    what `gyrator_reference` writes for nec2c) is wrong HERE: our own reader
    gives the 1-segment remote wire to issue #427's detector, which reads it
    as a bare TL termination and pins a driven one as electrically REAL. The
    deck would then round trip to 1/Z."""
    gw = [ln for ln in _export(NEC2).splitlines() if ln.startswith("GW ")]
    phantom = gw[-1].split()
    assert int(phantom[2]) >= 2


def test_the_phantom_stays_electrically_negligible():
    """The reader's other gate: extent under 0.05 lambda end to end. Sized at
    lambda/200 however many sources there are, so a four-source deck does not
    grow into that limit."""
    gw = [ln for ln in _export(NEC2).splitlines() if ln.startswith("GW ")]
    f = [float(x) for x in gw[-1].split()[3:9]]
    length = np.linalg.norm(np.array(f[3:]) - np.array(f[:3]))
    lam = 299.792458 / 299.7925
    assert length / lam < 0.05


def test_every_NT_precedes_every_EX():
    """NEC DROPS a voltage source read before a network card, and requires one
    configuration's network cards to be contiguous — the hazard
    `gyrator_reference` records, where it silently lost a TL. Card ORDER is
    part of the deck being correct."""
    lines = _export(NEC2).splitlines()
    nts = [i for i, ln in enumerate(lines) if ln.startswith("NT ")]
    exs = [i for i, ln in enumerate(lines) if ln.startswith("EX ")]
    assert nts and exs
    assert max(nts) < min(exs)
    assert nts == list(range(min(nts), max(nts) + 1))  # contiguous


def test_a_ground_mounted_export_says_GE_1():
    """A pre-existing writer bug this arc surfaced, fixed here because the
    nec2c gate below cannot pass without it. The writer emitted `GE 0`
    unconditionally; GE 1 is what tells NEC a wire END at z = 0 is CONNECTED
    to the ground plane. With GE 0 that end is silently insulated and the deck
    models a different antenna -- on this one, nec2c reports
    54.8 - 2961j instead of 36.5 - 19.2j."""
    assert "GE 1" in _export(NEC2).splitlines()
    # A free-space design still says GE 0.
    cls = builder_from_file(str(NEC2))
    assert "GE 0" in export_nec(cls(), ground="free", include_rp=False).splitlines()


@needs_nec2c
def test_a_real_nec2_kernel_forces_the_currents_we_asked_for(tmp_path):
    """The independent gate: nec2c is a different implementation, and it must
    both ACCEPT these cards and deliver the requested currents. The CURRENT
    column of its network block is the drive the gyrators forced."""
    inp, out = tmp_path / "g.nec", tmp_path / "g.out"
    inp.write_text(_export(NEC2))
    r = subprocess.run(
        ["nec2c", "-i", str(inp), "-o", str(out)], capture_output=True, timeout=300
    )
    assert r.returncode == 0, r.stderr.decode()[:400]
    lines = out.read_text(errors="replace").splitlines()
    i = next(
        k
        for k, ln in enumerate(lines)
        if "STRUCTURE EXCITATION DATA AT NETWORK CONNECTION POINTS" in ln
    )
    rows = []
    for ln in lines[i + 1 : i + 20]:
        nums = re.findall(r"[-+]?\d+\.\d+E[-+]\d+", ln)
        toks = ln.split()
        if len(nums) >= 8 and len(toks) >= 10:
            rows.append(
                (
                    complex(float(nums[0]), float(nums[1])),  # VOLTAGE
                    complex(float(nums[2]), float(nums[3])),  # CURRENT
                )
            )
    assert len(rows) >= 2
    # nec2c prints five significant figures (1.4142E+00), so the tolerance is
    # its PRINT precision, not the solve's.
    for (_v, i_got), i_want in zip(rows[:2], EX6_CURRENTS, strict=True):
        assert i_got == pytest.approx(i_want, abs=2e-5)


@needs_nec2c
def test_a_real_nec2_kernel_lands_on_the_oracle(tmp_path):
    """And the impedance it reports is Dan's antenna. Read as V/I_requested:
    with a gyrator the ANTENNA INPUT PARAMETERS block reports the PHANTOM
    port, and the true port voltage is the network row's VOLTAGE column
    (`gyrator_reference`'s readout rule). Tolerance is loose on purpose --
    nec2c is a different kernel and a different basis from the NEC-4.2 twin,
    so agreeing to a percent is the claim, not agreeing to the digit."""
    inp, out = tmp_path / "g.nec", tmp_path / "g.out"
    inp.write_text(_export(NEC2))
    subprocess.run(
        ["nec2c", "-i", str(inp), "-o", str(out)], capture_output=True, timeout=300
    )
    lines = out.read_text(errors="replace").splitlines()
    i = next(
        k
        for k, ln in enumerate(lines)
        if "STRUCTURE EXCITATION DATA AT NETWORK CONNECTION POINTS" in ln
    )
    volts = []
    for ln in lines[i + 1 : i + 20]:
        nums = re.findall(r"[-+]?\d+\.\d+E[-+]\d+", ln)
        if len(nums) >= 8 and len(ln.split()) >= 10:
            volts.append(complex(float(nums[0]), float(nums[1])))
    # np.all([]) is True, so an empty parse would pass this silently.
    assert len(volts) >= 2, f"parsed no network rows from nec2c: {volts!r}"
    z = np.array([v / i_req for v, i_req in zip(volts[:2], EX6_CURRENTS, strict=True)])
    assert z.shape == (2,)
    assert np.all(np.abs(z - ORACLE) / np.abs(ORACLE) < 0.01)


def _drive_map(deck_text, n_seg_by_tag):
    """``{target absolute segment: source voltage}`` for a gyrator deck.

    Pairs each ``NT`` with the ``EX 0`` on the SAME phantom node, so a deck is
    compared by what it DRIVES and where, not by how it happened to lay its
    phantom out. EZNEC parks two nodes on one 4-segment wire and uses segments
    2 and 3; we use a 2-segment wire and segments 1 and 2. Same drives.
    """
    base, acc = {}, 0
    for tag in sorted(n_seg_by_tag):
        base[tag] = acc
        acc += n_seg_by_tag[tag]

    def absolute(tag, seg):
        # NEC's tag-0 convention: tag 0 means seg is already absolute.
        return seg if tag == 0 else base[tag] + seg

    nts, exs = {}, {}
    for ln in deck_text.replace(",", " ").splitlines():
        f = ln.split()
        if f[:1] == ["NT"]:
            nts[(int(f[1]), int(f[2]))] = absolute(int(f[3]), int(f[4]))
        elif f[:2] == ["EX", "0"]:
            exs[(int(f[2]), int(f[3]))] = complex(float(f[5]), float(f[6]))
    return {target: exs[node] for node, target in nts.items() if node in exs}


def test_the_drive_matches_the_one_EZNEC_ITSELF_WROTE():
    """The sign gate, and the only one that cannot cancel.

    A round trip CANNOT catch an inversion: if the writer inverted and the
    reader inverted back, it would still be an identity — which is exactly the
    shape of the AK#1595 defect, where a test "verified" the pair by dividing
    one side by the other. So the sign is pinned against an EXTERNAL
    authority: EZNEC's own `Cardioidmodnec2.nec`, which it wrote for this
    antenna without our involvement.

    Compared as {what it drives: with what}, so the phantom's own layout is
    free to differ. A flipped `Y12`, a conjugated phasor, or `V = -j*I` in
    place of `j*I` all move these numbers and none of them can hide.
    """
    n_seg = {1: 6, 2: 6}  # the two real wires, in tag order
    theirs = _drive_map(NEC2.read_text(), {**n_seg, 3: 4})
    ours = _drive_map(_export(NEC2), {**n_seg, 3: 2})
    assert set(ours) == set(theirs) == {1, 7}
    for target in sorted(theirs):
        assert ours[target] == pytest.approx(theirs[target], rel=1e-9)
    # And those drives are j * the EX 6 currents the NEC-4.2 twin asks for,
    # stated absolutely so "both agree" cannot be agreement on the wrong sign.
    assert ours[1] == pytest.approx(1j * EX6_CURRENTS[0], rel=1e-6)
    assert ours[7] == pytest.approx(1j * EX6_CURRENTS[1], rel=1e-6)


def test_the_nec42_deck_exports_the_same_way():
    """The other dialect of the same drive: `EX 6` imports to the same
    DrivenCurrent (AK#1600), so it writes to the same gyrator cards."""
    a = [ln for ln in _export(NEC2).splitlines() if ln.startswith("NT ")]
    b = [ln for ln in _export(NEC4).splitlines() if ln.startswith("NT ")]
    assert a == b


def test_a_genuinely_inexpressible_network_still_refuses():
    """The relaxation is narrow: only a network whose SOLE reducer reason is
    its current sources is written. A deck with TL cards has no native card on
    this path and must still refuse, in the dialect's name (AK#1389)."""
    tl_deck = (
        Path(__file__).parent.parent
        / "momwire/tests/fixtures/eznec/decks/0001_4-square-array-w-feed-system.nec"
    )
    if not tl_deck.exists():
        pytest.skip("momwire submodule corpus not checked out")
    cls = builder_from_file(str(tl_deck))
    eng = PyNECEngine(cls(), ground=cls.file_ground)
    assert "transmission-line" in eng._reducer_reasons()
    with pytest.raises(NotImplementedError, match="cannot express TL"):
        export_nec(cls(), ground=cls.file_ground, include_rp=False)


def test_the_writer_only_engine_refuses_to_solve():
    """`_export_current_sources` makes the native path accept a DrivenCurrent,
    which leaves the baked context with NO excitation for that port. Solving
    it would answer for an undriven antenna and look healthy doing it, so it
    is refused rather than returned."""
    cls = builder_from_file(str(NEC2))
    eng = PyNECEngine(cls(), ground=cls.file_ground, _export_current_sources=True)
    assert eng.current_sources  # it did record them
    with pytest.raises(NotImplementedError, match="nec_export"):
        eng.impedance()


def test_the_reasons_split_is_what_makes_the_distinction():
    """The relaxation keys on WHICH features reduce, not whether any do."""
    cls = builder_from_file(str(NEC2))
    eng = PyNECEngine(cls(), ground=cls.file_ground)
    assert eng._reducer_reasons() == frozenset({"current-source"})
    assert eng._network_uses_reducer() is True


def test_a_deck_with_no_current_source_is_unchanged(tmp_path):
    """No gyrator machinery appears on an ordinary voltage-driven deck."""
    src = tmp_path / "v.nec"
    src.write_text(
        "CM plain\nCE\nGW 1,11,0.,0.,0.,0.,0.,5.,.001\nGE 0\n"
        "FR 0,1,0,0,14.\nEX 0,1,6,0,1.,0.\nEN\n"
    )
    deck = _export(src)
    assert not [ln for ln in deck.splitlines() if ln.startswith("NT ")]
    assert len([ln for ln in deck.splitlines() if ln.startswith("GW ")]) == 1
