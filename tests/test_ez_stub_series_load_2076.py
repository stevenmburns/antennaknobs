"""A stub and a series load on the same real segment of an ``.ez`` (AK#2076).

NEC's reading, which EZNEC's exports write: the series load is part of the
wire, and the stub hangs across the segment's gap, in parallel with a source
there and in series with the wire current elsewhere. The ``.ez`` import used
to write the stub as a placeholder load, which put the series load between
the gap and the stub instead (22-73 % off); a stub on a real wire is now a
one-port NT to the spare circuit wire, as EZNEC's exports write it.
"""

from __future__ import annotations

import math

import pytest

from tests.test_ez_import_1958 import DIPOLE, _open, _z, engine_block, ez_file

NEC5 = engine_block(8, "Ext NEC-5")
F_MHZ, LENGTH, VF, Z0 = 14.2, 2.0, 0.8, 50.0
CODE = {"short": -1, "open": -2}

# Licensed NEC-4.2 as a black box (2026-10-26): the same dipole as a deck,
# EX 0 at segment 11, LD 4 (20 ohm) and a one-port NT of the stub's
# admittance on the stub's segment (11 = 50 %, 16 = 75 %), sinusoidal basis.
NEC42 = {
    ("short", 50.0): 17.053 + 36.187j,
    ("short", 75.0): 88.074 + 33.609j,
    ("open", 50.0): 25.332 - 41.660j,
    ("open", 75.0): 80.675 - 22.170j,
}


def _zl(stub: str) -> complex:
    bl = 2 * math.pi * F_MHZ * 1e6 / (VF * 299_792_458.0) * LENGTH
    return 1j * Z0 * math.tan(bl) if stub == "short" else -1j * Z0 / math.tan(bl)


def _raw(stub, pct, series=None, blocks=()):
    loads = () if series is None else ({"wire": 1, "pct": pct, "z": series},)
    return ez_file(
        DIPOLE,
        lines=((1, pct, CODE[stub], 0.0, Z0, LENGTH, VF),),
        loads=loads,
        blocks=list(blocks),
    )


@pytest.mark.parametrize("blocks", [(), (NEC5,)], ids=["nec2", "nec5"])
@pytest.mark.parametrize("stub", ["short", "open"])
def test_off_the_feed_the_stub_and_the_load_add_in_the_wire(stub, blocks):
    both = _z(_open(_raw(stub, 75.0, (20.0, 0.0), blocks)))
    zl = _zl(stub)
    series = {"wire": 1, "pct": 75.0, "z": (zl.real + 20.0, zl.imag)}
    alone = _z(_open(ez_file(DIPOLE, loads=(series,), blocks=list(blocks))))
    assert both == pytest.approx(alone, rel=1e-6)


@pytest.mark.parametrize("blocks", [(), (NEC5,)], ids=["nec2", "nec5"])
@pytest.mark.parametrize("stub", ["short", "open"])
def test_at_the_feed_the_stub_shunts_the_source_and_the_load_is_in_the_wire(
    stub, blocks
):
    """The source sees the stub in parallel with the wire, the series load
    inside the wire: 1/(1/(Z_wire + 20) + 1/Z_stub)."""
    both = _z(_open(_raw(stub, 50.0, (20.0, 0.0), blocks)))
    s = {"wire": 1, "pct": 50.0, "z": (20.0, 0.0)}
    z_wire = _z(_open(ez_file(DIPOLE, loads=(s,), blocks=list(blocks))))
    assert both == pytest.approx(1 / (1 / z_wire + 1 / _zl(stub)), rel=1e-9)


@pytest.mark.parametrize(("stub", "pct"), sorted(NEC42))
def test_the_nec2_reading_agrees_with_nec42(stub, pct):
    """Within the bs2-against-sinusoidal basis spread on this mesh (1.3e-3
    to 4.4e-3 measured; the pre-fix import was 22 % to 73 % off)."""
    z = _z(_open(_raw(stub, pct, (20.0, 0.0))))
    ref = NEC42[(stub, pct)]
    assert abs(z - ref) <= 6e-3 * abs(ref), (z, ref)


def test_a_stub_on_a_real_wire_is_a_one_port_nt_to_the_spare_wire():
    from antennaknobs.ez_import import read_ez

    imp = read_ez(_raw("short", 75.0))
    (nt,) = [ln.split() for ln in imp.nec_text.splitlines() if ln.startswith("NT ")]
    assert nt[1:5] == ["1", "16", "2", "1"]
    assert [float(v) for v in nt[7:]] == [0.0, 0.0, 0.0, 0.0]
    assert not any(ln.startswith("LD 4") for ln in imp.nec_text.splitlines())
