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
from antennaknobs import AntennaBuilder, read_nec

WIRES_FILE = "my_yagi.nec"

class Builder(AntennaBuilder):
    label = "My Yagi (NEC deck)"
    default_params = MappingProxyType({
        "freq": 14.1,
        "scale": 1.0,          # stretches the whole deck; drag to resonate
        "height": 10.0,        # lifts a z=0 deck above the ground plane
    })

    def build_wires(self):
        deck = read_nec(self, WIRES_FILE, network=True)
        s, h = self.scale, self.height
        lift = lambda p: (p[0] * s, p[1] * s, p[2] * s + h)
        # specs=True: `Wire` entries, each carrying ITS OWN radius from the
        # deck's GW card (and LD 5 conductivity) — a fat driven element
        # with thin radials solves faithfully, wire by wire. The named
        # entries carry the deck's feed and network attachment points.
        return [
            w._replace(p0=lift(w.p0), p1=lift(w.p1))
            for w in deck.wire_tuples(specs=True)
        ]

    def build_network(self):
        # The deck's EX drive plus its translated LD/TL/NT cards (see below).
        return read_nec(self, WIRES_FILE, network=True).network()
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

And the radius is not optional. The solvers default to an idealized 0.5 mm
wire; a real deck's 5 mm Yagi elements have very different reactance. On the
xnec2c 2 m Yagi example deck, the imported geometry matches the independent
`nec2c` solver to **0.011 Ω** *with* the deck's radius, and misses by
**35 Ω** without it. `wire_tuples(specs=True)` (above) handles this per
wire: every emitted `Wire` carries a `WireSpec` with that GW card's own
radius, so even a mixed-radius deck keeps its reactance. (The pre-#388
recipe — plain `wire_tuples()` plus a `build_wire_material()` returning
`WireSpec(radius=deck.dominant_radius(), conductivity=deck.conductivity)` —
still works, approximating mixed radii with the length-dominant one.)

Two caveats on per-wire radii: the PyNEC engine honors them exactly (NEC
takes a radius per wire natively); momwire approximates *mixed* radii with
the length-dominant one until its per-wire radius kernels land. And the
`scale` knob stretches geometry only — specs describe physical wire stock
and are never scaled.

## Following the deck's band

A deck's `FR` card is exposed as `deck.freq_mhz = (lo, hi)`. Use it at import
time to seed `freq` and the measurement window, so a 40 m or 2 m deck is
tunable on its own band instead of parked in the default window. A stub can
do this to itself at the bottom of the file — copy this block verbatim:

```python
def _seed_defaults_from_deck(cls):
    """Follow the deck's FR card: default `freq` to the sweep centre and set
    the measurement window to the sweep, so the design tunes on its own band.
    Also surface the run-config cards the import recorded but didn't apply
    (deck.skipped_note()) as the UI's informational design note.
    Errors are swallowed here so they surface in build_wires instead of
    killing the import."""
    try:
        deck = read_nec(cls(), WIRES_FILE, network=True)
    except Exception:
        return
    params = dict(cls.default_params)
    ui = dict(params.get("ui_params", ()))
    if deck.freq_mhz:
        lo, hi = deck.freq_mhz
        mid = 0.5 * (lo + hi)
        if lo >= hi:
            lo, hi = 0.9 * mid, 1.1 * mid
        params["freq"] = round(mid, 3)
        ui["meas_freq_range"] = (lo, hi)
    note = deck.skipped_note()
    if note:
        ui["notes"] = note
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

Wires are also split wherever another wire's segment endpoint touches them
mid-wire. NEC connects *segments* whose ends coincide — the grouping into GW
cards is irrelevant to it — so a deck may run one wire straight through
another and rely on the crossing carrying current (the W8IO whip benchmark's
matching straps cross the whip axis exactly this way). antennaknobs'
engines junction wires at wire ends, so the import shatters such wires at the
shared boundary: same segments, same boundaries, and the crossing becomes the
real junction NEC's connection rule implies.

## Loading, feedlines, and networks (`network=True`)

`read_nec(self, name, network=True)` additionally translates the deck's
`LD`/`TL`/`NT` cards into the workbench's own port-network branches
(`antennaknobs.network`: `Load`, `TL`, `TwoPort`, `Shunt` — the same system
the trap dipole and station designs use), wherever it can express them
*exactly*:

| Card | Translation |
| --- | --- |
| `LD` type 0/1 (lumped series/parallel RLC) | A `Load` per segment in the card's range (expanded up to 8 segments), on a named 1-segment wire split out of the host wire |
| `LD` type 4 with X = 0 (pure resistance) | `Load(r=…)` |
| `LD` type 5 over the whole structure (wire conductivity) | `deck.conductivity`, baked into every `wire_tuples(specs=True)` spec (or feed it to `WireSpec` in `build_wire_material`) |
| `LD` type 5 on a tag/range covering whole wires | Per-wire conductivity (`deck.wire_conductivity`), baked into those wires' `specs=True` specs — a ranged card wins over the whole-structure one |
| `TL` | A `TL` branch: negative z0 (NEC's crossed line) becomes `transposed=True`, zero length resolves to the port separation, conductance-only end admittances become `Shunt(r=1/G)` |
| `NT` with an all-real Y matrix | Its exact resistive pi: a series `TwoPort` between the ports plus a `Shunt` at each |

`deck.wire_tuples()` then emits *named* wires at every attachment point (no
legacy `ex` markers) and `deck.network()` returns the matching `Network` —
the deck's `EX` cards become its `Driven` sources — ready to return from
`build_wires` / `build_network` as in the quick start above. A deck with no
network cards still works identically: `network()` is then just the drive.

What cannot be translated exactly stays out, with a per-card reason in
`deck.ignored_detail` (rendered by `skipped_note()`): frequency-independent
reactance (`LD` 4 with X ≠ 0, susceptance in `TL`/`NT` admittances — NEC's
constant-B convention has no R/L/C equivalent), distributed per-metre RLC
(`LD` 2/3), an `LD` 5 range covering only *part* of a wire's segments
(per-wire specs cover whole wires only), and an `LD` landing on a segment
that also has a `TL`/`NT` connection (NEC composes those in series inside
the segment, which the port model doesn't express).

## What is *not* applied

A deck also carries run configuration, which the workbench manages itself.
Those cards are recorded in `deck.ignored` rather than translated:

- `GN`/`GD` ground and the `GE` ground flag — the workbench applies **its own
  ground model** (`deck.ground` tells you the deck wanted one)
- `LD` loading, `TL`/`NT` feedlines and networks — unless imported with
  `network=True` as above
- `FR` sweeps (harvested into `deck.freq_mhz`), `RP`/`NE`/`NH`/`XQ` output requests

Expect readouts to differ from a deck's published numbers when those numbers
relied on its ground or on cards the translation could not express.

`deck.skipped_note()` turns that record into one human-readable sentence
("Deck cards not applied: LD (loading), RP (radiation-pattern request); the
deck models a ground plane — …"), or `None` when the deck carries nothing the
workbench overrides. Deck-backed design stubs put it under
`ui_params["notes"]` and the workbench shows it beneath the antenna selector,
so the mismatch is explained right where the deck is viewed.

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
| `loads`, `tls`, `nts` | The translated LD/TL/NT records (`network=True` only) |
| `conductivity` | Whole-structure `LD` 5 wire conductivity in S/m, or `None` |
| `ignored_detail` | `(mnemonic, reason)` per card `network=True` still could not translate |

plus four methods: `wire_tuples()` (the deck as `build_wires()` tuples;
raises if no voltage source drives the antenna), `network()` (the translated
cards + `EX` drives as a `Network`, `network=True` only),
`dominant_radius()`, and `skipped_note()` (the not-applied record as one
informational sentence, reasons included).
