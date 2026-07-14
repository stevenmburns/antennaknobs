---
title: Loading NEC decks
description: read_nec imports a NEC2 card deck — from xnec2c, 4nec2, EZNEC, or a handbook listing — as antenna geometry, the reverse of the .nec export.
---

antennaknobs can [export any design as a NEC2 card deck](/reference/cli/#exporting-to-nec);
`read_nec` is the reverse direction. It parses a `.nec` file — the format
xnec2c, 4nec2, EZNEC, and fifty years of antenna handbooks all speak — into
wire geometry a design can return from `build_wires`, so you can solve, sweep,
and view a deck someone published without retyping its coordinates.

Set expectations first, though: **a NEC deck is frozen geometry, not a
parameterized design.** The knobs are where antennaknobs earns its name — a
native builder expresses its dimensions as parameters and wavelength
fractions, so element lengths, spacings, and angles are all draggable and
optimizable, and `design_freq` moves the whole antenna to another band. A
deck has none of that structure to expose; coordinates are just numbers. What
an imported deck supports is the measurement frequency, a `height` lift, and
a whole-geometry `scale` — useful, but blunt. Treat the import as a *viewer*
for published decks, and as a source of dimensions when you decide a design
is worth porting to a real `AntennaBuilder`.

## Quick start

Drop the deck next to a small design stub in `~/.antennaknobs/designs/`:

```python
# my_yagi.py — my_yagi.nec sits next to it
from types import MappingProxyType
from antennaknobs import AntennaBuilder, WireSpec, read_nec

WIRES_FILE = "my_yagi.nec"

class Builder(AntennaBuilder):
    label = "My Yagi (NEC deck)"
    default_params = MappingProxyType({
        "freq": 14.1,
        "scale": 1.0,          # stretches the whole deck; drag to resonate
        "height": 10.0,        # lifts a z=0 deck above the ground plane
    })

    def build_wires(self):
        deck = read_nec(self, WIRES_FILE)
        s, h = self.scale, self.height
        return [((p1[0]*s, p1[1]*s, p1[2]*s + h),
                 (p2[0]*s, p2[1]*s, p2[2]*s + h), n, ex)
                for p1, p2, n, ex in deck.wire_tuples()]

    def build_wire_material(self):
        # Keep the deck's element radius — don't skip this (see below).
        return WireSpec(radius=read_nec(self, WIRES_FILE).dominant_radius() * self.scale)
```

`read_nec(self, name)` has the same folder confinement as `read_json`: it can
only read files next to the design — no absolute paths, no `..` that climbs
out, no symlinks pointing elsewhere — so a deck-based design stays safe to
share: the data can only ever become antenna geometry.

The two knobs above are essentially all a deck can offer, and both are worth
having:

- **`height`** — most published decks are drawn at z = 0 in free space, which
  would put the wires *in* the workbench's ground plane.
- **`scale`** — a deck is fixed metres; a uniform stretch of the whole
  geometry is the only way to move its resonance without editing the deck.
  It scales everything together — element lengths *and* spacings *and* the
  boom — so it is nothing like a native design's per-dimension knobs, but it
  will pull a slightly-off deck onto frequency.

There is no `design_freq` band scaling, no per-element tuning, and nothing
meaningful for the optimizer to hold onto — those need dimensions expressed
as parameters, which is exactly what porting the deck to a native
`AntennaBuilder` gives you.

And one method is not optional: **`build_wire_material`**. The solvers
default to an idealized 0.5 mm wire; a real deck's 5 mm Yagi elements have
very different reactance. `deck.dominant_radius()` returns the deck's radius
(length-weighted when wires differ) — feeding it to `WireSpec` is what makes
the import faithful. On the xnec2c 2 m Yagi example deck, the imported
geometry matches the independent `nec2c` solver to **0.011 Ω** *with* the
deck's radius, and misses by **35 Ω** without it.

## Following the deck's band

A deck's `FR` card is exposed as `deck.freq_mhz = (lo, hi)`. Use it at import
time to seed `freq` and the measurement window, so a 40 m or 2 m deck is
tunable on its own band instead of parked in the default window. A stub can
do this to itself at the bottom of the file — copy this block verbatim:

```python
def _seed_defaults_from_deck(cls):
    """Follow the deck's FR card: default `freq` to the sweep centre and set
    the measurement window to the sweep, so the design tunes on its own band.
    Errors are swallowed here so they surface in build_wires instead of
    killing the import."""
    try:
        freq_mhz = read_nec(cls(), WIRES_FILE).freq_mhz
    except Exception:
        return
    if not freq_mhz:
        return
    lo, hi = freq_mhz
    mid = 0.5 * (lo + hi)
    if lo >= hi:
        lo, hi = 0.9 * mid, 1.1 * mid
    params = dict(cls.default_params)
    params["freq"] = round(mid, 3)
    ui = dict(params.get("ui_params", ()))
    ui["meas_freq_range"] = (lo, hi)
    params["ui_params"] = MappingProxyType(ui)
    cls.default_params = MappingProxyType(params)


_seed_defaults_from_deck(Builder)
```

## What is translated

| Cards | Meaning |
| --- | --- |
| `GW` | Straight wires (tag, segments, endpoints, radius) |
| `GA`, `GH` | Arcs and helices, generated as per-segment chords exactly as NEC does internally |
| `GM` | Move / replicate — repetitions compound, each copy transforming the previous one |
| `GX` | Reflect in the Z, Y, X planes, tag increment doubling per plane |
| `GR` | Rotate about Z into a cylindrical array |
| `GS` | Scale — including xnec2c's tag-range extension (scale only tags I1..I2) |
| `EX` types 0/5 | Voltage-source feeds, resolved through NEC's (tag, segment) addressing |

Card semantics are transcribed from the `nec2c` 1.3.1 sources, quirks
included (tag 0 never increments under any transform), and validated against
it: 73 of the 75 xnec2c example decks parse — the other two are rejected with
a deliberate "cannot model" error — and impedance round-trips through the
`nec2c` CLI agree to a fraction of an ohm.

Decks are read the way real ones are written: free-format fields separated by
spaces and/or commas, missing trailing fields as `0`, old Fortran `1.0D+03`
exponents, `CM`/`CE` comment headers, parsing stops at `EN`.

A feed on a segment that isn't its wire's middle is handled by splitting the
wire on the deck's own segment boundaries, putting the feed on a 1-segment
wire of its own — same geometry, same segmentation, same feed point — so
off-center-fed designs import correctly.

## What is *not* applied

A deck also carries run configuration, which the workbench manages itself.
Those cards are recorded in `deck.ignored` rather than translated:

- `GN`/`GD` ground and the `GE` ground flag — the workbench applies **its own
  ground model** (`deck.ground` tells you the deck wanted one)
- `LD` loading, `TL`/`NT` feedlines and networks
- `FR` sweeps (harvested into `deck.freq_mhz`), `RP`/`NE`/`NH`/`XQ` output requests

Expect readouts to differ from a deck's published numbers when those numbers
relied on its ground, loading, or feedline cards — until you model those with
antennaknobs' own `Load`/`TL` network branches.

Decks the wire-model genuinely cannot represent are rejected with a clear
error rather than silently approximated: surface patches (`SP`/`SM`), tapered
wires (`GC`), Green's-function files (`GF`), 4nec2 symbolic variables (`SY`),
and plane-wave or current-source excitation (only voltage feeds exist here).

## Programmatic use

Outside a design, `parse_nec(text, name=...)` takes raw deck text and returns
the same `NecDeck`; `name` labels errors, which always carry the offending
line number (`my_yagi.nec, line 7: GW card: segment count must be >= 1, got 0`).

```python
from antennaknobs.nec_import import parse_nec
deck = parse_nec(open("some.nec").read(), name="some.nec")
```

| `NecDeck` field | Meaning |
| --- | --- |
| `wires` | `tuple[NecWire, ...]` — every straight wire after all transforms (`tag`, `n_seg`, `p1`, `p2`, `radius`) |
| `feeds` | `tuple[NecFeed, ...]` — each `EX` voltage source resolved onto a wire (`wire` index, 1-based `seg`, complex `voltage`) |
| `freq_mhz` | The `FR` card's sweep range as `(lo, hi)` MHz, or `None` |
| `ground` | `True` if the deck requested a ground plane (`GE` flag or a `GN` card) |
| `comments` | The `CM` header text, line by line |
| `ignored` | Mnemonics of run-configuration cards seen but not applied |

plus the two methods the quick start uses: `wire_tuples()` (the deck as
`build_wires()` tuples; raises if no voltage source drives the antenna) and
`dominant_radius()`.
