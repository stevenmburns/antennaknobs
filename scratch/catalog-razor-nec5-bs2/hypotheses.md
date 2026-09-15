## 7. What the tail is made of

The distributions above have a long thin tail and a very quiet body: **7 of 340**
razor-vs-NEC-5 rows exceed 2 %, **6** exceed 5 %, and those 6 are **three
designs**. The remaining 333 rows sit at a 0.066 % median. So the interesting
question is not "how big is the disagreement" — it is "what are those three".

### Hypothesis A — a segment-length step at the source. FALSIFIED.

The obvious candidate, and NEC's own thin-wire guidance makes it the first one
to try: adjacent segments should not differ in length by much more than 2:1, and
every one of the three offenders has a short feed wire sitting next to long arm
segments. `dipoles.pota_invvee` steps 4.94:1 at the source and is the worst row
in the study.

It does not survive contact with the catalog. Measured two ways — the feed
segment against the median segment of every longer wire, and (the honest
version) the feed segment against only the wires that **share an endpoint with
it** — the step does not predict the gap:

| design | source step | \|ΔX\| razor−NEC-5 |
|---|---:|---:|
| `loops.triangular_skyloop` | 18.97 : 1 | 0.0899 Ω |
| `multiband.fandipole` | 10.39 : 1 | 0.1991 Ω |
| `verticals.raised_vertical` | 9.97 : 1 | 0.0303 Ω |
| `verticals.vertical` | 4.99 : 1 | 0.0243 Ω |
| **`dipoles.pota_invvee`** | **4.94 : 1** | **7.9748 Ω** |

An 18.97:1 step is clean to 0.09 Ω and a 4.94:1 step is the worst row in the
catalog. The hypothesis is recorded here because it was tested, not because it
worked — and the first version of the measurement was worse than useless: it
took the median segment length over every wire longer than the feed, which on a
trap or a matching stub answers about a gap somewhere else on the antenna
entirely. `probe_jacket.py:source_step` uses only the wires that share an
endpoint with the fed wire. Both definitions falsify the hypothesis; only the
second one is measuring what the hypothesis is about.

### Hypothesis B — discretisation. FALSIFIED.

Razor and NEC-5 are both first order in the mesh, so if the gap were
discretisation it would shrink as the mesh refines. `probe_jacket.py` section 1
walks a 21 → 161 ladder (a 7.4× segment count) in free space:

| design | ΔX at 41 segs | at 77 | at 152 | at 303 |
|---|---:|---:|---:|---:|
| `dipoles.pota_invvee` | 7.9748 Ω | 7.9856 | 8.0211 | 8.0555 |
| `dipoles.invvee_catenary` | 5.4088 Ω | 5.4385 | 5.4748 | 5.5329 |
| `dipoles.invvee` (control) | 0.0374 Ω | 0.0372 | 0.0380 | 0.0380 |

Flat, and if anything very slightly widening. The mesh error that *does*
converge is visible in the same table — razor closes on bs2 from 2.9 Ω to 0.56 Ω
of X on the control as the mesh refines, exactly as the `RazorFarMeshClass`
advisory says it should. The razor↔NEC-5 offset is not that; it is a constant.

It is also **ground-independent**: 7.9748 Ω free vs 7.9692 Ω over Sommerfeld on
`pota_invvee`. A constant series reactance that ignores both mesh and ground is
not a radiation difference. It is something lumped into the wire.

### Hypothesis C — the insulation jacket. CONFIRMED.

Exactly **3 of the 103** catalog designs default to a PVC-jacketed `wire_type`:

    dipoles.invvee_catenary   18-awg-pvc
    dipoles.pota_invvee       22-awg-pvc
    wire.efhw_sloper          28-awg-pvc

They are the same three designs, and the only three, whose razor-vs-NEC-5 rows
exceed 5 %. Removing the jacket and changing nothing else settles it:

| `pota_invvee`, free space | razor | NEC-5 | rel\|ΔZ\| |
|---|---|---|---:|
| `wire_type = 22-awg-pvc` | 53.6022 − 8.1782j | 53.1480 − 16.1530j | **14.38 %** |
| `wire_type = 22-awg` | 50.8918 − 73.2323j | 50.8890 − 73.2740j | **0.047 %** |

14.38 % → 0.047 %, which is *below* the catalog median of 0.066 %. The
formulation twins agree on this design to four figures; what they disagree about
is the jacket.

**Where the two spellings live.** NEC-5 has no native insulated-wire card — the
3.2/3.3 roster carries no `IS`, NEC-4's card did not survive — so
`engines/nec5.py:_build_material_lines` emulates the jacket as an `LD 2` card
carrying King's quasi-static series inductance L′ (H/m), which NEC distributes
over the tagged segments. momwire's lane does not go through a card at all:
`engines/momwire.py` passes `insulation_radius` / `insulation_eps_r` into the
solver's own loading path. Two routes to the same physics, differing by a
per-design constant — 7.97 Ω on `pota_invvee` at 14.1 MHz, 5.44 Ω on
`invvee_catenary` at 28.47 MHz.

**bs2 is on razor's side of it.** On jacketed `pota_invvee`, bs2 reads
−5.2408j and razor −8.1782j while NEC-5 reads −16.1530j; both momwire lanes sit
together and the NEC-5 emulation is the outlier. That is what you would expect
if the difference is the route rather than the basis, and it is the reason this
section names the LD-2 emulation as the thing to look at rather than razor.

`wire.efhw_sloper` is the same cause with a different signature — its gap is
11.4 % in **R** and 3.4 % in X, not the reverse — because its port sits behind a
49:1 end-fed transformer network, which re-refers a feed-region series term into
the resistive part. Same three designs, same single cause.

### The fourth confound

`PLAN.md` registered three confounds. This is a fourth, it was not anticipated,
and it dominates the razor-vs-NEC-5 tail completely. Stated plainly so the
headline is not over-read:

> **The 0.066 % median is a formulation result. The 5–14 % tail is not — it is
> the insulated-wire model, and it would be there between any two engines that
> spell the jacket differently.** Excluding the three jacketed designs, the
> worst razor-vs-NEC-5 row in the whole catalog is `verticals.four_square` at
> **2.0 %**, and the next is 1.86 %.

Not fixed here, per the brief. What a fix would need is a decision about which
spelling is right, which is a momwire/NEC-5 question and not one this study is
positioned to answer: neither engine is a truth oracle, and the bare-wire
control only shows that they agree when the jacket is absent.

## 8. Reproducing

```
NEC5_EXE=<path to nec5cl-3b75639> \
  python scratch/catalog-razor-nec5-bs2/run_catalog.py \
    --out scratch/catalog-razor-nec5-bs2/records.jsonl
python scratch/catalog-razor-nec5-bs2/report.py > scratch/catalog-razor-nec5-bs2/README.md
NEC5_EXE=<path> python scratch/catalog-razor-nec5-bs2/probe_jacket.py \
  > scratch/catalog-razor-nec5-bs2/probe_jacket.txt
```

618 cells in 630 s on this box. The NEC-5 binary is licensed (LLNL-CODE-746721)
and lives outside this repo; nothing in this directory contains its source, its
printouts or any per-deck NEC-5 output — only impedances and aggregates.
