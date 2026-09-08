# 2026-09-08 — razor-2p on vertex-port designs: measured

## Why

`_VERTEX_PORT_WITHHELD = ("razor-2p",)` (antennaknobs#1264) records that
`RazorSolver` **serves** momwire's series node gap (momwire#603) and solves the
catalog's vertex-port design, but is not offered as a tab because nobody had
driven that path. This is that drive. **No code changed and no tab list moved**
— this document and its `.jsonl` are the whole output.

## The count, first, because it shapes everything else

Enumerated from the registry rather than assumed: every one of the **103**
catalog designs had its network built and its ports typed.

> **Exactly one design carries a `PortAtVertex`: `dipoles.invvee_apex`.**

A tab decision resting on one geometry is thin, so the sweep varies that
design's **own declared `ui_params` ranges** — `angle_deg` 0–60, `base` 1–16,
`length_factor` 0.8–1.25 — one knob at a time around the default, plus three
corners: **10 parameter points**. Those are the knobs a user can move behind
the tab, so the sample is the space the decision is about rather than decks
invented for the occasion.

240 cells: 10 points × 2 grounds × 3 engines × 4 rungs (21/42/84/168), plus a
13-cell fine ladder on the default geometry out to n=1344. **0 errors.**

## Method

Skylake (`smburns-Z170-WS`, 4 cores), antennaknobs `7dab8ba18c2c`, momwire
`d6340aba0d14`, numpy 2.5.2, BLAS pinned through
`bench_nec_corpus.apply_server_thread_policy` — the same pin the catalog cost
ladder runs under, so these numbers are comparable with it. All SHAs in the
file's `_meta`.

One cell per subprocess (`ru_maxrss` is a high-water mark). Warm timing with
`_solved_cache` cleared — the #1235 cache trap, where a second `impedance()`
on an unchanged engine is a dict lookup and reads as a 1,300× speedup.

**The reference is a PAIR.** `bs2` and `sinusoidal-galerkin` are two
independent converged formulations, and their **spread** is the yardstick.
Comparing razor against one of them would score the pair's own disagreement as
razor's error.

`razor-2p` is measured as the **tab's preset** (`nec5_quadrature=True`), not a
bare `RazorSolver`: measuring the unbound class would answer about a
configuration no tab offers.

### Two instrument bugs, found before any table existed

- **The advisory column was silently empty.** The first spelling wrapped
  `eng.impedance()` in `warnings.catch_warnings(record=True)` and recorded
  **zero** advisories for every razor cell. `@_captures_advisories` already
  catches them *inside* the engine and absorbs them into
  `_advisory_recorder`, so nothing propagates to an outer recorder. It would
  have reported "razor raises no advisory here", which is the opposite of
  true. Fixed by reading `eng.advisories`.
- **Parameters never reached the geometry.** `Builder(**params)` raises —
  `AntennaBuilder.__init__` takes no design knobs, they are attributes seeded
  from `default_params`. The harness now sets them and **rejects an unknown
  knob**, so a typo fails loudly instead of quietly measuring the default
  geometry ten times.

## Does razor sit inside the bs2/sing spread?

**No, at every mesh anyone would run.** At the coarse grid's finest rung
(n=168) razor is outside the pair spread on **14 of 20** (parameter × ground)
cells, by 8–16×.

The six that look "inside" are not razor doing better — they are the
**yardstick blowing up**. They are all `length_factor` extremes, where the
arms are far off resonance and the two references themselves disagree by
1.8–3.0 Ω. Razor's own deviation stays 0.34–1.05 Ω throughout:

| parameter point | ground | pair spread | razor dev | verdict |
|---|---|---|---|---|
| default | free | 0.0402 | 0.4996 | 12.4× outside |
| default | finite 13/0.005 | 0.0314 | 0.4985 | 15.9× outside |
| angle_deg=7.2 | finite | 0.0516 | 0.6102 | 11.8× outside |
| angle_deg=52.8 | free | 0.0409 | 0.3397 | 8.3× outside |
| length_factor=1.196 | free | **1.8337** | 0.4756 | "inside" — pair disagrees |
| angle_deg=52+base=2.5+lf=1.2 | finite | **2.9932** | 1.0520 | "inside" — pair disagrees |

Reading those last two as passes would be scoring razor against a broken
ruler.

`base` has no effect in free space and the rows are identical to the default
there — correct (it is height above a ground plane), and a useful check that
the harness responds to geometry at all, since `angle_deg` and
`length_factor` plainly do.

## Does its step shrink with refinement, and what does first order cost?

**It shrinks, every time: 40/40 step ratios below 1**, min 0.46, median 0.57,
max 0.67 per doubling. momwire#845's "first order in the far mesh, so doubling
the segment count roughly halves the error" holds on this design.

The fine ladder (default geometry, free space) shows what that buys:

| n | segs | bs2 | sinusoidal-Galerkin | razor-2p | pair spread | razor dev | × |
|---|---|---|---|---|---|---|---|
| 168 | 326 | 54.4974 −11.9604j | 54.5144 −11.9239j | 54.4305 −12.4360j | 0.0402 | 0.4996 | 12.4 |
| 336 | 654 | 54.5041 −11.8945j | 54.5168 −11.8668j | 54.4646 −12.1993j | 0.0305 | 0.3220 | 10.6 |
| 672 | 1306 | 54.5086 −11.8415j | 54.5198 −11.8169j | 54.4861 −12.0374j | 0.0270 | 0.2101 | 7.8 |
| 1344 | 2612 | 54.5098 −11.7996j | 54.5229 −11.7709j | 54.5002 −11.9186j | 0.0316 | 0.1343 | **4.3** |

**The reassuring half: razor converges to the same answer.** Its deviation
falls monotonically and its trajectory heads into the pair, so this is a
*cost* problem and not a *correctness* one — which is the finding that would
have been a reason to refuse the tab outright, and it is not what happened.

**The deciding half: the cost is out of reach.** The deviation ratio is a
stable **0.64 per doubling** across all three doublings (0.644 / 0.653 /
0.639). Extrapolating that — and it is an extrapolation, from three
consistent doublings — razor needs **3.3 further doublings**, about
**n = 13,000 (≈25,800 segments)**, to bring its deviation inside the pair
spread. The finest mesh here, 2,612 segments, already costs razor 944 MB.

### Cost at matched mesh, and at matched accuracy

| n | bs2 ms | sing ms | razor ms | bs2 MB | sing MB | razor MB |
|---|---|---|---|---|---|---|
| 168 | 110 | 138 | **24** | 137 | 127 | 120 |
| 336 | 249 | 316 | **68** | 244 | 199 | 179 |
| 672 | 704 | 1012 | **241** | 642 | 470 | 355 |
| 1344 | 2524 | 4024 | **1143** | 2137 | 1554 | 944 |

Razor is **the cheapest engine at matched mesh** — 4–5× faster than bs2 and
smaller in memory at every rung. That is the case *for* the tab, and it is
real.

It does not survive the change of denominator. Razor at n=1344 (1,143 ms,
944 MB) is still 4.3× outside a spread that **bs2 reaches at n=168 for
110 ms**. At matched *accuracy* razor is roughly an order of magnitude more
expensive, and the mesh that would close the gap is not one this box runs.

## Advisories and refusals

`razor-2p` raises `RazorFarMeshClass` on **every** cell — the mesh-class
advisory momwire#845 added, which says in prose exactly what the tables above
say in numbers. `bs2` and `sinusoidal-galerkin` raise none. **No engine
refused any cell**; there is no vertex-port geometry here that razor declines.

## Recommendation

**Keep `razor-2p` withheld from the vertex-port tab list.** Not because it is
wrong — it serves the node gap, refuses nothing, and converges to the same
impedance the two reference formulations do — but because the one design that
would use the tab is the design where its first-order convergence is least
affordable. On every parameter point where the reference pair agrees to better
than 0.1 Ω, razor sits 8–16× outside that agreement at the finest mesh a user
would run, and closing the gap needs roughly ten times the segments of the
finest mesh measured here. The tab would offer a cheaper solve whose answer is
half an ohm of reactance away, on a design whose whole purpose
(`dipoles.invvee_apex`'s docstring) is to measure a **2.2 Ω** difference
between two feed models — an error a third the size of the effect the design
exists to show. The case would change if razor's node-gap path were ever
wanted for its speed on a much larger vertex-port deck, and there is no such
deck in the catalog today; that, rather than this measurement, is what should
reopen the question.

## Data

`docs/status/2026-09-08-razor-vertex-port-ladder.jsonl` — 253 lines: one
`_meta`, 240 grid cells, 12 fine-ladder cells. Regenerate with

```
python scripts/bench_vertex_port_razor.py --out <path>.jsonl
python scripts/bench_vertex_port_razor.py --out <path>.jsonl --fine
```
