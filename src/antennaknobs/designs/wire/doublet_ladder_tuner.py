"""88 ft doublet + 100 ft of 600 Ω open-wire line + lossy T-network tuner —
the "non-resonant wire and a matchbox" station, modelled from the rig
(issue #300).

The other half of the comparison with `dipoles.invvee_coax_station`: instead
of a resonant antenna on 50 Ω coax, a deliberately non-resonant flat doublet
(88 ft ≈ 26.8 m total — 0.25·λ(7.1 MHz)·length_factor 1.26944) feeds 100 ft of
`openwire-600` ladder line (issue #297) into a T-network — series C, shunt L,
series C, the `inverted_l_tmatch` topology — whose inductor has a finite
`coil_q` (issue #298). The source sits at the virtual **rig** node, so
impedance, SWR, gain, and the power budget (issue #299) are all referenced to
the transmitter.

Stock values match ~50 Ω at 7.1 MHz (40 m) over the workbench-default
finite-fast ground (εr=10, σ=0.002): the readout shows SWR ≈ 1 while the
budget itemizes where the watts actually go — with Q = 200 about 3.5 % in
the line and 4 % in the tuner coil, ~92 % accepted by the antenna. Retune
for 80 m
(3.8 MHz: C1 ≈ 38.8 pF, L ≈ 32.6 µH, C2 stays at 500 pF) and the same
doublet is electrically short: the line's SWR loss climbs to ~17 % and the
coil to ~15 % — a third of the power never leaves the shack — the honest
cost of working a too-short wire. The classic folklore —
"open-wire line shrugs off SWR, the tuner coil is where multiband
flexibility is paid for" — falls out of the circuit solve as numbers.

T-network caveats inherited from `inverted_l_tmatch`: T-match solutions are
not unique — bigger capacitors with a smaller L generally mean less
circulating current and lower coil loss. Both capacitor knobs run
25–600 pF, the span a real matchbox's variable caps cover, so every tune
here is one you could actually dial: the degenerate 0 pF endpoint (a series
open — Z = ∞) is out of reach, and past ~300 pF the coil-loss curve is
nearly flat, so the practical ceiling costs only tenths of a percent.
"""

from types import MappingProxyType

from antennaknobs.network import (
    TL,
    Driven,
    Instance,
    Network,
    PortOnWire,
    PortVirtual,
    as_wire,
)
from antennaknobs.station import t_network_tuner
from antennaknobs.designs.dipoles.invvee import Builder as InvVee


class Builder(InvVee):
    default_params = MappingProxyType(
        {
            **InvVee.default_params,
            # 88 ft flat doublet: 0.25·λ(7.1 MHz)·1.26944 = 13.40 m per
            # side. design_freq matches the stock operating band (40 m) so
            # the workbench band row loads — and band-hops — this station
            # without silently resizing the wire; the 88 ft length lives in
            # length_factor. (An earlier expression put design_freq at
            # 5.593 MHz with length_factor 1.0 — same geometry, but the
            # band snap on load clobbered it to the 40 m default.)
            "design_freq": 7.1,
            "freq": 7.1,
            "angle_deg": 0.0,
            "length_factor": 1.26944,
            "base": 10.0,
            # Feedline: 100 ft of 600 Ω open-wire line.
            "line_len_m": 30.48,
            # T-network, tuned for ~50 Ω at 7.1 MHz on the stock doublet
            # over the workbench-default finite-fast ground (εr=10,
            # σ=0.002) — the reference the workbench actually shows —
            # with both capacitors inside a real matchbox's range
            # (≤ 600 pF; see the ui ranges below).
            # (See the 80 m retune in the module docstring.)
            "series_c1_pF": 81.2,
            "shunt_l_uH": 4.218,
            "series_c2_pF": 500.0,
            # Tuner coil Q (issue #298). Defaults LOSSY — the point of this
            # design is seeing the tuner cost; set 0 for the ideal coil.
            "coil_q": 200.0,
            "ui_params": MappingProxyType(
                {
                    **InvVee.default_params["ui_params"],
                    "target_z0": 50.0,
                    "angle_deg": {"hidden": True},
                    # 100 ft of line rotates the sweep trace around the
                    # Smith chart several times over the default ±20/25 %
                    # window — lock the sweep to the band being measured.
                    "sweep_policy": {"anchor": "meas_freq", "band_locked": True},
                    # The 88 ft default (1.26944) sits above the inherited
                    # half-wave window (0.8–1.25).
                    "length_factor": {"min": 0.9, "max": 1.6},
                    "line_len_m": {"min": 3.0, "max": 100.0, "unit": "m"},
                    # Ranges span the 40 m stock tune AND the 80 m retune.
                    # Both capacitor knobs stop at 600 pF — about the
                    # largest variable cap any real matchbox offers — so
                    # every tune reachable here is one you could dial on
                    # actual hardware. (The loss penalty vs arbitrarily
                    # big caps is a few tenths of a percent.)
                    "series_c1_pF": {"min": 25.0, "max": 600.0},
                    "shunt_l_uH": {"min": 0.5, "max": 40.0},
                    "series_c2_pF": {"min": 25.0, "max": 600.0},
                    "coil_q": {"min": 0.0, "max": 400.0},
                }
            ),
        }
    )

    def build_wires(self):
        # Flat-doublet geometry from the inv-vee builder (angle 0); the
        # driven gap becomes the named "feed" port and loses its inline
        # excitation — the source lives at the virtual rig node.
        wires = []
        for w in map(as_wire, super().build_wires()):
            if w.ex is not None:
                wires.append(w._replace(ex=None, name="feed"))
            else:
                wires.append(w)
        return wires

    def build_network(self):
        return Network(
            ports={
                "feed": PortOnWire("feed"),
                "li": PortVirtual("li"),  # line input (tuner output)
                "rig": PortVirtual("rig"),
            },
            branches=[
                TL.from_cable("openwire-600", "li", "feed", self.line_len_m),
                # T-network tuner box; its tee midpoint is the instance's
                # own internal node ("tuner.m" after expansion).
                Instance(
                    "tuner",
                    t_network_tuner(
                        c1_pF=self.series_c1_pF,
                        c2_pF=self.series_c2_pF,
                        l_uH=self.shunt_l_uH,
                        ql=self.coil_q if self.coil_q > 0 else None,
                    ),
                    rig="rig",
                    out="li",
                ),
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
