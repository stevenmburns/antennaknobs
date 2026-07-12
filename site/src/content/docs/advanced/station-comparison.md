---
title: "Coax vs. ladder line: a tale of two stations"
description: An advanced worked example — model two complete HF stations from the rig to the wire, and read where every watt goes off the power budget.
---

Every club meeting has the argument. One camp: *a resonant antenna on 50 Ω coax
is simple and it works*. The other: *put up one non-resonant wire, feed it with
open-wire line, and let the tuner sort it out — ladder line shrugs off SWR*.
Both camps are right, and both are paying for something. This example models
both stations **end to end — rig, feedline, matching, wire** — reads the
folklore off the [power budget](/reference/web/#power-budget) as numbers, and
finishes with the two stations head to head on the same band, 20 m.

Two catalog designs (new in v0.22) carry the comparison:

| | Station A | Station B |
|---|---|---|
| Design | `dipoles.invvee_coax_station` | `wire.doublet_ladder_tuner` |
| Antenna | resonant inverted-V (half-wave at 28.47 MHz) | 88 ft flat doublet — deliberately *non*-resonant |
| Feedline | 100 ft of RG-8X coax | 100 ft of 600 Ω open-wire line |
| Matching | none — the antenna itself is the match | T-network tuner with a finite-Q coil |

Both are **modelled from the rig**: the source sits at a virtual *rig* port and
reaches the wire through the real feed network, so every number the workbench
reports — impedance, SWR, gain, the power budget — is referenced to the
transmitter, not the feedpoint. That reference-plane move is the whole trick;
everything below falls out of it.

## Station A — the resonant antenna on coax

The geometry is the stock `dipoles.invvee`. What changes is the feed: the
driven gap becomes a named **feed** port, and the excitation moves to the far
end of a real cable:

```python
def build_network(self):
    return Network(
        ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
        branches=[
            TL.from_cable(self.cable, "rig", "feed", self.line_len_m),
        ],
        sources=[Driven(port="rig", voltage=1 + 0j)],
    )
```

`TL.from_cable` pulls attenuation and velocity factor from the built-in
`CABLES` catalog, so the line is lossy the way real cable is. Open the design
in the [workbench](https://app.antennaknobs.dev/) and look at three things:

1. **On resonance, coax at 10 m still isn't cheap.** The V is near 50 Ω, the
   line runs essentially matched — and the budget still shows roughly the
   cable's matched loss: **~1.6 dB ≈ 31 % of your power** for 100 ft of RG-8X
   at 28 MHz, before any mismatch enters the story.
2. **Drag `freq` off resonance.** The SWR climbs, and the line row of the
   budget grows past the matched loss — the classic *SWR-multiplied line loss*.
   Nobody typed that formula in: it emerges from the circuit solve.
3. **Swap the `cable` preset.** RG-58 vs. LMR-400 is the "should I buy better
   coax?" question answered in one dropdown. Then pick one of the 450/600 Ω
   window-line presets and watch the loss nearly vanish even at high SWR —
   that's the effect Station B is built around.

## Station B — the doublet and the matchbox

The other philosophy: don't chase resonance at all. An 88 ft doublet — a
40 m quarter-wave per side stretched by `length_factor = 1.269`, resonant
nowhere you'd operate it — feeds 100 ft of 600 Ω open-wire line into a
T-network — series C, shunt L, series C — whose inductor has a finite
`coil_q`:

```python
def build_network(self):
    return Network(
        ports={
            "feed": PortOnWire("feed"),
            "li": PortVirtual("li"),   # line input (tuner output)
            "m": PortVirtual("m"),     # tee midpoint
            "rig": PortVirtual("rig"),
        },
        branches=[
            TL.from_cable("openwire-600", "li", "feed", self.line_len_m),
            TwoPort(a="rig", b="m", c=self.series_c1_pF * 1e-12),
            Shunt(port="m", l=self.shunt_l_uH * 1e-6,
                  ql=self.coil_q if self.coil_q > 0 else None),
            TwoPort(a="m", b="li", c=self.series_c2_pF * 1e-12),
        ],
        sources=[Driven(port="rig", voltage=1 + 0j)],
    )
```

The stock capacitor and inductor values match ~50 Ω at **7.1 MHz (40 m)**, and
the budget itemizes the price of the matchbox: with Q = 200, about **3.5 % in
the line and 4 % in the tuner coil — ~92 % radiated**. That's the ladder-line
promise kept.

Now make the wire *too short* — retune for **80 m** (pick 80m in the
measurement-band selector, dial the frequency to 3.8, then
`series_c1_pF ≈ 38.8`, `shunt_l_uH ≈ 32.6`; `series_c2_pF` stays at 500).
SWR at the rig is still ≈ 1 — the tuner did its job — but the line's SWR
loss climbs to **~17 %** and the coil's to **~15 %**. A perfect match at the
rig, and a third of the power never leaves the shack wiring. That is the
honest cost of working an electrically short wire, and no SWR meter will
ever show it to you.

Two things worth knowing while you drag:

- **T-match solutions aren't unique.** Bigger capacitors with a smaller L
  generally mean less circulating current and lower coil loss — try finding a
  second match for the same band and compare budgets. The capacitor knobs
  stop at 600 pF, about the largest variable cap a real matchbox offers, so
  every tune you can dial here is one you could dial on hardware (past
  ~300 pF the coil-loss curve is nearly flat anyway). Sweep `coil_q` too
  (0 = ideal coil) to see how much of the loss is the coil's fault.
- **The slider endpoints are physics, not bugs.** `series_c1_pF = 0` is a
  0 pF series capacitor — an open circuit — so the readout reports Z = ∞.

## The head-to-head: both stations on 20 m

Stock, the two designs sit on different bands — the V on 10 m, the doublet
tuned for 40 m — so their budgets above aren't yet comparable. Put both on
**20 m** and let them fight fair. Load Station A and Station B in two
[design sessions](/reference/web/#design-sessions-tabs) (**D1** / **D2**).
The workbench's frequency controls are band-first, and the two stations use
them in tellingly different ways:

- **Station A** — click **20m** in the *design-frequency band row*. The
  design frequency snaps to 14.300 MHz, the measurement frequency follows,
  and the V rebuilds itself resonant on the new band. That's the resonant
  station's whole deal: changing bands means changing the antenna, because
  the antenna *is* the match.
- **Station B** — click **20m** in the *measurement-band selector* instead.
  That moves only the operating frequency (unlinking it from the design
  frequency automatically); the wire and the line are untouched. Then retune
  the box: `series_c1_pF = 29.1`, `shunt_l_uH = 2.56` (`series_c2_pF` stays
  at its 500 pF default). Band-hopping is two tuner knobs.

Same frequency (14.300 MHz), same 100 ft feed run, rig-referenced budgets
side by side:

| at 14.3 MHz | A — inv-vee + RG-8X | B — doublet + ladder line + tuner |
|---|---|---|
| SWR at the rig | 1.4 | 1.0 |
| SWR on the feedline | ≈ 1.4 | ≈ 11 |
| feedline loss | 24 % | 9 % |
| tuner coil loss | — | 6 % |
| **radiated** | **76 %** | **84 %** |

(Every number on this page is solved the way the workbench solves it by
default: finite ground — εr = 10, σ = 0.002, reflection-coefficient model —
with the B-spline d = 2 solver.)

What the table says:

- **Matched loss is a floor.** Station A's coax runs essentially flat —
  SWR 1.4 — and still eats 24 %, because 100 ft of RG-8X is 1.10 dB at
  14.3 MHz *matched*. No antenna trimming gets under that line.
- **The ladder line runs SWR ≈ 11 and shrugs.** The mismatch that multiplies
  coax loss into disaster (Station A's off-resonance beat, above) costs the
  open-wire line 9 % — total, matched loss included.
- **The coil takes its cut — and B still wins.** 6 % in the tuner inductor is
  the price of the matchbox, and the doublet station radiates eight points
  more anyway.
- **The tuner protects the rig, not the watts.** Wreck the match on purpose:
  drag `shunt_l_uH` from 2.56 to 3.0 and the rig sees SWR 5 — yet radiated
  power doesn't drop at all (84.3 % → 85.2 %). The watts were already decided
  out on the line and in the coil; the match just decides whether your
  transmitter is happy delivering them.

[Pin a pattern](/reference/web/#comparing-patterns) from one session onto the
other before you leave: both antennas hang at 10 m, but at 14.3 MHz the 88 ft
doublet is about 1.28 λ long, so its azimuth pattern is starting to break
into lobes — the budget is only half of what distinguishes two stations.

## What's actually being solved

There is no special-case feedline math anywhere in this page. A design's
`build_network()` declares **ports** (`PortOnWire` on a wire gap,
`PortVirtual` for pure circuit nodes), **branches** (`TL`, `TwoPort`, `Shunt`,
`Transformer`), and **sources** (`Driven`), and the whole thing is solved as
one MNA circuit coupled to the method-of-moments wire solution. Every branch
current is an explicit unknown, so the watts in the
[power budget](/reference/web/#power-budget) are *read off the solution*, and
gain is normalised by input power — network loss is already in the dBi you see.

## Where to go next

- **`dipoles.folded_invvee_balun`** — the third v0.22 station design: a folded
  inverted-V through a 4:1 balun (`Transformer`, core loss included).
- **Roll your own station.** Any builder can add a `build_network()` — take a
  design you care about from the [catalog](/reference/catalog/), and put *your*
  actual feedline length and tuner on it.
- **[The model](/concepts/model/)** and
  **[write your first design](/concepts/first-builder/)** — if you want to
  build the antenna itself from scratch first.
