# momwire bs2 against NEC-5 over the public NEC corpus

**Evidence, not a scoreboard.** AK#896. Measured 2026-09-11 on antennaknobs
`746c641d0` and momwire **0.53.0**, imported from the editable submodule at
`23d81e5` (tag `v0.53.0`, clean working tree) rather than from a wheel, running
the portal's default basis **momwire bs2 (B-spline, d=2)**. "momwire" alone
names a package and not a solver — the portal's roster carries seven bases that
disagree with each other by design — so the artifact records the basis, its
solver class and degree, and the banner they were read from, beside the version,
commit and import path. Which build and which basis answered is recoverable from
the data and not only from this line.
Skylake box, over the 21 public deck collections
`scripts/nec5_corpus/nec5_corpus.py fetch` knows about. 3,076 decks, 889 s on
the momwire side. Per-deck momwire rows in
`data/2026-09-11-corpus-census-momwire.jsonl`.

## What this census can and cannot say

It reports **how far apart two formulations land on the decks people actually
published, at the mesh densities those people chose**. That is all it reports.

It does **not** say which engine is closer to the truth on any deck. Deciding
that needs a mesh ladder and a limit extrapolation per deck — the #872 / #890
machinery — and this census is the instrument that finds the cases worth
spending that on, not a substitute for it. A deck where the two disagree is a
*question*; the census's job is to turn three thousand decks into a short,
ranked, reproducible list of them.

Read the headline with that in mind. A median disagreement of 11 % at
author-chosen density is the **convergence-rate gap made visible at scale**: a
coarse deck leaves the O(1/N) formulation further from its own limit than the
B-spline basis is from the same limit, so the gap at N-as-published is expected
to exceed the gap at N-as-converged. This measures the first. Only a ladder
measures the second.

## Method

- **Decks**: the translated tree — the same bytes into both engines.
- **NEC-5 side**: the existing `check` report, unchanged.
- **momwire side**: `scratch/896-census/census_momwire.py`, one deck per
  subprocess under a 300 s wall timeout and a 6 GB address-space rlimit.
- **Join**: `compare`'s own `_first_z` — row 0 of the first frequency's
  ANTENNA INPUT PARAMETERS on each side.
- **Regenerate**: `scratch/896-census/census_report.py --nec5 <a> --momwire <b>`.
  The committed script reproduces every table on this page byte for byte from
  the two reports; checked rather than claimed.

**The census itself is deterministic.** Run three times end to end on the same
box — 891 s, 889 s and 889 s — the reports agree on every row: status, error
text, impedances and advisory classes alike, with only the wall clock excluded.
The third run differs from the first on exactly **6 rows of 3,076**, and only
because it applies the `no-drive` status introduced below; nothing else moved,
which is the check rather than an exception to it.
That matters more here than it would for a benchmark: a census whose refusals or
impedances wandered between runs could not support a named-case list, because
nobody could tell a finding from a re-roll.

## Why the translated decks, and what that costs

The obvious choice is the raw NEC-2 decks — momwire speaks NEC-2, the translated
tree is NEC-5 dialect. Measured on one 150-deck sample, that choice is wrong by
22 points: momwire answers **122/150 (81 %)** translated against **88/150
(59 %)** raw.

`SY` is why. 4nec2's symbolic-variable card appears in **680 raw decks and none
of the translated ones**, because `translate` expands it. Running raw would drop
the corpus's most heavily parameterised models and report the gap as a momwire
limitation, which it is not. Translated also makes the join exact by
construction.

The cost is ours and is the single largest refusal below: **175 decks lost to
`LD 5` on a partial-wire range.** NEC-5 addresses knots where NEC-2 addresses
segment centres, so `translate` remeshes a wire to put a referenced centre on a
knot and remaps the references — by design. The side effect is that a
**whole-wire** `LD 5` stops being whole-wire: `GW 1 25` with `LD 5 1 1 25`
becomes `GW 1 50` with `LD 5 1 2 50`, and momwire's nec2 dialect, which carries
per-wire conductivity but not partial ranges, refuses it. Whether `2 50` is the
right remap is a question for whoever owns `translate`; that it converts a
whole-wire load into a partial one is the part that costs this census 175 decks.

It does **not** bias the comparison: both engines read the same translated bytes,
so every deck that got through was the same antenna on both sides.

## Two checks without which none of the numbers below would mean anything

**The join could have been comparing different ports.** `_first_z` takes row 0
on each side; had the engines ordered their sources differently, the result
would have looked exactly like physics. The report publishes the check rather
than the assurance — and it **fired**: one deck addresses a different segment on
each side and is excluded by name. Ten more list different source counts, which
is a listing limit with an identical row 0, and are kept.

**The tolerance could have been inherited.** `compare`'s 1e-4 default is right
for diffing two builds of one engine, where the last printed digit is the noise
floor. Cross-engine it marks essentially everything as moved. The headline is
therefore a distribution, and the tail is **ranked symmetrically**: `compare`
divides by |Z_NEC5|, which on this corpus gives the same median to five decimals
and a wildly different tail (worst 1.45e+03 against 1.96). A deck must not
become the corpus's worst disagreement by having a small denominator.

## An exact zero is not an impedance

Six decks solve, report `ok`, and print an impedance of exactly zero at the
feed. They were filed under "|Z| under 1 ohm, degenerate" — as though they were
very small numbers rather than no answer at all.

The cause is measured, not inferred. NEC defaults an `EX` card with a zero
voltage to **1 V**; momwire's portal takes the zero literally, so nothing is
driven and the printout carries 0 V, 0 A and 0 ohm. NEC-5 reads the same
translated bytes, prints V = 1.0 and returns 54.832+3.001j on
`4nec2-models/Equations/Moxon.nec`; given an explicit 1 V the portal solves the
same deck normally at 58.889+6.705j. A drive failure, not a small impedance.

They now carry a status of their own, `no-drive`, with the printed source
voltage in the error text; they count as momwire bs2 refusals in the coverage
table above and no longer appear in the degenerate table. Filed as
stevenmburns/momwire#1041.

Sweeping the artifact for both parts exactly `0.0` **and** for |Z| < 1e-9 found
**six**, where three were expected: the two Moxons and `qantenna/yg_4el_20.nec`,
plus `necpp/patch_999.nec`, `necpp/patch_999_2.nec` and `necpp/ga_pjw_1.nec`
(|Z| = 1.17e-12). All six are row 0 with a single source, so each affects its
whole deck. `ga_pjw_1.nec` is worth noting twice: it is also one of the five
decks that moved between the reference NEC-5 build and 63d0f93, so its departure
from the degenerate table removes a row that was never a disagreement about
physics.

## Publication discipline

momwire bs2's per-deck rows are committed beside this page. The NEC-5 side appears
as **aggregates and named cases with their impedances only** — no per-deck NEC-5
report is committed anywhere, which is the strict reading of the standing rule.
AK#896's Phase 0 note records a more permissive position (captures as End-User
Reports, LLNL-CODE-746721); if that holds, the per-deck NEC-5 column can be
added and the adjudication section gets materially more legible.

---

## Coverage

The momwire side is **momwire bs2 (B-spline, d=2)**, read from the portal's own banner and recorded per run in the artifact's `_meta.environment.basis`; called momwire bs2 below.

- decks in the NEC-5 report: **3076**
- decks in the momwire report: **3076**
- joined on `file`: **3076**

| status | NEC-5 | momwire bs2 |
|---|---:|---:|
| `crash` | 43 | 5 |
| `error` | 10 | 622 |
| `no-drive` | 0 | 6 |
| `no-impedance` | 8 | 0 |
| `ok` | 2946 | 2437 |
| `ok-no-source` | 67 | 0 |
| `over-cap` | 0 | 6 |
| `timeout` | 2 | 0 |

Both engines solved and printed an impedance on **2386** decks.

### Is the join sound?

- row 0 is the same `(tag, seg)` on both sides: **2385/2386**
- both reports list the same number of sources: **2376/2386**

The following deck(s) address a different segment on each side. Their comparison would be of two different ports, so they are **excluded** from everything below:

- `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-6/6-6-nec4.nec` — NEC-5 `(101, 832)`, momwire `(101, 2204)`

10 deck(s) list different numbers of sources. On every one the NEC-5 listing stops at 8 rows while momwire lists 11 to 50, and row 0 — the only row the join reads — is identical. A listing limit, not a disagreement; these decks are kept.

## Agreement on the driving-point impedance

21 deck(s) report |Z| under 1 ohm on one side and are excluded by `compare`'s own degeneracy rule — a large percentage of nothing is not a disagreement:

| deck | momwire bs2 Z (ohm) | NEC-5 Z (ohm) |
|---|---|---|
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-1/10-4-2.nec` | 0.03579+0.003214j | 0.03585+0.001451j |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-10/10-10.nec` | 0.01375+0.0001382j | 0.01413+0.002862j |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-10/10-10a.nec` | 0.01375+0.0001382j | 0.01413+0.002862j |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-10/10-10b.nec` | 0.01375+0.0001382j | 0.01413+0.002862j |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-10/10-10c.nec` | 0.01375+0.0001382j | 0.01413+0.002862j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r4-bc3elendfire-pergnd.nec` | 0.000982+0.002466j | 0.0009861+0.002485j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r4-bc6elb-s+e-f-pergnd.nec` | 0.001438+0.001363j | 0.001448+0.001376j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r5-bc4elendfire-pergnd.nec` | 1.961e-07+0.0001939j | 3.668e-07+0.000257j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r5-bc6elphaseaim-pergnd.nec` | 0.004866+0.04607j | 0.004443+0.0448j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r8-4el-endfire.nec` | 3.564e-07+0.0002135j | 5.881e-07+0.0002839j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r8-5el-endfire.nec` | 9.264e-07+0.000214j | 1.532e-06+0.0002849j |
| `cebik-w4rnl/models/Phased-Arrays/nec/3r6-phasedrect-10-N2DT.nec` | 0.01188-0.01568j | 0.01069-0.01371j |
| `cebik-w4rnl/models/VHF-UHF/nec/300-turnstile-dipoles.nec` | 0.01384+0.0001097j | 0.01401+0.001469j |
| `cebik-w4rnl/models/VHF-UHF/nec/50-lazyH-phasedarray.nec` | 0.0004858-0.001726j | 0.000472-0.001674j |
| `cebik-w4rnl/models/VHF-UHF/nec/850-dbldiamond-planarrefl.nec` | 0.01078+0.006326j | 0.009815+0.00797j |
| `cebik-w4rnl/models/Yagis-HF/nec/2el60mwireYagi.nec` | 0.01879-0.002225j | 0.02166+0.004231j |
| `g1ojs/160m/160m Coax Magloop V.nec` | 0.4039+0.2693j | 0.4264+6.053j |
| `g1ojs/_2m/Hentenna based/2m Small Hentenna Loop 700x200 Stub Match Wire dia.nec` | 0.03134+0.6602j | 0.1774-1.576j |
| `necpp/plet_helixumts.nec` | 1.67e-11+0.0007148j | 3.39e-06-7.686e-06j |
| `sokyrad/unsorted/10m efhw narrow rect 28.4mhz  10m efhw narrow rect 28.4mhz.nec` | 1.465e-07+4.997e-05j | 6.536e-08+3.806e-05j |
| `sokyrad/unsorted/stacked_146MHz_moxon_vertical_0_75lambda.nec` | 0.02045+6.104j | 0.03756+0.2698j |

Comparable decks: **2364**

| relative difference \|Zm-Zn\|/\|Zn\| | decks | share |
|---|---:|---:|
| < 0.1 % | 6 | 0.3 % |
| < 1 % | 142 | 6.0 % |
| < 10 % | 975 | 41.2 % |
| >= 10 % | 1241 | 52.5 % |

| quantile | p50 | p75 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| relative difference \|Zm-Zn\|/\|Zn\| | 1.10e-01 | 2.33e-01 | 5.55e-01 | 1.08e+00 | 3.21e+01 |

Median 1.10e-01; worst 1.45e+03 — but see the tail table: that worst figure is `compare`'s NEC-5-referenced ratio and the same deck is 1.96e+00 measured symmetrically. The median is identical either way.

## The tail: the 20 widest disagreements

Ranked by the symmetric measure, with `compare`'s NEC-5-referenced ratio beside it. Where the two columns diverge sharply, the deck's NEC-5 |Z| is small and `compare`'s figure is mostly its denominator.

| deck | momwire bs2 Z (ohm) = Zm | NEC-5 Z (ohm) = Zn | symmetric rel. diff \|Zm-Zn\|/max(\|Zm\|,\|Zn\|) | `compare`'s rel. diff \|Zm-Zn\|/\|Zn\| |
|---|---|---|---:|---:|
| `g1ojs/160m/160m Single Turn Coax Magloop V.nec` | 0.4037-2.898j | 0.426+2.953j | 1.96 | 1.96 |
| `g1ojs/opt/Loaded V-20.nec` | 8.295+177j | 7.772-200.3j | 1.88 | 1.88 |
| `g1ojs/_1m/Dipole with matching l _ 0.25 v1.nec` | 5.421-121.2j | 3.796+106.2j | 1.87 | 2.14 |
| `4nec2-models/zz_MiniNec/HFshort/3el short Yagj W1FBY.nec` | 0.1176-49.13j | 2.305+40.1j | 1.82 | 2.22 |
| `g1ojs/opt/Loaded V-15.nec` | 8.722+132.9j | 8.249-180.6j | 1.73 | 1.73 |
| `nec2c/VB_28_T.nec` | 84.55+513.1j | 428.9-615.2j | 1.57 | 1.57 |
| `g1ojs/opt/Loaded V-21.nec` | 8.988+268.7j | 8.249-144.5j | 1.54 | 2.86 |
| `g1ojs/opt/Loaded V-28.nec` | 9.697+218.1j | 8.971-116.6j | 1.53 | 2.86 |
| `nec2c/VBS_28_T.nec` | 112.4+505.6j | 422.9-683.9j | 1.53 | 1.53 |
| `qantenna/5_8l-gp_on_pole.nec` | 184.4+154.1j | 126.4-227.2j | 1.48 | 1.48 |
| `4nec2-models/zz_MiniNec/HFbeams/2ELVP15.nec` | 70.56+125.4j | 13.89-75.1j | 1.45 | 2.73 |
| `icecube-dbesson/BCone65.nec` | 26.62+69.78j | 73.64-99.83j | 1.42 | 1.42 |
| `g1ojs/80m/tmp.nec` | 0.6107-219.4j | 0.7323+525.2j | 1.42 | 1.42 |
| `g1ojs/opt/Loaded V-12.nec` | 9.153+279.1j | 8.453-116.7j | 1.42 | 3.38 |
| `g1ojs/opt/Loaded V-08.nec` | 8.66+198.2j | 8.434-82.97j | 1.42 | 3.37 |
| `g1ojs/_1m/Dipole linear 1 75pc.nec` | 53.87-68.81j | 76.37+66.36j | 1.35 | 1.35 |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-10/10-5.nec` | 381.7+1087j | 613.8-3174j | 1.32 | 1.32 |
| `g1ojs/opt/Loaded V-22.nec` | 9.004+242j | 8.685-55.62j | 1.23 | 5.29 |
| `g1ojs/40m/opt/40m V integral PI_007-12.nec` | 0.2569-49.26j | 2.942e-06+10.76j | 1.22 | 5.58 |
| `g1ojs/opt/Loaded V-02.nec` | 9.559+313.1j | 8.864-66.19j | 1.21 | 5.68 |

## The reactance sign

On **455** of 2364 comparable decks (19.2 %) the two engines disagree on the SIGN of the reactance, and those decks dominate the tail above.

| group | decks | median symmetric rel. diff | same, with Zm conjugated |
|---|---:|---:|---:|
| reactance signs disagree | 455 | 0.1911 | 0.1221 |
| reactance signs agree | 1909 | 0.0952 | 0.4582 |

**The obvious explanation is ruled out by that last column.** If one side carried the opposite time convention, conjugating it would collapse the disagreeing group to near zero and wreck the agreeing one. The agreeing group does break, as it must — but the disagreeing group only improves partway, nowhere near zero. So this is not a global sign convention; it is a real disagreement about reactance on a specific class of deck.


## momwire bs2 advisories

| advisory | decks |
|---|---:|
| `SurfaceRadialHeight` | 33 |
| `LinAlgWarning` | 1 |

## Where momwire bs2 declined

| reason | decks |
|---|---:|
| LD 5 conductivity on a partial-wire segment range is not supported by this engine — per-wi | 175 |
| GH (helix) is not part of this engine's nec2 dialect, whose geometry is GW with GM / GS tr | 71 |
| EX type 4 is not a voltage source; this engine drives EX 0 only | 59 |
| EX type 1 is not a voltage source; this engine drives EX 0 only | 37 |
| GN type 3 is not supported by this engine | 34 |
| LD type 2 is not supported by this engine | 29 |
| GA (wire arc) is not part of this engine's nec2 dialect, whose geometry is GW with GM / GS | 29 |
| deck has no EX card — nothing drives the structure | 26 |
| wire 0 start lies in the ground plane: ground CONTACT under ground_model='refl-coef' is re | 19 |
| GC (tapered wire continuation) is not part of this engine's nec2 dialect | 17 |
| RP 3 asks for a cliff pattern over a ground with no second medium stated (an all-zero EPSR | 16 |
| NE over a finite ground is not supported by this engine (the near field of a Sommerfeld ha | 10 |
| unrecognised NEC card 'CW' | 7 |
| NE coordinate system 1 (spherical) is not supported by this engine; rectangular (0) only | 7 |
| PL (plot request) is not supported by this engine | 7 |
| RP 2 asks for a cliff pattern over a ground with no second medium stated (an all-zero EPSR | 6 |
| RP mode 1 is not supported by this engine (modes 0, 2, 3 only) | 5 |
| wire 0 end lies in the ground plane: ground CONTACT under ground_model='refl-coef' is refu | 4 |
| wire 1 end, wire 4 end lies in the ground plane: ground CONTACT under ground_model='refl-c | 3 |
| RP mode 4 is not supported by this engine (modes 0, 2, 3 only) | 3 |

<sub>Environments — NEC-5: `/home/smburns/nec5-timing/nec5-src/nec5cl`, momwire: `?`, seg cap 4000, timing_valid True.</sub>
