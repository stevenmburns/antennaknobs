"""`antennaknobs export --dialect nec5` writes the catalog's network designs
as ONE NEC-5 deck each, and refuses only what NEC-5 cannot carry, by name.

The 11-15 census exported every catalog design as a NEC-5 deck: 51 of them
(102 design x ground rows) refused with one blanket sentence about
"TL/virtual-driver networks". The export now writes them as the station
deck (`nec5_station.station_deck`) at the one frequency the command writes
anyway: lines as ``TL``, two-ports as ``NT``, virtual nodes as pinned
phantom knots, and a network with a part no card spells (an
autotransformer, a floating balun or gap, a balanced line, a dead short)
reduced onto its terminals as ``NT`` cards.

THE ACCEPTANCE TEST is that momwire's own NEC-5 launchers serve the deck,
and that the impedance they print is the one antennaknobs' NEC-5 route
computes on the SAME launcher: `NEC5Engine` reducing the network over one
deck per port. Same field solver, same mesh, same knots, so the two answers
differ only by what the deck and the route each round. The bound is
derived, not chosen, from three measured parts:

* the pinned knots' residual (`StationDeck.tolerance`, measured per knot);
* the deck printout's own rounding, half a unit in the fifth figure of
  each part of the impedance it prints;
* the route's rounding: its antenna Y is read off five-figure printouts,
  and the network carries that rounding into the composite. Bounded first
  order by perturbing each entry of Y by its own half unit, one part at a
  time, and summing the moves.

What it is NOT compared with is `MomwireEngine` of the same basis. That
engine meshes with odd parity and feeds a delta gap mid-segment; the NEC-5
route meshes with even parity, splits the fed wire at the feed and sources
the knot, so the two differ by 1e-3 to 1e-2 on designs with no network at
all (a plain inverted-V dipole: 2.4e-3 on bs2). That is the dialect,
not the deck.
"""

from __future__ import annotations

import math
import pathlib
import shutil
import subprocess
import sys
import tempfile
import warnings

import numpy as np
import pytest

import antennaknobs
from antennaknobs.cli import get_builder, list_builtin_designs, list_variants
from antennaknobs.cli import parse_ground
from antennaknobs.engines.momwire import C_LIGHT_MHZ_M
from antennaknobs.engines.nec5 import NEC5Engine, _network_needs_reducer
from antennaknobs.nec5_export import export_nec5
from antennaknobs.nec5_station import _driven_z, station_deck

LAUNCHERS = ("bs2", "razor2p")
GROUNDS = ("free", "finite")

# The sentence every one of these designs used to get. No design may get it
# from the command's path again.
BLANKET = "NEC-5 export of TL/virtual-driver networks"

# What the catalog still refuses, and the words that say why. Each is a
# limit of NEC-5 itself or of this geometry, and none is a network the
# writer could not spell. (spec, ground or None for both) -> phrase.
REFUSED = {
    ("beams.yagi_endport", None): "PortAtEnd",
    ("dipoles.invvee_endport", None): "PortAtEnd",
    ("dipoles.invvee_endport:classic_edz", None): "PortAtEnd",
    ("dipoles.invvee_endport:dipole", None): "PortAtEnd",
    ("dipoles.invvee_endport:three_halves", None): "PortAtEnd",
    ("verticals.collinear_stub:bl_stub", None): "PortAtEnd",
    ("verticals.collinear_stub:bl_stub_diffonly", None): "PortAtEnd",
    ("wire.sterba_bl", None): "distributed",
    ("wire.sterba_tl", None): "distributed",
    ("wire.zepp", None): "distributed",
    ("verticals.buried_radial_vertical:bundle", None): "geometrically coincident",
    ("verticals.buried_radial_vertical:detached", "finite"): "ends ON the ground",
}


# A deck the export writes and momwire's launchers refuse, by name. Not a
# network: the jacketed radials lie 1.05 mm above the soil, and a NEC-5 deck
# carries a jacket only as the equivalent bare radius (`JACKET_COMMENT_CARDS`),
# so the launcher meets h/a = 1.23 under its bare-wire floor of 2
# (momwire#865) on bs2; razor2p serves it. AK's own NEC-5 route on the
# bs2 launcher refuses the same deck the same way.
UNSERVED = {
    ("verticals.buried_radial_vertical:surface", "finite", "bs2"): ("validity floor"),
}


def _launcher(basis):
    exe = pathlib.Path(sys.executable).parent / f"momwire-nec5-{basis}"
    return str(exe) if exe.is_file() else shutil.which(f"momwire-nec5-{basis}")


def _specs():
    out = []
    for name in list_builtin_designs():
        out.append(name)
        try:
            cls = get_builder(name)
        except Exception:  # noqa: BLE001 — collection must not die on one design
            continue
        out += [f"{name}:{v}" for v in list_variants(cls) if v != "default"]
    return out


def _serve(exe, text):
    """The launcher's printed driving-point impedances, or the reason it
    printed none."""
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td)
        (p / "m.nec").write_text(text)
        run = subprocess.run(
            [exe],
            input="m.nec\nm.out\n\n",
            cwd=td,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        out = p / "m.out"
        printout = out.read_text(errors="replace") if out.exists() else ""
    if "ANTENNA INPUT PARAMETERS" not in printout:
        return None, (run.stdout + run.stderr + printout)[-2000:]
    rows = NEC5Engine._parse_input_parameters(printout)[0]
    return [complex(z) for *_x, z in rows], ""


def _half(x):
    return 0.0 if x == 0 else 0.5 * 10 ** (math.floor(math.log10(abs(x))) - 4)


def _printout_rounding(z):
    """Half a unit in the fifth significant figure of each part, over |Z|."""
    return math.hypot(_half(z.real), _half(z.imag)) / abs(z)


def _y_rounding(sd, builder):
    """First-order bound, relative, on how far the route's five-figure Y
    moves its composite impedance: each part of each entry moved by its
    own half unit, the moves summed."""
    c = float(builder.c_light_mhz_m)
    wl = c / sd.freq_mhz
    cl = None if c == C_LIGHT_MHZ_M else c
    y, names = sd.antenna_y, list(sd.antenna_ports)

    def z(yy):
        return complex(_driven_z(sd.network, yy, names, wl, cl)[0])

    z0 = z(y)
    total = 0.0
    for i in range(y.shape[0]):
        for j in range(y.shape[1]):
            for step in (_half(y[i, j].real), 1j * _half(y[i, j].imag)):
                if step:
                    yy = y.copy()
                    yy[i, j] += step
                    total += abs(z(yy) - z0)
    return total / abs(z0)


def _expected_refusal(spec, ground):
    return REFUSED.get((spec, ground)) or REFUSED.get((spec, None))


def _export(spec, ground):
    b = get_builder(spec)()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        text = export_nec5(
            b,
            ground=parse_ground(ground),
            design=spec,
            rung="default",
            ground_name=ground,
            networks=True,
        )
    return b, text


def _check_design(spec, ground):
    """The whole contract for one design on one ground."""
    want = _expected_refusal(spec, ground)
    try:
        b, text = _export(spec, ground)
    except (NotImplementedError, ValueError) as exc:
        msg = str(exc)
        assert BLANKET not in msg, msg
        assert want is not None, f"{spec} on {ground} refused unexpectedly: {msg}"
        assert want in msg, msg
        return
    assert want is None, f"{spec} on {ground} exported; expected a refusal ({want})"
    on_route = _network_needs_reducer(b.build_network())
    gs = parse_ground(ground)
    for basis in LAUNCHERS:
        exe = _launcher(basis)
        zs, why = _serve(exe, text)
        unserved = UNSERVED.get((spec, ground, basis))
        if unserved is not None:
            assert not zs and unserved in why, (spec, ground, basis, zs, why)
            continue
        assert zs, f"momwire-nec5-{basis} did not serve {spec}: {why}"
        assert all(np.isfinite(z) for z in zs), zs
        if not on_route:
            # The deck IS NEC5Engine's own deck, so the route solves it: no
            # second answer to compare with.
            continue
        # The same network measured on THIS launcher's Y (a tuner tunes on
        # it, as the route does), served, against the route's composite.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            eng = NEC5Engine(b, ground=gs, nec5_exe=exe, timeout=1800)
            sd = station_deck(b, ground=gs, engine=eng, title=spec)
        zs, why = _serve(exe, sd.text)
        assert zs, f"momwire-nec5-{basis} did not serve {spec}'s measured deck: {why}"
        z = zs[0]
        tol = sd.tolerance + _printout_rounding(z) + _y_rounding(sd, b)
        rel = abs(z - sd.z_composite) / abs(sd.z_composite)
        assert rel <= tol, (spec, ground, basis, z, sd.z_composite, rel, tol)


@pytest.mark.antenna_computation_check
@pytest.mark.skipif(
    not all(_launcher(b) for b in LAUNCHERS), reason="momwire NEC-5 launchers"
)
@pytest.mark.parametrize("ground", GROUNDS)
@pytest.mark.parametrize("spec", _specs())
def test_every_catalog_design_exports_or_refuses_by_name(spec, ground):
    _check_design(spec, ground)


# --- the per-PR lane: one design per spelling, each a few seconds -------------


@pytest.mark.skipif(
    not all(_launcher(b) for b in LAUNCHERS), reason="momwire NEC-5 launchers"
)
@pytest.mark.parametrize(
    "spec",
    [
        # every line a TL card
        "broadband.lpda",
        # an autotransformer, reduced onto its terminals
        "wire.efhw_autotransformer",
        # a floating gap, a floating balun and a lossy balanced line, reduced
        "wire.doublet_remote_tuner",
        # a shorted stub: a dead short to ground, reduced
        "verticals.stub_matched_vertical",
    ],
)
def test_a_network_design_exports_a_deck_the_launchers_serve(spec):
    _check_design(spec, "free")


def test_a_self_tuning_tuner_is_written_as_the_parts_it_tuned_to():
    b, text = _export("wire.doublet_remote_tuner:band_loss", "free")
    assert "CM the self-tuning tuner is written as the parts it tuned to" in text
    assert "REDUCED" in text


def test_the_command_writes_a_network_design(tmp_path):
    """The command's deck is `export_nec5`'s with ``networks=True``, byte for
    byte: one writer behind both."""
    out = tmp_path / "lpda.nec"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        antennaknobs.cli(
            [
                "export",
                "--builder",
                "broadband.lpda",
                "--dialect",
                "nec5",
                "--ground",
                "free",
                "--out",
                str(out),
            ]
        )
        expected = export_nec5(
            get_builder("broadband.lpda")(),
            ground=None,
            design="broadband.lpda",
            rung="default",
            ground_name="free",
            note="written by `antennaknobs export --dialect nec5`",
            networks=True,
        )
    text = out.read_text(encoding="utf-8")
    assert text == expected
    assert "\nTL " in text and "\nEX 0 " in text


@pytest.mark.parametrize(
    ("spec", "phrase"),
    [("beams.yagi_endport", "PortAtEnd"), ("wire.zepp", "distributed")],
)
def test_what_nec5_cannot_carry_is_refused_by_name(spec, phrase):
    with pytest.raises(NotImplementedError) as exc:
        _export(spec, "free")
    assert phrase in str(exc.value)
    assert BLANKET not in str(exc.value)


def test_the_download_keeps_its_refusal():
    """The app's Download is the catalog's file (#1389), which holds at every
    frequency, so without ``networks=True`` the refusal stands."""
    b = get_builder("broadband.lpda")()
    with pytest.raises(NotImplementedError, match=BLANKET):
        export_nec5(b, design="broadband.lpda", rung="default", ground_name="free")
