"""Tests for antennaknobs.nec_export.

Structural tests run everywhere. The numerical cross-check runs the exported
deck through the `nec2c` CLI (an independent NEC2 implementation) and compares
impedance to PyNECEngine; it is skipped when nec2c is not installed.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("PyNEC")

from antennaknobs import resolve_variant_params  # noqa: E402
from antennaknobs.designs.dipoles.invvee import Builder as InvVee  # noqa: E402
from antennaknobs.designs.beams.yagi import Builder as Yagi  # noqa: E402
from antennaknobs.engines import PyNECEngine  # noqa: E402
from antennaknobs.nec_export import export_nec  # noqa: E402

# InvVee's `dipole` variant is a partial overlay on default_params; resolve it
# to a complete param set before constructing the Builder directly.
_DIPOLE = resolve_variant_params(InvVee, "dipole")

HAVE_NEC2C = shutil.which("nec2c") is not None


def test_export_basic_structure():
    deck = export_nec(InvVee(_DIPOLE), ground="free", include_rp=False)
    lines = deck.splitlines()
    assert lines[0].startswith("CM ")
    assert "CE" in lines
    assert any(ln.startswith("GW ") for ln in lines)
    assert "GE 0" in lines
    assert any(ln.startswith("EX 0 ") for ln in lines)
    assert any(ln.startswith("FR 0 ") for ln in lines)
    # no pattern requested -> an XQ must still trigger the solve, not RP
    assert "XQ 0" in lines
    assert not any(ln.startswith("RP ") for ln in lines)
    assert lines[-1] == "EN"


def test_export_rp_card_when_pattern_requested():
    deck = export_nec(InvVee(_DIPOLE), include_rp=True)
    lines = deck.splitlines()
    assert any(ln.startswith("RP ") for ln in lines)
    assert "XQ 0" not in lines  # RP triggers the solve instead


def test_export_one_gw_per_wire():
    b = Yagi()
    deck = export_nec(b, ground="free")
    n_gw = sum(1 for ln in deck.splitlines() if ln.startswith("GW "))
    assert n_gw == len(PyNECEngine(b, ground="free").tups)


def test_export_ground_cards():
    assert "GN 1" in export_nec(InvVee(_DIPOLE), ground="pec")
    assert "GN 0" in export_nec(InvVee(_DIPOLE), ground=("finite", 10.0, 0.002))
    # free space emits no GN card
    assert "GN " not in export_nec(InvVee(_DIPOLE), ground="free")


def test_export_reducer_network_raises():
    """build_network() TL/virtual-driver designs go through the multiport-Y
    reducer and have no faithful native-NEC deck."""
    from antennaknobs.designs.arrays.delta_looparray_network import (
        Builder as NetTLBuilder,
    )

    with pytest.raises(NotImplementedError):
        export_nec(NetTLBuilder())


def test_export_legacy_tls_emits_tl_cards():
    """The legacy build_tls() path maps to native NEC TL cards."""
    from antennaknobs.designs.arrays.delta_looparray_with_tls import (
        Builder as TLBuilder,
    )

    deck = export_nec(TLBuilder(), ground="free")
    assert any(ln.startswith("TL ") for ln in deck.splitlines())


def _nec2c_impedances(deck):
    with tempfile.TemporaryDirectory() as d:
        nec = Path(d) / "deck.nec"
        out = Path(d) / "deck.out"
        nec.write_text(deck)
        subprocess.run(
            ["nec2c", "-i", str(nec), "-o", str(out)], check=True, capture_output=True
        )
        text = out.read_text()
    zs = []
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if "ANTENNA INPUT PARAMETERS" in ln:
            j = i + 3
            while j < len(lines) and lines[j].strip():
                toks = lines[j].split()
                if len(toks) >= 8:
                    zs.append(complex(float(toks[6]), float(toks[7])))
                j += 1
            break
    return zs


@pytest.mark.skipif(not HAVE_NEC2C, reason="nec2c CLI not installed")
@pytest.mark.parametrize(
    "builder,ground",
    [
        (InvVee(_DIPOLE), "free"),
        (InvVee(_DIPOLE), "pec"),
        (InvVee(_DIPOLE), ("finite", 10.0, 0.002)),
        (Yagi(), "free"),
    ],
)
def test_export_matches_nec2c(builder, ground):
    """The exported deck, run through nec2c, reproduces PyNECEngine impedance."""
    deck = export_nec(builder, ground=ground, include_rp=False)
    z_nec2c = _nec2c_impedances(deck)
    z_engine = PyNECEngine(builder, ground=ground).impedance()
    assert len(z_nec2c) >= len(z_engine)
    for k, ze in enumerate(z_engine):
        zc = z_nec2c[k]
        # nec2c (C) vs nec2++ (PyNEC) agree to a few mΩ; allow 0.1 Ω abs.
        assert abs(ze - zc) < 0.1, f"feed {k}: engine={ze} nec2c={zc}"
