---
title: "Cut for one band, worked on another"
description: Off-band designs — how design frequency and measurement frequency separate, what the tuner is really doing, and how to author a design that opens mid-mismatch on purpose.
---

Real antennas get cut once and worked everywhere. The 10 m inverted-L that
was perfect in October is what you have when the propagation moves to 12 m;
the 80 m skyloop is what's in the air when 17 m opens. You don't re-saw the
wire — you reach for the tuner. Two catalog designs model exactly that
situation, and they lean on a distinction the workbench keeps carefully:
**the frequency the antenna is built for is not the frequency you measure
it at.**

## Two frequencies, two controls

Every design carries both:

- **`design_freq`** sizes the geometry. It's the saw and the tape measure —
  change it and the wires themselves change length. In the workbench it's
  the *band tabs* row.
- **`freq`** is where the measurement happens: the impedance readout, the
  SWR, the Smith chart, the pattern. In the workbench it's the *dial*.

For most designs the two travel together — the dial is locked to the design
frequency, and retuning the antenna drags the measurement along. That lock
is a convenience, not a law. Open it and you can park the dial anywhere
while the geometry stays frozen: that's "checking what my 10 m antenna
looks like on 12 m" as a single click.

Off-band designs open **with the lock already open**: geometry parked on
the band they're cut for, dial parked on the band they're operated on.
(They have to — snapping both controls to one frequency would silently
re-saw the antenna for the operating band and dissolve the design's whole
premise.)

## The hard case: a short antenna and a T-network

[`verticals.inverted_l_tmatch`](/reference/catalog/) is a 10 m inverted-L
(cut at 28.57 MHz) worked on 12 m. At 24.9 MHz the riser is electrically
short and the feed sees roughly **11 − 117 j Ω** — low resistance, a big
capacitive reactance, nowhere near 50 Ω. The classic fix is the ham
T-tuner: two series capacitors flanking a shunt inductor.

The stock knobs are the *solved* tuner — the design opens as the "after"
picture, and the interesting move is turning the knobs and watching the
match fall apart. Three things to look at:

1. **The power budget.** The tuner is a composite box, so its rows sit
   indented under `tuner` in the readout: *series C1*, *shunt coil*,
   *series C2*. The coil row is the story — a T-network matches a short
   antenna by riding a virtual resistance of ~2 kΩ through the tee, which
   runs high circulating current through the inductor. At the stock coil
   Q of 200 (a good air-wound coil) that burns **~9 % of everything you
   feed it**, before a single watt reaches the wire. This is the classic
   hidden cost of the T-match, and it's why the design ships a *real*
   coil: set `coil_q` to 0 (ideal) and the loss vanishes — along with the
   entire budget display, because a lossless network has nothing to
   report.
2. **The loaded Q.** The match is narrow — sweep the band and the SWR
   notch is sharp (loaded Q ≈ 13). That's the real-world "retune every
   50 kHz" behavior of tuners on short antennas, reproduced from first
   principles.
3. **The touchiness.** The stock values land SWR ≈ 1.0 in the workbench,
   but they only *stay* there because they were tuned against the exact
   solve the workbench runs. Solve the same stock design on a different
   basis (the test suite's sinusoidal reference, say) and the bare
   antenna moves by only a few percent — which the ~2 kΩ
   virtual-resistance ride magnifies to SWR ≈ 1.4 at the input. A high-Q
   match amplifies *every* small difference, in models and in hardware
   alike: it's the same reason the physical version of this tuner needs
   re-dipping when the feedline is re-routed or the ground dries out.
   Nudge `series_c1_pF` a hair off stock and watch how fast the notch
   walks away — then walk it back, which is precisely the bench
   experience.

## The easy case: a big loop and an L-network

[`loops.skyloop_lmatch`](/reference/catalog/) is the opposite corner: an
80 m full-wave triangular loop (~85 m of wire) worked on 17 m, where its
perimeter is ~4.7 λ and the corner feed sits around **225 − 70 j Ω**.
That's a moderate mismatch, not a desperate one, and a two-element
L-network handles it: series inductor to the source, shunt capacitor
across the feed.

Same stock coil Q of 200, very different bill: the L-match runs modest
circulating current, so the coil burns only **~1 %** and the design opens
at SWR ≈ 1.15 in the workbench. Comparing the two budget readouts side by
side is the cleanest illustration in the catalog of why "it matched"
isn't the same claim as "it matched cheaply": the SWR meter reads ~1 in
both shacks while the tuner eats nine times more of your power in one of
them.

## Authoring one

If you're [writing your own design](/concepts/authoring/), an off-band
design is three decisions:

```python
class Builder(SomeAntenna):
    default_params = MappingProxyType({
        **SomeAntenna.default_params,
        # 1. Keep the inherited design_freq (the band it's CUT for)
        #    and set freq to the band it's WORKED on.
        "freq": 24.9,
        # 2. Give the matchbox coil a real Q — an ideal matchbox
        #    dissipates nothing and hides the whole power budget.
        "coil_q": 200.0,
        ...
    })

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed"), "in": PortVirtual("in")},
            branches=[
                # 3. The matchbox is a station-stdlib composite, so its
                #    budget rows group under the instance name.
                Instance("tuner",
                         t_network_tuner(c1_pF=..., c2_pF=..., l_uH=...,
                                         ql=self.coil_q or None),
                         rig="in", out="feed"),
            ],
            sources=[Driven(port="in", voltage=1 + 0j)],
        )
```

The workbench does the rest from the two frequency defaults: it opens the
design with the geometry on `design_freq`, the dial on `freq`, and the
lock open. Tune your stock matchbox values at `freq` — that's where the
design will be judged — and remember the T-match lesson above: the higher
the virtual resistance your match rides, the more sensitive the stock
tune is to *everything*, so quote the reference you tuned against. A
`ui_params["budget_labels"]` map turns the structural row names into
friendly ones (`"tuner: Shunt m"` → `"shunt coil"`).

The network vocabulary (ports, branches, boxes) is introduced in
[Station modelling](/concepts/station-modelling/); the full watt-by-watt
methodology is worked in
[Coax vs. ladder line](/advanced/station-comparison/).
