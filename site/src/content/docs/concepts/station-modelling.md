---
title: "Station modelling"
description: Model the whole signal chain — feedline, transformer, matchbox, antenna — as one circuit, and read where every watt goes.
---

An antenna is never fed directly. Between the transmitter and the wire
there is a feedline, often a transformer, sometimes a tuner — and every
one of those pieces moves the impedance the rig sees and takes a cut of
the power. antennaknobs models the **whole station** as one system: the
antenna is solved as a multiport by the field solver, and everything
else is a circuit stamped on top of it, solved simultaneously. Nothing
is a correction factor; the SWR at the rig, the loss in the coax, and
the current arriving at the feedpoint all come out of one solution.

This page introduces the vocabulary. The worked examples put it to use:
[two stations compared head-to-head](/advanced/station-comparison/),
[the end-fed question](/advanced/efhw/), and
[three ledgers of efficiency](/advanced/pota-performer/).

## Ports: where the circuit meets the wire

A design's `build_network()` returns a `Network` — ports, branches,
sources. Ports come in two kinds:

- **`PortOnWire("feed")`** — a real port at a named wire of the
  geometry. This is the seam between the circuit world and the field
  world: the MoM solve produces the antenna's multiport impedance at
  exactly these gaps.
- **`PortVirtual("rig")`** — a pure circuit node with no geometry. The
  transmitter end of a feedline is the classic one: it exists only in
  the network, and driving it makes every readout — impedance, SWR,
  gain, the power budget — **rig-referenced**.

The source (`Driven(port="rig")`) goes wherever your measurement plane
is. Put it at the antenna feed and you're modelling the antenna; put it
at the far end of the feedline and you're modelling the station.

The whole contract in one place — the simplest station in the catalog
(`dipoles.invvee_coax_station`, a resonant inverted vee on a real coax
run) returns exactly this:

```python
from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL

def build_network(self):
    return Network(
        ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
        branches=[
            TL.from_cable(self.cable, "rig", "feed", self.line_len_m),
        ],
        sources=[Driven(port="rig", voltage=1 + 0j)],
    )
```

Three fields, always: **ports** (every name a branch or source may
reference), **branches**, **sources**. The one geometry-side
obligation: a `PortOnWire` name must match a *named wire* in
`build_wires()` — a short wire tagged `"feed"` whose middle segment
becomes the port's gap.

## Branches: the circuit vocabulary

Between ports run **branches**, each a physical element with a minimal,
honest model:

| branch | what it is |
|---|---|
| `TL` / `TL.from_cable` | transmission line — ideal, or a real cable from the `CABLES` catalog (RG-58, RG-8X, window line…) with frequency-dependent matched loss; SWR-multiplied loss *emerges* from the circuit solution rather than a formula |
| `Load` | series R/L/C in a wire's current path — a trap, a terminating resistor |
| `TwoPort` | series R/L/C between two ports — a tuner's series capacitor |
| `Shunt` | R/L/C from a port to the common return — a tuner's shunt coil |
| `Transformer` | ideal ratio + magnetizing branch with core-loss Q — the balun/unun model, calibrated against measured insertion loss rather than derived from core datasheets |

Reactive elements accept a finite **Q** (`ql`, `qc`, `qlmag`), and that
is where real matchboxes and transformers burn power. Degenerate values
are physics, not errors: a 0 H series arm is an ideal short, a 0 F
shunt is an open — sliders can sweep straight through them.

## Boxes: reusable station components

You could assemble every tuner from raw branches — but the common boxes
ship pre-built in `antennaknobs.station`, and designs instantiate them
by name:

```python
from antennaknobs.network import Instance, TL
from antennaknobs.station import t_network_tuner

branches = [
    Instance(
        "tuner",
        t_network_tuner(c1_pF=81.2, c2_pF=500, l_uH=4.218, ql=200),
        rig="rig",      # formal → actual port map
        out="li",
    ),
    TL.from_cable("openwire-600", "li", "feed", 30.48),
]
```

A box (`Composite`) has a formal port interface and a private inside:
the tuner's tee midpoint exists as `tuner.m`, invisible to the rest of
the design. The stdlib today: `t_network_tuner`, `l_network_tuner`,
`unun` (with the compensation capacitor real 49:1 builds carry),
`balun` — all parameterized in radio units (picofarads, microhenries)
— plus one special member:

- **`bypass()`** — a box-shaped nothing: it wires its input straight to
  its output. Swap any tuner or balun for `bypass()` and you get the
  same station *without* that box, in a one-line change — the honest
  way to answer "what is this component actually buying me?"

Boxes are ordinary values made by ordinary functions, so a design can
also define its own — a measured, calibrated component wrapped once and
reused across variants.

## The power budget: where the watts go

Because every branch current is an explicit unknown in the circuit
solve, dissipation is *read off the solution*, branch by branch. The
workbench shows it as the [power budget](/reference/web/#power-budget):
one row per lossy element, grouped by box (`tuner: Shunt m`), an
**antenna (accepted)** row for what survives to the wires, and — with a
finite ground selected — the honest bottom line, **radiated (incl.
ground)**.

Those are the [three ledgers of
efficiency](/advanced/pota-performer/#the-efficiency-claim-true-in-its-ledger)
in one display: the network's cut, the structure's cut, and the dirt's
cut. A station that is "matched at 1.1:1" can still be delivering half
its power to the feedline and the ionosphere none the wiser — the
budget is what makes that visible while you turn the knobs.

## What the model deliberately isn't

The circuit layer is **minimal on purpose**. The transformer is an
ideal ratio plus one magnetizing branch — enough to reproduce a
published insertion-loss curve's shape, calibrated to a measurement,
not a full core characterization. Line loss is the cable-table
matched-loss model. Component Q is constant with frequency. Each of
these is the simplest model that makes the power budget honest; when a
measurement disagrees, the knobs (`qlmag`, `ql`, cable choice) are
where you reconcile it.

## Try it

Open [`wire.doublet_ladder_tuner`](https://app.antennaknobs.dev/) —
an 88 ft doublet, 100 ft of open-wire line, and a lossy T-network,
referenced to the rig. Watch the tuner's rows in the power budget as
you drag the capacitor knobs: the SWR meter and the watts tell
different stories, and this page is the vocabulary for reading both.
