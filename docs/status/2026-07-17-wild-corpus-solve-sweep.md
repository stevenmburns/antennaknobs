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
