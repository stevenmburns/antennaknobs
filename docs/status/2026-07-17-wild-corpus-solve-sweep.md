# 2026-07-17 — wild-corpus solve sweep (3,146 decks, 4 engines, bounded)

## Goal

Issue #410, final leg: run every unique deck of the wild corpus
(`~/antennas/nec-wild/`, provenance per-source `MANIFEST.md`) through the
full impedance benchmark — nec2c reference on the original deck, then
PyNEC / Sinusoidal / BSpline d=1 / BSpline d=2 on the imported geometry —
under hard resource bounds: **300 s wall-clock per solve** and **8 GB
RLIMIT_AS** per solve subprocess (and per nec2c run).

Reference build (pinned, per the parse-census caveat): **vanilla nec2c
1.3.1**, `/usr/bin/nec2c`, md5 `050927160cecf7ee86db907dafac7bbe`. The
KJ7LNW 1.3 fork disagrees with it on some near-resonance decks; numbers in
this doc are only comparable against this exact binary.

Tooling (`scripts/bench_nec_corpus.py`, this branch): `--mem-limit-gb`
(RLIMIT_AS, MEM/TIME/GEO/ERR error taxonomy), TimeoutExpired containment,
content-md5 dedup in solve mode, corpus-relative row keys, and incremental
`.jsonl` output that doubles as a resume point. Full results:
`bench_out/wild-solve-2026-07-17.jsonl` (~5 MB, untracked).

## Headline census

**3,146 unique decks → 1,875 scored against nec2c. Zero sweep crashes
after hardening, zero engine crashes unaccounted for, one memory-cap trip
(the bound is real), 38 momwire-timeout decks — all one root cause, now
understood and filed.**

| outcome | decks | note |
|---|--:|---|
| scored vs nec2c | **1,875** | full 4-engine comparison |
| parse-rejected | 260 | exactly the parse census's designed rejections (91.7% parse rate) |
| parsed, no nec2c reference | 1,011 | 978 no impedance block (no EX / scattering / report-only decks), 32 nec2c faulty-card aborts, 1 nec2c timeout |

Ground mix of the scored decks: 1,162 free / 533 Sommerfeld / 153 PEC /
27 refl-coef. Flags: 190 partial-network (`n`), 31 unsupported-ground (`g`).

## Agreement rollup (clean decks: supported ground, full network)

Feed-0 reflection-coefficient distance ΔΓ = |Γ_eng − Γ_nec2c|, Γ at 50 Ω:

| engine | n | median | p90 | ≤0.01 | ≤0.05 | ≤0.2 |
|---|--:|--:|--:|--:|--:|--:|
| PyNEC | 1,590 | **0.0002** | 0.0077 | 91% | 96% | 98% |
| Sinusoidal | 1,620 | 0.0046 | 0.0337 | 65% | 93% | 97% |
| BSpline d=2 | 1,623 | 0.0084 | 0.1326 | 52% | 79% | 92% |
| BSpline d=1 | 1,623 | 0.0251 | 0.1977 | 23% | 68% | 89% |

The engine ordering from the 82-deck xnec2c benchmark holds at 20× the
scale across at least four authoring dialects — strong evidence the
import pipeline is faithful and the momwire deltas are solver physics
(mesh-convergence and basis effects), not translation bugs.

## Resource-bound outcomes

- **Memory**: one deck tripped the 8 GB cap (`Tutorial-2/ch-5/5-8.nec`,
  BSpline d=1 and d=2 → MEM). Biggest successful solves peaked at
  4.5 GB (bs1) — the cap has real headroom yet actually protects.
- **Time**: solve medians are ~10–20 ms across engines (p90 ≤ 2 s);
  nec2c median 0.01 s, max 166 s. The 300 s cap only ever fired on the
  anchor family below and one nec2c sweep-heavy deck.
- **Cost of the bounds**: the 38 timeout decks burned ~9.5 h of the
  ~15 h total wall time — bounded, resumable, and now avoidable (below).

## The one big finding: remote TL-anchor wires × Sommerfeld (38 decks)

Every momwire timeout (38 decks — all three momwire solvers burn the full
300 s while PyNEC solves in <1 s) is the same classic NEC modeling trick:
a tiny wire parked ~100–500 λ away so a `TL` card has a far-end segment
(open/shorted stub emulation), or its dual, a remote EX-driven source
rack fanned out over TLs — combined with `GN 2` Sommerfeld ground.

Minimal repro (no TL needed — it is pure matrix assembly): a 51-seg
dipole + one 1-seg wire at 2.1 km solves in 1.27 s without the remote
wire, >60 s with it, whether the separation is lateral or vertical;
PyNEC does the same geometry in 0.07 s. Filed as **momwire#157**
(kernel: likely far outside the Sommerfeld interpolation grid →
per-element brute quadrature).

Import-side fix filed as **#427** and implemented in **PR #428**
(review measurements posted there): translate anchor wires to
`PortVirtual` circuit terminations. PyNEC proves the anchors are
electrically negligible (Δz ≈ 1 Ω on the repro). With the review's
relaxed "electrically tiny" gate (`extent < λ/20` instead of
`n_seg == 1`), 16 of the 38 virtualize; the remaining decks are the
remote-*source* variant (EX-driven racks, e.g. K8UR's 16 phased sources
on a 16-seg wire at 16 km) needing `Driven`-on-`PortVirtual` as a
follow-up. Full deck list in the appendix.

## Accuracy outliers to triage (clean decks, PyNEC ΔΓ > 0.2 — 17 decks)

Worst cases, all with the *engines agreeing with each other* against
nec2c in the ones spot-checked, suggesting deck-semantics gaps rather
than solver error:

| ΔΓ | deck | suspicion |
|--:|---|---|
| 1.59 | 4nec2/zz_MiniNec/HFshort/TopCap75.nec | MiniNec-dialect ground? |
| 1.28 / 1.21 | Verticals/{10,7}-dpl-spiralhats-sngnd.nec | dense spiral hats — segmentation semantics |
| 1.13 | necpp/salt_ground.nec | extreme ground params |
| 0.93 | Tutorial-2/ch-11/11-4.nec | — |
| 0.79 | qantenna/zepp-80m.nec | — |

These 17 (0.9% of scored) are the residue worth individual study; the
list is derivable from the JSON (`dgamma > 0.2`, clean flags).

## Incidents (sweep hardening that came out of this run)

1. **UnicodeDecodeError at deck 1,666**: nec2c emitted a raw `0xff` into
   its own output file; the strict `read_text()` killed the sweep 8 h in.
   The `.jsonl` resume point restored all 1,665 rows; fix: tolerant
   decoding everywhere + a per-deck catch-all so no single deck can end a
   sweep. Lesson generalized: **wild input contaminates outputs too** —
   every byte-stream in the loop needs the tolerant path, not just decks.
2. **Monitor self-match**: the progress watcher's `pgrep -f` pattern
   matched its own shell, reporting "progress" for 30+ min after the
   death. Liveness checks must target a recorded PID, not a pattern.

## Caveats

- nec2c is the *reference*, not truth: the 32 faulty-card decks and the
  17-outlier residue may include nec2c-side quirks (see the 1.3.1 vs
  KJ7LNW disagreement note in the parse census).
- Engine solves ran at the single frequency nec2c reported first;
  sweep-heavy decks are compared at one point only.
- The 190 `n`-flagged decks (inexpressible LD/TL/NT pieces) are scored
  best-effort and excluded from the clean rollup.

## Next

1. Land PR #428 (+ relaxed gate) → delete the 38 timeout rows from the
   jsonl → resume-re-run just that family for scored ΔΓ values.
2. `Driven`-on-`PortVirtual` follow-up for the remote-source variant.
3. momwire#157 kernel hardening (benefits genuinely large structures).
4. Triage the 17-deck outlier residue as its own errand.

## Addendum (2026-07-18): the anchor family is fully resolved

Both fixes landed the next day — PR #428 (anchor virtualization, merged
with the `n_seg == 1` gate) and momwire `57a8b22` ("cap grid r1_max to
bound far-pair fill", momwire#157; repro went >60 s → 4.27 s with the
impedance matching the anchor-free control exactly). The 38 timeout rows
were deleted from the jsonl and the family re-run via the resume path on
the fixed stack:

**38/38 decks now solve and score — zero timeouts, zero failures.**
11 decks virtualized their anchors (`v` flag); the rest — including the
K8UR 16-segment source racks at 16 km — solve as real geometry through
the capped Sommerfeld kernel.

| engine | n | median ΔΓ | p90 | max |
|---|--:|--:|--:|--:|
| PyNEC | 38 | 0.0003 | 0.0035 | 0.115 |
| Sinusoidal | 38 | 0.0008 | 0.0167 | 0.017 |
| BSpline d=2 | 38 | 0.0053 | 0.0185 | 0.021 |
| BSpline d=1 | 38 | 0.0115 | 0.0331 | 0.052 |

The family agrees with nec2c *better* than the corpus at large (these
are electrically small HF arrays — friendly geometry once the kernel
stops brute-forcing 100 λ+ pair integrals). Wall-clock for the whole
family: ~25 min (was ~9.5 h of bounded timeouts); slowest deck
5r4-2x4elphased-K8UR at 506 s summed across the four engines, each
within the 300 s cap. `bench_out/wild-solve-2026-07-17.jsonl` is updated
in place (pre-fix rows preserved in `*.pre157`); headline tables above
describe the original bounded run and deliberately still exclude
`v`-flagged decks from the clean rollup.

Still open from the family: the relaxed "electrically tiny" anchor gate
(review on #428 — an economy, no longer a blocker) and
`Driven`-on-`PortVirtual` for remote-source decks.

## Addendum 2 (2026-07-18): z₀ sensitivity of the ΔΓ metric

The scoring uses a fixed Z₀ = 50 Ω for both engine and reference Γ. That
can never *create* disagreement (Γ is injective in Z: ΔΓ = 0 iff the
impedances match, for any z₀), but it can *mask* it: sensitivity goes as
2z₀/|Z + z₀|², so a deck with |Z| ≫ 50 Ω compresses a large absolute Z
error into a small ΔΓ. Exposure in this corpus: median |Z_ref| = 59 Ω
(mostly near-matched designs, where 50 Ω is most sensitive), but 142
scored decks sit above 500 Ω and 31 above 5 kΩ.

Since both complex impedances are kept in the jsonl, re-scoring at a
per-deck matched z₀ = |Z_ref| is pure post-processing. Clean decks:

| engine | median @50 Ω | median @matched | p90 @50 Ω | p90 @matched | moved > 0.05 |
|---|--:|--:|--:|--:|--:|
| PyNEC | 0.0002 | 0.0003 | 0.008 | 0.011 | 19 |
| Sinusoidal | 0.0045 | 0.0060 | 0.033 | 0.043 | 54 |
| BSpline d=2 | 0.0074 | 0.0106 | 0.109 | 0.169 | 160 |
| BSpline d=1 | 0.0225 | 0.0325 | 0.151 | 0.245 | 207 |

Conclusions:

- The import-validation headline (PyNEC ≈ nec2c) is z₀-robust. Exactly
  **one** deck is hidden at 50 Ω — fine at ΔΓ 0.006, but 0.28 at matched
  z₀: `arrl/cebik-models/Phased-Arrays/7-2xhalfwldr+6parguy-sngnd.nec`
  (|Z_ref| = 6.3 kΩ). It joins the outlier-triage errand, making that
  list **18 decks**.
- The momwire ranking is flattered by the 50 Ω choice: the BSpline tails
  are ~1.6× worse at matched z₀, because the high-|Z| decks where their
  mesh-convergence error is largest are exactly the ones a 50 Ω metric
  down-weights.
- If ΔΓ ever backs an acceptance *gate*, score it at matched z₀ (or dual
  50 Ω + matched) — the rescore is free.

## Appendix: the 38 momwire-timeout decks

All `arrl/cebik-models/` unless noted:

Phased-Arrays: 14-shortel-stubs-50-N7CL, 14-zlsporig-1-ZL3MH,
18-shortel-stubs-50-N7CL, 1r8-2x4elphased-K8UR, 1r8-4elphased-lowbend-K8UR,
1r8-4elphased-midelbend-K8UR, 21-shortel-stubs-50-N7CL, 21-zlsporig-1-ZL3MH,
24-shortel-stubs-50-N7CL, 28-shortel-stubs-50-N7CL,
28-shortel-stubstack-50-N7CL, 28-zlsp-udp-75-W4RNL, 28-zlsporig-1-ZL3MH,
3r6-2x4elphased-K8UR, 3r6-4elphased-lowbend-K8UR,
3r6-4elphased-midelbend-K8UR, 3r6-phasedrect-10-N2DT, 5r4-2x4elphased-K8UR,
5r4-4elphased-lowbend-K8UR, 5r4-4elphased-midelbend-K8UR ·
Quads: 18-3elquad-14-reversible-AA2NN · VHF-UHF: 50-lazyH-phasedarray ·
Verticals: 10-3elwireparasitic-sngnd, 10-hsbeam-12, 3r6-hsbeam-reverible-12,
7-3elwireparasitic-sngnd, 7-hsbeam-12 · Wire-Arrays: 10-3elYagi-14,
21-coledz-12, 21-coledzlazyh-12, 3r6-3elYagi-14, 3r9-2elYagi-reflload-14,
3r9-3elYagi-14, 5r4-moxrect-reversible-12-AA2NN, 7-2eldelta-12-K4TX,
7-3elYagi-14, 7-moxrect-reversible-12-AA2NN ·
opensource: sokyrad/unsorted/10m efhw narrow rect 28.4mhz.nec

## Addendum 3 (2026-07-18): the dialect-rescue arc — 853 decks gain references

The census's biggest bucket — 1,011 decks with no nec2c reference — was
mostly *dialect*, not physics. Four changes landed in one day
(PRs #441, #443, #445, #446; issues #439, #442, #444):

1. **`resolve_sy`** (nec_import): SY symbols, `#AWG` gauges, quote
   comments, fused mnemonics → plain NEC-2 text, round-trip
   parse-identical on all parseable decks. The bench retries the nec2c
   reference on prepared text whenever the original run fails, plus two
   run-request quirks 4nec2 leaves to its GUI: an appended `XQ` (project
   decks carry no execute request) and the FR NFRQ=0 → 1 spec default.
2. **EX 6 current sources** (network + import + bench): MNA
   `DrivenCurrent` termination; nec2c misparses type 6 as a plane wave,
   so the reference uses the voltage-behind-R_BIG emulation with R_BIG
   subtracted back out. 61 of the 63 blocked decks now score.
3. **LD 6 LC-traps**: F1 is the coil's unloaded Q (0 → 100), converted
   to parallel RLC with R_p = Q·ωL at the initial FR frequency — the
   formula confirmed by 4nec2's own converted-load table on MultiTrap
   (whose FR sits far off trap resonance, the discriminating case).
4. **GN 3 = MiniNec-style ground → pec**: nec2c lands type 3 in its PEC
   branch bit-for-bit; the bench had been solving those 70 decks in free
   space *and counting them clean* — TopCap75's headline ΔΓ 1.59 was
   this artifact (0.09 over pec). Unknown IPERF now flags unclean.

### Final census (content-unique corpus, all references pinned nec2c 1.3.1)

| outcome | decks | was |
|---|--:|--:|
| scored, verbatim reference | 1,875 | 1,875 |
| scored, resolved/prepared reference (`r` flag) | **853** | 0 |
| parse-rejected (plane wave, patches, GF, taper, ...) | 197 | 260 |
| no reference (no EX, LD 7 insulation (#447), exotic) | 221 | 1,011 |
| **total scored** | **2,728 (87%)** | 1,875 (60%) |

### Agreement, by cohort (clean flags: supported ground, full network, no `v`)

Verbatim-reference cohort (unchanged baseline):

| engine | n | median | p90 | ≤0.01 | ≤0.05 | ≤0.2 |
|---|--:|--:|--:|--:|--:|--:|
| PyNEC | 1,684 | 0.0002 | 0.0085 | 90% | 96% | 98% |
| Sinusoidal | 1,733 | 0.0046 | 0.0341 | 65% | 92% | 97% |
| BSpline d=2 | 1,736 | 0.0090 | 0.1360 | 51% | 78% | 92% |
| BSpline d=1 | 1,736 | 0.0259 | 0.2201 | 23% | 68% | 88% |

Resolved-reference cohort (`r`; separated because resolution and engines
share the SY evaluator — independently validated, see below):

| engine | n | median | p90 | ≤0.01 | ≤0.05 | ≤0.2 |
|---|--:|--:|--:|--:|--:|--:|
| PyNEC | 782 | 0.0003 | 0.0126 | 84% | 92% | 95% |
| Sinusoidal | 837 | 0.0005 | 0.0371 | 58% | 87% | 93% |
| BSpline d=2 | 832 | 0.0512 | 0.1436 | 26% | 54% | 76% |
| BSpline d=1 | 833 | 0.0531 | 0.1584 | 11% | 45% | 74% |

The r-cohort's PyNEC agreement matching the verbatim cohort is itself
evidence the resolution is faithful. The BSpline medians degrade because
the SY population is dominated by electrically small VHF/UHF loops,
helices and meander dipoles (g1ojs) — the known basis-convergence class
(#436), not a resolution artifact. Families: EX 6 emulated 61 scored
(PyNEC median 0.0042), LD 6 traps 24, GN 3 grounds 42.

### Independent cross-validation (4nec2 on Windows, native)

A from-scratch reimplementation of 4nec2's SY evaluator (built against
4nec2's own Symbols.txt, not our code) matched our resolved geometry on
all 11 stratified spot-check decks to ≤4.2e-4 relative — and the diff is
discriminating: radians-trig or log10 variants blow errors to 190–1200%.
The LD 6 → LD 1 conversion reproduces 4nec2's GUI impedances headless to
<0.1%. And 4nec2's Fortran-lineage engine adjudicated all six triaged
outliers **in nec2c's favor**, reclassifying them:

| deck | verdict → issue |
|---|---|
| TopCap75 | bench GN 3 mapping (fixed, PR #446) |
| 10/7-dpl-spiralhats | import-geometry suspect, both engines agree wrong (#450) |
| salt_ground | engine gap at extreme ground (εr 81, σ 5) |
| ch-11/11-4, 7-2xhalfwldr | PyNEC/nec2++ real part ~7–8× off on high-|Z| feeds (#448) |
| zepp-80m | shared TL translation is the artifact — both true NEC-2s agree on −41 kΩ (#449) |

Post-arc outlier census (PyNEC ΔΓ > 0.2, clean flags, both cohorts):
51 decks, the largest identifiable classes being the TL-semantics family
(#449 — 4SQTL, CardTL, DipTL, Coax, zepp, ZLTROM) and the
parasitic-vertical/spiral-hat geometry family (#450).

### Incidents

- Two sweep processes briefly raced on the results file (one launched
  outside the session), producing 617 adjacent duplicate rows — deduped
  keeping the best row per deck. Content-duplicate corpus paths can also
  re-record under their alias when reruns interleave (21 alias rows
  dropped in the final numbers). Lesson: one writer per jsonl, enforced
  by checking `pgrep` before every launch, and analyze content-deduped.
- The GN 3 bug class existed because unknown ground types passed as
  *clean* comparisons. Anything unknown must degrade loudly.

Follow-ups filed: LD 7 insulation (82 decks, #447), PyNEC high-|Z|
divergence (#448), TL-semantics family (#449), spiral-hat geometry
(#450). This closes #439, #442 and #444.
