"""EZNEC's repeated load probe at one node (momwire#1787, AK#2087).

A model with two lumped loads at ONE node (two ``LD 1`` parallel-LC traps)
makes EZNEC write one ``EX 0,tag,node,0,1.E-10,0.`` probe per load, so its
NEC-5 export carries two identical probes at one address beside the ``EX 4``
drive. Licensed NEC-5 solves that as ONE passive probe: the drive row equals
the one-probe deck's to every printed digit. momwire 0.85.0's seam serves
exactly that shape and refuses every other repeat; the importer follows the
same rule, no wider.

The deck is momwire's ``tests/fixtures/eznec_load_probes_1110/
M_0195_two_loads_one_node.nec`` (capture 0195 with a second trap at 1,8),
inline because the fixture is newer than the recorded submodule pointer.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs.cli import deck_extended_kernel_flag, make_engine_factory
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec

DRIVE = "EX 4,1,6,0,1.414214,0."
PROBE = "EX 0,1,8,0,1.E-10,0."

TWO_PROBES = f"""\
CM Dipole in free space, two parallel-LC traps at one node (momwire#1787)
CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.
CM ! 1.E-10 volt sources for recording currents at load locations.
CE
GW 1,11,0.,-.25,0.,0.,.25,0.,.0005
GE 0,-1
LD 1,1,8,0,0.,.0000001,5.E-12
LD 1,1,8,0,0.,.0000002,3.E-12
FR 0,1,0,0,299.7925
GN -1
{DRIVE}
{PROBE}
{PROBE}
PQ 0
RP 0,1,361,1000,90.,0.,0.,1.,0.
EN
"""
ONE_PROBE = TWO_PROBES.replace(f"{PROBE}\n{PROBE}\n", f"{PROBE}\n")

# Licensed NEC-5's drive row for the two-probe deck (the fixture's .out):
# 5.9041E+01 -1.6374E+02, the one-probe deck's digits.
NEC5 = 59.041 - 163.74j

# Where AK refuses two EX cards at one address: the port planners at import
# (`_port_plan` for a segment, `_vertex_claims` for a knot) name the card; a
# knot on the positioned-port path reaches the wire builder as two ports at one
# point (AK#1469).
REFUSAL = "with more than one EX card|sit at the same point"


def _parse(text: str):
    return parse_nec(text, name="probes.nec", network=True)


def _z(tmp_path, text: str, basis: str) -> complex:
    """The ``@file.nec`` route, as ``antennaknobs analyze @deck.nec`` takes it."""
    path = tmp_path / "deck.nec"
    path.write_text(text)
    cls = builder_from_file(str(path))
    factory = make_engine_factory(
        f"momwire:{basis}",
        getattr(cls, "file_ground", None),
        deck_extended_kernel=deck_extended_kernel_flag(cls),
    )
    return complex(np.atleast_1d(np.asarray(factory(cls()).impedance()))[0])


def test_two_probes_at_one_node_import_as_the_one_probe_deck():
    two, one = _parse(TWO_PROBES), _parse(ONE_PROBE)
    assert two.feeds == one.feeds
    assert len(two.feeds) == 2
    assert two.network() == one.network()


@pytest.mark.parametrize("basis", ["razor-2p", "bspline"])
def test_two_probes_give_the_one_probe_feed_impedance(tmp_path, basis):
    z_two = _z(tmp_path, TWO_PROBES, basis)
    z_one = _z(tmp_path, ONE_PROBE, basis)
    assert z_two == pytest.approx(z_one, rel=1e-12)
    if basis == "razor-2p":
        # NEC-5's own basis: the licensed engine's printed digits.
        assert abs(z_two - NEC5) < 0.01, z_two


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # Two set currents on one gap.
        (DRIVE, f"{DRIVE}\n{DRIVE}"),
        # A probe at the EX 4's own address (loaded there, so only the drive
        # beside it is what keeps it from being a probe repeat).
        (
            f"{DRIVE}\n",
            f"{DRIVE}\nEX 0,1,6,0,1.E-10,0.\nLD 4,1,6,0,10.,0.\n",
        ),
        # A real generator repeated at the loaded node, not a probe.
        (f"{PROBE}\n{PROBE}", "EX 0,1,8,0,1.,0.\nEX 0,1,8,0,1.,0."),
        # A probe beside a generator at one address.
        (f"{PROBE}\n{PROBE}", f"{PROBE}\nEX 0,1,8,0,1.,0."),
    ],
    ids=["doubled-ex4", "probe-at-ex4", "doubled-generator", "probe-plus-generator"],
)
def test_any_other_repeated_address_still_refuses(tmp_path, old, new):
    assert old in TWO_PROBES
    with pytest.raises(ValueError, match=REFUSAL):
        _z(tmp_path, TWO_PROBES.replace(old, new), "razor-2p")


def test_repeated_probes_at_an_unloaded_node_still_refuse(tmp_path):
    """No load under the probes: they read nothing back, so not this shape."""
    text = TWO_PROBES.replace("EX 0,1,8,0,", "EX 0,1,9,0,")
    with pytest.raises(ValueError, match=REFUSAL):
        _z(tmp_path, text, "razor-2p")


def test_repeated_probes_without_a_non_ex0_drive_still_refuse(tmp_path):
    """Not a mixed deck: an EX 0 drive in place of the EX 4."""
    text = TWO_PROBES.replace(DRIVE, "EX 0,1,6,0,1.,0.")
    with pytest.raises(ValueError, match=REFUSAL):
        _z(tmp_path, text, "razor-2p")
