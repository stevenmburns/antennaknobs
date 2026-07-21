# Basis-convergence census — sin vs BSpline d=2 (issue #477 follow-up)

**Date:** 2026-07-20
**Tool:** `scripts/bench_basis_convergence.py` (ladder N = 21/61/161/321,
free space, seg-cap 4000, RLIMIT 6 GB) + a targeted N = 641 top-up on the
no-mutual class. Measured with PR #481's radials fix applied (the two
`verticals` rows are meaningless without it).

## Question

The #477 diagnosis kept finding the same pattern anecdotally: BSpline d=2
already sits at the converged answer on meshes where sin/PyNEC are far from
it. Is that a defensible general statement, and where exactly does it hold?

## Method — the mutual-limit criterion

A single basis flat on its own ladder can be flat at the wrong value
(sterba_tl's pinned ports prove it: flat AND ~5 Ω of X from the
basis-agreed limit). So a design is only *scored* when the two bases agree
within 2 % at the finest common rung — the mutual limit Z\* (mean of the
two finest values). Against Z\* the census reports each basis's error at
N = 21 and its conv@N. Everything else lands in an explicit "no mutual
limit" list — the honest *cannot yet say* class, not a silent omission.

## Result — 91 designs

**66 mutual-limit, 24 no-mutual-limit, 1 incomplete** (elt_whip, over the
seg cap at every rung).

### The scored 66: bs2 converged at N=21 on 80 %

| | sin | bs2 |
|---|--:|--:|
| within 2 % of Z\* at N = 21 | 36/66 | **53/66** |
| conv@N ratio sin/bs2 | median 1.0× (44/66 tie at N=21) | max **15.3×** |

Two-thirds of the catalog (dipoles, loops, yagis, arrays) converges at
N = 21 on *both* bases — the advantage is not universal and the census says
so. It concentrates exactly on the port-fed and junction-heavy designs the
#459 feed-drift census flagged:

| design | Z\* | sin err @21 | bs2 err @21 | conv sin | conv bs2 |
|---|--:|--:|--:|--:|--:|
| doublet_ladder_tuner | 42.2−5.6j | 42.5 % | 0.9 % | 321 | 21 |
| dominator | 30.8+1.0j | 26.2 % | 7.3 % | 321 | 321 |
| challenger | 31.0+8.0j | 23.2 % | 1.5 % | 321 | 21 |
| pota_performer | 37.5+3.7j | 18.6 % | 3.2 % | 321 | 61 |
| skyloop_lmatch | 47.5−6.7j | 14.8 % | 0.4 % | 161 | 21 |
| triangular_skyloop | 113.9+1.0j | 12.9 % | 0.2 % | 161 | 21 |
| efhw_sloper | 52.6−3.1j | 11.2 % | 0.7 % | 161 | 21 |
| inverted_l / vertical (post-#481) | 17.3+0.3j / 22.1+0.2j | 4.5 / 3.9 % | 1.6 / 1.5 % | 161 | 21 |

Honest exceptions inside the scored class — both bases slow together
(physics-limited, not basis-limited): edz, lazy_h, vbeam, trap_dipole,
owa_yagi, and dominator's reactance (Z\* has X ≈ 1 Ω, inflating the
relative metric).

### The unscored 24: dominated by folded/fan junctions

Where the bases had NOT met by N = 321, the N = 641 top-up splits the class:

| design | apart @321 | apart @641 | verdict |
|---|--:|--:|---|
| folded_invvee | **515 %** | 63.6 % | closing — sin X −1188j → −173j racing toward the 223−30j bs2 held from N=21 |
| folded_invvee_balun | 96 % | 34.6 % | closing, same shape |
| inverted_l_tmatch | 7.2 % | 3.9 % | closing (sin lags, known) |
| short_dipole_loaded / jpole / zepp | 3–6 % | 2–4 % | slow-closing |
| trap_fan_dipole | 23.9 % | 25.9 % | **open** |
| twoband_fan_dipole | 11.4 % | 17.8 % | **open** |
| sterba_tl (pinned ports) | 2.3 % | 2.3 % | held open by the pins (unpinned, both bases meet at ~72.0−11.6j) |
| helix | 30.6 % | — | mesh is a design knob (ppt), ladder inapplicable |
| 11 designs (hentenna/hourglass families, fandipole, discone, moxon, bowtie, hexbeams, terminated_longwire, folded_invveearray) | 15–109 % | seg-capped | unresolved at affordable mesh |

The folded_invvee result is the strongest single data point in the study:
sin needs *thousands* of segments to resolve a folded element's
transmission-line mode and is still 64 % away at N = 641, while bs2's
coarse-mesh value is what sin is converging toward. The still-open fan
dipoles (multi-wire fan junctions) are the next thing to explain — filed
observations, not yet a diagnosis.

## Implications

1. **The claim is now defensible and scoped**: on feed/junction-
   discretization-limited designs — about a third of the catalog — bs2 at
   N = 21 sits within ~2 % of the mutual limit that sin needs 3–15× more
   segments to reach; and bs2 was immune to the graded-junction divergence
   PR #481 fixed. Where convergence is physics-limited (near-open, high-Q:
   the #478 class), bs2 tracks sin point-for-point and buys nothing.
2. **A wild-corpus scoring caveat**: nec2c shares sin's basis family. A
   bs1/bs2 ΔΓ against nec2c at a deck's native coarse mesh partly measures
   *correlated* sin-family error, not bs2 error — folded/fan-junction decks
   especially. Prior evidence in the same direction: #436 (bs2 converges
   2–3× coarser on closed loops).
3. **Workbench guidance seed**: when the convergence slider on a networked
   or junction-heavy design won't settle under sin/PyNEC, solve it on
   BSpline d=2 before concluding the design is at fault.

## Pointers

- #477 — diagnosis comment with the four-class decomposition of the
  feed-drift cluster; PR #481 (radials fix).
- #478 — the physics-limited class (zepp's 14 kΩ port belongs to it).
- #436 — basis-aware loop meshing (same direction, loops).
- Raw rows: session scratchpad `basis_census.jsonl` / `topup641.jsonl`
  (regenerate with the script; ~6 min for the main ladder on a laptop).
