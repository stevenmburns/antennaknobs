# momwire#677 phase 0 — the instruments

What remains here are the three tools that produced the #677 diagnosis. The
data they produced does not: it was 2.1 MB of CI dumps and licensed NEC-5
printouts, all of it recoverable, and none of it cited by any issue or by any
file in either repository.

## What #677 was

The residency gate diverged on decks 0116/0117 (the four-square pair) on CI
runners only. It was not a cache. The whole divergence was one line: a cold
process printed `NETWORK LOSS = 2.1316E-14 WATTS` and a warm one omitted it,
in 20 of 20 dump pairs across five CI runs.

The mechanism: those decks have a lossless transmission line, so `p_network`
is exactly zero, and printing-when-positive therefore tests **the sign of an
8-ULP crumb** — which moves with the machine and with process history, as heap
and BLAS rounding shift underneath it. Fixed in PR #721 by having the seam
floor its own presence decision.

## The tools

- `census.py` — the cache census that ruled out a module-level cache with an
  under-identifying key. Its finding: only pure memos grow, and there were
  zero cross-deck hits on the failing prefix (0015 → 0009 → 0001 → 0117).
- `warmrun.py` — the warm/cold harness that produced the dump pairs.
- `watch_verdict.sh` — watched main for the first post-merge `test-slow` run,
  which was the verdict this phase was waiting on.

## Getting the data back

- **CI dumps**: artifact `momwire-677-dumps` on momwire runs 33138357986,
  33185649317, 33200122019, 33266925010, 33267469402 — live until
  **2026-11-26/27**. Lesson worth keeping from this phase: those artifacts
  existed on main all along, so check for them BEFORE building diagnostics.
- **The printouts**: `census-*.out`, `warm-*.out`, `cold-*.out` and `hash-*.out`
  were licensed NEC-5 output for corpus decks 0001, 0009, 0015 and 0117. The
  decks are in `scratch/eznec-capture/`; the licensed engine regenerates the
  printouts from them.
