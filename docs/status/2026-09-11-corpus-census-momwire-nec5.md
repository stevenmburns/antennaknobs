# momwire bs2 against NEC-5 over the public NEC corpus

**Evidence, not a scoreboard.** AK#896. Measured 2026-09-11 on momwire **0.53.0**,
imported from the editable submodule at `23d81e5` (tag `v0.53.0`, clean working
tree) rather than from a wheel, running the portal's default basis **momwire bs2
(B-spline, d=2)**. "momwire" alone names a package and not a solver — the
portal's roster carries seven bases that disagree with each other by design — so
the artifact records the basis, its solver class and degree, and the banner they
were read from, beside the version, commit and import path. Which build and which
basis answered is recoverable from the data and not only from this line.

**The commit is named for a reason, not for form.** This census runs momwire at
the submodule POINTER, which normally sits ahead of the released version, so
`0.53.0` does not by itself identify the solver that answered — a pointer bump
can move rows while the version string stands still. That is why the commit is
named — and it has since been tested rather than left as a caution: momwire
**v0.54.0** (`260bd91`, carrying the crossing kernel's W terms, momwire#1043, and
momwire#1004's cross-block quadrature) was run against `23d81e5` on all 873 decks
whose rows moved in this re-render and changed **no status and no impedance**.

Skylake box, over the 21 public deck collections
`scripts/nec5_corpus/nec5_corpus.py fetch` knows about. **3,066 decks**, which is
what the translate report writes and what is on disk, 2,159 s on the momwire side.
Per-deck momwire rows in `data/2026-09-11-corpus-census-momwire.jsonl`.

## Re-rendered 2026-09-13 on corpus tool 1.11

Every number on this page was re-measured on corpus tool **1.11**, which carries
three corpus fixes made since the first publication: **#1442** (`GN 2` passes
through instead of being rewritten to `GN 0`), **#1435** (a `collision` status, so
`written` equals the deck files on disk) and the tab-field tokenizer fix (a number
and its unit in one TAB field, `-68 ft`, is one value), alongside #1416 and #1430
from the previous re-render.

| | first publication (1.6) | this page (1.11) |
|---|---:|---:|
| deck files in the corpus | 3,076 | **3,066** |
| `written` in the translate report | 3,077 | **3,066** — equal to the files on disk |
| decks both engines solve with an impedance | 2,386 | **2,578** |
| **comparable after the degeneracy rule** | **2,364** | **2,547** |
| reactance-sign disagreements | 455 (19.2 %) | **503 (19.7 %)** |
| median relative difference | 1.10e-01 | **1.01e-01** |

The ground spelling is the substantive change: on the **1,104** decks whose ground
was being rewritten to `GN 0`, momwire was reading the reflection-coefficient
approximation where NEC-5 read Sommerfeld, and with `GN 2` restored both engines
now solve the ground the deck asks for — which moves the median on that population
from 0.1161 to 0.0982, the count past 10 % from 470 to 440, and the
reactance-sign disagreements from 198 to 203.

Five decks also change because their cards were being mis-read: `2lsloper` in two
collections, `G5RV.nec` and `g5rv.nec`, and `Vehicle.nec`. `2lsloper` is an 80 m
sloper standing **7.9 to 41.1 m above ground**, not the buried antenna this page
previously reported.

The census is deterministic on 1.11: two full passes agree on **every one of the
3,066 rows** bar the wall clock, and two translate passes are byte-identical. The
record is `scratch/896-census/RERENDER-1442.md`; the commands are
`scratch/896-census/rerender_1442.sh`.

## What this census can and cannot say

It reports **how far apart two formulations land on the decks people actually
published, at the mesh densities those people chose**. That is all it reports.

It does **not** say which engine is closer to the truth on any deck. Deciding
that needs a mesh ladder and a limit extrapolation per deck — the #872 / #890
machinery — and this census is the instrument that finds the cases worth
spending that on, not a substitute for it. A deck where the two disagree is a
*question*; the census's job is to turn three thousand decks into a short,
ranked, reproducible list of them.

Read the headline with that in mind. A median disagreement of 10.1 % at
author-chosen density is the **convergence-rate gap made visible at scale**: a
coarse deck leaves the O(1/N) formulation further from its own limit than the
B-spline basis is from the same limit, so the gap at N-as-published is expected
to exceed the gap at N-as-converged. This measures the first. Only a ladder
measures the second.

## Method

- **Decks**: the translated tree — the same bytes into both engines.
- **NEC-5 side**: `nec5_corpus.py check`, re-run over this tree at the same
  settings as the first publication (`OMP`/`OPENBLAS` 4, `--timeout 300`,
  `--jobs` 4) with the binary that publication used. 918 s.
- **momwire side**: `scratch/896-census/census_momwire.py`, one deck per
  subprocess under a 300 s wall timeout and a 6 GB address-space rlimit.
- **Join**: `compare`'s own `_first_z` — row 0 of the first frequency's
  ANTENNA INPUT PARAMETERS on each side.
- **Regenerate**: `scratch/896-census/census_report.py --cases 20 --nec5 <a>
  --momwire <b>`. The committed script reproduces every table on this page byte
  for byte from the two reports; checked rather than claimed. `--cases 20` is
  part of the command and not a detail — the script's default is 25, so without
  it the tail table below comes out five rows longer and the byte-for-byte claim
  fails on exactly that table.

**The census itself is deterministic**, and the re-render re-established that
rather than inheriting it. Two full passes over this tree — 887 s and 885 s —
agree on **every one of 3,066 rows**: status, error text, impedances and advisory
classes alike, with only `wall_s` excluded. Zero rows differ. (The first
publication's three passes measured 891 s, 889 s and 889 s and agreed likewise,
differing on 6 rows only because the third introduced the `no-drive` status
described below.)

That matters more here than it would for a benchmark: a census whose refusals or
impedances wandered between runs could not support a named-case list, because
nobody could tell a finding from a re-roll.

**`--jobs` is a wall-clock parameter and nothing else**, which is worth stating
because getting it wrong costs a comparison rather than a run. `census_momwire.py`
defaults to `--jobs 1`; both publications used **4**. A 1-way pass measured ~3x
the wall for **0.93x** the summed per-deck `wall_s` over the 1,634 decks it
reached — the same work at the same speed per deck, and a wall figure that could
not honestly be set beside 889 s.

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

The cost used to be ours, and was the single largest refusal on this page:
**175 decks lost to `LD 5` on a partial-wire range** at first publication, now
**16**. NEC-5 addresses knots where NEC-2 addresses segment centres, so
`translate` remeshes a wire to put a referenced centre on a knot and remaps the
references — by design. The side effect was that a **whole-wire** `LD 5` stopped
being whole-wire: `GW 1 25` with `LD 5 1 1 25` became `GW 1 50` with
`LD 5 1 2 50`, and momwire's nec2 dialect, which carries per-wire conductivity
but not partial ranges, refused it.

The first publication left that open — "whether `2 50` is the right remap is a
question for whoever owns `translate`". **It was not**, and #1416 answered it: a
range that covered a whole wire before the remesh covers the whole wire after it,
so `LD 5 1 1 25` becomes `LD 5 1 1 50`. Measured here, that recovers **158 of the
175** — every one of them a deck whose refusal text was exactly this, and every
one of them now solving. One more left the corpus under #1430.

The remaining **16** split two ways, and the split is measured from the authors'
own raw decks rather than assumed:

- **11** carry `LD 5` on a range that is already partial in the raw deck. Those
  are momwire's dialect limit — per-wire conductivity, no partial ranges — and
  nothing about `translate` is implicated.
- **5** are ours still, in a form #1416 does not reach: `LD 5 0 1 N`, a **tag-0**
  load over absolute segment numbers `1..N` where N is the structure's whole
  segment count. The remesh grows the structure — 211 → 222 segments on
  `sokyrad/…/K8UY_yagi_2m_original.nec`, 97 → 99, 395 → 403, 136 → 139 on the
  others — and the range is left at `1 211`, so a whole-structure load silently
  becomes a partial one. #1416 made a whole-**wire** range stay whole-wire; the
  tag-0 whole-**structure** range is the hole in #1423.

This is also why the re-render is worth more than a version bump: the census's
largest self-reported defect is now measured as fixed, on the corpus that
reported it.

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

Six decks solved, reported `ok`, and printed an impedance of exactly zero at the
feed. They were filed under "|Z| under 1 ohm, degenerate" — as though they were
very small numbers rather than no answer at all. **Four remain in this corpus**;
the two that left are `necpp/patch_999.nec` and `necpp/patch_999_2.nec`, which
#1430 now refuses at translation because each lists the same wire twice.

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
(|Z| = 1.17e-12). All six were row 0 with a single source, so each affected its
whole deck. The coverage table above now counts **four**, for the reason given at
the top of this section — the two `patch_999` decks are out of the corpus, not
re-classified. `ga_pjw_1.nec` is worth noting twice: it is also one of the five
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

- decks in the NEC-5 report: **3066**
- decks in the momwire report: **3066**
- joined on `file`: **3066**

| status | NEC-5 | momwire bs2 |
|---|---:|---:|
| `crash` | 43 | 5 |
| `error` | 6 | 423 |
| `no-drive` | 0 | 4 |
| `no-impedance` | 7 | 0 |
| `ok` | 2942 | 2627 |
| `ok-no-source` | 66 | 0 |
| `over-cap` | 0 | 6 |
| `timeout` | 2 | 1 |

Both engines solved and printed an impedance on **2578** decks.

### Is the join sound?

- row 0 is the same `(tag, seg)` on both sides: **2577/2578**
- both reports list the same number of sources: **2565/2578**

The following deck(s) address a different segment on each side. Their comparison would be of two different ports, so they are **excluded** from everything below:

- `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-6/6-6-nec4.nec` — NEC-5 `(101, 832)`, momwire `(101, 2204)`

13 deck(s) list different numbers of sources. On every one the NEC-5 listing stops at 8 rows while momwire lists 11 to 50, and row 0 — the only row the join reads — is identical. A listing limit, not a disagreement; these decks are kept.

## Agreement on the driving-point impedance

30 deck(s) report |Z| under 1 ohm on one side and are excluded by `compare`'s own degeneracy rule — a large percentage of nothing is not a disagreement:

| deck | momwire bs2 Z (ohm) | NEC-5 Z (ohm) |
|---|---|---|
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-1/10-4-2.nec` | 0.03579+0.003214j | 0.03585+0.001451j |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-1/16-5.nec` | 0.02794+0.02427j | 0.0268+0.02473j |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-10/10-10.nec` | 0.01375+0.0001382j | 0.01413+0.002862j |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-10/10-10a.nec` | 0.01375+0.0001382j | 0.01413+0.002862j |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-10/10-10b.nec` | 0.01375+0.0001382j | 0.01413+0.002862j |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-10/10-10c.nec` | 0.01375+0.0001382j | 0.01413+0.002862j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r4-bc3elendfire-pergnd.nec` | 0.000982+0.002466j | 0.0009861+0.002485j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r4-bc6elb-s+e-f-pergnd.nec` | 0.001438+0.001363j | 0.001448+0.001376j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r5-bc4elendfire-pergnd.nec` | 1.961e-07+0.0001939j | 3.668e-07+0.000257j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r5-bc6elphaseaim-pergnd.nec` | 0.004866+0.04607j | 0.004443+0.0448j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r8-2x4elphased-K8UR.nec` | 0.002902-0.01179j | 0.004763-0.01515j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r8-4el-endfire.nec` | 3.564e-07+0.0002135j | 5.881e-07+0.0002839j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r8-4elphased-lowbend-K8UR.nec` | 0.0005791-0.00412j | 0.0007242-0.004729j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r8-4elphased-midelbend-K8UR.nec` | 0.002197-0.01254j | 0.003746-0.01655j |
| `cebik-w4rnl/models/Phased-Arrays/nec/1r8-5el-endfire.nec` | 9.264e-07+0.000214j | 1.532e-06+0.0002849j |
| `cebik-w4rnl/models/Phased-Arrays/nec/3r6-2x4elphased-K8UR.nec` | 0.002944-0.01173j | 0.004817-0.01504j |
| `cebik-w4rnl/models/Phased-Arrays/nec/3r6-4elphased-lowbend-K8UR.nec` | 0.0005944-0.004126j | 0.0007432-0.004735j |
| `cebik-w4rnl/models/Phased-Arrays/nec/3r6-4elphased-midelbend-K8UR.nec` | 0.002246-0.01249j | 0.003819-0.01645j |
| `cebik-w4rnl/models/Phased-Arrays/nec/3r6-phasedrect-10-N2DT.nec` | 0.01183-0.01506j | 0.01069-0.01371j |
| `cebik-w4rnl/models/Phased-Arrays/nec/5r4-2x4elphased-K8UR.nec` | 0.002974-0.01168j | 0.004854-0.01495j |
| `cebik-w4rnl/models/Phased-Arrays/nec/5r4-4elphased-lowbend-K8UR.nec` | 0.0006007-0.004128j | 0.0007512-0.004737j |
| `cebik-w4rnl/models/Phased-Arrays/nec/5r4-4elphased-midelbend-K8UR.nec` | 0.002274-0.01244j | 0.003858-0.01636j |
| `cebik-w4rnl/models/VHF-UHF/nec/300-turnstile-dipoles.nec` | 0.01384+0.0001097j | 0.01401+0.001469j |
| `cebik-w4rnl/models/VHF-UHF/nec/50-lazyH-phasedarray.nec` | 0.0004858-0.001726j | 0.000472-0.001674j |
| `cebik-w4rnl/models/VHF-UHF/nec/850-dbldiamond-planarrefl.nec` | 0.01078+0.006326j | 0.009815+0.00797j |
| `cebik-w4rnl/models/Yagis-HF/nec/2el60mwireYagi.nec` | 0.01879-0.002225j | 0.02166+0.004231j |
| `g1ojs/160m/160m Coax Magloop V.nec` | 0.4331+0.2983j | 0.4264+6.053j |
| `g1ojs/_2m/Hentenna based/2m Small Hentenna Loop 700x200 Stub Match Wire dia.nec` | 0.03134+0.6602j | 0.1774-1.576j |
| `sokyrad/unsorted/10m efhw narrow rect 28.4mhz  10m efhw narrow rect 28.4mhz.nec` | 1.463e-07+4.997e-05j | 6.536e-08+3.806e-05j |
| `sokyrad/unsorted/stacked_146MHz_moxon_vertical_0_75lambda.nec` | 0.02045+6.104j | 0.03756+0.2698j |

Comparable decks: **2547**

| relative difference \|Zm-Zn\|/\|Zn\| | decks | share |
|---|---:|---:|
| < 0.1 % | 8 | 0.3 % |
| < 1 % | 157 | 6.2 % |
| < 10 % | 1104 | 43.3 % |
| >= 10 % | 1278 | 50.2 % |

| quantile | p50 | p75 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| relative difference \|Zm-Zn\|/\|Zn\| | 1.01e-01 | 2.19e-01 | 5.16e-01 | 1.05e+00 | 3.12e+01 |

Median 1.01e-01; worst 1.42e+03 — but see the tail table: that worst figure is `compare`'s NEC-5-referenced ratio and the same deck is 1.95e+00 measured symmetrically. The median is identical either way.

## The tail: the 20 widest disagreements

Ranked by the symmetric measure, with `compare`'s NEC-5-referenced ratio beside it. Where the two columns diverge sharply, the deck's NEC-5 |Z| is small and `compare`'s figure is mostly its denominator.

| deck | momwire bs2 Z (ohm) = Zm | NEC-5 Z (ohm) = Zn | symmetric rel. diff \|Zm-Zn\|/max(\|Zm\|,\|Zn\|) | `compare`'s rel. diff \|Zm-Zn\|/\|Zn\| |
|---|---|---|---:|---:|
| `g1ojs/160m/160m Single Turn Coax Magloop V.nec` | 0.4328-2.869j | 0.426+2.953j | 1.95 | 1.95 |
| `g1ojs/opt/Loaded V-20.nec` | 8.826+177.1j | 7.772-200.3j | 1.88 | 1.88 |
| `g1ojs/_1m/Dipole with matching l _ 0.25 v1.nec` | 5.421-121.2j | 3.796+106.2j | 1.87 | 2.14 |
| `4nec2-models/zz_MiniNec/HFshort/3el short Yagj W1FBY.nec` | 0.1176-49.13j | 2.305+40.1j | 1.82 | 2.22 |
| `g1ojs/opt/Loaded V-15.nec` | 9.287+133j | 8.249-180.6j | 1.73 | 1.73 |
| `nec2c/VB_28_T.nec` | 84.55+513.1j | 428.9-615.2j | 1.57 | 1.57 |
| `g1ojs/opt/Loaded V-21.nec` | 9.572+268.8j | 8.249-144.5j | 1.54 | 2.86 |
| `g1ojs/opt/Loaded V-28.nec` | 10.34+218.2j | 8.971-116.6j | 1.53 | 2.86 |
| `nec2c/VBS_28_T.nec` | 112.4+505.6j | 422.9-683.9j | 1.53 | 1.53 |
| `qantenna/5_8l-gp_on_pole.nec` | 184.4+154.1j | 126.4-227.2j | 1.48 | 1.48 |
| `4nec2-models/zz_MiniNec/HFbeams/2ELVP15.nec` | 70.56+125.4j | 13.89-75.1j | 1.45 | 2.73 |
| `icecube-dbesson/BCone65.nec` | 26.62+69.78j | 73.64-99.83j | 1.42 | 1.42 |
| `g1ojs/80m/tmp.nec` | 0.6378-219.4j | 0.7323+525.2j | 1.42 | 1.42 |
| `g1ojs/opt/Loaded V-12.nec` | 9.749+279.1j | 8.453-116.7j | 1.42 | 3.38 |
| `g1ojs/opt/Loaded V-08.nec` | 9.216+198.3j | 8.434-82.97j | 1.42 | 3.37 |
| `g1ojs/_1m/Dipole linear 1 75pc.nec` | 53.87-68.81j | 76.37+66.36j | 1.35 | 1.35 |
| `cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-2/ch-10/10-5.nec` | 381.7+1087j | 613.8-3174j | 1.32 | 1.32 |
| `g1ojs/opt/Loaded V-22.nec` | 9.586+242.1j | 8.685-55.62j | 1.23 | 5.29 |
| `g1ojs/40m/opt/40m V integral PI_007-12.nec` | 0.2577-49.26j | 2.942e-06+10.76j | 1.22 | 5.58 |
| `g1ojs/opt/Loaded V-02.nec` | 10.19+313.2j | 8.864-66.19j | 1.21 | 5.68 |

## The reactance sign

On **503** of 2547 comparable decks (19.7 %) the two engines disagree on the SIGN of the reactance, and those decks dominate the tail above.

| group | decks | median symmetric rel. diff | same, with Zm conjugated |
|---|---:|---:|---:|
| reactance signs disagree | 503 | 0.1707 | 0.1105 |
| reactance signs agree | 2044 | 0.0873 | 0.4624 |

**The obvious explanation is ruled out by that last column.** If one side carried the opposite time convention, conjugating it would collapse the disagreeing group to near zero and wreck the agreeing one. The agreeing group does break, as it must — but the disagreeing group only improves partway, nowhere near zero. So this is not a global sign convention; it is a real disagreement about reactance on a specific class of deck.


## momwire bs2 advisories

| advisory | decks |
|---|---:|
| `SurfaceRadialHeight` | 39 |
| `LinAlgWarning` | 1 |

## Where momwire bs2 declined

| reason | decks |
|---|---:|
| GH (helix) is not part of this engine's nec2 dialect, whose geometry is GW with GM / GS tr | 71 |
| EX type 4 is not a voltage source; this engine drives EX 0 only | 59 |
| EX type 1 is not a voltage source; this engine drives EX 0 only | 37 |
| GN type 3 is not supported by this engine | 34 |
| LD type 2 is not supported by this engine | 29 |
| GA (wire arc) is not part of this engine's nec2 dialect, whose geometry is GW with GM / GS | 29 |
| deck has no EX card — nothing drives the structure | 24 |
| GC (tapered wire continuation) is not part of this engine's nec2 dialect | 17 |
| LD 5 conductivity on a partial-wire segment range is not supported by this engine — per-wi | 16 |
| RP 3 asks for a cliff pattern over a ground with no second medium stated (an all-zero EPSR | 16 |
| NE over a finite ground is not supported by this engine (the near field of a Sommerfeld ha | 10 |
| wire 0 start lies in the ground plane: ground CONTACT under ground_model='refl-coef' is re | 7 |
| unrecognised NEC card 'CW' | 7 |
| NE coordinate system 1 (spherical) is not supported by this engine; rectangular (0) only | 7 |
| PL (plot request) is not supported by this engine | 7 |
| RP 2 asks for a cliff pattern over a ground with no second medium stated (an all-zero EPSR | 6 |
| RP mode 1 is not supported by this engine (modes 0, 2, 3 only) | 5 |
| RP mode 4 is not supported by this engine (modes 0, 2, 3 only) | 3 |
| unrecognised NEC card 'UM' | 3 |
| GE -1 declares the ground plane without the ground-contact current expansion, and wire 6's | 3 |

<sub>Environments — NEC-5: `/home/smburns/nec5-timing/nec5cl-x13`, momwire: `0.53.0 @ 23d81e5 clean`, seg cap 4000, timing_valid True.</sub>
