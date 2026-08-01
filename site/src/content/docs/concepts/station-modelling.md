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
sources. Ports come in four kinds:

- **`PortOnWire("feed")`** — a real port at a named wire of the
  geometry. This is the seam between the circuit world and the field
  world: the MoM solve produces the antenna's multiport impedance at
  exactly these gaps.
- **`PortVirtual("rig")`** — a pure circuit node with no geometry. The
  transmitter end of a feedline is the classic one: it exists only in
  the network, and driving it makes every readout — impedance, SWR,
  gain, the power budget — **rig-referenced**.
- **`PortOnWireFloating("feed")`** — a gap port with **both** terminals
  exposed, addressed as `feed.p` and `feed.n`. An ordinary `PortOnWire` is
  stamped node-to-datum: its second terminal is bonded to the common return,
  so a branch can only reach one side of the gap. That is a stamping
  convention, not physics — the field solver only ever knows gap voltage and
  gap current. Use this when the two sides must go to *different* branches,
  which is what a balanced feed actually needs. It asks nothing of the
  solver, so it works on **every** engine — this is the construct to reach
  for when you need to hang a floating element off an antenna.

  A single floating gap is a one-port, so its stamp is purely differential and
  provides **no** common-mode path — give the network a CM return, or model
  the common-mode path as its own gap port and let the two-port coupling carry
  that physics.
- **`PortAtEnd("riser", "p1")`** — a port at a wire's *endpoint*
  rather than a mid-wire gap. It attaches to the shared junction node
  at that point without cutting a gap. momwire-only: NEC-2 has no
  junction-node port, so the PyNEC backend rejects designs that use it
  (a declared engine-parity break).

  Prefer `PortOnWireFloating` where the attachment can be authored as a
  mid-wire gap — it is portable and costs nothing. `PortAtEnd` earns its
  parity break only where the attachment is genuinely at a bare conductor
  *end*, because the obvious workarounds are measurably wrong there: a
  vanishing centre-tapped stub converges to an **open** (its far face is a
  dead end, not live conductor), and bridging across the two conductors
  gives the wrong conduction graph.

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
| `BalancedLine` | balanced / differential two-conductor line — the pair sibling of `TL`, carrying ±I with the return riding the partner wire (open-wire feeder, the Sterba curtain's offset-pair risers). Set by a single differential impedance `zdiff`; add an optional common-mode path `zcomm` for a pair that also carries end-to-end conductor continuity. Narrower scope than the rest of this table — see [what `BalancedLine` is good for](#what-balancedline-is-good-for) |
| `Load` | series R/L/C in a wire's current path — a trap, a terminating resistor |
| `TwoPort` | series R/L/C between two ports — a tuner's series capacitor |
| `Shunt` | R/L/C from a port to the common return — a tuner's shunt coil |
| `Transformer` | ideal ratio + magnetizing branch with core-loss Q — the balun/unun model, calibrated against measured insertion loss rather than derived from core datasheets |

Reactive elements accept a finite **Q** (`ql`, `qc`, `qlmag`), and that
is where real matchboxes and transformers burn power. Degenerate values
are physics, not errors: a 0 H series arm is an ideal short, a 0 F
shunt is an open — sliders can sweep straight through them.

### What `BalancedLine` is good for

`BalancedLine` is newer and more narrowly validated than the other
branches, so it is worth being explicit about where it earns its keep.

**It models a *tightly coupled* pair.** The differential stamp assumes the
two conductors are close enough to behave as one TEM line. Measured
against physical MoM wires, a pair at 0.004 λ spacing (the Sterba
offset-pair scale) matches the analytic
`(η₀/π)·acosh(D/2a)` within 3 %; by 0.06 λ the TEM model is visibly wrong
and degrades monotonically in between. A widely-spaced pair is not a
transmission line, and modelling it as one will quietly mislead you.

**It is differential-only by construction.** The stamp carries ±I and
cannot represent common-mode radiation. That is a deliberate contract, and
it is why the element suits structures whose pairs measurably *are*
balanced — `wire.sterba`'s risers run a common-mode residual of 0.05–0.15
of the differential current. It is not the tool for asking "how much does
my feedline radiate"; for feedline common-mode see `FloatingBalun`.

**Whether `zcomm` matters depends on the topology it sits in.** The optional
common-mode path exists because a real pair also provides end-to-end
*conductor continuity*, which a purely differential stamp drops. Two regimes,
and it is worth knowing which one you are in:

- *Closed loop, λ/2 pairs* — the Sterba curtain. Continuity is load-bearing:
  omit it and the three-bay array loses 5 dB with its beam swung 35° off
  broadside. But the **value** carries no information: sweeping `zcomm` from
  25 Ω to 3200 Ω moves the gain by 0.05 dB, because at λ/2 the common-mode
  line is a repeater. Turn it on; don't try to tune it.
- *Open feed tree* — `arrays.bowtie1x2_bl`'s corporate feed. There is no
  common-mode return, so a CM path is a genuine extra shunt admittance and
  its value matters a great deal: `zcomm = 100 Ω` drags the driving-point
  resistance from 50 Ω to 5 Ω. The correct model is CM-**open** (leave
  `zcomm` unset), which is what that design defaults to; large finite values
  converge back to it.

The rule of thumb: set `zcomm` when the pair's two conductors are part of a
closed conduction path that the differential stamp would otherwise break.
Leave it open when the pair simply ends.

**Engine support follows the port, not the element.** `BalancedLine` itself
is a pure circuit stamp and runs anywhere. What can pin a design to momwire
is how it *attaches*: a design that hangs the line off `PortAtEnd` is
momwire-only, because NEC-2 has no junction-node port and the PyNEC backend
rejects it (see [Ports](#ports-where-the-circuit-meets-the-wire)). Those
designs lose cross-*engine* validation, but no longer cross-*basis*
validation: the sinusoidal-Galerkin solver implements junction ports as well
(momwire#182), in free space and over a **PEC** ground (momwire#191; finite
grounds are still refused). So a `PortAtEnd` design can be checked against a
different basis *and* a different testing scheme, not merely a second B-spline
degree. A design that attaches through `PortOnWireFloating` keeps both engines.

### Naming a line by its geometry instead of its spool

`zdiff` is the number off the spool — 300 / 450 / 600 Ω. When you know the
*line* instead (conductor size, spacing, jacket), `BalancedLine.from_geometry`
computes `zdiff` and `vf` for you:

```python
# #12 bare wire on six-inch spreaders — the classic 600 Ω open-wire line
BalancedLine.from_geometry(
    "t1", "t2", "a1", "a2",
    spacing=0.1524, length=20.0, conductor=0.001024,
)
# a jacketed catalog wire brings its own insulation along
BalancedLine.from_geometry(
    "t1", "t2", "a1", "a2",
    spacing=0.0254, length=20.0, conductor="18-awg-pvc",
)
```

`conductor` is a radius in metres, a `WireSpec`, or a `WIRES` catalog key; pass
`conductor2` for an unequal pair. `two_wire_params()` is the same calculation
standalone, if you want the numbers without the element.

How much to trust it depends on the construction:

- **Bare conductors are exact** — the general unequal-radius
  `Z = (η₀/2π)·acosh((D² − a₁² − a₂²)/2a₁a₂)`, which collapses to the textbook
  `(η₀/π)·acosh(D/d)` for a matched pair. #12 at six inches comes out at
  599.9 Ω.
- **Jacketed round conductors** use a coaxial-shell model: the potential splits
  into a dielectric part near each wire and an air part across the gap. Right
  for insulated open-wire and for window line, and refused outright when the
  jackets touch — there is no air path then, and the model would be quietly
  wrong rather than loudly absent.
- **Solid-web twinlead** has no air path at all, so it takes the mixing rule
  `ε_eff = 1 + fill·(εᵣ − 1)` with an explicit `fill` (≈0.5 for a solid web,
  ≈0.15–0.25 for windowed). That is a *fitted* fraction, not a derived one.

A manufacturer's "450 Ω" is a round number covering a range of real
constructions, so expect geometry to land within a few percent of a nameplate
rather than on it — and when you know the nameplate `vf`, that is better data
than either estimator here.

Three catalog designs use `BalancedLine` today:
`wire.doublet_balanced_tuner` (floating centre port — runs on every engine),
plus `wire.sterba_bl` and `arrays.bowtie1x2_bl` (both `PortAtEnd`, so
momwire-only).

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
`balun`, `link_coupling`, `balanced_l_tuner` — all parameterized in
radio units (picofarads, microhenries) — plus two special members:

- **`bypass()`** — a box-shaped nothing: it wires its input straight to
  its output. Swap any tuner or balun for `bypass()` and you get the
  same station *without* that box, in a one-line change — the honest
  way to answer "what is this component actually buying me?"

- **stubs** — `shunt_shorted_stub`, `shunt_open_stub`, and their
  `series_*` twins are matching elements made of nothing but cable: a
  length of line terminated in a short or an open, presenting
  `+jZ₀·tan(βl)` or `−jZ₀·cot(βl)` at its port. Lengths are given in
  wavelengths *on the line* at a design frequency (the velocity factor
  is applied for you; the composite bakes metres, so it detunes across
  a sweep like the real thing), and `cable="RG-213"` cuts it from a
  catalog reel, loss included. `single_stub_tuner` and
  `double_stub_tuner` place them at the classic positions — a match
  with no lumped parts, just cable lengths.

Boxes are ordinary values made by ordinary functions, so a design can
also define its own — a measured, calibrated component wrapped once and
reused across variants.

### When a lossless line has no answer

An *ideal* line has frequencies where the circuit genuinely has no finite
solution. A lossless half-wave line has no finite admittance at all; a lossless
quarter-wave **open** stub is a dead short across the port it hangs on. These
are not numerical accidents — they are what the idealisation says, and the fix
is physical: give the line the loss it really has (`k1`/`k2`, or `cable="..."`).
Any real attenuation moves the pole off the real axis.

Two places this shows up:

- **At construction**, when the length and design frequency make it decidable —
  `shunt_open_stub` at exactly λ/4 refuses to be built.
- **Mid-sweep**, when a length that was innocuous at its design frequency
  becomes λ/4 or λ/2 somewhere else in the swept band. Nothing is decidable in
  advance there, and no individual element is singular — each stamp is finite
  and the *assembled system* is not. The reducer detects it, names the branch
  and its electrical length, and repeats the remedy:

  ```
  SingularNetworkError: the network has no finite solution at this frequency
  (reciprocal condition 7.6e-16 after equilibration). Every branch stamped fine
  on its own — the singularity is in the assembled system.
  Suspect:
    stub: open-ended line feed→stub.far is 0.2500 λ at 35.0000 MHz — an odd
    multiple of λ/4, where an open stub's Z_in = 0 shorts the port it hangs on
  ```

A **sweep** loses only that sample: the frequency in question comes back as
NaN (the workbench renders it as an open) with the reason logged, and every
other frequency answers normally. A single-point solve raises, because someone
who asked about one frequency should get the sentence, not a silent NaN.

The near-miss is the sneaky case and gets the same treatment: a sample a few
kHz off the pole is not singular, merely dominated by it, and produces
enormous numbers whose leading digits are noise. That logs a warning rather
than refusing — the answer exists, it just should not be believed.

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
