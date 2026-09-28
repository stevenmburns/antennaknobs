# Sweep framework: driving examples

Companion to `sweep-framework.md`. These are the three concrete analyses that
axes A1–A4 (§4 there) must serve, chosen by Steve on 2026-09-28. Each is real:
the chart, the numbers and the commands below were produced from the released
antennaknobs 0.90.0 / momwire 0.66.0 on the default inverted vee
(`dipoles.invvee`, 28.47 MHz, 7 m apex, 31.7°) over average ground
(εr 13, σ 0.005 S/m, Sommerfeld-Norton).

For each example:

- the question it answers;
- how it is drawn today;
- what neither tool can do yet;
- a *strawman* of the Python that would declare it, written against A1's
  option (a), declarative specs.

The strawman API is invented for this page. Its names are placeholders for A1
and A2 to decide, not a proposal.

---

## E1. Convergence, several engines

**The question.** Is the answer I am reading converged, and do the engines
agree once they are?

![E1](sweep-framework-examples/ex1_convergence.png)

**Today.** The CLI draws it in one command (4.6 s):

```
NEC5_EXE=~/bin/nec5-licensed antennaknobs sweep --builder dipoles.invvee \
  --param nominal_nsegs --engine momwire:bspline,momwire:razor-2p,nec5 \
  --ground finite:13,0.005 --overlay
```

| engine | extrapolated Z |
|---|---|
| momwire:bspline | 48.912 − j8.016 |
| momwire:razor-2p | 48.874 − j8.405 |
| NEC-5 | 48.870 − j8.444 |

- razor-2p's extrapolation lands within 0.04 Ω of NEC-5's; B-spline's is
  0.43 Ω higher in X.
- B-spline is nearly flat across the ladder: R moves 0.05 Ω and X 0.7 Ω,
  against 1.0 Ω and 7.9 Ω for razor-2p and NEC-5. All three approach from
  below in X.
- (0.90.0 prints the older "Z*" label; the next release reads Z∞, with one
  estimator in both tools, #1782.)

**Missing.** The workbench runs a density sweep on the active slot only. It
cannot overlay engines.

**Strawman.**

```python
def build_analyses(self):
    return [
        analyses.convergence(
            engines=("momwire:bspline", "momwire:razor-2p", "nec5"),
            ground="finite:13,0.005",
        ),
    ]
```

**What it asks of the spec:**

- a list of engines, so an analysis is not bound to the active slot;
- a ground that can differ from the session's;
- no knob names at all, so the same spec applies to ANY design. That is the
  A2 case for a shared library: `analyses.convergence()` is generic.

---

## E2. Tune two knobs to a Z0

**The question.** Which length and apex angle make this inverted vee resonant
at 50 Ω, or at 75 Ω?

![E2](sweep-framework-examples/ex2_tuning.png)

**Today.** Neither tool draws it. The chart above is a one-off script
(`scratch/sweep-examples/ex2_tuning.py`, 825 solves in 11.8 s on momwire
B-spline):

- **Left, a family:** R/X against length_factor, one pair per apex angle.
  Resonance moves little with angle; R falls steeply as the arms droop.
- **Right, a tuning map over (length_factor, angle):** the X = 0 contour
  against the R = 50 and R = 75 contours, over |Γ| on 50 Ω.
  - **50 Ω:** X = 0 crosses R = 50 at about 32.5° and length_factor 0.978. The
    catalog default (31.7°, 0.972) was tuned to 50 Ω, and the map agrees.
  - **75 Ω is not reachable at this height.** The largest resonant R is about
    66 Ω, flat (0°). The R = 75 contour never meets X = 0 in range.

**Missing.**

- A family of curves over a second knob is #1757's phase-2 step 2, not
  built.
- The 2-D map is named there only as "a later option".
- The workbench's optimizer finds a match but draws no picture of where the
  matches are.

**Strawman.**

```python
def build_analyses(self):
    lf = analyses.knob("length_factor", 0.90, 1.06, points=33)
    return [
        analyses.family(
            x=lf,
            step=analyses.knob("angle_deg", values=(0, 15, 30, 45, 60)),
            references={"R": (50, 75), "X": (0,)},
        ),
        analyses.tuning_map(
            x=lf, y=analyses.knob("angle_deg", 0, 60, points=25), z0=(50, 75)
        ),
    ]
```

**What it asks of the spec:**

- more than one swept knob;
- explicit values as well as ranges;
- reference lines (R = Z0, X = 0);
- views beyond R/X vs x: a map. So a spec names the view it wants, and one
  sweep can feed several views.
- The 75 Ω result is also a finding about composition. The next knob to reach
  for is height, which is E3.

---

## E3. R and X against mast height

**The question.** How does the feed impedance wander as I raise the antenna,
and where does it settle?

![E3](sweep-framework-examples/ex3_height.png)

**Today.** Both tools draw it:

- the CLI: `antennaknobs sweep --builder dipoles.invvee --param base --range 2
  20 --npoints 37 --ground finite:13,0.005` (4.4 s);
- the workbench's Z-vs-parameter view, on `base`.

R and X oscillate with a period of about 5.3 m, which is λ/2 at 28.47 MHz:
the ground reflection's phase at the feed turns once per half wavelength of
height. The swing shrinks as the antenna rises: R runs 48–67 Ω near the
ground and 52–58 Ω above 13 m.

**Missing.**

- There's no reference to read the wiggle against: the free-space value, or
  the λ/2 marks.
- The ground cannot be compared inside one analysis (free vs average vs poor
  soil).
- The height knob has a different name in different designs (`base` here),
  so a generic "height sweep" needs the design to say which knob is its
  height.

**Strawman.**

```python
def build_analyses(self):
    return [
        analyses.knob(
            "base",
            2,
            20,
            points=37,
            grounds=("free", "finite:13,0.005", "finite:5,0.001"),
            references={"R": (50,), "X": (0,)},
        ),
    ]
```

**What it asks of the spec:**

- a comparison dimension that is not a knob (the ground). The same shape as
  E1's engines, so a spec may cross its sweep with engines OR grounds.
- Reuse across designs needs a knob ROLE ("height") or a design-provided
  name.

---

## What the three ask of A1–A4, together

| need | E1 | E2 | E3 | axis |
|---|---|---|---|---|
| list without solving, print back as code | ✓ | ✓ | ✓ | A1 (a) |
| cross a sweep with engines / grounds | engines | | grounds | A1 |
| more than one swept knob; explicit values | | ✓ | | A1 |
| name the views one sweep feeds (R/X, Smith, map) | | ✓ | | A1 |
| reference lines (Z0, X = 0) | | ✓ | ✓ | A1 |
| generic across designs | ✓ (no knobs) | | needs a height role | A2 |
| one analysis leads to the next | | 75 Ω → height | | later |

Cost is not the obstacle on this design: E2's 825-solve grid takes 12 s.
Larger designs will need the grid to be admitted by cost, as the hosted
instance already does for sweeps.
