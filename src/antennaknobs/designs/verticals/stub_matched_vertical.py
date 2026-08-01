"""Quarter-wave vertical matched with nothing but cable (issue #648).

A quarter-wave vertical is the standard example of an antenna that is *fine*
and still doesn't present 50 Ω: this one (the stock `verticals.vertical`, three
elevated radials) solves to about **22 − 0j** — resonant, and a 2.3:1 mismatch
purely from its radiation resistance. The textbook fix needs no components at
all, just two lengths of the same coax you were going to run anyway:

1. Walk ``line_wl`` up the line from the antenna until the admittance there has
   the right *real* part — Y = Y₀ + jB. Rotating around the Smith chart is what
   the line section is for.
2. Hang a shunt stub of length ``stub_wl`` at that point, cut so its
   susceptance is exactly −jB.

Both knobs are live, so the match is something you *find* rather than something
you're handed — drag ``line_wl`` and watch the trace swing around the constant-
SWR circle, then drag ``stub_wl`` to pull it into the middle. The defaults sit
on a solved match; leaving them is the boring case, and moving them is the
lesson.

**There are two answers, not one.** The load's constant-SWR circle crosses the
unit-conductance circle twice, so this antenna is matched by either

- ``line_wl = 0.406``, ``stub_wl = 0.141`` — the default: a longer walk, a
  short stub, and 3.8 m of RG-213 in total;
- ``line_wl = 0.096``, ``stub_wl = 0.360`` — a short walk and a stub nearly
  0.4 λ long (3.2 m of cable, but an unwieldy stub).

Both give SWR 1.00 at the design frequency. Which you build is a mechanical
question, not an electrical one.

**Bandwidth is the honest part.** A stub match is a *narrowband* device: the
line section and the stub are both cut in metres, so their electrical lengths
walk with frequency and the match comes apart either side of the design point
faster than the antenna itself goes off-resonance. Drag the measurement
frequency and watch the SWR climb — that steepness is the price of matching
with cable instead of a tuner, and it is the reason a stub match is cut for one
band and only one band.

Set ``match="bypass"`` to feed the same antenna straight through the same
length of line: the A/B that says what the stub is actually buying.

Because the whole match is `NetworkReducer` circuit math on a shunt-stub
topology, it runs identically on **both engines** (momwire and PyNEC) — see
``tests/test_stub_matched_vertical.py``, which pins that parity.
"""

from types import MappingProxyType

from antennaknobs.designs.verticals.vertical import Builder as Vertical
from antennaknobs.network import (
    CABLES,
    Driven,
    Instance,
    Network,
    PortOnWire,
    PortVirtual,
    as_wire,
)
from antennaknobs.station import bypass, single_stub_tuner


class Builder(Vertical):
    default_params = MappingProxyType(
        {
            **Vertical.default_params,
            "cable": "RG-213",
            # The solved match for this antenna's 22 − 0j feedpoint. See the
            # module docstring for the second solution.
            "line_wl": 0.406,
            "stub_wl": 0.1408,
            "match": "stub",
            "ui_params": MappingProxyType(
                {
                    **Vertical.default_params["ui_params"],
                    "target_z0": 50.0,
                    "cable": {"enum_options": tuple(sorted(CABLES))},
                    "match": {"enum_options": ("stub", "bypass")},
                    # Half a wavelength covers every distinct tap position and
                    # stub length; beyond that both repeat.
                    "line_wl": {"min": 0.01, "max": 0.5, "step": 0.002},
                    "stub_wl": {"min": 0.01, "max": 0.49, "step": 0.002},
                    # A stub match is narrow by nature: keep the sweep on the
                    # band being measured rather than the default ±20/25 %
                    # window, which would show mostly the collapse.
                    "sweep_policy": {"anchor": "meas_freq", "band_locked": True},
                    # Structural labels (verified against the reducer's
                    # actual probe names) renamed for the budget panel.
                    "budget_labels": {
                        "match: TL rig→feed": "matching section",
                        "match.stub: TL rig→far": "stub",
                        "match.stub: Shunt far": "stub short (ideal)",
                    },
                }
            ),
        }
    )

    def build_wires(self):
        # Stock vertical geometry, with the driven gap renamed and stripped of
        # its inline excitation: the source now sits at the rig end of the
        # matching section, so what the workbench reports is what the
        # transmitter sees through the match.
        return [
            w._replace(ex=None, name="feed") if w.ex is not None else w
            for w in map(as_wire, super().build_wires())
        ]

    def build_network(self):
        # Cut at design_freq, in metres — so dragging the *measurement*
        # frequency detunes the match exactly the way a real one detunes.
        box = (
            single_stub_tuner(
                freq_mhz=self.design_freq,
                line_wl=self.line_wl,
                stub_wl=self.stub_wl,
                cable=self.cable,
                shorted=True,
            )
            if self.match == "stub"
            else bypass()
        )
        formals = {"rig": "rig", "ant": "feed"} if self.match == "stub" else {"a": "rig", "b": "feed"}  # fmt: skip
        return Network(
            ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
            branches=[Instance("match", box, **formals)],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
