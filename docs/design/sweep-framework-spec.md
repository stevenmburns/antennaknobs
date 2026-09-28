# Sweep framework, step 1: the analysis spec (proposal for A1 and A2)

Status: **proposal, for Steve's decision.** Nothing here is built. This page
answers axis A1 (what `build_analyses()` returns) and the part of A2 that the
examples force (knob roles). It is tested on paper against all seven driving
examples in `sweep-framework-examples.md`: if an example needs a special
case, the types are wrong. The names are proposals too; renaming is cheap now
and expensive later.

## The shape in one paragraph

An **analysis** is a declarative, frozen value that a design's
`build_analyses()` returns, and nothing runs when it is built. It has:

- ONE **sweep**, the thing on the x axis: a knob, or a role such as
  frequency, density or height. It can have a range or explicit values, lin
  or log.
- Zero or more **crosses**, the things compared as separate curves: engines,
  grounds, measurement planes, designs, or a second knob's values (a family).
- The **views** it draws: R/X, SWR, S11, Smith, a map, a table.
- The **references** drawn on them: R = Z0, X = 0, an SWR threshold.

The CLI and the workbench both read the same value. An analysis prints back
as the Python that makes it, which is what the UI's "suggest the commands"
needs.

## The types

```python
from antennaknobs import analyses as an

# ── what varies: the x axis ─────────────────────────────────────────────
an.Sweep(
    knob,  # a knob name ("length_factor"), or a role:
    #   an.FREQUENCY, an.DENSITY, an.HEIGHT
    lo=None,
    hi=None,  # None: the design's own (see "Defaults")
    points=None,  # None: the role's / knob's default count
    values=None,  # explicit values instead of lo/hi/points
    spacing="lin",  # "lin" | "log"
)

# ── what is compared: one curve per combination ─────────────────────────
an.Cross(engines=("momwire:bspline", "nec5"))  # engine specs, as --engine takes
an.Cross(grounds=("free", "finite:13,0.005"))  # ground specs, as --ground takes
an.Cross(planes=("rig", "feed"))  # measurement planes (network ports)
an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex"))  # other designs/variants
an.Cross(step=an.Sweep("angle_deg", values=(0, 15, 30)))  # a family over a 2nd knob

# ── what is drawn on it ──────────────────────────────────────────────────
an.Ref(r=(50,), x=(0,), swr=2.0)  # reference lines; z0 comes from the session

# ── the analysis ─────────────────────────────────────────────────────────
an.Analysis(
    name,  # shown in the workbench's picker and the CLI's list
    sweep,  # a Sweep, or (Sweep, Sweep) for a map
    cross=(),  # Cross or a tuple of them: their product
    views=("rx",),  # "rx" | "swr" | "s11" | "smith" | "map" | "table"
    references=an.Ref(),
    ground=None,
    engine=None,  # None: the session's own
)

# ── the library (A2): generic analyses for any design ──────────────────────
an.convergence(**kw)  # Analysis("convergence", Sweep(an.DENSITY),
#          views=("rx", "table", "smith")) + **kw
an.band_swr(**kw)  # Analysis("band SWR", Sweep(an.FREQUENCY),
#          views=("swr",), references=Ref(swr=2.0)) + **kw
an.knob(name, **kw)  # Analysis(name, Sweep(name), views=("rx", "smith")) + **kw
```

### Roles (A2)

A role says what a knob MEANS, so a generic analysis can find it on any
design. It is declared where the per-knob UI metadata already lives:

```python
default_params = {
    "base": 7.0,
    "ui_params": {"base": {"min": 1.0, "max": 16.0, "role": "height"}},
}
```

- `an.FREQUENCY` is built in: the measurement frequency.
- `an.DENSITY` defaults to `nominal_nsegs` on a catalog design. A deck
  declares its own. A SimNEC `JamSegments($segs)` knob gets
  `role: "density"` from the importer.
- `an.HEIGHT` and any future role must be declared.
- A role the design lacks makes the analysis **unavailable on that design,
  by name** ("this design declares no height knob"). It is not an error.

### Defaults ("the design's own")

| sweep | `lo`/`hi`/`points` when None |
|---|---|
| `an.FREQUENCY` | the design's measurement range. For a deck, its own sweep (a SimNEC Generator sweep, an `FR` card). Otherwise the workbench's band policy. |
| `an.DENSITY` | the app's ladder, 8…68 (7 rungs) |
| a knob or another role | the knob's `ui_params` min/max, 11 points |

### Crossing, and refused cells

- Several `Cross` values multiply: engines × designs gives one curve per
  pair.
- A combination an engine cannot serve (NEC-2 on the apex knot, E7) is a
  **refused cell**. It is drawn as a named gap in the legend, and the rest
  of the analysis runs.
- A curve cap applies (instruments use 4, Gleicher says superposition is
  poor past 2–3). A product over the cap is refused when the analysis is
  **listed**, not when it runs.

### What the spec deliberately leaves out

- **Layout** (which pane, how many graphs): the view decides. §3.2
  principle 6 is still open.
- **Pins:** a pin is data captured from a run of an analysis, never part of
  the spec.
- **Imperative hooks:** there is no `custom=callable` (A1 (c)) until an
  example needs one. None of the seven does.

## The seven examples, written in it

**E1, convergence on three engines:**

```python
def build_analyses(self):
    return [
        an.convergence(
            cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec5")),
            ground="finite:13,0.005",
        ),
    ]
```

**E2, tuning two knobs to a Z0:**

```python
def build_analyses(self):
    lf = an.Sweep("length_factor", 0.90, 1.06, points=33)
    refs = an.Ref(r=(50, 75), x=(0,))
    return [
        an.Analysis(
            "tuning family",
            lf,
            cross=an.Cross(step=an.Sweep("angle_deg", values=(0, 15, 30, 45, 60))),
            references=refs,
        ),
        an.Analysis(
            "tuning map",
            (lf, an.Sweep("angle_deg", 0, 60, points=25)),
            views=("map",),
            references=refs,
        ),
    ]
```

**E3, R/X against height, three grounds** (the invvee's `base` declares
`role: "height"`):

```python
def build_analyses(self):
    return [
        an.Analysis(
            "height",
            an.Sweep(an.HEIGHT, 2, 20, points=37),
            cross=an.Cross(grounds=("free", "finite:13,0.005", "finite:5,0.001")),
            references=an.Ref(r=(50,), x=(0,)),
        ),
    ]
```

**E4, band SWR on the deck's own sweep** (this is also the deck stub A4
would generate, since `an.FREQUENCY` with no range means the file's
14.0–14.35 MHz):

```python
def build_analyses(self):
    return [an.band_swr(swr_scale="rho")]
```

**E5, one sweep at three network planes:**

```python
def build_analyses(self):
    return [
        an.band_swr(
            name="rig vs antenna",
            cross=an.Cross(planes=("rig", "T1", "feed")),
            views=("swr", "rx"),
        ),
    ]
```

**E6, convergence through the deck's own density knob** (the importer marks
`tmp_segs` with `role: "density"`):

```python
def build_analyses(self):
    return [
        an.convergence(
            sweep=an.Sweep(an.DENSITY, 10, 500, points=20, spacing="log"),
            cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec5")),
        ),
    ]
```

**E7, two feed spellings on one convergence chart** (NEC-2 × apex is a
refused cell):

```python
def build_analyses(self):
    return [
        an.convergence(
            cross=(
                an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex")),
                an.Cross(
                    engines=("momwire:bspline", "momwire:razor-2p", "nec5", "nec2")
                ),
            ),
        ),
    ]
```

**What writing them showed:**

- **No special case was needed.** Every example is a sweep, crosses, views
  and references.
- **Two small additions came from the examples**, not from design ahead of
  them:
  - `swr_scale` (E4) is a view option. It's the one keyword here that isn't
    in the types above, so either views take options, or the SWR view is
    `("swr", "rho")`. See Q2.
  - `name=` overriding a library default (E5).
- **The library carries most of the weight.** Four of the seven are one
  library call with keywords. That's A2's case for option (a), a shared
  library, over inheritance alone.

## Questions for Steve (the decisions this step needs)

1. **Declarative specs (A1 (a)).** Yes or no. This whole page assumes yes.
2. **View options.** Should views take options (`views=(an.Swr(scale="rho"),
   "rx")`), or stay strings with a few spelled variants? I lean to objects,
   because E4's scale and E2's map both want parameters.
3. **Roles in `ui_params`,** beside `min`/`max`/`hidden`, rather than a
   separate class attribute. I lean `ui_params`, since it's one place per
   knob.
4. **Crossing multiplies.** Two crosses give their product, with a curve
   cap enforced at listing time. Is the cap 4, as for pattern pins, or 6?
5. **Library names:** `convergence`, `band_swr`, `knob`. And one module,
   `antennaknobs.analyses`, imported as `an`?

When these are settled, step 2 (the CLI-first implementation of E1, E3 and
E6) can start from this page.
