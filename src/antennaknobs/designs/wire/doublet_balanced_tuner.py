"""Center-fed doublet on open-wire line into a genuinely balanced tuner — the
`FloatingBalun` showcase (issue #589).

The balanced twin of `wire.doublet_ladder_tuner`. That design brings the
open-wire line onto a single-ended feed gap and matches it with a T-network
referenced to the chassis — faithful as a circuit, but it grounds one side of
the "balanced" feed. This design keeps the feed balanced end to end: the
open-wire line runs into a balanced L-network tuner whose 50 Ω input is a 1:1
current balun, so both tuner legs float above the datum and no common-mode
current is injected at the coax. That is the chain the framework could not
close before #589 — a balanced feedline into a balanced tuner into a
*single-ended* rig — because every source and transformer was datum-locked.
`FloatingBalun` is the missing primitive.

Signal path, the Palstar BT1500A "double roller balanced tuner" idiom:

    rig (50 Ω) → FloatingBalun 1:1 → [L/2 roller in each leg] → diff cap
                → open-wire BalancedLine → doublet centre port

Only the balun's primary touches the datum. The doublet is ONE wire carrying a
`PortOnWireFloating` at its centre: an ordinary delta gap (a point
discontinuity, no physical extent), but with BOTH its terminals exposed as
circuit nodes, so the `BalancedLine`'s two conductors attach to the two sides
of it. The line is an ideal element — its conductor spacing lives in
``line_zdiff``, not in the geometry — so nothing here has a second length
scale, and the whole antenna meshes at one uniform density. The line's
``line_zcomm`` (issue #576) is the common-mode return that lets the floating
tuner section reference ground through the antenna — without it the MNA is
singular, and the design says so at build time.

The roller inductance ``tuner_l_uH`` and differential capacitance
``tuner_c_pF`` are the two tuning knobs; ``tuner_ql`` is the roller-coil Q (the
tuner's dominant loss, so the power budget shows where the watts go). The stock
values land the ~0.72 λ doublet's ladder-line feedpoint on 50 Ω at the rig
(SWR ≈ 1.00 momwire, 1.03 PyNEC) at 14.1 MHz — retune them (and the line length) for another band,
the way a real balanced tuner is worked.

Engine support: **every engine**. A floating port changes only how the shared
reducer stamps the antenna's multiport Y, never what the solver is asked for,
so this runs on PyNEC as well as momwire. Both converge on refinement and agree
to 0.2 % by N=641 (the delta gap is smeared over one segment, so the answer
depends on segment length until refined — the usual delta-gap convergence, not
a modelling choice)."""

from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    BalancedLine,
    Driven,
    Instance,
    Network,
    PortOnWireFloating,
    PortVirtual,
    Wire,
)
from antennaknobs.station import balanced_l_tuner


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 14.1,
            # design_freq scales the geometry AND anchors auto_mesh; hidden.
            "design_freq": 14.1,
            # Doublet total length as a wavelength factor (each arm is half).
            # ~0.72 λ — a moderately long, non-resonant doublet whose feedpoint
            # is reactive, so the tuner does real work.
            "length_factor": 0.72,
            # Antenna height (a wavelength factor); free space by default.
            "height_factor": 0.5,
            # Open-wire feedline: 450 Ω window line, length a wavelength factor.
            "line_zdiff": 450.0,
            "line_vf": 0.91,
            "line_len_factor": 0.40,
            # The line's common-mode return impedance (issue #576) — the path
            # that grounds the floating tuner section through the antenna. At a
            # non-resonant line length the exact value matters little; it must
            # be present (0 → None → a singular, rejected common mode).
            "line_zcomm": 250.0,
            # Balanced L-network tuner knobs (roller L split into both legs,
            # differential resonating C), tuned to 50 Ω at the rig (SWR ≈ 1.00
            # at 14.1 MHz on the stock geometry).
            "tuner_l_uH": 3.350,
            "tuner_c_pF": 60.43,
            # Roller-coil Q (issue #298) — defaults high (near-ideal); the
            # power budget itemizes the coil loss so you can watch it grow as
            # you retune a shorter wire.
            "tuner_ql": 200.0,
            "ui_params": MappingProxyType(
                {
                    "design_freq": {"hidden": True},
                    "target_z0": 50.0,
                    "length_factor": {"min": 0.30, "max": 1.30, "step": 0.01},
                    "height_factor": {"min": 0.1, "max": 2.0, "step": 0.05},
                    "line_zdiff": {"min": 300.0, "max": 600.0, "step": 10.0},
                    "line_vf": {"min": 0.80, "max": 1.0, "step": 0.01},
                    "line_len_factor": {"min": 0.05, "max": 1.0, "step": 0.01},
                    "line_zcomm": {"min": 0.0, "max": 400.0, "step": 25.0},
                    "tuner_l_uH": {"min": 0.5, "max": 30.0, "step": 0.1, "unit": "µH"},
                    "tuner_c_pF": {
                        "min": 10.0,
                        "max": 500.0,
                        "step": 1.0,
                        "unit": "pF",
                    },
                    "tuner_ql": {"min": 0.0, "max": 400.0},
                }
            ),
        }
    )

    # ---- geometry -------------------------------------------------------
    def build_wires(self):
        wl = self.design_wavelength
        arm = 0.5 * self.length_factor * wl
        z = self.height_factor * wl

        # One horizontal wire along y. The feed is a floating port at its
        # centre — a delta gap has no physical extent, so there is no bridge
        # and no second length scale to mesh around.
        return self.auto_mesh([Wire((0.0, -arm, z), (0.0, arm, z), name="feed")])

    # ---- feed network ---------------------------------------------------
    def build_network(self):
        wl = self.design_wavelength
        line_len = self.line_len_factor * wl
        zc = self.line_zcomm or None
        return Network(
            ports={
                # the doublet's centre port, BOTH terminals exposed
                "feed": PortOnWireFloating("feed"),
                "rig": PortVirtual("rig"),
                "liL": PortVirtual("liL"),  # tuner output → line bottom
                "liR": PortVirtual("liR"),
            },
            branches=[
                Instance(
                    "tuner",
                    balanced_l_tuner(
                        l_uH=self.tuner_l_uH,
                        c_pF=self.tuner_c_pF,
                        n=1.0,
                        ql=self.tuner_ql if self.tuner_ql > 0 else None,
                    ),
                    rig="rig",
                    outL="liL",
                    outR="liR",
                ),  # fmt: skip
                BalancedLine(
                    a1="liL",
                    a2="liR",
                    b1="feed.p",
                    b2="feed.n",
                    zdiff=self.line_zdiff,
                    length=line_len,
                    vf=self.line_vf,
                    zcomm=zc,
                ),  # fmt: skip
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
