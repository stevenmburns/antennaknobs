# 2026-09-07 — wild-corpus solve sweep (3,146 decks, 5 engines, bounded)

## Goal

Re-run the bounded solve sweep of 2026-07-17/18 against today's engines, add
NEC-5 as a fifth engine, and say what moved. The July run is the baseline;
this one answers whether seven weeks of solver work helped, and where it did
not.

**Headline: a large net improvement with a real regression tail.** Median
agreement improves for every momwire engine, several decks fall from ΔΓ ≈ 1.5
to ≈ 0.01, and NEC-5 enters the corpus at 2,314 scored decks. Against that,
**272 engine-deck pairs across 144 decks got measurably worse**, and the cause
is engine-side rather than reference or import drift. Three causes are named
and filed (momwire#963, #964, #965); part of the tail remains unattributed.
The tail is in this headline rather than an appendix because it is the part
that needs work.

## Method

Run on Haswell (8 threads, 31 GB), serially, with nothing else on the box:
the sweep records per-deck `solve_s` and `peak_rss_mb`, so a concurrent job
would corrupt the measurement rather than merely slow it. Wall time **4 h
57 m** (17:32:48 → 22:29:40).

| | this run | 2026-07-17 / 07-18 |
|---|---|---|
| corpus | `~/antennas/nec-wild`, 3,146 unique decks | same |
| engines | pynec, sin, bs1, bs2, **nec5** | pynec, sin, bs1, bs2 |
| reference | nec2c 1.3.1, md5 `050927160cecf7ee86db907dafac7bbe` | same binary |
| caps | 300 s, 8 GB | same |

**The reference binary is the same one, and that took a correction.** The
box's `nec2c` on `PATH` was the jammy package, 1.3 at md5
`989ece20053ba73535a739172452c1f2` — not the 1.3.1 the 07-17 doc pins. ΔΓ is
measured against the reference, so a different one moves every row and would
have drowned the movers diff in reference noise. The first 154 rows were
discarded and the sweep restarted after installing the pinned 1.3.1 (md5
verified before use, into `~/.local/bin`, which the bench script already
resolves). The discarded rows are kept beside the run as `DISCARDED-*`.

**Baseline.** `wild-solve-2026-07-18-post455.jsonl` (md5
`e278992135038e8f5d885be9c37eec69`), the re-run after momwire#157 fixed the 38
anchor-family timeouts. It is used throughout rather than only where it has
the deck: measured, it scores **2,801** decks against 07-17's **2,714**, with
**zero** decks scored only in 07-17 — a strict superset, so the fallback to
`wild-solve-2026-07-17.jsonl` (md5 `393ba3ba1325d685f2f400df757358dd`) never
fires. That file also carries 21 duplicated deck rows; post455 has exactly one
row per deck.

**Taxonomy.** `OOS` is a DECLARED refusal — a sentence naming what is out of
scope — regardless of which exception carried it. That matters for the
side-by-side: momwire's buried pre-flight refusals (AK#1135) are declared
sentences and belong in OOS, and classifying them by exception type would put
them in ERR and read as breakage. The rollup prints every distinct refusal
sentence so this can be audited rather than trusted, and flags any refusal
arriving as a bare exception class name. This run: none did.

**Movers are reported two ways**, because ΔΓ-vs-nec2c cannot separate an
engine change from a reference or import change — the reference is on both
sides of that subtraction. Alongside it, each engine is compared against
ITSELF between runs: every engine on a deck moving together points upstream of
all of them; one engine moving alone is that engine.

### The rollup was wrong before it was right

The first rollup of this run reported a p90 **below** the median for three of
five engines, which is arithmetically impossible from a sorted list. Cause:
between one and five decks per engine return `z = [inf, 0]` — an open-circuit
port — and `abs()` of the resulting reflection coefficient is NaN. NaN
compares `False` against everything, so `sorted()` left the list in an
arbitrary order and every median and p90 in the table was meaningless.
BSpline d=1's median was reported as 0.6248; it is **0.0324**. NEC-5's row was
the only correct one because NEC-5 alone had no NaN.

`quantile()` now drops non-finite values before sorting, the affected decks
are reported as their own census row rather than silently dropped, and the
impossible-ordering check is a live `assert` in the script — it is what caught
this, so it stays.

## Headline census

| outcome | 2026-09-07 | 2026-07-18 |
|---|--:|--:|
| decks | 3,146 | 3,146 |
| scored vs nec2c | **2,812** | 2,812 |
| parse-rejected | **188** | 197 |
| parsed, no nec2c reference | 146 | 146 |

Nine decks that the importer rejected in July now parse.

## Per-engine outcomes

| engine | ok | OOS | MEM | TIME | GEO | ERR | ok vs July |
|---|--:|--:|--:|--:|--:|--:|--:|
| PyNEC | 2692 | 1 | 0 | 0 | 118 | 1 | +1 |
| Sinusoidal | 2771 | 34 | 0 | 0 | 4 | 3 | −25 |
| BSpline d=1 | 2765 | 33 | 0 | 0 | 4 | 10 | −35 |
| BSpline d=2 | 2764 | 33 | 1 | 0 | 4 | 10 | −34 |
| NEC-5 | 2314 | 467 | 0 | 0 | 4 | 27 | new |

**The momwire engines solve fewer decks than in July, and that is the
intended direction.** The losses are declared pre-flight refusals that did not
exist then: the buried below/below domain limit (AK#1135) and the
ground-contact refusal under `refl-coef` (momwire#282 stage 1). Those decks
previously produced a number; they now say why they cannot. A count that goes
down because the engine stopped guessing is not a regression.

NEC-5's 467 OOS are overwhelmingly structural rather than numerical: 357
decks carry a TL branch it cannot stamp natively, 45 an Admittance branch, and
56 ask for reflection-coefficient ground, which NEC-5 does not have.

### Open-circuit ports (reported as success, not refused)

Five decks return a non-finite impedance with no error raised, so they land in
the scored population carrying no usable number. This is the defect that
corrupted the first rollup.

| deck | engines | reference Z |
|---|---|---|
| `community/icecube-dbesson/Moxon.nec` | sin, bs1, bs2 | 58.83+6.45j |
| `opensource/4nec2/Equations/Moxon.nec` | sin, bs1, bs2 | 58.83+6.45j |
| `opensource/g1ojs/_2m/Owen Collinear.nec` | pynec, sin, bs1, bs2 | 33.0+6.34j |
| `opensource/necpp/patch_999.nec` | bs1, bs2 | 3.61−1198.7j |
| `opensource/necpp/patch_999_2.nec` | bs1, bs2 | −259.63−425.06j |

Owen Collinear fails this way in PyNEC too, which points at the deck or the
import rather than at momwire; the other four are momwire-side, and the two
`patch_999` decks fail in the BSpline bases only.

## Agreement (all scored decks)

| engine | n | median | p90 | ≤0.01 | ≤0.05 | ≤0.2 | open |
|---|--:|--:|--:|--:|--:|--:|--:|
| PyNEC | 2691 | **0.0002** | 0.0008 | 97% | 98% | 99% | 1 |
| Sinusoidal | 2768 | **0.0036** | 0.0382 | 67% | 92% | 97% | 3 |
| BSpline d=1 | 2760 | **0.0324** | 0.3455 | 20% | 61% | 84% | 5 |
| BSpline d=2 | 2759 | **0.0134** | 0.2889 | 45% | 71% | 88% | 5 |
| NEC-5 | 2314 | **0.0304** | 0.4158 | 25% | 60% | 83% | 0 |

## Agreement (clean decks: supported ground, full network)

| engine | n | median | p90 | ≤0.01 | ≤0.05 | ≤0.2 | open |
|---|--:|--:|--:|--:|--:|--:|--:|
| PyNEC | 2545 | **0.0002** | 0.0007 | 99% | 100% | 100% | 1 |
| Sinusoidal | 2629 | **0.0032** | 0.0342 | 68% | 93% | 98% | 3 |
| BSpline d=1 | 2621 | **0.0324** | 0.3345 | 20% | 61% | 85% | 5 |
| BSpline d=2 | 2620 | **0.0133** | 0.2651 | 45% | 71% | 88% | 5 |
| NEC-5 | 2245 | **0.0301** | 0.4055 | 25% | 60% | 84% | 0 |

## Cost

| engine | solves | total solve s | median s | p90 s | max peak RSS MB |
|---|--:|--:|--:|--:|--:|
| PyNEC | 2692 | 288.8 | 0.0201 | 0.084 | 426 |
| Sinusoidal | 2771 | 1843.3 | 0.0279 | 1.800 | 1060 |
| BSpline d=1 | 2765 | 2222.9 | 0.0770 | 2.093 | **7026** |
| BSpline d=2 | 2764 | 2487.8 | 0.1339 | 2.201 | 3277 |
| NEC-5 | 2314 | 1260.0 | 0.0792 | 0.956 | 174 |

Total solve time is 8,103 s — 45 % of the 4 h 57 m wall. The rest is import,
the nec2c reference, and process churn. BSpline d=1's 7 GB peak sits just
under the 8 GB cap and is the single figure most likely to turn into a MEM
outcome on a larger deck; d=2 peaks at less than half that.

## What improved

647 engine-deck pairs moved by more than 0.02, the large majority toward the
reference. The biggest falls are whole-deck rescues rather than nudges:

| move | engine | deck | was | now |
|--:|---|---|--:|--:|
| 1.586 | bs2 | `opensource/nec2c/dl_4el_20.nec` | 1.5956 | 0.0094 |
| 1.550 | sin | `.../HFbeams/DL9JFT Yagi 14.nec` | 1.5512 | 0.0016 |
| 1.447 | sin | `opensource/4nec2/HFshort/CoilCapHat.nec` | 1.4723 | 0.0251 |
| 1.410 | sin | `.../HFshort/Gp40short rad.nec` | 1.4105 | 0.0006 |
| 1.318 | bs2 | `.../HFmultiband/SHOEBOX.NEC` | 1.3188 | 0.0009 |
| 1.314 | sin | `.../zz_EZnec/v3.0/BYVee.nec` | 1.3155 | 0.0016 |

## The regression tail: 272 pairs, 144 decks

| engine | regressed pairs |
|---|--:|
| Sinusoidal | 100 |
| BSpline d=1 | 83 |
| BSpline d=2 | 89 |
| PyNEC | 0 |
| NEC-5 | 0 |

**It is engine-side.** On every regressed deck the nec2c reference is
bit-identical between the two runs, and PyNEC's impedance moves only in the
last two or three digits, so neither the reference nor the importer explains
it. The worst:

| move | engine | deck | was | now |
|--:|---|---|--:|--:|
| +1.171 | sin | `.../Verticals/others/opt/general 2-04.nec` | 0.0017 | 1.1731 |
| +1.028 | sin | `.../Verticals/others/opt/general 2-05.nec` | 0.0011 | 1.0290 |
| +1.011 | bs1 | `opensource/nec2c/VB_28_T.NEC` | 0.1897 | 1.2010 |
| +1.005 | bs1 | `opensource/nec2c/VBS_28_T.NEC` | 0.1903 | 1.1953 |
| +0.994 | sin | `.../Shortened dipoles/Dipole wire diameter.nec` | 0.1798 | 1.1740 |
| +0.969 | sin | `opensource/g1ojs/_6m/6m Moxon coax inner fed.nec` | 0.0081 | 0.9771 |

It is not one uniform cause. On
`20m 65cm Circ 10mm Copper Magloop V.nec` bs1 regresses hard (133 Ω → 8.5 Ω
against a 73 Ω reference) while **bs2 improves on the same deck**, landing at
75.7 − 76.7j against a reference of 73.0 − 77.0j.

### What the tail is: three named causes

Two candidate explanations were measured first and neither survives as stated,
which is worth recording because both looked convincing.

**Loads and ground are mostly base rate.** 120 of the 144 decks carry an `LD`
card and 119 a `GN` card, which looks damning until compared against the
corpus: 65.9 % and 70.8 % of all comparable decks carry them anyway. The
enrichment is 1.26× and 1.17× — not a cause.

**High Q does not explain it either.** The obvious physical story is that these
are high-reactance structures where a small absolute error swings ΔΓ. Decks
with |X|/R > 1 are enriched 2.36×, but the enrichment *falls* to 1.04× above
|X|/R > 30. If reactance were the mechanism the trend would run the other way.

What did survive is three separate causes, each pinned by an experiment.

#### 1. The extended kernel — 85 pairs (momwire#963)

In July the momwire bases could not honour an `EK` card, so those decks ran
reduced-kernel; today they honour it. PyNEC honoured EK in both eras and has
**zero** regressions, which is the control. EK-carrying decks are enriched
**4.01×** in the tail.

Re-solving all 136 EK-carrying regressed pairs with `extended_kernel=False`
returns **85** of them to their July value exactly; 16 recover partially and
35 are unmoved. Median regression in the restored group is 0.034, reaching
0.99.

The reference is nec2c with the *same* EK card applied, unchanged between
runs — so both codes now use an extended kernel and they agree *less* than
when only one of them did. Most of this family is thin-wire Yagis, where EK
should be a small correction.

#### 2. momwire 0.45.0, the quadrature split — bs1/bs2 on fat loops (momwire#965)

A bisect over all 19 releases from 0.34.0 to 0.50.0 pins a step at
0.44 → 0.45, the `n_qp_pair` split into cross-edge 8 / same-edge 4 (#743). It
touches the BSpline bases only, and its sign is mixed: on
`20m 65cm Circ 10mm Copper Magloop V.nec` bs1 degrades from 0.5773 to 1.0577
while **bs2 improves from 0.6184 to 0.0125** on the same deck and the same
change.

#### 3. momwire 0.48.0, on elevated finite-ground decks (momwire#964)

The same bisect pins a second step at 0.47 → 0.48, this one across all three
bases and carrying the largest numbers in the tail: `general 2-04` sin goes
0.0016 → 1.1731, the 6m Moxon 0.0082 → 0.9771. On `general 2-04` the solver
returns 3.34 + 156.07j against a −11.42 − 156.68j reference — the reactance
changes sign.

Widened past the bisect's own eight decks: taking the 24 decks with the
largest regressions that the kernel flag does *not* explain and re-solving
them at both releases, **30 of their 44 regressed pairs move at this one
step** and 14 are flat. The whole `general 2-xx` optimised-vertical series
moves together in `sin`, every member of it sitting below ΔΓ 0.01 at 0.47 —
near-exact agreement with nec2c — and between 0.5 and 1.2 at 0.48.

The release's headline feature is "a wire may now lie on the ground", and it
is **not** implicated: none of these decks has a wire at or below z = 0 (the
minima are 5.3 m to 9.0 m), and no advisory is emitted. By elimination from
the changelog the only numerical change in that release is one `perf` commit
to `_crossing_fill.py` whose own message states it is "an exact restriction,
not an approximation" and reports Z bit-identical on three decks. These decks
say otherwise on their geometry.

#### What is still open

The three causes do not cover the whole tail. 136 of the 272 pairs carry no
`EK` card at all, and the release boundaries are measured on 8 decks across all 19
releases plus 24 more at the 0.47/0.48 step, not across all 144 — a tail-wide
re-run at four releases was started and abandoned at a measured ~16 h, because
the regressed decks are the corpus's slowest. At least one deck
(`cebik-w4rnl/.../ch-11/11-2b.nec`, sin 0.0011 → 0.9550) is flat across every
release from 0.34 to 0.50, so its cause predates the range today's
antennaknobs can drive at all: the importer requires `momwire.networks`, which
does not exist before ~0.33, while the July baseline ran on ~0.14.

Reproducers for all three live in `scratch/1234-study/`.

A fourth hypothesis was tested and is **not confirmed**: momwire#959's finding
that dense collocation returns noise below ~0.3 × the kernel radius. Regressed
decks do sit closer to the limit (median min Δ/a 6.8 against 40.5 for
unchanged decks) but essentially none reach it — only 2.6 % fall below Δ/a = 2
and none below 0.3. That measurement covers 38 of the 144 decks, since the
parser reads plain `GW` cards only and much of this family is `GH`-generated,
and it does not model the equivalent radius of a jacketed conductor. It bounds
the question rather than settling it.

## Incidents

- **Wrong reference binary, caught before it mattered.** See Method. The
  lesson is that the reference deserves an md5 check at sweep start rather
  than trust in `PATH`; the bench script does not do this yet.
- **Neither run records the engine versions it used.** `_meta` carries the
  corpus, caps and nec2c md5 but no momwire or antennaknobs version, which is
  exactly the field needed to attribute a regression to a release. Filed.
- **NaN-poisoned quantiles.** See Method.

## Next

- **momwire#964** — 0.48.0 on elevated finite-ground decks. The largest
  numbers in the tail, and the release's only numerical change asserts it is
  exact.
- **momwire#965** — 0.45.0's quadrature split moving bs1 and bs2 in opposite
  directions on the same deck.
- **momwire#963** — the extended kernel disagreeing with a reference that was
  already using one.
- **momwire#962** — refuse rather than return `z = [inf, 0]`.
- **#1256** — record engine versions in `_meta`, and verify the nec2c md5
  rather than trusting `PATH`.
- Size the unattributed residue: 136 pairs carry no `EK` card, and the
  pre-0.34 breakages need an antennaknobs worktree at the July commit to
  reach at all.
- BSpline d=1's 7 GB peak against an 8 GB cap.
